"""Applies the recomputed profile figures after the merge (untracked helper)."""

from pathlib import Path


def sub(path: str, pairs: list[tuple[str, str]]) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    for before, after in pairs:
        if before not in text:
            raise SystemExit(f"{path}: {before[:70]!r} not found")
        text = text.replace(before, after)
    file.write_text(text, encoding="utf-8", newline="\n")
    print("fixed", path)


sub(
    "ops/install/install.sh",
    [
        (' -f /opt/brain/docker-compose.inference.yml', ""),
        ('BRAIN_SERVICES="15"; BRAIN_MEMORY_MIB="12032"', 'BRAIN_SERVICES="14"; BRAIN_MEMORY_MIB="8960"'),
        ('BRAIN_SERVICES="23"; BRAIN_MEMORY_MIB="16000"', 'BRAIN_SERVICES="22"; BRAIN_MEMORY_MIB="12928"'),
    ],
)
sub(
    "docs/install/install.md",
    [
        (
            "| `standard` | the above plus two workers, the file store, the identity provider, the inference server and the personal data analyser | 12032 MiB | 6 | 38 GiB | 15 |",
            "| `standard` | the above plus two workers, the file store, the identity provider and the personal data analyser | 8960 MiB | 5 | 36 GiB | 14 |",
        ),
        (
            "| `full` | the above plus the trace ledger, the automation canvas and the record matcher | 16000 MiB | 8 | 52 GiB | 23 |",
            "| `full` | the above plus the trace ledger, the automation canvas and the record matcher | 12928 MiB | 7 | 50 GiB | 22 |",
        ),
    ],
)
sub(
    "src/brain/ops/compose.py",
    [
        ("23 containers across 10 compose files", "22 containers across 9 compose files"),
        ("reserving 15744 MiB", "reserving 12672 MiB"),
        ("host with 16000 MiB", "host with 12928 MiB"),
    ],
)
sub(
    "docker-compose.lite.yml",
    [
        ("`full` means fourteen components", "`full` means thirteen components"),
        ("twenty-three containers", "twenty-two containers"),
        ("with 16000 MiB to spare", "with 12928 MiB to spare"),
    ],
)
sub(
    "tests/unit/test_compose.py",
    [
        ("summed_mib(files) == 16768", "summed_mib(files) == 13696"),
        ("deployment_mib(files) == 15744", "deployment_mib(files) == 12672"),
        ("needs 16000 MiB", "needs 12928 MiB"),
        ('host_mib_for("full", files) == 16000', 'host_mib_for("full", files) == 12928'),
    ],
)
sub(
    "tests/unit/test_deployment_requirements.py",
    [
        ('"standard": (12032, 15, 6, 38)', '"standard": (8960, 14, 5, 36)'),
        ('"full": (16000, 23, 8, 52)', '"full": (12928, 22, 7, 50)'),
    ],
)
