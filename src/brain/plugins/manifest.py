"""What a plugin says about itself, and every shape of reach it is refused a way to say.

A manifest arrives from outside the company, like a skill and unlike anything else this
system loads. `brain.tools.skills` settled the rule that governs both and it is stated there
in one sentence: of the three things an agent is built from, "a tool is grantable, and it is
the only one". This module applies that to plugins.

**The absence is the mechanism.** `PluginManifest` has no field that could hold a grant, a
scope, an entitlement set, a principal id or a leash rung, and `extra="forbid"` means an
unknown key is refused rather than ignored. A manifest whose `capabilities:` line was
silently dropped looks exactly like one whose `capabilities:` line was honoured, which is why
the reach keys are refused **by name** with an explanation instead of merely being unknown.
The names come from `brain.tools.skills.REACH_KEYS` rather than being listed again here: two
lists of the words meaning "reach" drift, and the one that drifts is the one nobody looked at.

**`requires` is a request and never a grant, and this is the paragraph that matters.**
Entitlements in this system are additive with no deny list, which `brain.core.entitlement`
states as the reason a union is safe: revocation is the deletion of a grant, so a second
source of grants can only ever add and nothing takes anything back. An extension point that
accepted grants would be exactly that second source. So a manifest naming
`admin:everything` is not refused and is not honoured: it is a list of capabilities the
plugin would like the caller to be holding, checked against the caller in
`brain.plugins.contract` and never added to anything.

Rejected: refusing a manifest that requires more than some ceiling. It reads stricter and is
weaker, because it turns the manifest into a thing worth negotiating with. A requirement that
cannot widen anything does not need a bound, and a bound would be the first place somebody
looked for the exception.

**A config key may not be an installation setting.** `brain.ops.independence.second_readers`
refuses any module other than `brain.install` reading an `INSTALL_` value, because two readers
means two defaults and the wrong one is the one nobody looked at. A plugin declaring
`INSTALL_OIDC_ISSUER` in its config schema is that second reader arriving as data, where no
sweep over the source would ever see it.

**A compatibility range is closed at both ends.** An open upper bound is a plugin author
claiming compatibility with versions of this platform that do not exist yet, and the claim is
free to make and impossible to check. The cost of a closed range is a plugin that needs its
manifest edited at the next major version, which is a person deciding it still works.

Task ids: M29.2.1
"""

from __future__ import annotations

import re
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from brain.core.entitlement import Capability
from brain.install import INSTALL_PREFIX
from brain.tools.skills import REACH_KEYS, VERSION_RE

#: A plugin's identity. The same shape a skill name takes, and folded the same way.
PLUGIN_ID_RE: Final = re.compile(r"^[a-z][a-z0-9_-]{0,79}$")

#: A config key. Upper case, because it is set in an environment file beside everything else.
CONFIG_KEY_RE: Final = re.compile(r"^[A-Z][A-Z0-9_]{0,79}$")

#: A type name a manifest may name as what it accepts or produces.
CONTRACT_TYPE_RE: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,79}$")


class ManifestError(Exception):
    """A plugin manifest was written in a way that cannot be made safe.

    Outside `brain.core.errors` for the reason `brain.tools.skills.SkillError` gives: nobody
    asking a question sees this. It is a contract violation by whoever wrote the manifest and
    it belongs in front of them, at install time, rather than degrading anything at request
    time.
    """


#: Why a required capability is not a granted one.
A_REQUIREMENT_IS_A_QUESTION_ABOUT_THE_CALLER_AND_NEVER_A_GRANT: Final = (
    "Entitlements here are additive and there is no deny list, so a second source of grants "
    "can only ever add and nothing takes any of them back. A manifest that could grant would "
    "be that second source, arriving from outside the company as a file. What a manifest "
    "names is what the plugin needs the caller to already hold, and the only thing done with "
    "it is to compare it against the caller's own reach."
)

#: Why the reach words are refused by name rather than being merely unknown.
A_SILENTLY_IGNORED_GRANT_LOOKS_LIKE_AN_HONOURED_ONE: Final = (
    "A manifest whose capabilities line was dropped without comment looks identical to one "
    "whose capabilities line was honoured, from the outside and from the inside. Whoever "
    "wrote it believes the plugin holds what it asked for. So the words are refused with a "
    "sentence saying why, which is the difference between a rule and a hope."
)

#: Why a plugin cannot declare an installation setting as its own config.
A_PLUGIN_CONFIG_KEY_IS_A_SECOND_READER_THAT_NO_SWEEP_CAN_SEE: Final = (
    "brain.ops.independence refuses a second module reading an INSTALL_ value, because two "
    "readers means two defaults and the wrong one is the one nobody looked at. A plugin "
    "declaring one in its config schema is that second reader arriving as data, on a client's "
    "server, where a sweep over this repository's source would never meet it."
)

