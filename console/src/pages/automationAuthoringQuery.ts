/**
 * What New automation asks the API for, and how each answer becomes what the form draws.
 *
 * **Every decision is the API's.** Whether the button is drawn is `enabled`, what a person may
 * choose is the options the route sent for this agent and this install, whether what they wrote is
 * fit is the route's `422` with every reason in words, and whether it is written is decided again
 * by the route, which recomputes the preview and refuses a confirmation that does not match. This
 * file drops what is malformed and carries the rest in the order it arrived.
 *
 * **The confirmation is carried and never computed**, for `automationGalleryQuery.ts`' reason: a
 * console that computed its own would be a second description of what the person agreed to.
 *
 * Task ids: M39.9.2.1, M39.9.2.2, M39.9.2.3, M39.9.2.4, M17.4.1, M17.4.2
 */

export function authoringOptionsApiPath(agentId: string): string {
  return `/agents/${encodeURIComponent(agentId)}/automation-authoring`;
}

export function authoringPreviewApiPath(agentId: string): string {
  return `${authoringOptionsApiPath(agentId)}/preview`;
}

export function authoringCreateApiPath(agentId: string): string {
  return `/agents/${encodeURIComponent(agentId)}/automations/authored`;
}

export type TriggerKind = "schedule" | "connector_event" | "webhook";
export type Every = "day" | "weekday" | "week";

export const TRIGGER_KINDS: readonly TriggerKind[] = ["schedule", "connector_event", "webhook"];

export interface TemplateOption {
  readonly templateId: string;
  readonly name: string;
  readonly summary: string;
  readonly guards: string;
  readonly every: Every;
  readonly hourUtc: number;
  readonly weekday: number | null;
}

export interface TriggerOption {
  readonly kind: TriggerKind;
  readonly label: string;
  readonly fires: boolean;
}

export interface OpOption {
  readonly op: string;
  readonly label: string;
  readonly inDays: boolean;
}

export interface FieldOption {
  readonly key: string;
  readonly label: string;
  readonly shape: string;
  readonly ops: readonly OpOption[];
}

/** Everything the form is drawn from, or `enabled: false` and nothing else. */
export interface AuthoringOptions {
  readonly enabled: boolean;
  readonly templates: readonly TemplateOption[];
  readonly triggers: readonly TriggerOption[];
  readonly fields: readonly FieldOption[];
  readonly tools: readonly string[];
  readonly connectors: readonly string[];
  readonly startsPaused: string;
  readonly writesWait: string;
}

/** What a person has chosen and written, as the form holds it before it is sent. */
export interface Draft {
  readonly templateId: string;
  readonly name: string;
  readonly instruction: string;
  readonly guards: string;
  readonly kind: TriggerKind;
  readonly every: Every;
  readonly hourUtc: number;
  readonly weekday: number;
  readonly source: string;
  readonly conditionField: string;
  readonly conditionOp: string;
  readonly conditionValue: string;
  readonly tools: readonly string[];
}

export interface RehearsalLine {
  readonly at?: string;
  readonly condition?: string;
  readonly says: string;
}

/** Everything the person confirms, and the digest the write must carry. */
export interface AuthoringPreview {
  readonly name: string;
  readonly instruction: string;
  readonly guards: string;
  readonly trigger: string;
  readonly fires: boolean;
  readonly nothingFires?: string;
  readonly condition?: string;
  readonly tools: readonly string[];
  readonly runsAs: string;
  readonly runsAsName: string;
  readonly reach: readonly string[];
  readonly startsPaused: string;
  readonly writesWait: string;
  readonly rehearsal: readonly RehearsalLine[];
  readonly rehearsalRule: string;
  readonly confirmation: string;
}

export interface Authored {
  readonly automationId: string;
  readonly name: string;
  readonly startsPaused: string;
}

type Fields = Readonly<Record<string, unknown>>;

function fieldsOf(value: unknown): Fields | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  // A cast at the boundary, where proving a structural match buys nothing: every field is read
  // back through `said`, `whole` or an array check below, which narrow everything this widens.
  return value as Fields;
}

