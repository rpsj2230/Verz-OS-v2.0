/**
 * What the Skills screen asks the API for, what it sends, and what it says. No React.
 *
 * The split is `governQuery.ts`'s and `recordsQuery.ts`': this decides what may be asked and
 * what a row is, the page renders it. The reason is the case that is always wrong, and here it
 * is a write: what a screen sends when a person presses Add cannot be tested through a component
 * that also mounts a form.
 *
 * **This screen is SCREEN 6 of `docs/screens.html`.** A library of skills with their source,
 * version, reviewer and state; a review pane with Approve and Reject and the words that changed;
 * what each skill asks for; and the drift between agents pinned to different bytes of one skill.
 * `brain.skill_routes` serves all of it from the library `0056` and `0121` store, and six writes:
 * add a pasted or chosen package, import from a GitHub repository at a commit or from an address
 * (the design's Connect repo and Paste URL), save an edit as a new version, set a skill's
 * categories, decide about one, and assign an approved one to an agent.
 *
 * **The library list is `GET /skills/library`, searched and filtered by the route** (M27.11.8), and
 * one skill's page reads `GET /skills` narrowed to its name. The paths for the lifecycle writes,
 * retiring, reinstating and detaching (M27.15.55, M27.15.56), are here with the others.
 *
 * **A package carries its scripts and example tasks, a version with examples is rehearsed before it
 * is approved, and an approved version is exported (M12.4.11, M12.3.4, M12.3.1).** The rehearsal
 * and the export are writes like the others; the export answers the package as base64, which
 * `packageFile` turns back into the zip a person saves, and another install adds it undecided.
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
 * Task ids: M42.6.4, M12.2.2, M12.2.3, M12.2.6, M12.3.2, M12.4.6, M12.4.13, M27.16.1, M12.4.11,
 * M12.3.4, M12.3.1
 */

import type { components } from "../api/schema";
import { NO_QUESTION, listPath } from "../components/listing";

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
/** The body an import sends, as `SkillImportAsked` declares it. */
export type ImportBody = components["schemas"]["SkillImportAsked"];
/** The body an edit sends, as `SkillEditAsked` declares it. */
export type EditBody = components["schemas"]["SkillEditAsked"];
/** The body setting categories sends, and what it answers. */
export type CategoriesBody = components["schemas"]["CategoriesAsked"];
export type Categorised = components["schemas"]["CategoriesView"];
/** The words that changed, as `SkillDiffView` sends them. */
export type SkillDiff = components["schemas"]["SkillDiffView"];
/** One version on the searchable library list, as `SkillVersionRowView` sends it (M27.11.8). */
export type LibraryRow = components["schemas"]["SkillVersionRowView"];
/** What a retirement or a reinstatement answered, as `RetirementView` sends it (M27.15.56). */
export type Retired = components["schemas"]["RetirementView"];
/** What a detachment answered, as `DetachedView` sends it (M27.15.55). */
export type Detached = components["schemas"]["DetachedView"];
/** One script a version carries, as `ScriptView` sends it (M12.4.11). */
export type SkillScript = components["schemas"]["ScriptView"];
/** One example task and the behaviour expected, as `ExampleView` sends it (M12.3.4). */
export type SkillExample = components["schemas"]["ExampleView"];
/** The newest rehearsal of a version, as `RehearsalView` sends it (M12.3.4). */
export type SkillRehearsal = components["schemas"]["SkillRehearsalView"];
/** The body a rehearsal sends, as `RehearsalAsked` declares it. */
export type RehearsalBody = components["schemas"]["RehearsalAsked"];
/** An exported package, as `SkillPackageView` sends it (M12.3.1). */
export type ExportedPackage = components["schemas"]["SkillPackageView"];

/** Where the API keeps this screen, and its writes. */
export const SKILLS_API_PATH = "/skills";

/** Where a repository or an address import is sent. */
export const IMPORT_PATH = `${SKILLS_API_PATH}/imports`;

/** The searchable library: one row per version, searched and filtered by the route (M27.11.8). */
export const LIBRARY_API_PATH = `${SKILLS_API_PATH}/library`;

export function retirementPath(digest: string): string {
  return `${SKILLS_API_PATH}/${encodeURIComponent(digest)}/retirement`;
}

export function reinstatementPath(digest: string): string {
  return `${SKILLS_API_PATH}/${encodeURIComponent(digest)}/reinstatement`;
}

export function detachPath(digest: string): string {
  return `${SKILLS_API_PATH}/${encodeURIComponent(digest)}/detachments`;
}

export function versionsPath(digest: string): string {
  return `${SKILLS_API_PATH}/${encodeURIComponent(digest)}/versions`;
}

