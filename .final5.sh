#!/bin/zsh
export PATH=/opt/homebrew/bin:$PATH DATABASE_URL=postgresql://postgres@127.0.0.1:55481/m7c PYTHONDONTWRITEBYTECODE=1
SP=/private/tmp/claude-501/-Users-rupash-Claude-Verz-OS-v2-0-brain--scratch-wt-cg-governance/0c352820-7ea6-4c17-be4f-1f3d73ae9161/scratchpad
cd /Users/rupash/Claude/Verz-OS-v2.0/brain/.scratch/wt-cg-governance/trial/wk-model-merge || exit 1
rm -f $SP/final5_done.txt
git rev-parse --short HEAD > $SP/final5.txt
uv run python -m pytest tests/invariants --no-header --disable-warnings -p no:cacheprovider > $SP/final5_inv.txt 2>&1
uv run python -m pytest tests/unit/test_acceptance.py --no-header --disable-warnings -p no:cacheprovider > $SP/final5_acc.txt 2>&1
echo done > $SP/final5_done.txt
