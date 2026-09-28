/**
 * What the Overview asks and how each answer is read. No React.
 *
 * **Five reads, each decided by the screen that owns it, and none decided here.** The health strip
 * and Needs you are `GET /console/overview` (`brain.console_overview_routes`, PR #157): readiness,
 * when the worker was last seen, and each queue the reader may act on with the length of the list
 * its own screen would show them. How the last week's requests ended is `GET
 * /console/overview/figures`. Active agents are counted over the roster the audience sends
 * (`GET /agents`) and connected sources over the Connectors screen's list (`GET /connectors`), so a
 * card is a count of rows the reader was already shown and never a second answer to who may see an
 * agent or a source. Recent activity is the audit ledger's newest page (`GET /audit`).
 *
 * **A figure nothing sent is absent, and a figure the API says is not recorded is "Not recorded
 * yet", never nought.** Every reader here returns `undefined` or `null` for a body it cannot read,
 * and the page then draws no card rather than a zero. `kit/KpiStrip.tsx` draws the sentence.
 *
 * **A queue the reader may not act on was never sent, so it is never drawn.** The route leaves it
 * out rather than sending it as nought, and this file adds no list of queues to fill the gap: a
 * line reading "Access review 0" to somebody who may not open access review says the queue exists
 * and is being kept from them.
 *
 * **The overview route is not in the generated schema until PR #157 lands**, so its shape is typed
 * here from `brain.console_overview_routes.OverviewView` and read field by field, keeping only what
 * was sent. The figures route is this package's own and comes from the generated schema.
 *
 * Task ids: M27.15.17, M27.16.1
 */

import type { components } from "../../api/schema";
import { readLedgerPage, phraseFor, type AuditRow } from "../auditQuery";
import { readConnectors, wasRead, type Connectors } from "../connectorsQuery";

// ---------------------------------------------------------------------------------- addresses

/** The health strip and Needs you, under the API base. */
export const OVERVIEW_API_PATH = "/console/overview";

/** How the last seven days' requests ended. */
export const FIGURES_API_PATH = "/console/overview/figures";

/** The roster, read wide enough to count one page of it. The route's own largest page. */
export const ROSTER_PAGE_ROWS = 200;
export const AGENTS_API_PATH = `/agents?limit=${String(ROSTER_PAGE_ROWS)}`;

/** The connected sources. */
export const SOURCES_API_PATH = "/connectors";

/** How many audit entries the activity card shows. */
export const ACTIVITY_ROWS = 6;
export const ACTIVITY_API_PATH = `/audit?limit=${String(ACTIVITY_ROWS)}`;

/** Where the whole audit log is. */
export const AUDIT_PATH = "/audit";

// ----------------------------------------------------------------------------------- shapes

/** A figure or queue the API names that nothing on this install records, and why. */
export interface NotRecorded {
  readonly figure: string;
  readonly why: string;
}

/** One part of the install, as `brain.readiness.ReadinessPart` sends it. */
export interface ReadinessPart {
  readonly name: string;
  readonly state: string;
}

/** One queue this reader may act on, and how many items in it they may act on. */
export interface WaitingQueue {
  readonly queue: string;
  readonly waiting: number;
  /** The list was read to its bound, so the figure is at least this. */
  readonly atLeast: boolean;
  /** The console page the queue opens, when the API sent one this console can link to. */
  readonly opens?: string;
}

/** One halt in force the reader may be told of: what it stops, and since when. */
export interface Halt {
  /** `brain.ops.halt.HaltScope`: everything, department, agent, connector or person. */
  readonly scope: string;
  /** What a targeted halt names; empty for a halt on everything. */
  readonly target: string;
  readonly since: string;
}

/** The overview as this console holds it. */
export interface OverviewAnswer {
  readonly status: string;
  readonly parts: readonly ReadinessPart[];
  /** The halts in force, widest first. Empty when nothing is stopped or the state is unknown. */
  readonly halts: readonly Halt[];
  /**
   * Whether the halts could be read. Absent when the API sent no word on it, which is a route
   * older than the halt store, and then the strip says what `unrecorded` says instead.
   */
  readonly haltsKnown?: boolean;
  readonly workerLastSeen?: string;
  readonly healthNotRecorded: readonly NotRecorded[];
  readonly needsYou: readonly WaitingQueue[];
  readonly uncounted: readonly NotRecorded[];
}

