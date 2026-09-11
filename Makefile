# Every command anyone needs, in one place, with no arguments to remember.
#
# `uv run python -m <tool>`, never `uv run <tool>`, and the difference is not style. The
# second spawns the console shim uv writes into the environment, and Windows Application
# Control intermittently refuses a freshly written unsigned executable in a temporary
# directory: `Failed to spawn: mypy ... (os error 4551)`. Intermittent is worse than
# consistent, because it presents as a gate failing with no gate having an opinion. Running
# the interpreter uv already trusts and importing the tool as a module spawns nothing new.
# `brain.ops.mutation` and `ops/hooks/pre-push` carry the same fix for the same reason.
#
# Task ids: M0.1.5
.DEFAULT_GOAL := help
.PHONY: help dev test invariants lint types fmt check migrate revision seed reset deploy status

help:  ## Show this list
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n",$$1,$$2}'

dev:  ## Run the app locally with reload
	uv run python -m uvicorn brain.app:app --reload --port 8000

test:  ## Every test, with the coverage floor
	uv run python -m pytest --cov

invariants:  ## Only the rules that must never break
	uv run python -m pytest tests/invariants -q

lint:  ## Ruff
	uv run python -m ruff check src tests migrations

types:  ## Mypy, strict
	uv run python -m mypy

fmt:  ## Format in place
	uv run python -m ruff format src tests migrations
	uv run python -m ruff check src tests migrations --fix

check: fmt lint types invariants  ## Everything the pre-push hook runs
	@echo "all gates green"

migrate:  ## Apply migrations to DATABASE_URL
	uv run python -m alembic upgrade head

revision:  ## New migration: make revision m="what it does"
	uv run python -m alembic revision -m "$(m)"

seed:  ## Load the synthetic company into the database
	uv run python -m brain.seed

reset:  ## Drop everything and rebuild. Destroys local data.
	uv run python -m alembic downgrade base && uv run python -m alembic upgrade head && $(MAKE) seed

deploy:  ## Push the current published image to the VPS
	sh ops/deploy.sh

status:  ## Recompute progress from git history
	uv run python -m brain.status
