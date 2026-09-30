/**
 * What the agent page reads beyond `pages/agentQuery.ts`: the header's dated and stated facts, the
 * Profile block the Settings read is sent, and the About tab's derived flow.
 *
 * **Read as sent, and absent as absent.** Every reader here carries a field only when the body gave
 * it in the shape the route declares, and leaves it out otherwise, so a reader who was not sent the
 * profile gets a page with no Profile cards rather than cards reading "unknown". That is
 * `agentWorkspaceState.ts`' `AN_ABSENT_FIELD_AND_A_WITHHELD_ONE_ARE_ONE_ABSENCE`, kept for the new
 * fields.
 *
 * **The About flow is the API's text.** `brain.console.agent_about` writes every line from the
 * agent's setup and nothing else, and numbers the steps without a gap, so a step the reader may not
 * see is not a hole in the numbering. This file keeps the lines in the order they came and adds no
 * sentence of its own.
 *
 * Task ids: M27.10.2
 */

/** Where one agent's About tab is asked for, under the API base. */
export function agentAboutApiPath(agentId: string): string {
  return `/agents/${encodeURIComponent(agentId)}/about`;
}

type Fields = Readonly<Record<string, unknown>>;

function fieldsOf(value: unknown): Fields | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  // A cast at the boundary, where proving a structural match buys nothing: every field is read
  // back through `said`, `listOf` or an exact comparison below.
  return value as Fields;
}

