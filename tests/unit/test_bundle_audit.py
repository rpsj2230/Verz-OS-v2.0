"""The built console names no other host, ships its fonts with a notice, and serves them as fonts.

`test_console_fonts_are_the_install_s_own.py` reads the console's sources. These read what the build
emits and what the install then serves, which is where a hosted font would actually appear: a
bundler rewrites addresses, inlines small files and copies a dependency's stylesheet in, so a
passing check over the sources says nothing about the output. Every bundle here is fabricated in a
temporary directory, good and bad, so the rule is held over the cases it exists for and not over
whatever the last build happened to produce; the one test over the real build skips where there is
none and runs in the console job, which has just built one.

Task ids: M27.15.75
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain.console_static import (
    CONSOLE_CONFIG_PATH,
    FONT_CONTENT_TYPES,
    HASHED_ASSET_CACHE_CONTROL,
    mount_console_fallback,
)
from brain.ops import bundle_audit
from brain.ops.bundle_audit import (
    A_FONT_HAS_NO_LICENCE_NOTICE_ID,
    A_REFERENCE_IS_A_FILE_THE_BUNDLE_CARRIES_ID,
    A_REFERENCE_NAMES_NO_OTHER_HOST_ID,
    A_SCRIPT_NAMES_NO_FONT_HOST_ID,
    FONT_HOSTS,
    FONT_LICENCES_FILE,
    THE_BUNDLE_CARRIES_NO_FONT_ID,
    THE_BUNDLE_HAS_NO_ENTRY_ID,
    audit,
    is_another_host,
    package_slug,
)

REPO = Path(__file__).resolve().parents[2]

#: A family's file name as Vite emits it, so the notice lookup is exercised on a real shape.
FONT_FILE = "plex-sans-latin-400-normal-AbC123.woff2"
FONT_SHEET = (
    '@font-face{font-family:"Plex Sans";font-weight:400;'
    f"src:url(/assets/{FONT_FILE}) format('woff2')}}\n"
    "body{font-family:Plex,system-ui}\n"
)
NOTICES = (
    "Fonts bundled with this console.\n\n@fontsource/plex-sans\n---------------------\nOFL text\n"
)
ENTRY = (
    "<!doctype html><html><head>"
    '<link rel="manifest" href="/manifest.webmanifest">'
    '<script src="/api/console.js"></script>'
    '<script type="module" src="/assets/app-1.js"></script>'
    '<link rel="stylesheet" href="/assets/app-1.css">'
    "</head><body><div id=root></div></body></html>"
)


def bundle(
    root: Path,
    *,
    entry: str = ENTRY,
    sheet: str = FONT_SHEET,
    script: str = "export const x = 1;\n",
    notices: str | None = NOTICES,
    font_name: str | None = FONT_FILE,
) -> Path:
    """A directory shaped like a built console, with each part replaceable by a bad one."""
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text(entry, encoding="utf-8", newline="\n")
    (root / "manifest.webmanifest").write_text("{}", encoding="utf-8", newline="\n")
    (root / "assets" / "app-1.css").write_text(sheet, encoding="utf-8", newline="\n")
    (root / "assets" / "app-1.js").write_text(script, encoding="utf-8", newline="\n")
    if font_name is not None:
        (root / "assets" / font_name).write_bytes(b"wOF2\x00fabricated")
    if notices is not None:
        (root / FONT_LICENCES_FILE).write_text(notices, encoding="utf-8", newline="\n")
    return root


def kinds(root: Path) -> list[str]:
    return [one.kind for one in audit(root)]


# ------------------------------------------------------------------ what passes
def test_a_bundle_naming_only_itself_and_shipping_a_licensed_font_has_no_finding(
    tmp_path: Path,
) -> None:
    """The positive case for every refusal below: a stylesheet, a script, a manifest and one font
    with its notice, all reached by addresses on the install, is clean. Delete this and an audit
    that refuses every bundle satisfies the refusals that follow."""
    assert audit(bundle(tmp_path / "dist")) == []


def test_the_applications_own_configuration_address_is_not_a_missing_file(
    tmp_path: Path,
) -> None:
    """The entry document names `/api/console.js`, which the application answers at runtime and
    the bundle has no file for, and any other address with no file behind it is a finding. Delete
    this and either the real build is refused for the one address it must name, or the exception
    swallows every missing file under `/api`."""
    root = bundle(tmp_path / "dist")
    assert CONSOLE_CONFIG_PATH in (root / "index.html").read_text(encoding="utf-8")
    assert audit(root) == []
    stray = ENTRY.replace(CONSOLE_CONFIG_PATH, "/api/elsewhere.js")
    other = bundle(tmp_path / "other", entry=stray)
    assert kinds(other) == [A_REFERENCE_IS_A_FILE_THE_BUNDLE_CARRIES_ID]


@pytest.mark.parametrize(
    ("address", "another"),
    [
        ("https://fonts.googleapis.com/css2?family=Inter", True),
        ("http://example.invalid/a.woff2", True),
        ("//cdn.example.invalid/a.woff2", True),
        ("ftp://example.invalid/a", True),
        ("/assets/a.woff2", False),
        ("./a.woff2", False),
        ("a.woff2", False),
        ("data:font/woff2;base64,AAAA", False),
        ("blob:abc", False),
        ("#fragment", False),
        ("", False),
    ],
)
def test_an_address_is_another_host_when_it_has_a_scheme_or_starts_with_two_slashes(
    address: str, another: bool
) -> None:
    """Delete this and the rule that every refusal below rests on can be inverted, or can read a
    `data:` font, which makes no request, as a request."""
    assert is_another_host(address) is another


# ------------------------------------------------------------------ what is refused
def test_a_stylesheet_import_of_a_hosted_font_service_is_refused(tmp_path: Path) -> None:
    """The cheap design the leaf exists to refuse: one `@import` of a hosted font service sends
    every person's browser to a third party on every page. Delete this and it ships."""
    sheet = '@import url("https://fonts.googleapis.com/css2?family=Inter");\n' + FONT_SHEET
    found = audit(bundle(tmp_path / "dist", sheet=sheet))
    assert [(f.kind, f.where) for f in found] == [
        (A_REFERENCE_NAMES_NO_OTHER_HOST_ID, "assets/app-1.css")
    ]
    assert "fonts.googleapis.com" in found[0].detail


