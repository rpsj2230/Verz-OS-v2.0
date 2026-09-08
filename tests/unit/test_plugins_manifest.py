"""What a plugin may say about itself, and every shape of reach it may not.

Every test here is about a file that arrived from outside the company. The ones that matter
most are the refusals: a manifest that could carry a grant would make importing a file a way
to grant one, and the review meant to catch it would be reviewing prose.

Task ids: M29.2.1
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from brain.core.entitlement import Capability
from brain.install import INSTALL_PREFIX, INSTALLATION
from brain.plugins.manifest import (
    ConfigKey,
    ManifestError,
    PluginManifest,
    declared_reach_keys,
    manifest_from,
)
from brain.tools.skills import REACH_KEYS


def _fields(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "plugin_id": "probe",
        "version": "1.0.0",
        "point": "connector",
        "core_min": "1.0.0",
        "core_max": "1.4.0",
    }
    base.update(overrides)
    return base


def _a_manifest(**overrides: object) -> PluginManifest:
    return PluginManifest(**_fields(**overrides))  # type: ignore[arg-type]


# --------------------------------------------------------- reach, and the absence of it
def test_a_manifest_has_no_field_that_could_hold_a_grant() -> None:
    """**The absence is the mechanism.** `brain.tools.skills` makes the same argument about
    a skill: if a manifest could declare a capability, importing a file would be a way to
    grant one. Asserted against the model's own field names rather than against a list in a
    docstring, so a field added later fails here.

    Delete this and a `grants:` field can be added and would look like the others."""
    declared = set(PluginManifest.model_fields)

    assert declared & REACH_KEYS == set()
    assert "principal_id" not in declared
    assert "entitlement" not in declared


@pytest.mark.parametrize("word", sorted(REACH_KEYS))
def test_every_word_meaning_reach_is_refused_by_name(word: str) -> None:
    """Refused with a sentence rather than as merely unknown. A manifest whose
    `capabilities:` line was dropped without comment looks identical to one whose line was
    honoured, and the author believes their plugin holds what it asked for.

    The list comes from `brain.tools.skills.REACH_KEYS` so there is one owner of the words.
    Delete this and a grant arrives as an unknown field and reads as a typo."""
    raw = _fields()
    raw[word] = "read:client.name"

    with pytest.raises(ManifestError, match="does not carry reach"):
        manifest_from(raw)


def test_a_manifest_carrying_no_reach_word_is_accepted() -> None:
    """The positive case. A refusal check tested only by its refusals is satisfied by a
    function that refuses every manifest, and then nothing installs.

    Delete this and `manifest_from` could tighten to refuse everything unnoticed."""
    parsed = manifest_from(_fields())

    assert parsed.plugin_id == "probe"


def test_the_reach_words_are_reported_before_the_shape_of_the_manifest_is() -> None:
    """Order is load-bearing. Pydantic's `extra="forbid"` would answer first and tell the
    author their grant is an unknown field, which sends them looking for a typo instead of
    reading the sentence explaining that a plugin does not carry reach.

    Delete this and the specific refusal is unreachable behind the general one."""
    raw = _fields(scope="department:sales")
    raw["also_not_a_field"] = "x"

    with pytest.raises(ManifestError, match="does not carry reach"):
        manifest_from(raw)


def test_a_required_capability_is_recorded_and_nothing_else_happens_to_it() -> None:
    """`requires` is a question about the caller. A manifest asking for `admin:everything`
    is neither refused nor honoured, because refusing it would make the manifest a thing
    worth negotiating with and honouring it would make a file a source of grants.

    Delete this and somebody adds a ceiling on requirements, which is the first place a
    reader would then look for the exception."""
    manifest = _a_manifest(requires=(Capability(value="admin:everything"),))

    assert manifest.requires == (Capability(value="admin:everything"),)


def test_anything_that_is_not_a_mapping_is_not_a_manifest() -> None:
    """What arrives is parsed from a file and may be a list, a string or nothing. A caller
    who had to prove it was a mapping first would have a reason to skip the reach check.

    Delete this and a non-mapping reaches pydantic and fails with a message about fields."""
    assert declared_reach_keys(["capabilities"]) == ()
    with pytest.raises(ManifestError, match="a manifest is a mapping"):
        manifest_from(["capabilities"])


# --------------------------------------------------------------- the config schema
def test_a_config_key_may_not_be_an_installation_setting() -> None:
    """`brain.ops.independence` refuses a second module reading an `INSTALL_` value because
    two readers means two defaults and the wrong one is the one nobody looked at. A plugin
    declaring one is that second reader arriving as data, on a client's server, where a
    sweep over this repository would never meet it.

    Asserted against a real declared setting rather than an invented name, so the tie to
    `brain.install` is a fact rather than a prefix match. Delete this and a plugin can quietly
    become the second reader of the identity provider's issuer."""
    real = next(one.name for one in INSTALLATION if one.required)

    assert real.startswith(INSTALL_PREFIX)
    with pytest.raises(ValidationError, match="is an installation setting"):
        ConfigKey(name=real, meaning="the issuer, read a second time")


