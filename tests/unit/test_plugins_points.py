"""The register of extension points, and every way a point can be declared dishonestly.

Every test here is about a claim a reader is entitled to make from the register: that a
point saying "plugin" would really take one, that a point naming a contract names one that
exists, and that a point saying nothing about isolation is a point nobody may supply.

Task ids: M29.1.1, M29.1.2, M29.1.3, M29.1.4, M29.1.5, M29.1.7, M29.1.12
Task ids: M29.2.5
"""

from __future__ import annotations

from pathlib import Path

import pytest

from brain.plugins.points import (
    BY_NAME,
    POINTS,
    Answer,
    Carries,
    Direction,
    ExtensionPoint,
    IsolationTier,
    PointError,
    contract_gaps,
    point_named,
    points_answering,
    undecided_points,
)

REPO = Path(__file__).resolve().parents[2]


def _a_point(**overrides: object) -> ExtensionPoint:
    base: dict[str, object] = {
        "name": "probe",
        "leaf": "M29.1.1",
        "answer": Answer.CONFIGURATION,
        "why": "a probe, built by a test",
    }
    base.update(overrides)
    return ExtensionPoint(**base)  # type: ignore[arg-type]


def _a_plugin_point(**overrides: object) -> ExtensionPoint:
    base: dict[str, object] = {
        "answer": Answer.PLUGIN,
        "contract": "brain.channels.adapter:ChannelAdapter",
        "direction": Direction.CONSUMES,
        "carries": Carries.CODE,
        "tier": IsolationTier.SIDECAR,
    }
    base.update(overrides)
    return _a_point(**base)


# ------------------------------------------------------- the register itself
def test_the_register_names_every_one_of_m29s_sixteen_interface_leaves() -> None:
    """The register is a reading of M29.1, so a leaf missing from it is a point nobody
    decided about while the register reads as complete. Sixteen is the number of leaves in
    that task group and the count is asserted against the leaves rather than against itself.

    Delete this and a seventeenth leaf can be added to the WBS with nothing here noticing,
    which is the exact failure CLAUDE.md records about positional task ids."""
    leaves = [one.leaf for one in POINTS]

    assert leaves == [f"M29.1.{n}" for n in range(1, 17)]


def test_every_point_is_named_once() -> None:
    """`BY_NAME` is what `point_named` reads and a duplicate would silently keep the last
    one, so two points could be declared and one of them would be unreachable with nothing
    saying which. Delete this and the register can hold a point nothing can look up."""
    assert len(BY_NAME) == len(POINTS)


def test_the_answers_sum_to_the_register() -> None:
    """The distribution is the finding this module exists to report: seven points a plugin
    may take, three answered another way, six with no contract and no decision. Asserted as
    a partition so a point cannot fall out of the counts by acquiring a fourth answer.

    Delete this and the honest answer to 'does M29 keep the promise' becomes a sentence in
    a docstring rather than a number a test holds."""
    counted = {answer: len(points_answering(answer)) for answer in Answer}

    assert counted == {
        Answer.PLUGIN: 7,
        Answer.CONFIGURATION: 2,
        Answer.FLAG: 1,
        Answer.UNDECIDED: 6,
    }
    assert sum(counted.values()) == len(POINTS)


def test_every_contract_the_register_names_is_defined_in_this_tree() -> None:
    """**The check that stops the register describing an intention.** A point naming
    `brain.knowledge.search:Retriever` would read exactly like the ten that are real, and a
    reader sent here by a refusal elsewhere would go looking for a protocol nobody wrote.

    Ten is asserted alongside, because a check over an empty set of contracts also returns
    no gaps, and the register's own claim is that ten of the sixteen points are defined
    somewhere in this tree.

    Delete this and a renamed protocol leaves the register pointing at nothing, which is
    discovered at the first install rather than here."""
    assert len([one for one in POINTS if one.contract]) == 10
    assert contract_gaps(REPO) == ()


