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
 * **Importing is the same submission from somewhere else (M12.2.2, M12.2.3).** A GitHub repository
 * at a full commit, with the folder holding the `SKILL.md`, or an https address. The page checks
 * the shape and nothing else; the API fetches, from its own list of hosts, and refuses in words.
 *
 * **An edit is saved as a new version (M12.3.2).** The edit box starts from the text the API sent,
 * and saving it leaves the version it came from where it is, with every agent still pinned to it.
 * The review pane shows the words that changed against the version the API names (M12.2.6).
 *
 * **Categories are chips (M12.4.13).** The API sends the chips, drawn from the skills this reader
 * was shown; choosing one narrows the library here and asks the skills-in-use listing for the same.
 *
 * **What a skill is trusted to reach is drawn from the tools it names**, each with the capability
 * the registered tool requires, and a tool this install does not have is named as such. A skill has
 * no reach of its own, and the page says so in one sentence rather than implying one.
 *
 * **Approve and Reject are drawn only where the API says this reader may decide**, which since the
 * owner's D4 includes a skill they added, and each is confirmed with what it does; a decision by
 * the person who added the skill is shown as their own (M12.4.6). **Assign is drawn only for an
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
 * Task ids: M42.6.4, M27.8.5, M27.8.6, M12.2.2, M12.2.3, M12.2.6, M12.3.2, M12.4.6, M12.4.13
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
  addressImport,
  assignConsequence,
  assignedSentence,
  assignPath,
  assignQuestion,
  CATEGORY_COLUMN,
  categoriesPath,
  categoriesTyped,
  categorisedSentence,
  chosen,
  decidedSentence,
  decisionConsequence,
  decisionQuestion,
  decisionWords,
  driftingRows,
  editedSentence,
  IMPORT_PATH,
  importProblem,
  inCategory,
  packageProblem,
  pasted,
  readSkillsPage,
  repositoryImport,
  reviewPath,
  reviewWords,
  skillAddress,
  skillIn,
  SKILLS_API_PATH,
  SKILL_FILTERS,
  SKILL_SORTS,
  skillApiPath,
  sourceWords,
  versionsOf,
  versionsPath,
  type AgentChoice,
  type Assigned,
  type Categorised,
  type LibrarySkill,
  type PackageBody,
  type SkillDiff,
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
  "and a skill that declares scripts is refused. Its description must open by saying when the " +
  "skill is used, as in \"Use when a client asks\". It is added unreviewed and cannot be " +
  "assigned to an agent until it is approved.";
export const PASTE_LABEL = "Paste a SKILL.md";
export const FILE_LABEL = "Or choose a file";
export const ADD = "Add to the library";
export const CATEGORIES_LABEL = "Categories, separated by commas";

/** Importing from GitHub or an address. */
export const IMPORT_HEADING = "Import a skill";
export const IMPORT_LEDE =
  "Import a SKILL.md from a GitHub repository at one commit, or from an https address on GitHub. " +
  "The server fetches it, only from GitHub's own hosts, reads it and runs nothing. Only the " +
  "SKILL.md is taken from a repository folder. It is added unreviewed, as a pasted skill is.";
export const FROM_REPOSITORY = "From a GitHub repository at a commit";
export const FROM_ADDRESS = "From an address";
export const REPOSITORY_LABEL = "Repository, as owner/repository";
export const COMMIT_LABEL = "Commit, all forty characters";
export const FOLDER_LABEL = "Folder holding the SKILL.md, empty for the top folder";
export const ADDRESS_LABEL = "Address of a SKILL.md or a .zip holding one";
export const IMPORT = "Import";

/** Editing, categories and the words that changed. */
export const EDIT = "Edit";
export const EDIT_LABEL = "The SKILL.md, edited";
export const SAVE_VERSION = "Save as a new version";
export const STOP_EDITING = "Stop editing";
export const EDIT_LEDE =
  "Saving makes a new version that waits for review. This version stays as it is, and every " +
  "agent keeps the version it runs until somebody assigns the new one. Give the edit a later " +
  "version number.";
