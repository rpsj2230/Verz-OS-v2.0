/**
 * The agent roster: every agent this reader may see, each a link to its workspace.
 *
 * **This is where the workspace's way back lands, and it is the half of M39.1.2.5 that was
 * missing.** `AgentWorkspace` puts a link to `ROSTER_ADDRESS` first in the workspace and moves
 * focus to it on Escape, and until this page existed following that link reached the console's
 * not-found page. The keyboard route is now a loop: Escape, Enter, and an agent's name is a
 * link again.
 *
 * **Nothing on this page decides who is listed.** The API filters by audience before it bounds
 * the answer, and this page draws what arrived, in the order it arrived. There is no count
 * above the list, no "and more" with a number in it, and no entry drawn for an agent the reader
 * may not open. See `A_ROSTER_DRAWS_WHAT_IT_WAS_SENT_AND_COUNTS_NOTHING`.
 *
 * **An empty roster says so in words that are true for every reason it could be empty.** A
 * company with no agents and a reader whose audience covers none of them are one sentence,
 * because the page cannot tell them apart and must not try.
 *
 * Imported statically rather than split. It reaches nothing the shell does not already reach,
 * which is `App.tsx`'s rule for `Overview` and `NotFound`: a chunk for it would buy a round trip
 * and save no bytes.
 *
 * Task ids: M39.1.2.5
 */

import { Link } from "react-router-dom";
import { useResource } from "../api/useResource";
import { AGENT_ADDRESS_PREFIX } from "../components/agentWorkspaceState";
import { Notice } from "../ui/Notice";
import { readRoster, ROSTER_API_PATH } from "./agentsQuery";
import { SOMETHING_DID_NOT_WORK } from "./Overview";

/** The page's heading. */
export const ROSTER_HEADING = "Agents";

/** Under the heading. Says what the list is, and nothing about what it is not. */
export const ROSTER_LEDE = "The agents you can open. Each name leads to that agent's workspace.";

/** An empty roster, whichever of the reasons it is empty. */
export const NO_AGENTS = "There are no agents to show.";

/** A truncated roster. A fact about there being more, and never a figure. */
export const MORE_AGENTS = "There are more agents than this page shows.";

/** The accessible name of the list. */
export const ROSTER_LIST_LABEL = "Agents you can open";

/** Where one agent's workspace is, as `brain.console.workspace.deep_link` spells the prefix. */
export function agentAddress(agentId: string): string {
  return `${AGENT_ADDRESS_PREFIX}${encodeURIComponent(agentId)}`;
}

function RosterAnswerView() {
  const answer = useResource<unknown>(ROSTER_API_PATH);

  if (answer.failure) {
    return (
      <Notice title={SOMETHING_DID_NOT_WORK} traceId={answer.failure.traceId}>
        <p>{answer.failure.message}</p>
      </Notice>
    );
  }
  if (answer.busy) {
    return (
      <p className="note" role="status">
        Loading.
      </p>
    );
  }
  const roster = readRoster(answer.data);
  if (roster === null) {
    return null;
  }
  return (
    <>
      {roster.entries.length === 0 ? (
        <p className="note">{NO_AGENTS}</p>
      ) : (
        <ul className="roster" aria-label={ROSTER_LIST_LABEL}>
          {roster.entries.map((entry) => (
            <li key={entry.agentId}>
              <Link to={agentAddress(entry.agentId)}>{entry.displayName}</Link>
            </li>
          ))}
        </ul>
      )}
      {roster.truncated ? <p className="note">{MORE_AGENTS}</p> : null}
    </>
  );
}

export function Agents() {
  return (
    <article className="page">
      <h1>{ROSTER_HEADING}</h1>
      <p className="lede">{ROSTER_LEDE}</p>
      <RosterAnswerView />
    </article>
  );
}
