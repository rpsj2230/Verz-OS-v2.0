"""One person moved by the scheduled staff run, and every rule of a move asked of the state the
run leaves: the knowledge they read, the answer they were served, the memory they are told, the
automation they own and the reach the one resolver gives them.

`tests/unit/test_lifecycle.py` proves each rule of a move over values the test builds, and
`tests/unit/test_starter_pack_sync.py` proves the packs change on the tables. Neither shows the
rules hold together on what the run leaves behind, which is what M26.2.7 asks: a test covering
every one of the mover leaves. **This drives the run, reads the person's reach back from the one
resolver (`StoredEntitlements`) and hands that reach to the real rule of each leaf**, so nothing
here is a reach the test wrote by hand. It skips where there is no server, and CI always has one.

**The personal agent that follows its owner (M26.2.2) is not asked here**, and the roll-up
`brain.ops.acceptance_checks_jml_roll_up` leaves M26.2.7 not run until a check names it. That leaf
is built on another branch, and a stand-in agent here would prove a rule this test did not read.

Task ids: M26.2.1, M26.2.3, M26.2.4, M26.2.5, M26.2.6, M26.2.7
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from brain.core.department import department_scope
from brain.core.entitlement import Capability
from brain.gate.cache_key import key_for
from brain.memory.formation import Formation, recallable
from tests.unit.test_mover_automations import NOW as AUTOMATION_DUE
from tests.unit.test_mover_automations import first_night, next_runs, second_night, turned_on
from tests.unit.test_starter_pack_sync import READ_AT, a_company, found, reach_of

READ = Capability(value="read:knowledge")
QUESTION = "how many clients are on retainer"


def _formed(department: str, reach_hash: str) -> Formation:
    """A memory Katherine's assistant formed under the knowledge read in one department."""
    return Formation(
        principal_id="p_katherine",
        capabilities=(READ,),
        scope=department_scope(department),
        ent_hash=reach_hash,
        formed_at=READ_AT,
    )


@pytest.mark.needs_db
def test_a_person_the_run_moves_is_changed_by_every_rule_of_a_move_at_once() -> None:
    """**M26.2.7.** Katherine is in finance on the first night and in engineering on the second,
    with an automation of hers and a memory formed under finance. After the second night, from the
    reach the resolver hands back and with nothing reindexed, purged or restarted: she reads the
    engineering document and did not before (M26.2.6); the key her old answers sit under cannot be
    built from her new reach (M26.2.4); the finance memory is not recalled and an engineering one
    is (M26.2.5); her automation is paused (M26.2.3); and her reach changed on the very next read
    (M26.2.1). Priya, whom nobody moved, keeps her automation and her reach.

    Delete this and the rules of a move are each tested over values the test wrote, with nothing
    showing they hold together on what the run actually leaves behind."""
    with a_company("brain_mover_end_to_end") as url:
        turned_on(url)
        first_night(url)
        before = reach_of(url, "p_katherine")
        read_before = found(url, "p_katherine")
        priya_before = reach_of(url, "p_priya")
        second_night(url)
        after = reach_of(url, "p_katherine")
        read_after = found(url, "p_katherine")
        priya_after = reach_of(url, "p_priya")
        runs = next_runs(url)

    now = READ_AT + timedelta(days=2)
    assert read_before == ()
    assert read_after and {one.department for one in read_after} == {"engineering"}
    assert before.ent_hash() != after.ent_hash()
    assert key_for(QUESTION, before.ent_hash(), "agent-cfg", 1, {}) != key_for(
        QUESTION, after.ent_hash(), "agent-cfg", 1, {}
    )
    finance_memory = _formed("finance", before.ent_hash())
    engineering_memory = _formed("engineering", after.ent_hash())
    assert recallable([(finance_memory, 1.0)], before, now=now) != ()
    assert recallable([(finance_memory, 1.0)], after, now=now) == ()
    assert recallable([(engineering_memory, 1.0)], after, now=now) != ()
    assert runs["auto_p_katherine"] is None
    assert runs["auto_p_priya"] == AUTOMATION_DUE
    assert priya_before.ent_hash() == priya_after.ent_hash()
