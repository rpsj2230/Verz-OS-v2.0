/**
 * Skills: every procedure the agents you can see are configured to run, and the review queue.
 *
 * SCREEN 6 of `docs/screens.html`, which is the design of record: Govern section, a library
 * table, a review pane and an upstream-drift card. What is built here is the part of it the API
 * can answer, and the parts it cannot are said in one sentence each rather than drawn empty.
 * `skillsQuery.A_COLUMN_THAT_CAN_ONLY_BE_BLANK_MAKES_A_CLAIM_THE_DATA_DOES_NOT` and
 * `A_CONTROL_WITH_NO_ROUTE_BEHIND_IT_IS_A_BUTTON_THAT_LIES` are the two arguments, and
 * `brain.skill_routes` is where the facts behind them live.
 *
 * **The address is the whole of the state.** `/skills` is the library and `/skills/{name}` is
 * the library with one skill open, so a person can send a colleague the row they are arguing
 * about. Holding the open skill in component state would make it unlinkable and would put the
 * back button somewhere it does not belong. That is `People.tsx`'s arrangement and its reason.
 *
 * **The deep link is resolved against the page and never against a route of its own.** There is
 * no `GET /skills/{name}`, and `brain.govern_routes.
 * A_DEEP_LINK_RESOLVED_AGAINST_THE_PAGE_CANNOT_BE_AN_ORACLE` says why: a route answering one
 * name would answer, for anybody able to type one, whether that skill is in use in an install
 * whose agents they cannot see. The sentence this page says when the name matches nothing is
 * about this page rather than about the company.
 *
 * **Nothing here decides who may see anything.** The request goes out identically for every
 * caller and the API answers from grants this browser never receives. There is no flag on the
 * response that hides a control, because there is no control: this screen makes no write at
 * all, which is the one honest difference between it and the design.
 *
 * **No number about the library is rendered**, for the reason every listing in this console
 * gives: the rows are filtered per caller, so a count is a subtraction. The queue's counts are
 * rendered, because `brain.console.govern_estate.skill_queue` computes them over exactly the
 * entries listed beneath them.
 *
 * Imported statically rather than split, which is `Roles.tsx`'s rule: it mounts neither heavy
 * library and imports no stylesheet of its own, so a chunk for it would buy a round trip and
 * save no bytes.
 *
 * Task ids: M42.6.4
 */

import { Link, useParams } from "react-router-dom";
import { useResource } from "../api/useResource";
import {
  driftingRows,
  readSkillsPage,
  skillAddress,
  skillIn,
  skillsApiPath,
  type SkillLibraryRow,
} from "./skillsQuery";
import { FailureNotice } from "../ui/FailureNotice";

export const SKILLS_HEADING = "Skills";

/**
 * Under the heading. The design's own sentence about what a skill is and where the boundary
 * sits, kept because the wording is the specification's rather than this file's.
 */
export const SKILLS_LEDE =
  "A skill is a folder with instructions and optional scripts, authored anywhere and imported " +
  "here. Import is the security boundary: a skill arrives unreviewed, runs against nothing, " +
  "and only reaches an agent after a named person has read it.";

/** An empty library, whichever of the reasons it is empty. */
export const NO_SKILLS = "There are no skills to show.";

/** A load that came back full. A fact about there being more, and never a figure. */
export const MORE_AGENTS =
  "This page was assembled from a full page of agents, so there are more agents than it covers.";

/**
 * What is said in place of the Source, Ver, Scope, Reviewed and State columns.
 *
 * One sentence, above the table, rather than five empty cells on every row. See
 * `skillsQuery.A_COLUMN_THAT_CAN_ONLY_BE_BLANK_MAKES_A_CLAIM_THE_DATA_DOES_NOT`.
 */
export const REVIEW_IS_NOT_RECORDED =
  "Nothing in this installation stores an imported skill, so no row here can carry the source " +
  "it came from, its version, the person who reviewed it or its review state. What is recorded " +
  "is which agents are configured to run which skill, and the exact bytes each one is pinned to.";

/**
 * What is said in place of the import and assignment controls.
 *
 * See `skillsQuery.A_CONTROL_WITH_NO_ROUTE_BEHIND_IT_IS_A_BUTTON_THAT_LIES`.
 */
export const ASSIGNMENT_IS_NOT_WRITABLE =
  "A skill cannot be imported, approved or assigned to an agent from this screen. Attaching one " +
  "pins the bytes a named person approved, there is nowhere here for that approval to have been " +
  "recorded, and a control that pinned a digest somebody typed would be an approval they granted " +
  "themselves.";

/** What an empty queue means here, which is not that everything has been read. */
export const NOTHING_IS_RECORDED_AS_WAITING =
  "Nothing is recorded as waiting for a reviewer. That is what this installation stores rather " +
  "than a statement that every skill has been read: submissions are held against an imported " +
  "skill, and nothing stores one.";

