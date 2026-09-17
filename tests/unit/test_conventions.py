"""The repository conventions, and the files that carry the ones code cannot.

Two halves. The first tests the rules in `brain.ops.conventions`, which decide whether a
commit message and a branch name mean what they say. The second tests three files that
are not code and therefore have nothing else guarding them: CODEOWNERS, the pull request
template, and the hook that calls the first half.

The second half is the unusual one, and it is here because those files fail silently. A
CODEOWNERS line deleted in a merge does not break a build; it just stops requiring a
review, and the first anybody knows is a permission change that went in unread.

Task ids: M38.1.1.1, M38.1.1.2, M38.1.1.4, M38.1.1.5, M42.6.8
"""

from __future__ import annotations

from pathlib import Path

import pytest

from brain import status
from brain.ops import independence
from brain.ops.conventions import (
    A_CLAIM_NEEDS_PROOF,
    A_PROOF_NAMES_NO_ADDRESS,
    CLOSES_LINE_RE,
    IPV4_RE,
    REOPENS_LINE_RE,
    SUBJECT_ID_RE,
    already_closed,
    body_of,
    check_branch_name,
    check_commit_message,
    leaf_ids_in,
    main,
    proofs_in,
    unmarked_install_finding,
)
from brain.status import TASK_ID_RE as STATUS_TASK_ID_RE
from brain.status import claimed_ids as status_claimed_ids
from brain.status import closed_task_ids

REPO = Path(__file__).resolve().parents[2]

#: The proof a claim needs, for the tests about something other than proof.
PROVED = "Proved-in-ci: unit"


# ------------------------------------------------- the commit message (M38.1.1.2)
def test_a_message_closing_a_leaf_is_accepted() -> None:
    """The happy path. If this fails, every commit in the repository is refused and the
    rule gets turned off within the hour. It carries its proof, which a claim needs; the
    refusal without one is tested below."""
    assert check_commit_message(f"Add the thing\n\nCloses: M12.1.1\n{PROVED}") is None


def test_a_message_closing_nothing_is_accepted() -> None:
    """A revert, a formatting pass, a fix to a fix and a merge all legitimately close
    nothing. Demanding an id from them would be satisfied with an invented one, and an
    invented id is worse than no id: it marks work done that nobody did."""
    assert check_commit_message("Fix a typo in a comment") is None


def test_a_parent_id_closes_nothing() -> None:
    """The rule that most needs enforcing, because `Closes: M12` is the natural thing to
    type. A module id is a summary of its children, so closing one would mark ten tasks
    done on the strength of finishing one."""
    refusal = check_commit_message("Work\n\nCloses: M12")
    assert refusal is not None
    assert "module or group id" in refusal.reason


def test_a_group_id_closes_nothing_either() -> None:
    """`M12.1` looks specific enough to be safe and is not. Two parts is a group; three
    is a leaf. Deleting this leaves the boundary undefended in the case that actually
    looks plausible on a Friday."""
    refusal = check_commit_message("Work\n\nCloses: M12.1")
    assert refusal is not None
    assert "module or group id" in refusal.reason


def test_a_group_id_in_the_subject_is_refused_because_the_status_page_reads_it_as_closed() -> None:
    """The hole the two tests above left: they guard the trailer, and `brain.status` also
    counts every id in the subject. On 2026-09-17 a subject saying a plan was appended as
    M27.9 to M27.14 passed this hook, closed two groups on the status page, and failed the
    traceability test in CI after it was pushed.

    The positive half is in the next test. Delete this and a subject can close a group again
    with every local check green."""
    refusal = check_commit_message("Append the plan as M27.9 to M27.14")
    assert refusal is not None
    assert "M27.9 in the subject" in refusal.reason
    assert status_claimed_ids("Append the plan as M27.9 to M27.14", "") == {"M27.9", "M27.14"}


def test_a_subject_naming_a_leaf_or_only_a_module_is_accepted() -> None:
    """A leaf in the subject is a legitimate claim, and a bare module id is prose the status
    page does not read as a claim, so neither may be refused. Without this sibling the rule
    above is satisfied by refusing every subject with an id in it.

    Delete this and the subject rule can be widened into refusing `M27` mentioned in passing,
    which the status page has never counted."""
    assert check_commit_message(f"Finish M12.1.1 properly\n\n{PROVED}") is None
    assert check_commit_message("Rework the M27 console shell") is None
    assert status_claimed_ids("Rework the M27 console shell", "") == set()


