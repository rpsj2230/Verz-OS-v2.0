"""Reading documents and meaning with the install's own model server (needs-rupash 119 and 120).

Off because it is the first thing in this product that loads a machine-learning model, and the
owner's server has no memory to spare for one until somebody has chosen which parts to run. The
switch is the product's half of that choice: it says whether a document is ever sent to the model
server, and `INSTALL_SERVICES` naming `modelserver` is the server's half, which says whether a
release starts it. Either alone does nothing, and that is on purpose: a service nobody sends work
to costs memory for nothing, and work sent to a service nobody started waits in the queue and is
never lost.

Task ids: M7.2.1, M7.3.3
"""

from __future__ import annotations

from typing import Final

from brain.ops.feature_model import Feature

MODEL_SERVER: Final = Feature(
    name="model_server",
    title="Read documents and find passages by meaning with this install's own model server",
    what=(
        "Uploaded documents are read by the model server's parts this install has chosen: tables "
        "and page layout in PDFs and Office files, scanned pages, and a general reader for formats "
        "the first cannot open. Passages are embedded by the install's own embedding model, so a "
        "question finds a passage by what it means as well as by its words. Names and details the "
        "standard rules miss are found by the entity part when it is chosen. The server holds "
        "memory only while work is waiting for it, and work sent while it is not running waits in "
        "the queue."
    ),
    while_off=(
        "Documents are read as they are today, in the application, as text, and nothing is sent "
        "to a model server. Search finds passages by their words alone. Nothing already stored "
        "changes."
    ),
    read_by=(
        "brain.ops.model_server_store:model_server_is_on",
        "brain.settings_routes:model_server",
    ),
)
