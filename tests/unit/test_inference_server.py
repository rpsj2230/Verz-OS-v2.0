"""The model server's own program: one part at a time, ended when idle, measured, and honest.

The supervisor is judged with a part that is a stand-in and a clock and a meter that are handed in,
because the cases that matter (a part that dies, a host with no room, a request that arrives while
another is served, a part that has been idle for exactly the idle time) cannot be reached through a
real model and a real wait. One test runs a real child process and one runs a real HTTP server, so
that the framing and the sockets are exercised as well as the logic.

**Names are held equal across the two programs.** The application and this one are built and
deployed apart, so the paths, the report's keys, the part names and the environment variables are
each spelled in both, and one test per spelling reads both and compares them. Without those a
renamed path is a 404 that the application reads as its own fault and does not retry.

Task ids: M7.2.1, M7.3.3
"""

from __future__ import annotations

import ast
import hashlib
import http.client
import io
import json
import shutil
import sys
import threading
from collections.abc import Callable
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from brain.ops import model_server as product
from inference_server import admit, config, fetch, framing, gateway, meter, supervisor, worker
from inference_server.parts import NEEDS, readiness_gaps

REPO = Path(__file__).resolve().parents[2]
PACKAGE = REPO / "src" / "inference_server"


def environment(**changed: str) -> dict[str, str]:
    """What the compose file hands the container for the default choice, with `changed` over it."""
    base = dict(product.environment(product.config_from()))
    base.update(
        {
            "INFERENCE_REQUESTS_AT_ONCE": "1",
            "INFERENCE_MODEL_DIR": "/models",
            "INFERENCE_EMBEDDING_MODEL": "qwen3-embedding-0.6b",
            "INFERENCE_EMBEDDING_FILE": "Qwen3-Embedding-0.6B-Q8_0.gguf",
            "OMP_NUM_THREADS": "2",
        }
    )
    base.update(changed)
    return base


def server_config(**changed: str) -> config.ServerConfig:
    return config.from_environment(environment(**changed))


# ------------------------------------------------------------------ the two programs agree
def test_this_package_imports_nothing_from_the_application() -> None:
    """The image carries this package and not the application, which is the permission boundary as
    a fact of the image: a process that holds a client's document has no code to reach the
    application's database with. An import of `brain` would also make the image fail to start.

    Parsed rather than grepped, so a word in a docstring is not an import and an import under an
    `if` is found. Delete this and the first convenient import takes the boundary away."""
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            offenders += [f"{path.name}: {n}" for n in names if n.split(".")[0] == "brain"]

    assert offenders == []
    assert list(PACKAGE.rglob("*.py")), "the scan found nothing to scan"


def test_the_part_names_and_the_paths_are_spelled_the_same_in_both_programs() -> None:
    """A path spelled differently on the two sides is a 404, which `classify` reads as this
    system having sent something malformed, and which is never retried.

    Delete this and a renamed route is a document that is never read and an error nobody can
    place."""
    assert tuple(one.value for one in product.Part) == config.PARTS
    assert {part: path for path, part in gateway.ROUTES.items()} == {
        one.value: path for one, path in product.PATH_OF_PART.items()
    }
    assert set(NEEDS) == set(config.PARTS)


def test_the_environment_the_application_writes_is_exactly_the_one_this_program_reads() -> None:
    """Each variable the product's `environment` writes is read by `from_environment`, and the
    per-part need names are the ones `need_variable` builds.

    Delete this and a renamed variable starts a container that refuses its own configuration."""
    written = dict(product.environment(product.config_from(parts="embedding,layout")))
    read = server_config(**written)

    assert read.parts == ("embedding", "layout")
    assert read.memory_mib == int(written["INFERENCE_MEMORY_MIB"])
    assert read.max_request_bytes == int(written["INFERENCE_MAX_REQUEST_BYTES"])
    assert read.needs_mib == {
        "embedding": int(written[config.need_variable("embedding")]),
        "layout": int(written[config.need_variable("layout")]),
    }
    assert config.need_variable("embedding") in written


def test_the_report_keys_are_spelled_the_same_in_both_programs() -> None:
    """Held in `test_model_server_peaks` from the application's side; held here from this one's,
    so a rename on either side fails a test in the program that did it.

    Delete this and the server's report stops matching the reader without this file noticing."""
    from brain.ops.model_server_peaks import REPORT_FIELDS, REPORT_KEY

    assert meter.REPORT_KEY == REPORT_KEY
    assert meter.REPORT_FIELDS == REPORT_FIELDS
    produced = meter.report(
        model="m",
        items=1,
        request_bytes=2,
        measured=meter.Measurement(3, 4, 5, 6),
        duration_ms=6,
    )
    assert produced is not None and set(produced) == set(REPORT_FIELDS)


