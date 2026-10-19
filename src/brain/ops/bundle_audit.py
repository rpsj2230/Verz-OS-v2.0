"""What the built console names, read from the files the install serves.

`tests/unit/test_console_fonts_are_the_install_s_own.py` reads the console's **sources**: the
theme's tokens, its `@import` lines, the package manifest. That proves what the developer wrote and
nothing about what the build emitted, and the two differ by exactly the things a bundler does for
you: it rewrites a font's `url()` to a hashed path, it inlines a small file as a `data:` address, it
copies a dependency's stylesheet in, and it leaves a third party's address in a string if a library
carries one. "Loading any page makes no request to a font host" is a claim about the output.

**So this reads the output, and one rule serves three callers.** CI runs it over `console/dist`
right after the build, the install runs it over the bundle its own image carries (the acceptance
check `the_console_names_no_font_host_and_serves_every_font_it_ships`), and the unit tests run it
over fabricated bundles, good and bad. Three copies of the rule, one per place, would be three
places for it to drift; there is one, and `audit` is it.

**What it can prove and what it cannot.** Anything the page *loads* is named in a place a parser can
read: an attribute in `index.html`, a `url()` or `@import` in a stylesheet. Those are held to the
strict rule that nothing names another host and every address resolves to a file the bundle carries.
A script is different: a library may carry a URL in a string for any reason (a documentation link in
an error message, an XML namespace), so scripts are held to the narrower rule that none names a
host that exists to serve fonts (`FONT_HOSTS`). That is a list of fingerprints, and a font host
that is not on it passes; it is a net for the careless case and not a proof. **The proof that no
request leaves the install is the browser's:** `e2e/lib/checklist.ts` records every request each
page makes, fonts included, and fails on one that goes anywhere but the install and its identity
provider. This audit is what makes that failure cheap, because it fails in the build job in a
minute rather than in the nightly browser run.

**Licence notices travel with the fonts.** The SIL Open Font Licence asks that the copyright notice
and the licence accompany every copy of the font software. The build emits `font-licences.txt` in
the bundle (`console/scripts/font-licences.mjs`) and a font family with no section in it
is a finding, because a font that ships without its notice is a licence breach nobody sees until a
copyright holder does.

**Rejected:** matching a list of hosts in every file, which refuses a bundle for an XML namespace in
a library and teaches people to delete the rule; and reading only the source, which is the test that
already existed and passed with a hosted font in the output.

Task ids: M27.15.75
"""

from __future__ import annotations

import argparse
import re
from collections.abc import Sequence
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Final

from brain.console_static import CONSOLE_CONFIG_PATH

#: Where the build puts the notices the Open Font Licence asks to travel with a font.
FONT_LICENCES_FILE: Final = "font-licences.txt"

#: The file types a browser draws text from. The ones Vite emits for the fontsource packages are the
#: first two; the rest are listed so a font that arrives another way is still found and judged.
FONT_EXTENSIONS: Final = (".woff2", ".woff", ".ttf", ".otf", ".eot")

#: Hosts that exist to serve fonts. A fingerprint list: the module docstring says what it is for
#: and what it is not. A script that names one of these is the careless case, caught here.
FONT_HOSTS: Final = (
    "fonts.googleapis.com",
    "fonts.gstatic.com",
    "fonts.googleapis.cn",
    "fonts.bunny.net",
    "use.typekit.net",
    "p.typekit.net",
    "fonts.adobe.com",
    "use.fontawesome.com",
    "kit.fontawesome.com",
    "api.fontshare.com",
    "cdn.fonts.net",
    "fast.fonts.net",
    "cloud.typography.com",
    "cdnfonts.com",
)

#: Addresses the entry document names that the application answers at runtime, so the bundle does
#: not carry a file for them. One: the install's own configuration, served by `brain.console_static`
#: from the same origin. Taken from that module rather than typed, so the two cannot disagree.
SERVED_BY_THE_APPLICATION: Final = frozenset({CONSOLE_CONFIG_PATH})

# ---------------------------------------------------------------- the rules, in words
A_REFERENCE_NAMES_NO_OTHER_HOST_ID: Final = "names another host"
A_REFERENCE_IS_A_FILE_THE_BUNDLE_CARRIES_ID: Final = "names a file the bundle does not carry"
A_SCRIPT_NAMES_NO_FONT_HOST_ID: Final = "names a font host"
A_FONT_HAS_NO_LICENCE_NOTICE_ID: Final = "ships a font with no licence notice"
THE_BUNDLE_CARRIES_NO_FONT_ID: Final = "carries no font at all"
THE_BUNDLE_HAS_NO_ENTRY_ID: Final = "has no entry document"