export const SET_CATEGORIES = "Set categories";
export const CHANGED_HEADING = "What changed";
export const CHIPS_LABEL = "Show the skills in one category";
export const EVERY_CATEGORY = "Every category";

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
const PACKAGE_FIELDS: readonly string[] = ["content", "file_name", "encoding", "categories"];
const PACKAGE_FILE_NAMES: readonly string[] = ["file_name", "encoding"];
const PACKAGE_FORM = "skills-add";
const IMPORT_FORM = "skills-import";
const IMPORT_FIELDS: readonly string[] = ["kind", "repository", "commit", "path", "url", "categories"];

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
  const [filed, setFiled] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const categories = categoriesTyped(filed);
  const body =
    file === null ? (text.trim() === "" ? null : pasted(text, categories)) : { ...file, categories };
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
      setFiled("");
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
        <label className="control-label" htmlFor="skills-categories">
          {CATEGORIES_LABEL}
        </label>
        <input
          id="skills-categories"
          className="form-control"
          name="categories"
          value={filed}
          {...problemAttributes(problems, PACKAGE_FORM, "categories")}
          onChange={(event) => {
            setFiled(event.target.value);
          }}
        />
        <FieldProblems problems={problems} form={PACKAGE_FORM} names="categories" />
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

type ImportFrom = "github" | "url";

function ImportSkill({ onTold }: { readonly onTold: Tell }) {
  const [from, setFrom] = useState<ImportFrom>("github");
  const [repository, setRepository] = useState("");
  const [commit, setCommit] = useState("");
  const [folder, setFolder] = useState("");
  const [address, setAddress] = useState("");
  const [filed, setFiled] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const categories = categoriesTyped(filed);
  const body =
    from === "github"
      ? repositoryImport(repository, commit, folder, categories)
      : addressImport(address, categories);
  const problem = importProblem(body);
  const started = from === "github" ? repository !== "" || commit !== "" : address !== "";
  const problems = failure?.problems ?? [];

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (problem !== null) {
      return;
    }
    setBusy(true);
    setFailure(null);
    const result = await request<LibrarySkill>(IMPORT_PATH, { method: "POST", body });
    setBusy(false);
    if (result.ok) {
      setRepository("");
      setCommit("");
      setFolder("");
      setAddress("");
      setFiled("");
      onTold({ ok: true, sentence: addedSentence(result.data) });
    } else {
      setFailure(result.failure);
    }
  }

  function field(id: string, label: string, name: string, value: string, set: (next: string) => void) {
    return (
      <>
        <label className="control-label" htmlFor={id}>
          {label}
        </label>
        <input
          id={id}
          className="form-control"
          name={name}
          value={value}
          {...problemAttributes(problems, IMPORT_FORM, name)}
          onChange={(event) => {
            set(event.target.value);
          }}
        />
        <FieldProblems problems={problems} form={IMPORT_FORM} names={name} />
      </>
    );
  }

  return (
    <section className="card" aria-labelledby="skills-import">
      <h2 id="skills-import">{IMPORT_HEADING}</h2>
      <p className="note">{IMPORT_LEDE}</p>
      {failure === null ? null : <FailureNotice failure={failure} fields={IMPORT_FIELDS} />}
      <form className="form" aria-label={IMPORT_HEADING} onSubmit={(event) => void onSubmit(event)}>
        <fieldset className="theme-control">
          {(
            [
              ["github", FROM_REPOSITORY],
              ["url", FROM_ADDRESS],
            ] as const
          ).map(([value, label]) => (
            <label key={value} className="control-label">
              <input
                type="radio"
                name="kind"
                value={value}
                checked={from === value}
                onChange={() => {
                  setFrom(value);
                }}
              />{" "}
              {label}
            </label>
          ))}
        </fieldset>
        {from === "github" ? (
          <>
            {field("skills-repository", REPOSITORY_LABEL, "repository", repository, setRepository)}
            {field("skills-commit", COMMIT_LABEL, "commit", commit, setCommit)}
            {field("skills-folder", FOLDER_LABEL, "path", folder, setFolder)}
          </>
        ) : (
          field("skills-address", ADDRESS_LABEL, "url", address, setAddress)
        )}
        {field("skills-import-categories", CATEGORIES_LABEL, "categories", filed, setFiled)}
        {started && problem !== null ? (
          <p className="note" role="alert">
            {problem}
          </p>
        ) : null}
        <div className="form-actions">
          <button type="submit" className="button" disabled={busy || problem !== null}>
            {IMPORT}
          </button>
        </div>
      </form>
    </section>
  );
}

