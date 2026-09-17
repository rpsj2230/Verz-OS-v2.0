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
# Task ids: M0.1.5, M0.4.5
.DEFAULT_GOAL := help
.PHONY: help dev test invariants lint types fmt check migrate revision seed reset deploy status

help:  ## Show this list
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n",$$1,$$2}'

# Every target below that M0.1.5 or M0.4.5 names is one line calling `brain.tasks`, which holds
# the command itself. `make` is not installed on the machine this is developed on, so the
# commands live where the interpreter can run them: `uv run python -m brain.tasks <task>` is
# the same thing without make. See the module docstring for why there is one copy.
dev:  ## Run the app locally with reload
	uv run python -m brain.tasks dev

test:  ## Every test, with the coverage floor
	uv run python -m brain.tasks test

invariants:  ## Only the rules that must never break
	uv run python -m brain.tasks invariants

lint:  ## Ruff
	uv run python -m brain.tasks lint

# `brain.tasks` passes `--platform linux` rather than this machine's. mypy narrows `sys.platform`
# to the platform it runs on, so on 2026-09-11 a Windows machine reported Success on a function
# whose other half was unreachable on the runner, CI went red on it, and because CI gates Deploy
# production sat on the previous commit. `make types-here` is the native run for debugging.
types:  ## Mypy, strict, against the platform this ships on
	uv run python -m brain.tasks types

types-here:  ## Mypy, strict, against this machine's own platform
	uv run python -m brain.tasks types-here

fmt:  ## Format in place
	uv run python -m brain.tasks fmt

check:  ## Everything the pre-push hook runs
	uv run python -m brain.tasks check

migrate:  ## Apply migrations to DATABASE_URL
	uv run python -m brain.tasks migrate

revision:  ## New migration: make revision m="what it does"
	uv run python -m alembic revision -m "$(m)"

seed:  ## Load the synthetic company into the database
	uv run python -m brain.tasks seed

reset:  ## Drop everything and rebuild. Refuses any install that is not a development one.
	uv run python -m brain.tasks reset

deploy:  ## Push the current published image to the VPS
	sh ops/deploy.sh

status:  ## Recompute progress from git history
	uv run python -m brain.status
