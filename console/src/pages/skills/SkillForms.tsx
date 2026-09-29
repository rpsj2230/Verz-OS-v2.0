/**
 * The Skills module's forms: add a skill by paste or upload, import one from GitHub or an address,
 * save an edit as a new version, set categories, record a rehearsal of a version's example tasks,
 * and assign an approved version to an agent.
 *
 * **Every form says what it accepts before anybody presses anything.** The owner's rule for these
 * pages, and the old page broke it: a paste box with no word about the format, and a refusal
 * arriving afterwards. Each form now has its format line above its fields (a `SKILL.md`, or a `.zip`
 * holding only one; `owner/repository`; the full forty-character commit; an `https://` address on
 * GitHub; lower-case categories separated by commas), and its submit stays disabled until the
 * shape is right, with the reason drawn under the fields. The API still judges everything; a
 * refusal is drawn where it was made, with each problem beside the input it names.
 *
 * **Adding, importing, editing, categorising and rehearsing end nothing, so none asks to be
 * confirmed**; each is recorded in `tests/destructive-confirmed.test.ts` with its reason.
 * **Assigning replaces the version an agent runs, so its submit opens a `ConfirmDialog`** naming the
 * agent, and only the dialog's confirm sends it.
 *
 * **Add and Edit carry example tasks** (M12.3.4): one or more rows, each a task and the behaviour
 * expected, which the API stores exactly as it stores a zip's `examples.json`, so a pasted
 * `SKILL.md` or an edit can be rehearsed and approved. A row left wholly blank is dropped and a
 * row with one half filled in is said beside the button before anything is sent; the API refuses
 * an empty task in words. A chosen zip carries its own and the field is not drawn for it.
 *
 * **A rehearsal asks one question per example and sends nothing until each is answered** (M12.3.4):
 * behaved as expected, or did not. None is chosen to begin with, because a verdict filled in for a
 * person is a rehearsal nobody did, and the form says above its questions that the verdict is theirs
 * and not a model's.
 *
 * Task ids: M27.16.1, M12.2.2, M12.2.3, M12.3.2, M12.4.13, M12.3.4
 */

import { useState, type ChangeEvent, type FormEvent, type ReactNode } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { ConfirmDialog, Note } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Textarea } from "../../components/ui/textarea";
import { FailureNotice } from "../../ui/FailureNotice";
import { FieldProblems, problemAttributes } from "../../ui/FieldProblems";
import {
  addedSentence,
  addressImport,
  assignConsequence,
  assignedSentence,
  assignPath,
  assignQuestion,
  categoriesPath,
  categoriesTyped,
  categorisedSentence,
  chosen,
  editBody,
  editedSentence,
  EXAMPLES_FORMAT,
  examplesProblem,
  examplesTyped,
  isArchive,
  NO_EXAMPLE,
  IMPORT_PATH,
  importProblem,
  MAX_PACKAGE_BYTES,
  packageProblem,
  pasted,
  REHEARSAL_IS_A_PERSON_S_VERDICT,
  rehearsalBody,
  rehearsalsPath,
  rehearsedSentence,
  repositoryImport,
  SKILLS_API_PATH,
  versionsPath,
  type AgentChoice,
  type Assigned,
  type Categorised,
  type ExampleRow,
  type LibrarySkill,
  type PackageBody,
} from "../skillsQuery";

/** What a finished write says, drawn above the page while it is read again. */
export interface Told {
  readonly ok: boolean;
  readonly sentence: string;
}

export type Tell = (told: Told) => void;

