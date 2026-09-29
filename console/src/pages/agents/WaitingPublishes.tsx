/**
 * The agent publishes waiting for this reader as the second person, on the Approvals page.
 *
 * `GET /api/v1/agent-drafts` answers them already filtered to the drafts this reader could approve:
 * not their own, and only those whose every capability their own access covers. So a reader with
 * none sees nothing here at all, not an empty heading, and a reader who may not make agents, whom the
 * route answers with the one 404, sees nothing either: a heading over nothing, or a refusal drawn
 * here, would each say something is waiting that they may not see. Each entry opens the draft's
 * publish step, where what it adds is listed beside Approve and Send back, each confirmed.
 *
 * Task ids: M27.15.31
 */

import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useResource } from "../../api/useResource";
import { SectionCard } from "../../components/kit";
import { DRAFTS_API_PATH, draftAddress, kindWords, readDrafts } from "./agentDraftsQuery";

export const WAITING_PUBLISHES_HEADING = "Agents waiting for your approval";
export const WAITING_PUBLISHES_LEDE =
  "Each reaches further than before and needs a second person who is not its author.";

export function WaitingPublishes() {
  const answer = useResource<unknown>(DRAFTS_API_PATH);
  const waiting = useMemo(() => readDrafts(answer.data).waitingForYou, [answer.data]);
  if (answer.failure !== null || answer.busy || waiting.length === 0) {
    return null;
  }
  return (
    <SectionCard title={WAITING_PUBLISHES_HEADING} lede={WAITING_PUBLISHES_LEDE}>
      <ul className="m-0 flex list-none flex-col gap-2 p-0">
        {waiting.map((one) => (
          <li key={one.draftId} className="flex min-w-0 flex-wrap items-center justify-between gap-2">
            <Link to={draftAddress(one.draftId, "publish")} className="font-medium text-ink underline-offset-4 hover:underline">
              {one.name}
            </Link>
            <span className="text-[12.5px] text-dim">{kindWords(one.kind)}</span>
          </li>
        ))}
      </ul>
    </SectionCard>
  );
}
