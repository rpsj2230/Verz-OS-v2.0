"""What one feature switch is, apart from the list of them.

**Split out of `brain.ops.features` so a feature can be declared in a file of its own.** Every
pull request that added a feature appended a constant above `FEATURES` and a line inside the tuple,
both at the end of the same file, so two such pull requests conflicted twice over and a conflicted
pull request gets no CI. A declaration that lives in its own module cannot conflict with another
(a new file never does), but that module has to import `Feature` from somewhere, and
`brain.ops.features` is where the list is assembled by importing every declaration. If the class
stayed there, a declaration imported first would find the list half built and the list would
find the declaration half built. The class is the one thing both need, so it is here, imports
nothing from either, and `brain.ops.features` re-exports it so no existing import moves.

Rejected: a decorator that registers a feature where it is declared. `brain.ops.features` rejects
it for a reason that still holds: it puts the declaration beside the code and hides the list of
what an install can switch on from the person reading that list. A package of declarations, one
file each, is read as a directory listing instead.

Task ids: M27.15.51
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

#: Why the readers are checked against the source.
A_SWITCH_NOTHING_READS_IS_A_CONTROL_THAT_REACHES_NOTHING: Final = (
    "A feature switch is pressed in a browser and read by a route. If the route stops asking, "
    "the switch goes on rendering and changing a row, and the feature is either always on or "
    "never on whatever the screen says. So the functions that ask are named on the feature, and "
    "the source is parsed to hold the names to the calls in both directions."
)

#: The `ops.setting` namespace every switch sits under: `feature.<name>`.
FEATURE_NAMESPACE: Final = "feature"

#: A feature's name, and the last segment of its key. The key grammar's own segment shape.
FEATURE_NAME_PATTERN: Final = r"^[a-z][a-z0-9_]*$"

#: `module:function`, both dotted identifiers, as `brain.ops.controls` spells a symbol.
_READER_RE: Final = re.compile(r"^[a-z_][a-z0-9_.]*:[a-z_][a-z0-9_]*$")


class FeatureError(Exception):
    """Raised for a feature this product does not declare, or one declared wrongly."""


@dataclass(frozen=True)
class Feature:
    """One switch an administrator can turn, and every function that reads it.

    `what` and `while_off` are product text a person reads beside the switch: what turning it
    on lets somebody do, and what stays true while it is off.
    """

    name: str
    title: str
    what: str
    while_off: str
    #: Every function that asks `is_on` about this feature, as `module:function`: the ones it gates
    #: and the ones that only say on a screen whether it is on, because both stop being true
    #: together if the switch stops reaching them.
    read_by: tuple[str, ...]

    def __post_init__(self) -> None:
        if not re.fullmatch(FEATURE_NAME_PATTERN, self.name):
            msg = f"{self.name!r} is not a feature name: lowercase, digits and underscores"
            raise FeatureError(msg)
        named = ((self.title, "title"), (self.what, "what"), (self.while_off, "while_off"))
        for sentence, field in named:
            if not sentence.strip():
                msg = f"feature {self.name!r} has no {field}, so its switch explains nothing"
                raise FeatureError(msg)
        if not self.read_by:
            msg = (
                f"feature {self.name!r} names no reader. "
                f"{A_SWITCH_NOTHING_READS_IS_A_CONTROL_THAT_REACHES_NOTHING}"
            )
            raise FeatureError(msg)
        for reader in self.read_by:
            if not _READER_RE.match(reader):
                msg = f"feature {self.name!r} names {reader!r}, which is not module:function"
                raise FeatureError(msg)

    @property
    def key(self) -> str:
        """The `ops.setting` key this feature's switch is kept under."""
        return f"{FEATURE_NAMESPACE}.{self.name}"
