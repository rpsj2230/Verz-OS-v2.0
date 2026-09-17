/**
 * What the Skills screen asks the API for, what it sends, and what it says. No React.
 *
 * The split is `governQuery.ts`'s and `recordsQuery.ts`': this decides what may be asked and
 * what a row is, the page renders it. The reason is the case that is always wrong, and here it
 * is a write: what a screen sends when a person presses Add cannot be tested through a component
 * that also mounts a form.
 *
 * **This screen is SCREEN 6 of `docs/screens.html`.** A library of skills with their source,
 * version, reviewer and state; a review pane with Approve and Reject; what each skill asks for;
 * and the drift between agents pinned to different bytes of one skill. `brain.skill_routes` serves
 * all of it from the library `0056` stores, and three writes: add a skill, decide about one, and
 * assign an approved one to an agent. The design's Paste URL and Connect repo are not here,
 * because nothing on an install fetches a skill from anywhere; a package is pasted or uploaded.
 *
 * **Nothing here decides who may do what.** `may_add`, `reviewable`, `assignable` and the list of
 * agents decide which controls are drawn, and each write asks every question again on the server.
 * The one check made here before a write is that there is something to send and that it is not
 * larger than the API accepts, so a person is told before they press rather than after.
 *
 * **No number about the library is rendered as a count.** Not a total, not a page number. The
 * listing is filtered per caller, so a figure is the subtraction `CLAUDE.md` forbids. The one count
 * on the page is the review queue's, which `brain.console.govern_estate.skill_queue` computes over
 * exactly the entries listed beneath it.
 *
 * Task ids: M42.6.4
 */

import type { components } from "../api/schema";
import { NO_QUESTION, listPath, type FilterChoice, type SortChoice } from "../components/listing";

/** One skill and the agents pinned to it, as `brain.skill_routes.SkillRow` sends it. */
export type SkillLibraryRow = components["schemas"]["SkillRow"];
/** One agent and the bytes of a skill it runs, as `SkillPinView` sends it. */
export type SkillPin = components["schemas"]["SkillPinView"];
/** One skill waiting for a reviewer, as `QueueEntryView` sends it. */
export type SkillQueueRow = components["schemas"]["QueueEntryView"];
/** One skill in the library, as `LibrarySkillView` sends it. */
export type LibrarySkill = components["schemas"]["LibrarySkillView"];
/** An agent this reader may assign a skill to, as `AgentChoiceView` sends it. */
export type AgentChoice = components["schemas"]["AgentChoiceView"];
/** What an assignment answered, as `AssignedView` sends it. */
export type Assigned = components["schemas"]["AssignedView"];
/** The body adding a skill sends, as `SkillPackageAsked` declares it. */
export type PackageBody = components["schemas"]["SkillPackageAsked"];

/** Where the API keeps this screen, and its three writes. */
export const SKILLS_API_PATH = "/skills";

export function reviewPath(digest: string): string {
  return `${SKILLS_API_PATH}/${encodeURIComponent(digest)}/review`;
}

export function assignPath(digest: string): string {
  return `${SKILLS_API_PATH}/${encodeURIComponent(digest)}/assignments`;
}

/** The console addresses. The second is one skill open. */
export const SKILLS_PATH = "/skills";

/** The filters the skills route declares that this screen offers, over values on rows drawn. */
export const SKILL_FILTERS: readonly FilterChoice<SkillLibraryRow>[] = [
  { column: "agents", label: "Agent", everything: "Any agent", read: (row) => row.pinned_by.map((one) => one.agent_id) },
  {
    column: "versions_differ",
    label: "Versions",
    everything: "Same or different",
    read: (row) => row.versions_differ,
    describe: (value) => (value === "true" ? "Agents run different versions" : "Every agent runs one version"),
  },
];

export const SKILL_SORTS: readonly SortChoice[] = [
  { value: "", label: "By name" },
  { value: "-name", label: "By name, last first" },
];

/**
 * The largest package the API reads, in bytes. `brain.console.skill_library.MAX_PACKAGE_BYTES`,
 * which the page test reads out of the Python source.
 */
export const MAX_PACKAGE_BYTES = 256 * 1024;

