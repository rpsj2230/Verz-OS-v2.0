/**
 * Skills: the library, what each skill is trusted to reach, the review queue, and assigning an
 * approved skill to an agent.
 *
 * SCREEN 6 of `docs/screens.html`, which is the design of record: Govern section, a library, a
 * review pane with Approve and Reject, and an upstream-drift card. `brain.skill_routes` serves the
 * library `0056` stores and three writes, and this page draws them. See `skillsQuery.ts` for what
 * is asked and sent.
 *
 * **Adding a skill is a submission.** The form takes a paste or a chosen file, checks there is
 * something to send and that it is not too large, and posts it. The page then says the skill is
 * waiting for review and asks for the library again, where it is listed with what it names.
 *
 * **What a skill is trusted to reach is drawn from the tools it names**, each with the capability
 * the registered tool requires, and a tool this install does not have is named as such. A skill has
 * no reach of its own, and the page says so in one sentence rather than implying one.
 *
 * **Approve and Reject are drawn only where the API says this reader may decide**, which is never
 * on a skill they added, and each is confirmed with what it does. **Assign is drawn only for an
 * approved skill and only with the agents the API listed**, and the confirmation names the agent.
 * The answer to an assignment is what the skill reaches through that agent for this person, which
 * the page says in words.
 *
 * **The address is the whole of the state.** `/skills` is the library and `/skills/{name}` is the
 * library with one skill open, so a person can send a colleague the skill they are arguing about.
 * The deep link is resolved against the page and never against a route of its own.
 *
 * **Nothing here decides who may see or do anything.** Every control is drawn from a flag the API
 * sent, and every write is decided again on the server.
 *
 * **A refused write is drawn where it was made, by `ui/FailureNotice.tsx`.** Until 2026-09-17 a
 * refusal was the API's sentence alone at the top of the page, as an alert, with its reference
 * dropped and every problem the API named thrown away. Each of the three writes now draws its own
 * failure in its own card, with the reference and with each problem beside the input it names.
 *
 * Imported statically rather than split, which is `Roles.tsx`'s rule.
 *
 * Task ids: M42.6.4, M27.8.5, M27.8.6
 */