def test_a_point_naming_a_contract_nothing_defines_is_reported() -> None:
    """The positive test above passes on a register whose every contract is empty, and it
    would pass on a `contract_gaps` that returned an empty tuple unconditionally. This is
    the half that proves the check reads the source.

    Delete this and `contract_gaps` can be reduced to `return ()` with the suite green."""
    invented = _a_point(contract="brain.knowledge.search:Retriever")

    found = contract_gaps(REPO, (invented,))

    assert len(found) == 1
    assert "brain.knowledge.search:Retriever" in found[0]


@pytest.mark.parametrize(
    ("body", "symbol"),
    [
        ("class Thing:\n    pass\n", "Thing"),
        ("def Thing() -> None:\n    return None\n", "Thing"),
        ("async def Thing() -> None:\n    return None\n", "Thing"),
        ("Thing: int = 1\n", "Thing"),
        ("Thing = 1\n", "Thing"),
    ],
)
def test_a_contract_counts_however_the_module_spells_it(
    tmp_path: Path, body: str, symbol: str
) -> None:
    """A protocol is usually a class and a contract is occasionally a callable or an alias.
    All five spellings are top-level definitions and all five have to count, or the register
    would report a gap against a module that does define the thing.

    Delete this and the assignment branches stop being exercised, so a contract declared as
    `Fetch = Callable[...]` reads as missing."""
    module = tmp_path / "src" / "probe_pkg" / "mod.py"
    module.parent.mkdir(parents=True)
    module.write_text(body, encoding="utf-8", newline="\n")
    point = _a_point(contract=f"probe_pkg.mod:{symbol}")

    assert contract_gaps(tmp_path, (point,)) == ()


def test_a_contract_in_a_package_init_counts_as_much_as_one_in_a_module(tmp_path: Path) -> None:
    """A contract defined in a package's `__init__.py` is as importable as one in a module,
    so the lookup tries the module file first and the package second.

    Delete this and a contract can only ever live in a `.py` file named for the module."""
    init = tmp_path / "src" / "probe_pkg" / "sub" / "__init__.py"
    init.parent.mkdir(parents=True)
    init.write_text("class Thing:\n    pass\n", encoding="utf-8", newline="\n")
    point = _a_point(contract="probe_pkg.sub:Thing")

    assert contract_gaps(tmp_path, (point,)) == ()


def test_a_symbol_a_module_only_re_exports_is_not_that_modules_contract() -> None:
    """`brain.plugins` imports `PluginManifest` and does not define it. An import is a
    convenience and the contract belongs to whoever wrote it, so a point naming the
    re-exporting package is naming the wrong owner and is reported.

    This is why the check parses rather than imports: an import would have found the symbol
    on the package and called the point satisfied. Delete this and two modules can both
    claim to own one contract."""
    found = contract_gaps(REPO, (_a_point(contract="brain.plugins:PluginManifest"),))

    assert len(found) == 1
    assert contract_gaps(REPO, (_a_point(contract="brain.plugins.manifest:PluginManifest"),)) == ()


def test_a_contract_in_a_module_that_does_not_exist_is_reported_rather_than_raised() -> None:
    """**A mutation found this.** Falsifying the `is_file` guard survived every test, because
    each of them named a module that exists and a symbol that does not. Without the guard the
    parser is handed a path nothing wrote and raises `FileNotFoundError`, so a register with
    one stale module name stops the sweep instead of reporting the one point that is wrong.

    The refusing direction is the one that matters: a gaps function that raises has no way to
    tell you about the other fifteen points. Delete this and the guard becomes unreachable
    again."""
    point = _a_point(contract="brain.nowhere.at_all:Thing")

    found = contract_gaps(REPO, (point,))

    assert len(found) == 1
    assert "brain.nowhere.at_all:Thing" in found[0]