/**
 * The request for one skill's row, when a skill is open: a filter on its name, so the skill is found
 * whichever page of the list it would sit on. The route answers it over the agents this reader's
 * audience covers, so a name nobody's agent runs and a name run only by agents the reader may not
 * see are the same answer.
 */
export function skillApiPath(name: string): string {
  return listPath(SKILLS_API_PATH, { ...NO_QUESTION, filters: { name } }, null, 1);
}

/**
 * The console address for one skill's page.
 *
 * Built from a constant prefix and an encoded name, for the reason `governQuery.subjectAddress`
 * gives: GHSA-wrjc-x8rr-h8h6 is an open redirect through a backslash reaching `<Link>`, and what
 * holds the defence up is the literal first segment rather than the encoding.
 */
export function skillAddress(name: string): string {
  return `${SKILLS_PATH}/${encodeURIComponent(name)}`;
}

/** One page of skills, as this console holds it. */
export interface SkillsPage {
  readonly skills: readonly SkillLibraryRow[];
  readonly queue: readonly SkillQueueRow[];
  /** The queue's own counts, over exactly the entries above. */
  readonly waiting: number;
  readonly edits: number;
  readonly stale: number;
  /** The agent load came back full. Never how much more there is. */
  readonly truncated: boolean;
  readonly library: readonly LibrarySkill[];
  /** The library load came back full. Never how much more there is. */
  readonly libraryTruncated: boolean;
  /** The agents this reader may assign an approved skill to. */
  readonly agents: readonly AgentChoice[];
  /** This reader may add a skill. Presentation only. */
  readonly mayAdd: boolean;
  /** No tool registry on the API's process, so no tool a skill names could be resolved. */
  readonly registryIsAbsent: boolean;
}

const NOTHING: SkillsPage = Object.freeze({
  skills: [],
  queue: [],
  waiting: 0,
  edits: 0,
  stale: 0,
  truncated: false,
  library: [],
  libraryTruncated: false,
  agents: [],
  // False on an unreadable body: a control drawn for an answer this console could not read is a
  // control whose every press is refused.
  mayAdd: false,
  registryIsAbsent: false,
});

/**
 * Read `brain.skill_routes.SkillsPage` out of a response body.
 *
 * **`total` and `next_cursor` stop here**, in the way `readPeoplePage` stops them. An unreadable
 * body yields an empty page offering nothing rather than throwing, which is `readMatrixPage`'s
 * choice and for its reason.
 */
export function readSkillsPage(payload: unknown): SkillsPage {
  if (typeof payload !== "object" || payload === null) {
    return NOTHING;
  }
  const body = payload as {
    items?: unknown;
    queue?: unknown;
    truncated?: unknown;
    library?: unknown;
    library_truncated?: unknown;
    agents?: unknown;
    may_add?: unknown;
    registry_is_absent?: unknown;
  };
  if (!Array.isArray(body.items)) {
    return NOTHING;
  }
  const queue = body.queue as
    | { entries?: unknown; waiting?: unknown; edits?: unknown; stale?: unknown }
    | undefined;
  return {
    skills: body.items as SkillLibraryRow[],
    queue: Array.isArray(queue?.entries) ? (queue.entries as SkillQueueRow[]) : [],
    waiting: typeof queue?.waiting === "number" ? queue.waiting : 0,
    edits: typeof queue?.edits === "number" ? queue.edits : 0,
    stale: typeof queue?.stale === "number" ? queue.stale : 0,
    truncated: body.truncated === true,
    library: Array.isArray(body.library) ? (body.library as LibrarySkill[]) : [],
    libraryTruncated: body.library_truncated === true,
    agents: Array.isArray(body.agents) ? (body.agents as AgentChoice[]) : [],
    mayAdd: body.may_add === true,
    registryIsAbsent: body.registry_is_absent === true,
  };
}

/** The pinned skill with this name among the ones on the page, or null. Never by a prefix. */
export function skillIn(
  skills: readonly SkillLibraryRow[],
  name: string,
): SkillLibraryRow | null {
  return skills.find((one) => one.name === name) ?? null;
}

