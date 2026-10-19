"""The sentence that explains one act the console cannot offer, over HTTP.

`brain.console.explanations` holds every sentence and says why the server is where they live.
This is the route a page asks when it draws one: `GET /console/explanations/{act}`, answered with
the sentence, the form it is drawn in and its lead.

**The reader is admitted and then ignored.** Every route here is behind sign-in, like the menu
beside it, so an anonymous request learns nothing about what this product does and does not
offer. Nothing past that is asked of the reader: `explanation_for` takes no principal, so two
readers holding different grants are answered the same bytes, and `tests/unit/
test_console_explanations.py` asks as two of them and compares. That is the DENIED-and-ABSENT
rule applied to a sentence: it cannot say why this reader in particular may not.

**An act nobody registered is the ordinary 404.** `Absent` is the same answer an unknown entity
gets, so the route is not an oracle for which acts exist beyond the ones a page names.

Task ids: M27.15.70
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.console.explanations import Explanation, explanation_for
from brain.core.errors import Absent


class ExplanationView(BaseModel):
    """One explanation as the console draws it: the form, the lead and the sentence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    act: str
    form: str
    lead: str
    sentence: str


def explanation_view(one: Explanation) -> ExplanationView:
    """One explanation, copied field by field. `retired_by` stays on the server."""
    return ExplanationView(
        act=one.act, form=one.form.value, lead=one.lead.value, sentence=one.sentence
    )


router = APIRouter(prefix=API_PREFIX, tags=["console"])


@router.get(
    "/console/explanations/{act}", response_model=ExplanationView, responses=COMMON_RESPONSES
)
async def console_explanation(act: str, asked: Asked) -> ExplanationView:
    """Why one act cannot be done, in the words every screen uses for it."""
    del asked  # admitted, and deliberately not consulted: see the module docstring.
    one = explanation_for(act)
    if one is None:
        raise Absent(f"no explanation is registered for {act!r}")
    return explanation_view(one)
