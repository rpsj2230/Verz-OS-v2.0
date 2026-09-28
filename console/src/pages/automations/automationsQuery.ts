/**
 * The Automations module's addresses and the readers of what the API sends for them.
 *
 * **Four reads and five writes, all served by `brain.automations_routes`.** The list is
 * `GET /api/v1/console/automations` on the list contract; one automation is
 * `GET /api/v1/console/automations/{id}`, its figures `.../stats`; and the five changes are
 * `POST /api/v1/automations/{id}/{pause|resume|reschedule|remove|adopt}`, each carrying the
 * confirmation the page was sent.
 *
 * **A reader keeps only the fields that were sent, in the shape they should have.** A missing or
 * malformed field is absent here, and the page draws nothing for it rather than a zero or an empty
 * string it made up. A figure the API did not send is "Not recorded yet" (`kit/KpiStrip.tsx`).
 *
 * Task ids: M27.12.3, M27.15.37, M27.16.1
 */

/** Where the module lives in the console. */
export const AUTOMATIONS_ADDRESS = "/automations";

/** The list route, under the API base. */
export const AUTOMATIONS_API_PATH = "/console/automations";

/** The five changes, as the route spells them. */
export const CHANGES = ["pause", "resume", "reschedule", "remove", "adopt"] as const;
export type ChangeAct = (typeof CHANGES)[number];

export function automationAddress(id: string): string {
  return `${AUTOMATIONS_ADDRESS}/${encodeURIComponent(id)}`;
}

export function automationApiPath(id: string): string {
  return `${AUTOMATIONS_API_PATH}/${encodeURIComponent(id)}`;
}

export function automationStatsApiPath(id: string): string {
  return `${automationApiPath(id)}/stats`;
}

export function changeApiPath(id: string, act: ChangeAct): string {
  return `/automations/${encodeURIComponent(id)}/${act}`;
}

/** The four states, as the API spells them, and how each reads. */
export const STATE_WORDS: Readonly<Record<string, string>> = Object.freeze({
  running: "Running",
  paused: "Paused",
  ownerless: "Ownerless",
  removed: "Removed",
});

export function stateWords(state: string): string {
  return STATE_WORDS[state] ?? state;
}

/** How a run ended, as the API spells it, and how each reads. */
export const OUTCOME_WORDS: Readonly<Record<string, string>> = Object.freeze({
  succeeded: "Succeeded",
  failed: "Failed",
  refused: "Refused",
});

export function outcomeWords(outcome: string): string {
  return OUTCOME_WORDS[outcome] ?? outcome;
}

/** How a run's reach compares with the run before it. `brain.automations_routes.REACH_*`. */
export const REACH_WORDS: Readonly<Record<string, string>> = Object.freeze({
  first: "First run read here",
  same: "Same as the run before",
  changed: "Changed since the run before",
  none: "Not resolved: the run was refused first",
});

/** An instant as a date and a time, in the reader's own time zone. */
export function dateWords(at: string | undefined): string | undefined {
  if (at === undefined) {
    return undefined;
  }
  return new Date(at).toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// ------------------------------------------------------------------------------ reading

type Fields = Readonly<Record<string, unknown>>;

function fieldsOf(value: unknown): Fields | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  // A cast at the boundary, where proving a structural match buys nothing: every field is read
  // back through one of the typed readers below.
  return value as Fields;
}