#: Attributes that make a browser fetch something, by what is read from them.
_FETCHING_ATTRIBUTES: Final = frozenset(
    {"href", "src", "poster", "data", "action", "formaction", "srcset", "imagesrcset"}
)

_CSS_URL: Final = re.compile(r"""url\(\s*(['"]?)(?P<target>[^'")]*?)\1\s*\)""", re.IGNORECASE)
_CSS_IMPORT: Final = re.compile(r"""@import\s+(['"])(?P<target>[^'"]+)\1""", re.IGNORECASE)
_FONT_FACE: Final = re.compile(r"@font-face\s*\{(?P<body>[^}]*)\}", re.IGNORECASE)
_SCHEME: Final = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)


@dataclass(frozen=True)
class Finding:
    """One thing the bundle does that it must not, and where.

    `kind` is one of the `*_ID` strings above, so a caller can say what class of fault it is
    without parsing a sentence; `where` is the bundle-relative file; `detail` is the address or
    the family, for a person reading CI output. It is never served on a page: the acceptance
    check raises its own literal sentence per kind.
    """

    kind: str
    where: str
    detail: str

    def __str__(self) -> str:
        return f"{self.where} {self.kind}: {self.detail}"


class _References(HTMLParser):
    """Every address a document's elements make a browser fetch, and every inline stylesheet."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.addresses: list[str] = []
        self.styles: list[str] = []
        self._in_style = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._in_style = tag == "style"
        named = {name: value for name, value in attrs if value is not None}
        for name, value in named.items():
            if name in _FETCHING_ATTRIBUTES:
                # A srcset is a comma list of "address descriptor".
                parts = value.split(",") if name in {"srcset", "imagesrcset"} else [value]
                self.addresses.extend(part.split()[0] for part in parts if part.strip())
            elif name == "style":
                self.styles.append(value)
        if tag == "meta" and named.get("http-equiv", "").lower() == "refresh":
            self.addresses.append(named.get("content", "").lower().split("url=")[-1].strip())

    def handle_endtag(self, tag: str) -> None:
        if tag == "style":
            self._in_style = False

    def handle_data(self, data: str) -> None:
        if self._in_style:
            self.styles.append(data)


def is_another_host(address: str) -> bool:
    """Whether an address leaves the install: a scheme other than `data:`, or `//host`."""
    text = address.strip()
    if text.startswith("//"):
        return True
    return bool(_SCHEME.match(text)) and not text.lower().startswith(("data:", "blob:"))


def _resolve(address: str, document: Path, root: Path) -> Path | None:
    """The file an install-local address names, or None when it names nothing in the bundle."""
    path = address.split("#", 1)[0].split("?", 1)[0]
    if not path:
        return None
    base = root if path.startswith("/") else document.parent
    candidate = (base / path.lstrip("/")).resolve()
    resolved_root = root.resolve()
    if candidate != resolved_root and resolved_root not in candidate.parents:
        return None
    return candidate if candidate.is_file() else None


def _stylesheet_addresses(css: str) -> list[str]:
    found = [match.group("target") for match in _CSS_URL.finditer(css)]
    found += [match.group("target") for match in _CSS_IMPORT.finditer(css)]
    return found


_FAMILY: Final = re.compile(r"""font-family\s*:\s*['"]?(?P<family>[^;'"}]+)""", re.IGNORECASE)


def _faces(css: str, document: Path, root: Path) -> list[tuple[str, Path]]:
    """Each `@font-face` as (family, font file), for the font files the bundle carries."""
    named: list[tuple[str, Path]] = []
    for face in _FONT_FACE.finditer(css):
        body = face.group("body")
        family = _FAMILY.search(body)
        for target in _stylesheet_addresses(body):
            if is_another_host(target):
                continue
            found = _resolve(target, document, root)
            if found is not None and found.suffix.lower() in FONT_EXTENSIONS:
                named.append((family.group("family").strip() if family else "", found))
    return named


