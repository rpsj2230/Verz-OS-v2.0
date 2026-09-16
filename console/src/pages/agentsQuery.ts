/**
 * What the roster asks the API for, and how an answer becomes the list it draws.
 *
 * **The list is the API's, and nothing here decides who is on it.** `GET /api/v1/agents`
 * answers with the agents this reader's audience covers, filtered by
 * `brain.agents.model.visible_agent_ids` before the page is bounded, so an agent the reader
 * may not see is not in the body at all. This file has nothing to filter with and filters
 * nothing: it drops an entry that does not say which agent it is, and a second entry for an
 * agent already read, and carries every other entry in the order it arrived.
 *
 * **Five fields an entry, and none of them is a count or a state.** An id, which is the
 * address of the agent's workspace; a name, which is what a person looks for; and the three
 * columns `docs/screens.html` SCREEN 4 puts beside them: the department, the steward and the
 * ceiling. The route sends the first two to everybody its audience covers, because they are
 * what the agent's own page already tells the same reader, and the ceiling only to a reader
 * holding the Agents screen's read. A body carrying a lifecycle word or a total reaches
 * nothing here, because the reader never takes it: a roster that greyed out an agent or
 * counted the list would be telling the reader about agents they may not see. See
 * `A_ROSTER_DRAWS_WHAT_IT_WAS_SENT_AND_COUNTS_NOTHING`.
 *
 * **`truncated` is a fact without a number.** The API sets it when there are more agents
 * this reader may see than one answer carries. It is carried only when it is exactly `true`,
 * so a string or a number in its place is no claim at all, which is the direction a flag about
 * hidden rows has to fail in.
 *
 * Task ids: M39.1.2.5
 */

import { scopeLines } from "./scopeText";

/** Written down because every screen of rows here is tempted by a count above it. */
export const A_ROSTER_DRAWS_WHAT_IT_WAS_SENT_AND_COUNTS_NOTHING =
  "The roster is a listing, and a listing is where a hidden count leaks: a total beside a " +
  "list filtered by audience is the number of agents the reader was not told about. So the " +
  "roster draws the entries the API sent, in the order it sent them, as links, and draws " +
  "no number anywhere. An agent outside the reader's audience is absent, never greyed out.";

/** Where the roster is asked for, under the API base. */
export const ROSTER_API_PATH = "/agents";

/**
 * One agent on the roster, as `docs/screens.html` SCREEN 4 tabulates one.
 *
 * The id and the name are required, because an agent in the body is one this reader may open.
 * The department, the steward and the ceiling are answers the API gives separately, and an
 * absent key is carried as an absent field rather than as a blank: a column reading unknown
 * where a ceiling goes would say this agent has one the reader may not be told about.
 */
export interface RosterEntryView {
  readonly agentId: string;
  readonly displayName: string;
  /** The department whose people can find it, for an agent whose audience is a department's. */
  readonly department?: string;
  /** `AgentAudience.owner_id`: who answers for this agent now, never who built it. */
  readonly ownerId?: string;
  /**
   * The widest any run through this agent may reach, as lines of `brain.core.scope.Clause`.
   *
   * Rendered by `scopeLines`, which is the console's one rendering of a scope, so the ceiling
   * column here and a rung's scope on the routing matrix cannot disagree about what a clause
   * says. An unrestricted ceiling yields no lines and the cell is empty, which is that
   * module's own rule: this agent narrows no rows of its own, and a word like "all" would be
   * this browser naming a state the payload does not carry.
   */
  readonly ceiling?: readonly string[];
}

/** The roster as this console holds it. Two fields, and neither is a count. */
export interface RosterAnswer {
  readonly entries: readonly RosterEntryView[];
  /** There are more agents this reader may see than the answer carried. Never how many. */
  readonly truncated: boolean;
}

function said(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

/**
 * The roster out of a response body, or `null` when the body is not a roster.
 *
 * `null` rather than an empty list for a body with no `items` array, for the reason
 * `readAgentWorkspace` gives: an empty list is a claim that the reader may see no agents, and
 * a body that is not a roster makes no such claim.
 */
export function readRoster(payload: unknown): RosterAnswer | null {
  if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
    return null;
  }
  // A cast at the boundary, where proving a structural match buys nothing: every value is read
  // back through `said` or an exact comparison below.
  const fields = payload as Readonly<Record<string, unknown>>;
  const items = fields["items"];
  if (!Array.isArray(items)) {
    return null;
  }
  const seen = new Set<string>();
  const entries: RosterEntryView[] = [];
  for (const item of items as readonly unknown[]) {
    const entry =
      typeof item === "object" && item !== null && !Array.isArray(item)
        ? (item as Readonly<Record<string, unknown>>)
        : undefined;
    const agentId = said(entry?.["agent_id"]);
    const displayName = said(entry?.["display_name"]);
    if (agentId === undefined || displayName === undefined || seen.has(agentId)) {
      continue;
    }
    seen.add(agentId);
    const department = said(entry?.["department"]);
    const ownerId = said(entry?.["owner_id"]);
    const ceiling = scopeLines(entry?.["ceiling"]);
    entries.push({
      agentId,
      displayName,
      ...(department === undefined ? {} : { department }),
      ...(ownerId === undefined ? {} : { ownerId }),
      // A scope with no clauses and an absent ceiling are one absence here, which is what
      // `scopeLines` already answers for both: an unrestricted ceiling narrows nothing and a
      // withheld one is not this reader's to see, and neither is a cell with words in it.
      ...(ceiling.length === 0 ? {} : { ceiling }),
    });
  }
  return { entries, truncated: fields["truncated"] === true };
}
