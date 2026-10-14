/**
 * The personal agents a reader holding the audit capability may be told exist, drawn above the
 * Agents list, for oversight (M39.10.3).
 *
 * **A list that names and offers nothing.** Each row is the agent's name, whose it is and whether it
 * is running, and none of it is a link: the reader may not open it, ask it or see what its owner
 * connected to it, so a link would be a door the API shuts. `GET /api/v1/agent-oversight` decides who
 * is on it (`brain.agents.oversight`), and the page draws what arrived in the order it arrived.
 *
 * **No count, ever, and nothing when there is nothing.** The section is absent for a reader the API
 * told of no agent, whatever the reason: the API answers the same empty list to a reader who holds no
 * audit capability, to an install with the switch off and to an install with no personal agent, so a
 * heading drawn over an empty list would be the one thing that told those apart. For the same reason
 * a failed request draws nothing: the Agents list beneath it already says if the Brain could not be
 * reached, and a second notice for a section nobody was promised would be noise.
 *
 * Task ids: M39.10.3
 */

import { useMemo } from "react";
import { useResource } from "../../api/useResource";
import { SectionCard } from "../../components/kit";
import { StatePill } from "./pills";

export const OVERSIGHT_API_PATH = "/agent-oversight";
export const OVERSIGHT_HEADING = "Personal agents under oversight";
export const OVERSIGHT_LEDE =
  "You hold the audit capability for these personal agents, so you are told that they exist and whose they are. " +
  "You cannot open them, ask them or see what their owners connected to them; what changed is on the audit log.";
export const OVERSIGHT_LIST_LABEL = "Personal agents you may oversee";

/** One personal agent as oversight tells of it. */
export interface OverseenShown {
  readonly agentId: string;
  readonly displayName: string;
  readonly ownerName: string;
  readonly state: string;
}

type Fields = Readonly<Record<string, unknown>>;

function fieldsOf(value: unknown): Fields | null {
  // A cast at the boundary, where proving a structural match buys nothing: every field is read back
  // through a type test below.
  return typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Fields) : null;
}

/** The agents out of the oversight body: an entry with its id and name, once, in the order it came. */
export function readOverseen(payload: unknown): readonly OverseenShown[] {
  const items = fieldsOf(payload)?.["items"];
  if (!Array.isArray(items)) {
    return [];
  }
  const seen = new Set<string>();
  const rows: OverseenShown[] = [];
  for (const item of items as readonly unknown[]) {
    const entry = fieldsOf(item);
    const agentId = entry?.["agent_id"];
    const displayName = entry?.["display_name"];
    if (entry === null || typeof agentId !== "string" || typeof displayName !== "string" || seen.has(agentId)) {
      continue;
    }
    seen.add(agentId);
    const ownerName = typeof entry["owner_name"] === "string" && entry["owner_name"] !== "" ? entry["owner_name"] : "";
    rows.push({
      agentId,
      displayName,
      ownerName: ownerName === "" ? (typeof entry["owner_id"] === "string" ? entry["owner_id"] : "") : ownerName,
      state: typeof entry["state"] === "string" ? entry["state"] : "",
    });
  }
  return rows;
}

export function AgentOversight() {
  const answer = useResource<unknown>(OVERSIGHT_API_PATH);
  const rows = useMemo(() => (answer.data === null ? [] : readOverseen(answer.data)), [answer.data]);
  if (rows.length === 0) {
    return null;
  }
  return (
    <SectionCard title={OVERSIGHT_HEADING} lede={OVERSIGHT_LEDE}>
      <ul aria-label={OVERSIGHT_LIST_LABEL} data-slot="agent-oversight" className="m-0 flex list-none flex-col gap-2 p-0">
        {rows.map((one) => (
          <li key={one.agentId} className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
            <span className="min-w-0 font-medium text-ink">{one.displayName}</span>
            {one.ownerName === "" ? null : <span className="min-w-0 text-[12px] text-dim">{one.ownerName}</span>}
            {one.state === "" ? null : <StatePill state={one.state} />}
          </li>
        ))}
      </ul>
    </SectionCard>
  );
}
