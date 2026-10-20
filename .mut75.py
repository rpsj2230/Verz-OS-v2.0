from pathlib import Path

from brain.ops.mutation import Mutation, verify

AUDIT = "src/brain/ops/bundle_audit.py"
STATIC = "src/brain/console_static.py"
CHECK = "src/brain/ops/acceptance_checks_console_bundle.py"
T_AUDIT = ("tests/unit/test_bundle_audit.py", "tests/unit/test_acceptance_checks_console_bundle.py")
T_STATIC = ("tests/unit/test_bundle_audit.py", "tests/unit/test_console_served.py")
T_CHECK = ("tests/unit/test_acceptance_checks_console_bundle.py",)


def a(label: str, before: str, after: str) -> Mutation:
    return Mutation(label=label, path=AUDIT, before=before, after=after, tests=T_AUDIT)


def s(label: str, before: str, after: str) -> Mutation:
    return Mutation(label=label, path=STATIC, before=before, after=after, tests=T_STATIC)


def c(label: str, before: str, after: str) -> Mutation:
    return Mutation(label=label, path=CHECK, before=before, after=after, tests=T_CHECK)


report = verify(
    [
        a("a protocol-relative address is not another host", 'if text.startswith("//"):', "if False:"),
        a(
            "a data: address is another host",
            'return bool(_SCHEME.match(text)) and not text.lower().startswith(("data:", "blob:"))',
            "return bool(_SCHEME.match(text))",
        ),
        a(
            "the runtime configuration address is a missing file",
            "if shown in SERVED_BY_THE_APPLICATION:\n            continue",
            "if False:\n            continue",
        ),
        a(
            "an address may leave the bundle",
            "if candidate != resolved_root and resolved_root not in candidate.parents:",
            "if False:",
        ),
        a("a file that is not there resolves", "return candidate if candidate.is_file() else None", "return candidate"),
        a(
            "an address that names no file is not a finding",
            "and _resolve(shown, document, root) is None",
            "and False",
        ),
        a(
            "any file a font face names is a font",
            "if found is not None and found.suffix.lower() in FONT_EXTENSIONS:",
            "if found is not None:",
        ),
        a("a bundle with no font passes", "if not faces:", "if False:"),
        a("a font needs no notice", "if package_slug(family) not in slugs:", "if False:"),
        a(
            "the notice is read from a file that may not exist",
            "if notices.is_file():",
            "if True:",
        ),
        a("a family is looked up as written", '.replace(" ", "-")', '.replace(" ", "")'),
        a("a srcset is read as one address", 'parts = value.split(",") if name in {"srcset", "imagesrcset"} else [value]', "parts = [value]"),
        a("a style attribute is not read", 'elif name == "style":', "elif False:"),
        a("an inline style element is not read", "self._in_style = tag == \"style\"", "self._in_style = False"),
        a("a meta refresh is not read", 'if tag == "meta" and named.get("http-equiv", "").lower() == "refresh":', "if False:"),
        a("a script naming a font host passes", "if host in text:", "if False:"),
        a("a font host is dropped from the list", '"fonts.gstatic.com",\n', ""),
        a("the command always succeeds", "return 1 if findings else 0", "return 0"),
        a(
            "a font the sheet declares is not listed for the install check",
            'found.add("/" + file.relative_to(base).as_posix())',
            "pass",
        ),
        s("a woff2 is served as a woff", '".woff2": "font/woff2",', '".woff2": "font/woff",'),
        s("a font gets no explicit type", "found, media_type=FONT_CONTENT_TYPES.get(found.suffix.lower()), headers=headers", "found, media_type=None, headers=headers"),
        s("a year becomes a minute", 'HASHED_ASSET_CACHE_CONTROL: Final = "public, max-age=31536000, immutable"', 'HASHED_ASSET_CACHE_CONTROL: Final = "public, max-age=60, immutable"'),
        s("a hashed file may be revalidated", 'HASHED_ASSET_CACHE_CONTROL: Final = "public, max-age=31536000, immutable"', 'HASHED_ASSET_CACHE_CONTROL: Final = "public, max-age=31536000"'),
        s("every file is cached for ever", "if inside[:1] == (HASHED_ASSET_DIRECTORY,)", "if True"),
        s("no file is cached for ever", "if inside[:1] == (HASHED_ASSET_DIRECTORY,)", "if False"),
        c("an image with no console is a failure", "if bundle_entry() is None:", "if False:"),
        c("another host is not reported", "if A_REFERENCE_NAMES_NO_OTHER_HOST_ID in found:", "if False:"),
        c("a missing file is not reported", "if A_REFERENCE_IS_A_FILE_THE_BUNDLE_CARRIES_ID in found:", "if False:"),
        c("a script naming a font host is not reported", "if A_SCRIPT_NAMES_NO_FONT_HOST_ID in found:", "if False:"),
        c("a bundle with no font is not reported", "if THE_BUNDLE_CARRIES_NO_FONT_ID in found:", "if False:"),
        c("a font with no notice is not reported", "if A_FONT_HAS_NO_LICENCE_NOTICE_ID in found:", "if False:"),
        c("a font answered as another type passes", 'if served.headers.get("content-type") != expected:', "if False:"),
        c("a font that may not be kept passes", 'if "immutable" not in served.headers.get("cache-control", ""):', "if False:"),
        c("an unserved notice passes", 'if not notices.headers.get("content-type", "").startswith("text/plain"):', "if False:"),
    ],
    repo=Path("."),
    carry=(
        "tests/unit/test_bundle_audit.py",
        "tests/unit/test_acceptance_checks_console_bundle.py",
        "src/brain/ops/bundle_audit.py",
        "src/brain/ops/acceptance_checks_console_bundle.py",
        "src/brain/console_static.py",
        ".github/workflows/ci.yml",
    ),
)
print(report.table())
assert not report.survivors, report.survivors
