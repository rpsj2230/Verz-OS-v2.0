"""Registering an outside AI service, such as image generation or speech to text (M12.3.7).

Off because it puts a new kind of tool in the catalogue: one that, once a call path exists, sends a
person's material to an outside company. Today turning it on registers the services an install has
declared as tools that need their own permission, count as sending something out, and are offered to
no agent whose ceiling does not name them; nothing calls one yet, because which service comes first
is the owner's to say (needs-rupash 184).

Task ids: M12.3.7
"""

from __future__ import annotations

from typing import Final

from brain.ops.feature_model import Feature

EXTERNAL_AI_SERVICES: Final = Feature(
    name="external_ai_services",
    title="Register outside AI services as tools an agent must be given",
    what=(
        "Each outside AI service this install has declared, a service that is not a chat model, "
        "such as image generation or speech to text, is put in the tool catalogue with a "
        "permission of its own and counted as a tool that sends something out, so a person "
        "approves each call. An agent is shown one only when its tools name it and the person "
        "asking holds its permission. Services are registered when the application starts, so a "
        "change here applies at the next start. Nothing calls a service yet."
    ),
    while_off=(
        "No outside service is in the catalogue, whatever has been declared, and no agent can be "
        "given one. Declarations are kept and are registered the next time the application starts "
        "with this on."
    ),
    read_by=("brain.ops.external_ai_store:services_are_on",),
)