export function categoriesPath(digest: string): string {
  return `${SKILLS_API_PATH}/${encodeURIComponent(digest)}/categories`;
}

/** The column the skills-in-use listing filters categories on. `brain.skill_routes`' own. */
export const CATEGORY_COLUMN = "categories";

export function reviewPath(digest: string): string {
  return `${SKILLS_API_PATH}/${encodeURIComponent(digest)}/review`;
}

export function assignPath(digest: string): string {
  return `${SKILLS_API_PATH}/${encodeURIComponent(digest)}/assignments`;
}

/** Where a rehearsal of one version's examples is recorded (M12.3.4). */
export function rehearsalsPath(digest: string): string {
  return `${SKILLS_API_PATH}/${encodeURIComponent(digest)}/rehearsals`;
}

/** Where one approved version is exported as a package (M12.3.1). */
export function exportsPath(digest: string): string {
  return `${SKILLS_API_PATH}/${encodeURIComponent(digest)}/exports`;
}

/** The console addresses. The second is one skill open. */
export const SKILLS_PATH = "/skills";

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
  /** The category chips: those of the skills on this page, and no other. */
  readonly categories: readonly string[];
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
  categories: [],
});

/**
 * Read `brain.skill_routes.SkillsPage` out of a response body.
 *
 * **`total` and `next_cursor` stop here**, in the way `people/peopleQuery.readPeople` stops them. An unreadable
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
    categories?: unknown;
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
    categories: Array.isArray(body.categories)
      ? body.categories.filter((one): one is string => typeof one === "string")
      : [],
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

/**
 * Categories as a person typed them, split on commas. The API folds, deduplicates and refuses
 * them; this only splits, so what it refuses is what was typed.
 */
export function categoriesTyped(text: string): string[] {
  return text
    .split(",")
    .map((one) => one.trim())
    .filter((one) => one !== "");
}