def test_a_font_face_whose_url_is_on_another_host_is_refused_even_when_protocol_relative(
    tmp_path: Path,
) -> None:
    """Delete this and a `src: url(//host/...)`, which has no scheme for a naive check to find, is
    carried to every browser."""
    sheet = "@font-face{font-family:X;src:url(//cdn.example.invalid/x.woff2)}\n" + FONT_SHEET
    assert kinds(bundle(tmp_path / "dist", sheet=sheet)) == [A_REFERENCE_NAMES_NO_OTHER_HOST_ID]


def test_a_preconnect_in_the_entry_document_is_refused(tmp_path: Path) -> None:
    """A `<link rel=preconnect>` makes a connection before a single font is asked for, so it is a
    request to a font host even when no font follows. Delete this and the entry document can open
    a connection to a third party that no stylesheet mentions."""
    entry = ENTRY.replace(
        "<head>", '<head><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    )
    found = audit(bundle(tmp_path / "dist", entry=entry))
    assert [(f.kind, f.where) for f in found] == [
        (A_REFERENCE_NAMES_NO_OTHER_HOST_ID, "index.html")
    ]


def test_an_inline_style_and_a_style_attribute_are_read_like_a_stylesheet(
    tmp_path: Path,
) -> None:
    """Delete this and a hosted font moved from a stylesheet into the entry document's own
    `<style>` or a `style=` attribute is the one place nothing looks."""
    block = ENTRY.replace(
        "<head>", '<head><style>@import url("https://fonts.bunny.net/css?family=a");</style>'
    )
    assert kinds(bundle(tmp_path / "a", entry=block)) == [A_REFERENCE_NAMES_NO_OTHER_HOST_ID]
    attribute = ENTRY.replace(
        "<body>", '<body style="background:url(https://example.invalid/x.png)">'
    )
    assert kinds(bundle(tmp_path / "b", entry=attribute)) == [A_REFERENCE_NAMES_NO_OTHER_HOST_ID]


def test_a_font_face_naming_a_file_the_bundle_does_not_carry_is_refused(tmp_path: Path) -> None:
    """The install's own address is not enough: a font the build did not copy is a 404 and a
    fallback face. Delete this and an unbundled font passes because its address is local."""
    sheet = "@font-face{font-family:X;src:url(/assets/missing-400-normal-Zz.woff2)}\n" + FONT_SHEET
    found = audit(bundle(tmp_path / "dist", sheet=sheet))
    assert [f.kind for f in found] == [A_REFERENCE_IS_A_FILE_THE_BUNDLE_CARRIES_ID]
    assert found[0].detail == "/assets/missing-400-normal-Zz.woff2"


def test_a_reference_cannot_name_a_file_outside_the_bundle(tmp_path: Path) -> None:
    """Delete this and `../` out of the bundle resolves to a file that exists on the machine
    running the audit, and a build reaching outside itself is read as carried."""
    (tmp_path / "outside.woff2").write_bytes(b"x")
    sheet = "@font-face{font-family:X;src:url(../../outside.woff2)}\n" + FONT_SHEET
    assert kinds(bundle(tmp_path / "dist", sheet=sheet)) == [
        A_REFERENCE_IS_A_FILE_THE_BUNDLE_CARRIES_ID
    ]


def test_a_data_address_in_a_stylesheet_is_not_a_request(tmp_path: Path) -> None:
    """The positive case for the address rule: a `data:` image makes no request. Delete this and
    the rule refuses every inlined asset, which is what the bundler does to small files."""
    sheet = FONT_SHEET + "i{background:url(data:image/svg+xml;utf8,<svg/>)}\n"
    assert audit(bundle(tmp_path / "dist", sheet=sheet)) == []


def test_a_script_naming_a_font_host_is_refused_and_one_naming_a_namespace_is_not(
    tmp_path: Path,
) -> None:
    """Scripts carry URLs for reasons that are not requests, so they are held to the narrower rule.
    Delete this and either a library's XML namespace refuses every build, or a script that
    appends a hosted stylesheet to the page passes."""
    namespace = bundle(tmp_path / "a", script='const ns="http://www.w3.org/2000/svg";\n')
    assert audit(namespace) == []
    hosted = bundle(
        tmp_path / "b",
        script='document.head.append(Object.assign(document.createElement("link"),'
        '{href:"https://fonts.googleapis.com/css?family=Inter"}));\n',
    )
    found = audit(hosted)
    assert [(f.kind, f.detail) for f in found] == [
        (A_SCRIPT_NAMES_NO_FONT_HOST_ID, "fonts.googleapis.com")
    ]


def test_every_font_host_on_the_list_is_found_in_a_script(tmp_path: Path) -> None:
    """Delete this and a host dropped from `FONT_HOSTS`, or one the scan stops at the first of,
    goes unnoticed: each is asked for separately."""
    for index, host in enumerate(FONT_HOSTS):
        root = bundle(tmp_path / str(index), script=f'const h="{host}";\n')
        assert [f.detail for f in audit(root)] == [host], host


def test_a_font_family_with_no_section_in_the_licence_notices_is_refused(
    tmp_path: Path,
) -> None:
    """The Open Font Licence asks that its notice travels with the font. Delete this and a font
    ships with no notice, which nobody sees until a copyright holder does."""
    found = audit(bundle(tmp_path / "a", notices=None))
    assert [(f.kind, f.where, f.detail) for f in found] == [
        (A_FONT_HAS_NO_LICENCE_NOTICE_ID, "assets/app-1.css", "Plex Sans")
    ]
    other = "Fonts.\n\n@fontsource/another\n---------------\ntext\n"
    assert kinds(bundle(tmp_path / "b", notices=other)) == [A_FONT_HAS_NO_LICENCE_NOTICE_ID]


def test_a_notice_for_one_family_does_not_cover_another_whose_name_begins_with_it(
    tmp_path: Path,
) -> None:
    """A section for `plex` must not cover `Plex Sans`, and a section for `roboto` must not cover
    `roboto-mono`: the family is matched whole, and never by the start of a file name. Delete this
    and one family's notice stands in for a longer-named family that has none."""
    short = "Fonts.\n\n@fontsource/plex\n------------\ntext\n"
    assert kinds(bundle(tmp_path / "a", notices=short)) == [A_FONT_HAS_NO_LICENCE_NOTICE_ID]
    exact = "Fonts.\n\n@fontsource/plex\n------------\ntext\n\n@fontsource/plex-sans\n--\nt\n"
    assert audit(bundle(tmp_path / "b", notices=exact)) == []


def test_a_family_is_the_package_its_name_hyphenated() -> None:
    """The convention the console's own tests rely on. Delete this and a family with a space in
    it is looked up as written, so no real family is ever found in its notice."""
    assert package_slug("IBM Plex Sans") == "ibm-plex-sans"
    assert package_slug("Poppins") == "poppins"


def test_a_bundle_with_no_font_in_use_is_refused(tmp_path: Path) -> None:
    """A bundle whose stylesheet names no font file passes every other rule vacuously. Delete this
    and a build that lost its fonts reports success, and the console draws in the system face."""
    root = bundle(tmp_path / "dist", sheet="body{margin:0}\n", font_name=None, notices=None)
    assert kinds(root) == [THE_BUNDLE_CARRIES_NO_FONT_ID]


def test_a_directory_with_no_entry_document_is_one_finding_and_nothing_more(
    tmp_path: Path,
) -> None:
    """Delete this and an empty or mistyped directory is read as a clean bundle."""
    (tmp_path / "empty").mkdir()
    assert kinds(tmp_path / "empty") == [THE_BUNDLE_HAS_NO_ENTRY_ID]


def test_the_command_exits_non_zero_on_a_finding_and_zero_on_a_clean_bundle(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """What CI runs. Delete this and the step prints findings and exits 0, so the job is green."""
    clean = bundle(tmp_path / "clean")
    assert bundle_audit.main([str(clean)]) == 0
    assert capsys.readouterr().out.startswith("ok:")
    dirty = bundle(
        tmp_path / "dirty", sheet='@import "https://fonts.bunny.net/x.css";\n' + FONT_SHEET
    )
    assert bundle_audit.main([str(dirty)]) == 1
    assert "refused: assets/app-1.css names another host" in capsys.readouterr().out


@pytest.mark.parametrize(
    "element",
    [
        '<script src="https://cdn.example.invalid/a.js"></script>',
        '<img srcset="/manifest.webmanifest 1x, https://cdn.example.invalid/a.png 2x">',
        '<iframe src="//cdn.example.invalid/frame"></iframe>',
        '<video poster="http://cdn.example.invalid/p.png"></video>',
        '<meta http-equiv="refresh" content="0; url=https://cdn.example.invalid/">',
        '<link rel="stylesheet" href="https://cdn.example.invalid/a.css">',
    ],
)
def test_every_element_that_makes_a_browser_fetch_is_read_for_another_host(
    tmp_path: Path, element: str
) -> None:
    """The entry document is read as a document, attribute by attribute, and not searched for a
    scheme. Delete this and a script, an image set, a frame, a poster, a redirect or a stylesheet
    on another host passes because the check only knew the handful of attributes it was written
    against."""
    entry = ENTRY.replace("<head>", f"<head>{element}")
    found = audit(bundle(tmp_path / "dist", entry=entry))
    assert [(f.kind, f.where) for f in found] == [
        (A_REFERENCE_NAMES_NO_OTHER_HOST_ID, "index.html")
    ]
    assert found[0].detail.startswith(("http://cdn.", "https://cdn.", "//cdn."))


def test_a_srcset_of_the_installs_own_files_is_clean_and_a_comment_is_not_read(
    tmp_path: Path,
) -> None:
    """The positive case for the document reader: an image set of local files, and a comment that
    names a font host to explain the rule, are clean. Delete this and the reader refuses every
    page, or reads the explanation of the rule as a breach of it."""
    entry = ENTRY.replace(
        "<head>",
        "<head><!-- never fonts.googleapis.com -->"
        '<img srcset="/manifest.webmanifest 1x, /manifest.webmanifest 2x">',
    )
    assert audit(bundle(tmp_path / "dist", entry=entry)) == []


def test_a_font_face_whose_file_is_not_a_font_does_not_count_as_one(tmp_path: Path) -> None:
    """A stylesheet whose only `@font-face` points at an image ships no font. Delete this and the
    rule that a bundle must carry a font is satisfied by any file a face names."""
    (tmp_path / "dist").mkdir()
    sheet = '@font-face{font-family:"Plex Sans";src:url(/icon.svg)}\nbody{margin:0}\n'
    root = bundle(tmp_path / "dist2", sheet=sheet, font_name=None)
    (root / "icon.svg").write_text("<svg/>", encoding="utf-8", newline="\n")
    assert THE_BUNDLE_CARRIES_NO_FONT_ID in kinds(root)


# ------------------------------------------------------------------ what the install serves
def client_over(root: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """The product's own fallback route over a bundle, the way the application mounts it."""
    monkeypatch.setattr("brain.console_static.CONSOLE_DIST", root)
    app = FastAPI()
    mount_console_fallback(app)
    return TestClient(app)


def test_a_font_is_served_as_a_font_and_may_be_kept_for_ever(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The install serves its own fonts with the type a font has and the lifetime a hashed file
    may have. Delete this and a font answers `text/plain` on an image with no mime table, or is
    revalidated with the install on every visit."""
    root = bundle(tmp_path / "dist")
    (root / "assets" / "plex-sans-latin-400-normal-AbC123.woff").write_bytes(b"wOFF")
    served = client_over(root, monkeypatch)
    modern = served.get(f"/assets/{FONT_FILE}")
    legacy = served.get("/assets/plex-sans-latin-400-normal-AbC123.woff")
    assert modern.status_code == 200 and legacy.status_code == 200
    assert modern.headers["content-type"] == FONT_CONTENT_TYPES[".woff2"] == "font/woff2"
    assert legacy.headers["content-type"] == FONT_CONTENT_TYPES[".woff"] == "font/woff"
    assert modern.headers["cache-control"] == HASHED_ASSET_CACHE_CONTROL
    # Asserted against figures outside the constant: a year, and never revalidated.
    assert "max-age=31536000" in modern.headers["cache-control"]
    assert "immutable" in modern.headers["cache-control"]


def test_a_font_is_served_as_a_font_even_where_the_machine_knows_no_font_types(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A slim image has no mime table, and the answer is then whatever the interpreter carries. The
    product names the type of every font it serves, so it does not depend on either. Delete this and
    the test above passes on a machine whose table happens to know `.woff2`, and the install serves
    `text/plain` on one whose table does not."""
    monkeypatch.setattr("starlette.responses.guess_type", lambda *_, **__: (None, None))
    served = client_over(bundle(tmp_path / "dist"), monkeypatch)
    assert served.get(f"/assets/{FONT_FILE}").headers["content-type"] == "font/woff2"


def test_only_a_hashed_file_is_cached_for_ever_and_the_licence_notice_is_plain_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sibling: a file outside `assets/` keeps no lifetime, because its name does not change
    when its contents do, and the font notices are readable as text. Delete this and the manifest
    is cached for a year under an unchanging name, or the notice is served as a download."""
    served = client_over(bundle(tmp_path / "dist"), monkeypatch)
    manifest = served.get("/manifest.webmanifest")
    notices = served.get(f"/{FONT_LICENCES_FILE}")
    assert manifest.status_code == 200 and "cache-control" not in manifest.headers
    assert notices.status_code == 200 and notices.text == NOTICES
    assert notices.headers["content-type"].startswith("text/plain")
    assert "cache-control" not in notices.headers
    script = served.get("/assets/app-1.js")
    assert script.headers["cache-control"] == HASHED_ASSET_CACHE_CONTROL


# ------------------------------------------------------------------ the pipeline and the build
def test_the_console_job_audits_the_bundle_it_has_just_built() -> None:
    """CI reads the build's output in the same job that builds it, after the build and not before.
    Delete this and the audit can move above the build, where it reads no bundle and fails, or be
    dropped, where nothing reads the output at all."""
    workflow: dict[Any, Any] = yaml.safe_load(
        (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["console"]["steps"]
    commands = [str(step.get("run", "")) for step in steps]
    built = next(i for i, run in enumerate(commands) if "npm run build" in run)
    audited = [i for i, run in enumerate(commands) if "brain.ops.bundle_audit" in run]
    assert len(audited) == 1 and audited[0] > built
    assert "console/dist" in commands[audited[0]]
    assert "uv run python -m brain.ops.bundle_audit" in commands[audited[0]]


def test_the_real_built_console_passes_where_there_is_one() -> None:
    """Over the real build, in the job that has just made it: no other host, every font carried and
    noticed. Skipped where there is no build. Delete this and the fabricated bundles above are
    the only evidence about what Vite emits."""
    dist = REPO / "console" / "dist"
    if not (dist / "index.html").is_file():
        pytest.skip("this tree has no built console; the console job builds one and runs this")
    assert audit(dist) == []
