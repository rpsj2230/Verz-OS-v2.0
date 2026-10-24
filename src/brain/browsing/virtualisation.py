"""Whether the host a browser run lands on offers kernel virtualisation, said next to gVisor.

A browser run is isolated by gVisor, which answers a page's system calls in a user-space kernel.
gVisor can run on three platforms, and one of them is KVM, which uses the host's hardware
virtualisation to keep that kernel out of the host's own: a stronger boundary and a faster one,
and available only where the host has `/dev/kvm`. Many hosts do not: a virtual machine without
nested virtualisation, a laptop, a cloud instance of the wrong family. Nothing in the product
required it and nothing told the person installing it which they had, so `launcher --check` said
`runsc` was registered and stopped, and an administrator read "gVisor" as one thing on every host.

**It reports and never refuses.** Isolation by gVisor is the product's claim on every host and
is held by `brain.browsing.sandbox`; KVM changes how strong the second boundary is. A refusal
here would turn an installable host into an uninstallable one over a property that was not
promised. The one exception is a configuration that cannot work: gVisor set to use KVM on a host
where `/dev/kvm` is not usable would fail at the first run, and that is called what it is.

**What is read is what the launcher can see.** `/dev/kvm` as seen from the launcher's own
filesystem, and the arguments the Docker daemon says it registered `runsc` with. A launcher in a
container that was not given `/dev/kvm` reports it unavailable on a host that has it, which is
the more cautious wrong answer, and the sentence for that state says to check the host.

Task ids: M42.7.1
"""

from __future__ import annotations

import enum
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

#: Where the kernel offers hardware virtualisation to a process that may use it.
KVM_DEVICE: Final = "/dev/kvm"

#: The runtime gVisor registers as. Restated rather than imported so this module stands alone.
RUNSC: Final = "runsc"


class State(enum.StrEnum):
    """The four things a host can be, for the launcher's answer and for the install check."""

    #: gVisor is set to run on KVM and the device is usable here.
    KVM_IN_USE = "kvm_in_use"
    #: The device is usable here and gVisor is not set to use it.
    KVM_AVAILABLE_NOT_USED = "kvm_available_not_used"
    #: No usable device here and gVisor is not set to use it. Isolation is gVisor's, without KVM.
    KVM_UNAVAILABLE = "kvm_unavailable"
    #: gVisor is set to use KVM and the device is not usable here, so a run would fail.
    KVM_REQUIRED_BUT_UNAVAILABLE = "kvm_required_but_unavailable"
    #: gVisor is not registered with the daemon, so nothing can be said about its platform.
    NO_GVISOR = "no_gvisor"


#: Every state's name, for the launcher's answer to be held to by a reader of it.
STATES: Final = tuple(one.value for one in State)

SENTENCES: Final[Mapping[State, str]] = {
    State.KVM_IN_USE: (
        "kernel virtualisation: gVisor runs on KVM and /dev/kvm is usable, so a page's system "
        "calls are answered by a kernel that hardware virtualisation keeps apart from the host's"
    ),
    State.KVM_AVAILABLE_NOT_USED: (
        "kernel virtualisation: /dev/kvm is usable here and gVisor is not set to use it. "
        "Isolation is gVisor's user-space kernel; setting its platform to kvm adds the hardware "
        "boundary"
    ),
    State.KVM_UNAVAILABLE: (
        "kernel virtualisation: /dev/kvm is not usable from this launcher, so gVisor runs without "
        "KVM. Isolation is still gVisor's user-space kernel. If the host does have /dev/kvm, "
        "this launcher was not given it"
    ),
    State.KVM_REQUIRED_BUT_UNAVAILABLE: (
        "kernel virtualisation: gVisor is set to use KVM and /dev/kvm is not usable from this "
        "launcher, so every run would fail to start. Give the launcher /dev/kvm or set gVisor's "
        "platform to something that does not need it"
    ),
    State.NO_GVISOR: (
        "kernel virtualisation: not known, because gVisor is not registered with this daemon"
    ),
}


@dataclass(frozen=True)
class Virtualisation:
    """What the host offers and what gVisor is set to, in one state and one sentence."""

    state: State
    sentence: str


def wants_kvm(arguments: Sequence[str]) -> bool:
    """Whether `runsc` was registered with a platform of KVM, in either spelling Docker takes."""
    for index, one in enumerate(arguments):
        if one == "--platform=kvm":
            return True
        if one == "--platform" and index + 1 < len(arguments) and arguments[index + 1] == "kvm":
            return True
    return False


def kvm_usable(
    *,
    exists: Callable[[str], bool] = os.path.exists,
    access: Callable[[str, int], bool] = os.access,
) -> bool:
    """Whether this process can open `/dev/kvm` for reading and writing, which KVM needs."""
    return exists(KVM_DEVICE) and access(KVM_DEVICE, os.R_OK | os.W_OK)


def report_for(runtime_arguments: Sequence[str] | None, *, usable: bool) -> Virtualisation:
    """The state of this host. `runtime_arguments` is None when `runsc` is not registered."""
    if runtime_arguments is None:
        state = State.NO_GVISOR
    elif wants_kvm(runtime_arguments):
        state = State.KVM_IN_USE if usable else State.KVM_REQUIRED_BUT_UNAVAILABLE
    else:
        state = State.KVM_AVAILABLE_NOT_USED if usable else State.KVM_UNAVAILABLE
    return Virtualisation(state=state, sentence=SENTENCES[state])


def arguments_of(info: Mapping[str, object]) -> Sequence[str] | None:
    """The arguments `runsc` was registered with, out of the daemon's `/info`, or None."""
    runtimes = info.get("Runtimes")
    if not isinstance(runtimes, Mapping) or RUNSC not in runtimes:
        return None
    registered = runtimes[RUNSC]
    given = registered.get("runtimeArgs") if isinstance(registered, Mapping) else None
    if not isinstance(given, list):
        return ()
    return tuple(str(one) for one in given)
