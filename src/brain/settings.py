"""Configuration, read in one place, by a module that builds nothing when it is imported.

**`Settings` lived in `brain.app` until 2026-09-15, and `brain.app` ends `app = create_app()`.**
So a process that wanted one setting built the whole web application to get it: every router,
the middleware, the tool catalogue's imports and FastAPI itself. Nothing forced anybody to
pay that, and so nobody did. The worker read `DATABASE_URL` for itself, the demo seeder read
`DATABASE_URL` then `BRAIN_DATABASE_URL`, the schema check and the database script read them
in that order too, the sweeps read only the first, and the application read
`BRAIN_DATABASE_URL` first. **Six readers of one address with three different rules**, which
on a host where both names are set, one of them stale, is an application and a worker
connecting to two different databases while each reports healthy.

That is the shape the rule "nothing reads the environment directly" exists to prevent, and
the cost of obeying it was an import. So the settings object is here, importing only what its
own fields need, and `brain.app` re-exports it so every existing `from brain.app import
Settings` still works. `tests/invariants/test_configuration_is_read_in_one_place.py` holds
both halves: no module under `src/brain` names the process environment except this one, and
importing this one does not import `brain.app`.

**Rejected: making `brain.app` lazy instead.** `uvicorn brain.app:app` is the entry point in
`brain.serve`, in the Makefile, and in whatever a client's deployment platform stored when it
was installed, and a stored compose file is the one copy of a command this repository cannot
update. Moving the settings costs nothing on the serving side and moving the application
object costs a migration on every install.

**Rejected: keeping `env: Mapping | None = None` parameters that default to `os.environ` in
each module.** That was the pattern in five modules, and it is right about testability and
wrong about where the default lives. A default of `os.environ` in five places is five places a
new reader can be copied from. `process_environment` is that default, once, and the modules
keep their parameters.

Three kinds of caller still need the raw mapping, and they are why it is exposed at all:

- **Declared tables of names that are not fields here.** `brain.install.INSTALLATION` owns
  the `INSTALL_` names and generates `.env.example` from them, and `brain.ops.worker` owns its
  slot, pool and heartbeat names beside the arithmetic that checks them. Both read a mapping
  they are handed, and the database address in the worker's comes through `settings_from`.
- **A child process inheriting this one's environment**, which is `brain.ops.mutation`.
- **A vendor SDK that reads its key from the environment**, which `brain.ops.provider_keys`
  writes there from the vault. That is the one writer, and `writable_process_environment`
  exists for it alone.

**A variable set to nothing is a variable not set, and since 2026-09-16 that is true of every
field here.** The compose files hand the application each setting as `${NAME:-}`, because a
setting the file does not name never reaches the container at all (see
`brain.deployment.app_environment`), and an unset `NAME` then arrives as `NAME=` rather than
not arriving. Read literally, that blank is a value: `setup_issued_at` refused it as a date,
`release_check` as a boolean and `profile` as a member of its literal, so passing the setup
code through would have stopped every install that had none. `brain.install.value_of` already
treats a blank as unset, and one rule for both readers is the only arrangement where a
template line left empty means the same thing to each. See `A_BLANK_VARIABLE_IS_AN_UNSET_ONE`.

Task ids: M41.1.2, M31.3.1.2
"""

from __future__ import annotations

import os
from collections.abc import Mapping, MutableMapping
from datetime import datetime
from typing import Annotated, Final, Literal

from pydantic import AliasChoices, BeforeValidator, Field
from pydantic_settings import (
    BaseSettings,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)
from pydantic_settings.sources.utils import parse_env_vars

from brain.firstrun import Enrolment, derived_enrolment, sealed_setup_secret
from brain.ops.leases import SealedSecret
from brain.ops.wiring import DEFAULT_PROFILE

#: Why no other module under `src/brain` names `os.environ` or `getenv`.
NOTHING_ELSE_READS_THE_ENVIRONMENT: Final = (
    "Anything that differs between installs is configuration, and configuration is read in one "
    "place. A module that reads the environment for itself decides its own names, its own "
    "precedence and its own default, and the second reader of one value is the one that "
    "disagrees: until 2026-09-15 the application preferred BRAIN_DATABASE_URL and the worker "
    "read only DATABASE_URL. Read a field of Settings, or be handed a mapping by whoever did."
)

