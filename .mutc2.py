import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("mutc", Path(__file__).with_name(".mutc.py"))
mutc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mutc)

idx = "../docs/reference-screens/index.json"
mutc.mutate(
    "a record cites a screenshot that does not cover it",
    idx,
    '"screenshots": [\n        "image-1788498419735"\n      ],\n      "requirements": [\n        "ANY-019",\n        "ANY-020",\n        "ANY-023"',
    '"screenshots": [\n        "image-1788498391599"\n      ],\n      "requirements": [\n        "ANY-019",\n        "ANY-020",\n        "ANY-023"',
    mutc.REF,
)
mutc.mutate(
    "a requirement is answered by another screenshot's record",
    idx,
    '"requirements": [\n        "ANY-050",',
    '"requirements": [\n        "ANY-001",',
    mutc.REF,
)
