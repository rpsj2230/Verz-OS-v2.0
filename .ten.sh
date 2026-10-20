#!/bin/zsh
export PATH=/opt/homebrew/bin:$PATH PYTHONDONTWRITEBYTECODE=1
SP=/private/tmp/claude-501/-Users-rupash-Claude-Verz-OS-v2-0-brain--scratch-wt-cg-governance/0c352820-7ea6-4c17-be4f-1f3d73ae9161/scratchpad
cd /Users/rupash/Claude/Verz-OS-v2.0/brain/.scratch/wt-cg-governance/trial/wk-model-snap || exit 1
rm -f $SP/ten_done.txt
for b in M7/model-server-frame M7/model-server-document-parts M7/model-server-embedding M7/model-server-provenance; do
  git checkout -q --detach $b
  echo "== $b"
  uv run python -m pytest tests/unit/test_deployment_release.py::test_a_rollback_refuses_when_the_database_is_past_the_release_it_goes_back_to tests/unit/test_independence.py tests/unit/test_inference_client.py tests/unit/test_install_docs.py tests/unit/test_repository_template.py tests/unit/test_scaling.py tests/unit/test_test_selection.py tests/unit/test_search.py tests/unit/test_guards.py tests/unit/test_deployment_compatibility.py tests/unit/test_model_server_routes.py tests/unit/test_connector_routes.py "tests/unit/test_sweeps.py::test_every_registered_sweep_runs_and_passes_on_this_tree[client_independence]" --no-header --disable-warnings -p no:cacheprovider 2>&1 | grep -E "^FAILED|passed|failed"
done > $SP/ten.txt 2>&1
echo done > $SP/ten_done.txt