/** What is said when the address names a skill this page does not carry. */
export const NO_SUCH_SKILL = "No skill on this page has that name.";

/** What the drift card says, in the design's own terms and from the inside. */
export const DRIFT_HEADING = "Version drift";
export const NO_DRIFT =
  "Every skill here is pinned to the same bytes by every agent on this page that runs it.";
export const DRIFT_IS_PINNED_BY_DESIGN =
  "A pin is over bytes rather than over a version number, so a change upstream never reaches a " +
  "live agent on its own. Two agents on different bytes of one skill are running two different " +
  "procedures under one name.";

/** The accessible names of the lists. */
export const LIBRARY_LABEL = "Skills in use";
export const QUEUE_LABEL = "Skills waiting for a reviewer";
export const DRIFT_LABEL = "Skills whose agents run different bytes";
export const PINS_LABEL = "Agents running this skill";

/** The queue's own counts, in words, so a bare number is never the whole sentence. */
export function queueCount(waiting: number, edits: number, stale: number): string {
  return `${String(waiting)} waiting, ${String(edits)} of them edits, ${String(stale)} overdue.`;
}

/** One skill's pins, as the library's Used by column and as the open skill's list. */
function Pins({ row }: { readonly row: SkillLibraryRow }) {
  return (
    <ul className="roster" aria-label={PINS_LABEL}>
      {row.pinned_by.map((pin) => (
        <li key={`${pin.agent_id}-${pin.digest}`}>
          <Link to={`/agents/${encodeURIComponent(pin.agent_id)}`}>{pin.agent_id}</Link>{" "}
          <code>{pin.digest}</code>
        </li>
      ))}
    </ul>
  );
}

function SkillsAnswerView({ openName }: { readonly openName: string | undefined }) {
  const answer = useResource<unknown>(skillsApiPath());

  if (answer.failure) {
    return (
      <FailureNotice failure={answer.failure} />
    );
  }
  if (answer.busy) {
    return (
      <p className="note" role="status">
        Loading.
      </p>
    );
  }

  const page = readSkillsPage(answer.data);
  const open = openName === undefined ? null : skillIn(page.skills, openName);
  const drifting = driftingRows(page.skills);

  return (
    <>
      {page.reviewIsNotRecorded ? <p className="note">{REVIEW_IS_NOT_RECORDED}</p> : null}

      <h2>Library</h2>
      {page.skills.length === 0 ? (
        <p className="note">{NO_SKILLS}</p>
      ) : (
        <ul className="roster" aria-label={LIBRARY_LABEL}>
          {page.skills.map((row) => (
            <li key={row.name}>
              <Link to={skillAddress(row.name)}>{row.name}</Link>
              <Pins row={row} />
            </li>
          ))}
        </ul>
      )}

      {page.truncated ? <p className="note">{MORE_AGENTS}</p> : null}

      {open === null ? null : (
        <section className="card">
          <h2>{open.name}</h2>
          <Pins row={open} />
          <p className="note">{ASSIGNMENT_IS_NOT_WRITABLE}</p>
        </section>
      )}

      {openName !== undefined && open === null ? (
        <p className="note">{NO_SUCH_SKILL}</p>
      ) : null}

      <h2>Awaiting review</h2>
      {page.queue.length === 0 ? (
        <p className="note">{NOTHING_IS_RECORDED_AS_WAITING}</p>
      ) : (
        <>
          <ul className="roster" aria-label={QUEUE_LABEL}>
            {page.queue.map((entry) => (
              <li key={entry.name}>
                {entry.name} <span className="note">{entry.waiting_since}</span>
                {entry.changed.length === 0 ? null : (
                  <span className="note">
                    {" "}
                    changed: {entry.changed.join(", ")}
                  </span>
                )}
              </li>
            ))}
          </ul>
          <p className="note">{queueCount(page.waiting, page.edits, page.stale)}</p>
        </>
      )}

      <h2>{DRIFT_HEADING}</h2>
      {drifting.length === 0 ? (
        <p className="note">{NO_DRIFT}</p>
      ) : (
        <ul className="roster" aria-label={DRIFT_LABEL}>
          {drifting.map((row) => (
            <li key={row.name}>
              <Link to={skillAddress(row.name)}>{row.name}</Link>
            </li>
          ))}
        </ul>
      )}
      <p className="note">{DRIFT_IS_PINNED_BY_DESIGN}</p>

      {page.assignmentIsNotWritable && open === null ? (
        <p className="note">{ASSIGNMENT_IS_NOT_WRITABLE}</p>
      ) : null}
    </>
  );
}

export function Skills() {
  const { name } = useParams();

  return (
    <article className="page">
      <h1>{SKILLS_HEADING}</h1>
      <p className="lede">{SKILLS_LEDE}</p>
      <SkillsAnswerView openName={name} />
    </article>
  );
}
