# ===== resume_parser.py =====

import json
import re
import requests
import logging

logger = logging.getLogger(__name__)

OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.1:8b"

PARSE_PROMPT = """You are a resume parser. Extract structured information from the resume text below.

Return ONLY a valid JSON object with exactly these fields (no extra text, no markdown, no code fences):

{{
  "resume_skills": ["skill1", "skill2", ...],
  "total_experience_years": <float>,
  "education_level": "<highest degree e.g. B.Tech, M.Tech, MBA, B.Sc>",
  "preferred_location": "<primary city from resume address or most recent job location>",
  "preferred_work_mode": "<one of: remote, hybrid, office>",
  "willing_to_relocate": <true or false>,
  "resume_sections": {{
    "summary": "<full professional summary / objective section verbatim or paraphrased, minimum 3 sentences>",
    "experience": "<ALL work experience entries combined — include company names, roles, dates, responsibilities, technologies used. Be comprehensive, minimum 100 words>",
    "projects": "<ALL project descriptions combined — include project names, tech stack, outcomes. Be comprehensive, minimum 80 words>",
    "skills": "<all skills listed anywhere in the resume as a single comma-separated paragraph>",
    "education": "<all education details — degrees, institutions, years, grades>",
    "certifications": "<all certifications, courses, training — empty string if none>"
  }}
}}

Rules:
- resume_skills: flat list of ALL technical skills, tools, frameworks, languages, platforms found ANYWHERE in resume
- total_experience_years: sum of all work durations as decimal float (e.g. 2.5 for 2 years 6 months)
- preferred_work_mode: infer from resume mentions; default to "hybrid" if not mentioned
- willing_to_relocate: true if resume mentions relocation or multiple cities; default true
- resume_sections values MUST be plain strings — NO nested objects, NO lists
- Each section string should be DETAILED and LONG — short sections hurt matching accuracy
- Do NOT include any explanation, preamble, or text outside the JSON object

Resume Text:
{resume_text}
"""


def parse_resume_with_ollama(resume_text: str) -> dict:
    """
    Use Ollama llama3.1:8b to extract structured profile from resume text.
    """
    prompt = PARSE_PROMPT.format(resume_text=resume_text[:8000])  # increased cap

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 3000,   # increased to allow richer section text
        }
    }

    logger.info(f"Calling Ollama ({OLLAMA_MODEL}) to parse resume...")

    response = requests.post(OLLAMA_URL, json=payload, timeout=180)
    response.raise_for_status()

    raw = response.json().get("response", "")

    # Strip markdown code fences if model wraps output
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)

    # Extract JSON object if there's preamble text
    json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if json_match:
        cleaned = json_match.group(0)

    parsed = json.loads(cleaned)

    # Validate required keys
    required = [
        "resume_skills", "total_experience_years", "education_level",
        "preferred_location", "preferred_work_mode", "resume_sections"
    ]
    missing = [k for k in required if k not in parsed]
    if missing:
        raise ValueError(f"Ollama response missing keys: {missing}")

    # Ensure all section sub-keys exist
    section_defaults = {
        "summary": "", "experience": "", "projects": "",
        "skills": "", "education": "", "certifications": ""
    }
    for k, default in section_defaults.items():
        parsed["resume_sections"].setdefault(k, default)

    # Default willing_to_relocate to True if not present
    parsed.setdefault("willing_to_relocate", True)

    # Log section lengths so we can verify richness
    for sec, text in parsed["resume_sections"].items():
        logger.info(f"  Section '{sec}': {len(text.split())} words")

    logger.info(
        f"Resume parsed — {len(parsed['resume_skills'])} skills, "
        f"{parsed['total_experience_years']} yrs exp, "
        f"location: {parsed['preferred_location']}, "
        f"relocate: {parsed.get('willing_to_relocate')}"
    )

    return parsed


def load_or_create_resume_profile(config: dict, config_path: str, resume_text: str) -> dict:
    """
    Check if parsed resume profile JSON exists (via config key).
    If yes — load and return it.
    If no  — parse via Ollama, save JSON, update config with its path.
    """
    profile_path = config.get("resume_profile_path")

    # ── Try loading existing profile ──────────────────────
    if profile_path:
        try:
            with open(profile_path, "r", encoding="utf-8") as f:
                profile = json.load(f)
            logger.info(f"Loaded existing resume profile from {profile_path}")

            # Log section lengths to catch thin profiles from old runs
            sections = profile.get("resume_sections", {})
            for sec, text in sections.items():
                word_count = len(str(text).split())
                if word_count < 20:
                    logger.warning(f"  Section '{sec}' is thin ({word_count} words) — consider deleting profile to re-parse")
                else:
                    logger.info(f"  Section '{sec}': {word_count} words")

            return profile
        except Exception as e:
            logger.warning(f"Failed to load resume profile from {profile_path}: {e}. Re-parsing...")

    # ── Parse with Ollama ─────────────────────────────────
    try:
        profile = parse_resume_with_ollama(resume_text)
    except Exception as e:
        logger.error(f"Ollama parsing failed: {e}")
        logger.warning("Falling back to empty profile — scoring accuracy will be reduced.")
        profile = {
            "resume_skills": [],
            "total_experience_years": 0.0,
            "education_level": "",
            "preferred_location": "",
            "preferred_work_mode": "hybrid",
            "willing_to_relocate": True,
            "resume_sections": {
                "summary": "", "experience": "", "projects": "",
                "skills": "", "education": "", "certifications": ""
            }
        }

    # ── Save profile JSON next to resume ─────────────────
    try:
        import os
        resume_dir        = os.path.dirname(os.path.abspath(config.get("resume_path", ".")))
        profile_save_path = os.path.join(resume_dir, "resume_profile.json")

        with open(profile_save_path, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)

        logger.info(f"Resume profile saved at {profile_save_path}")

        # Update config with path so next run skips Ollama
        config["resume_profile_path"] = profile_save_path
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        logger.info("Config updated with resume_profile_path")

    except Exception as e:
        logger.warning(f"Could not save resume profile: {e}")

    return profile