export const PASTE_LABEL = "Paste a SKILL.md";
export const FILE_LABEL = "Or choose a file";
export const CATEGORIES_LABEL = "Categories";
export const ADD = "Add to the library";
export const IMPORT = "Import";
export const FROM_REPOSITORY = "From a GitHub repository";
export const FROM_ADDRESS = "From a web address";
export const REPOSITORY_LABEL = "Repository";
export const COMMIT_LABEL = "Commit";
export const FOLDER_LABEL = "Folder holding the SKILL.md";
export const ADDRESS_LABEL = "Address";
export const EDIT_LABEL = "The SKILL.md, edited";
export const SAVE_VERSION = "Save as a new version";
export const SET_CATEGORIES = "Save categories";
export const EXAMPLES_LABEL = "Example tasks";
export const EXAMPLE_TASK_LABEL = "Task";
export const EXAMPLE_EXPECTED_LABEL = "Behaviour expected";
export const ADD_EXAMPLE = "Add an example";
export const REMOVE_EXAMPLE = "Remove example";
export const ZIP_CARRIES_EXAMPLES = "A .zip carries its example tasks in its examples.json.";
export const RECORD_REHEARSAL = "Record the rehearsal";
export const BEHAVED = "Behaved as expected";
export const DID_NOT_BEHAVE = "Did not";
export const ANSWER_EVERY_EXAMPLE = "Say for every example whether it behaved as expected.";
export const ASSIGN_LABEL = "Agent";
export const ASSIGN = "Assign to agent";
export const DO_NOT_ASSIGN = "Do not assign";

/** The format lines, said before a person submits. */
export const PACKAGE_FORMAT =
  `A SKILL.md with a name, a description that opens "Use when", a version such as 1.0.0 and the tools ` +
  "it uses, with its example tasks typed below; or a .zip holding that file with the scripts it declares " +
  `and an examples.json listing each task and what is expected. At most ${String(MAX_PACKAGE_BYTES / 1024)} KB. ` +
  "A package exported from another install is added the same way and waits for review here.";
export const CATEGORIES_FORMAT =
  "Optional. Lower-case words or hyphenated words, separated by commas, at most eight: hosting, client-billing.";
export const REPOSITORY_FORMAT =
  "The repository as owner/repository, the full forty-character commit (not a branch), and the folder " +
  "holding the SKILL.md, left empty for the top folder. The SKILL.md, the scripts it declares and its " +
  "examples.json are taken, and nothing else in the folder.";
export const ADDRESS_FORMAT = "An https:// address on GitHub answering with a SKILL.md or a .zip holding one.";
export const EDIT_FORMAT =
  "The whole SKILL.md. Keep the name, and give a later version number than this one; the edit waits for review. " +
  "Its example tasks are below, and a new version is rehearsed against them before it can be approved.";

const PACKAGE_FORM = "skills-add";
const PACKAGE_FIELDS: readonly string[] = ["content", "file_name", "encoding", "categories"];
const PACKAGE_FILE_NAMES: readonly string[] = ["file_name", "encoding"];
const IMPORT_FORM = "skills-import";
const IMPORT_FIELDS: readonly string[] = ["kind", "repository", "commit", "path", "url", "categories"];

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

function Field({
  id,
  label,
  hint,
  children,
}: {
  readonly id: string;
  readonly label: string;
  readonly hint?: string | undefined;
  readonly children: ReactNode;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {hint === undefined ? null : <p className="m-0 text-[12px] leading-snug text-dim">{hint}</p>}
      {children}
    </div>
  );
}

function Problem({ text }: { readonly text: string | null }) {
  return text === null ? null : (
    <p role="alert" className="m-0 text-[12.5px] text-warn">
      {text}
    </p>
  );
}