import { useState, type ChangeEvent, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { ListControls, NOTHING_MATCHES, ShowMore } from "../components/ListControls";
import { narrows } from "../components/listing";
import { useListing } from "../components/useListing";
import { ConfirmAction } from "../components/ConfirmAction";
import { FailureNotice } from "../ui/FailureNotice";
import { FieldProblems, problemAttributes } from "../ui/FieldProblems";
import {
  addedSentence,
  assignConsequence,
  assignedSentence,
  assignPath,
  assignQuestion,
  chosen,
  decidedSentence,
  decisionConsequence,
  decisionQuestion,
  driftingRows,
  packageProblem,
  pasted,
  readSkillsPage,
  reviewPath,
  reviewWords,
  skillAddress,
  skillIn,
  SKILLS_API_PATH,
  SKILL_FILTERS,
  SKILL_SORTS,
  skillApiPath,
  versionsOf,
  type AgentChoice,
  type Assigned,
  type LibrarySkill,
  type PackageBody,
  type SkillLibraryRow,
} from "./skillsQuery";
import { when } from "./sessionsQuery";

export const SKILLS_HEADING = "Skills";

/** Under the heading. The design's own sentence about what a skill is and where the boundary sits. */
export const SKILLS_LEDE =
  "A skill is a folder with instructions and optional scripts, authored anywhere and imported " +
  "here. Import is the security boundary: a skill arrives unreviewed, runs against nothing, " +
  "and only reaches an agent after a named person has read it.";

/** An empty library, whichever of the reasons it is empty. */
export const NO_LIBRARY = "There are no skills in the library to show.";

/** No agent runs a skill this reader's agents run, whichever of the reasons. */
export const NO_SKILLS = "There are no skills in use to show.";
export const NONE_MATCH = NOTHING_MATCHES;
export const FILTERS_LABEL = "Narrow the skills in use";

/** A load that came back full. A fact about there being more, and never a figure. */
export const MORE_AGENTS =
  "This page was assembled from a full page of agents, so there are more agents than it covers.";
export const MORE_SKILLS =
  "The library came back full, so there are more skills in it than this page lists.";

/** What adding a skill does, above the form. */
export const ADD_HEADING = "Add a skill";
export const ADD_LEDE =
  "Paste a SKILL.md, or choose a SKILL.md or a .zip holding only one. It is read and never run, " +
  "and a skill that declares scripts is refused. It is added unreviewed and cannot be assigned " +
  "to an agent until somebody other than you approves it.";
export const PASTE_LABEL = "Paste a SKILL.md";
export const FILE_LABEL = "Or choose a file";
export const ADD = "Add to the library";

/** What reach means, beside every skill's list of tools. */
export const REACH_HEADING = "What it is trusted to reach";
export const A_SKILL_HAS_NO_REACH_OF_ITS_OWN =
  "A skill has no reach of its own. It can use a tool it names only through an agent allowed that " +
  "tool, and only for somebody who already holds what the tool requires.";
export const NAMES_NO_TOOLS = "It names no tools, so it can use none.";
export const NOT_ON_THIS_INSTALL = "not a tool this install has, so it reaches nothing";
export const NO_REGISTRY =
  "The server has no tool registry loaded, so no tool a skill names can be matched to what it " +
  "requires.";

/** The review controls. */
export const APPROVE = "Approve";
export const REJECT = "Reject";
export const KEEP_IT = "Leave it undecided";
export const INSTRUCTIONS = "Instructions";

/** The assignment controls. */
export const ASSIGN_LABEL = "Agent";
export const ASSIGN = "Assign to agent";
export const DO_NOT_ASSIGN = "Do not assign";

/** What an empty queue means. */
export const NOTHING_IS_WAITING = "No skill in the library is waiting for a review you may see.";

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
export const LIBRARY_LABEL = "Skills in the library";
export const IN_USE_LABEL = "Skills in use";
export const QUEUE_LABEL = "Skills waiting for a reviewer";
export const DRIFT_LABEL = "Skills whose agents run different bytes";
export const PINS_LABEL = "Agents running this skill";
export const REACH_LABEL = "Tools this skill names";

/** The queue's own counts, in words, so a bare number is never the whole sentence. */
export function queueCount(waiting: number, edits: number, stale: number): string {
  return `${String(waiting)} waiting, ${String(edits)} of them edits, ${String(stale)} overdue.`;
}

/** The names a package is sent under, and the prefix of the lists drawn beside its two inputs. */
const PACKAGE_FIELDS: readonly string[] = ["content", "file_name", "encoding"];
const PACKAGE_FILE_NAMES: readonly string[] = ["file_name", "encoding"];
const PACKAGE_FORM = "skills-add";

/** What the last write said, kept above the page while it is read again. */
interface Told {
  readonly ok: boolean;
  readonly sentence: string;
}

type Tell = (told: Told) => void;

/** One skill's pins, as the in-use list and as the open skill's list. */
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

function readFile(file: File): Promise<Uint8Array> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      resolve(new Uint8Array(reader.result as ArrayBuffer));
    };
    reader.onerror = () => {
      reject(reader.error ?? new Error("the file could not be read"));
    };
    reader.readAsArrayBuffer(file);
  });
}

