/**
 * Department: the overview `docs/screens.html` SCREEN 2 draws for somebody who runs one department.
 *
 * **Every card is a read another screen of the department's console already makes, and nothing
 * here is a read of its own.** The design draws a figure row, the agents and their leashes, the
 * queues waiting on the admin and the questions nobody could answer. Each of those has a screen
 * behind it that the API already narrows per reader: Usage for questions and who asked them,
 * Agents and leashes for the roster, Gaps for what cannot be answered. So this page asks those
 * three routes, draws a card from each and links to the screen it came from. A department admin
 * is shown their department on every card because each route decided that, and a company
 * administrator who opens this address is shown the company's, because nothing here narrows
 * anything. `brain.console.department_console` decides who is offered the page in a menu.
 *
 * **Rejected: an overview route of its own.** A single response carrying usage, agents and gaps
 * would be a second door to three sets of rows under a fourth decision, and the fourth would drift
 * from the three. It is also the shape `brain.operate_routes.A_FIGURE_ANOTHER_ROUTE_SERVES_IS_READ_THERE`
 * refuses for the models screen.
 *
 * **What the design draws and this page does not, said on the page.** Answered, escalated and
 * budget figures, the rung-by-rung leash matrix and the counts on the queues. Nothing on an
 * install records how a question ended, the roster carries no rung, and a count beside a queue is
 * a figure no route here serves. `NOT_DRAWN_HERE` says so in one sentence rather than drawing
 * zeros, and the queue card links to the screens where each queue is worked.
 *
 * **No count of anything the reader was not shown.** The questions figure is the API's own total,
 * and the people figure is the number of lines the API sent, which are lines the reader holds.
 * Nothing is added up here.
 *
 * Imported statically rather than split, for `Roles.tsx`' reason: it mounts neither heavy library
 * and imports no stylesheet of its own.
 *
 * Task ids: M27.7.29
 */

import { Link } from "react-router-dom";
import { useResource } from "../api/useResource";
import { NAVIGATION_API_PATH, readNavigation } from "../layout/navigationQuery";
import { Chip } from "../ui/Chip";
import { agentAddress } from "./Agents";
import { readRoster, ROSTER_API_PATH } from "./agentsQuery";
import { readQuestions, QUESTIONS_API_PATH } from "./questionsQuery";
import { FailureNotice } from "./reportFailure";
import { readUsage, usageApiPath } from "./usageQuery";

/** The console address, which `brain.console.department_console.DEPARTMENT_NAVIGATION` links to. */
export const DEPARTMENT_PATH = "/department";

/** The design's own label for this screen, which the menu and this heading share. */
export const DEPARTMENT_HEADING = "Department";

/** Under the heading. */
export const DEPARTMENT_LEDE =
  "What is happening in your department this week, from the screens that show each part in full.";

/** The window the usage card reads, in days, which is the design's "Last 7 days". */
export const DEPARTMENT_WINDOW_DAYS = 7;

/** The four card headings, in the design's words where it has them. */
export const USAGE_CARD = "Questions this week";
export const AGENTS_CARD = "Agents and leashes";
export const QUEUES_CARD = "Your queues";
export const GAPS_CARD = "Questions nobody could answer";

/** A card whose route sent nothing this reader is shown. */
export const NOTHING_TO_SHOW = "There is nothing to show here.";

/** The roster sent no agent. */
export const NO_AGENT = "No agent is listed for you.";

/** The roster has more agents than it sent. Never how many. */
export const MORE_AGENTS = "There are more agents than are listed here.";

/** Where each agent's rungs are, since the roster carries none. */
export const LEASHES_ARE_ON_EACH_AGENT = "Each agent's leash is on its own page.";

/** No gap to show, whichever of the reasons there is none. */
export const NO_GAP = "There is no gap to show here.";

/** What the design draws that no route serves, in one sentence rather than as zeros. */
export const NOT_DRAWN_HERE =
  "How many questions were answered or escalated, the budget and the counts on each queue are " +
  "not shown: nothing on this install records how a question ended, and no screen counts a queue.";

/** Where each of the design's queues is worked. Links, and no figure beside any of them. */
const QUEUES: readonly { readonly to: string; readonly label: string; readonly what: string }[] = [
  { to: "/approvals", label: "Approvals", what: "promotions and actions waiting on a decision" },
  { to: "/learning", label: "Learning", what: "what was learned and needs a person" },
  { to: "/skills", label: "Skills", what: "skills to review" },
  { to: "/library", label: "Knowledge", what: "knowledge items and how widely each reaches" },
];