/** One or more example tasks, each a task and the behaviour expected, typed in rows (M12.3.4). */
export function ExamplesField({
  id,
  rows,
  onChange,
}: {
  readonly id: string;
  readonly rows: readonly ExampleRow[];
  readonly onChange: (rows: readonly ExampleRow[]) => void;
}) {
  function set(index: number, next: Partial<ExampleRow>) {
    onChange(rows.map((row, at) => (at === index ? { ...row, ...next } : row)));
  }
  return (
    <fieldset className="m-0 flex min-w-0 flex-col gap-2 border-0 p-0">
      <legend className="mb-1 text-sm font-medium text-ink">{EXAMPLES_LABEL}</legend>
      <p className="m-0 text-[12px] leading-snug text-dim">{EXAMPLES_FORMAT}</p>
      <ol className="m-0 flex list-none flex-col gap-3 p-0">
        {rows.map((row, index) => {
          const taskId = `${id}-task-${String(index)}`;
          const expectedId = `${id}-expected-${String(index)}`;
          return (
            <li key={`${id}-${String(index)}`} className="flex min-w-0 flex-col gap-2 rounded-md border border-line p-3">
              <div className="flex min-w-0 flex-col gap-1.5">
                <Label htmlFor={taskId}>
                  {EXAMPLE_TASK_LABEL} {String(index + 1)}
                </Label>
                <Input
                  id={taskId}
                  name="examples.task"
                  value={row.task}
                  onChange={(event) => {
                    set(index, { task: event.target.value });
                  }}
                />
              </div>
              <div className="flex min-w-0 flex-col gap-1.5">
                <Label htmlFor={expectedId}>{EXAMPLE_EXPECTED_LABEL}</Label>
                <Input
                  id={expectedId}
                  name="examples.expected"
                  value={row.expected}
                  onChange={(event) => {
                    set(index, { expected: event.target.value });
                  }}
                />
              </div>
              <div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="min-h-11 sm:min-h-8"
                  aria-label={`${REMOVE_EXAMPLE} ${String(index + 1)}`}
                  onClick={() => {
                    onChange(rows.filter((_, at) => at !== index));
                  }}
                >
                  {REMOVE_EXAMPLE}
                </Button>
              </div>
            </li>
          );
        })}
      </ol>
      <div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="min-h-11 sm:min-h-8"
          onClick={() => {
            onChange([...rows, NO_EXAMPLE]);
          }}
        >
          {ADD_EXAMPLE}
        </Button>
      </div>
    </fieldset>
  );
}

/** Add by paste or upload (M42.6.4), with example tasks typed beside a SKILL.md (M12.3.4). */
export function AddSkillForm({ onTold }: { readonly onTold: Tell }) {
  const [text, setText] = useState("");
  const [file, setFile] = useState<PackageBody | null>(null);
  const [filed, setFiled] = useState("");
  const [examples, setExamples] = useState<readonly ExampleRow[]>([NO_EXAMPLE]);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const categories = categoriesTyped(filed);
  const archive = file !== null && isArchive(file.file_name);
  const body =
    file === null
      ? text.trim() === ""
        ? null
        : pasted(text, categories, examples)
      : { ...file, categories, examples: archive ? [] : examplesTyped(examples) };
  const problem = packageProblem(body) ?? (archive ? null : examplesProblem(examples));
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

  async function add(event: FormEvent<HTMLFormElement>) {
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
      setExamples([NO_EXAMPLE]);
      onTold({ ok: true, sentence: addedSentence(result.data) });
    } else {
      setFailure(result.failure);
    }
  }

  return (
    <form className="flex min-w-0 flex-col gap-3" aria-label="Add a skill" onSubmit={(event) => void add(event)}>
      <Note>{PACKAGE_FORMAT}</Note>
      {failure === null ? null : <FailureNotice failure={failure} fields={PACKAGE_FIELDS} />}
      <Field id="skills-paste" label={PASTE_LABEL}>
        <Textarea
          id="skills-paste"
          name="content"
          rows={8}
          className="font-mono text-[12.5px]"
          value={text}
          disabled={file !== null}
          placeholder={"---\nname: hosting-expiry\ndescription: Use when a client asks...\nversion: 1.0.0\ntools: [crm.read_client]\n---"}
          {...problemAttributes(problems, PACKAGE_FORM, "content")}
          onChange={(event) => {
            setText(event.target.value);
          }}
        />
        <FieldProblems problems={problems} form={PACKAGE_FORM} names="content" />
      </Field>
      <Field id="skills-file" label={FILE_LABEL} hint="A SKILL.md or a .zip.">
        <Input
          id="skills-file"
          type="file"
          name="file_name"
          accept=".md,.zip"
          {...problemAttributes(problems, PACKAGE_FORM, PACKAGE_FILE_NAMES)}
          onChange={(event) => void onChoose(event)}
        />
        <FieldProblems problems={problems} form={PACKAGE_FORM} names={PACKAGE_FILE_NAMES} />
      </Field>
      {archive ? <Note>{ZIP_CARRIES_EXAMPLES}</Note> : <ExamplesField id="skills-add-examples" rows={examples} onChange={setExamples} />}
      <Field id="skills-categories" label={CATEGORIES_LABEL} hint={CATEGORIES_FORMAT}>
        <Input
          id="skills-categories"
          name="categories"
          value={filed}
          {...problemAttributes(problems, PACKAGE_FORM, "categories")}
          onChange={(event) => {
            setFiled(event.target.value);
          }}
        />
        <FieldProblems problems={problems} form={PACKAGE_FORM} names="categories" />
      </Field>
      <Problem text={body === null ? null : problem} />
      <div>
        <Button type="submit" disabled={busy || problem !== null}>
          {ADD}
        </Button>
      </div>
    </form>
  );
}

