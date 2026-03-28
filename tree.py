# tree.py

from pathlib import Path

# ================== CONFIG ==================
ROOT_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = Path("folder_tree.txt")

# Folders to ignore (names only, not full paths)
IGNORE_FOLDERS = {
    "__pycache__",
    ".git",
    ".venv",
    "enhanced_env",
    "node_modules",
    "text_project", "data", "old","review", "close-applied-tabs", "resume_transformers", "vllm" , "outputs"
}

# Files to ignore (by filename)
IGNORE_FILES = {
    "folder_tree.txt",
    "tree.py", "ontology.rar"
}

# Optional: ignore file extensions
IGNORE_EXTENSIONS = {
    ".pyc",
    ".log"
}
# ===========================================


def generate_tree(root: Path, prefix=""):
    lines = []

    entries = sorted(root.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))

    for index, entry in enumerate(entries):
        if entry.name in IGNORE_FOLDERS:
            continue

        connector = "└── " if index == len(entries) - 1 else "├── "
        line = f"{prefix}{connector}{entry.name}"
        lines.append(line)

        if entry.is_dir():
            extension = "    " if index == len(entries) - 1 else "│   "
            lines.extend(generate_tree(entry, prefix + extension))
        else:
            if entry.suffix in IGNORE_EXTENSIONS or entry.name in IGNORE_FILES:
                lines.pop()  # remove ignored file

    return lines


def main():
    if not ROOT_DIR.exists():
        print(f"Root path not found: {ROOT_DIR}")
        return

    tree_lines = [ROOT_DIR.name]
    tree_lines.extend(generate_tree(ROOT_DIR))

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(tree_lines))

    print(f"Tree saved to: {OUTPUT_FILE.resolve()}")


if __name__ == "__main__":
    main()
