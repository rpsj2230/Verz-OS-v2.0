"""What a person declared about a system, and what a page is allowed to be.

Two modules, together because they are the two halves of the same rule: the target registry
is the description a planner may read, and the snapshot is the description it may not.

Task ids: M19.2.4, M19.4.5
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from brain.browsing.observation import (
    IMAGE_SHAPED,
    Node,
    ObservationError,
    Snapshot,
    is_current,
    vision_gaps,
)
from brain.browsing.targets import (
    READ_VERBS,
    Surface,
    Target,
    TargetError,
    TargetRegistry,
    Verb,
    is_write,
)
from brain.core.entitlement import Capability

READ_CAPABILITY = Capability(value="read:browser_surface")
ORIGIN = "https://books.example"


def surface(name: str = "invoices", **changes: object) -> Surface:
    fields: dict[str, object] = {
        "name": name,
        "origin": "https://books.example",
        "path": "/invoices",
        "verbs": frozenset({Verb.OPEN, Verb.READ}),
        "capability": READ_CAPABILITY,
        "reads": ("number", "total"),
    }
    fields.update(changes)
    return Surface(**fields)  # type: ignore[arg-type]


def target(**changes: object) -> Target:
    fields: dict[str, object] = {
        "name": "books",
        "origins": frozenset({"https://books.example"}),
        "surfaces": (surface(),),
        "api_tools": (),
    }
    fields.update(changes)
    return Target(**fields)  # type: ignore[arg-type]


# --------------------------------------------------------------------- the surface map


def test_a_declared_surface_is_what_a_plan_may_use() -> None:
    """The positive case, and it is the one that makes every refusal below meaningful.

    Delete this and every remaining test in this file is a refusal, which is satisfied by a
    registry that refuses everything.
    """
    declared = target()

    assert declared.surface("invoices") is not None
    assert declared.allows_origin("https://books.example")
    assert declared.surface("invoices").admits(Verb.READ)  # type: ignore[union-attr]


def test_a_surface_on_an_origin_the_target_does_not_allow_is_refused() -> None:
    """A surface that widened the allowlist by existing would let a declaration authorise
    itself, and the origin check per action is decided against that allowlist.

    Delete this and adding a surface is a way to add an origin, which makes the allowlist a
    summary of the surfaces rather than a constraint on them.
    """
    with pytest.raises(TargetError, match="does not allow"):
        target(surfaces=(surface(origin="https://elsewhere.example"),))


def test_an_origin_that_is_not_normalised_is_refused_when_it_is_declared() -> None:
    """Comparing a normalised action origin against a raw declaration refuses every action
    and looks like a browser fault rather than a typing one.

    Delete this and a trailing slash in configuration produces a target nothing can reach,
    with nothing anywhere saying why.
    """
    with pytest.raises(TargetError, match="normalised"):
        target(origins=frozenset({"https://books.example/"}))


def test_an_origin_is_matched_exactly_and_never_by_suffix() -> None:
    """A suffix test admits `books.example.evil.test` for an entry naming `books.example`.

    Delete this and the allowlist can be loosened to a suffix comparison, which reads as the
    more forgiving option and forgives precisely the host it must not.
    """
    declared = target()

    assert declared.allows_origin("https://books.example")
    assert not declared.allows_origin("https://books.example.evil.test")
    assert not declared.allows_origin("https://evil.test")


def test_a_read_surface_that_declares_no_fields_is_refused() -> None:
    """What a read returns has to be declared, or it is decided by whatever the page contained.

    Delete this and a surface can admit READ with nothing said about what comes back, which
    makes the rubric criterion for that surface unwritable.
    """
    with pytest.raises(TargetError, match="declares no fields"):
        surface(verbs=frozenset({Verb.OPEN, Verb.READ}), reads=())


def test_a_surface_with_no_verbs_is_refused() -> None:
    """A surface admitting nothing exists only to look like a capability.

    Delete this and the registry can carry entries that refuse every step, which reads to an
    author as a permission problem rather than as an empty declaration.
    """
    with pytest.raises(TargetError, match="declares no verbs"):
        surface(verbs=frozenset())


def test_two_targets_with_one_name_are_refused() -> None:
    """Which target a plan resolves to would otherwise be decided by list order.

    Delete this and the same failure `brain.tools.registry` refuses for tools arrives for
    targets, where the loser is invisible rather than broken.
    """
    with pytest.raises(TargetError, match="share a name"):
        TargetRegistry(targets=(target(), target()))


def test_a_registry_answers_for_a_target_it_holds_and_not_for_one_it_does_not() -> None:
    """Both halves, because a `get` that always returned None would pass a refusal test.

    Delete this and the registry can stop resolving anything, and the planner's refusal to
    plan against an undeclared target would fire for every target.
    """
    registry = TargetRegistry(targets=(target(),))

    assert registry.get("books") is not None
    assert registry.get("ledger") is None
    assert registry.names() == ("books",)
    assert registry.origins() == frozenset({"https://books.example"})


# --------------------------------------------------------------------- verbs


def test_a_click_is_counted_as_a_write() -> None:
    """The page decides what a click does, and the page is the untrusted party.

    Delete this and `CLICK` can be moved into `READ_VERBS` on the reasonable-sounding grounds
    that clicking a link is navigation, and every click then runs outside the write budget.
    """
    assert is_write(Verb.CLICK)
    assert is_write(Verb.TYPE)
    assert is_write(Verb.SUBMIT)
    assert is_write(Verb.UPLOAD)


def test_only_the_two_verbs_that_do_not_dispatch_an_event_are_reads() -> None:
    """Asserted against the whole enumeration rather than against `READ_VERBS` itself.

    A test comparing `READ_VERBS` with `READ_VERBS` is green for every value it could hold,
    which is the constant trap CLAUDE.md records from `hubspot.CEILING_NAME`. This states the
    property instead: exactly two verbs are reads, and they are the two named.

    Delete this and the read set can be widened one verb at a time.
    """
    reads = {verb for verb in Verb if not is_write(verb)}

    assert reads == {Verb.OPEN, Verb.READ}
    assert len(READ_VERBS) == 2
    assert len(list(Verb)) == 6


# --------------------------------------------------------------------- observation


def test_a_snapshot_holds_nodes_and_can_be_asked_about_a_reference() -> None:
    """The positive case for reference validation, which every refusal below rests on.

    Delete this and a `Snapshot` that reported every reference as absent would satisfy the
    enforcer's refusal tests while making every legitimate action impossible.
    """
    seen = Snapshot(
        run_id="run-1",
        sequence=1,
        origin="https://books.example",
        nodes=(Node(ref="n1", role="button", name="Export"),),
    )

    assert seen.has("n1")
    assert not seen.has("n2")
    assert seen.node("n1") is not None
    assert seen.node("n2") is None
    assert seen.refs() == frozenset({"n1"})


def test_two_nodes_sharing_a_reference_are_refused() -> None:
    """Validating a reference against such a tree would authorise acting on either node.

    Delete this and a runner bug that mints one reference twice turns into an action on
    whichever element the page resolves it to.
    """
    with pytest.raises(ObservationError, match="share a reference"):
        Snapshot(
            run_id="run-1",
            sequence=1,
            origin="https://books.example",
            nodes=(
                Node(ref="n1", role="button", name="Export"),
                Node(ref="n1", role="link", name="Delete"),
            ),
        )


def test_a_snapshot_sequence_starts_at_one_so_a_default_cannot_pass_for_the_first() -> None:
    """Zero is what an unset integer field holds, and the enforcer compares sequences.

    Delete this and an action carrying no sequence at all matches a snapshot carrying no
    sequence at all, and the staleness check passes on two defaults.
    """
    with pytest.raises(ObservationError, match="not a position in a run"):
        Snapshot(run_id="run-1", sequence=0, origin="https://books.example")


def test_currency_requires_the_run_as_well_as_the_number() -> None:
    """Two runs against one target mint colliding references, because they are minted per tree.

    Delete this and a snapshot from another run with the right sequence number satisfies the
    reference check, which is the one place references from two runs could meet.
    """
    seen = Snapshot(run_id="run-1", sequence=2, origin="https://books.example")

    assert is_current(seen, run_id="run-1", sequence=2)
    assert not is_current(seen, run_id="run-2", sequence=2)
    assert not is_current(seen, run_id="run-1", sequence=3)


def test_nothing_in_an_observation_could_carry_a_picture() -> None:
    """M19.4.5. Vision is disabled by there being no field for an image to arrive in.

    Delete this and a `screenshot` field can be added to `Snapshot` with a plausible default,
    and a run that has just typed a password has the password on the screen.
    """
    assert vision_gaps() == ()


def test_a_type_carrying_an_image_field_is_reported() -> None:
    """The positive case for the check: it must be looking rather than empty.

    Planted rather than asserted against the real types, because the check has to be shown to
    fire. An absence asserted against a scan that never scanned is true for every state the
    source could be in.

    Delete this and `vision_gaps` could return an empty tuple unconditionally and every other
    test in this file would still pass.
    """

    @dataclass(frozen=True)
    class WithAPicture:
        ref: str
        screenshot_png: bytes

    findings = vision_gaps((WithAPicture,))

    assert len(findings) == 1
    assert "WithAPicture.screenshot_png would carry a picture" in findings[0]


def test_every_image_shaped_name_is_actually_looked_for() -> None:
    """The list is only worth what the check does with it, and the list is written out here.

    **Written out rather than iterated from the constant, and a mutation is why.** The first
    version looped over `IMAGE_SHAPED` itself and planted one field per entry, which passes for
    every list the module could hold: shrinking the constant to one word shrinks the loop to
    one iteration and the assertion still holds. Restating the names here puts the assertion
    outside the thing being asserted, which is the shape CLAUDE.md records for
    `hubspot.CEILING_NAME`.

    Delete this and the list can be reduced to `screenshot` alone, and a `video` or a `dom`
    field arrives on a snapshot with nothing objecting.
    """
    expected = (
        "screenshot",
        "image",
        "png",
        "jpeg",
        "jpg",
        "pixel",
        "bitmap",
        "video",
        "frame",
        "data_url",
        "html",
        "dom",
    )

    assert set(IMAGE_SHAPED) == set(expected)

    for shape_word in expected:
        planted = type(
            "Planted",
            (),
            {"__annotations__": {f"a_{shape_word}_field": str}},
        )
        found = vision_gaps((dataclass(frozen=True)(planted),))

        assert found, f"{shape_word} is named as image shaped and nothing looks for it"


def test_an_origin_ending_in_an_allowed_one_is_not_allowed() -> None:
    """The attack a suffix comparison actually admits, which is not the one it looks like.

    `books.example.evil.test` is the obvious try and a suffix test refuses it, because it ends
    in `evil.test`. `evilbooks.example` is the one that gets through: it ends with the allowed
    origin's host exactly, so `endswith` says yes.

    Found by mutation. Replacing the equality with a suffix test passed every origin assertion
    in this file until this case existed.

    Delete this and the comparison can be loosened to `endswith`, which reads as forgiving and
    hands the run to a host somebody registered this morning.
    """
    declared = target()

    assert declared.allows_origin(ORIGIN)
    assert not declared.allows_origin("https://evilbooks.example")
    assert not declared.allows_origin("https://books.example.evil.test")


def test_a_surface_name_that_is_not_a_slug_is_refused() -> None:
    """A surface name is a policy key, a trace field and a log line, so it has to be safe in
    all three without anybody quoting it.

    The empty and whitespace cases are both here deliberately. CLAUDE.md records that a
    dataclass validator whose tests only ever build valid objects is the survivor found in
    nine modules running, and that covering `" "` as well as `""` is what closes it.

    Delete this and a surface can be named anything, including a string with a newline in it,
    which arrives in a log as two lines.
    """
    for bad in ("Invoices", "", "   ", "invoices/../etc", "1invoices"):
        with pytest.raises(TargetError, match="not a lowercase slug"):
            surface(name=bad)


def test_a_surface_origin_that_is_not_normalised_is_refused() -> None:
    """The same rule as the target's, stated on the surface, because both are separately
    constructible and the action check compares against whichever one was declared.

    Delete this and a surface declared with a trailing slash never matches an action origin,
    and the run fails with a refusal that looks like the browser being on the wrong page.
    """
    with pytest.raises(TargetError, match="not the normalised form"):
        surface(origin="https://books.example/")

    with pytest.raises(TargetError, match="not the normalised form"):
        surface(origin="HTTPS://Books.example")


def test_a_surface_path_that_is_not_rooted_is_refused() -> None:
    """A path a run navigates to has to be a path, and a relative one resolves against
    wherever the run happens to be.

    Delete this and a surface declared as `invoices` is read by whoever is debugging as a
    path, and by a browser as a sibling of whatever page it is on.
    """
    for bad in ("invoices", "", "   "):
        with pytest.raises(TargetError, match="not rooted at /"):
            surface(path=bad)


def test_a_target_name_that_is_not_a_slug_is_refused() -> None:
    """The target name is what a plan request resolves against and what a scope predicate
    narrows to, so the same argument as the surface's applies one level up.

    Delete this and a target can be named with a space in it, which then goes into the scope
    clause that narrows a shared credential.
    """
    for bad in ("Books", "", "   ", "books ledger"):
        with pytest.raises(TargetError, match="not a lowercase slug"):
            target(name=bad)


def test_a_target_that_allows_no_origin_is_refused() -> None:
    """An empty allowlist is either a refusal of everything or a set somebody later reads as
    no restriction, and which of the two it is cannot be told from the value.

    Delete this and the first person to write `if target.origins:` turns the empty set into
    the permissive reading, and that is the change nobody reviews as a security one.
    """
    with pytest.raises(TargetError, match="allows no origin"):
        target(origins=frozenset(), surfaces=())


def test_a_target_declaring_two_surfaces_with_one_name_is_refused() -> None:
    """Which surface a step resolves to would otherwise be decided by declaration order, and
    the loser is invisible rather than broken.

    Delete this and a copied surface row silently overrides the one above it, so a step
    planned against a read surface can run against a write one with the same name.
    """
    with pytest.raises(TargetError, match="two surfaces with one name"):
        target(surfaces=(surface(), surface(path="/invoices-again")))


def test_a_node_with_no_reference_or_no_role_is_refused() -> None:
    """A node with no reference cannot be acted on or validated against, and one with no role
    cannot be told from a paragraph, which is what the write checks are decided on.

    Whitespace as well as empty, because `" "` is what a runner produces from an element whose
    attribute was present and blank, and it is the survivor CLAUDE.md records finding in nine
    modules of validator.

    Delete this and a snapshot can carry nodes the enforcer will happily validate a reference
    against, none of which name anything.
    """
    for bad in ("", "   "):
        with pytest.raises(ObservationError, match="no reference"):
            Node(ref=bad, role="button", name="Export")

    for bad in ("", "   "):
        with pytest.raises(ObservationError, match="has no role"):
            Node(ref="n1", role=bad, name="Export")


def test_a_snapshot_with_no_run_or_no_origin_is_refused() -> None:
    """Both fields are compared rather than read: the run against the policy's, the origin
    against the action's.

    An empty run id would make `is_current` compare two empty strings and answer True, and an
    empty origin would make the per-action origin check compare against nothing.

    Delete this and the two comparisons the enforcer makes first can both be satisfied by a
    snapshot that names neither.
    """
    for bad in ("", "   "):
        with pytest.raises(ObservationError, match="belonging to no run"):
            Snapshot(run_id=bad, sequence=1, origin=ORIGIN)

    for bad in ("", "   "):
        with pytest.raises(ObservationError, match="names no origin"):
            Snapshot(run_id="run-1", sequence=1, origin=bad)


def test_a_surface_with_no_origin_is_refused() -> None:
    """Found by mutation on the sibling check in `brain.browsing.credentials`.

    The empty string is what `normalise_origin` returns for anything it cannot parse, so an
    empty declared origin passes "is this normalised" by comparing "" with "", and the
    allowlist built from it then admits every action whose origin failed to parse.

    Delete this and a surface declared with no origin reaches every unparseable one.
    """
    with pytest.raises(TargetError, match="declares no origin"):
        surface(origin="")


def test_a_target_allowing_the_empty_origin_is_refused() -> None:
    """The same hole one level up, where the allowlist actually lives.

    Delete this and an empty entry in `origins` makes `allows_origin` true for `null`, for a
    `file://` document and for every malformed authority.
    """
    with pytest.raises(TargetError, match="allows the empty origin"):
        Target(name="books", origins=frozenset({""}), surfaces=())


def test_an_origin_that_did_not_parse_is_never_allowed() -> None:
    """Stated on the method as well, because a `Policy` and a `Target` are separately
    reachable and this is the comparison both of them make.

    Delete this and `allows_origin` can go back to a bare membership test, which is right for
    every origin that parses and wrong for every one that does not.
    """
    declared = target()

    assert declared.allows_origin(ORIGIN)
    assert not declared.allows_origin("null")
    assert not declared.allows_origin("not-a-url")
    assert not declared.allows_origin("")
