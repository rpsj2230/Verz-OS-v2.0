"""A feature is declared by adding a file, and listing the directory finds it.

`brain.ops.features` used to take every new feature as a constant and a tuple line appended at the
end of one file, so two pull requests adding a feature conflicted twice, and a conflicted pull
request gets no CI. These tests hold what replaced it: the discovery is right, it is ordered by
name and not by the file system, a declared feature is held to the same reader check as a built-in
one, and a name cannot be declared twice.

The package under test is built in a temporary directory and imported from there, because the real
package holds no feature until the first one is added and a test over an empty directory proves
nothing about discovery.

Task ids: M27.15.51
"""

from __future__ import annotations

import importlib
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path

import pytest

from brain.ops import features
from brain.ops.feature_model import Feature
from brain.ops.features import (
    BUILT_IN_FEATURES,
    FEATURES,
    FeatureError,
    declared_in,
    declared_modules,
    feature_gaps,
)

PACKAGE = "decl_pkg_for_the_features_test"


def _feature(name: str, reader: str = f"{PACKAGE}.reader:reads") -> str:
    return textwrap.dedent(
        f"""
        from brain.ops.feature_model import Feature

        {name.upper()} = Feature(
            name="{name}",
            title="t",
            what="w",
            while_off="o",
            read_by=("{reader}",),
        )
        """
    )


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


@pytest.fixture
def package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A declaring package on `sys.path`: `b_second` and `a_first` written in that order, a
    helper that starts with an underscore, and a reader module that imports a feature."""
    root = tmp_path / PACKAGE
    root.mkdir()
    _write(root / "__init__.py", '"""A package of declarations for a test."""\n')
    _write(root / "b_second.py", _feature("beta") + _feature("gamma").split("\n", 2)[2])
    _write(root / "a_first.py", _feature("alpha"))
    _write(root / "_helper.py", _feature("hidden"))
    _write(
        root / "reader.py",
        textwrap.dedent(
            f"""
            from brain.ops.features import is_on
            from {PACKAGE}.a_first import ALPHA

            async def reads(session):
                return await is_on(session, ALPHA)
            """
        ),
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(features, "DECLARED_PACKAGE", PACKAGE)
    importlib.invalidate_caches()
    yield root
    for name in [one for one in sys.modules if one == PACKAGE or one.startswith(f"{PACKAGE}.")]:
        del sys.modules[name]


def test_every_feature_a_package_declares_is_found_in_name_order(package: Path) -> None:
    """`a_first` is found before `b_second` though it was written second, and a module that
    binds two features gives both in the order it binds them. Delete this and the screen's order
    depends on the file system, so two installs list the same switches differently."""
    assert [one.name for one in declared_in(PACKAGE)] == ["alpha", "beta", "gamma"]


def test_a_module_beginning_with_an_underscore_is_a_helper_and_declares_nothing(
    package: Path,
) -> None:
    """Delete this and a helper that builds a `Feature` to demonstrate one becomes a switch an
    administrator sees and nothing reads."""
    assert "hidden" not in [one.name for one in declared_in(PACKAGE)]
    assert all(
        not one.__name__.rpartition(".")[2].startswith("_") for one in declared_modules(PACKAGE)
    )


def test_a_feature_one_module_imports_from_another_is_counted_once(package: Path) -> None:
    """`reader` imports `ALPHA` to ask about it, so the same object is bound in two modules.
    Delete this and every reader that names its feature doubles it on the screen, and the
    duplicate-name check then refuses a perfectly good tree."""
    names = [one.name for one in declared_in(PACKAGE)]

    assert names.count("alpha") == 1


def test_two_features_with_one_name_are_refused_and_not_drawn_as_two_switches() -> None:
    """The refusal. Delete this and two declarations over one `feature.<name>` row render as two
    switches that turn each other on and off."""
    one = Feature(name="same", title="t", what="w", while_off="o", read_by=("m:f",))
    two = Feature(name="same", title="u", what="x", while_off="p", read_by=("m:g",))

    with pytest.raises(FeatureError, match="two features are declared with the name 'same'"):
        features._checked_unique((one, two))


def test_distinct_names_pass_the_uniqueness_check_in_the_order_given() -> None:
    """The positive sibling: a check that refused everything would satisfy the test above."""
    one = Feature(name="first", title="t", what="w", while_off="o", read_by=("m:f",))
    two = Feature(name="second", title="t", what="w", while_off="o", read_by=("m:g",))

    assert features._checked_unique((one, two)) == (one, two)


def test_a_declared_feature_is_held_to_the_reader_check_like_a_built_in_one(
    package: Path,
) -> None:
    """The reader of `alpha` asks about `ALPHA`, which is bound in `a_first` and not in
    `features.py`, so the check has to find its name there. Delete this and a declared feature
    names a reader that does not ask about it and nothing says so."""
    found = feature_gaps(declared_in(PACKAGE)[:1], src=package)

    assert found == (), found


def test_a_declared_reader_that_asks_about_another_feature_is_a_gap(package: Path) -> None:
    """The refusal sibling of the test above: `beta` names the reader of `alpha`, which never
    asks about `BETA`. Delete this and the declared half of the check passes everything."""
    beta = declared_in(PACKAGE)[1]

    found = feature_gaps((beta,), src=package)

    assert any("never asks" in one for one in found), found


def test_the_list_is_the_built_in_features_then_the_declared_ones_in_that_order(
    package: Path,
) -> None:
    """Assembled over the temporary package, because the real one declares nothing yet and an
    assembly that dropped it, or put it first, would pass over an empty directory. Delete this and
    a new feature is found by `declared_in` and never reaches the list the screen draws."""
    assembled = features.all_features(PACKAGE)

    assert assembled[: len(BUILT_IN_FEATURES)] == BUILT_IN_FEATURES
    assert [one.name for one in assembled[len(BUILT_IN_FEATURES) :]] == ["alpha", "beta", "gamma"]


def test_the_features_the_product_lists_are_the_built_in_ones_then_the_declared() -> None:
    """The real tree. Delete this and the assembly can drop either half: the built-in list the
    seventeen readers import from, or the package a new feature is declared in."""
    assert (*BUILT_IN_FEATURES, *declared_in()) == FEATURES
    names = [one.name for one in FEATURES]
    assert len(names) == len(set(names))
    assert len(BUILT_IN_FEATURES) > 0


def test_the_real_declaring_package_is_found_and_imports_cleanly() -> None:
    """The directory this package's docstring tells a contributor to add to exists and can be
    listed. Delete this and a typo in the package name makes discovery find nothing, silently,
    which is indistinguishable from there being no new features yet."""
    assert declared_modules() == declared_modules(features.DECLARED_PACKAGE)
    assert importlib.import_module("brain.ops.features_declared").__doc__