def test_the_subject_rule_reads_ids_exactly_as_the_status_page_does() -> None:
    """The rule copies the status page's id pattern rather than importing it, to keep the
    hook light. A copy drifts, and a drift in either direction is silent: a narrower pattern
    lets a group claim through again, a wider one refuses what the status page ignores.

    Delete this and the two patterns can part without any test noticing."""
    assert SUBJECT_ID_RE.pattern == STATUS_TASK_ID_RE.pattern
    assert SUBJECT_ID_RE.flags == STATUS_TASK_ID_RE.flags


def test_an_id_mentioned_in_prose_closes_nothing() -> None:
    """A message explaining why M12.1.1 was deliberately *not* done must not close it.
    Only the Closes: line closes anything, and the difference matters most in exactly the
    commit that discusses a task at length."""
    message = "Deferred the registry\n\nM12.1.1 needs a decision from Rupash first."
    assert leaf_ids_in(message) == ()
    assert check_commit_message(message) is None


def test_several_ids_on_one_line_are_all_checked() -> None:
    """Deleting this lets a bad id hide behind a good one, which is the shape a real
    mistake takes: two ids typed together, one of them a parent."""
    assert leaf_ids_in("x\n\nCloses: M12.1.1, M12.1.2") == ("M12.1.1", "M12.1.2")
    refusal = check_commit_message("x\n\nCloses: M12.1.1, M12")
    assert refusal is not None


def test_an_empty_message_is_refused() -> None:
    """Git allows it with --allow-empty-message and the history is then unreadable at
    exactly the commit somebody is trying to understand."""
    refusal = check_commit_message("   \n\n  ")
    assert refusal is not None
    assert "subject line" in refusal.reason


def test_a_refusal_quotes_what_was_written() -> None:
    """A hook that prints only "invalid commit message" makes the author guess which of
    three rules they broke. Guessing wrong twice is how a rule gets disabled."""
    refusal = check_commit_message("Add the registry\n\nCloses: M12")
    assert refusal is not None
    assert "M12" in str(refusal)
    assert "Add the registry" in str(refusal)


# ------------------------------------------- noticing a re-claim (M38.1.1.2)
def test_a_leaf_an_earlier_commit_already_closed_is_reported() -> None:
    """Advisory, not a refusal, and the difference is deliberate. Re-claiming is sometimes
    right: a leaf claimed on a thin implementation and later given the test that proves it
    should say so, and the count is a set, so nothing double-counts.

    What is wrong is doing it without noticing, which produces a commit message announcing
    eight closures that moves the number by nothing. This exists because that happened
    twice in one session, both times from reading "no test names this leaf" as "this leaf
    is unclaimed". They are different questions and the second one was never asked.

    Asserted against this repository's own history, because a fixture repository would only
    prove the fixture."""
    repo = Path(__file__).resolve().parents[2]
    # M0.1.1 is closed if anything is; if this repository has no history the check below is
    # vacuous rather than wrong, which is why it asserts on a specific known id.
    closed, _ = closed_task_ids(repo)
    known = next(iter(sorted(closed)), None)
    if known is None:
        pytest.skip("no commit history to check against")
    assert already_closed(f"Something\n\nCloses: {known}", repo) == (known,)


def test_a_leaf_nobody_has_closed_is_not_reported() -> None:
    """Otherwise the note fires on every commit and stops being read, which is the ordinary
    death of a warning."""
    repo = Path(__file__).resolve().parents[2]
    assert already_closed("Something\n\nCloses: M99.9.9", repo) == ()


def test_the_note_never_fires_outside_a_repository() -> None:
    """A hook that failed because it could not answer an advisory question would block a
    commit for no reason at all."""
    assert already_closed("x\n\nCloses: M0.1.1", Path("/nonexistent")) == ()


