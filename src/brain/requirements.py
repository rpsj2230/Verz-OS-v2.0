"""The owner's requirements, held against the work breakdown so a missing task turns the build red.

The owner asked for capabilities that never became tasks. His first brief lived in a
conversation and was never saved, the architecture was reconstructed from what was left, and
nothing compared the two. When he asked what stops it happening again, the only answer worth
giving was a check that fails, so this is that check: `docs/requirements/register.json` names
every requirement, the leaves that build it and the leaves that prove it, and
`tests/unit/test_requirements_register.py` goes red on the day a row is left uncovered.

**The register is its own file and not a field on the work breakdown, because a requirement
with no task has nowhere to live in a list of tasks.** Tagging each leaf with the requirement it
serves was the cheaper design and it is blind to exactly the failure this exists for: a
requirement nobody wrote a leaf for carries no tag, so it is absent from every view of the plan,
and absence is what went unnoticed the first time. A row in a register exists before its tasks
do, and an empty `leaves` is a finding rather than a silence.

**Nor is it a Markdown list.** A list of requirements in prose is a promise about coverage, and
the check that follows it is somebody reading carefully. Every rule below is a property of the
data that a test can assert, which is the difference between a register and a document.

**A requirement is delivered when its proof is closed, not when its parts are.** The tracker
already showed tasks as done that the owner's own install did not show done, and those were
reopened (c082c13). A requirement whose building leaves are all ticked has shown that its
parts were committed; only a leaf that proves the whole on an install or in the browser shows
that it works. So a row with no proof leaf is a finding, and nothing without one is ever
counted as delivered, however many of its leaves are closed.

**A leaf decided against is a narrowing, and a narrowing is a question to the owner.** A row
resting on a leaf flagged DECIDED in `docs/wbs.json` has to name the `docs/needs-rupash.md`
item that decided it, and the item has to exist. The alternative was to treat a decided leaf as
satisfied and let the row count as delivered without it, and that is the silent narrowing again
with a green tick on it: the architecture deciding against the owner in a docstring, which is
the other half of how the capabilities went missing. So a row resting on a decided leaf is
covered once it names its decision, and is delivered only if that leaf is closed anyway: the
decision explains the narrowing, it does not stand in for the work.

**An id that names no leaf covers nothing, and that includes a group.** `brain.status` closes a
leaf only when its own id is named and never through an ancestor, so a row naming `M17.4`
would look covered and could never be delivered, and a row naming a mistyped id would look
covered for ever. Both are the same finding.

**Delivered needs a clean row as well as closed leaves.** An id `closed_task_ids` reports is
whatever a commit subject named, including a group or an id that was never a leaf; testing
only "every named id is closed" would count a row whose one proof is a group somebody named in
a subject line.

**The page reads `done_task_ids` from the baked `status.json`, not git.** The image carries no
history, for the reason `brain.docs_routes._read_status` gives, and `done_task_ids` is
`closed_task_ids` restricted to the leaves of the breakdown, which is every id a clean row can
name. The test and `main` read git directly through `closed_task_ids`, and neither this module
nor its tests change what counts as closed.

Task ids: none
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, ConfigDict

from brain.status import closed_task_ids, decided_of, load_wbs

#: Where the register lives, relative to the repository and to the `docs` directory.
REGISTER_IN_DOCS: Final = Path("requirements") / "register.json"

#: The file whose items a decision names.
NEEDS_FILE: Final = "needs-rupash.md"

A_REQUIREMENT_WITH_NO_TASK_IS_A_REQUIREMENT_NOBODY_WILL_BUILD: Final = (
    "names no task, so nothing in the plan builds it and no view of the plan will ever show it "
    "missing"
)

A_REQUIREMENT_WITH_NO_PROOF_TASK_CAN_ONLY_EVER_BE_TICKED: Final = (
    "names no proof task, so nothing shows it working on an install and it could only ever be "
    "counted done because its parts were ticked"
)

AN_ID_THAT_NAMES_NO_LEAF_COVERS_NOTHING: Final = (
    "names an id that is not a leaf of the work breakdown: a group closes none of its children "
    "and a mistyped id closes nothing, so the row looks covered and is not"
)

A_DECIDED_LEAF_IS_A_NARROWING_AND_A_NARROWING_IS_ASKED: Final = (
    "rests on a leaf decided against as written and names no decision, so the requirement was "
    "narrowed without the register saying who decided it"
)

A_DECISION_NAMES_THE_QUESTION_THAT_DECIDED_IT: Final = (
    "names a decision that is no item of docs/needs-rupash.md, so nobody can find the question "
    "that narrowed it or the answer given"
)

ONE_ID_IS_ONE_REQUIREMENT: Final = (
    "shares its id with another row, so a finding or a delivery against that id is about two "
    "requirements at once"
)

A_REQUIREMENT_IS_DELIVERED_WHEN_IT_IS_PROVED_ON_AN_INSTALL_NOT_WHEN_ITS_PARTS_ARE_TICKED: Final = (
    "A requirement is delivered when its row has no finding and every leaf and every proof leaf it "
    "names is closed. A row with no proof leaf is a finding, so it is never delivered, however "
    "many of its building leaves are closed."
)

#: How a decision names its item: `needs-rupash 58`, anywhere in the string.
NAMED_ITEM: Final = re.compile(r"\bneeds-rupash (\d+)\b")

#: An item heading in `docs/needs-rupash.md`: `## 58. Nine plug-in points ...`.
ITEM_HEADING: Final = re.compile(r"^## (\d+)\.", re.MULTILINE)


class Requirement(BaseModel):
    """One row of the register. Every field is required, `decision` included, even when null.

    **`extra="forbid"`, because the key a row should not carry is the one most likely to
    arrive.** The tracing that fills this register writes a `conflict` beside each row, naming
    where the architecture decided against the owner. Pasted in and quietly ignored, that is a
    narrowing recorded in the one field no rule reads, which is the failure `decision` exists to
    end. Refused, it has to become a `decision` naming a question, or be dropped on purpose.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    source: str
    area: str
    requirement: str
    leaves: tuple[str, ...]
    proof: tuple[str, ...]
    decision: str | None


