# ==========================================
# NAUKRI AUTO-APPLY — SIMPLIFIED & RELIABLE
#
# Architecture (Hirist-inspired):
#   1. Topic normalizer  →  canonical cache keys (input_type::topic)
#   2. 4-tier resolution: exact cache → cross-type → QA master → Ollama
#   3. Ollama ALWAYS sees full cache (consistency) + resume text (accuracy)
#   4. No question classifier — one prompt path, full context, Ollama decides
#   5. CTC unit repair only — the one post-processing that's actually needed
#
# FIXES APPLIED:
#   FIX 1: Resume text now injected into build_prompt — Ollama can actually
#           search the resume for skill presence (fixes Databricks = 0 bug)
#   FIX 2: handle_chips now always calls resolve() — no longer blindly picks
#           first chip regardless of the question being asked
#   FIX 3: fuzzy_match uses token-overlap fallback before defaulting to
#           options[0] — wrong silent fallbacks greatly reduced
#   FIX 4: cache_get_by_topic restricts cross-type to compatible pairs —
#           radio labels no longer bleed into text fields
#   FIX 5: qa_lookup word-count gate lowered to 2 — short questions like
#           "Open to bond?" now match QA master instead of going to Ollama
# ==========================================

import os, re, json, time, logging
from pathlib import Path
from datetime import datetime, timezone
from difflib import get_close_matches

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

from ollama import chat
import requests as _requests
import PyPDF2


# ==========================================
# CONFIGURATION
# ==========================================

# ── Dynamic base path resolution ─────────────────────────────────────────
# auto_apply_new.py lives at  oneClickShell/core/auto_apply/
# Project root is two levels up
_HERE    = os.path.dirname(os.path.abspath(__file__))   # core/auto_apply/
BASE_DIR = os.path.dirname(os.path.dirname(_HERE))       # oneClickShell/

def _p(profile: str, filename: str) -> str:
    """Resolve a path inside profiles/<profile>/."""
    return os.path.join(BASE_DIR, "profiles", profile, filename)

CONFIGS = {
    "A_NEW": {
        "APPLIED_LOG": _p("pandurang", "applied_jobs.json"),
        "QA_MASTER":   _p("pandurang", "master_qa.json"),
        "QA_CACHE":    _p("pandurang", "qa_cache.json"),
        "CONFIG":      _p("pandurang", "config_A.json"),
        "FAILED_LOG":  _p("pandurang", "failed_applications.json"),
    },
    "B_OLD": {
        "APPLIED_LOG": _p("pandurang", "applied_jobs.json"),   # shared with A
        "QA_MASTER":   _p("pandurang", "master_qa.json"),      # shared with A
        "QA_CACHE":    _p("pandurang", "qa_cache.json"),       # shared with A
        "CONFIG":      _p("pandurang", "config_B.json"),
        "FAILED_LOG":  _p("pandurang", "failed_applications.json"),
    },
    "C_MAYURI": {
        "APPLIED_LOG": _p("mayuri", "applied_jobs.json"),
        "QA_MASTER":   _p("mayuri", "master_qa.json"),
        "QA_CACHE":    _p("mayuri", "qa_cache.json"),
        "CONFIG":      _p("mayuri", "config.json"),
        "FAILED_LOG":  _p("mayuri", "failed_applications.json"),
    },
}

ACTIVE_PROFILE = "C_MAYURI"   # ← change to switch profile
PROFILE        = CONFIGS[ACTIVE_PROFILE]
FAILED_LOG     = PROFILE["FAILED_LOG"]   # ← now derived from active profile
URLS_JSON      = os.path.join(BASE_DIR, "outputs", "latest_job_data.json")  # update as needed


def set_active_profile(profile_key: str):
    """
    Switch the active profile at runtime. Call this from main.py
    right after importing, before using AppliedCache or FailedLogger.

    Usage:
        from auto_apply.auto_apply_new import set_active_profile
        set_active_profile("B_OLD")   # or "A_NEW" / "C_MAYURI"
    """
    global ACTIVE_PROFILE, PROFILE, FAILED_LOG
    if profile_key not in CONFIGS:
        raise ValueError(f"Unknown profile key '{profile_key}'. Valid: {list(CONFIGS.keys())}")
    ACTIVE_PROFILE = profile_key
    PROFILE        = CONFIGS[ACTIVE_PROFILE]
    FAILED_LOG     = PROFILE["FAILED_LOG"]
OLLAMA_MODEL    = "qwen2.5:7b"
NEBIUS_URL      = "https://api.tokenfactory.nebius.com/v1/chat/completions"
NEBIUS_MODEL    = "meta-llama/Meta-Llama-3.1-8B-Instruct"
_USE_NEBIUS     = False   # set by set_llm_backend()
_NEBIUS_API_KEY = None    # set by set_llm_backend()

MAX_STEPS       = 30
POLL_RETRIES    = 10
POLL_INTERVAL   = 1.0
POST_SUBMIT_DELAY = 2.0
MAX_SUCCESS     = 60
LOGIN_URL    = r"https://www.naukri.com/nlogin/login"
SELECTORS = {
    "bot_messages":    "li.botItem span",
    "radio_inputs":    "input.ssrc__radio",
    "text_input":      "div.textArea[contenteditable='true']",
    "chips":           ".chatbot_Chip span",
    "save_btn":        "div.sendMsg",
    "applied":         "div.applied-job-content",
    "checkbox_inputs": "input.mcc__checkbox",
    "calendar_input":  "input.cc__input-box",
    "calendar_months": ".cc__calendar-month span",
    "calendar_years":  ".cc__calendar-year span",
}


# ==========================================
# TOPIC NORMALIZER
# ==========================================

_SKILL_NAMES = [
    "agentforce", "copilot studio", "vertex ai", "gemini", "palantir",
    "ray.io", "ray io", "triton",
    "machine learning", "deep learning", "transfer learning",
    "natural language processing", "natural language",
    "computer vision", "object detection",
    "generative ai", "gen ai", "genai",
    "large language model", "llm",
    "retrieval augmented", "rag",
    "reinforcement learning",
    "time series", "anomaly detection", "feature engineering",
    "mlops", "ml devops", "ml ops",
    "databricks", "snowflake", "redshift", "bigquery",
    "azure data factory", "azure data lake", "azure",
    "aws sagemaker", "aws bedrock", "aws lambda", "aws",
    "apache spark", "spark",
    "kubernetes", "k8s", "docker",
    "fastapi", "flask", "django",
    "tensorflow", "pytorch", "scikit-learn", "scikit learn", "xgboost", "lightgbm",
    "langchain",
    "hugging face", "huggingface",
    "faiss", "pgvector", "pinecone", "weaviate", "chroma",
    "openai", "gpt",
    "pandas", "numpy", "dask",
    "postgresql", "postgres", "mysql", "sqlite", "mongodb", "nosql",
    "sql server", "sql",
    "hadoop", "hive", "kafka", "airflow",
    "mlflow", "wandb", "w&b",
    "terraform", "ansible",
    "react", "angular", "vue",
    "node.js", "nodejs", "node js",
    "java", "spring boot", "spring",
    "golang", "go lang",
    "scala",
    "c++", "c#", ".net",
    "python",
    "power bi", "tableau", "looker",
    "full stack", "fullstack", "full-stack",
    "data engineering", "data engineer",
    "data science", "data scientist",
    "artificial intelligence",
    "nlp",
    "computer science",
    "software engineering", "software development",
    "devops",
    "ci/cd", "ci cd",
]