# ---------------------------------------------------------- a claim carries its proof
@pytest.mark.parametrize(
    "message",
    [
        "Add the thing\n\nCloses: M12.1.1\n",
        "Finish M12.1.1 properly\n",
        "Finish M12.1.1 properly\n\nIt works now, trust me.\n",
        "Add the thing\n\ncloses: M12.1.1\n",
    ],
    ids=["on a Closes line", "in the subject", "in the subject with prose", "lower-case closes"],
)
def test_a_claim_with_no_proof_is_refused(message: str) -> None:
    """**The rule.** On 2026-09-17 an audit reopened 1046 of 1213 tasks the tracker counted as
    done, each claimed and none shown working on the owner's install. A claim now carries a
    `Proved-on-install:` or `Proved-in-ci:` line, and the refusal says why and names the ids.

    The lower-case line is here because the tracker reads `closes:` as a claim. Until this rule
    the hook read only `Closes:`, so an unproved claim written in lower case would have passed
    here and been silently ignored by the tracker.

    Delete this and the hook accepts a claim with nothing behind it, which is the state of
    affairs the audit took a day to undo."""
    refusal = check_commit_message(message)

    assert refusal is not None
    assert A_CLAIM_NEEDS_PROOF in refusal.reason
    assert refusal.reason.startswith("M12.1.1 claimed")
    # The explanation names the two trailers, spelled so the reader of proof accepts them, so a
    # person who follows the refusal word for word gets a commit that counts.
    for trailer in ("Proved-on-install:", "Proved-in-ci:"):
        assert A_CLAIM_NEEDS_PROOF.count(trailer) == 1, trailer
        assert proofs_in(f"{trailer} what was seen\n") == ("what was seen",)


@pytest.mark.parametrize(
    "proof",
    [
        "Proved-on-install: signed in as a staff member and the answer named the invoice",
        "Proved-in-ci: the unit job runs tests/unit/test_status.py",
        "proved-on-install: the nightly dump ran and the file was 3.2 MB",
    ],
    ids=["on an install", "in CI", "lower case"],
)
def test_a_claim_with_proof_is_accepted(proof: str) -> None:
    """The positive sibling, for both trailers and for a claim in the subject as well as on a
    `Closes:` line. Without it the rule above is satisfied by refusing every claim, and the rule
    gets switched off within the hour.

    Delete this and a proved claim can be refused with every refusal test still green."""
    assert check_commit_message(f"Add the thing\n\nCloses: M12.1.1\n{proof}\n") is None
    assert check_commit_message(f"Finish M12.1.1 properly\n\n{proof}\n") is None


@pytest.mark.parametrize(
    "trailer",
    ["Proved-on-install:", "Proved-in-ci:   ", "Proved-on-install:\t"],
    ids=["nothing after the colon", "spaces", "a tab"],
)
def test_an_empty_proof_trailer_proves_nothing(trailer: str) -> None:
    """A colon with nothing after it is the cheapest way to satisfy the letter of the rule.

    Delete this and the trailer is a word to type rather than a sentence saying what was seen,
    and the tracker, which reads proof through the same function, counts it too."""
    refusal = check_commit_message(f"Add the thing\n\nCloses: M12.1.1\n{trailer}\n")

    assert refusal is not None
    assert A_CLAIM_NEEDS_PROOF in refusal.reason
    assert proofs_in(f"{trailer}\n") == ()


def test_a_proof_typed_straight_under_the_subject_is_not_in_the_body() -> None:
    """Git's subject is the first paragraph, so a trailer with no blank line above it is part of
    the subject and git's `%b`, which is all the tracker reads for proof, is empty.

    Delete this and the hook can read proof from the first paragraph, accepting a claim the
    tracker then declines to count, which looks proved to its author and open to everybody
    else."""
    message = f"Finish M12.1.1 properly\n{PROVED}\n"

    assert body_of(message) == ""
    assert check_commit_message(message) is not None
    # The positive half: a line of nothing but spaces is a blank line to git as well.
    assert body_of(f"Finish it\n  \n{PROVED}\n") == PROVED