function said(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

function whole(value: unknown): number | undefined {
  return typeof value === "number" && Number.isInteger(value) ? value : undefined;
}

function words(value: unknown): string[] | null {
  if (!Array.isArray(value) || !(value as readonly unknown[]).every((one) => said(one) !== undefined)) {
    return null;
  }
  return [...(value as readonly string[])];
}

const DIGEST = /^[0-9a-f]{64}$/;

function kindOf(value: unknown): TriggerKind | undefined {
  return TRIGGER_KINDS.find((one) => one === value);
}

function everyOf(value: unknown): Every | undefined {
  return value === "day" || value === "weekday" || value === "week" ? value : undefined;
}

/**
 * The options out of a response body, or `null` when the body is not one. A switched-off install
 * answers `enabled: false` with nothing else, and that is a valid answer that draws no button.
 */
export function readAuthoringOptions(payload: unknown): AuthoringOptions | null {
  const fields = fieldsOf(payload);
  if (fields === null || typeof fields["enabled"] !== "boolean") {
    return null;
  }
  const startsPaused = said(fields["starts_paused"]);
  const writesWait = said(fields["writes_wait"]);
  if (startsPaused === undefined || writesWait === undefined) {
    return null;
  }
  const templates: TemplateOption[] = [];
  for (const item of Array.isArray(fields["templates"]) ? (fields["templates"] as readonly unknown[]) : []) {
    const entry = fieldsOf(item);
    const templateId = said(entry?.["template_id"]);
    const name = said(entry?.["name"]);
    const summary = said(entry?.["summary"]);
    const guards = said(entry?.["guards"]);
    const every = everyOf(entry?.["every"]);
    const hourUtc = whole(entry?.["hour_utc"]);
    if (templateId === undefined || name === undefined || summary === undefined || guards === undefined || every === undefined || hourUtc === undefined) {
      continue;
    }
    templates.push({ templateId, name, summary, guards, every, hourUtc, weekday: whole(entry?.["weekday"]) ?? null });
  }
  const triggers: TriggerOption[] = [];
  for (const item of Array.isArray(fields["triggers"]) ? (fields["triggers"] as readonly unknown[]) : []) {
    const entry = fieldsOf(item);
    const kind = kindOf(entry?.["kind"]);
    const label = said(entry?.["label"]);
    if (kind === undefined || label === undefined || typeof entry?.["fires"] !== "boolean") {
      continue;
    }
    triggers.push({ kind, label, fires: entry["fires"] });
  }
  const options: FieldOption[] = [];
  for (const item of Array.isArray(fields["fields"]) ? (fields["fields"] as readonly unknown[]) : []) {
    const entry = fieldsOf(item);
    const key = said(entry?.["key"]);
    const label = said(entry?.["label"]);
    const shape = said(entry?.["shape"]);
    if (key === undefined || label === undefined || shape === undefined || !Array.isArray(entry?.["ops"])) {
      continue;
    }
    const ops: OpOption[] = [];
    for (const one of entry["ops"] as readonly unknown[]) {
      const op = fieldsOf(one);
      const name = said(op?.["op"]);
      const opLabel = said(op?.["label"]);
      if (name !== undefined && opLabel !== undefined && typeof op?.["in_days"] === "boolean") {
        ops.push({ op: name, label: opLabel, inDays: op["in_days"] });
      }
    }
    if (ops.length > 0) {
      options.push({ key, label, shape, ops });
    }
  }
  return {
    enabled: fields["enabled"],
    templates,
    triggers,
    fields: options,
    tools: words(fields["tools"]) ?? [],
    connectors: words(fields["connectors"]) ?? [],
    startsPaused,
    writesWait,
  };
}

/** The body a preview or a write sends: what the person chose and wrote, and nothing about who. */
export function draftBody(draft: Draft): Record<string, unknown> {
  const trigger =
    draft.kind === "schedule"
      ? {
          kind: draft.kind,
          cadence: { every: draft.every, hour_utc: draft.hourUtc, ...(draft.every === "week" ? { weekday: draft.weekday } : {}) },
        }
      : { kind: draft.kind, source: draft.source.trim() };
  return {
    ...(draft.templateId === "" ? {} : { template_id: draft.templateId }),
    name: draft.name.trim(),
    instruction: draft.instruction.trim(),
    guards: draft.guards.trim(),
    trigger,
    ...(draft.conditionField === ""
      ? {}
      : { condition: { field: draft.conditionField, op: draft.conditionOp, value: draft.conditionValue.trim() } }),
    tools: [...draft.tools],
  };
}

/** The write's body: the draft and the digest the person confirmed, exactly as sent. */
export function createBody(draft: Draft, preview: AuthoringPreview): Record<string, unknown> {
  return { ...draftBody(draft), confirmation: preview.confirmation };
}

/** A preview out of a response body, or `null` when any fact the person confirms is missing. */
export function readAuthoringPreview(payload: unknown): AuthoringPreview | null {
  const fields = fieldsOf(payload);
  if (fields === null) {
    return null;
  }
  const name = said(fields["name"]);
  const instruction = said(fields["instruction"]);
  const guards = said(fields["guards"]);
  const trigger = said(fields["trigger"]);
  const runsAs = said(fields["runs_as"]);
  const runsAsName = said(fields["runs_as_name"]);
  const startsPaused = said(fields["starts_paused"]);
  const writesWait = said(fields["writes_wait"]);
  const rehearsalRule = said(fields["rehearsal_rule"]);
  const confirmation = said(fields["confirmation"]);
  const tools = words(fields["tools"]);
  const reach = words(fields["reach"]);
  if (
    name === undefined ||
    instruction === undefined ||
    guards === undefined ||
    trigger === undefined ||
    runsAs === undefined ||
    runsAsName === undefined ||
    startsPaused === undefined ||
    writesWait === undefined ||
    rehearsalRule === undefined ||
    confirmation === undefined ||
    !DIGEST.test(confirmation) ||
    tools === null ||
    reach === null ||
    typeof fields["fires"] !== "boolean" ||
    !Array.isArray(fields["rehearsal"])
  ) {
    return null;
  }
  const rehearsal: RehearsalLine[] = [];
  for (const item of fields["rehearsal"] as readonly unknown[]) {
    const entry = fieldsOf(item);
    const says = said(entry?.["says"]);
    if (says === undefined) {
      return null;
    }
    const at = said(entry?.["at"]);
    const condition = said(entry?.["condition"]);
    rehearsal.push({ says, ...(at === undefined ? {} : { at }), ...(condition === undefined ? {} : { condition }) });
  }
  const nothingFires = said(fields["nothing_fires"]);
  const condition = said(fields["condition"]);
  return {
    name,
    instruction,
    guards,
    trigger,
    fires: fields["fires"],
    tools,
    runsAs,
    runsAsName,
    reach,
    startsPaused,
    writesWait,
    rehearsal,
    rehearsalRule,
    confirmation,
    ...(nothingFires === undefined ? {} : { nothingFires }),
    ...(condition === undefined ? {} : { condition }),
  };
}

export function readAuthored(payload: unknown): Authored | null {
  const fields = fieldsOf(payload);
  const automationId = said(fields?.["automation_id"]);
  const name = said(fields?.["name"]);
  const startsPaused = said(fields?.["starts_paused"]);
  return automationId === undefined || name === undefined || startsPaused === undefined ? null : { automationId, name, startsPaused };
}

/** Every reason what was written cannot be an automation, in the API's words. */
export function readRefusal(payload: unknown): readonly string[] | null {
  const fields = fieldsOf(payload);
  if (fields === null || fields["outcome"] !== "refused") {
    return null;
  }
  const sentences = words(fields["sentences"]);
  return sentences === null || sentences.length === 0 ? null : sentences;
}

/** Why a confirmation was not written, when the API said so with a 409. */
export function readNotWritten(payload: unknown): string | null {
  const fields = fieldsOf(payload);
  return fields?.["outcome"] === "unconfirmed" ? (said(fields["sentence"]) ?? null) : null;
}

/** A draft that starts from a template, or from words when `template` is undefined. */
export function startDraft(template: TemplateOption | undefined): Draft {
  return {
    templateId: template?.templateId ?? "",
    name: template?.name ?? "I ",
    instruction: template?.summary ?? "",
    guards: template?.guards ?? "",
    kind: "schedule",
    every: template?.every ?? "weekday",
    hourUtc: template?.hourUtc ?? 9,
    weekday: template?.weekday ?? 0,
    source: "",
    conditionField: "",
    conditionOp: "",
    conditionValue: "",
    tools: [],
  };
}
