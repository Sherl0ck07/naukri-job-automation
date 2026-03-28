# ===== core/job_cache.py =====

import json
import os
import threading
from datetime import datetime, timezone, timedelta

TTL_DAYS = 30


class JobScrapeCache:
    """
    Per-profile disk-backed cache for scraped Naukri job data.

    - Thread-safe: single RLock guards all reads and writes.
    - TTL: entries older than TTL_DAYS days are pruned on init.
    - Storage: <profile_dir>/<cache_filename>
      e.g. profiles/pandurang/job_cache_B.json

    Entry format:
        {
            "<job_id>": {
                "cached_at": "2026-02-24T10:00:00+00:00",
                "job_data":  { ...full dict from extract_job_details... }
            }
        }
    """

    def __init__(self, profile_dir: str, cache_filename: str = "job_cache.json"):
        os.makedirs(profile_dir, exist_ok=True)
        self._path  = os.path.join(profile_dir, cache_filename)
        self._lock  = threading.RLock()
        self._store: dict = {}

        self._load()
        pruned = self._prune_expired()
        if pruned:
            self._save()

    # ── public API ────────────────────────────────────────────────────────

    def is_cached(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._store

    def get(self, job_id: str) -> dict | None:
        """Return the cached job_data dict, or None if not found."""
        with self._lock:
            entry = self._store.get(job_id)
            return entry["job_data"] if entry else None

    def get_batch(self, job_ids: list[str]) -> dict[str, dict]:
        """Return {job_id: job_data} for every id that is cached."""
        with self._lock:
            return {
                jid: self._store[jid]["job_data"]
                for jid in job_ids
                if jid in self._store
            }

    def set_batch(self, jobs: list[dict]) -> int:
        """
        Persist a list of freshly scraped job dicts.
        Each dict must contain a 'job_id' key.
        Returns number of entries written.
        """
        if not jobs:
            return 0

        now     = datetime.now(timezone.utc).isoformat()
        written = 0

        with self._lock:
            for job in jobs:
                job_id = job.get("job_id")
                if not job_id:
                    continue
                self._store[job_id] = {
                    "cached_at": now,
                    "job_data":  job,
                }
                written += 1
            if written:
                self._save()

        return written

    def stats(self) -> dict:
        with self._lock:
            return {"total_entries": len(self._store), "path": self._path}

    # ── internals ─────────────────────────────────────────────────────────

    def _load(self):
        if not os.path.exists(self._path):
            self._store = {}
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                self._store = json.load(f)
        except (json.JSONDecodeError, OSError):
            self._store = {}

    def _save(self):
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._store, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self._path)  # atomic on all major OSes

    def _prune_expired(self) -> int:
        cutoff  = datetime.now(timezone.utc) - timedelta(days=TTL_DAYS)
        expired = [
            jid for jid, entry in self._store.items()
            if datetime.fromisoformat(
                entry.get("cached_at", "1970-01-01T00:00:00+00:00")
            ) < cutoff
        ]
        for jid in expired:
            del self._store[jid]
        return len(expired)