def test_an_id_the_same_commit_reopens_needs_no_proof() -> None:
    """Taking a claim back only lowers the count, so it needs no proof, and a subject naming the
    id it reopens is not a claim the tracker counts. The sibling half: a `Reopens:` written as
    the subject is a claim to the tracker, which reads every id in a subject, so it needs proof.

    Delete this and either correcting a false claim is refused for want of proof of something
    that is not there, or a subject can claim with no proof by calling itself a reopen."""
    subject, body = "Reopen M12.1.1, which never worked", "Reopens: M12.1.1"

    assert check_commit_message(f"{subject}\n\n{body}\n") is None
    assert status.claimed_ids(subject, body) - status.reopened_ids(body) == set()
    assert check_commit_message("Reopens: M12.1.1\n") is not None


@pytest.mark.parametrize(
    "proof",
    [
        "Proved-on-install: opened https://brain.example/health/ready and it said ready",
        "Proved-on-install: ssh to 203.0.113.7 and the worker was running",
        "Proved-in-ci: http://ci.example/run/42",
    ],
    ids=["a URL", "an IPv4", "a URL on the CI trailer"],
)
def test_a_proof_that_names_an_address_is_refused(proof: str) -> None:
    """A commit message is pushed and kept for ever, and the audit commit that prompted this
    rule named the install by its address. So a proof says what was done and seen, never where,
    and this refuses one that names a URL or an IPv4 even on a message claiming nothing.

    Delete this and the trailer written most often on the day an install is checked is the one
    most likely to carry that install's address into the history."""
    for message in (f"Add the thing\n\nCloses: M12.1.1\n{proof}\n", f"Tidy\n\n{proof}\n"):
        refusal = check_commit_message(message)
        assert refusal is not None
        assert A_PROOF_NAMES_NO_ADDRESS in refusal.reason


def test_a_proof_naming_a_version_a_path_or_a_size_is_accepted() -> None:
    """The positive sibling. A version number has dots, a path has slashes and a size has a
    decimal point, and all three are what a proof honestly says, so none may read as an address.

    Delete this and the address check can be widened into refusing an ordinary sentence, which
    is how a rule gets bypassed with `--no-verify` and then forgotten."""
    proof = "Proved-in-ci: tests/unit/test_status.py on Python 3.13.1, image 1.2.3 of 412.5 MB"

    assert check_commit_message(f"Add the thing\n\nCloses: M12.1.1\n{proof}\n") is None


def test_the_hook_refuses_an_unproved_claim_and_accepts_a_proved_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Through `main`, which is what `ops/hooks/commit-msg` runs, so the refusal is an exit code
    git acts on and not only a return value.

    Delete this and the rule can be computed and never enforced: printed as a note with exit 0,
    or never called by the entry point at all."""
    unproved = tmp_path / "UNPROVED"
    unproved.write_text("Add the thing\n\nCloses: M99.9.9\n", encoding="utf-8")
    proved = tmp_path / "PROVED"
    proved.write_text(f"Add the thing\n\nCloses: M99.9.9\n{PROVED}\n", encoding="utf-8")

    assert main([str(unproved)]) == 1
    assert "Proved-on-install:" in capsys.readouterr().err
    assert main([str(proved)]) == 0


def test_the_hook_reads_claims_reopens_and_proof_exactly_as_the_tracker_does() -> None:
    """The hook keeps copies of the tracker's patterns rather than importing `brain.status`,
    which pulls in the work breakdown loader on every commit. A copy drifts, and a drift is a
    message the hook accepts and the tracker reads differently. Proof is not copied: the tracker
    imports `proofs_in` from here, and this asserts it is the same function.

    The address pattern is copied from `brain.ops.independence` for the same reason, because
    that module loads the settings on import.

    Delete this and any of the four can part without a test noticing."""
    assert (CLOSES_LINE_RE.pattern, CLOSES_LINE_RE.flags) == (
        status.CLOSES_RE.pattern,
        status.CLOSES_RE.flags,
    )
    assert (REOPENS_LINE_RE.pattern, REOPENS_LINE_RE.flags) == (
        status.REOPENS_RE.pattern,
        status.REOPENS_RE.flags,
    )
    # Through the module's namespace, because `brain.status` imports the function to use it
    # rather than to export it, and the type checker says so about an attribute read.
    assert vars(status)["proofs_in"] is proofs_in
    assert (IPV4_RE.pattern, IPV4_RE.flags) == (independence.IPV4.pattern, independence.IPV4.flags)


# -------------------------------------------------- the branch name (M38.1.1.1)
@pytest.mark.parametrize("name", ["M12/tool-registry", "M38.1/staging", "M3/gate"])
def test_a_branch_named_for_its_module_is_accepted(name: str) -> None:
    assert check_branch_name(name) is None


@pytest.mark.parametrize("name", ["fix", "feature/registry", "M12", "M12/Tool_Registry"])
def test_a_branch_not_named_for_its_module_is_refused(name: str) -> None:
    """Twelve tracks run at once, and they collide in one way: two branches that sound
    alike get reviewed as though they were the same work. The module id makes that
    impossible to do by accident."""
    assert check_branch_name(name) is not None


def test_main_is_exempt() -> None:
    """The trunk is not a track. Refusing it would make the rule something people work
    around rather than follow."""
    assert check_branch_name("main") is None


def test_the_command_line_refuses_a_misnamed_branch_and_passes_a_named_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--branch` is the rule's only caller, from CI's `branch_name` job. Delete this and the
    flag can stop refusing, or refuse everything, with the rule's own tests green."""
    assert main(["--branch", "feature/registry"]) == 1
    assert "refused:" in capsys.readouterr().err
    assert main(["--branch", "M12/tool-registry"]) == 0
    assert main(["--branch"]) == 1