function Changed({ one, diff }: { readonly one: LibrarySkill; readonly diff: SkillDiff }) {
  const marks = { kept: "  ", removed: "- ", added: "+ " } as const;
  return (
    <section aria-label={`${CHANGED_HEADING}: ${one.name} ${one.version}`}>
      <h3>
        {CHANGED_HEADING} since {diff.against_version}
      </h3>
      <p className="note">
        Compared with <code>{diff.against_digest}</code>.
      </p>
      {diff.fields.length === 0 ? null : (
        <ul className="roster">
          {diff.fields.map((change) => (
            <li key={change.field}>
              <code>{change.field}</code>: <del>{change.before}</del> <ins>{change.after}</ins>
            </li>
          ))}
        </ul>
      )}
      {/* Each line says what happened to it in its text, and `del` and `ins` say it to an eye and a
          screen reader alike, so no colour is needed and none is added. */}
      <pre className="skill-diff">
        {diff.body.map((line, index) => {
          const key = `${String(index)}-${line.change}`;
          const text = `${marks[line.change]}${line.text}\n`;
          const className = `skill-diff__line skill-diff__line--${line.change}`;
          if (line.change === "removed") {
            return (
              <del key={key} className={className}>
                {text}
              </del>
            );
          }
          if (line.change === "added") {
            return (
              <ins key={key} className={className}>
                {text}
              </ins>
            );
          }
          return (
            <span key={key} className={className}>
              {text}
            </span>
          );
        })}
      </pre>
    </section>
  );
}

function EditSkill({ one, onTold }: { readonly one: LibrarySkill; readonly onTold: Tell }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState(one.markdown ?? "");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const fieldId = `edit-${one.digest}`;

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setFailure(null);
    const result = await request<LibrarySkill>(versionsPath(one.digest), {
      method: "POST",
      body: { content: text },
    });
    setBusy(false);
    if (result.ok) {
      setOpen(false);
      onTold({ ok: true, sentence: editedSentence(result.data) });
    } else {
      setFailure(result.failure);
    }
  }

  if (!open) {
    return (
      <div className="form-actions">
        <button
          type="button"
          className="button"
          aria-label={`${EDIT}: ${one.name} ${one.version}`}
          onClick={() => {
            setText(one.markdown ?? "");
            setOpen(true);
          }}
        >
          {EDIT}
        </button>
      </div>
    );
  }
  return (
    <form className="form" aria-label={`${EDIT}: ${one.name} ${one.version}`} onSubmit={(event) => void save(event)}>
      <p className="note">{EDIT_LEDE}</p>
      {failure === null ? null : <FailureNotice failure={failure} fields={["content"]} />}
      <label className="control-label" htmlFor={fieldId}>
        {EDIT_LABEL}
      </label>
      <textarea
        id={fieldId}
        className="form-control"
        name="content"
        rows={12}
        value={text}
        onChange={(event) => {
          setText(event.target.value);
        }}
      />
      <div className="form-actions">
        <button type="submit" className="button" disabled={busy || text.trim() === ""}>
          {SAVE_VERSION}
        </button>{" "}
        <button
          type="button"
          className="button"
          onClick={() => {
            setOpen(false);
          }}
        >
          {STOP_EDITING}
        </button>
      </div>
    </form>
  );
}