def test_a_symbol_that_is_not_at_the_top_level_does_not_count_as_a_contract() -> None:
    """A name bound inside a function is not a contract anything can import, and counting it
    would let a point name a local variable. Parsed rather than searched, so the difference
    between a definition and a mention is the parser's rather than a regex's.

    Delete this and a point can name a symbol nothing outside its own function can reach."""
    point = _a_point(contract="brain.plugins.points:found")

    assert contract_gaps(REPO, (point,)) != ()


def test_a_point_with_no_contract_is_not_reported_as_a_contract_gap() -> None:
    """The six undecided points name nothing, and reporting them here would put the same
    fact in two places with two different meanings: one saying a protocol is missing and one
    saying a decision is. They are different problems for different people.

    Delete this and the undecided six start failing a check about symbols."""
    assert contract_gaps(REPO, (_a_point(),)) == ()


def test_every_undecided_point_says_which_leaf_it_leaves_open() -> None:
    """A count of open points is not actionable; the leaf is. Six is asserted against the
    register rather than as a literal so this and the partition above cannot drift apart.

    Delete this and the six become invisible the moment nobody reads the register."""
    open_points = undecided_points()

    assert len(open_points) == len(points_answering(Answer.UNDECIDED))
    for one in open_points:
        assert one.startswith("M29.1.")


def test_point_named_answers_nothing_for_a_name_that_is_not_a_point() -> None:
    """`point_named` is called with a name off a manifest that arrived from outside, so the
    absent case is the ordinary one rather than the error. Delete this and a caller starts
    handling an exception on the path a bad manifest takes every time."""
    assert point_named("channel_adapter") is not None
    assert point_named("not_a_point") is None


# ------------------------------------------------------- how a point may be declared
def test_a_point_needs_a_name_shaped_like_a_name() -> None:
    """The name is what a manifest names and what `BY_NAME` keys on, so a name with a space
    or a capital in it is a point no manifest can reach. Delete this and the register can
    hold an unreachable point."""
    with pytest.raises(PointError, match="not an extension point name"):
        _a_point(name="Channel Adapter")


def test_a_point_must_claim_a_leaf_that_is_one_of_m29s() -> None:
    """A point claiming `M30.1.1` puts an id in a source docstring that the traceability
    sweep credits to another module's work. CLAUDE.md records the same failure from the
    other direction, where four M27 claims silently repointed at leaves about backups.

    Delete this and the register can claim leaves that belong to something else."""
    with pytest.raises(PointError, match="not one of M29's interface leaves"):
        _a_point(leaf="M30.1.1")


@pytest.mark.parametrize("blank", ["", " ", "\n", "\t "])
def test_a_point_with_no_reason_written_down_is_refused(blank: str) -> None:
    """`why` is what a reader gets when a module elsewhere refuses their request and sends
    them here, and whitespace is refused as well as empty because a space satisfies a length
    check and says nothing. A point nobody can explain is one somebody reclassifies as a
    plugin the first time a client asks.

    Delete this and the register fills up with points whose terms have no argument."""
    with pytest.raises(PointError, match="no reason written down"):
        _a_point(why=blank)


def test_a_contract_that_is_not_module_and_symbol_is_refused() -> None:
    """`contract_gaps` splits on the colon, so a contract without one is a check that never
    runs while the point reads as checked. Delete this and a malformed contract silently
    stops being verified."""
    with pytest.raises(PointError, match="cannot check that it exists"):
        _a_point(contract="brain.channels.adapter.ChannelAdapter")


def test_a_plugin_point_with_no_contract_is_refused() -> None:
    """**This is the promise-keeping check.** A point declared as taking a plugin with
    nothing to plug into is exactly the failure M29 is asked about: every module elsewhere
    that refuses a company-specific request by pointing here would be pointing at an
    interface that does not exist.

    Delete this and the register can say yes to a request it cannot take."""
    with pytest.raises(PointError, match="plugin point with no contract"):
        _a_plugin_point(contract="")