/** The figure row's own answer, from the generated schema. */
export type FiguresBody = components["schemas"]["OverviewFiguresView"];

/** The figure row as this console holds it. */
export interface Figures {
  readonly basis: string;
  readonly answered: number;
  readonly nothingReturned: number;
  readonly notRecorded: readonly NotRecorded[];
}

// ---------------------------------------------------------------------------------- readers

type Fields = Readonly<Record<string, unknown>>;

function fieldsOf(value: unknown): Fields | null {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Fields) : null;
}

function text(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

function count(value: unknown): number | undefined {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : undefined;
}

function listOf(value: unknown): readonly unknown[] {
  return Array.isArray(value) ? value : [];
}

/** Entries of a `{figure, why}` list, keeping every one that is one. */
export function readNotRecorded(value: unknown): NotRecorded[] {
  const read: NotRecorded[] = [];
  for (const one of listOf(value)) {
    const entry = fieldsOf(one);
    const figure = text(entry?.["figure"]);
    const why = text(entry?.["why"]);
    if (figure !== undefined && why !== undefined) {
      read.push({ figure, why });
    }
  }
  return read;
}

/** A console address the page may link to: absolute inside this console, never another origin. */
function consoleAddress(value: unknown): string | undefined {
  const address = text(value);
  return address !== undefined && address.startsWith("/") && !address.startsWith("//") ? address : undefined;
}

/**
 * The overview out of a response body, or `null` when the body is not one.
 *
 * `null` for a body with no health or no Needs you list, rather than an empty strip, because an
 * empty Needs you is a claim that nothing waits on the reader and a body that is not an overview
 * makes no such claim. A queue line that is malformed is dropped, never drawn as nought.
 */
export function readOverview(payload: unknown): OverviewAnswer | null {
  const body = fieldsOf(payload);
  const health = fieldsOf(body?.["health"]);
  const status = text(health?.["status"]);
  if (body === null || health === null || status === undefined || !Array.isArray(body["needs_you"])) {
    return null;
  }
  const parts: ReadinessPart[] = [];
  for (const one of listOf(health["parts"])) {
    const part = fieldsOf(one);
    const name = text(part?.["name"]);
    const state = text(part?.["state"]);
    if (name !== undefined && state !== undefined) {
      parts.push({ name, state });
    }
  }
  const needsYou: WaitingQueue[] = [];
  for (const one of listOf(body["needs_you"])) {
    const line = fieldsOf(one);
    const queue = text(line?.["queue"]);
    const waiting = count(line?.["waiting"]);
    if (queue === undefined || waiting === undefined) {
      continue;
    }
    const opens = consoleAddress(line?.["opens"]);
    needsYou.push({ queue, waiting, atLeast: line?.["at_least"] === true, ...(opens === undefined ? {} : { opens }) });
  }
  const halts: Halt[] = [];
  for (const one of listOf(health["halts"])) {
    const halt = fieldsOf(one);
    const scope = text(halt?.["scope"]);
    const since = text(halt?.["since"]);
    const target = halt?.["target"];
    if (scope !== undefined && since !== undefined && typeof target === "string") {
      halts.push({ scope, target: target.trim(), since });
    }
  }
  const known = health["halts_known"];
  const seen = text(health["worker_last_seen"]);
  return {
    status,
    parts,
    // A halt the API sent but this reader cannot read is still a stop, so an unreadable entry
    // makes the whole state unknown rather than dropping to "Nothing stopped".
    halts,
    ...(typeof known === "boolean"
      ? { haltsKnown: known && halts.length === listOf(health["halts"]).length }
      : {}),
    ...(seen === undefined ? {} : { workerLastSeen: seen }),
    healthNotRecorded: readNotRecorded(health["unrecorded"]),
    needsYou,
    uncounted: readNotRecorded(body["uncounted"]),
  };
}

/** The figure row out of a response body, or `null` when a figure is not a count. */
export function readFigures(payload: unknown): Figures | null {
  const body = fieldsOf(payload);
  const basis = text(body?.["basis"]);
  const answered = count(body?.["answered"]);
  const nothingReturned = count(body?.["nothing_returned"]);
  if (basis === undefined || answered === undefined || nothingReturned === undefined) {
    return null;
  }
  return { basis, answered, nothingReturned, notRecorded: readNotRecorded(body?.["not_recorded"]) };
}

/** A count of rows a list route sent, and whether it sent a full page with more behind it. */
export interface Counted {
  readonly value: number;
  readonly atLeast: boolean;
}

/**
 * How many of the agents on one page of the roster are switched on, or `undefined`.
 *
 * The roster says an agent's state only to a reader of its Settings tab. A page on which any agent
 * arrived without one is a page whose states this reader was not told, so there is no honest count
 * of the switched-on ones and the card is left out rather than drawn from the ones that happened to
 * carry a state. An empty page is a count of nought over what the reader may see, which is true.
 */
export function activeAgents(payload: unknown): Counted | undefined {
  const body = fieldsOf(payload);
  const items = body?.["items"];
  if (!Array.isArray(items)) {
    return undefined;
  }
  const states = items.map((one) => text(fieldsOf(one)?.["state"]));
  if (states.some((one) => one === undefined)) {
    return undefined;
  }
  return { value: states.filter((one) => one === "enabled").length, atLeast: body?.["truncated"] === true };
}

/** How many sources the Connectors screen lists to this reader, or why it lists none. */
export function connectedSources(payload: unknown): Counted | { readonly unread: string } | undefined {
  const body = fieldsOf(payload);
  if (body === null) {
    return undefined;
  }
  // A cast at the boundary: `readConnectors` reads the two fields it needs and nothing else.
  const read = readConnectors(body as unknown as Connectors);
  if (!wasRead(read)) {
    return read.unread === "" ? undefined : { unread: read.unread };
  }
  return Array.isArray(read.rows) ? { value: read.rows.length, atLeast: false } : undefined;
}

/** The newest audit entries this reader may read, at most `ACTIVITY_ROWS`. */
export function recentActivity(payload: unknown): readonly AuditRow[] {
  return readLedgerPage(payload)
    .rows.filter((row) => typeof row.at === "string" && typeof row.action === "string")
    .slice(0, ACTIVITY_ROWS);
}

// ------------------------------------------------------------------------------------ words

/** A sentence with its first letter upper cased, in a fixed locale. */
export function capitalised(words: string): string {
  return `${words.slice(0, 1).toLocaleUpperCase("en-GB")}${words.slice(1)}`;
}

/** A key such as `sign_in` as words: "Sign in". Used only where no label is written below. */
export function humanised(key: string): string {
  const words = key.replace(/[_-]+/g, " ").trim();
  return words === "" ? key : capitalised(words);
}

/** Each queue's line on Needs you, in the design's words. */
export const QUEUE_LABELS: Readonly<Record<string, string>> = Object.freeze({
  approvals: "Approvals waiting",
  access_review: "Access to review",
  elevation: "Elevation requests",
  skill_reviews: "Skills awaiting review",
  tier_three_learning: "Learning changes to decide",
  publish_approvals: "Publishes awaiting a second approver",
  unbound_sign_ins: "Sign-ins waiting to be linked",
  knowledge_past_review: "Knowledge past its review date",
});

/**
 * Where each queue is worked, for a queue the API named but could not count, which carries no
 * address of its own. The same pages `brain.console.needs_you.OPENS` sends for a counted queue.
 */
export const QUEUE_PAGES: Readonly<Record<string, string>> = Object.freeze({
  approvals: "/approvals",
  access_review: "/access_review",
  elevation: "/elevation",
  skill_reviews: "/skills",
  tier_three_learning: "/learning",
  publish_approvals: "/agents",
  unbound_sign_ins: "/sign-in-links",
  knowledge_past_review: "/library",
});

export function queueLabel(queue: string): string {
  return QUEUE_LABELS[queue] ?? humanised(queue);
}

/** A queue's figure: the count, or "at least" it when the list was read to its bound. */
export function waitingWords(line: WaitingQueue): string {
  const figure = line.waiting.toLocaleString("en-GB");
  return line.atLeast ? `at least ${figure}` : figure;
}

/** The install's state in a word an administrator reads. Anything else is shown as sent. */
export function readinessWords(status: string): string {
  return status === "ok" ? "Ready" : status === "degraded" ? "Degraded" : humanised(status);
}

const PART_NAMES: Readonly<Record<string, string>> = Object.freeze({
  database: "Database",
  cache: "Cache",
  vault: "Secret store",
  sign_in: "Sign-in",
});

const PART_STATES: Readonly<Record<string, string>> = Object.freeze({
  ready: "ready",
  not_ready: "not ready",
  not_configured: "not set up",
});

/** One part as a person reads it: "Database: ready". */
export function partWords(part: ReadinessPart): string {
  return `${PART_NAMES[part.name] ?? humanised(part.name)}: ${PART_STATES[part.state] ?? part.state.replace(/_/g, " ")}`;
}

/** Whether a part is up, which chooses its tone. A state this console does not know is not. */
export function partIsReady(part: ReadinessPart): boolean {
  return part.state === "ready";
}

/** The health strip's figures the API names, in the words its cards carry. */
export const HEALTH_FIGURES: Readonly<Record<string, string>> = Object.freeze({
  halts: "Halts in force",
  budget_stops: "Budget stops",
});

/** Said when the halts were read and none is in force. */
export const NOTHING_STOPPED = "Nothing stopped";

/** Said when the halts could not be read. Admission refuses everything then, so the page says so. */
export const STOP_STATE_UNKNOWN = "Stop state unknown, treated as stopped";

/** What each scope of halt stops, as the words after "Stopped:". */
function stoppedWhat(halt: Halt): string {
  switch (halt.scope) {
    case "everything":
      return "everything";
    case "department":
      return `department ${halt.target}`;
    case "agent":
      return `agent ${halt.target}`;
    case "connector":
      return `source ${halt.target}`;
    case "person":
      // The target is a principal id, which belongs in Advanced and nowhere else on a page.
      return "one person's work";
    default:
      return halt.target === "" ? humanised(halt.scope).toLocaleLowerCase("en-GB") : `${halt.scope.replace(/_/g, " ")} ${halt.target}`;
  }
}

/** An instant as the strip says it: the time alone when it is today, else the day and the time. */
export function sinceWords(at: string, now: Date = new Date()): string {
  const when = new Date(at);
  if (Number.isNaN(when.getTime())) {
    return at;
  }
  const time = when.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  return when.toDateString() === now.toDateString()
    ? time
    : `${when.toLocaleDateString("en-GB", { day: "numeric", month: "short" })}, ${time}`;
}

/** One halt in plain words: "Stopped: everything since 14:05". */
export function haltWords(halt: Halt, now: Date = new Date()): string {
  return `Stopped: ${stoppedWhat(halt)} since ${sinceWords(halt.since, now)}`;
}

/** Whose requests the figures are over, in words. */
export function basisWords(basis: string): string {
  return basis === "everyone" ? "everyone's requests" : "your requests only";
}

/** How the subject of an audit entry is named in a sentence. Never its identifier. */
const SUBJECT_WORDS: Readonly<Record<string, string>> = Object.freeze({
  principal: "a person",
  grant: "a grant",
  agent: "an agent",
  leash: "an agent's leash",
  entity: "a record",
  artifact: "an artefact",
  connector: "a source",
  session: "a session",
  credential: "a credential",
  retention: "a retention release",
  legal_hold: "a legal hold",
  skill: "a skill",
  setting: "a setting",
  routing: "",
  webhook: "",
  erasure: "an erasure request",
  memory: "a memory",
  department: "a department",
  scope: "a scope",
  breach: "a breach report",
});

/** One audit entry as a sentence: what was done, and to what kind of thing. No names, no ids. */
export function activityWords(row: AuditRow): string {
  const phrase = phraseFor(row.action);
  const subject = SUBJECT_WORDS[row.subject_kind] ?? row.subject_kind.replace(/_/g, " ");
  return capitalised(subject === "" ? phrase : `${phrase} ${subject}`);
}
