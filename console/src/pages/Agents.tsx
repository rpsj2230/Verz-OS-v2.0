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
 * Task ids: M39.1.2.5, M27.8.6
 */

import { Link } from "react-router-dom";
import { ListControls, NOTHING_MATCHES, ShowMore } from "../components/ListControls";
import { narrows, type FilterChoice, type SortChoice } from "../components/listing";
import { useListing } from "../components/useListing";
import type { components } from "../api/schema";
import { AGENT_ADDRESS_PREFIX } from "../components/agentWorkspaceState";
import { readRoster, ROSTER_API_PATH } from "./agentsQuery";
import { FailureNotice } from "../ui/FailureNotice";

/** The page's heading. */
export const ROSTER_HEADING = "Agents";

/** Under the heading. Says what the list is, and nothing about what it is not. */
export const ROSTER_LEDE = "The agents you can open. Each name leads to that agent's workspace.";

/** An empty roster, whichever of the reasons it is empty. */
export const NO_AGENTS = "There are no agents to show.";

/** A truncated roster. A fact about there being more, and never a figure. */
export const MORE_AGENTS = "There are more agents than this page shows.";

/** The accessible name of the table. */
export const ROSTER_LIST_LABEL = "Agents you can open";

export const FILTERS_LABEL = "Narrow the agents";
export const NONE_MATCH = NOTHING_MATCHES;

type RosterRow = components["schemas"]["RosterEntry"];

/** The filters the roster route declares that this screen offers, over values on rows drawn. */
export const ROSTER_FILTERS: readonly FilterChoice<RosterRow>[] = [
  { column: "department", label: "Department", everything: "All departments", read: (row) => row.department },
  { column: "owner_id", label: "Owner", everything: "Anybody", read: (row) => row.owner_id },
];

export const ROSTER_SORTS: readonly SortChoice[] = [
  { value: "", label: "By name" },
  { value: "department", label: "By department" },
  { value: "agent_id", label: "By id" },
];

/**
 * The four columns `docs/screens.html` SCREEN 4 names, under its own words.
 *
 * Four of the design's nine. Runs, cost and the three leash rungs are absent, and they are
 * absent because nothing serves them per agent: a rung has no table on the Python side at all,
 * and a figure per agent would be a second reading of the spend the agent's own page already
 * computes at the basis this reader holds. A column of dashes would say every agent is on the
 * bottom rung and cost nothing, which is two claims nobody measured.
 */
export const AGENT_COLUMN = "Agent";
export const DEPARTMENT_COLUMN = "Dept";
export const OWNER_COLUMN = "Owner";
export const CEILING_COLUMN = "Ceiling";

/** What the table is, said once above it. */
export const ROSTER_CAPTION =
  "Every agent you can open, with the department that can find it, who answers for it, and " +
  "the widest any run through it may reach.";

/** Where the catalogue of installable roles is, and what the link to it says. */
export const TEMPLATES_ADDRESS = "/agent-templates";
export const TEMPLATES_LINK = "Agent templates";

/** Where one agent's workspace is, as `brain.console.workspace.deep_link` spells the prefix. */
export function agentAddress(agentId: string): string {
  return `${AGENT_ADDRESS_PREFIX}${encodeURIComponent(agentId)}`;
}

function RosterAnswerView() {
  const listing = useListing<RosterRow>(ROSTER_API_PATH, { choices: ROSTER_FILTERS });
  const controls = (
    <ListControls label={FILTERS_LABEL} listing={listing} choices={ROSTER_FILTERS} sorts={ROSTER_SORTS} />
  );

  if (listing.failure) {
    return (
      <>
        {controls}
        <FailureNotice failure={listing.failure} />
      </>
    );
  }
  if (listing.busy) {
    return (
      <>
        {controls}
        <p className="note" role="status">
          Loading.
        </p>
      </>
    );
  }
  const roster = readRoster(listing.body);
  if (roster === null) {
    return controls;
  }
  return (
    <>
      {controls}
      {roster.entries.length === 0 ? (
        <p className="note">{narrows(listing.question) ? NONE_MATCH : NO_AGENTS}</p>
      ) : (
        /*
         * Wrapped in `.grid__scroll`, which is not decoration: a ceiling clause and an agent
         * slug are both tokens with nowhere to break, and a table of them at a phone's width
         * takes the document sideways unless the table scrolls inside its own box.
         */
        <div className="grid__scroll">
          <table className="grid__table roster" aria-label={ROSTER_LIST_LABEL}>
            <caption className="grid__caption">{ROSTER_CAPTION}</caption>
            <thead>
              <tr>
                <th scope="col">{AGENT_COLUMN}</th>
                <th scope="col">{DEPARTMENT_COLUMN}</th>
                <th scope="col">{OWNER_COLUMN}</th>
                <th scope="col">{CEILING_COLUMN}</th>
              </tr>
            </thead>
            <tbody>
              {roster.entries.map((entry) => (
                <tr key={entry.agentId}>
                  <th scope="row">
                    <Link to={agentAddress(entry.agentId)}>{entry.displayName}</Link>
                  </th>
                  {/*
                   * An absent field contributes no text, in every one of the three cells. The
                   * cell itself is still there, because a table row with three cells where its
                   * neighbours have four is a table nobody can read; what must not appear is a
                   * word saying something was withheld.
                   */}
                  <td>{entry.department ?? ""}</td>
                  <td>{entry.ownerId === undefined ? "" : <code>{entry.ownerId}</code>}</td>
                  <td>
                    {entry.ceiling === undefined
                      ? ""
                      : entry.ceiling.map((line) => (
                          <code className="roster__clause" key={line}>
                            {line}
                          </code>
                        ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <ShowMore listing={listing} />
      {roster.truncated ? <p className="note">{MORE_AGENTS}</p> : null}
    </>
  );
}

export function Agents() {
  return (
    <article className="page">
      <h1>{ROSTER_HEADING}</h1>
      <p className="lede">{ROSTER_LEDE}</p>
      {/*
       * The way to the catalogue, which is SCREEN 5 and sits under Skills and templates in
       * the design's own navigation. A link from here rather than a section of its own in the
       * menu, because the menu is held against that design by
       * `brain.ops.console_design.navigation_gaps` and the catalogue is not a row in it.
       */}
      <p className="note">
        <Link to={TEMPLATES_ADDRESS}>{TEMPLATES_LINK}</Link>
      </p>
      <RosterAnswerView />
    </article>
  );
}
