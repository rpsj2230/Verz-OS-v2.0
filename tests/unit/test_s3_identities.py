"""The object store's access file is edited one identity at a time, and never started over.

Two overlays write an identity into `/opt/brain/settings/seaweedfs/s3.json`: the object store's own
(the application's key) and the trace ledger's. The ledger's preparation used to write the whole
file from its one identity, which removed the application's key from the store the day the ledger
was switched on. `brain.ops.s3_identities.merge` is the rule that replaced it, and these tests are
about the rule itself; `test_overlays.py` runs the shell scripts that call it.

Every key and secret here is a made-up string of letters no generator produces, so a leak into an
error message is a failure that names itself.

Task ids: M32.3.1.1, M32.3.1.4, M32.1.1.1
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from brain.ops.s3_identities import (
    PLACEHOLDER_CREDENTIAL,
    Identity,
    S3IdentityError,
    main,
    merge,
    read_request,
)

REPO = Path(__file__).resolve().parents[2]

APP = Identity(
    "brain-application", "appkeyaaaaaaaaaa", "appsecretbbbbbbbbbbbbbbbb", ("Read", "Write")
)
LEDGER = Identity(
    "langfuse",
    "ledgerkeycccccccc",
    "ledgersecretdddddddddddd",
    ("Read:langfuse-events", "List:langfuse-events"),
)


def names(text: str) -> list[str]:
    return [one["name"] for one in json.loads(text)["identities"]]


def test_an_identity_is_added_to_a_file_that_does_not_exist_yet() -> None:
    """Nothing, or only whitespace, is an empty file and not an error: the first writer on a server
    meets exactly that. Delete this and the first deploy of the object store refuses to start for
    want of a file it was about to make."""
    for existing in ("", "  \n"):
        written = json.loads(merge(existing, APP))
        assert written["identities"] == [APP.entry()]


def test_a_second_writer_adds_its_identity_and_the_first_one_comes_back_as_it_went_in() -> None:
    """The defect itself: two overlays, one file. Whichever merges second, the file holds both and
    the first's key is the one it wrote. Delete this and the ledger can take the application's key
    away, which is the failure this module exists to end."""
    first = merge("", APP)
    both = merge(first, LEDGER)
    other_order = merge(merge("", LEDGER), APP)

    assert names(both) == ["brain-application", "langfuse"]
    assert json.loads(both)["identities"][0] == APP.entry()
    assert sorted(names(other_order)) == sorted(names(both))


def test_an_identity_of_the_same_name_is_replaced_in_its_place_and_never_duplicated() -> None:
    """A key rotated on the server, or the same merge run on every deploy, leaves one identity of
    that name at its old position with the new key. Delete this and every deploy appends another
    copy of the ledger's identity, and a rotated key leaves the old one valid beside the new."""
    rotated = Identity(
        "brain-application", "rotatedkeyeeeeeeee", "rotatedsecretffffffffffff", ("Read",)
    )
    once = merge(merge(merge("", APP), LEDGER), APP)
    replaced = merge(once, rotated)

    assert names(once) == ["brain-application", "langfuse"]
    assert merge(once, APP) == once
    assert names(replaced) == ["brain-application", "langfuse"]
    assert json.loads(replaced)["identities"][0] == rotated.entry()
    assert APP.access_key not in replaced


def test_what_the_merge_does_not_own_comes_back_untouched() -> None:
    """An identity an administrator added, with fields this module has never heard of, and a key at
    the top of the file, are returned as they were. Delete this and a merge becomes a rewrite that
    drops whatever it does not model, which is the same defect with a smaller blast radius."""
    existing = json.dumps(
        {
            "_comment": ["kept"],
            "identities": [
                {
                    "name": "by-hand",
                    "credentials": [
                        {"accessKey": "handkeygggggggg", "secretKey": "handsecrethhhhhhhhh"}
                    ],
                    "actions": ["Admin"],
                    "account": {"id": "x"},
                }
            ],
            "accounts": [{"id": "x"}],
        }
    )
    written = json.loads(merge(existing, LEDGER))

    assert written["_comment"] == ["kept"]
    assert written["accounts"] == [{"id": "x"}]
    assert written["identities"][0] == json.loads(existing)["identities"][0]
    assert written["identities"][1] == LEDGER.entry()


def test_the_repository_s_placeholder_identity_is_removed_when_anything_merges() -> None:
    """The shipped file's application identity holds a key anybody who has read this repository
    holds. A merge that kept every identity would carry it into a running store. Delete this and
    switching the ledger on, the one thing the old overwrite did well, becomes a way to open the
    store to a published key."""
    shipped = (REPO / "ops" / "seaweedfs" / "s3.json").read_text(encoding="utf-8")
    assert PLACEHOLDER_CREDENTIAL in shipped

    written = merge(shipped, LEDGER)

    assert PLACEHOLDER_CREDENTIAL not in written
    assert names(written) == ["langfuse"]
    assert "_comment" in json.loads(written)