# ------------------------------------------------------------------ configuration
def test_a_configuration_the_compose_file_hands_over_is_read_in_full() -> None:
    """The positive case for the reader, so a reader that refuses everything is caught.

    Delete this and every refusal test below is satisfied by a function that always raises."""
    read = server_config()

    assert read.parts == ("embedding",)
    assert read.idle_seconds == 300 and read.upload_mb == 25
    assert read.requests_at_once == 1
    assert read.model_dir == Path("/models")


@pytest.mark.parametrize(
    "broken",
    [
        {"INFERENCE_PARTS": ""},
        {"INFERENCE_PARTS": "embedding,translation"},
        {"INFERENCE_PARTS": "ocr,ocr"},
        {"INFERENCE_IDLE_SECONDS": "never"},
        {"INFERENCE_IDLE_SECONDS": "0"},
        {"INFERENCE_MEMORY_MIB": ""},
        {"INFERENCE_NEED_EMBEDDING_MIB": "0"},
    ],
    ids=repr,
)
def test_a_container_started_with_something_it_cannot_run_on_says_so_and_does_not_guess(
    broken: dict[str, str],
) -> None:
    """A server that started on a half-read configuration would answer, and be wrong in a way the
    application cannot see. Every variable it needs is asked for, and the refusal says which.

    Delete this and a missing figure is a default nobody chose."""
    with pytest.raises(config.ConfigError):
        server_config(**broken)


