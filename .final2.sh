#!/bin/zsh
export PATH=/opt/homebrew/bin:$PATH DATABASE_URL=postgresql://postgres@127.0.0.1:55481/m7b PYTHONDONTWRITEBYTECODE=1
SP=/private/tmp/claude-501/-Users-rupash-Claude-Verz-OS-v2-0-brain--scratch-wt-cg-governance/0c352820-7ea6-4c17-be4f-1f3d73ae9161/scratchpad
cd /Users/rupash/Claude/Verz-OS-v2.0/brain/.scratch/wt-cg-governance/trial/wk-model || exit 1
rm -f $SP/final2_done.txt
git branch --show-current > $SP/final2.txt
uv run python -m ruff check src tests >> $SP/final2.txt 2>&1
uv run python -m ruff format --check src tests migrations >> $SP/final2.txt 2>&1
uv run python -m mypy --platform linux >> $SP/final2.txt 2>&1
uv run python -m brain.ops.sweeps traceability 2>&1 | grep -E "^ok|names a group" >> $SP/final2.txt
uv run python -m pytest tests/unit/test_search.py tests/unit/test_tables.py tests/unit/test_connector_routes.py tests/unit/test_deployment_release.py tests/unit/test_independence.py tests/unit/test_inference_client.py tests/unit/test_install_docs.py tests/unit/test_model_server_routes.py tests/unit/test_repository_template.py tests/unit/test_scaling.py tests/unit/test_sweeps.py tests/unit/test_knowledge_item.py tests/unit/test_acceptance_modelserver.py tests/unit/test_acceptance_modelserver_documents.py tests/unit/test_how_a_passage_was_read_db.py tests/unit/test_knowledge_intake_db.py --no-header --disable-warnings -p no:cacheprovider > $SP/final2_unit.txt 2>&1
uv run python -m pytest tests/invariants --no-header --disable-warnings -p no:cacheprovider > $SP/final2_inv.txt 2>&1
echo done > $SP/final2_done.txt