function Categorise({ one, onTold }: { readonly one: LibrarySkill; readonly onTold: Tell }) {
  const [filed, setFiled] = useState(one.categories.join(", "));
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const fieldId = `categories-${one.digest}`;

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setFailure(null);
    const result = await request<Categorised>(categoriesPath(one.digest), {
      method: "POST",
      body: { categories: categoriesTyped(filed) },
    });
    setBusy(false);
    if (result.ok) {
      onTold({ ok: true, sentence: categorisedSentence(result.data) });
    } else {
      setFailure(result.failure);
    }
  }

  return (
    <form className="form" aria-label={`${SET_CATEGORIES}: ${one.name}`} onSubmit={(event) => void save(event)}>
      {failure === null ? null : <FailureNotice failure={failure} fields={["categories"]} />}
      <label className="control-label" htmlFor={fieldId}>
        {CATEGORIES_LABEL}
      </label>
      <input
        id={fieldId}
        className="form-control"
        name="categories"
        value={filed}
        onChange={(event) => {
          setFiled(event.target.value);
        }}
      />
      <div className="form-actions">
        <button type="submit" className="button" disabled={busy}>
          {SET_CATEGORIES}
        </button>
      </div>
    </form>
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
        {reviewWords(one.review)}. Added by {one.submitted_by} {sourceWords(one)} on{" "}
        {when(one.submitted_at)}
        {one.reviewer === null || one.reviewed_at === null
          ? "."
          : `, ${decisionWords(one)} on ${when(one.reviewed_at)}.`}
      </p>
      <p className="note">
        <code>{one.digest}</code>
      </p>
      {one.edited_from === null ? null : (
        <p className="note">
          Edited from <code>{one.edited_from}</code>.
        </p>
      )}
      {one.categories.length === 0 ? null : (
        <p className="note">
          {one.categories.map((category) => (
            <span key={category} className="chip">
              {category}
            </span>
          ))}
        </p>
      )}
      <Reach one={one} registryIsAbsent={registryIsAbsent} />
      {one.body === null ? null : (
        <details>
          <summary>{INSTRUCTIONS}</summary>
          <pre>{one.body}</pre>
        </details>
      )}
      {one.diff === null || one.diff === undefined ? null : <Changed one={one} diff={one.diff} />}
      {one.reviewable ? <Decide one={one} onTold={onTold} /> : null}
      {one.assignable && agents.length > 0 ? (
        <Assign one={one} agents={agents} onTold={onTold} />
      ) : null}
      {one.editable ? <EditSkill one={one} onTold={onTold} /> : null}
      {one.editable ? <Categorise one={one} onTold={onTold} /> : null}
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
  const chosen = listing.question.filters[CATEGORY_COLUMN] ?? "";
  const shown = inCategory(page.library, chosen);

  function choose(category: string) {
    listing.ask({
      ...listing.question,
      filters: { ...listing.question.filters, [CATEGORY_COLUMN]: category },
    });
  }

  return (
    <>
      {page.mayAdd ? <AddSkill onTold={onTold} /> : null}
      {page.mayAdd ? <ImportSkill onTold={onTold} /> : null}

      <h2>Library</h2>
      {page.categories.length === 0 ? null : (
        <div className="form-actions" role="group" aria-label={CHIPS_LABEL}>
          {["", ...page.categories].map((category) => (
            <button
              key={category === "" ? "every" : category}
              type="button"
              className="button"
              aria-pressed={chosen === category}
              onClick={() => {
                choose(category);
              }}
            >
              {/* Pressed is said to a screen reader by aria-pressed and to an eye by the weight. */}
              {chosen === category ? (
                <strong>{category === "" ? EVERY_CATEGORY : category}</strong>
              ) : category === "" ? (
                EVERY_CATEGORY
              ) : (
                category
              )}
            </button>
          ))}
        </div>
      )}
      {shown.length === 0 ? (
        <p className="note">{NO_LIBRARY}</p>
      ) : (
        <ul className="roster" aria-label={LIBRARY_LABEL}>
          {shown.map((one) => (
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
