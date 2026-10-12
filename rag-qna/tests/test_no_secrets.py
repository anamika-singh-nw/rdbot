"""Fails if anything that looks like a credential is in the repository tree.

The bot reads ANTHROPIC_API_KEY from the environment and nothing else; no file in the
repo should ever contain a real key or token.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", "index"}

PATTERNS = {
    "Anthropic key": re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
    "OpenAI-style key": re.compile(r"\bsk-[A-Za-z0-9]{32,}"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "Hugging Face token": re.compile(r"\bhf_[A-Za-z0-9]{30,}"),
    "Slack token": re.compile(r"\bxox[abpr]-[A-Za-z0-9-]{10,}"),
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "assigned secret": re.compile(r"(?i)\b(api_?key|secret|token|password)\s*[=:]\s*['\"][^'\"\s]{12,}['\"]"),
}


def files():
    for p in REPO.rglob("*"):
        if p.is_file() and not SKIP_DIRS.intersection(p.relative_to(REPO).parts):
            yield p


def test_no_credentials_in_tree():
    found = []
    for p in files():
        try:
            text = p.read_text(errors="ignore")
        except OSError:
            continue
        for name, pat in PATTERNS.items():
            if pat.search(text):
                found.append(f"{p.relative_to(REPO)}: {name}")
    assert not found, "Possible credentials committed:\n" + "\n".join(found)


def test_no_env_files_outside_examples():
    envs = [p for p in files() if p.name.startswith(".env") and p.name != ".env.example"]
    assert not envs, envs
