#!/bin/zsh
export PATH=/opt/homebrew/bin:$PATH DATABASE_URL=postgresql://postgres@127.0.0.1:55481/m7b PYTHONDONTWRITEBYTECODE=1
SP=/private/tmp/claude-501/-Users-rupash-Claude-Verz-OS-v2-0-brain--scratch-wt-cg-governance/0c352820-7ea6-4c17-be4f-1f3d73ae9161/scratchpad
cd /Users/rupash/Claude/Verz-OS-v2.0/brain/.scratch/wt-cg-governance/trial/wk-model || exit 1
rm -f $SP/final3_done.txt
git branch --show-current > $SP/final3.txt
git rev-parse --short HEAD >> $SP/final3.txt
uv run python -m ruff check src tests >> $SP/final3.txt 2>&1
uv run python -m ruff format --check src tests migrations >> $SP/final3.txt 2>&1
uv run python -m mypy --platform linux >> $SP/final3.txt 2>&1
uv run python -m brain.ops.sweeps traceability 2>&1 | grep -E "^ok|names a group" >> $SP/final3.txt
uv run python -m pytest tests/unit/test_test_selection.py tests/unit/test_skill_routes.py tests/unit/test_webhook_routes.py tests/unit/test_tool_routes.py tests/unit/test_sign_in_routes.py tests/unit/test_setup_routes.py tests/unit/test_routing_routes.py tests/unit/test_provider_routes.py tests/unit/test_provider_registry_routes.py tests/unit/test_plugin_routes.py tests/unit/test_knowledge_routes.py tests/unit/test_console_overview_figures_routes.py tests/unit/test_channel_binding.py tests/unit/test_app_wiring.py tests/unit/test_parse_layout.py tests/unit/test_deployment_compatibility.py tests/unit/test_guards.py tests/unit/test_independence.py tests/unit/test_install_docs.py tests/unit/test_repository_template.py tests/unit/test_scaling.py tests/unit/test_search.py tests/unit/test_inference_client.py tests/unit/test_connector_routes.py tests/unit/test_model_server_routes.py "tests/unit/test_sweeps.py::test_every_registered_sweep_runs_and_passes_on_this_tree[client_independence]" tests/unit/test_architecture_doc.py tests/unit/test_requirements_register.py tests/unit/test_features.py tests/unit/test_money_figures.py tests/unit/test_install_routes.py tests/unit/test_console_screens.py tests/unit/test_console_reads.py tests/unit/test_console_design.py --no-header --disable-warnings -p no:cacheprovider > $SP/final3_unit.txt 2>&1
uv run python -m pytest tests/unit/test_acceptance.py --no-header --disable-warnings -p no:cacheprovider > $SP/final3_acc.txt 2>&1
echo done > $SP/final3_done.txt
