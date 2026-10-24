"""Whether the host offers kernel virtualisation, said next to gVisor by `launcher --check`.

Task ids: M42.7.1
"""

from __future__ import annotations

import os
from collections.abc import Mapping

import pytest

from brain.browsing import launcher as launcher_module
from brain.browsing.virtualisation import (
    SENTENCES,
    STATES,
    State,
    arguments_of,
    kvm_usable,
    report_for,
    wants_kvm,
)


@pytest.mark.parametrize(
    ("arguments", "usable", "state"),
    [
        (("--platform=kvm",), True, State.KVM_IN_USE),
        (("--platform=kvm",), False, State.KVM_REQUIRED_BUT_UNAVAILABLE),
        (("--platform", "kvm"), True, State.KVM_IN_USE),
        ((), True, State.KVM_AVAILABLE_NOT_USED),
        (("--platform=systrap",), True, State.KVM_AVAILABLE_NOT_USED),
        ((), False, State.KVM_UNAVAILABLE),
        (("--platform=ptrace",), False, State.KVM_UNAVAILABLE),
        (None, True, State.NO_GVISOR),
        (None, False, State.NO_GVISOR),
    ],
)
def test_a_host_is_one_of_five_states_by_what_gvisor_is_set_to_and_what_the_device_allows(
    arguments: tuple[str, ...] | None, usable: bool, state: State
) -> None:
    """Delete this and a host that has KVM and does not use it reads the same as one that cannot,
    and gVisor set to a platform the host cannot give reads as healthy."""
    report = report_for(arguments, usable=usable)

    assert report.state is state
    assert report.sentence == SENTENCES[state]
    assert report.sentence.startswith("kernel virtualisation:")


def test_every_state_has_a_sentence_and_a_name_the_launcher_can_send() -> None:
    """Delete this and a state added without words goes out as a blank line, or the launcher sends
    a name the install check does not know."""
    assert set(SENTENCES) == set(State)
    assert tuple(one.value for one in State) == STATES
    assert len({SENTENCES[one] for one in State}) == len(State)


def test_only_a_platform_of_kvm_counts_as_kvm() -> None:
    """The two spellings Docker takes, and nothing that merely contains the letters. Delete this and
    `--platform=kvm-ish` or a flag named `kvm` turns the report on."""
    assert wants_kvm(("--platform=kvm",)) and wants_kvm(("--debug", "--platform", "kvm"))
    assert not wants_kvm(("--platform=kvm-ish", "--kvm", "kvm"))
    assert not wants_kvm(("--platform",))


def test_the_arguments_gvisor_was_registered_with_are_read_out_of_the_daemons_info() -> None:
    """Delete this and the report reads the wrong runtime's arguments, or crashes on a daemon that
    registered `runsc` with none."""
    info = {"Runtimes": {"runc": {"path": "runc"}, "runsc": {"runtimeArgs": ["--platform=kvm"]}}}

    assert arguments_of(info) == ("--platform=kvm",)
    assert arguments_of({"Runtimes": {"runsc": {"path": "runsc"}}}) == ()
    assert arguments_of({"Runtimes": {"runc": {}}}) is None
    assert arguments_of({}) is None
    assert arguments_of({"Runtimes": "broken"}) is None


def test_the_device_is_usable_only_when_it_exists_and_can_be_read_and_written() -> None:
    """Delete this and a device a process may not open counts as KVM, which is the case that makes
    every run fail to start."""
    both = os.R_OK | os.W_OK

    assert kvm_usable(exists=lambda path: True, access=lambda path, mode: mode == both)
    assert not kvm_usable(exists=lambda path: False, access=lambda path, mode: True)
    assert not kvm_usable(exists=lambda path: True, access=lambda path, mode: False)
    assert not kvm_usable(exists=lambda path: True, access=lambda path, mode: mode == os.R_OK)


class _Daemon:
    def __init__(self, info: Mapping[str, object]) -> None:
        self._info = info

    def runtimes(self) -> tuple[str, ...]:
        return tuple(sorted(self._info.get("Runtimes", {})))  # type: ignore[call-overload]

    def info(self) -> Mapping[str, object]:
        return self._info


def _check(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    info: Mapping[str, object],
    *,
    usable: bool,
) -> tuple[int, str]:
    monkeypatch.setattr(
        launcher_module.DockerEngine, "over", classmethod(lambda cls: _Daemon(info))
    )
    monkeypatch.setattr(launcher_module, "kvm_usable", lambda: usable)
    code = launcher_module.main(["--app-image", "app:x", "--check"])
    return code, capsys.readouterr().out


def test_check_says_what_the_host_offers_beside_gvisor_and_passes_without_kvm(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Delete this and `--check` goes back to saying gVisor is registered and nothing about the
    kernel under it, or fails a host for lacking a property the product never required."""
    code, said = _check(monkeypatch, capsys, {"Runtimes": {"runsc": {}}}, usable=False)

    assert code == 0
    assert SENTENCES[State.KVM_UNAVAILABLE] in said


def test_check_fails_for_gvisor_set_to_kvm_on_a_host_without_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Delete this and a launcher whose every run would fail to start passes its own check."""
    info = {"Runtimes": {"runsc": {"runtimeArgs": ["--platform=kvm"]}}}
    code, said = _check(monkeypatch, capsys, info, usable=False)

    assert code == 1
    assert SENTENCES[State.KVM_REQUIRED_BUT_UNAVAILABLE] in said


def test_check_still_fails_without_gvisor_and_says_so_beside_the_virtualisation(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Delete this and the original refusal for a missing runtime is lost when the new line is
    added."""
    code, said = _check(monkeypatch, capsys, {"Runtimes": {"runc": {}}}, usable=True)

    assert code == 1
    assert "no runsc runtime" in said
    assert SENTENCES[State.NO_GVISOR] in said
