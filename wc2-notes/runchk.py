"""Run the checks of one acceptance module against $DATABASE_URL at head, print outcomes."""
import asyncio, os, sys
from brain.ops import acceptance_run
from brain.ops.acceptance import registered
from brain.settings import settings_from
from brain.db import normalise_database_url
import importlib

module = sys.argv[1]
only = sys.argv[2:] 
url = os.environ["DATABASE_URL"]
importlib.import_module(module)
settings = settings_from({"BRAIN_DATABASE_URL": url})
checks = [c for c in registered((module,)) if not only or c.name in only]
_, results = asyncio.run(acceptance_run.run_acceptance(normalise_database_url(url), settings=settings, commit="abc1234", checks=checks, force=True))
for r in results:
    print(r.name, r.outcome, r.reason)