function said(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

function listOf(value: unknown): readonly unknown[] {
  return Array.isArray(value) ? (value as readonly unknown[]) : [];
}

function words(value: unknown): readonly string[] {
  return listOf(value)
    .map(said)
    .filter((one): one is string => one !== undefined);
}

/** The header's facts beyond who the agent is. Each is absent when it was not sent. */
export interface HeaderFacts {
  /** The steward's display name. Their id is kept for the Advanced section. */
  readonly ownerName?: string;
  readonly createdAt?: string;
  /** `AgentRecord.state`, sent to a reader of the Settings tab and nobody else. */
  readonly state?: string;
  /** The highest rung any action could be held to, sent where the state is. */
  readonly leashUpTo?: string;
}

export function readHeaderFacts(payload: unknown): HeaderFacts {
  const agent = fieldsOf(fieldsOf(payload)?.["agent"]);
  const ownerName = said(agent?.["owner_name"]);
  const created = said(agent?.["created_at"]);
  const createdAt = created !== undefined && !Number.isNaN(Date.parse(created)) ? created : undefined;
  const state = said(agent?.["state"]);
  const leashUpTo = said(agent?.["leash_up_to"]);
  return {
    ...(ownerName === undefined ? {} : { ownerName }),
    ...(createdAt === undefined ? {} : { createdAt }),
    ...(state === undefined ? {} : { state }),
    ...(leashUpTo === undefined ? {} : { leashUpTo }),
  };
}

/** Whether anything records what a run costs. False, or not said, means spend is not recorded. */
export function spendIsRecorded(payload: unknown): boolean {
  return fieldsOf(fieldsOf(payload)?.["headline"])?.["recorded"] === true;
}

/** One tool the ceiling names, as the Profile block sends it. */
export interface ToolShown {
  readonly name: string;
  readonly description?: string;
  readonly sideEffect?: string;
  readonly withinCeiling: boolean;
}

/** One target on the leash and the highest rung it could be held to. */
export interface LeashShown {
  readonly target: string;
  readonly rung: string;
  readonly configured: boolean;
  readonly acts: boolean;
  /** The rung people taking this action over has lowered it to, when it is lower (M8.3.5). */
  readonly loweredTo?: string;
  /** When people took this action over inside the week, oldest first. When, and nothing else. */
  readonly takenOverAt: readonly string[];
}

/** The ceiling in words, as `brain.console.agent_profile.CeilingWords` carries it. */
export interface CeilingShown {
  readonly rows: string;
  readonly reads: readonly string[];
  readonly readsLocked: boolean;
  readonly tools: string;
  readonly largestEffect: string;
  readonly maxSideEffect: string;
}

/** How the agent is set up, for a reader of the Settings tab. */
export interface ProfileShown {
  readonly tier?: string;
  readonly audienceLevel?: string;
  readonly ceiling?: CeilingShown;
  readonly tools: readonly ToolShown[];
  readonly leash: readonly LeashShown[];
}

function readCeiling(value: unknown): CeilingShown | undefined {
  const fields = fieldsOf(value);
  const rows = said(fields?.["rows"]);
  const tools = said(fields?.["tools"]);
  const largestEffect = said(fields?.["largest_effect"]);
  const maxSideEffect = said(fields?.["max_side_effect"]);
  if (fields === null || rows === undefined || tools === undefined || largestEffect === undefined || maxSideEffect === undefined) {
    return undefined;
  }
  return {
    rows,
    reads: words(fields["reads"]),
    readsLocked: fields["reads_locked"] === true,
    tools,
    largestEffect,
    maxSideEffect,
  };
}

/** The Profile block, or null for a reader the workspace sent none. */
export function readProfile(payload: unknown): ProfileShown | null {
  const profile = fieldsOf(fieldsOf(payload)?.["profile"]);
  if (profile === null) {
    return null;
  }
  const tier = said(profile["tier"]);
  const audienceLevel = said(profile["audience_level"]);
  const ceiling = readCeiling(profile["ceiling"]);
  const tools: ToolShown[] = [];
  for (const entry of listOf(profile["tools"])) {
    const fields = fieldsOf(entry);
    const name = said(fields?.["name"]);
    if (fields === null || name === undefined) {
      continue;
    }
    const description = said(fields["description"]);
    const sideEffect = said(fields["side_effect"]);
    tools.push({
      name,
      ...(description === undefined ? {} : { description }),
      ...(sideEffect === undefined ? {} : { sideEffect }),
      withinCeiling: fields["within_ceiling"] === true,
    });
  }
  const leash: LeashShown[] = [];
  for (const entry of listOf(profile["leash"])) {
    const fields = fieldsOf(entry);
    const target = said(fields?.["target"]);
    const rung = said(fields?.["rung"]);
    if (fields === null || target === undefined || rung === undefined) {
      continue;
    }
    const loweredTo = said(fields["lowered_to"]);
    const takenOverAt = listOf(fields["taken_over_at"]).filter(
      (at): at is string => typeof at === "string" && !Number.isNaN(Date.parse(at)),
    );
    leash.push({
      target,
      rung,
      configured: fields["configured"] === true,
      acts: fields["acts"] === true,
      ...(loweredTo === undefined ? {} : { loweredTo }),
      takenOverAt,
    });
  }
  return {
    ...(tier === undefined ? {} : { tier }),
    ...(audienceLevel === undefined ? {} : { audienceLevel }),
    ...(ceiling === undefined ? {} : { ceiling }),
    tools,
    leash,
  };
}

/** One line of a step of the About flow, as the API wrote it. */
export interface FlowLine {
  readonly kind: string;
  readonly text: string;
  /** The tool behind an action line, which is the leash target it links to on the Profile. */
  readonly tool?: string;
  readonly leashEntry?: boolean;
}

export interface FlowStep {
  readonly number: number;
  readonly title: string;
  readonly lines: readonly FlowLine[];
}

export interface AboutShown {
  readonly summary?: string;
  readonly steps: readonly FlowStep[];
  readonly never: readonly { readonly text: string; readonly everyAgent: boolean }[];
}

/** The About tab, or null when the body is not one. */
export function readAbout(payload: unknown): AboutShown | null {
  const fields = fieldsOf(payload);
  if (fields === null || !Array.isArray(fields["steps"])) {
    return null;
  }
  const steps: FlowStep[] = [];
  for (const entry of listOf(fields["steps"])) {
    const step = fieldsOf(entry);
    const title = said(step?.["title"]);
    const number = step?.["number"];
    if (step === null || title === undefined || typeof number !== "number") {
      continue;
    }
    const lines: FlowLine[] = [];
    for (const one of listOf(step["lines"])) {
      const line = fieldsOf(one);
      const text = said(line?.["text"]);
      const kind = said(line?.["kind"]);
      if (line === null || text === undefined || kind === undefined) {
        continue;
      }
      const tool = said(line["tool"]);
      lines.push({
        kind,
        text,
        ...(tool === undefined ? {} : { tool }),
        ...(typeof line["leash_entry"] === "boolean" ? { leashEntry: line["leash_entry"] } : {}),
      });
    }
    steps.push({ number, title, lines });
  }
  const never: { text: string; everyAgent: boolean }[] = [];
  for (const entry of listOf(fields["never"])) {
    const one = fieldsOf(entry);
    const text = said(one?.["text"]);
    if (one !== null && text !== undefined) {
      never.push({ text, everyAgent: one["every_agent"] === true });
    }
  }
  const summary = said(fields["summary"]);
  return { ...(summary === undefined ? {} : { summary }), steps, never };
}

/** The element id of a leash row on the Profile, from its target. A target may hold a dot. */
export function leashRowId(target: string): string {
  return `leash-${target.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
}

/** Whole days between an instant and now, never negative. */
export function daysSince(at: string, now: Date = new Date()): number {
  const days = Math.floor((now.getTime() - Date.parse(at)) / 86_400_000);
  return days < 0 ? 0 : days;
}
