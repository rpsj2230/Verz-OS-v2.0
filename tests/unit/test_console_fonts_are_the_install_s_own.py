"""The console's fonts are bundled with it and served by the install, and no page asks a font host.

Every typeface the theme names is one an `@fontsource` package installs: the package is a
dependency of the console, its stylesheet is imported by the theme, and the build copies the font
files beside the console's own, so loading a page fetches them from the install's own address.
Nothing in the console's sources or its HTML names another host for a font: no stylesheet,
`@import` or `url()` reaches outside, and no `<link>` preconnects to a font service. The cheaper
design, a stylesheet link to a hosted font service, is one request per page view to a third party
from every person's browser, carrying the install's address, and a console that does not render
its type on a network that blocks that host.

The assertions read the theme's declarations and the console's files as structure: the families
a `--ui`, `--brandfont` or `--mono` token names, the `@import` lines of the theme, the package
manifest's dependencies, and every URL with a scheme in any stylesheet or the HTML. Where the
console's packages are installed, each imported `@fontsource` stylesheet is read too, and every
font file it names is a relative path inside the package.

Task ids: M27.15.75
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

CONSOLE = Path(__file__).resolve().parents[2] / "console"
THEME = CONSOLE / "src" / "theme"

#: A stylesheet import of an `@fontsource` package's file.
FONTSOURCE_IMPORT = re.compile(r'@import\s+"(@fontsource/[a-z0-9-]+)/[^"]+\.css"\s*;')

#: The theme tokens that name a family, and the first family each names.
FAMILY_TOKEN = re.compile(r"--(ui|brandfont|mono):\s*\"([^\"]+)\"")

#: Any address with a scheme, which is what reaching outside the install looks like.
ADDRESS = re.compile(r"""(?:https?:)?//[a-z0-9.-]+\.[a-z]{2,}""", re.IGNORECASE)

#: Where a stylesheet or the HTML could ask for a font: an import, a url(), or a link element.
FONT_REACH = re.compile(r"""@import[^;]*|url\([^)]*\)|<link[^>]*>""", re.IGNORECASE)


def _stylesheets() -> list[Path]:
    return sorted((CONSOLE / "src").rglob("*.css"))


def _imported_packages() -> set[str]:
    return set(FONTSOURCE_IMPORT.findall((THEME / "tailwind.css").read_text(encoding="utf-8")))


def _package_of(family: str) -> str:
    return "@fontsource/" + family.lower().replace(" ", "-")


def test_every_family_the_theme_names_is_a_bundled_package_the_theme_imports() -> None:
    """The three type tokens each name a family whose `@fontsource` package is a dependency and
    whose stylesheet the theme imports. Delete this and a family can be named with nothing
    bundled behind it, so the browser falls back or a later change reaches for a hosted copy."""
    tokens = dict(FAMILY_TOKEN.findall((THEME / "tokens.css").read_text(encoding="utf-8")))
    assert set(tokens) == {"ui", "brandfont", "mono"}
    manifest = json.loads((CONSOLE / "package.json").read_text(encoding="utf-8"))
    dependencies = set(manifest.get("dependencies", {}))
    imported = _imported_packages()
    for family in tokens.values():
        package = _package_of(family)
        assert package in dependencies, family
        assert package in imported, family


def test_no_stylesheet_or_page_asks_another_host_for_anything() -> None:
    """Every import, url() and link in every stylesheet under the console's sources and in its
    HTML is a path on the install. Delete this and one `@import` of a hosted font service sends
    every person's browser to a third party on every page."""
    sources = [*_stylesheets(), CONSOLE / "index.html"]
    assert len(sources) > 1
    reaching = [
        (path.name, found)
        for path in sources
        for found in FONT_REACH.findall(path.read_text(encoding="utf-8"))
        if ADDRESS.search(found)
    ]
    assert reaching == []


def test_the_address_rule_would_find_a_hosted_font() -> None:
    """The positive case for the rule above: a hosted font service's stylesheet and link are each
    found, and the theme's own imports are not. Delete this and a rule that matches nothing passes
    the test above on every console."""
    hosted = (
        '@import url("https://fonts.googleapis.com/css2?family=Inter");\n'
        '<link rel="preconnect" href="https://fonts.gstatic.com">\n'
        "src: url(//use.typekit.net/abc.woff2);\n"
    )
    found = [one for one in FONT_REACH.findall(hosted) if ADDRESS.search(one)]
    assert len(found) == 3
    own = (THEME / "tailwind.css").read_text(encoding="utf-8")
    assert _imported_packages() and not any(ADDRESS.search(one) for one in FONT_REACH.findall(own))


def test_each_bundled_font_file_is_a_path_inside_its_package() -> None:
    """Read where the console's packages are installed: every font file an imported
    `@fontsource` stylesheet names is a relative path, so the build copies it and the install
    serves it. Delete this and a package whose stylesheet points at its own CDN passes."""
    root = CONSOLE / "node_modules"
    if not root.is_dir():
        pytest.skip("the console's packages are not installed here; the console job installs them")
    imports = FONTSOURCE_IMPORT.finditer((THEME / "tailwind.css").read_text(encoding="utf-8"))
    files = [root / match.group(0).split('"')[1] for match in imports]
    assert files
    for sheet in files:
        named = re.findall(r"url\(([^)]+)\)", sheet.read_text(encoding="utf-8"))
        assert named, sheet.name
        assert all(not ADDRESS.search(one) and one.strip("'\"").startswith("./") for one in named)
