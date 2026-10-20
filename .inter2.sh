#!/bin/zsh
export PATH=/opt/homebrew/bin:$PATH PYTHONDONTWRITEBYTECODE=1
SP=/private/tmp/claude-501/-Users-rupash-Claude-Verz-OS-v2-0-brain--scratch-wt-cg-governance/0c352820-7ea6-4c17-be4f-1f3d73ae9161/scratchpad
cd /Users/rupash/Claude/Verz-OS-v2.0/brain/.scratch/wt-cg-governance/trial/wk-model-snap || exit 1
for b in M7/model-server-frame M7/model-server-document-parts M7/model-server-embedding M7/model-server-provenance; do
  git checkout -q --detach $b
  echo "== $b"
  uv run python -m ruff check src tests 2>&1 | tail -1
  uv run python -m ruff format --check src tests migrations 2>&1 | tail -1
  uv run python -m mypy --platform linux 2>&1 | tail -1
  uv run python -m pytest tests/unit/test_search.py tests/unit/test_guards.py tests/unit/test_tables.py tests/unit/test_model_server.py tests/unit/test_overlay_tuning.py tests/unit/test_acceptance_modelserver.py --no-header --disable-warnings -p no:cacheprovider 2>&1 | tail -2
done > $SP/intermediate2.txt 2>&1
echo done >> $SP/intermediate2.txt