_SKILL_PATTERNS = [(s, re.compile(r'\b' + re.escape(s) + r'\b', re.IGNORECASE))
                   for s in _SKILL_NAMES]


def _extract_skill(q_text: str) -> str | None:
    for name, pattern in _SKILL_PATTERNS:
        if pattern.search(q_text):
            return re.sub(r'\s+', '_', name.lower())
    return None


_TOPIC_PATTERNS = [
    # CTC / Salary
    (r"(rate|rating|proficien|scale|out of)\s*.{0,30}(python|sql|java|scala|spark|ml|ai|skill)", "proficiency_rating"),
    (r"current\s*(ctc|salary|compensation|package)",            "current_ctc"),
    (r"expected\s*(ctc|salary|compensation|package)",           "expected_ctc"),
    (r"(current|present).{0,20}(expected|ectc)",                "ctc_combined"),
    (r"\bectc\b",                                               "expected_ctc"),
    (r"\bcctc\b",                                               "current_ctc"),
    (r"in\s*(lacs?|lakhs?|lpa)",                                "ctc_lacs"),
    (r"in\s*(inr|rupees)",                                      "ctc_inr"),
    (r"\bctc\b",                                                "ctc_combined"),
    (r"salary\s*(expectation|range|ask)",                       "expected_ctc"),
    (r"annual\s*compensation",                                  "ctc_combined"),
    (r"fixed.{0,20}variable",                                   "ctc_combined"),
    # Notice / Joining
    (r"notice\s*period",                                        "notice_period"),
    (r"how\s*soon\s*can\s*you\s*(join|start)",                  "notice_period"),
    (r"when\s*can\s*you\s*(join|start)",                        "notice_period"),
    (r"available\s*(to\s*)?(join|start)",                       "notice_period"),
    (r"immediate\s*(joiner|join|availability)",                  "notice_period"),
    (r"earliest\s*(possible\s*)?(start|join)",                  "joining_date"),
    (r"preferred\s*(start|joining)\s*date",                     "joining_date"),
    (r"when\s*(can|would)\s*you\s*(be\s*able\s*to\s*)?(join|start)", "joining_date"),
    (r"last\s*working\s*day",                                   "lwd"),
    (r"\blwd\b",                                                "lwd"),
    # Location / Relocation
    (r"current\s*location",                                     "current_location"),
    (r"where\s*(are\s*you\s*)?currently\s*(located|based)",     "current_location"),
    (r"(comfortable|willing|open|okay)\s*(to\s*)?(relocat)",    "relocation"),
    (r"\brelocation\b",                                         "relocation"),
    (r"preferred\s*(work\s*)?location",                         "preferred_location"),
    # Work mode
    (r"(wfo|work\s*from\s*office|onsite)",                      "work_mode"),
    (r"(wfh|work\s*from\s*home|remote\s*work)",                 "work_mode"),
    (r"\bhybrid\b",                                             "work_mode"),
    # Shift
    (r"(shift|timing|working\s*hours)",                         "shift"),
    # Total experience (generic — only fires when no skill name is found)
    (r"total\s*(work|it|industry|professional)?\s*experience",  "total_experience"),
    # Personal
    (r"(pan\s*card|pan\s*number)",                              "pan_card"),
    (r"(date\s*of\s*birth|\bdob\b)",                            "dob"),
    (r"\bpassport\b",                                           "passport"),
    (r"\blinkedin\b",                                           "linkedin"),
    # Disability — must come BEFORE education_degree so "disability percentage"
    # doesn't fall through to the education patterns
    (r"kind\s*(of\s*)?disability",                              "disability_type"),
    (r"disability\s*(percent|percentage)",                      "disability_percentage"),
    (r"\bdisabilit",                                            "disability"),
    (r"(10th|ssc|matriculat)",                                  "education_10th"),
    (r"(12th|hsc|intermediate)",                                "education_12th"),
    # b.e. requires both dots to avoid matching the word "be"
    (r"(graduation|degree|b\.e\.|b\.?tech)",                    "education_degree"),
    # percentage only fires for education context — disability is already caught above
    (r"(10th|12th|graduation|marks|cgpa|gpa).{0,20}percentage"
     r"|percentage.{0,20}(10th|12th|marks|score|cgpa|gpa)",    "education"),
    # Role / Motivation
    (r"reason\s*for\s*(change|leav|switch)",                    "reason_for_change"),
    (r"why\s*(this\s*company|your\s*company|\bus\b)",            "why_company"),
    (r"\bbond\b",                                               "bond"),
    (r"(c2h|contract.to.hire)",                                 "open_to_c2h"),
    (r"career\s*(goal|aspir|plan)",                             "career_goal"),
    # Interview
    (r"available\s*for\s*interview",                            "interview_availability"),
    (r"(face.to.face|in.person|\bf2f\b)\s*interview",           "face_to_face_interview"),
]
_TOPIC_COMPILED = [(re.compile(p, re.IGNORECASE), t) for p, t in _TOPIC_PATTERNS]

_EXP_TRIGGERS = re.compile(
    r"\b(how many years|years of experience|years.{0,10}exp|"
    r"yoe|experience in|exp in|experience with|hands.on.{0,20}(experience|exp)|"
    r"how long.{0,20}(work|use|using|used))\b",
    re.IGNORECASE,
)


def normalize_topic(q_text: str) -> str:
    q = q_text.strip()

    if _EXP_TRIGGERS.search(q):
        skill = _extract_skill(q)
        if skill:
            return f"exp::{skill}"
        cleaned = re.sub(r'\b(how|many|years|of|experience|do|you|have|in|with|'
                         r'what|is|your|please|tell|us|me|the|a|an)\b',
                         '', q.lower())
        slug = re.sub(r'[^\w]+', '_', cleaned.strip()).strip('_')[:50]
        slug = re.sub(r'_+', '_', slug)
        return f"exp::{slug}" if slug else "exp::unknown"

    q_lower = q.lower()
    for pattern, topic in _TOPIC_COMPILED:
        if pattern.search(q_lower):
            return topic

    filler = (r"\b(what|is|your|are|you|please|mention|share|tell|us|me|the|"
              r"have|do|how|many|a|an|in|with|for|of|and|or|to|at|on|"
              r"can|will|would|should|could|any|some|this|that|which|"
              r"describe|explain|briefly|detail|provide|give|specify|"
              r"currently|current|present|about|from|experience|rate|"
              r"out|much|number|years|total)\b")
    stripped = re.sub(r"[^\w\s]", "", re.sub(filler, "", q_lower))
    stripped = re.sub(r"\s+", "_", stripped.strip())
    stripped = re.sub(r"_+", "_", stripped).strip("_")
    return stripped[:60] if stripped else q_lower[:60]