type ImportFrom = "github" | "url";

/** Import from a GitHub repository at a commit, or from an address (M12.2.2, M12.2.3). */
export function ImportSkillForm({ onTold }: { readonly onTold: Tell }) {
  const [from, setFrom] = useState<ImportFrom>("github");
  const [repository, setRepository] = useState("");
  const [commit, setCommit] = useState("");
  const [folder, setFolder] = useState("");
  const [address, setAddress] = useState("");
  const [filed, setFiled] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const categories = categoriesTyped(filed);
  const body = from === "github" ? repositoryImport(repository, commit, folder, categories) : addressImport(address, categories);
  const problem = importProblem(body);
  const started = from === "github" ? repository !== "" || commit !== "" : address !== "";
  const problems = failure?.problems ?? [];

  async function importOne(event: FormEvent<HTMLFormElement>) {
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

  function field(id: string, label: string, name: string, value: string, set: (next: string) => void, hint?: string) {
    return (
      <Field id={id} label={label} hint={hint}>
        <Input
          id={id}
          name={name}
          value={value}
          {...problemAttributes(problems, IMPORT_FORM, name)}
          onChange={(event) => {
            set(event.target.value);
          }}
        />
        <FieldProblems problems={problems} form={IMPORT_FORM} names={name} />
      </Field>
    );
  }

  return (
    <form className="flex min-w-0 flex-col gap-3" aria-label="Import a skill" onSubmit={(event) => void importOne(event)}>
      <Note>{from === "github" ? REPOSITORY_FORMAT : ADDRESS_FORMAT}</Note>
      {failure === null ? null : <FailureNotice failure={failure} fields={IMPORT_FIELDS} />}
      <fieldset className="m-0 flex flex-wrap gap-4 border-0 p-0">
        <legend className="sr-only">Where from</legend>
        {(
          [
            ["github", FROM_REPOSITORY],
            ["url", FROM_ADDRESS],
          ] as const
        ).map(([value, label]) => (
          <label key={value} className="inline-flex min-h-11 items-center gap-2 text-[13px] text-ink sm:min-h-8">
            <input
              type="radio"
              name="kind"
              value={value}
              checked={from === value}
              onChange={() => {
                setFrom(value);
              }}
            />
            {label}
          </label>
        ))}
      </fieldset>
      {from === "github" ? (
        <>
          {field("skills-repository", REPOSITORY_LABEL, "repository", repository, setRepository, "owner/repository")}
          {field("skills-commit", COMMIT_LABEL, "commit", commit, setCommit, "All forty characters.")}
          {field("skills-folder", FOLDER_LABEL, "path", folder, setFolder, "Empty for the top folder.")}
        </>
      ) : (
        field("skills-address", ADDRESS_LABEL, "url", address, setAddress, "Starts with https://")
      )}
      {field("skills-import-categories", CATEGORIES_LABEL, "categories", filed, setFiled, CATEGORIES_FORMAT)}
      <Problem text={started ? problem : null} />
      <div>
        <Button type="submit" disabled={busy || problem !== null}>
          {IMPORT}
        </Button>
      </div>
    </form>
  );
}

/** An edit saved as a new version (M12.3.2). */
export function EditVersionForm({
  one,
  onTold,
  onDone,
}: {
  readonly one: LibrarySkill;
  readonly onTold: Tell;
  readonly onDone: () => void;
}) {
  const [text, setText] = useState(one.markdown ?? "");
  const [examples, setExamples] = useState<readonly ExampleRow[]>(
    (one.examples ?? []).length === 0 ? [NO_EXAMPLE] : (one.examples ?? []).map((item) => ({ task: item.task, expected: item.expected })),
  );
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const fieldId = `edit-${one.digest}`;
  const problem = text.trim() === "" ? "Write the SKILL.md before saving it." : examplesProblem(examples);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (problem !== null) {
      return;
    }
    setBusy(true);
    setFailure(null);
    const result = await request<LibrarySkill>(versionsPath(one.digest), { method: "POST", body: editBody(text, examples) });
    setBusy(false);
    if (result.ok) {
      onDone();
      onTold({ ok: true, sentence: editedSentence(result.data) });
    } else {
      setFailure(result.failure);
    }
  }

  return (
    <form className="flex min-w-0 flex-col gap-3" aria-label={`Edit ${one.name} ${one.version}`} onSubmit={(event) => void save(event)}>
      {failure === null ? null : <FailureNotice failure={failure} fields={["content", "examples"]} />}
      <Field id={fieldId} label={EDIT_LABEL} hint={EDIT_FORMAT}>
        <Textarea
          id={fieldId}
          name="content"
          rows={14}
          className="font-mono text-[12.5px]"
          value={text}
          onChange={(event) => {
            setText(event.target.value);
          }}
        />
      </Field>
      <ExamplesField id={`${fieldId}-examples`} rows={examples} onChange={setExamples} />
      <Problem text={problem} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={busy || problem !== null}>
          {SAVE_VERSION}
        </Button>
        <Button type="button" variant="outline" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

/** A skill's categories, set on its name for every version at once (M12.4.13). */
export function CategoriesForm({ one, onTold }: { readonly one: LibrarySkill; readonly onTold: Tell }) {
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
    <form className="flex min-w-0 flex-col gap-3" aria-label={`Categories of ${one.name}`} onSubmit={(event) => void save(event)}>
      {failure === null ? null : <FailureNotice failure={failure} fields={["categories"]} />}
      <Field id={fieldId} label={CATEGORIES_LABEL} hint={CATEGORIES_FORMAT}>
        <Input
          id={fieldId}
          name="categories"
          value={filed}
          onChange={(event) => {
            setFiled(event.target.value);
          }}
        />
      </Field>
      <div>
        <Button type="submit" variant="outline" size="sm" className="min-h-11 sm:min-h-8" disabled={busy}>
          {SET_CATEGORIES}
        </Button>
      </div>
    </form>
  );
}

/** Whether each example behaved as expected, one answer per example, none chosen (M12.3.4). */
export function RehearseForm({
  one,
  onTold,
  onDone,
}: {
  readonly one: LibrarySkill;
  readonly onTold: Tell;
  readonly onDone: () => void;
}) {
  const examples = one.examples ?? [];
  const [verdicts, setVerdicts] = useState<readonly (boolean | null)[]>(examples.map(() => null));
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const answered = verdicts.every((verdict) => verdict !== null);

  async function record(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!answered) {
      return;
    }
    setBusy(true);
    setFailure(null);
    const result = await request<LibrarySkill>(rehearsalsPath(one.digest), {
      method: "POST",
      body: rehearsalBody(verdicts.map((verdict) => verdict === true)),
    });
    setBusy(false);
    if (result.ok) {
      onDone();
      onTold({ ok: true, sentence: rehearsedSentence(result.data) });
    } else {
      setFailure(result.failure);
    }
  }

  return (
    <form
      className="flex min-w-0 flex-col gap-3"
      aria-label={`Rehearse ${one.name} ${one.version}`}
      onSubmit={(event) => void record(event)}
    >
      <Note>{REHEARSAL_IS_A_PERSON_S_VERDICT}</Note>
      {failure === null ? null : <FailureNotice failure={failure} fields={["behaved"]} />}
      <ol className="m-0 flex list-decimal flex-col gap-3 pl-5">
        {examples.map((example, index) => (
          <li key={`${String(index)}-${example.task}`} className="flex min-w-0 flex-col gap-1.5">
            <fieldset className="m-0 flex min-w-0 flex-col gap-1.5 border-0 p-0">
              <legend className="text-[13px] font-medium text-ink [overflow-wrap:anywhere]">{example.task}</legend>
              <p className="m-0 text-[12.5px] text-dim [overflow-wrap:anywhere]">Expected: {example.expected}</p>
              <span className="flex flex-wrap gap-4">
                {(
                  [
                    [true, BEHAVED],
                    [false, DID_NOT_BEHAVE],
                  ] as const
                ).map(([value, label]) => (
                  <label key={label} className="inline-flex min-h-11 items-center gap-2 text-[13px] text-ink sm:min-h-8">
                    <input
                      type="radio"
                      name={`behaved-${String(index)}`}
                      checked={verdicts[index] === value}
                      onChange={() => {
                        setVerdicts(verdicts.map((verdict, at) => (at === index ? value : verdict)));
                      }}
                    />
                    {label}
                  </label>
                ))}
              </span>
            </fieldset>
          </li>
        ))}
      </ol>
      <Problem text={answered ? null : ANSWER_EVERY_EXAMPLE} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={busy || !answered}>
          {RECORD_REHEARSAL}
        </Button>
        <Button type="button" variant="outline" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

/** Assign one approved version to one agent the API listed, confirmed first. */
export function AssignForm({
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

  async function assign() {
    if (agent === undefined) {
      return;
    }
    setBusy(true);
    setFailure(null);
    const result = await request<Assigned>(assignPath(one.digest), { method: "POST", body: { agent_id: agent.agent_id } });
    setBusy(false);
    setAsking(false);
    if (result.ok) {
      onTold({ ok: true, sentence: assignedSentence(result.data, agent) });
    } else {
      setFailure(result.failure);
    }
  }

  return (
    <>
      <form
        className="flex min-w-0 flex-col gap-2"
        aria-label={`Assign ${one.name} ${one.version}`}
        onSubmit={(event) => {
          event.preventDefault();
          setAsking(true);
        }}
      >
        {failure === null ? null : <FailureNotice failure={failure} fields={["agent_id"]} />}
        <div className="flex flex-wrap items-end gap-2">
          <Field id={fieldId} label={ASSIGN_LABEL} hint="The agents you may give a skill to.">
            <select
              id={fieldId}
              name="agent_id"
              className="h-11 min-w-0 rounded-md border border-input bg-panel px-2.5 text-sm text-ink shadow-xs outline-hidden focus-visible:ring-2 focus-visible:ring-ring sm:h-8"
              value={agentId}
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
          </Field>
          <Button type="submit" size="sm" className="min-h-11 sm:min-h-8" disabled={agent === undefined}>
            {ASSIGN}
          </Button>
        </div>
      </form>
      <ConfirmDialog
        open={asking && agent !== undefined}
        question={agent === undefined ? "Assign?" : assignQuestion(one, agent)}
        consequence={agent === undefined ? "" : assignConsequence(one, agent)}
        confirmLabel={ASSIGN}
        cancelLabel={DO_NOT_ASSIGN}
        busy={busy}
        onConfirm={() => void assign()}
        onCancel={() => {
          setAsking(false);
        }}
      />
    </>
  );
}
