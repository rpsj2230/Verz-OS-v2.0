"""An agent producing a Word document from an approved company template (M12.3.5).

Off because it is a new way for a run to put a file in a person's name: the tool reads a template
at the run's reach and keeps what it makes as an artifact, and the owner has not yet answered which
formats follow Word (needs-rupash 193). Turning it on lets an agent whose ceiling names the tool
fill an approved template and hand the person the file; nothing else about a run changes.

Task ids: M12.3.5
"""

from __future__ import annotations

from typing import Final

from brain.ops.feature_model import Feature

DOCUMENT_GENERATION: Final = Feature(
    name="document_generation",
    title="Let an agent produce a Word document from an approved template",
    what=(
        "An agent whose ceiling names the document tool can fill a company template, a document "
        "in the knowledge library of kind Template that a person has verified and that the "
        "person asking may read, and keep the result as a file for that person. The file holds "
        "only the template and the words the agent supplied for it, so it holds nothing the "
        "person asking could not see. Slide decks and spreadsheets are not offered."
    ),
    while_off=(
        "The tool answers as an unavailable tool does and nothing is produced. Files already "
        "produced stay where they are and are opened as before."
    ),
    read_by=("brain.tools.document_generation:generation_is_on",),
)
