"""Rewrites the generated block of .env.example from the declaration (untracked helper)."""

from pathlib import Path

from brain.install import ENV_BLOCK_END, ENV_BLOCK_START, env_example

path = Path(".env.example")
text = path.read_text(encoding="utf-8")
start = text.index(ENV_BLOCK_START)
end = text.index(ENV_BLOCK_END) + len(ENV_BLOCK_END)
path.write_text(text[:start] + env_example().strip() + text[end:], encoding="utf-8", newline="\n")
