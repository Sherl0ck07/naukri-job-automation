# ===== migrate.py =====
# Run ONCE from oneClickShell/ root:  python migrate.py
# Safe: only moves, never deletes. Skips if destination already exists.

import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))

def move(src, dst):
    src = os.path.join(HERE, src)
    dst = os.path.join(HERE, dst)
    if not os.path.exists(src):
        print(f"  SKIP (not found): {src}")
        return
    if os.path.exists(dst):
        print(f"  SKIP (already exists): {dst}")
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.move(src, dst)
    print(f"  MOVED: {src}  →  {dst}")


print("\n── Creating folder structure ──")
for folder in [
    "core/auto_apply",
    "profiles/pandurang",
    "profiles/mayuri",
    "outputs",
]:
    os.makedirs(os.path.join(HERE, folder), exist_ok=True)
    print(f"  OK: {folder}/")


print("\n── Core scripts ──")
move("main.py",          "core/main.py")
move("helpers.py",       "core/helpers.py")
move("score.py",         "core/score.py")
move("report.py",        "core/report.py")
move("resume_parser.py", "core/resume_parser.py")
move("cache/job_cache.py", "core/job_cache.py")
move("AutoApply/auto_apply_new.py", "core/auto_apply/auto_apply_new.py")

# __init__.py so auto_apply is importable as a package
init = os.path.join(HERE, "core/auto_apply/__init__.py")
if not os.path.exists(init):
    open(init, "w").close()
    print("  CREATED: core/auto_apply/__init__.py")


print("\n── Pandurang profile ──")
move("config.json",      "profiles/pandurang/config_B.json")
move("config-old.json",  "profiles/pandurang/config_A.json")
# Resume profile lives outside the project — copy (don't move) it in
_resume_src = r"C:\Users\imjad\Desktop\Resumes\resume_profile.json"
_resume_dst = os.path.join(HERE, "profiles", "pandurang", "resume_profile.json")
if os.path.exists(_resume_src) and not os.path.exists(_resume_dst):
    shutil.copy2(_resume_src, _resume_dst)
    print(f"  COPIED: {_resume_src}  →  {_resume_dst}")
elif not os.path.exists(_resume_src):
    print(f"  SKIP (not found): {_resume_src}")
else:
    print(f"  SKIP (already exists): {_resume_dst}")
move("links.txt",        "profiles/pandurang/links.txt")

# AutoApply shared data (A and B share same person's data)
move("AutoApply/applied_jobs.json",       "profiles/pandurang/applied_jobs.json")
move("AutoApply/master_qa.json",          "profiles/pandurang/master_qa.json")
move("AutoApply/qa_cache.json",           "profiles/pandurang/qa_cache.json")
move("AutoApply/failed_applications.json","profiles/pandurang/failed_applications.json")

# Cache files
move("cache/job_cache_A.json", "profiles/pandurang/job_cache_A.json")
move("cache/job_cache_B.json", "profiles/pandurang/job_cache_B.json")


print("\n── Mayuri profile ──")
move("config - Mayuri.json",               "profiles/mayuri/config.json")
move("Mayuri_Baraskar_ReactJS.pdf",        "profiles/mayuri/resume.pdf")
move("resume_profile_mayuri.json",         "profiles/mayuri/resume_profile.json")
move("AutoApply/C_mayuri/applied_jobs.json","profiles/mayuri/applied_jobs.json")
move("AutoApply/C_mayuri/master_qa.json",  "profiles/mayuri/master_qa.json")
move("AutoApply/C_mayuri/qa_cache.json",   "profiles/mayuri/qa_cache.json")
move("cache/job_cache_M.json",             "profiles/mayuri/job_cache.json")

# Mayuri gets her own failed_applications
mayuri_failed = os.path.join(HERE, "profiles/mayuri/failed_applications.json")
if not os.path.exists(mayuri_failed):
    with open(mayuri_failed, "w") as f:
        f.write("[]")
    print("  CREATED: profiles/mayuri/failed_applications.json (empty)")

# Mayuri needs her own links file — create empty placeholder if not present
mayuri_links = os.path.join(HERE, "profiles/mayuri/links.txt")
if not os.path.exists(mayuri_links):
    open(mayuri_links, "w").close()
    print("  CREATED: profiles/mayuri/links.txt (empty placeholder)")


print("\n── Done. Old empty folders left in place — remove manually if desired. ──\n")