# ==========================================
# ANSWER CLEANER
# ==========================================

_PREAMBLE_RE = re.compile(
    r'^('
    r'here\s+(is|are)\s+(the\s+)?answers?.*?:|'
    r"based\s+on\s+(my|the\s+candidate'?s?)\s+(profile|resume|previous).*?:|"
    r'according\s+to\s+.*?:|'
    r"here'?s\s+(a\s+)?(possible\s+)?response.*?:|"
    r"here'?s\s+my\s+.*?:|"
    r'note\s+that\s+.{0,80}\.|'
    r'the\s+candidate\s+.*?\.|'
    r'as\s+(per|mentioned\s+in)\s+(the\s+)?(resume|profile).*?:|'
    r'based\s+on\s+the\s+(resume|information|profile).*?:'
    r')\s*',
    re.IGNORECASE | re.DOTALL,
)

_BULLET_START = re.compile(r'^[\*\-•\d]+[.)]\s*', re.MULTILINE)


def clean_answer(raw: str) -> str:
    cleaned = raw.strip()
    cleaned = _PREAMBLE_RE.sub('', cleaned).strip()

    if '\n' in cleaned:
        a_match = re.search(r'^a\s*\d*\s*[:.)]\s*(.+)', cleaned, re.IGNORECASE | re.MULTILINE)
        if a_match:
            cleaned = a_match.group(1).strip()
            cleaned = re.sub(r'\s*\(.*?\)\s*$', '', cleaned).strip()

    if '\n' in cleaned:
        lines = [l.strip() for l in cleaned.splitlines() if l.strip()]
        content_lines = []
        for line in lines:
            lw = line.lower()
            if re.match(r'^(q\d*|note|explanation|candidate)[:\s]', lw):
                continue
            line = _BULLET_START.sub('', line).strip()
            if line:
                content_lines.append(line)
        if content_lines:
            cleaned = content_lines[0]

    cleaned = re.sub(r'\s*\(.{0,120}\)\s*$', '', cleaned).strip()
    return cleaned.strip()


# ==========================================
# OPTIONS COMPATIBILITY CHECK
# ==========================================

def _is_answer_compatible(answer, options: list) -> bool:
    """
    Return True if a stored answer can be meaningfully mapped to the current
    options list.  Used to skip stale cache entries when options have changed.
    """
    if not options:
        return True
    answers = answer if isinstance(answer, list) else [str(answer)]
    opts_lower = [o.lower() for o in options]
    for a in answers:
        a_lower = str(a).strip().lower()
        if any(a_lower in o or o in a_lower for o in opts_lower):
            return True
        if get_close_matches(a_lower, opts_lower, n=1, cutoff=0.4):
            return True
        a_tokens = set(re.findall(r'\d+|\b\w{2,}\b', a_lower))
        for opt in opts_lower:
            if a_tokens & set(re.findall(r'\d+|\b\w{2,}\b', opt)):
                return True
    return False


# ==========================================
# QA STORE  (unified single source of truth)
# ==========================================

