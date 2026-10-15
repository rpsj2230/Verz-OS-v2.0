import asyncio, sys, dataclasses, traceback, importlib
from tests.unit.test_acceptance import at_head
from brain.db import normalise_database_url
from brain.ops import acceptance_run, acceptance
from brain.settings import settings_from
from brain.session import make_app_engine
mod = importlib.import_module(sys.argv[1])
name = sys.argv[2]
chk = [c for c in acceptance.registered((sys.argv[1],)) if c.name == name][0]
orig = chk.run
async def wrapped(h):
    try:
        await orig(h)
    except Exception:
        traceback.print_exc(); raise
chk = dataclasses.replace(chk, run=wrapped)
with at_head("brain_dbg_" + sys.argv[3]) as url:
    async def go():
        engine = make_app_engine(normalise_database_url(url))
        try:
            r = await acceptance_run.run_suite(engine,(chk,),settings=settings_from({"BRAIN_DATABASE_URL":url}),stream=sys.stderr)
            print([(x.outcome,x.reason) for x in r])
        finally:
            await engine.dispose()
    asyncio.run(go())
