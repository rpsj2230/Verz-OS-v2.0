/**
 * One agent's leash as `brain.agent_leash_routes` sends it, and the addresses of its four writes.
 * No React.
 *
 * **Read as sent, and absent as absent.** An entry missing its target or rung is left out, a move
 * missing its kind or rungs is left out, and a supervision block the API did not send stays
 * undefined: an agent nobody pinned is not an agent with a pin of nothing. Nothing here decides
 * who may move a rung; `mayMove` and `mayJudge` are the route's own answers.
 *
 * Task ids: M39.3.2.1, M39.3.2.2, M39.3.2.3, M39.3.2.4, M39.3.2.5, M39.8.2
 */

export function agentLeashApiPath(agentId: string): string {
  return `/agents/${encodeURIComponent(agentId)}/leash`;
}

export function leashMoveApiPath(agentId: string): string {
  return `${agentLeashApiPath(agentId)}/moves`;
}

export function supervisionApiPath(agentId: string, act: "pin" | "review" | "verdicts"): string {
  return `/agents/${encodeURIComponent(agentId)}/supervision/${act}`;
}

export interface LeashScope {
  readonly clauses: readonly unknown[];
}

export interface LeashEntryShown {
  readonly target: string;
  readonly scope: LeashScope;
  readonly where: string;
  readonly rung: string;
  /** The rung a proposal waiting for a second person would raise it to. */
  readonly proposed?: string;
}

export interface LeashMoveShown {
  readonly target: string;
  readonly where: string;
  readonly kind: string;
  readonly was: string;
  readonly became: string;
  readonly at: string;
  readonly approver: string;
  readonly secondApprover: string;
  readonly cleanRuns?: number;
  readonly agreementRate?: number;
  readonly metric: string;
  readonly measured?: number;
  readonly threshold?: number;
}

export interface SupervisionShown {
  readonly pinnedAt: string;
  readonly reviewDueAt: string;
  readonly outcome: string;
  readonly understood?: number;
  readonly reviewed?: number;
  readonly held: boolean;
  readonly due: boolean;
}

export interface AwaitingShown {
  readonly actionDigest: string;
  readonly target: string;
  readonly route: string;
  readonly at: string;
}

export interface AgentLeash {
  readonly entries: readonly LeashEntryShown[];
  readonly history: readonly LeashMoveShown[];
  readonly supervision?: SupervisionShown;
  readonly awaiting: readonly AwaitingShown[];
  readonly mayMove: boolean;
  readonly mayJudge: boolean;
}

type Fields = Readonly<Record<string, unknown>>;

function fieldsOf(value: unknown): Fields | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  // A cast at the boundary, where proving a structural match buys nothing: every field is read
  // back through `said`, `numberOf` or a type test below.
  return value as Fields;
}

function said(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

function numberOf(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function each<T>(value: unknown, read: (one: Fields) => T | null): T[] {
  return (Array.isArray(value) ? (value as readonly unknown[]) : [])
    .map(fieldsOf)
    .map((one) => (one === null ? null : read(one)))
    .filter((one): one is T => one !== null);
}

function optional<K extends string, V>(key: K, value: V | undefined): Partial<Record<K, V>> {
  return value === undefined ? {} : ({ [key]: value } as Record<K, V>);
}

/** The leash block out of a body, or null when the body is not an object at all. */
export function readAgentLeash(payload: unknown): AgentLeash | null {
  const fields = fieldsOf(payload);
  if (fields === null) {
    return null;
  }
  const supervision = fieldsOf(fields["supervision"]);
  const pinnedAt = supervision === null ? undefined : said(supervision["pinned_at"]);
  const reviewDueAt = supervision === null ? undefined : said(supervision["review_due_at"]);
  const outcome = supervision === null ? undefined : said(supervision["outcome"]);
  return {
    entries: each(fields["entries"], (one) => {
      const target = said(one["target"]);
      const rung = said(one["rung"]);
      const scope = fieldsOf(one["scope"]);
      if (target === undefined || rung === undefined || scope === null) {
        return null;
      }
      return {
        target,
        rung,
        scope: { clauses: Array.isArray(scope["clauses"]) ? (scope["clauses"] as readonly unknown[]) : [] },
        where: said(one["where"]) ?? "",
        ...optional("proposed", said(one["proposed"])),
      };
    }),
    history: each(fields["history"], (one) => {
      const target = said(one["target"]);
      const kind = said(one["kind"]);
      const was = said(one["was"]);
      const became = said(one["became"]);
      const at = said(one["at"]);
      if (target === undefined || kind === undefined || was === undefined || became === undefined || at === undefined) {
        return null;
      }
      return {
        target,
        kind,
        was,
        became,
        at,
        where: said(one["where"]) ?? "",
        approver: said(one["approver"]) ?? "",
        secondApprover: said(one["second_approver"]) ?? "",
        metric: said(one["metric"]) ?? "",
        ...optional("cleanRuns", numberOf(one["clean_runs"])),
        ...optional("agreementRate", numberOf(one["agreement_rate"])),
        ...optional("measured", numberOf(one["measured"])),
        ...optional("threshold", numberOf(one["threshold"])),
      };
    }),
    ...(supervision === null || pinnedAt === undefined || reviewDueAt === undefined || outcome === undefined
      ? {}
      : {
          supervision: {
            pinnedAt,
            reviewDueAt,
            outcome,
            held: supervision["held"] === true,
            due: supervision["due"] === true,
            ...optional("understood", numberOf(supervision["understood"])),
            ...optional("reviewed", numberOf(supervision["reviewed"])),
          },
        }),
    awaiting: each(fields["awaiting"], (one) => {
      const actionDigest = said(one["action_digest"]);
      const target = said(one["target"]);
      const at = said(one["at"]);
      return actionDigest === undefined || target === undefined || at === undefined
        ? null
        : { actionDigest, target, at, route: said(one["route"]) ?? "" };
    }),
    mayMove: fields["may_move"] === true,
    mayJudge: fields["may_judge"] === true,
  };
}

/** How each move reads in the history. */
export const MOVE_WORDS: Readonly<Record<string, string>> = Object.freeze({
  lowered: "Lowered",
  proposed: "Proposed, waiting for a second person",
  raised: "Raised on its record",
  tripped: "Tripped by its breaker",
});

/** What a person says of one action, as the ledger's verdicts read. */
export const VERDICT_WORDS: Readonly<Record<string, string>> = Object.freeze({
  approved: "I would have done exactly that",
  amended: "I would have changed it",
  taken_over: "I would have done it myself",
  rejected: "It should not have happened",
});

/** Where a supervision review stands, in words. */
export const PIN_WORDS: Readonly<Record<string, string>> = Object.freeze({
  pinned: "Under supervision",
  extended: "Under supervision, extended at its last review",
  eligible: "Found ready at its last review",
});

/** A share as a whole percentage. */
export function percent(share: number): string {
  return `${String(Math.round(share * 100))}%`;
}