/** A pasted `SKILL.md`, as the add route takes it. */
export function pasted(text: string, categories: readonly string[] = []): PackageBody {
  return { file_name: "SKILL.md", content: text, encoding: "text", categories: [...categories] };
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
export function chosen(
  fileName: string,
  bytes: Uint8Array,
  categories: readonly string[] = [],
): PackageBody {
  if (fileName.toLowerCase().endsWith(".zip")) {
    return { file_name: fileName, content: base64Of(bytes), encoding: "base64", categories: [...categories] };
  }
  return {
    file_name: fileName,
    content: new TextDecoder().decode(bytes),
    encoding: "text",
    categories: [...categories],
  };
}

/** A repository import at one commit, as the import route takes it. */
export function repositoryImport(
  repository: string,
  commit: string,
  path: string,
  categories: readonly string[] = [],
): ImportBody {
  return {
    kind: "github",
    repository: repository.trim(),
    commit: commit.trim(),
    path: path.trim(),
    url: "",
    categories: [...categories],
  };
}

/** An address import, as the import route takes it. */
export function addressImport(url: string, categories: readonly string[] = []): ImportBody {
  return { kind: "url", repository: "", commit: "", path: "", url: url.trim(), categories: [...categories] };
}

/** `owner/repo`, as GitHub spells it. The API's own check is `brain.tools.skills.GITHUB_REPO_RE`. */
const REPOSITORY_SHAPE = /^[A-Za-z0-9][A-Za-z0-9._-]*\/[A-Za-z0-9][A-Za-z0-9._-]*$/;

/** A full commit sha: forty hexadecimal digits. A branch or a short sha moves, so neither is one. */
const COMMIT_SHAPE = /^[0-9a-fA-F]{40}$/;

/** Why an import cannot be sent yet, or null. The API decides everything else, fetch included. */
export function importProblem(body: ImportBody): string | null {
  if (body.kind === "github") {
    if (!REPOSITORY_SHAPE.test(body.repository ?? "")) {
      return "Name the repository as owner/repository.";
    }
    if (!COMMIT_SHAPE.test(body.commit ?? "")) {
      return "Give the full forty-character commit, not a branch or a short commit.";
    }
    return null;
  }
  if (!(body.url ?? "").startsWith("https://")) {
    return "Give an https address.";
  }
  return null;
}

/** The sentence after a skill was added or imported. */
export function addedSentence(one: LibrarySkill): string {
  return (
    `${one.name} ${one.version} was added and is waiting for review. It cannot be assigned to an ` +
    "agent until it is approved; if you may review skills you may approve it yourself, and the " +
    "audit trail records that it was your own."
  );
}

/** The sentence after an edit was saved. */
export function editedSentence(one: LibrarySkill): string {
  return (
    `${one.name} ${one.version} was saved as a new version and is waiting for review. Every agent ` +
    "keeps the version it runs until somebody assigns this one."
  );
}

/** The sentence after categories were set. */
export function categorisedSentence(done: Categorised): string {
  return done.categories.length === 0
    ? `${done.name} is in no category.`
    : `${done.name} is filed under ${done.categories.join(", ")}.`;
}

/** Where a skill came from, in words. The commit itself is an identifier, kept for Advanced. */
export function sourceWords(one: LibrarySkill): string {
  if (one.source === "github") {
    const where = one.source_path === null ? "its top folder" : `the folder ${one.source_path}`;
    return `from the GitHub repository ${one.source_location} at one commit, ${where}`;
  }
  if (one.source === "url") {
    return `from ${one.source_location}`;
  }
  return `as ${one.source_location}`;
}

export function decisionQuestion(one: LibrarySkill, approve: boolean): string {
  return `${approve ? "Approve" : "Reject"} ${one.name} ${one.version}?`;
}

/** A person as the page names them: the directory's name, or a plain word when it has none. */
export function personWords(name: string | null | undefined, otherwise: string): string {
  return name === null || name === undefined || name.trim() === "" ? otherwise : name;
}

export function decisionConsequence(one: LibrarySkill, approve: boolean): string {
  const by = personWords(one.submitted_by_name, "the person who added it");
  const own = " If you added it yourself, the audit trail records the decision as your own.";
  return approve
    ? `These exact words, added by ${by}, can then be assigned to agents. An edit ` +
        "to them later is a new version that needs a review of its own. The decision is recorded " +
        `in the audit trail under your name and cannot be changed.${own}`
    : `This version, added by ${by}, can never be assigned to an agent. The ` +
        `decision is recorded in the audit trail under your name and cannot be changed.${own}`;
}

/** How a decision reads beside the skill, saying when it was the importer's own. */
export function decisionWords(one: LibrarySkill): string {
  if (one.reviewer === null) {
    return "";
  }
  const who = personWords(one.reviewer_name, "a reviewer");
  return one.self_decided ? `decided by ${who}, who added it` : `decided by ${who}`;
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

// ------------------------------------------------------------------- rehearsing and exporting

/** What a rehearsal is on this install today, said beside the form rather than implied. */
export const REHEARSAL_IS_A_PERSON_S_VERDICT =
  "No model carries out a skill here yet, so a rehearsal is you reading each example against these " +
  "instructions, or trying it yourself, and saying whether it behaved as expected. It is recorded " +
  "under your name for exactly this version.";

/** Why Approve is not drawn yet for a version with examples. */
export const REHEARSE_BEFORE_APPROVING =
  "This version has example tasks, so it can be approved only after a rehearsal in which every " +
  "example behaved as expected. Reject is still open.";

/** The rehearsal a person sends: one verdict per example, in order. */
export function rehearsalBody(behaved: readonly boolean[]): RehearsalBody {
  return { behaved: [...behaved] };
}

/** How a rehearsal reads beside the version. */
export function rehearsalWords(done: SkillRehearsal): string {
  const who = personWords(done.rehearsed_by_name, "somebody");
  const behaved = done.behaved.filter((one) => one).length;
  return done.passed
    ? `Rehearsed by ${who}: every example behaved as expected.`
    : `Rehearsed by ${who}: ${String(behaved)} of the ${String(done.behaved.length)} examples behaved as expected.`;
}

/** The sentence after a rehearsal was recorded. */
export function rehearsedSentence(one: LibrarySkill): string {
  return one.awaits_rehearsal === true
    ? `The rehearsal of ${one.name} ${one.version} was recorded. Not every example behaved, so it cannot be approved yet.`
    : `The rehearsal of ${one.name} ${one.version} was recorded. It can now be approved.`;
}

/** What exporting does, said on the button's page before it is pressed. */
export const EXPORT_WORDS =
  "Saves this approved version as a .zip another install can add. It arrives there waiting for " +
  "review; the approval here does not travel with it.";

/** The sentence after a package was saved. */
export function exportedSentence(done: ExportedPackage): string {
  return `${done.name} ${done.version} was saved as ${done.file_name}. Add it on another install to review it there.`;
}

/**
 * Hand the package to the browser as a file, from the base64 the route answered with, as a `data:`
 * address a link saves. Nothing here decodes it: the bytes go to the file as they came.
 */
export function savePackage(done: ExportedPackage, into: Document = globalThis.document): boolean {
  if (typeof into.createElement !== "function") {
    return false;
  }
  const link = into.createElement("a");
  link.href = `data:application/zip;base64,${done.content}`;
  link.download = done.file_name;
  into.body.appendChild(link);
  link.click();
  link.remove();
  return true;
}