@pytest.mark.parametrize("missing", ["direction", "carries", "tier"])
def test_a_plugin_point_states_all_of_its_terms_or_none_of_them(missing: str) -> None:
    """Half a declaration is worse than none: whichever term is unset gets decided by
    whoever wires the point up, which is the moment nobody is thinking about isolation.

    Delete this and a plugin point can arrive with no tier and acquire one by default."""
    with pytest.raises(PointError, match="missing its direction"):
        _a_plugin_point(**{missing: None})


@pytest.mark.parametrize(
    ("term", "value"),
    [
        ("direction", Direction.CONSUMES),
        ("carries", Carries.CODE),
        ("tier", IsolationTier.SIDECAR),
    ],
)
def test_a_point_nobody_may_supply_states_no_isolation_terms(term: str, value: object) -> None:
    """A tier on a point that takes no plugin reads as a promise that somebody may supply
    one, which is precisely the misreading this register exists to prevent: `storage_backend`
    is answered by a flag and a sidecar tier on it would undo the argument
    `brain.ops.storage` makes in writing.

    Delete this and the three non-plugin points can be dressed as plugin points."""
    with pytest.raises(PointError, match="not a plugin point but states"):
        _a_point(**{term: value})


def test_an_undecided_point_that_names_a_contract_is_refused() -> None:
    """Undecided means there is nothing to plug into. A point with a contract has a
    different open question, which is which answer it takes, and conflating the two hides
    the one that is nearly resolved among the five that are not.

    Delete this and the count of six stops meaning what the register says it means."""
    with pytest.raises(PointError, match="undecided and names"):
        _a_point(answer=Answer.UNDECIDED, contract="brain.ops.storage:StorageBackend")


def test_code_from_outside_the_company_never_runs_in_this_process() -> None:
    """A signature check stops a plugin being handed the trace and does nothing about a
    plugin that imports the vault client. In-process code is on the inside of every guard
    this repository has, which is why `brain.ops.automation` treats flows written by a
    client's own staff as hostile.

    Delete this and a connector plugin can be declared as running in the application."""
    with pytest.raises(PointError, match="inside every guard at once"):
        _a_plugin_point(carries=Carries.CODE, tier=IsolationTier.IN_PROCESS)


@pytest.mark.parametrize("tier", [IsolationTier.SIDECAR, IsolationTier.SANDBOX])
def test_data_runs_nowhere_but_this_process(tier: IsolationTier) -> None:
    """A container whose only job is to parse a manifest isolates nothing the parser has not
    already validated, and it is a container to operate, a network to allow and a version to
    upgrade. Both non-local tiers are refused, so the rule is about the tier rather than
    about one of them.

    Delete this and a template point can acquire a sidecar nobody needs."""
    with pytest.raises(PointError, match="the parser is the isolation"):
        _a_plugin_point(carries=Carries.DATA, tier=tier)


def test_the_two_isolation_rules_admit_the_combinations_the_register_actually_uses() -> None:
    """The positive case, without which both rules above are satisfied by refusing every
    point. Code in a sandbox, code in a sidecar and data in this process are the three
    combinations the register holds, and all three have to be constructible.

    Delete this and the isolation rules could tighten to refuse everything unnoticed."""
    assert _a_plugin_point(carries=Carries.CODE, tier=IsolationTier.SANDBOX).tier is (
        IsolationTier.SANDBOX
    )
    assert _a_plugin_point(carries=Carries.CODE, tier=IsolationTier.SIDECAR).tier is (
        IsolationTier.SIDECAR
    )
    assert _a_plugin_point(carries=Carries.DATA, tier=IsolationTier.IN_PROCESS).tier is (
        IsolationTier.IN_PROCESS
    )


def test_no_point_in_the_register_runs_third_party_code_in_this_process() -> None:
    """The rule above proves the constructor refuses it. This proves the register does not
    contain one, which is a different claim: the sixteen points are data and a rule is only
    as good as the data it was applied to.

    Delete this and the register's own conformance stops being asserted."""
    in_process = [one.name for one in POINTS if one.tier is IsolationTier.IN_PROCESS]

    assert in_process == ["template"]
    assert BY_NAME["template"].carries is Carries.DATA