/** Every version of one skill in the library, newest first as the API ordered them. */
export function versionsOf(library: readonly LibrarySkill[], name: string): readonly LibrarySkill[] {
  return library.filter((one) => one.name === name);
}

/**
 * The rows whose agents do not all run the same bytes. The API's marker, never a comparison
 * this console made over rows it may not have all of.
 */
export function driftingRows(skills: readonly SkillLibraryRow[]): readonly SkillLibraryRow[] {
  return skills.filter((one) => one.versions_differ);
}

// ------------------------------------------------------------------------- the words

/** What each review state reads as. `brain.console.agent_tabs.Review`, which the test reads. */
export const REVIEW_WORDS: Readonly<Record<string, string>> = Object.freeze({
  pending: "waiting for review",
  approved: "approved",
  rejected: "rejected",
  changed: "changed since it was approved, so nobody has read what is there",
});

export function reviewWords(review: string): string {
  return REVIEW_WORDS[review] ?? review;
}

/** Why a package cannot be sent yet, or null. The API decides everything else. */
export function packageProblem(body: PackageBody | null): string | null {
  if (body === null || body.content.trim() === "") {
    return "Paste a SKILL.md, or choose a SKILL.md or a .zip holding one.";
  }
  const bytes =
    body.encoding === "base64"
      ? Math.floor((body.content.length * 3) / 4)
      : new TextEncoder().encode(body.content).length;
  if (bytes > MAX_PACKAGE_BYTES) {
    return `A package is at most ${String(MAX_PACKAGE_BYTES / 1024)} KB, and this one is larger.`;
  }
  return null;
}

/** A pasted `SKILL.md`, as the add route takes it. */
export function pasted(text: string): PackageBody {
  return { file_name: "SKILL.md", content: text, encoding: "text" };
}

/** Bytes as base64, without a library: a zip is sent this way and a `SKILL.md` as text. */
export function base64Of(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary);
}

/** A chosen file, as the add route takes it: a zip as base64 and anything else as text. */
export function chosen(fileName: string, bytes: Uint8Array): PackageBody {
  if (fileName.toLowerCase().endsWith(".zip")) {
    return { file_name: fileName, content: base64Of(bytes), encoding: "base64" };
  }
  return { file_name: fileName, content: new TextDecoder().decode(bytes), encoding: "text" };
}

/** The sentence after a skill was added. */
export function addedSentence(one: LibrarySkill): string {
  return (
    `${one.name} ${one.version} was added and is waiting for review. It cannot be assigned to an ` +
    "agent until somebody other than you approves it."
  );
}

export function decisionQuestion(one: LibrarySkill, approve: boolean): string {
  return `${approve ? "Approve" : "Reject"} ${one.name} ${one.version}?`;
}

export function decisionConsequence(one: LibrarySkill, approve: boolean): string {
  return approve
    ? `These exact words, added by ${one.submitted_by}, can then be assigned to agents. An edit ` +
        "to them later is a new version that needs a review of its own. The decision is recorded " +
        "in the audit trail under your name and cannot be changed."
    : `This version, added by ${one.submitted_by}, can never be assigned to an agent. The ` +
        "decision is recorded in the audit trail under your name and cannot be changed.";
}

export function decidedSentence(one: LibrarySkill): string {
  return `${one.name} ${one.version} is ${reviewWords(one.review)}.`;
}

export function assignQuestion(one: LibrarySkill, agent: AgentChoice): string {
  return `Assign ${one.name} ${one.version} to ${agent.display_name}?`;
}

export function assignConsequence(one: LibrarySkill, agent: AgentChoice): string {
  return (
    `${agent.display_name} is pinned to these exact words from its next request, in place of any ` +
    `other version of ${one.name} it runs. What the skill can use is only what ` +
    `${agent.display_name} is already allowed and the person asking already holds. The change is ` +
    "recorded in the audit trail."
  );
}

export function assignedSentence(done: Assigned, agent: AgentChoice | undefined): string {
  const who = agent?.display_name ?? done.agent_id;
  const reach =
    done.reach.length === 0
      ? "Through that agent it can use none of the tools it names for you."
      : `Through that agent it can use, for you: ${done.reach.join(", ")}.`;
  return `${done.skill_name} was assigned to ${who}. ${reach}`;
}