class QAStore:
    """
    Replaces the old qa_cache.json + master_qa.json split.

    Every Q&A pair is one entry:
        {
            "question":   "What is your current notice period?",
            "input_type": "radio",
            "options":    ["15 days or less", "30 days", "60 days"],
            "answer":     "15 days or less",
            "source":     "manual",   # "manual" | "ollama"
            "confirmed":  true,       # true = used in a successful application
            "use_count":  3,
            "created_at": "2026-04-14T..."
        }

    Lookup confidence order (highest → lowest):
        1. manual  + exact question match
        2. manual  + fuzzy question match (word-overlap ≥ 0.55)
        3. ollama confirmed + exact/fuzzy + options compatible
        4. ollama unconfirmed + exact/fuzzy + options compatible
        (miss) → caller falls through to Ollama
    """

    def __init__(self, path: str):
        self.path = path
        self._session_questions: list = []
        p = Path(path)
        if not p.exists() or not p.read_text().strip():
            self.entries: list = []
            self._migrate_old_files()
        else:
            self.entries = self._load()

    # ── persistence ────────────────────────────────────────────────────────

    def _load(self) -> list:
        try:
            return json.loads(Path(self.path).read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.entries, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)

    # ── one-time migration from old split files ────────────────────────────

    def _migrate_old_files(self):
        store_dir   = Path(self.path).parent
        cache_path  = store_dir / "qa_cache.json"
        master_path = store_dir / "master_qa.json"
        entries: list = []
        seen: set = set()   # question.lower() — manual added first, wins on conflict

        # 1. master_qa.json → source="manual", confirmed=True
        if master_path.exists() and master_path.read_text().strip():
            try:
                for item in json.loads(master_path.read_text()):
                    q = item.get("question", "").strip()
                    if not q or item.get("answer") is None:
                        continue
                    entries.append({
                        "question":   q,
                        "input_type": item.get("input_type", "text"),
                        "options":    item.get("options") or [],
                        "answer":     item.get("answer"),
                        "source":     "manual",
                        "confirmed":  True,
                        "use_count":  0,
                        "created_at": item.get("updated_at", datetime.now(timezone.utc).isoformat()),
                    })
                    seen.add(q.lower())
            except Exception as exc:
                logging.warning(f"[QAStore] master_qa migration error: {exc}")

        # 2. qa_cache.json → only new rich-format entries (have a "question" key).
        #    Old flat bare-value entries are skipped — no question text to recover.
        if cache_path.exists() and cache_path.read_text().strip():
            try:
                for val in json.loads(cache_path.read_text()).values():
                    if not isinstance(val, dict):
                        continue
                    q = val.get("question", "").strip()
                    if not q or q.lower() in seen or val.get("answer") is None:
                        continue
                    entries.append({
                        "question":   q,
                        "input_type": val.get("type", "text"),
                        "options":    val.get("options") or [],
                        "answer":     val.get("answer"),
                        "source":     "ollama",
                        "confirmed":  False,
                        "use_count":  0,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    })
                    seen.add(q.lower())
            except Exception as exc:
                logging.warning(f"[QAStore] qa_cache migration error: {exc}")

        self.entries = entries
        if entries:
            self._save()
        logging.info(f"[QAStore] Migrated {len(entries)} entries → {self.path}")

    # ── public API ─────────────────────────────────────────────────────────

    def lookup(self, q_text: str, input_type: str, options: list = None):
        """
        Returns (answer, source_label) or (None, "miss").
        source_label: "manual" | "ollama_confirmed" | "ollama"
        """
        q_norm  = q_text.strip().lower()
        q_words = set(re.findall(r'\b\w{3,}\b', q_norm))
        best    = None   # (confidence, answer, label, entry_ref)

        for entry in self.entries:
            if entry.get("input_type") != input_type:
                continue
            answer = entry.get("answer")
            if answer is None:
                continue

            eq        = entry.get("question", "").strip().lower()
            source    = entry.get("source", "ollama")
            confirmed = entry.get("confirmed", False)

            # ── match score ───────────────────────────────────────────────
            if eq == q_norm:
                match_score = 1.0
            else:
                e_words = set(re.findall(r'\b\w{3,}\b', eq))
                if not e_words:
                    continue
                overlap = len(q_words & e_words) / len(e_words)
                if overlap < 0.55:
                    continue
                match_score = overlap

            # ── options compatibility ─────────────────────────────────────
            if options and not _is_answer_compatible(answer, options):
                continue   # cached answer can't map to current options → skip

            # ── confidence tier ───────────────────────────────────────────
            if source == "manual":
                conf, label = 3.0 + match_score, "manual"
            elif confirmed:
                conf, label = 2.0 + match_score, "ollama_confirmed"
            else:
                conf, label = 1.0 + match_score, "ollama"

            if best is None or conf > best[0]:
                best = (conf, answer, label, entry)

        if best is None:
            return None, "miss"

        best[3]["use_count"] = best[3].get("use_count", 0) + 1
        self._save()
        return best[1], best[2]

    def store(self, q_text: str, input_type: str, options, answer, source: str = "ollama"):
        """Add or update an entry. Manual entries are never overwritten by ollama."""
        if answer is None or (isinstance(answer, str) and not answer.strip()):
            return
        q_norm = q_text.strip()

        for entry in self.entries:
            if (entry.get("question", "").strip().lower() == q_norm.lower()
                    and entry.get("input_type") == input_type):
                if entry.get("source") == "manual" and source == "ollama":
                    return  # never overwrite human-curated answers
                entry["answer"]  = answer
                entry["options"] = options if options is not None else entry.get("options", [])
                entry["source"]  = source
                self._save()
                self._session_questions.append(q_norm)
                return

        self.entries.append({
            "question":   q_norm,
            "input_type": input_type,
            "options":    options if options is not None else [],
            "answer":     answer,
            "source":     source,
            "confirmed":  False,
            "use_count":  0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        self._save()
        self._session_questions.append(q_norm)

    def start_session(self):
        """Call at the start of each job's screening to track which answers were used."""
        self._session_questions = []

    def confirm_session(self):
        """
        Mark every question answered in this session as confirmed=True.
        Call this only when handle_screening returns "applied".
        """
        q_set   = {q.lower() for q in self._session_questions}
        changed = False
        for entry in self.entries:
            if (entry.get("question", "").strip().lower() in q_set
                    and not entry.get("confirmed")):
                entry["confirmed"] = True
                changed = True
        if changed:
            self._save()
        self._session_questions = []

    def as_context(self) -> str:
        """Format for Ollama prompt — manual + confirmed shown first, deduped by topic."""
        if not self.entries:
            return "No previous answers yet."
        sorted_entries = sorted(
            self.entries,
            key=lambda e: (0 if e.get("source") == "manual" else
                           1 if e.get("confirmed") else 2)
        )
        seen_topics: set = set()
        lines = ["ANSWERS I HAVE ALREADY GIVEN — stay 100% consistent with these:"]
        for entry in sorted_entries:
            topic = normalize_topic(entry.get("question", ""))
            if topic not in seen_topics:
                seen_topics.add(topic)
                lines.append(f'  {entry["question"]}: "{entry["answer"]}"')
        return "\n".join(lines)


# ==========================================
# RESUME LOADING & SKILL SUMMARY
# ==========================================

def load_resume(path: str) -> str:
    pages = []
    with open(path, "rb") as f:
        for page in PyPDF2.PdfReader(f).pages:
            txt = page.extract_text()
            if txt:
                pages.append(txt)
    text = "\n".join(pages)
    logging.info(f"Resume loaded — {len(text)} chars")
    return text


# ==========================================
# TOTAL EXPERIENCE EXTRACTOR
# ==========================================

from dateutil.relativedelta import relativedelta
from dateutil.parser import parse as parse_date

_DATE_RANGE_RE = re.compile(
    r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}|\d{4})"
    r"\s*(?:–|—|-|to)\s*"
    r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}|\d{4}|[Pp]resent|[Cc]urrent|[Nn]ow)",
    re.IGNORECASE,
)