class Register(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    requirements: tuple[Requirement, ...]


@dataclass(frozen=True)
class Finding:
    """One rule a row breaks, with the ids that break it where there are some."""

    requirement: str
    rule: str
    ids: tuple[str, ...] = ()

    def __str__(self) -> str:
        named = f" ({', '.join(self.ids)})" if self.ids else ""
        return f"{self.requirement} {self.rule}{named}"


@dataclass(frozen=True)
class Standing:
    """Where one requirement stands: what is wrong with its row, and whether it is delivered."""

    requirement: Requirement
    findings: tuple[Finding, ...]
    delivered: bool

    @property
    def covered(self) -> bool:
        return not self.findings


@dataclass(frozen=True)
class Assessment:
    standings: tuple[Standing, ...]

    @property
    def findings(self) -> tuple[Finding, ...]:
        return tuple(f for s in self.standings for f in s.findings)

    @property
    def total(self) -> int:
        return len(self.standings)

    @property
    def covered(self) -> int:
        return sum(1 for s in self.standings if s.covered)

    @property
    def delivered(self) -> int:
        return sum(1 for s in self.standings if s.delivered)

    def summary(self) -> dict[str, int]:
        return {"total": self.total, "covered": self.covered, "delivered": self.delivered}


def load_register(path: Path) -> Register:
    return Register.model_validate_json(path.read_text(encoding="utf-8"))


def needs_items(path: Path) -> frozenset[int]:
    """The item numbers `docs/needs-rupash.md` holds, open and answered alike.

    Open as well as answered, because a narrowing is recorded the moment it is asked: the row
    names the open question, and the answer arrives under the same number. Absent is empty, so
    every decision is then a finding rather than every decision passing.
    """
    if not path.exists():
        return frozenset()
    return frozenset(int(n) for n in ITEM_HEADING.findall(path.read_text(encoding="utf-8")))


def _leaves_and_decided(wbs: dict[str, Any]) -> tuple[frozenset[str], frozenset[str]]:
    leaves: set[str] = set()
    decided: set[str] = set()
    for module in wbs.get("modules", []):
        leaves.update(module.get("leaf_ids", []))
        decided.update(decided_of(module))
    return frozenset(leaves), frozenset(decided)


def assess(
    register: Register, wbs: dict[str, Any], closed: Iterable[str], items: Iterable[int]
) -> Assessment:
    """Every row against the breakdown, the decisions and the ids closed so far."""
    leaves, decided = _leaves_and_decided(wbs)
    closed_ids = frozenset(closed)
    item_numbers = frozenset(items)
    uses = Counter(row.id for row in register.requirements)
    standings: list[Standing] = []
    for row in register.requirements:
        found: list[Finding] = []
        named = (*row.leaves, *row.proof)
        if uses[row.id] > 1:
            found.append(Finding(row.id, ONE_ID_IS_ONE_REQUIREMENT))
        if not row.leaves:
            found.append(
                Finding(row.id, A_REQUIREMENT_WITH_NO_TASK_IS_A_REQUIREMENT_NOBODY_WILL_BUILD)
            )
        if not row.proof:
            found.append(Finding(row.id, A_REQUIREMENT_WITH_NO_PROOF_TASK_CAN_ONLY_EVER_BE_TICKED))
        unknown = tuple(i for i in named if i not in leaves)
        if unknown:
            found.append(Finding(row.id, AN_ID_THAT_NAMES_NO_LEAF_COVERS_NOTHING, unknown))
        narrowed = tuple(i for i in named if i in decided)
        if narrowed and row.decision is None:
            found.append(
                Finding(row.id, A_DECIDED_LEAF_IS_A_NARROWING_AND_A_NARROWING_IS_ASKED, narrowed)
            )
        if row.decision is not None:
            cited = [int(n) for n in NAMED_ITEM.findall(row.decision)]
            if not cited or any(n not in item_numbers for n in cited):
                found.append(Finding(row.id, A_DECISION_NAMES_THE_QUESTION_THAT_DECIDED_IT))
        # A clean row as well as closed ids, so a missing proof or a group named in a commit
        # subject can never count. The rule is the constant about being proved on an install.
        delivered = not found and all(i in closed_ids for i in named)
        standings.append(Standing(row, tuple(found), delivered))
    return Assessment(tuple(standings))


def assess_repository(repo: Path, ref: str = "HEAD") -> Assessment:
    """The register as this repository holds it, against the commits reachable from `ref`."""
    docs = repo / "docs"
    closed, _ = closed_task_ids(repo, ref)
    return assess(
        load_register(docs / REGISTER_IN_DOCS),
        load_wbs(docs / "wbs.json"),
        closed,
        needs_items(docs / NEEDS_FILE),
    )


def summary_of_docs(docs: Path, done: Iterable[str]) -> dict[str, int] | None:
    """Total, covered and delivered for the build pages, or None when no register is published.

    None rather than zeros: a page reading "0 requirements" says nothing was asked for, and a
    register that is missing from the image is a different fact that should read differently.
    """
    register = docs / REGISTER_IN_DOCS
    if not register.exists():
        return None
    wbs_path = docs / "wbs.json"
    wbs = load_wbs(wbs_path) if wbs_path.exists() else {"modules": []}
    return assess(load_register(register), wbs, done, needs_items(docs / NEEDS_FILE)).summary()


def main(repo: Path | None = None) -> int:
    """Print every finding and the three figures. Non-zero while any row has a finding.

    For whoever fills the register: `uv run python -m brain.requirements` is the same
    judgement the unit test makes, with every row's findings rather than the first failure.
    """
    repo = Path(__file__).resolve().parents[2] if repo is None else repo
    if not (repo / "docs" / REGISTER_IN_DOCS).exists():
        print(f"no register at {repo / 'docs' / REGISTER_IN_DOCS}")
        return 1
    assessment = assess_repository(repo)
    for finding in assessment.findings:
        print(finding)
    print(
        f"{assessment.total} requirements, {assessment.covered} covered by a task and a proof, "
        f"{assessment.delivered} delivered"
    )
    return 1 if assessment.findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