@pytest.mark.parametrize("word", sorted(REACH_KEYS))
def test_a_config_key_may_not_name_reach(word: str) -> None:
    """A config schema is a list of names a person sets on a server, and a plugin whose
    config included `CAPABILITIES` would be asking an operator to grant it something in a
    file nothing checks.

    Delete this and the reach words are refused in the manifest and allowed in its config."""
    with pytest.raises(ValidationError, match="names reach"):
        ConfigKey(name=word.upper(), meaning="a way in")


@pytest.mark.parametrize("blank", ["", " ", "\t"])
def test_a_config_key_with_no_meaning_is_refused(blank: str) -> None:
    """`meaning` is what the install runbook prints. A setting nobody can explain is one
    somebody guesses at on a client's server, where nobody here can see what they guessed.
    Whitespace is refused as well as empty, because a space passes a length check.

    Delete this and a plugin can require a value it never explains."""
    with pytest.raises(ValidationError):
        ConfigKey(name="PROBE_TOKEN", meaning=blank)


def test_a_config_key_is_an_environment_variable_name() -> None:
    """A key is set in an environment file beside everything else, so a lowercase or spaced
    name is one nobody can set. Delete this and a plugin declares config nothing can supply."""
    with pytest.raises(ValidationError, match="not an environment variable name"):
        ConfigKey(name="probe token", meaning="something")


def test_an_ordinary_config_key_is_accepted() -> None:
    """The positive sibling of the four refusals above. Delete this and `ConfigKey` could
    refuse every name with the suite green."""
    key = ConfigKey(name="PROBE_TOKEN", meaning="the token this plugin authenticates with")

    assert key.required is False


def test_one_config_key_declared_twice_is_refused_rather_than_deduplicated() -> None:
    """Two declarations are two meanings and the runbook would print whichever came first.
    `brain.connectors.manifest.ProjectedEntity` refuses a duplicate field for the same
    reason: deduplicating picks one without saying so.

    Delete this and a manifest can carry two contradictory explanations of one value."""
    twice = (
        ConfigKey(name="PROBE_TOKEN", meaning="the token"),
        ConfigKey(name="PROBE_TOKEN", meaning="something else entirely"),
    )

    with pytest.raises(ValidationError, match="more than once"):
        _a_manifest(config=twice)


def test_two_different_config_keys_are_accepted() -> None:
    """The positive case for the duplicate check, without which it is satisfied by refusing
    every manifest with any config at all. Delete this and no plugin may declare two values."""
    manifest = _a_manifest(
        config=(
            ConfigKey(name="PROBE_TOKEN", meaning="the token"),
            ConfigKey(name="PROBE_HOST", meaning="where the vendor is"),
        )
    )

    assert len(manifest.config) == 2


# ------------------------------------------------------- identity, version and range
def test_a_plugin_id_is_a_name() -> None:
    """The id is what the registry keys on and what an operator types. Delete this and two
    plugins can be installed under ids that differ by a space."""
    with pytest.raises(ValidationError, match="is not a name"):
        _a_manifest(plugin_id="Probe Connector")


