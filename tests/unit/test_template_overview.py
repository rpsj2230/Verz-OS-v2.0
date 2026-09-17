"""`identity.overview` arrives as manifest schema v2 without breaking a v1 signature.

Task ids: M27.11.16
"""

from __future__ import annotations

from datetime import UTC, datetime

from brain.agent_routes import manifest_of
from brain.agents.template import (
    MANIFEST_PATHS_V1,
    MANIFEST_SCHEMA_V1,
    ManifestIdentity,
    SignedManifest,
    TemplateManifest,
    _digest,
    canonical,
    content_digest,
    publish,
    verify,
)

KEY = "a-test-key"
AT = datetime(2019, 1, 1, tzinfo=UTC)


def _manifest(overview: str = "") -> TemplateManifest:
    return TemplateManifest(
        identity=ManifestIdentity(
            template_id="queue_triager",
            version=1,
            published_by="author",
            display_name="Queue triager",
            overview=overview,
        ),
        persona="Triage the queue.",
    )


def test_a_stored_v1_template_still_verifies_and_reads() -> None:
    """Delete this and adding a path can silently break every signed template version.

    The v1 document and digest are built by hand from the v1 path list, as a row signed
    before the field existed would hold them.
    """
    document = {p: v for p, v in _manifest().document().items() if p in MANIFEST_PATHS_V1}
    assert "identity.overview" not in document
    v1_digest = _digest((MANIFEST_SCHEMA_V1, canonical(document)))
    signed = publish(_manifest(), key=KEY, signed_by="author", at=AT)
    assert signed.content_digest == v1_digest
    rebuilt = SignedManifest(
        manifest=manifest_of(document),
        content_digest=v1_digest,
        signature=signed.signature,
        signed_by="author",
        signed_at=AT,
    )
    verify(rebuilt, key=KEY)
    assert rebuilt.manifest.identity.overview == ""


def test_a_v2_overview_is_inside_the_digest_and_round_trips() -> None:
    """Delete this and an overview edited after signing would load as if signed."""
    signed = publish(_manifest("How we use it."), key=KEY, signed_by="author", at=AT)
    assert signed.content_digest != content_digest(_manifest())
    rebuilt = manifest_of(signed.manifest.document())
    assert rebuilt.identity.overview == "How we use it."
    verify(signed, key=KEY)