def extract_total_experience(resume_text: str) -> int:
    today = datetime.now()
    spans = []
    for m in _DATE_RANGE_RE.finditer(resume_text):
        raw_start, raw_end = m.group(1), m.group(2)
        try:
            start = parse_date(raw_start, default=datetime(today.year, 1, 1))
            end   = today if raw_end.lower() in ("present", "current", "now") \
                          else parse_date(raw_end, default=datetime(today.year, 1, 1))
            if start < end:
                spans.append((start, end))
        except Exception:
            continue
    if not spans:
        logging.warning("[EXPERIENCE] No date ranges found — defaulting to 1 year")
        return 1
    spans.sort(key=lambda x: x[0])
    merged = [spans[0]]
    for start, end in spans[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    total_days  = sum((e - s).days for s, e in merged)
    whole_years = int(total_days // 365)
    logging.info(f"[EXPERIENCE] {len(merged)} span(s) → {total_days} days → {whole_years} whole year(s)")
    return whole_years


def extract_skill_summary(resume_text: str) -> str:
    total_years = extract_total_experience(resume_text)
    print(f"[SKILL EXTRACTOR] Total experience: {total_years} yr(s). Using flat model.")
    return f"TOTAL_YEARS={total_years}"


# ==========================================
# LLM BACKEND — Nebius (cloud) or Ollama (local)
# ==========================================

def set_llm_backend(use_nebius: bool = False, api_key: str = None):
    """Switch LLM backend. Falls back to Ollama silently if Nebius call fails."""
    global _USE_NEBIUS, _NEBIUS_API_KEY
    _USE_NEBIUS     = use_nebius and bool(api_key)
    _NEBIUS_API_KEY = api_key
    backend = f"Nebius ({NEBIUS_MODEL})" if _USE_NEBIUS else f"Ollama ({OLLAMA_MODEL})"
    logging.info(f"[auto_apply] LLM backend: {backend}")


def ask_ollama(prompt: str) -> str:
    response = chat(model=OLLAMA_MODEL, messages=[{"role": "user", "content": prompt}])
    return response.message.content.strip()


def ask_nebius(prompt: str) -> str:
    headers = {
        "Authorization": f"Bearer {_NEBIUS_API_KEY}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model":       NEBIUS_MODEL,
        "messages":    [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens":  500,
    }
    response = _requests.post(NEBIUS_URL, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


def ask_llm(prompt: str) -> str:
    """Route to Nebius or Ollama based on set_llm_backend() config."""
    if _USE_NEBIUS:
        try:
            return ask_nebius(prompt)
        except Exception as e:
            logging.warning(f"[nebius] call failed ({e}) — falling back to Ollama")
    return ask_ollama(prompt)


def build_prompt(q_text: str, qa_store: "QAStore",
                 skill_summary: str, resume: str,
                 options=None, is_multiselect=False) -> str:

    resume_snippet = resume[:3500] if resume else ""

    prompt = f"""You are ME filling in a job application screening form on Naukri right now.

{qa_store.as_context()}

MY RESUME (search this carefully for skill/tool presence):
{resume_snippet}

RESUME SKILL RULE (use for experience/years questions):
{skill_summary}

QUESTION: {q_text}

"""
    _q_lower = q_text.lower()
    _is_essay = any(p in _q_lower for p in [
        "for each", "list:", "list each", "for all", "every position",
        "every role", "last 3", "last 2", "last three", "last two",
        "each of your", "all positions", "all roles", "briefly explain",
        "describe in detail", "tell us about yourself", "walk us through",
        "elaborate", "summarize your", "explain your",
    ])

    _CTC_TOPICS = {"current_ctc", "expected_ctc", "ctc_combined", "ctc_lacs", "ctc_inr"}
    topic = normalize_topic(q_text)

    if options:
        opts = "\n".join(f"{i+1}. {o}" for i, o in enumerate(options))
        if is_multiselect:
            prompt += f"OPTIONS (select one or more):\n{opts}\n\nReturn selected options separated by ' || '. Exact option text only."
        else:
            prompt += f"OPTIONS (select exactly one):\n{opts}\n\nReturn ONLY the exact option text. No explanation."
    elif _is_essay:
        prompt += ("This is a multi-part or essay question. "
                   "Answer fully and clearly using information from the resume above. "
                   "Be specific — include company names, dates, and figures where asked. "
                   "First person only. No preamble like 'Based on my profile'.")
    elif topic in _CTC_TOPICS:
        prompt += ("Return ONLY a number. "
                   "If the question asks in Lakhs/LPA, return in Lakhs (e.g. 11). "
                   "If the question asks in INR, return full INR (e.g. 1100000). "
                   "No text, no units.")
    elif topic == "dob":
        prompt += "Return date of birth in DD/MM/YYYY format. No explanation."
    elif topic in ("joining_date", "lwd"):
        today = datetime.now().strftime("%m/%Y")
        prompt += f"Return a date in MM/YYYY format. Today is {today}. No explanation."
    elif "date" in topic:
        prompt += "Return date in MM/YYYY format. No explanation."
    elif topic.startswith("exp::"):
        import re as _re
        _m = _re.search(r'TOTAL_YEARS=(\d+)', skill_summary)
        _total = _m.group(1) if _m else "?"
        prompt += (
            f"This is an experience/years question about a specific skill.\n"
            f"The candidate's total career length is {_total} years.\n"
            f"\nRULE: Read the RESUME TEXT above carefully.\n"
            f"- If the skill/tool asked about appears ANYWHERE in the resume "
            f"(skills section, job description, projects, certifications) → answer {_total}\n"
            f"- If the skill does NOT appear anywhere in the resume → answer 0\n"
            f"Return ONLY a single whole number: either {_total} or 0. "
            f"No other values. No decimals. No text. No explanation."
        )
    elif topic in ("notice_period",):
        prompt += "Return a short direct answer (e.g. '30 days', 'Immediate'). No explanation."
    else:
        prompt += ("Return a SHORT, direct answer — one sentence or a number. "
                   "Do NOT say 'Based on my profile', 'Here are the answers', or write a bullet list. "
                   "First person only.")

    return prompt


# ==========================================
# CTC UNIT REPAIR
# ==========================================

def repair_ctc(answer: str, q_text: str) -> str:
    q = q_text.lower()
    wants_lacs = any(p in q for p in ["in lacs", "in lakhs", "lpa", "in lac", "in l"])
    wants_inr  = any(p in q for p in ["in inr", "in rupees"])
    if not (wants_lacs or wants_inr):
        return answer
    try:
        num = float(re.sub(r"[^\d.]", "", answer.split(",")[0].split("|")[0]))
    except Exception:
        return answer
    if wants_lacs and num >= 100_000:
        lac    = round(num / 100_000, 1)
        result = str(int(lac)) if lac == int(lac) else str(lac)
        logging.info(f"[CTC] INR {num:.0f} → {result} L")
        return result
    if wants_inr and 0 < num < 1_000:
        result = str(int(num * 100_000))
        logging.info(f"[CTC] {num} L → INR {result}")
        return result
    return answer


# ==========================================
# RESOLVER  (store lookup → Ollama)
# ==========================================

def resolve(q_text: str, input_type: str, qa_store: "QAStore",
            skill_summary: str, resume: str,
            options=None, is_multiselect=False):

    topic        = normalize_topic(q_text)
    _is_exp_text = (input_type == "text" and topic.startswith("exp::"))

    # 1. QA store lookup (manual → confirmed ollama → unconfirmed ollama, options-validated)
    answer, source = qa_store.lookup(q_text, input_type, options)

    if answer is not None:
        if _is_exp_text and not str(answer).replace('.', '').isdigit():
            logging.warning(
                f"  [store-skip] {topic} stored value '{answer}' ({source}) "
                f"is non-numeric for text field — falling through to Ollama"
            )
        else:
            logging.info(f"  [{source}] {topic} → {str(answer)[:40]}")
            return answer

    # 2. LLM — last resort (Nebius if enabled, else Ollama)
    prompt = build_prompt(q_text, qa_store, skill_summary, resume, options, is_multiselect)
    _backend = "nebius" if _USE_NEBIUS else "ollama"
    logging.info(f"  [{_backend}] {topic}")
    raw = ask_llm(prompt)
    logging.info(f"  [{_backend}-raw] {raw[:80]}")

    if not options:
        # Text answer: clean + CTC repair, then store immediately
        answer = repair_ctc(clean_answer(raw), q_text)
        qa_store.store(q_text, input_type, None, answer, source="ollama")
    else:
        # Option answer: return raw — handler does fuzzy_match then stores
        answer = raw

    return answer


# ==========================================
# FUZZY OPTION MATCHING
#
# FIX 3: Added token-overlap fallback before defaulting to options[0].
# Previously any mismatch silently picked the first option — wrong answers
# with no log. Now token overlap gives a much better last-resort match,
# and every fallback is logged as a warning so you can audit bad answers.
# ==========================================

def _numeric_range_match(answer: str, options: list):
    """
    Match a plain number to a range-style option.
    Handles: 'Less than N', 'N to M Years', 'More than N Years', 'N+'.
    Returns the matching option string, or None if no match found.
    """
    try:
        val = float(re.sub(r'[^\d.]', '', answer.strip()))
    except (ValueError, TypeError):
        return None
    if not answer.strip().replace('.', '').isdigit():
        return None   # not a plain number

    _range     = re.compile(r'(\d+(?:\.\d+)?)\s*(?:to|-)\s*(\d+(?:\.\d+)?)', re.I)
    _less_than = re.compile(r'less\s*than\s*(\d+(?:\.\d+)?)', re.I)
    _more_than = re.compile(r'(?:more|greater|above)\s*than\s*(\d+(?:\.\d+)?)', re.I)
    _plus      = re.compile(r'(\d+(?:\.\d+)?)\s*\+', re.I)

    for opt in options:
        m = _range.search(opt)
        if m and float(m.group(1)) <= val <= float(m.group(2)):
            return opt
        m = _less_than.search(opt)
        if m and val < float(m.group(1)):
            return opt
        m = _more_than.search(opt)
        if m and val > float(m.group(1)):
            return opt
        m = _plus.search(opt)
        if m and val >= float(m.group(1)):
            return opt  # e.g. "3+" matches 4

    return None


def fuzzy_match(answer, options: list) -> str:
    if not isinstance(answer, str):
        answer = str(answer)

    # Exact match
    if answer in options:
        return answer

    # Numeric range match — handles "28" → "25 to 32 Years", "4" → "3+", etc.
    range_hit = _numeric_range_match(answer, options)
    if range_hit:
        return range_hit

    lowered = [o.lower() for o in options]

    # difflib close match (handles minor typos / casing)
    matches = get_close_matches(answer.lower(), lowered, n=1, cutoff=0.4)
    if matches:
        return options[lowered.index(matches[0])]

    # Substring containment
    for opt in options:
        if answer.lower() in opt.lower() or opt.lower() in answer.lower():
            return opt

    # FIX 3: Token-overlap fallback — much better than blind options[0]
    # Tokenizes both answer and each option, picks highest overlap ratio.
    answer_tokens = set(re.findall(r'\d+|\b\w{2,}\b', answer.lower()))
    best_opt, best_score = options[0], 0.0
    for opt in options:
        opt_tokens = set(re.findall(r'\d+|\b\w{2,}\b', opt.lower()))
        if not opt_tokens:
            continue
        shared = answer_tokens & opt_tokens
        score  = len(shared) / max(len(answer_tokens), len(opt_tokens), 1)
        if score > best_score:
            best_score, best_opt = score, opt

    logging.warning(
        f"[fuzzy_match] No strong match for '{answer}' in {options} "
        f"→ token-overlap picked '{best_opt}' (score={best_score:.2f})"
    )
    return best_opt


# ==========================================
# INPUT HANDLERS
# ==========================================

def handle_radio(driver, question, qa_store, skill_summary, resume):
    inputs  = driver.find_elements(By.CSS_SELECTOR, SELECTORS["radio_inputs"])
    options = [r.get_attribute("value") for r in inputs]
    raw     = resolve(question, "radio", qa_store, skill_summary, resume, options)
    answer  = fuzzy_match(raw, options)
    radio   = driver.find_element(By.XPATH, f'//input[@value="{answer}"]')
    driver.execute_script("arguments[0].click();", radio)
    click_submit(driver)
    qa_store.store(question, "radio", options, answer)
    return answer


def handle_text(driver, question, qa_store, skill_summary, resume):
    wait   = WebDriverWait(driver, 25)
    box    = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, SELECTORS["text_input"])))
    answer = resolve(question, "text", qa_store, skill_summary, resume)
    if isinstance(answer, list):
        answer = ", ".join(str(x) for x in answer)
    driver.execute_script("arguments[0].innerText = '';", box)
    box.send_keys(str(answer))
    click_submit(driver)
    # Text answers stored inside resolve() for Ollama path; store here covers store hits too
    qa_store.store(question, "text", None, answer)
    return answer


def handle_multiselect(driver, question, qa_store, skill_summary, resume):
    inputs  = driver.find_elements(By.CSS_SELECTOR, SELECTORS["checkbox_inputs"])
    options = [i.get_attribute("value") for i in inputs]
    raw     = resolve(question, "multiselect", qa_store, skill_summary, resume,
                      options, is_multiselect=True)
    if isinstance(raw, list):
        selected = [str(x) for x in raw]
    elif " || " in str(raw):
        selected = [x.strip() for x in str(raw).split(" || ")]
    else:
        selected = [x.strip() for x in str(raw).split(",")]
    seen, final = set(), []
    for s in selected:
        matched = fuzzy_match(s, options)
        if matched not in seen:
            seen.add(matched)
            final.append(matched)
    for opt in final:
        cb = driver.find_element(By.XPATH, f'//input[@value="{opt}"]')
        driver.execute_script("arguments[0].click();", cb)
    click_submit(driver)
    qa_store.store(question, "multiselect", options, final)
    return final


def handle_chips(driver, question, qa_store, skill_summary, resume):
    chips      = driver.find_elements(By.CSS_SELECTOR, SELECTORS["chips"])
    chip_texts = [c.text.strip() for c in chips if c.text.strip()]

    if not chip_texts:
        logging.warning("[chips] No chip text found — skipping")
        return None

    raw    = resolve(question, "chip", qa_store, skill_summary, resume, options=chip_texts)
    answer = fuzzy_match(str(raw), chip_texts)

    for i, c in enumerate(chips):
        if c.text.strip() == answer:
            driver.execute_script("arguments[0].click();", c)
            break
    else:
        idx = chip_texts.index(answer) if answer in chip_texts else 0
        driver.execute_script("arguments[0].click();", chips[idx])
        logging.warning(f"[chips] Clicked by index fallback for '{answer}'")

    qa_store.store(question, "chip", chip_texts, answer)
    return answer


def handle_dob(driver, question, qa_store, skill_summary, resume):
    answer = resolve(question, "dob", qa_store, skill_summary, resume)
    try:
        day_val, month_val, year_val = answer.split("/")
    except Exception:
        raise ValueError(f"DOB malformed: {answer}")
    script = """
    function typeInto(el,value,delay=120){
      el.focus(); el.value="";
      value.split("").forEach((ch,i)=>{
        setTimeout(()=>{
          el.dispatchEvent(new KeyboardEvent("keydown",{key:ch,bubbles:true}));
          el.value+=ch;
          el.dispatchEvent(new Event("input",{bubbles:true}));
          el.dispatchEvent(new KeyboardEvent("keyup",{key:ch,bubbles:true}));
        }, i*delay);
      });
    }
    let d=document.querySelector("input.dob__input.day");
    let m=document.querySelector("input.dob__input.month");
    let y=document.querySelector("input.dob__input.year");
    setTimeout(()=>typeInto(d,arguments[0]),0);
    setTimeout(()=>typeInto(m,arguments[1]),400);
    setTimeout(()=>typeInto(y,arguments[2]),900);
    """
    driver.execute_script(script, day_val, month_val, year_val)
    time.sleep(2)
    click_submit(driver)
    qa_store.store(question, "dob", None, answer)
    return answer


def handle_calendar(driver, question, qa_store, skill_summary, resume):
    answer = resolve(question, "calendar", qa_store, skill_summary, resume)
    if "/" not in str(answer):
        try:
            answer = f"01/{int(str(answer).strip())}"
        except Exception:
            raise ValueError(f"Calendar malformed: {answer}")
    try:
        month_num, year_num = int(answer.split("/")[0]), int(answer.split("/")[1])
    except Exception:
        raise ValueError(f"Calendar malformed: {answer}")
    driver.execute_script("arguments[0].click();",
        driver.find_element(By.CSS_SELECTOR, "span.cc__calendar-icon"))
    time.sleep(0.5)
    month_names = ["Jan","Feb","Mar","Apr","May","Jun",
                   "Jul","Aug","Sept","Oct","Nov","Dec"]
    for m in driver.find_elements(By.CSS_SELECTOR, SELECTORS["calendar_months"]):
        if m.text.strip() == month_names[month_num - 1]:
            driver.execute_script("arguments[0].click();", m)
            break
    time.sleep(0.3)
    driver.execute_script("arguments[0].click();",
        driver.find_element(By.ID, "cc__year-navitem"))
    time.sleep(0.3)
    for y in driver.find_elements(By.CSS_SELECTOR, SELECTORS["calendar_years"]):
        if y.text.strip() == str(year_num):
            driver.execute_script("arguments[0].click();", y)
            break
    time.sleep(0.5)
    click_submit(driver)
    qa_store.store(question, "calendar", None, answer)
    return answer


def click_submit(driver):
    btn = driver.find_element(By.CSS_SELECTOR, SELECTORS["save_btn"])
    driver.execute_script("arguments[0].click();", btn)


# ==========================================
# PLATFORM ERROR DETECTION
# ==========================================

def detect_platform_error(driver) -> bool:
    try:
        page = driver.page_source.lower()
    except Exception:
        return False
    return any(sig in page for sig in [
        "there was an error while processing your request",
        "please try again later",
        "maximum number of applies",
        "daily apply limit",
        "you have reached the limit",
        "today's limit reached",
        "too many requests",
        "temporarily blocked",
        "access denied",
        "service unavailable",
        "something went wrong",
    ])


# ==========================================
# SCREENING HANDLER
# ==========================================

def wait_for_new_question(driver, last_question: str):
    for _ in range(POLL_RETRIES):
        msgs = driver.find_elements(By.CSS_SELECTOR, SELECTORS["bot_messages"])
        if msgs:
            current = msgs[-1].text.strip()
            if current and current != last_question:
                return current
        time.sleep(POLL_INTERVAL)
    return None


def handle_screening(driver, job_url, resume_text, skill_summary, qa_store, failed_logger):
    logging.info("Starting screening...")
    last_question = None
    qa_store.start_session()
    hkw = dict(qa_store=qa_store, skill_summary=skill_summary, resume=resume_text)

    for step in range(1, MAX_STEPS + 1):
        question = wait_for_new_question(driver, last_question)
        if not question:
            failed_logger.log(job_url, "timeout", "Timed out waiting for question", step, last_question)
            return "timeout"

        last_question = question
        logging.info(f"[Step {step}] {question}")

        if any(p in question.lower() for p in [
            "thank you for your response", "application submitted", "successfully applied"
        ]):
            try:
                WebDriverWait(driver, 25).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, SELECTORS["applied"])))
                return "applied"
            except TimeoutException:
                failed_logger.log(job_url, "terminal_no_applied_div", "Terminal but no applied div", step, question)
                return "terminal_no_applied_div"

        dob_day     = driver.find_elements(By.CSS_SELECTOR, "input.dob__input.day")
        checkbox    = driver.find_elements(By.CSS_SELECTOR, SELECTORS["checkbox_inputs"])
        radio       = driver.find_elements(By.CSS_SELECTOR, SELECTORS["radio_inputs"])
        chips       = driver.find_elements(By.CSS_SELECTOR, SELECTORS["chips"])
        calendar    = driver.find_elements(By.CSS_SELECTOR, SELECTORS["calendar_input"])
        text_inputs = driver.find_elements(By.CSS_SELECTOR, SELECTORS["text_input"])

        try:
            if checkbox:
                answer = handle_multiselect(driver, question, **hkw)
            elif dob_day:
                answer = handle_dob(driver, question, **hkw)
            elif calendar:
                answer = handle_calendar(driver, question, **hkw)
            elif radio:
                answer = handle_radio(driver, question, **hkw)
            elif chips:
                answer = handle_chips(driver, question, **hkw)
            elif text_inputs:
                answer = handle_text(driver, question, **hkw)
            else:
                logging.warning("Unknown input type — skipping step")
                failed_logger.log(job_url, "unknown_input", "No recognised input", step, question)
                return "unknown_input"
        except Exception as e:
            logging.warning(f"Handler error: {e}")
            failed_logger.log(job_url, "handler_error", str(e), step, question)
            return "handler_error"

        logging.info(f"  → {str(answer)[:60]}")
        time.sleep(POST_SUBMIT_DELAY)

        if driver.find_elements(By.CSS_SELECTOR, SELECTORS["applied"]):
            return "applied"

    failed_logger.log(job_url, "max_steps", f">{MAX_STEPS} steps", MAX_STEPS, last_question)
    return "max_steps"