function Loading() {
  return (
    <p className="note" role="status">
      Loading.
    </p>
  );
}

function UsageCard() {
  const answer = useResource<unknown>(usageApiPath(DEPARTMENT_WINDOW_DAYS));
  const body = answer.data === null ? null : readUsage(answer.data);

  return (
    <section className="card">
      <h2>{USAGE_CARD}</h2>
      {answer.failure ? <FailureNotice failure={answer.failure} /> : null}
      {answer.busy ? <Loading /> : null}
      {!answer.busy && !answer.failure ? (
        body === null || body.questions === null ? (
          <p className="note">{NOTHING_TO_SHOW}</p>
        ) : (
          <dl className="fields" aria-label={USAGE_CARD}>
            <div className="fields__row">
              <dt>Questions</dt>
              <dd>{String(body.questions)}</dd>
            </div>
            {body.people === null ? null : (
              <div className="fields__row">
                <dt>People who asked</dt>
                <dd>{String(body.people.length)}</dd>
              </div>
            )}
          </dl>
        )
      ) : null}
      <p className="note">
        By department and by person on <Link to="/usage">Usage</Link>.
      </p>
    </section>
  );
}

function AgentsCard() {
  const answer = useResource<unknown>(ROSTER_API_PATH);
  const roster = answer.data === null ? null : readRoster(answer.data);

  return (
    <section className="card">
      <h2>{AGENTS_CARD}</h2>
      {answer.failure ? <FailureNotice failure={answer.failure} /> : null}
      {answer.busy ? <Loading /> : null}
      {!answer.busy && !answer.failure ? (
        roster === null || roster.entries.length === 0 ? (
          <p className="note">{NO_AGENT}</p>
        ) : (
          <ul>
            {roster.entries.map((entry) => (
              <li key={entry.agentId}>
                <Link to={agentAddress(entry.agentId)}>{entry.displayName}</Link>
              </li>
            ))}
          </ul>
        )
      ) : null}
      {roster?.truncated ? <p className="note">{MORE_AGENTS}</p> : null}
      <p className="note">
        {LEASHES_ARE_ON_EACH_AGENT} Every agent is on <Link to="/agents">Agents and leashes</Link>.
      </p>
    </section>
  );
}

function QueuesCard() {
  return (
    <section className="card">
      <h2>{QUEUES_CARD}</h2>
      <ul>
        {QUEUES.map((queue) => (
          <li key={queue.to}>
            <Link to={queue.to}>{queue.label}</Link>: {queue.what}
          </li>
        ))}
      </ul>
    </section>
  );
}

function GapsCard() {
  const answer = useResource<unknown>(QUESTIONS_API_PATH);
  const body = answer.data === null ? null : readQuestions(answer.data);

  return (
    <section className="card">
      <h2>{GAPS_CARD}</h2>
      {answer.failure ? <FailureNotice failure={answer.failure} /> : null}
      {answer.busy ? <Loading /> : null}
      {!answer.busy && !answer.failure ? (
        body === null || !body.nothing_connected ? (
          <p className="note">{NO_GAP}</p>
        ) : (
          <p>
            No source is connected, so every question is answered:{" "}
            <q>{body.answered_when_nothing_connected}</q>{" "}
            <Link to="/connectors">Connect a source</Link>
          </p>
        )
      ) : null}
      <p className="note">
        Why questions could not be answered is on <Link to="/questions">Gaps</Link>.
      </p>
    </section>
  );
}

export function Department() {
  const navigation = useResource<unknown>(NAVIGATION_API_PATH);
  const given = navigation.data === null ? null : readNavigation(navigation.data);
  const departments = given?.console === "department" ? given.departments : [];

  return (
    <article className="page">
      <h1>{DEPARTMENT_HEADING}</h1>
      {departments.length > 0 ? (
        <p>
          Scope: <Chip label={departments.join(", ")} />
        </p>
      ) : null}
      <p className="lede">{DEPARTMENT_LEDE}</p>
      <UsageCard />
      <AgentsCard />
      <QueuesCard />
      <GapsCard />
      <p className="note">{NOT_DRAWN_HERE}</p>
    </article>
  );
}