#: Why this module must not import `brain.app`.
SETTINGS_ARE_READ_WITHOUT_BUILDING_THE_APPLICATION: Final = (
    "brain.app builds the web application when it is imported. A settings module that imported "
    "it would make every process that needs one value pay for every router, and the process "
    "that declines to pay reads the environment itself, which is how the worker came to."
)


#: Why a blank environment variable resolves to the field's default.
A_BLANK_VARIABLE_IS_AN_UNSET_ONE: Final = (
    "A compose file passes a setting as ${NAME:-}, so a variable the install never set arrives "
    "in the container as NAME= rather than not at all. Read as a value, the blank is refused "
    "by every field that is not a plain string, a date, a boolean, a literal, and the "
    "application does not start over a setting nobody chose. brain.install.value_of already "
    "reads a blank as unset, so one rule for both readers is what makes a template line left "
    "empty mean the default to each."
)


class Settings(BaseSettings):
    # `arbitrary_types_allowed` is for one field and buys nothing anywhere else: every other
    # type here is one pydantic already knows, so the loosening applies to `SealedSecret`
    # alone. The alternative was a second sealed-string type, which is the thing this
    # repository refuses everywhere: two answers to one question, and the wrong copy renders.
    #
    # `env_ignore_empty`: see `A_BLANK_VARIABLE_IS_AN_UNSET_ONE`.
    model_config = SettingsConfigDict(
        env_prefix="BRAIN_",
        extra="ignore",
        arbitrary_types_allowed=True,
        env_ignore_empty=True,
    )

    env: Literal["development", "staging", "production"] = "development"
    #: Read from the environment, and corrected from the image's own manifest when the
    #: environment lies. See `resolved_commit`.
    commit_sha: str = "unknown"

    # DATABASE_URL and VALKEY_URL are read under their plain names as well as the
    # prefixed ones. The prefix exists so BRAIN_ENV cannot collide with anything else on
    # a shared host, but these two have universal names that every tool, compose file and
    # operator already uses, including alembic/env.py two directories away.
    #
    # Having two names for one setting is not a naming preference, it is a bug waiting to
    # happen, and it did: the deployed app read BRAIN_DATABASE_URL, found nothing, and
    # skipped migrations in silence while reporting healthy.
    #
    # **The prefixed name wins when both are set, and that is now true of every process.**
    # Until 2026-09-15 it was true of the application only; see the module docstring.
    database_url: str = Field(
        default="", validation_alias=AliasChoices("BRAIN_DATABASE_URL", "DATABASE_URL")
    )
    valkey_url: str = Field(
        default="", validation_alias=AliasChoices("BRAIN_VALKEY_URL", "VALKEY_URL")
    )
    #: A streaming replica of `database_url`, for console pages that only display. Empty, the
    #: default, means every console read is answered by the primary exactly as before. Under
    #: the prefixed name only: unlike the two above, no other tool has a universal name for
    #: it, and a second accepted name is a second place a stale value can win from. What is
    #: read from it, and when a page falls back to the primary, is `brain.console.read_replica`.
    read_replica_url: str = ""
    #: The password of the database role the application connects as, checked by
    #: `brain.config` against the values people leave in place. Under its existing name only,
    #: because operators and three compose files already set `APP_ROLE_PASSWORD` and a second
    #: accepted name is a second place a stale value can win from. Kept out of `repr`, because
    #: this object is rendered whole into a log line and into any traceback that carries it.
    app_role_password: str = Field(default="", validation_alias="APP_ROLE_PASSWORD", repr=False)
    #: The image reference this container was started from, repository and tag, which is how
    #: the application learns the release it is running. Under its existing name only, for the
    #: reason `app_role_password` is: the installer, the update script and every compose file
    #: already spell it `APP_IMAGE`, and the compose files hand the application the same value
    #: its `image:` line selects it by, so the two cannot disagree about one container.
    #:
    #: **Not baked into the image, because the image cannot know it.** The deploy pipeline
    #: builds and signs an image per commit, and a release tag is put on that digest afterwards
    #: as a second name, so a build argument can only ever carry the commit. See
    #: `brain.console.version_view.A_RELEASE_TAG_IS_A_NAME_GIVEN_AFTER_THE_BUILD`.
    app_image: str = Field(default="", validation_alias="APP_IMAGE")
    #: Which set of wave-2 components this install runs. See `brain.ops.wiring`.
    #:
    #: The default comes from `wiring.DEFAULT_PROFILE` rather than being spelled again
    #: here. It was written in both places for about ten minutes, which is exactly long
    #: enough for a mutation test to show that changing one of them changed nothing
    #: observable.
    profile: Literal["lite", "standard", "full"] = DEFAULT_PROFILE
    #: Where spans go. Read here so that `brain.config.check` can refuse them being set on
    #: a profile that runs no trace ledger; see `wiring.trace_config_conflicts`.
    langfuse_host: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    #: Where text goes to have a model read it. Read here for the same reason the three
    #: above are, and with a heavier consequence: `brain.config.check` refuses it being set
    #: on a profile that deploys no inference server, because a span is metadata about a
    #: request and this address receives the text of the document itself. See
    #: `brain.ops.inference.inference_config_conflicts`.
    inference_url: str = ""
    #: Whether this install looks for a newer release at all. Off unless an install switches it
    #: on, because a look is a request leaving the client's network; see
    #: `brain.deployment.release_feed.A_CHECK_NOBODY_SWITCHED_ON_IS_A_DISCLOSURE_NOBODY_AGREED_TO`.
    release_check: bool = False
    #: A copy of the release list to ask instead of the product's own, such as a mirror inside
    #: the client's network. Read only while `release_check` is on. Handed to
    #: `brain.deployment.release_feed.feed_address`, which reads no environment of its own; see
    #: `release_feed.CONFIGURATION_IS_READ_IN_ONE_PLACE`.
    release_feed_url: str = ""
    #: Which system the built-in row tools read from, and therefore the first half of every
    #: tool name in the catalogue. `RowTool` refuses an empty source, because two systems'
    #: record ids collide by coincidence of integers, so this carries a real default rather
    #: than an empty string that would fail startup on a fresh install.
    tool_source: str = "local"
    #: The console and the widget only. Not a wildcard, in any environment.
    cors_origins: tuple[str, ...] = ()
    #: Off in tests, on everywhere else. A deployment that wants migrations applied
    #: by hand sets this false and runs `alembic upgrade head` itself.
    run_migrations: bool = True
    request_timeout_seconds: float = 30.0
    #: The setup code the installer minted for this install, and the instant it minted it.
    #: One place reads configuration, so this is where the pair arrives, and it is sealed on
    #: the way in because this object is rendered whole into a log line at startup and into
    #: any traceback that carries it. See `brain.firstrun.sealed_setup_secret`.
    #:
    #: Both default to None and both are blank in `.env.example`, which is deliberate on both
    #: counts. M31.3.1.2 says every setting the application reads is documented in that file,
    #: so the names are there; the values are not, because a setup code shipped with a value
    #: is the same code on every install that copied the template and an instant shipped with
    #: one would date the window to whenever the release was cut. The installer appends the
    #: real pair to its own copy of that file, on the client's server, in one guarded step,
    #: and the appended line is the one a reader of the finished file gets.
    setup_secret: Annotated[SealedSecret | None, BeforeValidator(sealed_setup_secret)] = None
    setup_issued_at: datetime | None = None
    #: Where this install's secrets vault answers, and the token the application presents to
    #: it. Both empty, the default, is an install with no vault, which is every install until
    #: its owner runs one: `brain.ops.credentials` then keeps no credential and says so in
    #: words rather than falling back to a table. The token is kept out of `repr` for the
    #: reason `app_role_password` is. Read here and handed on, because nothing else reads the
    #: environment; see `brain.ops.credentials.credentials_at_start`.
    vault_address: str = ""
    vault_token: str = Field(default="", repr=False)

    def setup_enrolment(self) -> Enrolment | None:
        """The one enrolment this installation's environment file describes, or none.

        The join, from this end. `brain.setup_wizard` is handed an `Enrolment` on every screen
        and `brain.deployment.installer` writes a secret and an instant; this is the only
        thing that turns the second into the first, and until it existed the install path did
        not connect at all.

        A method rather than a field, because a field would be computed once when the settings
        object is built and would then be a value that could be constructed with any expiry
        somebody passed. Derived on each read, from two values that cannot change while the
        process runs, it is the same enrolment every time and is nobody's to set. See
        `brain.firstrun.THE_WINDOW_IS_DERIVED_SO_A_RESTART_CANNOT_MOVE_IT`.

        None means this install has no setup code, which is a development machine or an
        install whose first administrator was appointed long ago. A route reading None has to
        refuse the wizard rather than open it: there is no code to present, so there is
        nothing for a stranger to guess and nothing for the client to type either.
        """
        return derived_enrolment(self.setup_secret, issued_at=self.setup_issued_at)

    def resolved_commit(self) -> str:
        """Which commit this process is running, believing the image over the environment.

        The environment is not trustworthy for this, measured rather than assumed. On the
        live server the image carries `BRAIN_COMMIT_SHA=724cf3f` and the container was
        created with `BRAIN_COMMIT_SHA=unknown`: Coolify stores its own copy of the compose
        file, that copy resolved a `${COMMIT_SHA:-unknown}` default to the literal string
        at save time, and an explicit environment entry in compose beats an image's ENV.
        So `/health/live` answered "unknown" while the status page beside it reported the
        truth, and a deployment nobody could identify is a deployment nobody can roll back
        with confidence.

        Baking the value into the image was the previous fix for this and it was not
        enough, because compose can override anything the image sets. A file cannot be
        overridden by an environment variable, so the manifest wins: it is written by CI
        into the image immediately before the build, from the same git repository that
        produced the code.

        The environment is still preferred when it says something, because a developer
        running `BRAIN_COMMIT_SHA=wip` locally means it, and because the manifest is absent
        outside a built image. Only the specific value "unknown" - which is the default,
        the thing a variable says when nobody set it - falls through to the file.
        """
        if self.commit_sha and self.commit_sha != "unknown":
            return self.commit_sha
        try:
            from brain.ops.release_manifest import read_manifest

            manifest = read_manifest()
        except Exception:
            # A malformed manifest must not stop the process answering health checks. The
            # honest answer to "which commit is this" is then still "unknown", which is
            # what the caller already had.
            return self.commit_sha
        return manifest.commit[:7] if manifest else self.commit_sha


