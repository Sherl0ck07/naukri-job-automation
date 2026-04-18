# ============= score.py =============

import re
import torch
import PyPDF2
from bs4 import BeautifulSoup
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────
# Original helpers
# ─────────────────────────────────────────────────────────

def extract_text_from_pdf(path: str) -> str:
    text = []
    with open(path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text.append(page_text)
    return "\n".join(text)


def chunk_text(text: str, max_tokens=200):
    sentences = text.split(".")
    chunks, current = [], []
    for s in sentences:
        current.append(s)
        if len(" ".join(current).split()) >= max_tokens:
            chunks.append(" ".join(current))
            current = []
    if current:
        chunks.append(" ".join(current))
    return chunks


def embed(model, texts):
    if isinstance(texts, str):
        texts = [texts]
    return model.encode(
        texts,
        convert_to_tensor=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )


# ─────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────

@dataclass
class ResumeProfile:
    skills: list
    total_experience_years: float
    sections: dict
    education_level: str
    location: str
    preferred_work_mode: str
    full_text: str
    willing_to_relocate: bool = True

    # ── Pre-encoded tensors (populated by precompute_resume_embeddings) ──
    skills_emb: Optional[object] = None          # (n_skills, D)
    section_embs: Optional[dict] = None          # {section_name: (1, D)}


def parse_job_data(listing: dict, v3: dict, v4: dict) -> dict:
    v3 = v3 or {}
    v4 = v4 or {}
    jd = v4.get("jobDetails", {})
    ab = v4.get("ambitionBoxDetails", {})

    skills_other     = [s["label"] for s in (jd.get("keySkills") or {}).get("other") or []]
    skills_preferred = [s["label"] for s in (jd.get("keySkills") or {}).get("preferred") or []]
    if not skills_other:
        skills_other = listing.get("skills") or []

    raw_html = jd.get("description", listing.get("job_description", ""))
    jd_text  = BeautifulSoup(raw_html, "html.parser").get_text(" ", strip=True) if raw_html else ""
    if not jd_text:
        jd_text = listing.get("job_description", "")

    min_exp = jd.get("minimumExperience") or _parse_exp_range(listing.get("experience_range", ""))[0]
    max_exp = jd.get("maximumExperience") or _parse_exp_range(listing.get("experience_range", ""))[1]

    apply_count  = jd.get("applyCount") or _parse_applicants(listing.get("applicants_text", ""))
    created_date = jd.get("createdDate")
    age_days     = _compute_age_days(created_date) if created_date else _parse_age_days(listing.get("age", ""))

    ab_salaries  = ab.get("salaries", {})
    salary_avg   = float(ab_salaries.get("AverageCtc", 0) or 0)
    salary_min   = float(ab_salaries.get("MinCtc", 0) or 0)
    salary_max   = float(ab_salaries.get("MaxCtc", 0) or 0)

    company_rating = float(v4.get("jdBrandingDetails", {}).get("overallRating", 0) or 0)
    company_tags   = v4.get("jdBrandingDetails", {}).get("tags", [])

    wfh_type  = str(jd.get("wfhType", ""))
    work_mode = {"0": "office", "1": "remote", "2": "hybrid"}.get(wfh_type, listing.get("work_mode", "").lower())

    # ── FIX 1: keyskillsCount is BINARY (0 or 1), not a continuous ratio ──
    # keyskillsCount=0 means Naukri didn't index a match — treat as None (no signal)
    # keyskillsCount=1 means Naukri found a match — treat as soft boost (0.7), not 1.0
    raw_keyskills = v3.get("Keyskills", listing.get("keyskillsCount", None))
    if raw_keyskills is None:
        naukri_skill_ratio = None          # truly missing
    else:
        raw_val = float(raw_keyskills)
        if raw_val == 0.0:
            naukri_skill_ratio = None      # no-match flag, not a ratio — treat as missing
        else:
            naukri_skill_ratio = 0.7       # matched flag → soft positive boost

    return {
        "skills_required":          skills_other,
        "skills_preferred":         skills_preferred,
        "skill_mismatch":           v3.get("skillMismatch", listing.get("skillMismatch", "")),
        "naukri_skill_ratio":       naukri_skill_ratio,
        "min_experience":           min_exp,
        "max_experience":           max_exp,
        "jd_text":                  jd_text,
        "role_title":               jd.get("title", listing.get("Job Title", "")),
        "job_role":                 jd.get("jobRole", ""),
        "role_category":            jd.get("roleCategory", ""),
        "functional_area":          jd.get("functionalArea", ""),
        "industry":                 jd.get("industry", ""),
        "education_ug":             jd.get("education", {}).get("ug", []),
        "education_pg":             jd.get("education", {}).get("pg", []),
        "locations":                [loc["label"] for loc in jd.get("locations", [])] or [listing.get("location", "")],
        "work_mode":                work_mode,
        "apply_count":              apply_count,
        "age_days":                 age_days,
        "early_applicant":          v3.get("earlyApplicant",      listing.get("earlyApplicant",     False)),
        "naukri_location_match":    v3.get("location",            listing.get("locationMatch",      False)),
        "naukri_experience_match":  v3.get("workExperience",      listing.get("experienceMatch",    False)),
        "naukri_industry_match":    v3.get("industry",            listing.get("industryMatch",      False)),
        "naukri_education_match":   v3.get("education",           listing.get("educationMatch",     False)),
        "naukri_functional_match":  v3.get("functionalArea",      listing.get("functionalAreaMatch",False)),
        "company_rating":           company_rating,
        "company_tags":             company_tags,
        "salary_avg_lpa":           salary_avg,
        "salary_min_lpa":           salary_min,
        "salary_max_lpa":           salary_max,
        # ── populated by precompute_job_embeddings ──
        "_req_emb":                 None,
        "_pref_emb":                None,
        "_jd_emb":                  None,
        "_role_emb":                None,
        # store original binary flag for knockout logic
        "_naukri_matched":          raw_keyskills is not None and float(raw_keyskills) > 0,
    }


# ─────────────────────────────────────────────────────────
# BATCH PRE-ENCODING
# ─────────────────────────────────────────────────────────

def precompute_resume_embeddings(resume: ResumeProfile, model, device: str) -> None:
    if resume.skills:
        with torch.no_grad():
            resume.skills_emb = model.encode(
                resume.skills,
                batch_size=512,
                convert_to_tensor=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            ).to(device)

    resume.section_embs = {}
    section_texts = {
        k: v for k, v in resume.sections.items()
        if k != "_embeddings" and isinstance(v, str) and v.strip()
    }
    if section_texts:
        names = list(section_texts.keys())
        texts = list(section_texts.values())
        with torch.no_grad():
            all_embs = model.encode(
                texts,
                batch_size=512,
                convert_to_tensor=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            ).to(device)
        for i, name in enumerate(names):
            resume.section_embs[name] = all_embs[i].unsqueeze(0)


def precompute_job_embeddings(jobs: list, model, device: str, batch_size: int = 512) -> None:
    # Pass 1: Required skills
    req_texts = []
    for job in jobs:
        req_texts.extend(job["skills_required"])

    if req_texts:
        with torch.no_grad():
            req_all = model.encode(
                req_texts,
                batch_size=batch_size,
                convert_to_tensor=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            ).to(device)
        start = 0
        for job in jobs:
            cnt = len(job["skills_required"])
            if cnt > 0:
                job["_req_emb"] = req_all[start:start + cnt]
            start += cnt

    # Pass 2: Preferred skills
    pref_texts = []
    for job in jobs:
        pref_texts.extend(job["skills_preferred"])

    if pref_texts:
        with torch.no_grad():
            pref_all = model.encode(
                pref_texts,
                batch_size=batch_size,
                convert_to_tensor=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            ).to(device)
        start = 0
        for job in jobs:
            cnt = len(job["skills_preferred"])
            if cnt > 0:
                job["_pref_emb"] = pref_all[start:start + cnt]
            start += cnt

    # Pass 3: JD texts
    jd_texts = [(job.get("jd_text") or "")[:2000] or "no description" for job in jobs]
    with torch.no_grad():
        jd_all = model.encode(
            jd_texts,
            batch_size=batch_size,
            convert_to_tensor=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).to(device)
    for j_idx, job in enumerate(jobs):
        job["_jd_emb"] = jd_all[j_idx].unsqueeze(0)

    # Pass 4: Role context
    role_texts = [
        f"{job.get('role_category','')} {job.get('functional_area','')} {job.get('job_role','')}".strip()
        or "software engineer"
        for job in jobs
    ]
    with torch.no_grad():
        role_all = model.encode(
            role_texts,
            batch_size=batch_size,
            convert_to_tensor=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).to(device)
    for j_idx, job in enumerate(jobs):
        job["_role_emb"] = role_all[j_idx].unsqueeze(0)


# ─────────────────────────────────────────────────────────
# Scoring Engine
# ─────────────────────────────────────────────────────────

class SmartScorer:

    WEIGHTS = {
        "skill_match":          0.35,   # bidirectional — most reliable signal
        "role_alignment":       0.20,   # NEW: job title domain vs resume domain
        "semantic_similarity":  0.15,   # holistic JD ↔ resume fit
        "experience_fit":       0.10,
        "naukri_v3_signals":    0.10,   # demoted — Naukri signals unreliable
        "competition_quality":  0.07,
        "location_mode":        0.03,
    }

    SECTION_WEIGHTS = {
        "experience":     1.6,
        "projects":       1.2,
        "skills":         1.0,
        "summary":        0.9,
        "certifications": 0.8,
        "education":      0.7,
    }

    SKILL_THRESHOLD = 0.78   # balanced — catches semantic-close skills without Java/JS confusion

    # Top-N resume skills used for reverse coverage check
    # (skills list is ordered by prominence — first N = core domain skills)
    REVERSE_TOP_N = 10

    def score(self, resume: ResumeProfile, job: dict, model=None) -> dict:
        signals = {
            "skill_match":          self._skill_match(resume, job),
            "role_alignment":       self._role_alignment(resume, job),
            "semantic_similarity":  self._semantic(resume, job),
            "naukri_v3_signals":    self._naukri_v3(job),
            "experience_fit":       self._experience(resume, job),
            "location_mode":        self._location(resume, job),
            "competition_quality":  self._competition(job),
        }

        raw = sum(self.WEIGHTS[k] * v for k, v in signals.items())
        raw = self._knockouts(raw, signals, resume, job)

        return {
            "total_score":    round(raw * 100, 1),
            "grade":          self._grade(raw),
            "breakdown":      {k: round(v * 100, 1) for k, v in signals.items()},
            "missing_skills": self._missing_skills(job),
            "salary_insight": self._salary_insight(job),
            "flags":          self._flags(signals, resume, job),
            "apply_priority": self._priority(raw, job),
        }

    def _skill_match(self, resume: ResumeProfile, job: dict) -> float:
        req_emb  = job.get("_req_emb")
        pref_emb = job.get("_pref_emb")

        if req_emb is None or resume.skills_emb is None:
            naukri_ratio = job["naukri_skill_ratio"]
            return naukri_ratio if naukri_ratio is not None else 0.3

        F = torch.nn.functional

        # ── Forward: fraction of job's REQUIRED skills found in resume ──────
        sim_fwd     = F.cosine_similarity(req_emb.unsqueeze(1), resume.skills_emb.unsqueeze(0), dim=-1)
        req_matched = (sim_fwd.max(dim=1).values >= self.SKILL_THRESHOLD).float().mean().item()

        # ── Reverse: fraction of resume's TOP-N core skills needed by this job ──
        # Catches domain mismatch: React resume vs Java job → reverse ≈ 0
        core_emb     = resume.skills_emb[:self.REVERSE_TOP_N]
        sim_rev      = F.cosine_similarity(req_emb.unsqueeze(1), core_emb.unsqueeze(0), dim=-1)
        core_covered = (sim_rev.max(dim=0).values >= self.SKILL_THRESHOLD).float().mean().item()

        # Bidirectional score: forward weighted more, reverse acts as domain gate
        embedding_score = 0.60 * req_matched + 0.40 * core_covered

        # Preferred skills: small bonus only when base score is already decent
        # Avoids: "Java job with React preferred" inflating score
        if pref_emb is not None and embedding_score > 0.25:
            sim_pref   = F.cosine_similarity(pref_emb.unsqueeze(1), resume.skills_emb.unsqueeze(0), dim=-1)
            pref_bonus = (sim_pref.max(dim=1).values >= self.SKILL_THRESHOLD).float().mean().item()
            embedding_score = min(1.0, embedding_score + 0.08 * pref_bonus)

        # naukri_ratio: soft modifier, embedding leads
        naukri_ratio = job["naukri_skill_ratio"]
        combined     = (0.65 * embedding_score + 0.35 * naukri_ratio) if naukri_ratio else embedding_score

        mismatch_skills  = [s.strip() for s in (job.get("skill_mismatch") or "").split(",") if s.strip()]
        mismatch_penalty = min(0.20, len(mismatch_skills) * 0.04)

        return max(0.0, combined - mismatch_penalty)

    def _role_alignment(self, resume: ResumeProfile, job: dict) -> float:
        """
        Cosine similarity between job's role context embedding and resume summary.
        High when job domain matches resume target role; low when different primary domain.
        E.g. 'Java Fullstack' vs 'React Developer resume' → low.
        """
        role_emb    = job.get("_role_emb")
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
        # Rescale [0.25, 0.70] → [0, 1]: below 0.25 = unrelated domain, above 0.70 = strong match
        rescaled = (raw - 0.25) / (0.70 - 0.25)
        return max(0.0, min(1.0, rescaled))

    def _semantic(self, resume: ResumeProfile, job: dict) -> float:
        jd_emb   = job.get("_jd_emb")
        role_emb = job.get("_role_emb")

        if jd_emb is None or resume.section_embs is None:
            return 0.0   # no embedding = no signal, not 0.5 neutral

        weighted_sims, total_w = [], 0.0

        for section, sec_emb in resume.section_embs.items():
            sim_jd   = torch.nn.functional.cosine_similarity(sec_emb, jd_emb).item()
            sim_role = torch.nn.functional.cosine_similarity(sec_emb, role_emb).item() \
                       if role_emb is not None else sim_jd
            sim = 0.75 * sim_jd + 0.25 * sim_role
            w   = self.SECTION_WEIGHTS.get(section, 1.0)
            weighted_sims.append(sim * w)
            total_w += w

        if not weighted_sims:
            return 0.0

        raw_sim  = sum(weighted_sims) / total_w
        # [0.25, 0.68] calibrated for JobBERT — ceiling raised to spread top-tier matches
        rescaled = (raw_sim - 0.25) / (0.68 - 0.25)
        return max(0.0, min(1.0, rescaled))

    def _naukri_v3(self, job: dict) -> float:
        naukri_matched = job.get("_naukri_matched", False)
        keyskill_score = 0.7 if naukri_matched else 0.0

        booleans = [
            (job["naukri_experience_match"],  0.30),
            (job["naukri_industry_match"],    0.20),
            (job["naukri_location_match"],    0.15),
            (job["naukri_functional_match"],  0.15),
            (job["naukri_education_match"],   0.10),
        ]
        bool_score = sum(w for flag, w in booleans if flag) / 0.90

        if naukri_matched:
            return 0.50 * keyskill_score + 0.50 * bool_score
        else:
            return 0.30 * bool_score

    def _experience(self, resume: ResumeProfile, job: dict) -> float:
        min_exp = job.get("min_experience")
        max_exp = job.get("max_experience")
        years   = resume.total_experience_years

        if job["naukri_experience_match"] and min_exp and max_exp and min_exp <= years <= max_exp:
            return 1.0
        if min_exp is None:
            return 0.5
        if years < min_exp:
            return max(0.0, 1.0 - ((min_exp - years) / min_exp) * 0.85)
        elif max_exp and years > max_exp:
            return max(0.65, 1.0 - ((years - max_exp) / max_exp) * 0.12)
        return 1.0

    def _location(self, resume: ResumeProfile, job: dict) -> float:
        if getattr(resume, 'willing_to_relocate', True):
            location_score = 0.5
        elif job["naukri_location_match"]:
            location_score = 1.0
        else:
            resume_loc = resume.location.lower()
            matched    = any(
                resume_loc in loc.lower() or loc.lower() in resume_loc
                for loc in job.get("locations", [])
            )
            location_score = 1.0 if matched else (0.8 if job.get("work_mode") == "remote" else 0.0)

        pref    = resume.preferred_work_mode.lower()
        jd_mode = job.get("work_mode", "").lower()
        if pref == jd_mode:               mode_score = 1.0
        elif "hybrid" in (pref, jd_mode): mode_score = 0.6
        else:                             mode_score = 0.2

        return min(1.0, 0.5 * location_score + 0.5 * mode_score)

    def _competition(self, job: dict) -> float:
        age_days = job.get("age_days", 7)
        if age_days <= 1:     freshness = 1.0
        elif age_days <= 3:   freshness = 0.85
        elif age_days <= 7:   freshness = 0.65
        elif age_days <= 14:  freshness = 0.40
        elif age_days <= 30:  freshness = 0.20
        else:                 freshness = 0.05

        count = job.get("apply_count", 50)
        if count < 20:      competition = 1.0
        elif count < 50:    competition = 0.80
        elif count < 100:   competition = 0.55
        elif count < 200:   competition = 0.30
        elif count < 500:   competition = 0.15
        else:               competition = 0.05

        rating  = job.get("company_rating", 0)
        quality = (rating / 5.0) if rating else 0.5
        tags    = [t.lower() for t in job.get("company_tags", [])]
        if "foreign mnc" in tags or "saas" in tags:
            quality = min(1.0, quality + 0.1)

        early_bonus = 0.1 if job.get("early_applicant") else 0.0
        return min(1.0, 0.35 * freshness + 0.35 * competition + 0.25 * quality + early_bonus)

    def _knockouts(self, score: float, signals: dict, resume: ResumeProfile, job: dict) -> float:
        # Hard domain mismatch: role doesn't align AND JD holistically doesn't fit → strong penalty
        if signals["role_alignment"] < 0.20 and signals["semantic_similarity"] < 0.40:
            score *= 0.35

        # Skill signal alone weak (both forward and reverse low) → moderate penalty
        elif signals["skill_match"] < 0.15 and signals["semantic_similarity"] < 0.15:
            score *= 0.50

        # Experience gap
        min_exp = job.get("min_experience") or 0
        if min_exp and resume.total_experience_years < (min_exp - 3):
            score *= 0.65

        return score

    # ── Output helpers (unchanged) ────────────────────────────────────────

    def _missing_skills(self, job: dict) -> list:
        raw = job.get("skill_mismatch", "")
        return [s.strip() for s in raw.split(",") if s.strip()]

    def _salary_insight(self, job: dict) -> Optional[str]:
        avg = job.get("salary_avg_lpa", 0)
        mn  = job.get("salary_min_lpa", 0)
        mx  = job.get("salary_max_lpa", 0)
        if avg:
            return f"₹{mn}L - ₹{mx}L (avg ₹{avg}L) — AmbitionBox data"
        return None

    def _grade(self, score: float) -> str:
        if score >= 0.80: return "A — Strong Match"
        if score >= 0.65: return "B — Good Match"
        if score >= 0.50: return "C — Moderate Match"
        if score >= 0.35: return "D — Weak Match"
        return "F — Poor Match"

    def _priority(self, score: float, job: dict) -> str:
        age_days = job.get("age_days", 99)
        count    = job.get("apply_count", 999)
        if score >= 0.70 and age_days <= 3 and count < 100:
            return "🔥 Apply Immediately"
        if score >= 0.60 and age_days <= 7:
            return "✅ Apply Today"
        if score >= 0.50:
            return "📋 Apply This Week"
        return "⏭️ Skip / Low Priority"

    def _flags(self, signals: dict, resume: ResumeProfile, job: dict) -> list:
        flags   = []
        missing = self._missing_skills(job)
        if missing:
            flags.append(f"Missing skills: {', '.join(missing)}")
        if signals["experience_fit"] < 0.5:
            flags.append(f"Experience gap: need {job.get('min_experience')}-{job.get('max_experience')}y, you have {resume.total_experience_years}y")
        if job.get("apply_count", 0) > 200:
            flags.append(f"High competition: {job['apply_count']} applicants already")
        if job.get("age_days", 0) > 14:
            flags.append(f"Stale posting: {job['age_days']} days old")
        sal = self._salary_insight(job)
        if sal:
            flags.append(f"Salary insight: {sal}")
        if "foreign mnc" in [t.lower() for t in job.get("company_tags", [])]:
            flags.append("Foreign MNC — global exposure")
        return flags


# ─────────────────────────────────────────────────────────
# Utility functions
# ─────────────────────────────────────────────────────────

def _parse_exp_range(text: str):
    nums = re.findall(r'\d+(?:\.\d+)?', str(text))
    if len(nums) >= 2: return float(nums[0]), float(nums[1])
    if len(nums) == 1: return float(nums[0]), float(nums[0]) + 2
    return None, None

def _parse_applicants(text: str) -> int:
    nums = re.findall(r'\d+', str(text))
    return int(nums[0]) if nums else 50

def _compute_age_days(date_str: str) -> int:
    try:
        posted = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        return (datetime.now() - posted).days
    except:
        return 7

def _parse_age_days(age_str: str) -> int:
    age_str = (age_str or "").lower()
    nums = re.findall(r'\d+', age_str)
    n = int(nums[0]) if nums else 1
    if "hour"  in age_str: return 0
    if "day"   in age_str: return n
    if "week"  in age_str: return n * 7
    if "month" in age_str: return n * 30
    return 7