def test_ci_calls_the_branch_rule_with_the_pull_requests_own_branch() -> None:
    """A rule with a test and no caller is how this one sat until 2026-09-17. Delete this and
    the job can be removed or pointed at the base branch, which is always `main` and exempt."""
    import yaml

    workflow = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
    )
    steps = workflow["jobs"]["branch_name"]["steps"]
    step = next(one for one in steps if "brain.ops.conventions" in str(one.get("run", "")))
    assert step["run"].split() == [
        "uv",
        "run",
        "python",
        "-m",
        "brain.ops.conventions",
        "--branch",
        '"$HEAD_REF"',
    ]
    assert step["env"]["HEAD_REF"] == "${{ github.head_ref }}"


# ------------------------------------- the files that carry the rest (M38.1.1.4, M38.1.1.5)
#: Every file that can widen what an answer contains. Each needs a second reader, and the
#: reason is the same for all of them: a mistake here returns a plausible answer that is
#: simply too wide, so nothing looks broken.
MUST_HAVE_AN_OWNER = (
    "/src/brain/core/entitlement.py",
    "/src/brain/core/scope.py",
    "/src/brain/core/scope_sql.py",
    "/src/brain/core/redaction.py",
    "/src/brain/core/field_policy.py",
    "/src/brain/core/projection.py",
    "/src/brain/gate/",
    "/tests/invariants/",
)


