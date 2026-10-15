from pathlib import Path

from brain.ops.mutation import Mutation, verify

PEAK = "src/brain/ops/load_peak.py"
STORE = "src/brain/ops/load_run_store.py"
T = (
    "tests/unit/test_load_peak.py",
    "tests/unit/test_load_peak_run.py",
    "tests/unit/test_load_run_store.py",
)


def m(label: str, path: str, before: str, after: str, tests: tuple[str, ...] = T) -> Mutation:
    return Mutation(label=label, path=path, before=before, after=after, tests=tests)


mutations = [
    m("a run never stops for the limits", PEAK, "STOP_WHEN_SHED_SHARE: Final = 0.5", "STOP_WHEN_SHED_SHARE: Final = 1.01"),
    m("stopping at exactly the share needs strictly more", PEAK, "shed / replied >= stop_when_shed_share", "shed / replied > stop_when_shed_share"),
    m("a run may stop on the first reply", PEAK, "replied >= MINIMUM_REQUESTS_FOR_A_P95 and shed", "replied >= 1 and shed"),
    m("a stopped run still waits out the schedule", PEAK, "        if not stopped:\n            await sleep(seconds)", "        if True:\n            await sleep(seconds)"),
    m("the peak in flight is the last reading", PEAK, "most = max(most, in_flight)", "most = in_flight"),
    m("held back requests are not counted", PEAK, "not_sent=len(results) - len(kept),", "not_sent=0,"),
    m("the length is the clock and not the difference", PEAK, "seconds_run=clock() - begun,", "seconds_run=clock(),"),
    m("a run below the rate is the peak test", PEAK, "profile.arrivals_per_second >= stated.arrivals_per_second", "True"),
    m("a short run is the peak test", PEAK, "and profile.seconds >= PEAK_SECONDS", "and True"),
    m("a bounded run is the peak test", PEAK, "and profile.total == planned", "and True"),
    m("a stopped run is the peak test", PEAK, "and measured.not_sent == 0\n    )", "and True\n    )"),
    m("the switch does not stop the command", PEAK, "    if not switch_is_on:\n        out.append(", "    if False:\n        out.append("),
    m("a person outside the department is allowed", PEAK, "outside = sum(1 for one in callers if one.primary_department != LOAD_TEST_DEPARTMENT)", "outside = 0"),
    m("no tokens at all is allowed", PEAK, "if not callers or outside:", "if outside:"),
    m("a wrong confirmation is allowed", PEAK, "if confirmed != planned:", "if False:"),
    m("a stopped run is recorded as held", PEAK, "held=report.held and not measured.not_sent,", "held=report.held,"),
    m("an unknown profile is accepted", PEAK, "    if found is None:\n        names", "    if False:\n        names"),
    m("a refused token is not a refusal", PEAK, "            if not isinstance(body, dict):", "            if False:"),
    m("the department of a person is not read", PEAK, "department = body.get(\"primary_department\")", "department = LOAD_TEST_DEPARTMENT"),
    m("the keeper's connection is not let go", PEAK, "        await keeper.close()", "        pass"),
    m("a refusal is not raised", PEAK, "        if refusals:\n            raise LoadError(\"; \".join(refusals))", "        if False:\n            raise LoadError(\"; \".join(refusals))"),
    m("the mix of a profile is ignored", PEAK, "weights = [profile.mix[lane] for lane in lanes]", "weights = [MIX[lane] for lane in lanes]"),
    m("a mix that forgets a lane is accepted", PEAK, "if set(self.mix) != set(MIX) or", "if False or"),
    m("a mix with no share is accepted", PEAK, "or any(weight <= 0 for weight in self.mix.values())", "or False"),
    m("the exit for an unkept result is zero", PEAK, "return EXIT_UNKEPT\n    print(f\"kept", "return 0\n    print(f\"kept"),
    m("an unkept result says it was kept", PEAK, "    if not ran.kept:", "    if False:"),
    m("a held run exits one", PEAK, "return 0 if ran.record.held else EXIT_UNMET", "return EXIT_UNMET"),
    m("a lower rate is not used", PEAK, "stated.arrivals_per_second\n                if args.arrivals_per_second is None\n                else args.arrivals_per_second", "stated.arrivals_per_second"),
    m("held is read as truthy", STORE, 'held=value["held"] is True,', 'held=bool(value["held"]),'),
    m("at_stated_peak is read as truthy", STORE, 'at_stated_peak=value["at_stated_peak"] is True,', 'at_stated_peak=bool(value["at_stated_peak"]),'),
    m("an upper-case run id is accepted", STORE, "or self.run_id != self.run_id.lower()", ""),
    m("a run id with punctuation is accepted", STORE, "or not self.run_id.isalnum()", ""),
    m("runs are listed oldest first", STORE, "key=lambda r: r.started_at, reverse=True", "key=lambda r: r.started_at, reverse=False"),
    m("a stray row in the namespace is read as a run", STORE, 'if key.startswith("load_test.run_")', "if True"),
    m("no database is no refusal", STORE, "    if not url:\n        raise RunStoreError", "    if False:\n        raise RunStoreError"),
    m("the row is not a json value", STORE, "value_type=SettingType.JSON,", "value_type=SettingType.STRING,"),
]

report = verify(mutations, repo=Path("."), carry=(
    "src/brain/ops/load_peak.py",
    "src/brain/ops/load_run_store.py",
    "src/brain/ops/features_declared/load_test.py",
    "src/brain/ops/acceptance_checks_load_peak.py",
    "tests/unit/test_load_peak.py",
    "tests/unit/test_load_peak_run.py",
    "tests/unit/test_load_run_store.py",
))
print(report.table())
print("SURVIVORS:", [s.label for s in report.survivors])