function AddSkill({ onTold }: { readonly onTold: Tell }) {
  const [text, setText] = useState("");
  const [file, setFile] = useState<PackageBody | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const body = file ?? (text.trim() === "" ? null : pasted(text));
  const problem = packageProblem(body);
  const problems = failure?.problems ?? [];

  async function onChoose(event: ChangeEvent<HTMLInputElement>) {
    const one = event.target.files?.[0];
    if (one === undefined) {
      setFile(null);
      return;
    }
    try {
      setFile(chosen(one.name, await readFile(one)));
    } catch {
      setFile(null);
      onTold({ ok: false, sentence: "That file could not be read. Choose it again." });
    }
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (body === null || problem !== null) {
      return;
    }
    setBusy(true);
    setFailure(null);
    const result = await request<LibrarySkill>(SKILLS_API_PATH, { method: "POST", body });
    setBusy(false);
    if (result.ok) {
      setText("");
      setFile(null);
      onTold({ ok: true, sentence: addedSentence(result.data) });
    } else {
      setFailure(result.failure);
    }
  }

  return (
    <section className="card" aria-labelledby="skills-add">
      <h2 id="skills-add">{ADD_HEADING}</h2>
      <p className="note">{ADD_LEDE}</p>
      {failure === null ? null : <FailureNotice failure={failure} fields={PACKAGE_FIELDS} />}
      <form className="form" aria-label={ADD_HEADING} onSubmit={(event) => void onSubmit(event)}>
        <label className="control-label" htmlFor="skills-paste">
          {PASTE_LABEL}
        </label>
        <textarea
          id="skills-paste"
          className="form-control"
          name="content"
          rows={8}
          value={text}
          disabled={file !== null}
          {...problemAttributes(problems, PACKAGE_FORM, "content")}
          onChange={(event) => {
            setText(event.target.value);
          }}
        />
        <FieldProblems problems={problems} form={PACKAGE_FORM} names="content" />
        <label className="control-label" htmlFor="skills-file">
          {FILE_LABEL}
        </label>
        <input
          id="skills-file"
          className="form-control"
          type="file"
          name="file_name"
          accept=".md,.zip"
          {...problemAttributes(problems, PACKAGE_FORM, PACKAGE_FILE_NAMES)}
          onChange={(event) => void onChoose(event)}
        />
        <FieldProblems problems={problems} form={PACKAGE_FORM} names={PACKAGE_FILE_NAMES} />
        {body === null ? null : problem === null ? null : (
          <p className="note" role="alert">
            {problem}
          </p>
        )}
        <div className="form-actions">
          <button type="submit" className="button" disabled={busy || problem !== null}>
            {ADD}
          </button>
        </div>
      </form>
    </section>
  );
}

function Reach({ one, registryIsAbsent }: { readonly one: LibrarySkill; readonly registryIsAbsent: boolean }) {
  return (
    <section aria-label={`${REACH_HEADING}: ${one.name} ${one.version}`}>
      <h3>{REACH_HEADING}</h3>
      {one.tools.length === 0 ? (
        <p className="note">{NAMES_NO_TOOLS}</p>
      ) : (
        <ul className="roster" aria-label={REACH_LABEL}>
          {one.tools.map((tool) => (
            <li key={tool.name}>
              <code>{tool.name}</code>{" "}
              {tool.capability === null ? (
                <span className="note">{NOT_ON_THIS_INSTALL}</span>
              ) : (
                <code>{tool.capability}</code>
              )}
            </li>
          ))}
        </ul>
      )}
      {registryIsAbsent ? <p className="note">{NO_REGISTRY}</p> : null}
      <p className="note">{A_SKILL_HAS_NO_REACH_OF_ITS_OWN}</p>
    </section>
  );
}

function Decide({ one, onTold }: { readonly one: LibrarySkill; readonly onTold: Tell }) {
  const [asking, setAsking] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  async function decide(approve: boolean) {
    setBusy(true);
    setFailure(null);
    const result = await request<LibrarySkill>(reviewPath(one.digest), {
      method: "POST",
      body: { decision: approve ? "approve" : "reject" },
    });
    setBusy(false);
    setAsking(null);
    if (result.ok) {
      onTold({ ok: true, sentence: decidedSentence(result.data) });
    } else {
      setFailure(result.failure);
    }
  }

  if (asking !== null) {
    return (
      <ConfirmAction
        question={decisionQuestion(one, asking)}
        consequence={decisionConsequence(one, asking)}
        confirmLabel={asking ? APPROVE : REJECT}
        cancelLabel={KEEP_IT}
        busy={busy}
        onConfirm={() => void decide(asking)}
        onCancel={() => {
          setAsking(null);
        }}
      />
    );
  }
  return (
    <>
      {failure === null ? null : <FailureNotice failure={failure} />}
      <div className="form-actions">
        <button
          type="button"
          className="button"
          aria-label={`${APPROVE}: ${one.name} ${one.version}`}
          onClick={() => {
            setAsking(true);
          }}
        >
          {APPROVE}
        </button>{" "}
        <button
          type="button"
          className="button"
          aria-label={`${REJECT}: ${one.name} ${one.version}`}
          onClick={() => {
            setAsking(false);
          }}
        >
          {REJECT}
        </button>
      </div>
    </>
  );
}

