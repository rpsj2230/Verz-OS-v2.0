from pathlib import Path

from brain.ops.mutation import Mutation, verify

SRC = "src/brain/ops/dependency_policy.py"
T = ("tests/unit/test_dependency_policy.py",)


def m(label: str, before: str, after: str) -> Mutation:
    return Mutation(label=label, path=SRC, before=before, after=after, tests=T)


report = verify(
    [
        m(
            "a development package is read as build-only",
            'build_only=bool(package.get("dev")),',
            "build_only=False,",
        ),
        m(
            "a development package is dropped from the lock reading again",
            'if not path or "version" not in package:',
            'if not path or package.get("dev") or "version" not in package:',
        ),
        m(
            "the console lock no longer refuses a package with no licence",
            'LOCKS_WHERE_NO_LICENCE_REFUSES: Final = ("console/package-lock.json",)',
            "LOCKS_WHERE_NO_LICENCE_REFUSES: Final = ()",
        ),
        m(
            "a waiting build-only package waits under any licence",
            "elif waiting is not None and waiting.licence == licence:",
            "elif waiting is not None:",
        ),
        m(
            "nothing waits on the owner at all",
            "elif waiting is not None and waiting.licence == licence:",
            "elif False:",
        ),
        m(
            "a shipped package may wait on the owner too",
            "waiting = BUILD_ONLY_AWAITING_THE_OWNER.get(key) if component.build_only else None",
            "waiting = BUILD_ONLY_AWAITING_THE_OWNER.get(key)",
        ),
        m(
            "a build-only package is judged for archived and age",
            'if component.ecosystem == "image" or component.build_only:',
            'if component.ecosystem == "image":',
        ),
        m(
            "a build-only package is asked of the index",
            'if c.ecosystem in {"pypi", "npm"} and not c.build_only',
            'if c.ecosystem in {"pypi", "npm"}',
        ),
    ],
    repo=Path("."),
    carry=("tests/unit/test_dependency_policy.py",),
)
print(report.table())
assert not report.survivors, report.survivors