def test_an_identity_with_a_real_key_is_not_taken_for_a_placeholder() -> None:
    """The positive half of the removal: only an identity whose every credential is the
    placeholder goes, and one that has any real credential stays. Delete this and the removal can
    become 'drop every identity that is not mine', which passes the test above."""
    mixed = json.dumps(
        {
            "identities": [
                {
                    "name": "half",
                    "credentials": [
                        {"accessKey": PLACEHOLDER_CREDENTIAL, "secretKey": PLACEHOLDER_CREDENTIAL},
                        {"accessKey": "realkeyiiiiiiiii", "secretKey": "realsecretjjjjjjjjjjjj"},
                    ],
                    "actions": ["Read"],
                }
            ]
        }
    )

    assert names(merge(mixed, LEDGER)) == ["half", "langfuse"]


@pytest.mark.parametrize(
    "existing",
    ['{"identities": [', "[]", '"text"', '{"identities": {"name": "x"}}', '{"identities": ["x"]}'],
    ids=["truncated", "a list", "a string", "identities an object", "an identity that is a string"],
)
def test_a_file_that_cannot_be_read_as_an_access_file_is_refused_and_never_started_over(
    existing: str,
) -> None:
    """Each shape is a file that may be the only record of who holds a key, and the answer to every
    one is a refusal, not an empty file. Delete this and unreadable quietly becomes empty, which is
    how the application's key was lost in the first place."""
    with pytest.raises(S3IdentityError, match="not changed"):
        merge(existing, LEDGER)


@pytest.mark.parametrize(
    "build",
    [
        lambda: Identity("", "keykeykeykey", "secretsecretsecret", ("Read",)),
        lambda: Identity("a b", "keykeykeykey", "secretsecretsecret", ("Read",)),
        lambda: Identity("ok", "short", "secretsecretsecret", ("Read",)),
        lambda: Identity("ok", "keykeykeykey", 'has"quote12345', ("Read",)),
        lambda: Identity("ok", "keykeykeykey", "secretsecretsecret", ()),
        lambda: Identity("ok", "keykeykeykey", "secretsecretsecret", (" Read",)),
    ],
    ids=[
        "no name",
        "name with a space",
        "short key",
        "quote in secret",
        "no actions",
        "padded action",
    ],
)
def test_an_identity_that_could_corrupt_the_file_or_grants_nothing_is_not_written(
    build: object,
) -> None:
    """The values are written into JSON by a shell, so one that could end a string, or an identity
    that may do nothing, is refused before any file is touched. Delete this and a malformed key
    reaches the store's access file as a syntax error the store reports at its next start."""
    with pytest.raises(S3IdentityError):
        build()  # type: ignore[operator]


def test_the_secret_is_not_in_the_identity_s_repr_or_in_a_refusal() -> None:
    """The identity can be printed by a traceback, and a refusal is printed by the script. Neither
    may carry the secret. Delete this and a key reaches the deploy journal."""
    assert LEDGER.secret_key not in repr(LEDGER)
    with pytest.raises(S3IdentityError) as caught:
        merge('{"identities": [', LEDGER)
    assert LEDGER.secret_key not in str(caught.value)


def request(identity: Identity, existing: str) -> str:
    """What the shell writes: the identity as one line of JSON, then the file."""
    head = json.dumps(
        {
            "name": identity.name,
            "access_key": identity.access_key,
            "secret_key": identity.secret_key,
            "actions": list(identity.actions),
        }
    )
    return head + "\n" + existing


def test_the_command_reads_the_identity_and_the_file_from_standard_input_and_writes_the_result(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The whole of what the shell runs, end to end: first line the identity, the rest the file,
    standard output the new file and nothing on standard error. Delete this and the shell and the
    module can disagree about the shape of the request, and every deploy reads it as a refusal."""
    existing = merge("", APP)
    monkeypatch.setattr("sys.stdin", io.StringIO(request(LEDGER, existing)))

    assert main(["merge"]) == 0

    seen = capsys.readouterr()
    assert seen.out == merge(existing, LEDGER)
    assert seen.err == ""


def test_the_command_refuses_with_a_sentence_and_nothing_on_standard_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A refusal writes nothing to standard output, so the shell's redirect would otherwise replace
    the file with an empty one if it ignored the exit code, and says why on standard error without
    the secret. Delete this and a refusal leaves a half-written file or a leaked key."""
    monkeypatch.setattr("sys.stdin", io.StringIO(request(LEDGER, '{"identities": [')))

    assert main(["merge"]) == 1

    seen = capsys.readouterr()
    assert seen.out == ""
    assert "was not changed" in seen.err
    assert LEDGER.secret_key not in seen.err


@pytest.mark.parametrize(
    "text",
    [
        "not json\n{}",
        '{"name": "x"}\n{}',
        '{"name": "x", "access_key": "keykeykeykey", "secret_key": "secretsecretsecret",'
        ' "actions": "Read"}\n',
        "[]\n{}",
    ],
    ids=["not json", "no key pair", "actions a string", "not an object"],
)
def test_a_request_that_is_not_an_identity_is_refused(text: str) -> None:
    """The first line is the only thing the shell controls, so every way it can be wrong is a
    refusal. Delete this and a request missing its secret is written as an identity with none."""
    with pytest.raises(S3IdentityError):
        read_request(text)


def test_the_command_takes_one_argument_and_says_what_it_takes_otherwise(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Delete this and a typo in the shell script runs the module with no verb and reads standard
    input as an identity anyway."""
    assert main([]) == 64
    assert main(["merge", "extra"]) == 64
    assert "usage" in capsys.readouterr().err