function Assign({
  one,
  agents,
  onTold,
}: {
  readonly one: LibrarySkill;
  readonly agents: readonly AgentChoice[];
  readonly onTold: Tell;
}) {
  const [agentId, setAgentId] = useState(agents[0]?.agent_id ?? "");
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const agent = agents.find((candidate) => candidate.agent_id === agentId);
  const fieldId = `assign-${one.digest}`;
  const problems = failure?.problems ?? [];

  async function assign() {
    if (agent === undefined) {
      return;
    }
    setBusy(true);
    setFailure(null);
    const result = await request<Assigned>(assignPath(one.digest), {
      method: "POST",
      body: { agent_id: agent.agent_id },
    });
    setBusy(false);
    setAsking(false);
    if (result.ok) {
      onTold({ ok: true, sentence: assignedSentence(result.data, agent) });
    } else {
      setFailure(result.failure);
    }
  }

  if (asking && agent !== undefined) {
    return (
      <ConfirmAction
        question={assignQuestion(one, agent)}
        consequence={assignConsequence(one, agent)}
        confirmLabel={ASSIGN}
        cancelLabel={DO_NOT_ASSIGN}
        busy={busy}
        onConfirm={() => void assign()}
        onCancel={() => {
          setAsking(false);
        }}
      />
    );
  }
  return (
    <form
      className="form"
      aria-label={`${ASSIGN}: ${one.name} ${one.version}`}
      onSubmit={(event) => {
        event.preventDefault();
        setAsking(true);
      }}
    >
      {failure === null ? null : <FailureNotice failure={failure} fields={["agent_id"]} />}
      <label className="control-label" htmlFor={fieldId}>
        {ASSIGN_LABEL}
      </label>
      <select
        id={fieldId}
        className="form-control"
        name="agent_id"
        value={agentId}
        {...problemAttributes(problems, fieldId, "agent_id")}
        onChange={(event) => {
          setAgentId(event.target.value);
        }}
      >
        {agents.map((candidate) => (
          <option key={candidate.agent_id} value={candidate.agent_id}>
            {candidate.display_name}
          </option>
        ))}
      </select>
      <FieldProblems problems={problems} form={fieldId} names="agent_id" />
      <div className="form-actions">
        <button type="submit" className="button" disabled={agent === undefined}>
          {ASSIGN}
        </button>
      </div>
    </form>
  );
}

function Version({
  one,
  agents,
  registryIsAbsent,
  onTold,
}: {
  readonly one: LibrarySkill;
  readonly agents: readonly AgentChoice[];
  readonly registryIsAbsent: boolean;
  readonly onTold: Tell;
}) {
  return (
    <section className="card" aria-label={`${one.name} ${one.version}`}>
      <h3>
        {one.name} {one.version}
      </h3>
      <p>{one.description}</p>
      <p className="note">
        {reviewWords(one.review)}. Added by {one.submitted_by} from {one.source}{" "}
        <code>{one.source_location}</code> on {when(one.submitted_at)}
        {one.reviewer === null || one.reviewed_at === null
          ? "."
          : `, decided by ${one.reviewer} on ${when(one.reviewed_at)}.`}
      </p>
      <p className="note">
        <code>{one.digest}</code>
      </p>
      <Reach one={one} registryIsAbsent={registryIsAbsent} />
      {one.body === null ? null : (
        <details>
          <summary>{INSTRUCTIONS}</summary>
          <pre>{one.body}</pre>
        </details>
      )}
      {one.reviewable ? <Decide one={one} onTold={onTold} /> : null}
      {one.assignable && agents.length > 0 ? (
        <Assign one={one} agents={agents} onTold={onTold} />
      ) : null}
    </section>
  );
}

