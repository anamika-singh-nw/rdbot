"""Call Claude through the local `claude` CLI (Claude Code, headless) instead of the API.

For local demos on a machine that is logged in to Claude Code but has no API key. It runs
under the logged-in Claude subscription, so it is for personal/local use, not for serving
other people — deploy with the API backend for that.

The CLI is locked down so the model can only read the prompt and write a reply:
`--tools ""` (no built-in tools), `--strict-mcp-config` with no config (none of the user's
MCP connectors, e.g. Gmail or Drive), `--disable-slash-commands` (no skills), and
`--setting-sources ""` (no local settings or CLAUDE.md). Sessions are not persisted.
"""

from __future__ import annotations

import json
import shutil
import subprocess

MODEL = "claude-opus-5-5"


class ClaudeCLIError(RuntimeError):
    pass


def available() -> bool:
    return shutil.which("claude") is not None


def ask(prompt: str, system: str, schema: dict | None = None, effort: str = "medium", timeout: int = 300):
    """Return the reply text, or the parsed object when `schema` is given."""
    if not available():
        raise ClaudeCLIError("The `claude` CLI is not installed or not on PATH.")
    cmd = [
        "claude", "-p",
        "--model", MODEL,
        "--effort", effort,
        "--system-prompt", system,
        "--tools", "",
        "--strict-mcp-config",
        "--disable-slash-commands",
        "--setting-sources", "",
        "--no-session-persistence",
        "--output-format", "json",
    ]
    if schema is not None:
        cmd += ["--json-schema", json.dumps(schema)]
    proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout)
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise ClaudeCLIError(f"claude CLI failed (exit {proc.returncode}): {(proc.stderr or proc.stdout)[:500]}")
    if out.get("is_error"):
        raise ClaudeCLIError(f"claude CLI error: {out.get('result') or out.get('subtype')}")
    if schema is not None:
        if out.get("structured_output") is None:
            raise ClaudeCLIError("claude CLI returned no structured output.")
        return out["structured_output"]
    return out.get("result", "")
