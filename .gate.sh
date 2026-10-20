#!/bin/zsh
# usage: .gate.sh <tag> ; runs in wk-model-merge on the checked-out branch
export PATH=/opt/homebrew/bin:$PATH DATABASE_URL=postgresql://postgres@127.0.0.1:55481/m7c PYTHONDONTWRITEBYTECODE=1
OUT=/tmp/pgm7/gate_$1
cd /Users/rupash/Claude/Verz-OS-v2.0/brain/.scratch/wt-cg-governance/trial/wk-model-merge || exit 1
rm -f $OUT.done
{
  git rev-parse --short HEAD
  uv run python -m ruff check src tests | tail -1
  uv run python -m ruff format --check src tests migrations | tail -1
  uv run python -m mypy --platform linux | tail -1
  uv run python -m alembic heads
  uv run python -m brain.ops.sweeps traceability 2>&1 | grep -E "^ok|names a group"
} > $OUT.txt 2>&1
uv run python -m pytest tests/unit/test_architecture_doc.py tests/unit/test_requirements_register.py tests/unit/test_features.py tests/unit/test_money_figures.py tests/unit/test_install_routes.py tests/unit/test_console_screens.py tests/unit/test_console_reads.py tests/unit/test_console_design.py tests/unit/test_acceptance.py --no-header --disable-warnings -p no:cacheprovider > $OUT.pinned.txt 2>&1
echo done > $OUT.done
