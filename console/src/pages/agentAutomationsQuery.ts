/**
 * What the Automations tab asks the API for about this agent's installed automations, and how
 * each answer becomes what the list draws.
 *
 * **Every decision is the API's.** Which automations are listed is
 * `brain.console.agent_automations.automations_for` for this reader, whether a Start or a Stop is
 * offered is whether the API sent that control's confirmation, and whether a change is written is
 * decided again by the route, which recomputes the confirmation and refuses one that does not
 * match. This file drops what is malformed and carries the rest in the order it arrived.
 *
 * **A confirmation is carried and never computed**, for `automationGalleryQuery.ts`' reason: a
 * console that computed its own would be a second description of what the person agreed to.
 *
 * **What a run found arrives only for whom it ran as**, and this file draws whatever lines were
 * sent. It has nothing to decide that with, which is the point.
 *
 * Task ids: M39.6.1.4, M39.6.1.5, M38.2.2.5
 */

export function agentAutomationsApiPath(agentId: string): string {
  return `/agents/${encodeURIComponent(agentId)}/automations`;
}

export function automationStartApiPath(agentId: string, automationId: string): string {
  return `${agentAutomationsApiPath(agentId)}/${encodeURIComponent(automationId)}/start`;
}

export function automationStopApiPath(agentId: string, automationId: string): string {
  return `${agentAutomationsApiPath(agentId)}/${encodeURIComponent(automationId)}/stop`;
}

/** One run, as `RunView` sends it. */
export interface AutomationRunShown {
  readonly finishedAt: string;
  readonly outcome: string;
  readonly reason?: string;
  /** The task's lines, sent only to whom it ran as. */
  readonly result: readonly string[];
}

/** One installed automation, as `AutomationView` sends it. */
export interface InstalledAutomationShown {
  readonly automationId: string;
  readonly name: string;
  readonly runsAs: string;
  readonly runsAsName: string;
  readonly schedule: string;
  readonly nextRunAt?: string;
  readonly pausedBecause?: string;
  readonly lastRun?: AutomationRunShown;
  /** Present when this reader may start it, with the next run a start would leave. */
  readonly start?: { readonly confirmation: string; readonly becomes: string };
  /** Present when this reader may stop it. */
  readonly stopConfirmation?: string;
  /** Why it cannot be started on this install. */
  readonly cannotStart?: string;
}

export interface AgentAutomationsAnswer {
  readonly items: readonly InstalledAutomationShown[];
  /** Who is shown what a run found, in the API's words. */
  readonly resultRule: string;
}

export interface NotChanged {
  readonly outcome: string;
  readonly sentence: string;
}

type Fields = Readonly<Record<string, unknown>>;

function fieldsOf(value: unknown): Fields | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  // A cast at the boundary, where proving a structural match buys nothing: every field is read
  // back through `said` or an array check below, which narrow everything this widens.
  return value as Fields;
}

function said(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

/** A confirmation: the SHA-256 the route computes, and nothing else. */
const DIGEST = /^[0-9a-f]{64}$/;

function confirmation(value: unknown): string | undefined {
  const found = said(value);
  return found !== undefined && DIGEST.test(found) ? found : undefined;
}

function runOf(value: unknown): AutomationRunShown | undefined {
  const fields = fieldsOf(value);
  const finishedAt = said(fields?.["finished_at"]);
  const outcome = said(fields?.["outcome"]);
  const result = fields?.["result"];
  if (
    finishedAt === undefined ||
    outcome === undefined ||
    !Array.isArray(result) ||
    !(result as readonly unknown[]).every((one) => said(one) !== undefined)
  ) {
    return undefined;
  }
  const reason = said(fields?.["reason"]);
  return {
    finishedAt,
    outcome,
    result: result as readonly string[],
    ...(reason === undefined ? {} : { reason }),
  };
}

/**
 * The list out of a response body, or `null` when the body is not one.
 *
 * An automation missing any fact it is drawn from is dropped rather than drawn with a gap, and a
 * second one with an id already read is dropped. A control whose confirmation is not a digest is
 * not offered, because the route would refuse it.
 */
export function readAgentAutomations(payload: unknown): AgentAutomationsAnswer | null {
  const fields = fieldsOf(payload);
  const items = fields?.["items"];
  const resultRule = said(fields?.["result_rule"]);
  if (fields === null || !Array.isArray(items) || resultRule === undefined) {
    return null;
  }
  const seen = new Set<string>();
  const found: InstalledAutomationShown[] = [];
  for (const item of items as readonly unknown[]) {
    const entry = fieldsOf(item);
    const automationId = said(entry?.["automation_id"]);
    const name = said(entry?.["name"]);
    const runsAs = said(entry?.["runs_as"]);
    const runsAsName = said(entry?.["runs_as_name"]);
    const schedule = said(entry?.["schedule"]);
    if (
      automationId === undefined ||
      name === undefined ||
      runsAs === undefined ||
      runsAsName === undefined ||
      schedule === undefined ||
      seen.has(automationId)
    ) {
      continue;
    }
    seen.add(automationId);
    const nextRunAt = said(entry?.["next_run_at"]);
    const pausedBecause = said(entry?.["paused_because"]);
    const lastRun = runOf(entry?.["last_run"]);
    const startConfirmation = confirmation(entry?.["start_confirmation"]);
    const becomes = said(entry?.["start_becomes"]);
    const stopConfirmation = confirmation(entry?.["stop_confirmation"]);
    const cannotStart = said(entry?.["cannot_start"]);
    found.push({
      automationId,
      name,
      runsAs,
      runsAsName,
      schedule,
      ...(nextRunAt === undefined ? {} : { nextRunAt }),
      ...(pausedBecause === undefined ? {} : { pausedBecause }),
      ...(lastRun === undefined ? {} : { lastRun }),
      ...(startConfirmation === undefined || becomes === undefined
        ? {}
        : { start: { confirmation: startConfirmation, becomes } }),
      ...(stopConfirmation === undefined ? {} : { stopConfirmation }),
      ...(cannotStart === undefined ? {} : { cannotStart }),
    });
  }
  return { items: found, resultRule };
}

/** The body a start or a stop sends: the digest the person confirmed, and nothing else. */
export function changeBody(digest: string): { confirmation: string } {
  return { confirmation: digest };
}

export function readNotChanged(payload: unknown): NotChanged | null {
  const fields = fieldsOf(payload);
  const outcome = said(fields?.["outcome"]);
  const sentence = said(fields?.["sentence"]);
  return outcome === undefined || sentence === undefined ? null : { outcome, sentence };
}