@pytest.mark.parametrize("field", ["version", "core_min", "core_max"])
def test_every_version_is_semantic_or_no_range_can_be_checked(field: str) -> None:
    """`admits` compares three integers, so a version like `2026-09` would raise inside the
    comparison rather than at the manifest, a long way from the file that caused it.

    Delete this and a malformed version fails at install time with a ValueError about
    unpacking."""
    with pytest.raises(ValidationError, match="not a semantic version"):
        _a_manifest(**{field: "2026-09"})


def test_a_compatibility_range_must_be_the_right_way_round() -> None:
    """An inverted range admits nothing, so every refusal would name the core version rather
    than the manifest and the operator would go looking at the platform.

    Delete this and a typo in a manifest presents as this system refusing to run anything."""
    with pytest.raises(ValidationError, match="above core_max"):
        _a_manifest(core_min="2.0.0", core_max="1.0.0")


def test_a_range_is_inclusive_at_both_ends() -> None:
    """A half-open top would refuse the exact version the author tested against, which reads
    as a defect in this system rather than as a policy.

    Delete this and a plugin declaring 1.0.0 to 1.4.0 stops working on 1.4.0."""
    manifest = _a_manifest(core_min="1.0.0", core_max="1.4.0")

    assert manifest.admits("1.0.0")
    assert manifest.admits("1.4.0")
    assert not manifest.admits("0.9.9")
    assert not manifest.admits("1.5.0")


def test_versions_are_compared_as_numbers_and_not_as_strings() -> None:
    """`"0.10.0" < "0.9.0"` is true of the strings and false of the versions, so a range
    checked on strings admits and refuses the wrong plugins around every tenth release.

    Delete this and the bug returns the first time somebody simplifies the comparison."""
    manifest = _a_manifest(core_min="0.9.0", core_max="0.11.0")

    assert manifest.admits("0.10.0")


def test_admits_refuses_a_core_version_it_cannot_parse() -> None:
    """The range is checked against whatever the caller says this platform is, and that
    string comes from a release tag. A version it cannot parse is refused rather than
    compared, because the comparison would raise somewhere less useful.

    Delete this and a malformed core version crashes inside the comparison."""
    with pytest.raises(ManifestError, match="not a semantic version"):
        _a_manifest().admits("v1.0")


def test_comparing_two_different_plugins_versions_is_refused() -> None:
    """A lifecycle comparing two different plugins' versions is a bug that reads as an
    upgrade, and the answer it gives is arbitrary rather than wrong, which is worse.

    Delete this and `upgrade` can replace one plugin with another under the first's name."""
    with pytest.raises(ManifestError, match="different plugins"):
        _a_manifest(plugin_id="one").is_newer_than(_a_manifest(plugin_id="two"))


def test_a_later_version_of_the_same_plugin_is_newer() -> None:
    """The positive case, and it is what `upgrade` branches on. Delete this and
    `is_newer_than` could return False always with only the refusal tests to notice."""
    assert _a_manifest(version="1.1.0").is_newer_than(_a_manifest(version="1.0.9"))
    assert not _a_manifest(version="1.0.0").is_newer_than(_a_manifest(version="1.0.0"))


def test_a_type_name_a_manifest_declares_has_to_be_a_type_name() -> None:
    """`accepts` and `produces` are checked against `UNREDACTED_TYPE_NAMES` by the contract
    module, and a value that is not an identifier can never match one, so the check would
    pass on a manifest saying `accepts: ["TypedResult | Mask"]`.

    Delete this and a plugin can declare a type expression that defeats the contract check
    by not being a name."""
    with pytest.raises(ValidationError, match="not a type name"):
        _a_manifest(accepts=("TypedResult | Mask",))
    with pytest.raises(ValidationError, match="not a type name"):
        _a_manifest(produces="list[Entity]")


def test_a_manifest_may_declare_nothing_about_what_it_handles() -> None:
    """Both fields default to empty and a plugin that names neither is legitimate: a
    template handles no record at all. Delete this and the empty string starts failing the
    type-name check, which is the shape of the branch that would break it."""
    manifest = _a_manifest()

    assert manifest.accepts == ()
    assert manifest.produces == ""
