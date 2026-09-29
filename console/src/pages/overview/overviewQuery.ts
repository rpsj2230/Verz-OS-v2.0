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
 * **The week's cost is kept only with the currency it is in.** The route sends `cost_minor` and
 * `currency` together, or neither with a `not_recorded` sentence saying why (spend recording off,
 * or no model priced in the install's currency). A sum with no currency beside it is no figure
 * here, because whole minor units in a currency nobody named read as whichever the reader assumes.
 * `cost_basis` is whose cost it is, which can be narrower than `basis`: money is the Budget
 * screen's to show, and questions the Usage screen's.
 *
 * **A queue the reader may not act on was never sent, so it is never drawn.** The route leaves it
 * out rather than sending it as nought, and this file adds no list of queues to fill the gap: a
 * line reading "Access review 0" to somebody who may not open access review says the queue exists
 * and is being kept from them.
 *
 * **The overview's shape is `brain.console_overview_routes.OverviewView`**, typed here and read
 * field by field, keeping only what was sent. The figures route comes from the generated schema.
 *
 * **Halts in force are drawn from `health.halts`, and an unreadable halt state is said in words.**
 * The route sends the halts this reader may be told of (a halt on everything to everybody, narrower
 * ones through the halt screen's grant) and `halts_known` false when they could not be read, which
 * admission treats as halted. So "none" is drawn only over a state that was read, and never the
 * reason or who declared a halt, which the route does not send.
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
/**
 * The newest changes only (`brain.audit_routes.RECENT_ACTIVITY_IS_CHANGES_AND_NOT_READS`). Until
 * 2026-09-29 the card asked for every entry, and on the owner's install all six read "Answered a
 * call about a credential", the vault's own record of the application reading its keys.
 */
export const ACTIVITY_API_PATH = `/audit?limit=${String(ACTIVITY_ROWS)}&changes_only=true`;

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

/** One halt in force this reader may be told of: what it stops and since when. */
export interface HaltLine {
  readonly scope: string;
  /** What a targeted halt names; empty for a halt on everything. */
  readonly target: string;
  readonly since?: string;
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

/** The overview as this console holds it. */
export interface OverviewAnswer {
  readonly status: string;
  readonly parts: readonly ReadinessPart[];
  readonly workerLastSeen?: string;
  /** The halts in force this reader may be told of, or absent when the route sent none. */
  readonly halts?: readonly HaltLine[];
  /** False when the halts could not be read, which admission treats as halted. */
  readonly haltsKnown: boolean;
  readonly healthNotRecorded: readonly NotRecorded[];
  readonly needsYou: readonly WaitingQueue[];
  readonly uncounted: readonly NotRecorded[];
}

/** The figure row's own answer, from the generated schema. */
export type FiguresBody = components["schemas"]["OverviewFiguresView"];

/** The week's cost as this console holds it: whole minor units, their currency, and whose. */
export interface WeekCost {
  readonly minor: number;
  readonly currency: string;
  readonly basis: string;
}

/** The figure row as this console holds it. */
export interface Figures {
  readonly basis: string;
  readonly answered: number;
  readonly nothingReturned: number;
  /** Absent when the route sent no cost, or a cost without its currency or its basis. */
  readonly cost?: WeekCost;
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
  const seen = text(health["worker_last_seen"]);
  const halts = Array.isArray(health["halts"]) ? readHalts(health["halts"]) : undefined;
  return {
    status,
    parts,
    ...(seen === undefined ? {} : { workerLastSeen: seen }),
    ...(halts === undefined ? {} : { halts }),
    haltsKnown: health["halts_known"] !== false,
    healthNotRecorded: readNotRecorded(health["unrecorded"]),
    needsYou,
    uncounted: readNotRecorded(body["uncounted"]),
  };
}

/** The week's cost out of a response body, or `undefined` unless its sum, currency and basis all came. */
function readWeekCost(body: Fields | null): WeekCost | undefined {
  const minor = count(body?.["cost_minor"]);
  const currency = text(body?.["currency"]);
  const basis = text(body?.["cost_basis"]);
  return minor === undefined || currency === undefined || basis === undefined ? undefined : { minor, currency, basis };
}

/** Each halt line that is one: a scope, a target (empty for everything) and when it began. */
function readHalts(value: readonly unknown[]): HaltLine[] {
  const read: HaltLine[] = [];
  for (const one of value) {
    const line = fieldsOf(one);
    const scope = text(line?.["scope"]);
    const target = line?.["target"];
    if (scope === undefined || typeof target !== "string") {
      continue;
    }
    const since = text(line?.["since"]);
    read.push({ scope, target, ...(since === undefined ? {} : { since }) });
  }
  return read;
}

/** A halt as a person reads it: "Everything" or "Department: finance". */
export function haltWords(halt: HaltLine): string {
  return halt.scope === "everything" || halt.target === "" ? "Everything" : `${humanised(halt.scope)}: ${halt.target}`;
}

/** The halts card's figure: how many are in force, or that nobody can tell. */
export const HALTS_UNKNOWN = "Cannot tell";
export const HALTS_UNKNOWN_SUB = "New work is refused until the halts can be read.";
export const NO_HALTS = "None";

/** The figure row out of a response body, or `null` when a figure is not a count. */
export function readFigures(payload: unknown): Figures | null {
  const body = fieldsOf(payload);
  const basis = text(body?.["basis"]);
  const answered = count(body?.["answered"]);
  const nothingReturned = count(body?.["nothing_returned"]);
  if (basis === undefined || answered === undefined || nothingReturned === undefined) {
    return null;
  }
  const cost = readWeekCost(body);
  return {
    basis,
    answered,
    nothingReturned,
    ...(cost === undefined ? {} : { cost }),
    notRecorded: readNotRecorded(body?.["not_recorded"]),
  };
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

/** Whose requests the figures are over, in words. */
export function basisWords(basis: string): string {
  return basis === "everyone" ? "everyone's requests" : "your requests only";
}

/** A week's cost in its currency, as "SGD 1,284.50": whole minor units as hundredths, grouped. */
export function costWords(cost: WeekCost): string {
  const amount = (cost.minor / 100).toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `${cost.currency} ${amount}`;
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