# ------------------------------------------------------------------ the meter
def _cgroup(root: Path, files: dict[str, str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root


def test_the_meter_reads_anonymous_and_file_memory_apart_from_a_version_two_cgroup(
    tmp_path: Path,
) -> None:
    """Shared memory is anonymous (it is charged as cache and cannot be given back without swap),
    and what is left of the file figure is cache the kernel can take back. Both are the cgroup's own
    bytes, so the children of a part and a JVM beside it are counted.

    Delete this and the two kinds are one number, and the owner's server looks full by exactly the
    weights it would hand over."""
    root = _cgroup(
        tmp_path,
        {
            "memory.stat": "anon 1000\nfile 5000\nshmem 400\nkernel 7\n",
            "memory.max": "1073741824\n",
        },
    )

    sample = meter.read_sample(root)

    assert sample == meter.Sample(anon=1400, file=4600, limit=1073741824)


def test_a_version_two_cgroup_with_no_limit_is_a_sample_with_none(tmp_path: Path) -> None:
    """The kernel writes `max` for no limit; that is not a number and not a limit of zero.

    Delete this and an unlimited container is reported as limited to nothing."""
    root = _cgroup(tmp_path, {"memory.stat": "anon 10\nfile 20\n", "memory.max": "max\n"})

    assert meter.read_sample(root) == meter.Sample(anon=10, file=20, limit=None)


def test_a_version_one_cgroup_is_read_and_its_no_limit_number_is_no_limit(tmp_path: Path) -> None:
    """Version 1 writes no limit as a number near two to the sixty-third, which is not a limit
    anybody set. Delete this and an install on the older layout reports an exabyte limit."""
    root = _cgroup(
        tmp_path,
        {
            "memory/memory.stat": "rss 700\ncache 900\nshmem 100\n",
            "memory/memory.limit_in_bytes": "9223372036854771712\n",
        },
    )

    assert meter.read_sample(root) == meter.Sample(anon=800, file=800, limit=None)


def test_no_cgroup_is_no_measurement_and_a_report_of_none(tmp_path: Path) -> None:
    """A developer's machine and a test have no cgroup; the answer carries no figures and not
    zeros, because a recorded zero would pull a suggested limit down on a machine nobody could
    read. Delete this and an unreadable host writes zeros into the table the limit is tuned from."""
    assert meter.read_sample(tmp_path / "nowhere") is None
    sampler = meter.Meter(read=lambda: None, interval=0.001)
    sampler.start()
    assert sampler.stop() is None
    assert meter.report(model="m", items=1, request_bytes=1, measured=None, duration_ms=1) is None


def test_the_meter_keeps_the_largest_figure_it_saw_and_rounds_up() -> None:
    """The peak is the largest sample of each kind, in whole mebibytes rounded up, and the limit is
    the last one read. A spike that is not the last sample must still be the figure.

    Delete this and the figure is the last reading, the memory the request had given back."""
    mib = 1024 * 1024
    samples = iter(
        [
            meter.Sample(10 * mib, 5 * mib, 100 * mib),
            meter.Sample(30 * mib + 1, 9 * mib, 100 * mib),
            meter.Sample(12 * mib, 2 * mib, 100 * mib),
        ]
    )
    last = meter.Sample(1 * mib, 1 * mib, 100 * mib)
    sampler = meter.Meter(read=lambda: next(samples, last), interval=3600.0)

    sampler.start()  # the first sample
    sampler._take()  # the spike, which is neither the first reading nor the last
    measured = sampler.stop()  # the last sample, after the request gave the memory back

    assert measured is not None
    assert measured.cgroup_limit_mib == 100
    assert measured.anon_peak_mib == 31  # 30 MiB and a byte, rounded up
    assert measured.cache_peak_mib == 9


# ------------------------------------------------------------------ admission
def test_a_host_with_room_admits_a_part_and_one_without_refuses_it_in_words(
    tmp_path: Path,
) -> None:
    """Both sides of the line, at the line: exactly the need plus the reserve is admitted and a
    mebibyte under is not. The sentence says what was short and that nothing was loaded.

    Delete this and a part is loaded onto a host that cannot hold it, and the kernel's killer
    chooses what to end."""
    need = 416
    edge = need + admit.RESERVE_MIB

    assert admit.admit("embedding", need_mib=need, available_mib=edge).admitted
    refused = admit.admit("embedding", need_mib=need, available_mib=edge - 1)
    assert not refused.admitted
    assert "embedding" in refused.words and "Nothing was loaded" in refused.words


def test_an_unreadable_host_is_admitted_and_says_it_was_not_judged(tmp_path: Path) -> None:
    """Refusing everything where `/proc/meminfo` cannot be read would be a server that is down for
    a reason nobody can see; the cgroup limit is still the backstop.

    Delete this and a developer's machine or a test host serves nothing."""
    decision = admit.admit("embedding", need_mib=10_000, available_mib=None)

    assert decision.admitted and "not judged" in decision.words
    assert admit.mem_available_mib(tmp_path / "missing") is None


def test_available_memory_is_read_in_mebibytes_from_the_kernels_own_line(tmp_path: Path) -> None:
    """`MemAvailable` counts the cache the kernel would hand back, which is the point. Delete this
    and the figure read is `MemFree`, which calls the owner's server full."""
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal: 12247040 kB\nMemFree: 100 kB\nMemAvailable: 7628800 kB\n")

    assert admit.mem_available_mib(meminfo) == 7450


# ------------------------------------------------------------------ framing
def test_a_frame_survives_a_round_trip_whatever_it_holds() -> None:
    """Any bytes and any length, including empty and including a body that looks like a header.

    Delete this and the protocol between the supervisor and a part corrupts a document that
    happens to contain the wrong eight bytes."""
    stream = io.BytesIO()
    bodies = [b"", b"\x00" * 8, b"x" * 100_000, json.dumps({"a": 1}).encode()]
    for body in bodies:
        framing.write_frame(stream, body)
    stream.seek(0)

    assert [framing.read_frame(stream, ceiling=1 << 20) for _ in bodies] == bodies
    assert framing.read_frame(stream, ceiling=1 << 20) is None


def test_a_frame_over_the_ceiling_or_cut_short_is_refused_and_never_taken_for_an_answer() -> None:
    """A part that wrote a length it did not mean cannot make the supervisor allocate for it, and a
    stream that ends inside a frame is a part that died with something half said.

    Delete this and a fragment is an answer."""
    stream = io.BytesIO()
    framing.write_frame(stream, b"x" * 100)
    stream.seek(0)
    with pytest.raises(framing.FrameError, match="over the ceiling"):
        framing.read_frame(stream, ceiling=10)
    # At the line from both sides: a frame of exactly the ceiling is read, one byte more is not.
    stream.seek(0)
    assert framing.read_frame(stream, ceiling=100) == b"x" * 100
    stream.seek(0)
    with pytest.raises(framing.FrameError, match="over the ceiling"):
        framing.read_frame(stream, ceiling=99)

    whole = io.BytesIO()
    framing.write_frame(whole, b"x" * 100)
    cut = io.BytesIO(whole.getvalue()[:50])
    with pytest.raises(framing.FrameError, match="still due"):
        framing.read_frame(cut, ceiling=1 << 20)
    with pytest.raises(framing.FrameError):
        framing.read_frame(io.BytesIO(b"\x00\x00\x00"), ceiling=1 << 20)


# ------------------------------------------------------------------ readiness
def test_readiness_lists_what_a_part_lacks_and_loads_nothing(tmp_path: Path) -> None:
    """Four absences in the order a person fixing them would meet them: the part's module, its
    libraries, its programs, its weights. A part not in this image is a gap, never a crash, and
    nothing is loaded to find out.

    Delete this and the health check is a TCP connect, which is liveness wearing readiness'
    clothes."""
    gaps = readiness_gaps(server_config(INFERENCE_MODEL_DIR=str(tmp_path)))

    assert any("embedding part" in one for one in gaps)
    # Whatever is reported names the part and the thing missing, in words.
    assert all("embedding" in one for one in gaps)


def test_a_part_with_everything_it_needs_has_no_gaps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The positive case, with the module, the library and the weights all present. Delete this and
    a readiness check that always says no passes every test above.

    Asserted by making the three things true, not by patching the answer."""
    from inference_server import parts

    (tmp_path / "Qwen3-Embedding-0.6B-Q8_0.gguf").write_bytes(b"weights")
    monkeypatch.setattr(parts, "_importable", lambda name: True)

    assert readiness_gaps(server_config(INFERENCE_MODEL_DIR=str(tmp_path))) == ()


def test_a_missing_program_and_missing_weights_are_each_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each absence is its own sentence, so the person fixing it knows which. Programs are looked
    for on the path and weights on the volume.

    Delete this and one of the two is reported as the other."""
    from inference_server import parts

    monkeypatch.setattr(parts, "_importable", lambda name: True)
    monkeypatch.setattr(shutil, "which", lambda name: None)
    gaps = readiness_gaps(server_config(INFERENCE_PARTS="tika", INFERENCE_MODEL_DIR=str(tmp_path)))

    assert any("needs the program java" in one for one in gaps)
    assert any("weights are not at" in one for one in gaps)


# ------------------------------------------------------------------ the supervisor
class FakePart:
    """A part that is a stand-in: it records what happened to it and answers what it is told to."""

    def __init__(self, name: str, log: list[str], *, fail_on_start: bool = False) -> None:
        self.name = name
        self.log = log
        self.fail_on_start = fail_on_start
        self.calls = 0
        self.dies = False
        self.status = 200

    def start(self) -> str:
        self.log.append(f"start {self.name}")
        if self.fail_on_start:
            raise supervisor.PartFailed("it would not load")
        return f"{self.name}@rev:1"

    def call(self, body: bytes) -> bytes:
        self.calls += 1
        if self.dies:
            raise supervisor.PartFailed("it ended while it worked")
        envelope = {"status": self.status, "answer": {"echo": len(body)}, "items": 3}
        return json.dumps(envelope).encode()

    def stop(self) -> None:
        self.log.append(f"stop {self.name}")


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class FakeMeter:
    def start(self) -> None:
        pass

    def stop(self) -> meter.Measurement:
        return meter.Measurement(
            anon_peak_mib=400, cache_peak_mib=650, cgroup_limit_mib=1088, duration_ms=12
        )


def built(
    parts: str = "embedding,layout",
    *,
    available: int | None = 100_000,
    **changed: str,
) -> tuple[supervisor.Supervisor, list[str], Clock, dict[str, FakePart]]:
    log: list[str] = []
    clock = Clock()
    made: dict[str, FakePart] = {}

    def spawn(part: str) -> FakePart:
        made[part] = FakePart(part, log)
        return made[part]

    unit = supervisor.Supervisor(
        server_config(INFERENCE_PARTS=parts, **changed),
        spawn=spawn,
        clock=clock,
        available=lambda: available,
        meter=FakeMeter,  # type: ignore[arg-type]
    )
    return unit, log, clock, made


def test_a_request_loads_its_part_serves_it_and_adds_what_was_measured() -> None:
    """The whole path: the part is started, the request goes to it, and the answer comes back with
    the memory block the supervisor measured and the model the part named. The answer is the part's
    own and nothing else of it is changed.

    Delete this and the application never sees a figure, so nothing is ever tuned."""
    unit, log, _, _ = built()

    reply = unit.handle("embedding", b"x" * 7)
    body = json.loads(reply.body)

    assert reply.status == 200 and body["echo"] == 7
    assert body["memory"] == {
        "model": "embedding@rev:1",
        "items": 3,
        "request_bytes": 7,
        "duration_ms": 12,
        "anon_peak_mib": 400,
        "cache_peak_mib": 650,
        "cgroup_limit_mib": 1088,
    }
    assert log == ["start embedding"] and unit.loaded == "embedding"


def test_asking_for_another_part_ends_the_loaded_one_first_so_one_is_resident_at_a_time() -> None:
    """The memory design in one assertion: the second part is never started while the first is
    alive. The order in the log is the property, because two starts before a stop is the sum.

    Delete this and the container holds both, the 3,072 MiB item 120 found would not fit."""
    unit, log, _, _ = built()

    unit.handle("embedding", b"a")
    unit.handle("layout", b"b")
    unit.handle("embedding", b"c")

    assert log == [
        "start embedding",
        "stop embedding",
        "start layout",
        "stop layout",
        "start embedding",
    ]


def test_a_second_request_for_the_loaded_part_does_not_load_it_again() -> None:
    """A model load is the expensive thing and the point of keeping a part for its idle time.

    Delete this and every request reloads the weights."""
    unit, log, _, made = built()

    unit.handle("embedding", b"a")
    unit.handle("embedding", b"b")

    assert log == ["start embedding"] and made["embedding"].calls == 2


def test_a_part_idle_for_the_whole_idle_time_is_ended_and_one_a_second_short_is_not() -> None:
    """At the line, both sides: the boundary is the idle time itself. Ending it returns its memory
    to the kernel, which is the only way an idle server holds nothing but its base.

    Delete this and a part stays loaded for ever, or is ended in the middle of a burst."""
    unit, log, clock, _ = built(INFERENCE_IDLE_SECONDS="300")
    unit.handle("embedding", b"a")

    def loaded() -> str | None:
        return unit.loaded

    clock.now += 299.0
    assert unit.reap() is None
    assert loaded() == "embedding"
    clock.now += 1.0
    assert unit.reap() == "embedding"
    assert loaded() is None and log[-1] == "stop embedding"
    assert unit.reap() is None, "nothing loaded is nothing to end"


def test_a_part_serving_a_request_is_never_reaped_from_under_it() -> None:
    """The lock is tried without waiting, so an idle check cannot end a part that a request holds
    the lock for. Delete this and a long document is cut off by the clock."""
    unit, _, clock, _ = built(INFERENCE_IDLE_SECONDS="30")
    unit.handle("embedding", b"a")
    clock.now += 10_000.0

    with unit._lock:  # the request in flight
        assert unit.reap() is None
    assert unit.loaded == "embedding"


def test_a_part_the_install_did_not_choose_is_not_found_and_is_never_started() -> None:
    """A 404 and not a 4xx the application would read as its own fault and stop sending: the part
    is simply not run here. Nothing is started to find out.

    Delete this and a request for a part nobody costed loads memory nobody budgeted."""
    unit, log, _, _ = built(parts="embedding")

    reply = unit.handle("layout", b"x")

    assert reply.status == 404 and log == []


def test_a_host_without_room_refuses_in_words_and_nothing_is_started() -> None:
    """The admission check from outside: with too little available, the answer is a 503 the
    application classifies as an outage and retries, the sentence says what was short, and no
    process was started.

    Delete this and a part is loaded onto a host that cannot hold it."""
    unit, log, _, _ = built(available=100)

    reply = unit.handle("embedding", b"x")

    assert reply.status == 503
    assert "cannot give" in json.loads(reply.body)["refusal"]
    assert log == [] and unit.loaded is None


def test_a_part_that_will_not_load_is_an_outage_and_leaves_nothing_loaded() -> None:
    """A load that fails is the supervisor's to report as unavailable, not a fact about the file,
    and the stand-in is stopped so no half-loaded process is left holding memory.

    Delete this and a part that cannot load leaves a process behind."""
    log: list[str] = []
    unit = supervisor.Supervisor(
        server_config(),
        spawn=lambda part: FakePart(part, log, fail_on_start=True),
        available=lambda: 100_000,
    )

    reply = unit.handle("embedding", b"x")

    assert reply.status == 503 and unit.loaded is None
    assert log == ["start embedding", "stop embedding"]


def test_a_part_that_dies_while_it_works_is_ended_and_the_request_is_an_outage() -> None:
    """The out-of-memory kill: the part's process ends and the supervisor does not. The request is
    answered 503 so the work waits in its queue, and the dead part is not kept as the loaded one.

    Delete this and the next request is sent to a process that is gone."""
    unit, log, _, made = built()
    unit.handle("embedding", b"a")
    made["embedding"].dies = True

    reply = unit.handle("embedding", b"b")

    assert reply.status == 503 and unit.loaded is None
    assert log[-1] == "stop embedding"


def test_a_request_that_waits_longer_than_the_queue_allows_is_told_to_come_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One request is served at a time. A second is told busy after a bounded wait, as a 503, so
    it is retried from the queue instead of holding a connection for the length of a long parse.

    Delete this and requests pile up on the lock without limit."""
    monkeypatch.setattr(supervisor, "QUEUE_WAIT_SECONDS", 0.05)
    unit, log, _, _ = built()

    with unit._lock:
        reply = unit.handle("embedding", b"x")

    assert reply.status == 503 and "busy" in json.loads(reply.body)["refusal"]
    assert log == []


def test_a_refusal_the_part_makes_carries_no_memory_block() -> None:
    """The block describes work that was done; a refusal did none. Recording a peak for it would
    fill the ring with the cost of saying no.

    Delete this and every refused document writes a row."""
    unit, _, _, made = built()
    unit.handle("embedding", b"a")
    made["embedding"].status = 503

    reply = unit.handle("embedding", b"b")

    assert reply.status == 503 and "memory" not in json.loads(reply.body)


def test_an_answer_nobody_can_read_is_an_outage_and_not_a_fact_about_the_document() -> None:
    """A part that sent something that is not an envelope is this side being wrong, which the
    application reads as `PARSER_UNAVAILABLE` and retries. Delete this and a garbled answer raises
    inside the request thread."""
    unit, _, _, made = built()
    unit.handle("embedding", b"a")
    made["embedding"].call = lambda body: b"not json"  # type: ignore[method-assign]

    reply = unit.handle("embedding", b"b")

    assert reply.status == 503 and "nobody can read" in json.loads(reply.body)["refusal"]


def test_closing_the_supervisor_ends_whatever_is_loaded() -> None:
    """The container is told to stop and the part's process goes with it, not after it.

    Delete this and a stopped container leaves a child that holds a model until it is killed."""
    unit, log, _, _ = built()
    unit.handle("embedding", b"a")

    unit.close()

    assert unit.loaded is None and log[-1] == "stop embedding"


# ------------------------------------------------------------------ a real child process
_STAND_IN = r"""
import json, sys
sys.path.insert(0, {src!r})
from inference_server.framing import read_frame, write_frame
out = sys.stdout.buffer
write_frame(out, json.dumps({{"ready": True, "model": "stand-in@r:3"}}).encode())
while True:
    body = read_frame(sys.stdin.buffer, ceiling=1 << 24)
    if body is None:
        break
    answer = {{"status": 200, "answer": {{"n": len(body)}}, "items": 1}}
    write_frame(out, json.dumps(answer).encode())
"""


def test_a_real_child_process_loads_answers_and_is_really_gone_when_stopped() -> None:
    """The framing and the process lifecycle through real pipes: the child says it has loaded,
    answers a request, and after `stop` is not running. A process that survived its stop would hold
    the memory the design exists to give back.

    Delete this and everything above is proved over stand-ins that cannot fail to end."""
    script = _STAND_IN.format(src=str(PACKAGE.parent))
    process = supervisor.SubprocessPart("embedding", argv=[sys.executable, "-c", script])

    label = process.start()
    answer = json.loads(process.call(b"abcdef"))
    child = process._process
    assert child is not None
    process.stop()

    assert label == "stand-in@r:3"
    assert answer == {"status": 200, "answer": {"n": 6}, "items": 1}
    assert child.poll() is not None, "the process outlived its stop"
    process.stop()  # safe twice


def test_a_child_that_exits_before_it_says_it_has_loaded_is_a_failed_load() -> None:
    """The part's process dying during load (out of memory, a missing library) is reported as a
    failure to load and not as a hang.

    Delete this and the supervisor waits out the load timeout for a process that is already gone."""
    process = supervisor.SubprocessPart("embedding", argv=[sys.executable, "-c", "pass"])

    with pytest.raises(supervisor.PartFailed, match="before it said it had loaded"):
        process.start()


# ------------------------------------------------------------------ the worker's loop
class _Backend:
    label = "stand-in@r:1"

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def handle(self, body: bytes) -> worker.Answer:
        if self.fail:
            raise ValueError("the secret passage of the document")
        return worker.Answer(200, {"len": len(body)}, items=2)


def _serve(monkeypatch: pytest.MonkeyPatch, backend: _Backend, requests: list[bytes]) -> list[Any]:
    monkeypatch.setattr(worker, "load_backend", lambda part, cfg: backend)
    inbound = io.BytesIO()
    for body in requests:
        framing.write_frame(inbound, body)
    inbound.seek(0)
    outbound = io.BytesIO()
    assert worker.serve("embedding", server_config(), inbound, outbound) == 0
    outbound.seek(0)
    frames = []
    while (one := framing.read_frame(outbound, ceiling=1 << 20)) is not None:
        frames.append(json.loads(one))
    return frames


def test_the_worker_says_it_has_loaded_and_then_answers_each_request_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first frame is the label the application records beside every vector, and each request
    gets exactly one answer.

    Delete this and the supervisor reads a request's answer as the load notice."""
    frames = _serve(monkeypatch, _Backend(), [b"aa", b"bbbb"])

    assert frames[0] == {"ready": True, "model": "stand-in@r:1"}
    assert frames[1:] == [
        {"status": 200, "answer": {"len": 2}, "items": 2},
        {"status": 200, "answer": {"len": 4}, "items": 2},
    ]


def test_an_exception_in_a_part_is_an_outage_and_its_text_never_leaves(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A parser's exception message quotes the file it was reading, so the type goes to the log and
    the answer says only that the part failed.

    Delete this and a document's text travels back to the application in an error."""
    frames = _serve(monkeypatch, _Backend(fail=True), [b"x"])

    assert frames[1]["status"] == 503
    assert "secret" not in json.dumps(frames)
    assert "ValueError" in capsys.readouterr().err


# ------------------------------------------------------------------ the HTTP face
class _Unit:
    """A supervisor stand-in that answers what a test says and records what it was asked."""

    loaded: str | None = None

    def __init__(self) -> None:
        self.asked: list[tuple[str, bytes]] = []

    def handle(self, part: str, body: bytes) -> supervisor.Reply:
        self.asked.append((part, body))
        status = 503 if body == b"refuse" else 200
        return supervisor.Reply(status, b'{"ok":true}')


@pytest.fixture
def running() -> Any:
    cfg = server_config(INFERENCE_MAX_REQUEST_BYTES="1024")
    unit = _Unit()
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        gateway.make_handler(cfg, unit),  # type: ignore[arg-type]
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1], unit
    server.shutdown()
    server.server_close()


def _ask(port: int, method: str, path: str, body: bytes | None = None, **headers: str) -> Any:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    data = response.read()
    connection.close()
    return response, data


def test_each_route_hands_its_body_to_its_part_and_returns_what_came_back(running: Any) -> None:
    """The five paths, each to its part, with the body untouched. Delete this and a route is
    wired to the wrong part and a document is read by the wrong model."""
    port, unit = running
    for path, part in gateway.ROUTES.items():
        response, data = _ask(port, "POST", path, b"payload")
        assert (response.status, json.loads(data)) == (200, {"ok": True}), path
        assert unit.asked[-1] == (part, b"payload")


def test_a_body_exactly_at_the_ceiling_is_taken_and_one_byte_over_is_not(running: Any) -> None:
    """The line itself, from both sides: the ceiling is the most it accepts, so a body of exactly
    that many bytes is served and one more is refused.

    Delete this and the comparison can move by one in either direction, which is a refusal of a
    request that fits or a read of one that does not."""
    port, unit = running

    assert _ask(port, "POST", "/embed", b"x" * 1024)[0].status == 200
    assert _ask(port, "POST", "/embed", b"x" * 1025)[0].status == 413
    assert [len(body) for _, body in unit.asked] == [1024]


def test_a_body_over_the_ceiling_is_refused_before_it_is_read(running: Any) -> None:
    """The ceiling caps what this process allocates, so it is a refusal and not a message sent
    after the allocation: the part was never asked.

    Delete this and one large request is allocated in full before anything says no."""
    port, unit = running
    response, _ = _ask(port, "POST", "/embed", b"x" * 2048)

    assert response.status == 413 and unit.asked == []


def test_a_request_that_does_not_say_how_long_it_is_is_refused_and_so_is_a_stranger_path(
    running: Any,
) -> None:
    """A body of unknown size is a body of any size, and a path nobody serves is a 404 that is the
    application's own mistake. Delete this and either reaches a part."""
    port, unit = running
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    connection.putrequest("POST", "/embed")
    connection.endheaders()
    assert connection.getresponse().status == 411
    connection.close()
    assert _ask(port, "POST", "/nowhere", b"x")[0].status == 404
    assert unit.asked == []


def test_an_unavailable_answer_tells_the_caller_to_retry_later(running: Any) -> None:
    """A 503 carries `Retry-After`, so a caller that honours it does not hammer a host that has
    just said it has no room. Delete this and a refusal invites an immediate retry."""
    port, _ = running
    response, _ = _ask(port, "POST", "/embed", b"refuse")

    assert response.status == 503 and response.getheader("Retry-After")


def test_readiness_is_503_with_the_gaps_when_a_part_is_missing_and_200_when_not(
    running: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What the container's health check reads: the gaps as a list and the parts the server runs,
    from the readiness route, which loads nothing.

    Delete this and the health check cannot tell a server that lacks its weights from one that
    has them."""
    port, _ = running
    monkeypatch.setattr(gateway, "readiness_gaps", lambda cfg: ("the embedding part is not here",))
    response, data = _ask(port, "GET", "/ready")
    body = json.loads(data)
    assert response.status == 503 and body["ready"] is False
    assert body["gaps"] == ["the embedding part is not here"] and body["parts"] == ["embedding"]

    monkeypatch.setattr(gateway, "readiness_gaps", lambda cfg: ())
    response, data = _ask(port, "GET", "/ready")
    assert response.status == 200 and json.loads(data)["ready"] is True


# ------------------------------------------------------------------ the weights
class _Response(io.BytesIO):
    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _opener(content: bytes) -> Callable[..., _Response]:
    calls: list[str] = []

    def opener(url: str, timeout: float = 0) -> _Response:
        calls.append(url)
        return _Response(content)

    opener.calls = calls  # type: ignore[attr-defined]
    return opener


def test_a_fetched_file_is_hashed_recorded_and_not_left_half_written(tmp_path: Path) -> None:
    """Written under a temporary name and moved into place, so a connection that dies leaves no
    file the server would mistake for weights; the digest it actually received is recorded.

    Delete this and a truncated download is read as a model."""
    source = fetch.Source(part="embedding", name="m.gguf", url="https://example.invalid/m")
    content = b"weights" * 1000

    said = fetch.fetch_one(source, tmp_path, opener=_opener(content))

    assert (tmp_path / "m.gguf").read_bytes() == content
    assert not list(tmp_path.glob("*.part"))
    record = json.loads((tmp_path / fetch.RECORD).read_text())
    assert record["m.gguf"]["sha256"] == hashlib.sha256(content).hexdigest()
    assert fetch.THE_FIRST_FETCH_IS_TRUSTED_UNTIL_SOMEBODY_PINS_IT in said


def test_a_file_that_does_not_match_its_pinned_digest_is_thrown_away(tmp_path: Path) -> None:
    """Pinned means held to it: the wrong bytes leave no file and raise. The positive case beside
    it, so a check that refuses everything is caught.

    Delete this and a pinned digest is a comment."""
    content = b"the right weights"
    right = fetch.Source(
        part="embedding",
        name="m.gguf",
        url="https://example.invalid/m",
        sha256=hashlib.sha256(content).hexdigest(),
    )
    wrong = fetch.Source(
        part="embedding", name="w.gguf", url="https://example.invalid/w", sha256="0" * 64
    )

    assert "matches its pinned digest" in fetch.fetch_one(right, tmp_path, opener=_opener(content))
    with pytest.raises(fetch.FetchError, match="not the pinned one"):
        fetch.fetch_one(wrong, tmp_path, opener=_opener(content))
    assert not (tmp_path / "w.gguf").exists() and not list(tmp_path.glob("*.part"))


def test_a_file_already_here_and_unchanged_is_not_fetched_again(tmp_path: Path) -> None:
    """A restart of the release must not become a download of a gigabyte, and an install with no
    route out at that moment keeps working. Changed bytes are fetched again.

    Delete this and every deploy downloads the model."""
    source = fetch.Source(part="embedding", name="m.gguf", url="https://example.invalid/m")
    first = _opener(b"weights")
    fetch.fetch_one(source, tmp_path, opener=first)
    second = _opener(b"weights")

    assert "already here" in fetch.fetch_one(source, tmp_path, opener=second)
    assert second.calls == []  # type: ignore[attr-defined]
    (tmp_path / "m.gguf").write_bytes(b"weight!")
    third = _opener(b"weights")
    fetch.fetch_one(source, tmp_path, opener=third)
    assert third.calls == ["https://example.invalid/m"]  # type: ignore[attr-defined]


def test_the_table_says_which_sources_are_unpinned_and_none_is_called_pinned_by_accident() -> None:
    """Nobody working on this product has downloaded these files, so no digest is pinned, and the
    table says so with `pinned` False rather than carrying a digest typed from memory.

    Delete this and a digest nobody checked is added, and the check it implies is a lie."""
    assert fetch.SOURCES
    for source in fetch.SOURCES:
        assert source.part in config.PARTS
        assert source.pinned is bool(source.sha256)
    assert [one.name for one in fetch.SOURCES if one.pinned] == []
    assert fetch.sources_for(["embedding"]) == tuple(
        one for one in fetch.SOURCES if one.part == "embedding"
    )
    assert fetch.sources_for(["layout"]) == ()  # a directory, fetched by the library's own tool
    assert [one.name for one in fetch.sources_for(["tika", "ocr"])] == [
        "tessdata/eng.traineddata",
        "tika/tika-server.jar",
    ]
