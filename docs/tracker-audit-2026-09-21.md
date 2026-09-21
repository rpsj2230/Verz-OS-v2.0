# Proof recorded on 2026-09-21

A proof commit that changes no file is dropped by a rebase merge, so its `Closes:` lines never
reach main (PR #51, "Eleven foundation tasks", merged empty). This note carries the same claims
with their evidence so the commit is kept.

| Task | Evidence |
| --- | --- |
| M0.4.1 | CI job "The whole stack starts" boots `docker-compose.lite.yml` (COMPOSE_FILE) |
| M31.2.2.3 | CI job "The previous release runs on the new schema" ran its steps on PRs #42 and #44, which carry migrations |
| M38.1.1.1 | CI job "Branch named for its module" passes on every pull request |
| M31.1.3.4 | unit test tests/unit/test_app_wiring.py: CORS admits only the named console and widget origins |
| M31.1.4.1 | unit tests for the deprecation headers and notice (test_api_deprecation) |
| M31.1.4.4 | tests/unit/test_api_paging.py: every paged route has one shape, no exceptions left |
| M31.1.2.2 | tests/unit/test_app_wiring.py: an in-flight request finishes under a real uvicorn shutdown |
| M0.2.5 | the TypedResult entity-tag tests (mypy and runtime) |
| M41.1.4, M41.1.5, M41.1.7 | Install > Settings on the owner's install shows branding, identity provider and storage values, each with its source |