#: Why the upper end of a compatibility range is required.
COMPATIBILITY_WITH_A_VERSION_THAT_DOES_NOT_EXIST_CANNOT_BE_CLAIMED: Final = (
    "An open upper bound is an author claiming their plugin works against releases nobody has "
    "written, which is free to assert and impossible to check, and it fails on the upgrade "
    "rather than on the install. A closed range costs an edited manifest at the next major "
    "version, and that edit is a person deciding it still works."
)


def _version_parts(value: str) -> tuple[int, int, int]:
    """A semantic version as three integers, for comparison.

    Compared as numbers rather than as strings, because `"0.10.0" < "0.9.0"` is true of the
    strings and false of the versions, and a range checked on strings admits and refuses the
    wrong plugins around every tenth release.
    """
    major, minor, patch = value.split(".")
    return int(major), int(minor), int(patch)


class ConfigKey(BaseModel):
    """One value a plugin needs set on the client's server.

    `meaning` is required and is not a comment, for the reason `brain.install.Setting`
    requires the same of an installation value: it is what the install runbook prints, and a
    setting nobody can explain is one somebody guesses at on a client's server.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    meaning: str = Field(min_length=1, max_length=400)
    #: True when the plugin cannot start without it. There is no default field: a plugin's
    #: default is the plugin's business, and a default declared here would be a value this
    #: repository had an opinion about on a server it has never seen.
    required: bool = False

    @field_validator("name")
    @classmethod
    def _shape(cls, value: str) -> str:
        if not CONFIG_KEY_RE.match(value):
            msg = f"config key {value!r} is not an environment variable name"
            raise ValueError(msg)
        if value.startswith(INSTALL_PREFIX):
            why = A_PLUGIN_CONFIG_KEY_IS_A_SECOND_READER_THAT_NO_SWEEP_CAN_SEE
            msg = (
                f"config key {value!r} is an installation setting, which belongs to the "
                f"install and is read in one place. {why}"
            )
            raise ValueError(msg)
        if value.lower() in REACH_KEYS:
            msg = (
                f"config key {value!r} names reach, and a plugin does not configure its own "
                f"reach. {A_REQUIREMENT_IS_A_QUESTION_ABOUT_THE_CALLER_AND_NEVER_A_GRANT}"
            )
            raise ValueError(msg)
        return value

    @field_validator("meaning")
    @classmethod
    def _explained(cls, value: str) -> str:
        if not value.strip():
            msg = (
                "a config key with no meaning written down is one somebody guesses at on a "
                "client's server, where nobody here can see what they guessed"
            )
            raise ValueError(msg)
        return value


class PluginManifest(BaseModel):
    """Identity, version, required capabilities, config schema and compatibility range.

    Frozen and closed. Read the class body as a list of what a plugin may say about itself,
    and then read `brain.plugins.contract` for what is done with each of those things, which
    in the case of `requires` is a comparison and nothing else.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: What the plugin is called, and what the registry keys it by.
    plugin_id: str = Field(min_length=1, max_length=80)
    #: The plugin's own version, semantic. Informational to this system and load-bearing to
    #: the lifecycle, which refuses an upgrade that does not move it.
    version: str
    #: The name of the extension point it plugs into. Checked against the register.
    point: str = Field(min_length=1, max_length=80)
    #: Capabilities the plugin needs the caller to hold. A question, never a grant.
    requires: tuple[Capability, ...] = ()
    #: Values that have to be set on the client's server for it to work.
    config: tuple[ConfigKey, ...] = ()
    #: The oldest core version this plugin was written against.
    core_min: str
    #: The newest core version its author has actually checked it against.
    core_max: str
    #: Type names the plugin is handed. Checked by `brain.plugins.contract`.
    accepts: tuple[str, ...] = ()
    #: The type name the plugin returns, if it returns one.
    produces: str = ""

    @field_validator("plugin_id")
    @classmethod
    def _identity(cls, value: str) -> str:
        if not PLUGIN_ID_RE.match(value):
            msg = f"plugin id {value!r} is not a name"
            raise ValueError(msg)
        return value

    @field_validator("version", "core_min", "core_max")
    @classmethod
    def _semantic(cls, value: str) -> str:
        if not VERSION_RE.match(value):
            msg = f"{value!r} is not a semantic version; a range cannot be checked against it"
            raise ValueError(msg)
        return value

    @field_validator("accepts", "produces")
    @classmethod
    def _type_names(cls, value: tuple[str, ...] | str) -> tuple[str, ...] | str:
        names = value if isinstance(value, tuple) else ((value,) if value else ())
        for one in names:
            if not CONTRACT_TYPE_RE.match(one):
                msg = f"{one!r} is not a type name, so no contract check can be made against it"
                raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _range_is_closed_and_ordered(self) -> Self:
        """The compatibility range has to be a range.

        See `COMPATIBILITY_WITH_A_VERSION_THAT_DOES_NOT_EXIST_CANNOT_BE_CLAIMED` for why both
        ends are required. Ordering is checked because an inverted range admits nothing at
        all, and a plugin that can never install is a support call rather than a refusal:
        every version is outside it, so the failure names the version rather than the range.
        """
        if _version_parts(self.core_min) > _version_parts(self.core_max):
            msg = (
                f"{self.plugin_id} declares core_min {self.core_min} above core_max "
                f"{self.core_max}, so no version of this platform is inside the range and "
                "every refusal would name the version rather than the manifest"
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _no_duplicate_config_keys(self) -> Self:
        """Two declarations of one key are two meanings, and one of them would win silently.

        Refused rather than deduplicated, following `ProjectedEntity` in
        `brain.connectors.manifest`: deduplicating picks one without saying so, and the one it
        picks decides what the install runbook prints.
        """
        names = [one.name for one in self.config]
        repeated = sorted({one for one in names if names.count(one) > 1})
        if repeated:
            msg = (
                f"{self.plugin_id} declares {repeated} more than once; two declarations are "
                "two meanings and the runbook would print whichever came first"
            )
            raise ValueError(msg)
        return self

    def admits(self, core_version: str) -> bool:
        """True when this plugin declares itself compatible with that core version.

        Inclusive at both ends. A plugin written against 1.2.0 and checked up to 1.4.0 runs on
        both, because a half-open range at the top would refuse the exact version its author
        tested against, which reads as a bug in this system rather than as a policy.
        """
        if not VERSION_RE.match(core_version):
            msg = f"{core_version!r} is not a semantic version"
            raise ManifestError(msg)
        return (
            _version_parts(self.core_min)
            <= _version_parts(core_version)
            <= _version_parts(self.core_max)
        )

    def is_newer_than(self, other: PluginManifest) -> bool:
        """True when this manifest is a later version of the same plugin.

        The identity check is here rather than at the call site because a lifecycle comparing
        two different plugins' versions is a bug that reads as an upgrade, and the answer it
        would give is arbitrary rather than wrong, which is worse.
        """
        if self.plugin_id != other.plugin_id:
            msg = (
                f"{self.plugin_id} and {other.plugin_id} are different plugins, and comparing "
                "their versions answers a question nobody asked"
            )
            raise ManifestError(msg)
        return _version_parts(self.version) > _version_parts(other.version)


def declared_reach_keys(raw: object) -> tuple[str, ...]:
    """Every reach word a raw manifest mapping carries, before pydantic ever sees it.

    **The refusal has to happen where the word still exists.** `extra="forbid"` refuses an
    unknown key and says it is unknown, which sends the author looking for a typo. These keys
    are not typos: each one is somebody expressing reach in a file that arrived from outside
    the company, and they are worth a sentence rather than a shrug. See
    `A_SILENTLY_IGNORED_GRANT_LOOKS_LIKE_AN_HONOURED_ONE`.

    Takes `object` rather than a mapping because what arrives is parsed from a file and may be
    anything at all; a caller who has to prove it is a mapping first has a reason to skip this.
    """
    if not isinstance(raw, dict):
        return ()
    return tuple(sorted(str(key) for key in raw if str(key).lower() in REACH_KEYS))


def manifest_from(raw: object) -> PluginManifest:
    """One parsed manifest, with the reach keys refused by name first.

    Order is load-bearing and is the same ordering `brain.ops.sweeps.sweep_traceability` uses
    on its own malformed-line check: the specific refusal runs before the general one, or the
    general one answers first and the author is told their grant is an unknown field.
    """
    smuggled = declared_reach_keys(raw)
    if smuggled:
        msg = (
            f"this manifest declares {list(smuggled)}, and a plugin does not carry reach. "
            f"{A_REQUIREMENT_IS_A_QUESTION_ABOUT_THE_CALLER_AND_NEVER_A_GRANT} "
            f"{A_SILENTLY_IGNORED_GRANT_LOOKS_LIKE_AN_HONOURED_ONE}"
        )
        raise ManifestError(msg)
    if not isinstance(raw, dict):
        msg = "a manifest is a mapping of fields, and this is not one"
        raise ManifestError(msg)
    return PluginManifest.model_validate(raw)
