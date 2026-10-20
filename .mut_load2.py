from pathlib import Path

from brain.ops.mutation import Mutation, verify

PEAK = "src/brain/ops/load_peak.py"
STORE = "src/brain/ops/load_run_store.py"
T = (
    "tests/unit/test_load_peak.py",
    "tests/unit/test_load_peak_run.py",
    "tests/unit/test_load_run_store.py",
)


def m(label: str, path: str, before: str, after: str) -> Mutation:
    return Mutation(label=label, path=path, before=before, after=after, tests=T)


mutations = [
    m("a lower rate is not used", PEAK, "stated.arrivals_per_second\n                if args.arrivals_per_second is None\n                else args.arrivals_per_second", "stated.arrivals_per_second"),
    m("a stray row in the namespace is read as a run", STORE, 'if key.startswith("load_test.run_")', "if True"),
    m("the row is not a json value", STORE, "value_type=SettingType.JSON,", "value_type=SettingType.STRING,"),
    m("the row is written under another actor", STORE, "updated_by=WRITER,", 'updated_by="someone",'),
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