function said(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

function instant(value: unknown): string | undefined {
  const text = said(value);
  return text !== undefined && !Number.isNaN(Date.parse(text)) ? text : undefined;
}

function counted(value: unknown): number | undefined {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : undefined;
}

function listOf(value: unknown): readonly unknown[] {
  return Array.isArray(value) ? (value as readonly unknown[]) : [];
}

function strings(value: unknown): string[] {
  return listOf(value).filter((one): one is string => typeof one === "string");
}

/** One automation on the list. */
export interface AutomationRow {
  readonly id: string;
  readonly name: string;
  readonly agentId: string;
  readonly agentName: string;
  readonly ownerName: string;
  /** The schedule in words, or absent when nothing says when it runs. */
  readonly schedule?: string;
  readonly state: string;
  readonly nextRunAt?: string;
  readonly lastRunAt?: string;
  readonly lastOutcome?: string;
}

export function readAutomationRow(value: unknown): AutomationRow | null {
  const fields = fieldsOf(value);
  const id = said(fields?.["automation_id"]);
  const name = said(fields?.["name"]);
  const agentId = said(fields?.["agent_id"]);
  const state = said(fields?.["state"]);
  if (fields === null || id === undefined || name === undefined || agentId === undefined || state === undefined) {
    return null;
  }
  const schedule = said(fields["schedule"]);
  const nextRunAt = instant(fields["next_run_at"]);
  const lastRunAt = instant(fields["last_run_at"]);
  const lastOutcome = said(fields["last_outcome"]);
  return {
    id,
    name,
    agentId,
    agentName: said(fields["agent_name"]) ?? agentId,
    ownerName: said(fields["owner_name"]) ?? "",
    state,
    ...(schedule === undefined ? {} : { schedule }),
    ...(nextRunAt === undefined ? {} : { nextRunAt }),
    ...(lastRunAt === undefined ? {} : { lastRunAt }),
    ...(lastOutcome === undefined ? {} : { lastOutcome }),
  };
}

/** The rows out of a list body, keeping every one that reads and passing over any that does not. */
export function readAutomationRows(body: unknown): AutomationRow[] {
  return listOf(fieldsOf(body)?.["items"])
    .map(readAutomationRow)
    .filter((one): one is AutomationRow => one !== null);
}

/** A cadence as its three fields. */
export interface CadenceFields {
  readonly every: string;
  readonly hourUtc: number;
  readonly weekday?: number;
}

/** One run on the automation's page. */
export interface AutomationRun {
  readonly finishedAt: string;
  readonly outcome: string;
  readonly reason?: string;
  readonly ranAsName: string;
  readonly reach: string;
  /** What it found, only for whom it ran as. */
  readonly result: readonly string[];
}

export interface HistoryEntry {
  readonly at: string;
  readonly what: string;
  readonly byName: string;
}

/** One automation for its own page. */
export interface AutomationDetail {
  readonly row: AutomationRow;
  readonly guards: string;
  readonly stoppedBecause?: string;
  readonly cannotRun?: string;
  readonly cadence?: CadenceFields;
  readonly installedByName: string;
  readonly installedAt?: string;
  readonly runs: readonly AutomationRun[];
  /** Whose runs are shown: "own" or "everyone". */
  readonly basis?: string;
  readonly history: readonly HistoryEntry[];
  readonly confirmation: string;
  readonly may: Readonly<Record<ChangeAct, boolean>>;
  readonly resumeBecomes?: string;
  readonly scheduleAccepts: string;
  readonly weekdays: readonly string[];
  readonly confirm: Readonly<Record<ChangeAct, string>>;
  readonly task: string;
  readonly templateId: string;
  readonly ownerId: string;
}

function readRun(value: unknown): AutomationRun | null {
  const fields = fieldsOf(value);
  const finishedAt = instant(fields?.["finished_at"]);
  const outcome = said(fields?.["outcome"]);
  if (fields === null || finishedAt === undefined || outcome === undefined) {
    return null;
  }
  const reason = said(fields["reason"]);
  return {
    finishedAt,
    outcome,
    ranAsName: said(fields["ran_as_name"]) ?? "",
    reach: said(fields["reach"]) ?? "",
    result: strings(fields["result"]),
    ...(reason === undefined ? {} : { reason }),
  };
}

function readHistory(value: unknown): HistoryEntry | null {
  const fields = fieldsOf(value);
  const at = instant(fields?.["at"]);
  const what = said(fields?.["what"]);
  if (fields === null || at === undefined || what === undefined) {
    return null;
  }
  return { at, what, byName: said(fields["by_name"]) ?? "" };
}

function readCadence(value: unknown): CadenceFields | undefined {
  const fields = fieldsOf(value);
  const every = said(fields?.["every"]);
  const hourUtc = counted(fields?.["hour_utc"]);
  if (fields === null || every === undefined || hourUtc === undefined) {
    return undefined;
  }
  const weekday = counted(fields["weekday"]);
  return { every, hourUtc, ...(weekday === undefined ? {} : { weekday }) };
}

export function readAutomationDetail(payload: unknown): AutomationDetail | null {
  const fields = fieldsOf(payload);
  const row = readAutomationRow(fields?.["automation"]);
  const confirmation = said(fields?.["confirmation"]);
  if (fields === null || row === null || confirmation === undefined) {
    return null;
  }
  const flag = (name: string): boolean => fields[name] === true;
  const stoppedBecause = said(fields["stopped_because"]);
  const cannotRun = said(fields["cannot_run"]);
  const cadence = readCadence(fields["cadence"]);
  const installedAt = instant(fields["installed_at"]);
  const resumeBecomes = instant(fields["resume_becomes"]);
  const basis = said(fields["basis"]);
  return {
    row,
    guards: said(fields["guards"]) ?? "",
    installedByName: said(fields["installed_by_name"]) ?? "",
    runs: listOf(fields["runs"])
      .map(readRun)
      .filter((one): one is AutomationRun => one !== null),
    history: listOf(fields["history"])
      .map(readHistory)
      .filter((one): one is HistoryEntry => one !== null),
    confirmation,
    may: {
      pause: flag("may_pause"),
      resume: flag("may_resume"),
      reschedule: flag("may_reschedule"),
      remove: flag("may_remove"),
      adopt: flag("may_adopt"),
    },
    scheduleAccepts: said(fields["schedule_accepts"]) ?? "",
    weekdays: strings(fields["weekdays"]),
    confirm: {
      pause: said(fields["confirm_pause"]) ?? "",
      resume: said(fields["confirm_resume"]) ?? "",
      reschedule: said(fields["confirm_reschedule"]) ?? "",
      remove: said(fields["confirm_remove"]) ?? "",
      adopt: said(fields["confirm_adopt"]) ?? "",
    },
    task: said(fields["task"]) ?? "",
    templateId: said(fields["template_id"]) ?? "",
    ownerId: said(fields["owner_id"]) ?? "",
    ...(stoppedBecause === undefined ? {} : { stoppedBecause }),
    ...(cannotRun === undefined ? {} : { cannotRun }),
    ...(cadence === undefined ? {} : { cadence }),
    ...(installedAt === undefined ? {} : { installedAt }),
    ...(resumeBecomes === undefined ? {} : { resumeBecomes }),
    ...(basis === undefined ? {} : { basis }),
  };
}

/** One period's runs by how they ended. A count absent from the body is absent here. */
export interface AutomationPeriod {
  readonly range: string;
  readonly runs?: number;
  readonly succeeded?: number;
  readonly failed?: number;
  readonly refused?: number;
}

export interface AutomationStats {
  readonly basis?: string;
  readonly periods: readonly AutomationPeriod[];
  /** Why each figure nothing records is not recorded, by figure. */
  readonly unrecorded: Readonly<Record<string, string>>;
}

/** The figure `unrecorded` names a run's cost by. `brain.automations_routes`. */
export const COST_FIGURE = "run_cost";

export function readAutomationStats(payload: unknown): AutomationStats | null {
  const fields = fieldsOf(payload);
  if (fields === null) {
    return null;
  }
  const periods: AutomationPeriod[] = [];
  for (const one of listOf(fields["periods"])) {
    const period = fieldsOf(one);
    const range = said(period?.["range"]);
    if (period === null || range === undefined) {
      continue;
    }
    const runs = counted(period["runs"]);
    const succeeded = counted(period["succeeded"]);
    const failed = counted(period["failed"]);
    const refused = counted(period["refused"]);
    periods.push({
      range,
      ...(runs === undefined ? {} : { runs }),
      ...(succeeded === undefined ? {} : { succeeded }),
      ...(failed === undefined ? {} : { failed }),
      ...(refused === undefined ? {} : { refused }),
    });
  }
  const unrecorded: Record<string, string> = {};
  for (const one of listOf(fields["unrecorded"])) {
    const entry = fieldsOf(one);
    const figure = said(entry?.["figure"]);
    const why = said(entry?.["why"]);
    if (figure !== undefined && why !== undefined) {
      unrecorded[figure] = why;
    }
  }
  const basis = said(fields["basis"]);
  return {
    periods,
    unrecorded,
    ...(basis === undefined ? {} : { basis }),
  };
}
