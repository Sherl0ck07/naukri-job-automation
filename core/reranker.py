# ===== core/reranker.py =====

import logging
import torch
import numpy as np
from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)

# BAAI/bge-reranker-base: trained on diverse text pairs, strong at domain
# relevance judgment — better than MS-MARCO models for job/resume matching.
RERANKER_MODEL = r"C:\models\bge-reranker-base"

_cross_encoder: CrossEncoder = None
_load_failed:   bool          = False


def _load_model(device: str):
    global _cross_encoder, _load_failed
    if _load_failed:
        return None
    if _cross_encoder is not None:
        return _cross_encoder
    try:
        logger.info(f"Loading cross-encoder: {RERANKER_MODEL}")
        import os
        local_path = r"C:\models\bge-reranker-base"
        if not os.path.isdir(local_path):
            logger.info(f"Model not found locally — downloading to {local_path}...")
            from huggingface_hub import snapshot_download
            snapshot_download(repo_id="BAAI/bge-reranker-base", local_dir=local_path)
            logger.info("Download complete.")
        _cross_encoder = CrossEncoder(
            local_path,
            device=device,
            max_length=512,
        )
        logger.info("Cross-encoder loaded.")
    except Exception as e:
        logger.warning(
            f"Cross-encoder load failed ({e}). "
            f"Run: python -c \"from sentence_transformers import CrossEncoder; "
            f"CrossEncoder('{RERANKER_MODEL}')\" once with internet to cache the model. "
            f"Reranker disabled for this run."
        )
        _load_failed = True
    return _cross_encoder


def _build_resume_text(resume_summary: str, resume_skills: list) -> str:
    skills_str = ", ".join(resume_skills[:20]) if resume_skills else ""
    # First 3 sentences of summary capture target role without noise
    summary_short = ". ".join(resume_summary.split(".")[:3]).strip()
    return f"{summary_short}\nCore skills: {skills_str}"


def _build_job_text(job: dict) -> str:
    title    = job.get("Job Title", "")
    skills   = job.get("skills", [])
    # Try to get JD snippet from v4 shortDescription
    jd_snip  = job.get("v4_data", {}).get("jobDetails", {}).get("shortDescription", "")
    skills_str = ", ".join(skills[:15]) if skills else ""
    parts = [f"Role: {title}"]
    if skills_str:
        parts.append(f"Required skills: {skills_str}")
    if jd_snip:
        parts.append(jd_snip[:300])
    return "\n".join(parts)


def rerank_jobs(
    resume_summary: str,
    resume_skills:  list,
    jobs:           list,
    device:         str = "cpu",
    top_n:          int = 60,
) -> list:
    """
    Cross-encoder reranks top_n jobs for primary role-domain fit.

    Builds (resume_text, job_text) pairs, runs BAAI/bge-reranker-base,
    blends cross-encoder logit with embedding score, re-sorts.
    Jobs beyond top_n are appended unchanged (already low score).
    """
    if not jobs:
        return jobs

    to_rerank = jobs[:top_n]
    tail       = jobs[top_n:]

    model = _load_model(device)
    if model is None:
        logger.warning("Reranker unavailable — returning jobs in original order.")
        return jobs

    resume_text = _build_resume_text(resume_summary, resume_skills)
    pairs       = [(resume_text, _build_job_text(j)) for j in to_rerank]

    logger.info(f"Cross-encoder reranking {len(pairs)} jobs...")

    with torch.no_grad():
        logits = model.predict(pairs, show_progress_bar=False)

    # bge-reranker raw logits: higher = more relevant, no fixed range
    # Normalize to [0, 1] via sigmoid
    scores_norm = 1.0 / (1.0 + np.exp(-np.array(logits, dtype=np.float32)))

    for job, ce_score in zip(to_rerank, scores_norm):
        emb_score = (job.get("total_score") or 0) / 100.0
        # Blend: embeddings 60%, cross-encoder 40%
        blended = 0.60 * emb_score + 0.40 * float(ce_score)

        job["ce_score"]      = round(float(ce_score) * 100, 1)
        job["blended_score"] = round(blended * 100, 1)

    # Re-sort: skillMatch bucket first, then blended_score desc
    to_rerank.sort(
        key=lambda x: (
            not x.get("skillMatch", False),
            -(x.get("blended_score") or 0),
        )
    )

    top = to_rerank[0]
    logger.info(
        f"Rerank done. Top: [{top.get('blended_score')}] "
        f"ce={top.get('ce_score')} | {top.get('Job Title','')[:55]}"
    )

    return to_rerank + tail