def _judge_addresses(
    addresses: Sequence[str], document: Path, root: Path, into: list[Finding]
) -> None:
    where = document.relative_to(root).as_posix()
    for address in addresses:
        shown = address.strip()
        if shown in SERVED_BY_THE_APPLICATION:
            continue
        if is_another_host(shown):
            into.append(Finding(A_REFERENCE_NAMES_NO_OTHER_HOST_ID, where, shown))
        elif (
            shown
            and not shown.lower().startswith(("data:", "blob:"))
            and _resolve(shown, document, root) is None
        ):
            into.append(Finding(A_REFERENCE_IS_A_FILE_THE_BUNDLE_CARRIES_ID, where, shown))


def fonts_in_use(root: Path) -> list[str]:
    """The address of every font file a stylesheet in the bundle declares, as a browser asks for it.

    `/assets/<name>.woff2` for each, sorted and without repeats. This is what the install check asks
    its own server for, one by one, so that "every font a page needs is served" is a request per
    font rather than a statement about a directory.
    """
    base = root.resolve()
    found: set[str] = set()
    for sheet in sorted(base.rglob("*.css")):
        for _family, file in _faces(sheet.read_text(encoding="utf-8"), sheet, base):
            found.add("/" + file.relative_to(base).as_posix())
    return sorted(found)


def audit(root: Path) -> list[Finding]:
    """Every fault in the bundle at `root`, empty when it names no other host and ships its fonts.

    A bundle with no entry document is one finding and nothing more: there is no page to read.
    """
    root = root.resolve()
    entry = root / "index.html"
    if not entry.is_file():
        return [Finding(THE_BUNDLE_HAS_NO_ENTRY_ID, "index.html", str(root))]
    into: list[Finding] = []

    page = _References()
    page.feed(entry.read_text(encoding="utf-8"))
    _judge_addresses(page.addresses, entry, root, into)
    for style in page.styles:
        _judge_addresses(_stylesheet_addresses(style), entry, root, into)

    faces: list[tuple[str, Path, Path]] = []
    for sheet in sorted(root.rglob("*.css")):
        css = sheet.read_text(encoding="utf-8")
        _judge_addresses(_stylesheet_addresses(css), sheet, root, into)
        faces.extend((family, file, sheet) for family, file in _faces(css, sheet, root))
    for style in page.styles:
        faces.extend((family, file, entry) for family, file in _faces(style, entry, root))

    for script in sorted(root.rglob("*.js")):
        text = script.read_text(encoding="utf-8")
        for host in FONT_HOSTS:
            if host in text:
                into.append(
                    Finding(
                        A_SCRIPT_NAMES_NO_FONT_HOST_ID, script.relative_to(root).as_posix(), host
                    )
                )

    if not faces:
        into.append(Finding(THE_BUNDLE_CARRIES_NO_FONT_ID, "index.html", str(root)))
    into.extend(_unlicensed(faces, root))
    return into


def package_slug(family: str) -> str:
    """The `@fontsource` package a family comes from: its name, lower-cased and hyphenated.

    The convention the console's own tests already rely on (`IBM Plex Sans` is
    `@fontsource/ibm-plex-sans`). A family that does not follow it has no section and is a finding,
    which is the conservative answer: somebody names the package, rather than the audit guessing.
    """
    return family.strip().lower().replace(" ", "-")


def _unlicensed(faces: Sequence[tuple[str, Path, Path]], root: Path) -> list[Finding]:
    """A family with a font in the bundle and no section in the notices the build wrote.

    Judged by the family a stylesheet declares and the exact package heading the build wrote for it
    (`@fontsource/<slug>`), and never by a prefix of a file name: `roboto` is a prefix of
    `roboto-mono-latin-400-...`, so a prefix rule lets one family's notice stand in for another's.
    """
    notices = root / FONT_LICENCES_FILE
    slugs: set[str] = set()
    if notices.is_file():
        slugs = set(re.findall(r"^@fontsource/([a-z0-9-]+)$", notices.read_text("utf-8"), re.M))
    found: dict[str, Finding] = {}
    for family, _font, sheet in faces:
        if package_slug(family) not in slugs:
            found.setdefault(
                family,
                Finding(
                    A_FONT_HAS_NO_LICENCE_NOTICE_ID, sheet.relative_to(root).as_posix(), family
                ),
            )
    return list(found.values())


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m brain.ops.bundle_audit")
    parser.add_argument("root", type=Path, nargs="?", default=Path("console/dist"))
    arguments = parser.parse_args(argv)
    findings = audit(arguments.root)
    for finding in findings:
        print(f"refused: {finding}")
    print(f"{'FAIL' if findings else 'ok'}: the built console at {arguments.root}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
