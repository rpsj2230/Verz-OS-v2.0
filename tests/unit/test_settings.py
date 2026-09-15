"""The settings module: a handed environment, the two database names, and the role password.

Task ids: M41.1.2, M31.3.1.2
"""

from __future__ import annotations

import pytest

from brain.settings import Settings, settings_from

CURRENT = "postgresql://brain@db:5432/current"
STALE = "postgresql://brain@db:5432/stale"


def test_settings_from_a_mapping_ignores_the_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """A handed environment is the whole environment. Both database names are set on the
    process and neither answers for a mapping that leaves them out; a mapping that names one is
    read.

    `_HandedEnvironment` overrides a method private to pydantic-settings, so this is also what
    notices an upgrade renaming it. Delete this and that upgrade reads the real environment
    behind every command's `env=` parameter, silently, and a test on a machine with a database
    configured starts passing for the wrong reason."""
    monkeypatch.setenv("DATABASE_URL", STALE)
    monkeypatch.setenv("BRAIN_DATABASE_URL", STALE)

    assert settings_from({}).database_url == ""
    assert settings_from({"DATABASE_URL": CURRENT}).database_url == CURRENT


def test_a_handed_mapping_and_the_process_agree_about_which_database_name_wins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The prefixed name wins, from the process and from a mapping alike, so the worker and the
    application cannot resolve one host to two databases.

    Delete this and `settings_from` can be rewritten to look the names up by hand in the other
    order, which is exactly the disagreement this module was written to end."""
    both = {"BRAIN_DATABASE_URL": CURRENT, "DATABASE_URL": STALE}
    for name, value in both.items():
        monkeypatch.setenv(name, value)

    assert Settings().database_url == CURRENT
    assert settings_from(both).database_url == CURRENT


def test_the_role_password_is_read_under_its_existing_name_and_never_rendered() -> None:
    """`APP_ROLE_PASSWORD` is the name three compose files and `.env.example` already use, and
    the settings object is rendered whole into logs, so the value must not be in its rendering.

    Delete this and the field can lose `repr=False`, after which the first traceback carrying
    the settings object prints the database role's password."""
    settings = settings_from({"APP_ROLE_PASSWORD": "a-password-nobody-guesses"})

    assert settings.app_role_password == "a-password-nobody-guesses"
    assert "a-password-nobody-guesses" not in repr(settings)
    assert "a-password-nobody-guesses" not in str(settings)


def test_the_launcher_checks_the_role_password_it_read_from_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`brain.serve` hands `brain.config` the password `Settings` read: a known default refuses
    to bind a port, and a real one starts.

    Delete this and the launcher can hand the check an empty string, which no forbidden value
    matches, so a staging install running as `change-me` starts and says nothing."""
    import brain.serve as serve

    started: list[bool] = []
    monkeypatch.setattr("uvicorn.run", lambda *_a, **_k: started.append(True))
    monkeypatch.setenv("BRAIN_ENV", "staging")
    monkeypatch.delenv("BRAIN_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", CURRENT)

    monkeypatch.setenv("APP_ROLE_PASSWORD", "change-me")
    with pytest.raises(RuntimeError, match="configuration is not valid"):
        serve.main()
    assert started == []

    monkeypatch.setenv("APP_ROLE_PASSWORD", "a-password-nobody-guesses")
    serve.main()
    assert started == [True]


def test_the_application_module_still_exports_the_settings_class() -> None:
    """Every `from brain.app import Settings` written before the move still names the same class,
    not a copy that could drift from it.

    Delete this and the re-export can be dropped or replaced by a subclass, breaking thirty test
    imports and `console/scripts/export-openapi.py`, or worse, not breaking them."""
    from brain.app import Settings as FromTheApplication

    assert FromTheApplication is Settings