@pytest.mark.parametrize("path", MUST_HAVE_AN_OWNER)
def test_every_file_that_can_widen_an_answer_has_an_owner(path: str) -> None:
    """CODEOWNERS fails silently, which is why it is tested rather than trusted. A line
    dropped in a merge breaks no build; it stops requiring a review, and the first anybody
    knows is a permission change that went in unread.

    `scope_sql.py` is on this list because it has already gone wrong: an unescaped LIKE
    and a string splitting into an IN list both made the SQL admit rows the Python
    evaluator refused. The redactor is on it because reclassifying one field from
    confidential to internal changes every answer touching that field and breaks no test
    about redaction.
    """
    owners = (REPO / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    lines = [
        line for line in owners.splitlines() if line.strip() and not line.strip().startswith("#")
    ]
    covered = {line.split()[0] for line in lines}
    assert path in covered, f"{path} can widen an answer and nobody is required to read it"
    assert any(line.split()[0] == path and "@" in line for line in lines)


def test_the_pull_request_template_asks_for_leaf_ids_only() -> None:
    """The status page is generated from what the template collects. A template that
    accepted a parent id would produce a page claiming ten tasks done for one."""
    template = (REPO / ".github" / "pull_request_template.md").read_text(encoding="utf-8")
    assert "Closes: M" in template
    assert "Leaf ids only" in template
    assert "a parent id closes nothing" in template


def test_the_commit_hook_calls_the_tested_rule_rather_than_repeating_it() -> None:
    """A hook is the worst place to put logic: it does not run in CI, it does not run for
    anybody who has not set core.hooksPath, and nothing tests it. This asserts the shim
    stays a shim, so the rule keeps living where the tests can reach it."""
    hook = (REPO / "ops" / "hooks" / "commit-msg").read_text(encoding="utf-8")
    assert "brain.ops.conventions" in hook
    # No second copy of the rule. A hook that grepped for `Closes:` itself would drift
    # from the module the moment either changed, and the hook is the copy nobody tests.
    assert "Closes:" not in hook.replace("`Closes:` line", "")


# ------------------------------------------ a finding from an install (M42.6.8)
def test_a_finding_from_an_install_that_says_why_its_fix_is_generic_is_accepted() -> None:
    """The sibling of the refusal below. If this fails, every commit that honestly answers a
    staging finding is refused, and the trailers stop being written at all."""
    message = (
        "Mint the subject from the realm's own scope\n\n"
        "Found-on: staging\n"
        "Generic-because: every full import discards the built-in scope, not only this one\n"
    )
    assert check_commit_message(message) is None


@pytest.mark.parametrize(
    "reason_line",
    ["", "Generic-because:\n", "Generic-because:   \n"],
    ids=["no reason line", "empty reason", "blank reason"],
)
def test_a_finding_from_an_install_that_does_not_say_why_its_fix_is_generic_is_refused(
    reason_line: str,
) -> None:
    """The rule. Delete this and `Found-on:` becomes a label, the question of whether a company
    nobody here has met would hit the same fault goes unasked, and one install's repair ships
    to every company looking like a product fix. A blank reason is refused as firmly as a
    missing one, because a colon with nothing after it is the cheapest way to satisfy the
    letter of the rule."""
    message = f"Fix the sign-in\n\nFound-on: staging\n{reason_line}"
    refusal = check_commit_message(message)
    assert refusal is not None
    assert "Generic-because" in refusal.reason
    assert refusal.subject == "Fix the sign-in"


def test_a_message_that_talks_about_an_install_without_the_trailer_gets_a_note() -> None:
    """The advisory half. Delete this and the note can go quiet for every message, and a
    commit answering a staging finding with no trailer is indistinguishable from a product
    change nobody saw on an install."""
    assert unmarked_install_finding("Fix the loop the owner hit on his staging install")
    assert unmarked_install_finding("Redirect loop seen on his server after first run")
    assert unmarked_install_finding("Seen on the owner's own install")


def test_an_ordinary_message_or_one_carrying_the_trailer_gets_no_note() -> None:
    """The positive sibling. A note that fires on every commit is a note nobody reads, so it
    must stay silent on an ordinary product change and on a message that already answered
    the question it asks."""
    assert not unmarked_install_finding("Add the skills screen\n\nCloses: M42.6.4")
    assert not unmarked_install_finding(
        "Fix the loop seen on staging\n\nFound-on: staging\nGeneric-because: every install\n"
    )


def test_the_note_is_printed_and_does_not_refuse(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The hook's own behaviour, through `main`. Delete this and the note can be computed and
    never shown, or shown with a non-zero exit, and the second is a refusal on a guess."""
    message_file = tmp_path / "COMMIT_EDITMSG"
    message_file.write_text("Fix the loop on the staging install\n", encoding="utf-8")

    assert main([str(message_file)]) == 0
    assert "Found-on:" in capsys.readouterr().err


def test_the_repository_instructions_carry_the_rule_and_its_worked_examples() -> None:
    """The rule is only half code. The other half is the table of findings in `CLAUDE.md`
    that says, for each, what belonged to the install and what belonged to the product.
    Delete this and the section can be trimmed to a sentence, which is the version an agent
    reads before fixing only the half in front of it."""
    text = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
    heading = "## A problem found on an install: is the fix the product's or that install's?"
    assert text.count(heading) == 1
    section = text.split(heading, 1)[1].split("\n## ", 1)[0]
    rows = [
        line
        for line in section.splitlines()
        if line.startswith("| ") and "install's half" not in line
    ]
    assert len(rows) >= 5, rows
    assert all(line.count(" | ") == 2 for line in rows), rows
    assert "\nFound-on: " in section
    assert "\nGeneric-because: " in section
