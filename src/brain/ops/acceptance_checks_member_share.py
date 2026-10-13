"""Install acceptance check for handing an artifact to a colleague (M40.3.3.3).

A member of acceptance_a whose agent made a file shares it with a colleague who already reaches
artifacts, and the colleague finds it under what was shared with them and opens it, as the routes
My workspace calls do, signed in through the install's own gate. **What the check is for is the
three things sharing must not do**: reach somebody who does not already reach it, grant anything
beyond the moment of the read, or survive being taken back. Each is asked beside the act that works.

**The file is kept in memory.** The artifact is written through the product's own store over an
object store held in this process, so nothing reaches a bucket and the rows are rolled back with the
check; what is proved is the share's verdict and the read, not the bucket.

Task ids: M40.3.3.3
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Final

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_people_signed_in import console
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1930

A, B = RESERVED_DEPARTMENTS

#: What the file holds, and what the colleague must read back.
CONTENT: Final = b"acceptance shared file"


class _Shelf:
    """An object store held in memory: a produced file is kept nowhere but this process."""

    def __init__(self) -> None:
        self.kept: dict[str, bytes] = {}

    def put_object(self, bucket_name: str, key: str, body: bytes, content_type: str) -> None:
        self.kept[f"{bucket_name}/{key}"] = body

    def get_object(self, bucket_name: str, key: str) -> bytes:
        return self.kept[f"{bucket_name}/{key}"]

    def delete_object(self, bucket_name: str, key: str) -> None:
        self.kept.pop(f"{bucket_name}/{key}", None)

    def list_objects(self, bucket_name: str, prefix: str) -> Any:
        return iter(())


async def _refused(call: Any) -> bool:
    """Whether a call was answered with the one refusal, `Absent`, and nothing else."""
    from brain.core.errors import Absent

    try:
        await call
    except Absent:
        return True
    return False


@check(
    leaves=("M40.3.3.3",),
    sentence=(
        "A member shares a file an agent made for them with a colleague who already reaches "
        "artifacts: it is listed for the colleague with who shared it and the colleague opens it; "
        "a colleague who does not reach artifacts, oneself and a stranger are refused in words; a "
        "share taken back is gone; and a share whose colleague has since lost their reach lists "
        "and opens nothing."
    ),
)
async def a_member_hands_a_file_to_a_colleague_who_can_already_open_it(h: Harness) -> None:
    from brain.console.agent_output import ARTIFACT_CAPABILITY, ArtifactInput, ArtifactKind
    from brain.core.field_policy import Classification
    from brain.govern_routes import retire_grant
    from brain.member_share_routes import (
        ShareAsked,
        my_shares,
        open_shared_artifact,
        share_my_artifact,
        shared_with_me,
        withdraw_my_share,
    )
    from brain.ops.acceptance_workspace import installed_agent
    from brain.ops.artifact_store import Produced, StoredArtifacts
    from brain.ops.retention import DataClass

    await h.found_departments()
    c = await console(h)
    maker, colleague, outsider = (h.principal(A, role) for role in ("maker", "friend", "outsider"))
    await h.person(maker, department=A)
    await h.person(
        colleague, department=A, grants=((ARTIFACT_CAPABILITY.value, Scope.unrestricted()),)
    )
    await h.person(outsider, department=A)
    agent = await installed_agent(h, maker, suffix="_share")
    store = StoredArtifacts(h.sessions, _Shelf(), "acceptance")
    made = await store.keep(
        Produced(
            agent_id=agent,
            kind=next(iter(ArtifactKind)),
            run_id=f"acceptance_{h.run}_share_run",
            agent_version="1",
            caller_id=maker,
            reach=await h.reach(maker),
            inputs=(
                ArtifactInput(
                    label="ticket",
                    data_class=DataClass.BUSINESS_RECORD,
                    classification=Classification.INTERNAL,
                ),
            ),
            body=CONTENT,
            content_type="text/plain",
        ),
        at=h.now - timedelta(minutes=1),
    )
    c.app.state.artifacts = store
    c.app.state.artifact_source = store.every

    async def sharing(who: str, with_whom: str) -> Any:
        with c.as_route():
            return await share_my_artifact(
                c.request("POST"),
                made.artifact_id,
                ShareAsked(colleague=with_whom),
                await c.asked(who, strong=False),
            )

    async def listed(who: str) -> list[str]:
        with c.as_route():
            page = await shared_with_me(c.request(), await c.asked(who, strong=False))
        return [one.artifact.artifact_id for one in page.items]

    async def opened(who: str) -> bytes:
        with c.as_route():
            got = await open_shared_artifact(
                c.request(), made.artifact_id, await c.asked(who, strong=False)
            )
        return bytes(got.body)

    for refused_one in (
        await sharing(maker, outsider),
        await sharing(maker, maker),
        await sharing(maker, f"acceptance-{h.run}-nobody"),
    ):
        if getattr(refused_one, "status_code", 200) != 422:
            raise CheckFailedError("a file was shared with somebody who could not open it")
    if await listed(outsider) or await listed(colleague):
        raise CheckFailedError("a refused share was listed")

    done = await sharing(maker, colleague)
    if getattr(done, "artifact_id", "") != made.artifact_id:
        raise CheckFailedError("a file was not shared with a colleague who could already open it")
    if await listed(colleague) != [made.artifact_id] or await listed(outsider):
        raise CheckFailedError("a share was not listed for the colleague alone")
    with c.as_route():
        sent = await my_shares(c.request(), await c.asked(maker, strong=False))
    if [(one.artifact_id, one.shared_with) for one in sent.shares] != [
        (made.artifact_id, colleague)
    ]:
        raise CheckFailedError("a person was not shown what they had shared")
    if await opened(colleague) != CONTENT:
        raise CheckFailedError("a colleague could not open what was shared with them")
    if not await _refused(opened(outsider)):
        raise CheckFailedError("a person it was not shared with opened the file")

    with c.as_route():
        gone = await withdraw_my_share(
            c.request("POST"),
            made.artifact_id,
            ShareAsked(colleague=colleague),
            await c.asked(maker, strong=False),
        )
    if gone.artifact_id != made.artifact_id or await listed(colleague):
        raise CheckFailedError("a share taken back was still listed")
    if not await _refused(opened(colleague)):
        raise CheckFailedError("a share taken back could still be opened")

    await sharing(maker, colleague)
    await h.execute(*h.attributed(), retire_grant(colleague, ARTIFACT_CAPABILITY.value))
    if await listed(colleague) or not await _refused(opened(colleague)):
        raise CheckFailedError("a share granted a colleague what they no longer reach")