# ==========================================
# APPLIED JOBS CACHE
# ==========================================

class AppliedCache:
    def __init__(self):
        self.path  = PROFILE["APPLIED_LOG"]
        self.cache = self._load()

    def _load(self):
        p = Path(self.path)
        if not p.exists() or not p.read_text().strip():
            return {}
        return {e["job_url"]: e for e in json.loads(p.read_text())}

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(list(self.cache.values()), f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)

    def is_applied(self, url):
        return url in self.cache

    def mark(self, url):
        self.cache[url] = {"job_url": url, "applied_at": datetime.now(timezone.utc).isoformat()}
        self._save()


# ==========================================
# FAILED JOBS LOGGER
# ==========================================

class FailedLogger:
    def __init__(self):
        self.path  = FAILED_LOG
        p = Path(self.path)
        self.cache = json.loads(p.read_text()) if p.exists() and p.read_text().strip() else []

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.cache, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)

    def log(self, url, failure_type, msg, step=None, question=None):
        self.cache.append({
            "job_url":      url,
            "failed_at":    datetime.now(timezone.utc).isoformat(),
            "failure_type": failure_type,
            "error":        str(msg),
            "step":         step,
            "question":     question,
        })
        self._save()


# ==========================================
# LOGIN
# ==========================================

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

