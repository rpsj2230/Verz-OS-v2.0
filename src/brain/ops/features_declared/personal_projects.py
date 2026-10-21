"""Personal projects: a person groups their threads and documents and a run reads the documents.

Off because a new capability ships switched off on every install, and because the second half is
a change to what a run is shown: with a project named, a question is answered with the project's
documents read ahead of the search, which no question did before. `brain.project_context` asks the
switch before a project is made, before a thread or document is listed in one and before a run reads
a project's documents, and never before a project is listed, renamed, put away or emptied: a switch
turned off must not leave a person unable to see or tidy what they made.

Task ids: M40.7.7
"""

from __future__ import annotations

from typing import Final

from brain.ops.feature_model import Feature

PERSONAL_PROJECTS: Final = Feature(
    name="personal_projects",
    title="Personal projects that group a person's threads and documents",
    what=(
        "A person can make a project of their own, list their own threads and documents they may "
        "read in it, and ask a question inside it. The question is then answered with those "
        "documents read as project context, at the reach the person holds when they ask, and a "
        "document they can no longer read is left out without a word. A project is context for "
        "a run and is never kept as memory. Nobody else can see or use a person's project."
    ),
    while_off=(
        "No project can be made, nothing can be added to one, and a question asked inside one is "
        "answered as an ordinary question. Projects already made can still be seen, renamed, "
        "put away and emptied."
    ),
    read_by=("brain.project_context:projects_are_on",),
)
