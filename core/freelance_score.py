# ===== core/freelance_score.py =====

import torch
from typing import Optional


# ─────────────────────────────────────────────────────────
# Detection
# ─────────────────────────────────────────────────────────

_KEYWORDS = {"freelance", "freelancer", "freelancing", "part-time", "part time"}


def is_freelance_job(job: dict) -> bool:
    """
    Title-only detection. Naukri's employmentType / jobType fields are
    unreliable (can say 'Full Time, Permanent' for genuine freelance gigs).
    shortDescription / staticUrl / applyRedirectUrl are excluded — they cause
    high false-positive rates (e.g. "managing freelancers", company name
    "Freelancer" in URL slug, freelance platforms mentioned as tools).

    Checks (any single hit = confirmed freelance):
        1. Scraped job title
        2. v4 title
    """
    jd = job.get("v4_data", {}).get("jobDetails", {})

    candidates = [
        job.get("Job Title", ""),
        jd.get("title", ""),
    ]

    for text in candidates:
        if not text:
            continue
        lower = text.lower()
        for kw in _KEYWORDS:
            if kw in lower:
                return True

    return False


# ─────────────────────────────────────────────────────────
# Scorer
# ─────────────────────────────────────────────────────────

class FreelanceScorer:
    """
    Scores freelance / part-time jobs.

    Weights (must sum to 1.0):
        skill_match      0.50  — bidirectional: forward + reverse top-10 coverage
        role_alignment   0.20  — job title/role domain vs resume summary (domain gate)
        semantic         0.20  — JD ↔ resume holistic fit
        remote_mode      0.05  — remote/hybrid preference
        early_applicant  0.05  — competition freshness

    Intentionally ignores: education, location, experience years.
    No score floor — ALL detected freelance jobs are applied to (after sem gate),
    sorted highest → lowest score. Cross-encoder reranker runs on top-60 in main.py.
    """

    WEIGHTS = {
        "skill_match":     0.50,
        "role_alignment":  0.20,
        "semantic":        0.20,
        "remote_mode":     0.05,
        "early_applicant": 0.05,
    }

    # JobBERT cosine for semantically close but non-identical skills sits ~0.70-0.78
    SKILL_THRESHOLD = 0.70

    # Top-N resume skills for reverse coverage (first N = core domain skills)
    REVERSE_TOP_N = 10

    # Section weights for semantic: experience + projects matter most
    SECTION_WEIGHTS = {
        "experience":     1.8,
        "projects":       1.5,
        "skills":         1.0,
        "summary":        0.8,
        "certifications": 0.5,
        "education":      0.2,
    }

    def score(self, resume, job: dict, model=None) -> dict:
        signals = {
            "skill_match":     self._skill_match(resume, job),
            "role_alignment":  self._role_alignment(resume, job),
            "semantic":        self._semantic(resume, job),
            "remote_mode":     self._remote_mode(job),
            "early_applicant": self._early(job),
        }

        raw = sum(self.WEIGHTS[k] * v for k, v in signals.items())
        raw = self._knockouts(raw, signals)

        return {
            "total_score":    round(raw * 100, 1),
            "grade":          self._grade(raw),
            "breakdown":      {k: round(v * 100, 1) for k, v in signals.items()},
            "missing_skills": self._missing_skills(job),
            "salary_insight": None,   # freelance rarely discloses salary on Naukri
            "flags":          self._flags(signals, job),
            "apply_priority": self._priority(raw),
        }

    # ── Signal methods ────────────────────────────────────────────────────

    def _skill_match(self, resume, job: dict) -> float:
        req_emb  = job.get("_req_emb")
        pref_emb = job.get("_pref_emb")

        if req_emb is None or resume.skills_emb is None:
            naukri_ratio = job.get("naukri_skill_ratio")
            return naukri_ratio if naukri_ratio is not None else 0.3

        F = torch.nn.functional

        # ── Forward: fraction of job's required skills found in resume ──────
        sim_fwd     = F.cosine_similarity(req_emb.unsqueeze(1), resume.skills_emb.unsqueeze(0), dim=-1)
        req_matched = (sim_fwd.max(dim=1).values >= self.SKILL_THRESHOLD).float().mean().item()

        # ── Reverse: fraction of resume's top-N core skills needed by this job ──
        # Catches: "Material Scientist with Python" → Python is in resume top-N,
        # but material science dominates required skills → reverse near 0
        core_emb     = resume.skills_emb[:self.REVERSE_TOP_N]
        sim_rev      = F.cosine_similarity(req_emb.unsqueeze(1), core_emb.unsqueeze(0), dim=-1)
        core_covered = (sim_rev.max(dim=0).values >= self.SKILL_THRESHOLD).float().mean().item()

        # Bidirectional: forward weighted more, reverse is domain gate
        embedding_score = 0.60 * req_matched + 0.40 * core_covered

        # Preferred skills: small bonus only when base score already decent
        if pref_emb is not None and embedding_score > 0.25:
            sim_pref   = F.cosine_similarity(pref_emb.unsqueeze(1), resume.skills_emb.unsqueeze(0), dim=-1)
            pref_bonus = (sim_pref.max(dim=1).values >= self.SKILL_THRESHOLD).float().mean().item()
            embedding_score = min(1.0, embedding_score + 0.08 * pref_bonus)

        # Mismatch penalty
        mismatch_skills  = [s.strip() for s in (job.get("skill_mismatch") or "").split(",") if s.strip()]
        mismatch_penalty = min(0.20, len(mismatch_skills) * 0.04)

        return max(0.0, embedding_score - mismatch_penalty)

    def _role_alignment(self, resume, job: dict) -> float:
        """
        Cosine similarity between job's role context and resume summary + skills.
        Gates domain mismatches: "Hindi Translator" vs "AI Engineer resume" → near 0.
        """
        role_emb     = job.get("_role_emb")
        section_embs = resume.section_embs

        if role_emb is None or section_embs is None:
            return 0.5

        summary_emb = section_embs.get("summary")
        skills_emb  = section_embs.get("skills")

        sims = []
        if summary_emb is not None:
            sims.append(0.6 * torch.nn.functional.cosine_similarity(summary_emb, role_emb).item())
        if skills_emb is not None:
            sims.append(0.4 * torch.nn.functional.cosine_similarity(skills_emb, role_emb).item())

        if not sims:
            return 0.5

        raw = sum(sims)
        # Rescale [0.22, 0.65] → [0, 1]
        # Freelance roles are more varied so ceiling is lower than SmartScorer
        rescaled = (raw - 0.22) / (0.65 - 0.22)
        return max(0.0, min(1.0, rescaled))

    def _semantic(self, resume, job: dict) -> float:
        jd_emb   = job.get("_jd_emb")
        role_emb = job.get("_role_emb")

        if jd_emb is None or resume.section_embs is None:
            return 0.0

        weighted_sims, total_w = [], 0.0
        for section, sec_emb in resume.section_embs.items():
            sim_jd   = torch.nn.functional.cosine_similarity(sec_emb, jd_emb).item()
            sim_role = (
                torch.nn.functional.cosine_similarity(sec_emb, role_emb).item()
                if role_emb is not None else sim_jd
            )
            sim = 0.75 * sim_jd + 0.25 * sim_role
            w   = self.SECTION_WEIGHTS.get(section, 1.0)
            weighted_sims.append(sim * w)
            total_w += w

        if not weighted_sims:
            return 0.0

        raw_sim  = sum(weighted_sims) / total_w
        # Rescale [0.22, 0.55] → [0, 1]
        rescaled = (raw_sim - 0.22) / (0.55 - 0.22)
        return max(0.0, min(1.0, rescaled))

    def _remote_mode(self, job: dict) -> float:
        mode = job.get("work_mode", "").lower()
        if "remote" in mode: return 1.0
        if "hybrid" in mode: return 0.6
        if "office" in mode: return 0.2
        return 0.5

    def _early(self, job: dict) -> float:
        return 1.0 if job.get("early_applicant") else 0.3

    def _knockouts(self, score: float, signals: dict) -> float:
        # Hard domain mismatch: role doesn't align AND skill overlap low → strong penalty
        if signals["role_alignment"] < 0.25 and signals["skill_match"] < 0.20:
            score *= 0.30

        # Both embedding signals weak → moderate penalty
        elif signals["skill_match"] < 0.15 and signals["semantic"] < 0.15:
            score *= 0.50

        return score

    # ── Output helpers ────────────────────────────────────────────────────

    def _missing_skills(self, job: dict) -> list:
        raw = job.get("skill_mismatch") or ""
        return [s.strip() for s in raw.split(",") if s.strip()]

    def _grade(self, score: float) -> str:
        if score >= 0.75: return "A — Strong Freelance Match"
        if score >= 0.55: return "B — Good Freelance Match"
        if score >= 0.35: return "C — Moderate Freelance Match"
        return "D — Weak Freelance Match"

    def _priority(self, score: float) -> str:
        if score >= 0.70: return "🔥 Apply Immediately"
        if score >= 0.50: return "✅ Apply Today"
        if score >= 0.30: return "📋 Apply This Week"
        return "⏭️ Low Priority"

    def _flags(self, signals: dict, job: dict) -> list:
        flags = []
        missing = self._missing_skills(job)
        if missing:
            flags.append(f"Missing skills: {', '.join(missing)}")
        if signals["role_alignment"] < 0.30:
            flags.append("Weak domain alignment — verify job relevance")
        if signals["remote_mode"] < 0.4:
            flags.append("On-site role — less flexible")
        if job.get("apply_count", 0) > 100:
            flags.append(f"High competition: {job['apply_count']} applicants")
        return flags