def create_driver():
    opts = Options()
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-notifications")

    # reduce automation detection noise
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    service = Service(ChromeDriverManager().install())

    driver = webdriver.Chrome(service=service, options=opts)
    return driver


def login(driver, config_path):
    with open(config_path) as f:
        cfg = json.load(f)
    wait = WebDriverWait(driver, 25)
    driver.get(LOGIN_URL)
    wait.until(EC.element_to_be_clickable((By.ID, "usernameField"))).send_keys(cfg["username"])
    wait.until(EC.element_to_be_clickable((By.ID, "passwordField"))).send_keys(cfg["password"])
    wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(),'Login')]"))).click()
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.info__heading[title]")))
    logging.info("Login successful.")
    return cfg["username"]


# ==========================================
# APPLY TO JOB
# ==========================================

def apply_to_job(driver, job_url, failed_logger):
    wait = WebDriverWait(driver, 25)
    try:
        wait.until(lambda d: (
            d.find_elements(By.ID, "already-applied") or
            d.find_elements(By.ID, "apply-button")
        ))
    except TimeoutException as e:
        failed_logger.log(job_url, "no_apply_state", str(e))
        return "no_apply_state"

    if [e for e in driver.find_elements(By.ID, "already-applied") if e.is_displayed()]:
        return "already_applied"

    try:
        btn      = driver.find_element(By.ID, "apply-button")
        btn_text = btn.text.strip().lower()
        if "applied" in btn_text:
            return "already_applied"
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", btn)
        logging.info("Apply button clicked.")
        time.sleep(2)
        if detect_platform_error(driver):
            failed_logger.log(job_url, "platform_error", "Platform error detected after apply click")
            return "platform_error"
    except Exception as e:
        failed_logger.log(job_url, "apply_click_error", str(e))
        return "apply_click_error"

    try:
        wait.until(lambda d: (
            d.find_elements(By.CSS_SELECTOR, "div.applied-job-content") or
            d.find_elements(By.CSS_SELECTOR, "div.chatbot_DrawerContentWrapper")
        ))
        if driver.find_elements(By.CSS_SELECTOR, "div.applied-job-content"):
            return "applied"
        if driver.find_elements(By.CSS_SELECTOR, "div.chatbot_DrawerContentWrapper"):
            return "screening"
    except TimeoutException as e:
        failed_logger.log(job_url, "unknown", str(e))
        return "unknown"