def process_environment() -> Mapping[str, str]:
    """This process's environment, for a caller holding a declared table of names of its own.

    The default behind every `env: Mapping[str, str] | None = None` parameter under
    `src/brain`, written once. A setting that is a field of `Settings` is read from `Settings`
    and not from this; see `NOTHING_ELSE_READS_THE_ENVIRONMENT`.
    """
    return os.environ


def writable_process_environment() -> MutableMapping[str, str]:
    """This process's environment, writable, for `brain.ops.provider_keys` alone.

    A vendor SDK reads its key from the environment and nowhere else, so the vault's copy has
    to be put there. Separate from `process_environment` so a reader cannot be handed a mapping
    it could write to by accident.
    """
    return os.environ


class _HandedEnvironment(EnvSettingsSource):
    """pydantic-settings' own environment source, reading a mapping instead of `os.environ`.

    The names, the prefix, the alias precedence and the case folding all stay pydantic's, which
    is the point: a caller handed a mapping gets the same answer `Settings()` gives for the same
    variables, rather than a second reading of the alias rule written out by hand.

    `_load_env_vars` is private to the library. `test_settings_from_a_mapping_ignores_the_process`
    is what notices if an upgrade renames it, because the failure would otherwise be silent: the
    override stops being called and the real environment is read instead.
    """

    def __init__(self, settings_cls: type[BaseSettings], handed: Mapping[str, str]) -> None:
        self._handed = handed
        super().__init__(settings_cls)

    def _load_env_vars(self) -> Mapping[str, str | None]:
        return parse_env_vars(
            self._handed,
            bool(self.case_sensitive),
            bool(self.env_ignore_empty),
            self.env_parse_none_str,
        )


def settings_from(env: Mapping[str, str]) -> Settings:
    """The settings a process with exactly this environment would read, and nothing else.

    For a command whose environment is a parameter so it can be tested at more than one
    setting, which is `brain.ops.worker` and `brain.deployment.database`. Constructing
    `Settings()` there instead would let a variable set on the machine running the test answer
    for one the test left out.
    """

    class Handed(Settings):
        @classmethod
        def settings_customise_sources(
            cls,
            settings_cls: type[BaseSettings],
            init_settings: PydanticBaseSettingsSource,
            env_settings: PydanticBaseSettingsSource,
            dotenv_settings: PydanticBaseSettingsSource,
            file_secret_settings: PydanticBaseSettingsSource,
        ) -> tuple[PydanticBaseSettingsSource, ...]:
            return (init_settings, _HandedEnvironment(settings_cls, env))

    return Handed()
