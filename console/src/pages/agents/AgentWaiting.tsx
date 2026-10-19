/**
 * What is waiting on a person for one agent: the Approvals queue narrowed to the agent.
 *
 * **It is the queue and nothing else.** `GET /approvals?filter=agent_id:<id>` is the Approvals
 * screen's own route, so the cards are the ones the signed-in reader could decide, and a reader who
 * could decide none of this agent's is sent an empty page, which is the page an agent that does not
 * exist sends too. **No card means no block**: this draws nothing at all for a reader with nothing to
 * decide, never a heading over "0", because a nought here would be a figure about approvals the
 * reader was not offered. While the request is on its way, or has failed, it also draws nothing:
 * the Approvals page is one press away in the header and says why when a queue cannot be read.
 *
 * Task ids: M27.15.30, M27.10.2
 */

import { ArrowUpRight } from "lucide-react";
import { Link } from "react-router-dom";
import { useResource } from "../../api/useResource";
import { SectionCard } from "../../components/kit";
import { approvalsForAgentApiPath, readApprovalQueue } from "../approvalsQuery";
import { WORKS_AT } from "./agentActions";

export const WAITING = "Waiting on a person";
export const WAITING_LEDE = "Actions this agent stopped before they happened, for a person who may decide them.";
export const MORE_WAITING = "There are more on the Approvals page.";

export function AgentWaiting({ agentId }: { readonly agentId: string }) {
  const asked = useResource<unknown>(approvalsForAgentApiPath(agentId));
  const queue = asked.data === null ? null : readApprovalQueue(asked.data);
  if (queue === null || queue.cards.length === 0) {
    return null;
  }
  return (
    <SectionCard
      title={WAITING}
      lede={WAITING_LEDE}
      action={
        <Link to={WORKS_AT.approvals} className="inline-flex items-center gap-1 text-[12px] text-acc-text underline-offset-4 hover:underline">
          Approvals <ArrowUpRight aria-hidden className="size-3" />
        </Link>
      }
    >
      <ul className="m-0 flex list-none flex-col gap-2 p-0">
        {queue.cards.map((card) => (
          <li key={card.suspensionId} className="text-[13px] text-ink">
            <Link to={`${WORKS_AT.approvals}/${encodeURIComponent(card.suspensionId)}`} className="underline-offset-4 hover:underline">
              {card.request}
            </Link>
          </li>
        ))}
      </ul>
      {queue.truncated ? <p className="m-0 mt-2 text-[12px] text-dim">{MORE_WAITING}</p> : null}
    </SectionCard>
  );
}