# ==========================================
# MAIN
# ==========================================

SKIP_URL_KEYWORDS = [["data", "analyst"]]

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    print(f"Profile: {ACTIVE_PROFILE}")

    with open(PROFILE["CONFIG"]) as f:
        cfg = json.load(f)

    resume_text   = load_resume(cfg["resume_path"])
    skill_summary = extract_skill_summary(resume_text)

    print("\n--- SKILL SUMMARY ---")
    print(skill_summary)
    print("---------------------\n")

    qa_store_path = _p(os.path.basename(os.path.dirname(PROFILE["APPLIED_LOG"])), "qa_store.json")
    qa_store      = QAStore(qa_store_path)   # auto-migrates from qa_cache + master_qa on first run
    applied_cache = AppliedCache()
    failed_logger = FailedLogger()

    logging.info(f"QA store: {len(qa_store.entries)} entries | Applied: {len(applied_cache.cache)}")

    driver = create_driver()
    login(driver, PROFILE["CONFIG"])

    with open(URLS_JSON, encoding="utf-8") as f:
        data = json.load(f)

    total_read = len(data)

    stats = {
        "score_filtered":    0,
        "extapp_filtered":   0,
        "already_applied":   0,
        "url_keyword_skip":  0,
        "duplicates_removed":0,
        "no_skillmatch":     0,
    }

    best = {}

    for job in data:
        score = job.get("score") or 0
        if score <= 0.4:
            stats["score_filtered"] += 1
            continue

        if job.get("extApp"):
            stats["extapp_filtered"] += 1
            continue

        url = job.get("URL", "")
        if applied_cache.is_applied(url):
            stats["already_applied"] += 1
            continue

        if any(all(kw in url.lower() for kw in pair) for pair in SKIP_URL_KEYWORDS):
            stats["url_keyword_skip"] += 1
            continue

        key = (job.get("Job Title"), job.get("Company Name"))
        if key in best:
            stats["duplicates_removed"] += 1

        if not best.get(key) or score > best[key].get("score", 0):
            best[key] = job


    def normalize_work_mode(value):
        if not value or value.strip().upper() == "N/A":
            return "Onsite"
        v = value.strip().lower()
        if "remote" in v and "hybrid" not in v:
            return "Remote"
        if "hybrid" in v:
            return "Hybrid"
        return "Onsite"


    priority = {"Remote": 0, "Hybrid": 1, "Onsite": 2}

    for job in best.values():
        job["work_mode"] = normalize_work_mode(job.get("work_mode"))
        job["skillMatch"] = bool(job.get("skillMatch"))

    jobs = sorted(
        best.values(),
        key=lambda x: (
            not x.get("skillMatch", False),
            -x.get("score", 0)
        )
    )
    urls = [j["URL"] for j in jobs]
    total = len(urls)

    logging.info("========== JOB FILTER FUNNEL ==========")
    logging.info(f"Total jobs read: {total_read}")
    logging.info(f"Filtered by score <=0.4: {stats['score_filtered']}")
    logging.info(f"Filtered extApp=True: {stats['extapp_filtered']}")
    logging.info(f"Filtered already applied: {stats['already_applied']}")
    logging.info(f"Filtered by URL keywords: {stats['url_keyword_skip']}")
    logging.info(f"Duplicate title+company removed: {stats['duplicates_removed']}")
    logging.info(f"Jobs without skillMatch (kept but ranked last): {stats['no_skillmatch']}")
    logging.info(f"Remaining unique jobs: {len(best)}")
    logging.info(f"Jobs to process: {total}")

    success_count = 0
    consec_errors = 0

    for idx, url in enumerate(urls, 1):
        try:
            logging.info(f"[{idx}/{total}] {url}")
            driver.get(url)
            status = apply_to_job(driver, url, failed_logger)

            ERROR_STATUSES = {"no_apply_state", "platform_error", "apply_click_error", "unknown"}

            if status in ERROR_STATUSES:
                logging.info(f"Skipped (status={status})")
                consec_errors += 1
                if consec_errors >= 8:
                    logging.error("Daily limit likely reached. Stopping.")
                    break
                continue

            consec_errors = 0

            if status in ("already_applied", "applied"):
                applied_cache.mark(url)
                if status == "applied":
                    success_count += 1
                    logging.info(f"Applied [{success_count}/{MAX_SUCCESS}]")
                    if success_count >= MAX_SUCCESS:
                        break
                continue

            if status == "screening":
                result = handle_screening(
                    driver, url, resume_text, skill_summary,
                    qa_store, failed_logger
                )
                if result == "applied":
                    applied_cache.mark(url)
                    qa_store.confirm_session()
                    success_count += 1
                    logging.info(f"Applied [{success_count}/{MAX_SUCCESS}]")
                    if success_count >= MAX_SUCCESS:
                        break
                logging.info(f"Screening result: {result}")
                continue

            logging.info(f"Skipped (status={status})")

        except Exception as e:
            logging.error(f"Error on {url}: {e}")
            failed_logger.log(url, "exception", str(e))

    logging.info(f"Done. Applied: {success_count} | QA store: {len(qa_store.entries)} entries")
    driver.quit()