function SkillsAnswerView({
  openName,
  version,
  onTold,
}: {
  readonly openName: string | undefined;
  readonly version: number;
  readonly onTold: Tell;
}) {
  const listing = useListing<SkillLibraryRow>(SKILLS_API_PATH, { choices: SKILL_FILTERS, version });
  const opened = useResource<unknown>(openName === undefined ? null : skillApiPath(openName), version);

  if (listing.body === null) {
    if (listing.failure) {
      return <FailureNotice failure={listing.failure} />;
    }
    return (
      <p className="note" role="status">
        Loading.
      </p>
    );
  }

  const page = readSkillsPage(listing.body);
  const openPage = readSkillsPage(opened.data);
  const pinned = openName === undefined ? null : skillIn(openPage.skills, openName);
  const versions = openName === undefined ? [] : versionsOf(page.library, openName);
  const drifting = driftingRows(page.skills);

  return (
    <>
      {page.mayAdd ? <AddSkill onTold={onTold} /> : null}

      <h2>Library</h2>
      {page.library.length === 0 ? (
        <p className="note">{NO_LIBRARY}</p>
      ) : (
        <ul className="roster" aria-label={LIBRARY_LABEL}>
          {page.library.map((one) => (
            <li key={one.digest}>
              <Link to={skillAddress(one.name)}>{one.name}</Link> {one.version}{" "}
              <span className="note">{reviewWords(one.review)}</span>
            </li>
          ))}
        </ul>
      )}
      {page.libraryTruncated ? <p className="note">{MORE_SKILLS}</p> : null}

      {openName === undefined || opened.busy ? null : versions.length === 0 && pinned === null ? (
        <p className="note">{NO_SUCH_SKILL}</p>
      ) : (
        <section className="card" aria-label={openName}>
          <h2>{openName}</h2>
          {versions.map((one) => (
            <Version
              key={one.digest}
              one={one}
              agents={page.agents}
              registryIsAbsent={page.registryIsAbsent}
              onTold={onTold}
            />
          ))}
          {pinned === null ? null : <Pins row={pinned} />}
        </section>
      )}

      <h2>Awaiting review</h2>
      {page.queue.length === 0 ? (
        <p className="note">{NOTHING_IS_WAITING}</p>
      ) : (
        <>
          <ul className="roster" aria-label={QUEUE_LABEL}>
            {page.queue.map((entry) => (
              <li key={entry.digest}>
                <Link to={skillAddress(entry.name)}>{entry.name}</Link>{" "}
                <span className="note">{entry.waiting_since}</span>
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

      <h2>In use by agents</h2>
      <ListControls label={FILTERS_LABEL} listing={listing} choices={SKILL_FILTERS} sorts={SKILL_SORTS} />
      {listing.failure ? (
        <FailureNotice failure={listing.failure} />
      ) : listing.busy ? (
        <p className="note" role="status">
          Loading.
        </p>
      ) : page.skills.length === 0 ? (
        <p className="note">{narrows(listing.question) ? NONE_MATCH : NO_SKILLS}</p>
      ) : (
        <>
          <ul className="roster" aria-label={IN_USE_LABEL}>
            {page.skills.map((row) => (
              <li key={row.name}>
                <Link to={skillAddress(row.name)}>{row.name}</Link>
                <Pins row={row} />
              </li>
            ))}
          </ul>
          <ShowMore listing={listing} />
        </>
      )}
      {page.truncated ? <p className="note">{MORE_AGENTS}</p> : null}

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
    </>
  );
}

export function Skills() {
  const { name } = useParams();
  const [version, setVersion] = useState(0);
  const [told, setTold] = useState<Told | null>(null);

  function onTold(next: Told) {
    setTold(next);
    if (next.ok) {
      setVersion((current) => current + 1);
    }
  }

  return (
    <article className="page">
      <h1>{SKILLS_HEADING}</h1>
      <p className="lede">{SKILLS_LEDE}</p>
      {told === null ? null : (
        <p className="note" role={told.ok ? "status" : "alert"}>
          {told.sentence}
        </p>
      )}
      <SkillsAnswerView openName={name} version={version} onTold={onTold} />
    </article>
  );
}
