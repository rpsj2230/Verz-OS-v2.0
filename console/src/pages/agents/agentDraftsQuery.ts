/**
 * What the New agent, drafts and draft pages ask the API and send it, and the words they say. No
 * React.
 *
 * `brain.agent_builder_routes` serves the builder, and this file names the same addresses. **Nothing
 * here decides what a draft may become.** Whether a publish goes out on its author's word or waits for
 * a second person, who that person may be, and whether a draft passes its check are the API's to say,
 * and each reader here keeps only the fields that were sent: a field missing from an answer is absent
 * on the page, never guessed.
 *
 * **Every sentence a person confirms is written here once**, so the page, its tests and the console
 * audit read the same words. A refusal is never one of them: it is the API's own sentence, read by
 * `readNotChanged`.
 *
 * Task ids: M27.11.6, M27.15.31
 */

export { readNotChanged } from "../agentAutomationsQuery";

// ------------------------------------------------------------------------ the addresses
/** `brain.agent_builder_routes.FORM_PATH`. */
export const BUILDER_FORM_API_PATH = "/builder/form";
/** `DRAFTS_PATH`: this reader's drafts, and a new agent's draft started. */
export const DRAFTS_API_PATH = "/agent-drafts";
/** The gallery a draft may start from, `brain.agent_routes`. */
export const TEMPLATES_API_PATH = "/agent-templates";

function underDraft(draftId: string, verb?: string): string {
  const base = `${DRAFTS_API_PATH}/${encodeURIComponent(draftId)}`;
  return verb === undefined ? base : `${base}/${verb}`;
}

/** `DRAFT_PATH`. */
export function draftApiPath(draftId: string): string {
  return underDraft(draftId);
}

/** The acts on one draft, by verb: `SAVE_PATH` and the rest. */
export type DraftVerb = "revisions" | "check" | "rehearse" | "procedure" | "publish" | "approve" | "decline";

export function draftActApiPath(draftId: string, verb: DraftVerb): string {
  return underDraft(draftId, verb);
}

/** `EDIT_PATH`: a draft of an agent as it is now. */
export function editAsDraftApiPath(agentId: string): string {
  return `/agents/${encodeURIComponent(agentId)}/drafts`;
}

// ------------------------------------------------------------------------ console addresses
export const NEW_AGENT_ADDRESS = "/agents/new";
export const DRAFTS_ADDRESS = "/agents/drafts";

/** The steps of a draft's page, in the order a person works through them. */
export const STEPS = ["write", "procedure", "check", "publish"] as const;
export type DraftStep = (typeof STEPS)[number];

export const STEP_LABELS: Readonly<Record<DraftStep, string>> = Object.freeze({
  write: "1 Write",
  procedure: "2 Procedure",
  check: "3 Check and rehearse",
  publish: "4 Publish",
});

/** Where one step of a draft is. The first step is the bare address. */
export function draftAddress(draftId: string, step: DraftStep = STEPS[0]): string {
  const base = `${DRAFTS_ADDRESS}/${encodeURIComponent(draftId)}`;
  return step === STEPS[0] ? base : `${base}/${step}`;
}

/** Which step an address opens. Anything else opens the first, silently. */
export function stepFor(step: string | undefined): DraftStep {
  return (STEPS as readonly string[]).includes(step ?? "") ? (step as DraftStep) : STEPS[0];
}

// ------------------------------------------------------------------------ reading answers
type Fields = Readonly<Record<string, unknown>>;

function fieldsOf(payload: unknown): Fields | null {
  return typeof payload === "object" && payload !== null && !Array.isArray(payload) ? (payload as Fields) : null;
}

function said(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

function words(value: unknown): readonly string[] {
  return Array.isArray(value) ? value.filter((one): one is string => typeof one === "string" && one.trim() !== "") : [];
}

function whole(value: unknown): number | undefined {
  return typeof value === "number" && Number.isInteger(value) ? value : undefined;
}

/** One draft on the drafts list: `AgentDraftSummary`. */
export interface DraftSummary {
  readonly draftId: string;
  readonly agentId: string;
  readonly name: string;
  readonly kind: string;
  readonly state: string;
  readonly revision: number;
  readonly savedAt?: string;
}

function summaryOf(value: unknown): DraftSummary | null {
  const fields = fieldsOf(value);
  const draftId = said(fields?.["draft_id"]);
  const agentId = said(fields?.["agent_id"]);
  const name = said(fields?.["name"]);
  const kind = said(fields?.["kind"]);
  const state = said(fields?.["state"]);
  const revision = whole(fields?.["revision"]);
  if (!fields || !draftId || !agentId || !name || !kind || !state || revision === undefined) {
    return null;
  }
  const savedAt = said(fields["saved_at"]);
  return { draftId, agentId, name, kind, state, revision, ...(savedAt === undefined ? {} : { savedAt }) };
}

function summaries(value: unknown): readonly DraftSummary[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const seen = new Set<string>();
  const kept: DraftSummary[] = [];
  for (const one of value) {
    const read = summaryOf(one);
    if (read !== null && !seen.has(read.draftId)) {
      seen.add(read.draftId);
      kept.push(read);
    }
  }
  return kept;
}

/** `AgentDraftsPage`: the reader's own drafts and the publishes waiting for them. */
export interface DraftsPage {
  readonly items: readonly DraftSummary[];
  readonly waitingForYou: readonly DraftSummary[];
}

export function readDrafts(payload: unknown): DraftsPage {
  const fields = fieldsOf(payload);
  return { items: summaries(fields?.["items"]), waitingForYou: summaries(fields?.["waiting_for_you"]) };
}

/** One act on one revision: `DraftActView`. */
export interface DraftActDone {
  readonly revision: number;
  readonly act: string;
  readonly at: string;
}

/** One draft: `AgentDraftView`. */
export interface Draft {
  readonly draftId: string;
  readonly agentId: string;
  readonly name: string;
  readonly kind: string;
  readonly state: string;
  readonly revision: number;
  readonly document: Record<string, unknown>;
  readonly problems: readonly string[];
  readonly savedAt?: string;
  readonly acts: readonly DraftActDone[];
  readonly yours: boolean;
  readonly waitingOnYou: boolean;
  readonly widened: readonly string[];
  readonly drawableTools: readonly string[];
  readonly publishUnavailable?: string;
}

export function readDraft(payload: unknown): Draft | null {
  const fields = fieldsOf(payload);
  const summary = summaryOf(payload);
  const document = fieldsOf(fields?.["document"]);
  if (!fields || summary === null || document === null) {
    return null;
  }
  const acts: DraftActDone[] = [];
  for (const one of Array.isArray(fields["acts"]) ? fields["acts"] : []) {
    const act = fieldsOf(one);
    const revision = whole(act?.["revision"]);
    const word = said(act?.["act"]);
    const at = said(act?.["at"]);
    if (revision !== undefined && word !== undefined && at !== undefined) {
      acts.push({ revision, act: word, at });
    }
  }
  const publishUnavailable = said(fields["publish_unavailable"]);
  return {
    ...summary,
    // A copy the page may edit: the answer itself is never changed.
    document: JSON.parse(JSON.stringify(document)) as Record<string, unknown>,
    problems: words(fields["problems"]),
    acts,
    yours: fields["yours"] === true,
    waitingOnYou: fields["waiting_on_you"] === true,
    widened: words(fields["widened"]),
    drawableTools: words(fields["drawable_tools"]),
    ...(publishUnavailable === undefined ? {} : { publishUnavailable }),
  };
}

/** One shaped literal the leak scan found: `CompanyDetailView`. */
export interface CompanyDetail {
  readonly kind: string;
  readonly text: string;
  readonly places: readonly string[];
}

/** A check of one revision: `DraftCheckView`. */
export interface DraftCheck {
  readonly revision: number;
  readonly passed: boolean;
  readonly problems: readonly string[];
  readonly missing: readonly string[];
  readonly companyDetails: readonly CompanyDetail[];
  readonly widened: readonly string[];
  readonly secondPersonNeeded: boolean;
  readonly publishUnavailable?: string;
}

export function readCheck(payload: unknown): DraftCheck | null {
  const fields = fieldsOf(payload);
  const revision = whole(fields?.["revision"]);
  if (!fields || revision === undefined || typeof fields["passed"] !== "boolean") {
    return null;
  }
  const details: CompanyDetail[] = [];
  for (const one of Array.isArray(fields["company_details"]) ? fields["company_details"] : []) {
    const detail = fieldsOf(one);
    const kind = said(detail?.["kind"]);
    const text = said(detail?.["text"]);
    if (kind !== undefined && text !== undefined) {
      details.push({ kind, text, places: words(detail?.["places"]) });
    }
  }
  const publishUnavailable = said(fields["publish_unavailable"]);
  return {
    revision,
    passed: fields["passed"],
    problems: words(fields["problems"]),
    missing: words(fields["missing"]),
    companyDetails: details,
    widened: words(fields["widened"]),
    secondPersonNeeded: fields["second_person_needed"] === true,
    ...(publishUnavailable === undefined ? {} : { publishUnavailable }),
  };
}

/** A rehearsal for the person asking: `DraftRehearsalView`. It carries no row, so none is read. */
export interface DraftRehearsal {
  readonly startsForYou: boolean;
  readonly reachesForYou: readonly string[];
  readonly rung: string;
  readonly questions: readonly string[];
  readonly notDone: string;
}

export function readRehearsal(payload: unknown): DraftRehearsal | null {
  const fields = fieldsOf(payload);
  const rung = said(fields?.["rung"]);
  const notDone = said(fields?.["not_done"]);
  if (!fields || rung === undefined || notDone === undefined || typeof fields["starts_for_you"] !== "boolean") {
    return null;
  }
  return {
    startsForYou: fields["starts_for_you"],
    reachesForYou: words(fields["reaches_for_you"]),
    rung,
    questions: words(fields["questions"]),
    notDone,
  };
}

/** What a publish did: `DraftPublishView`. */
export interface DraftPublished {
  readonly state: string;
  readonly agentId: string;
  readonly sentence: string;
  readonly widened: readonly string[];
}

export function readPublished(payload: unknown): DraftPublished | null {
  const fields = fieldsOf(payload);
  const state = said(fields?.["state"]);
  const agentId = said(fields?.["agent_id"]);
  const sentence = said(fields?.["sentence"]);
  if (!fields || state === undefined || agentId === undefined || sentence === undefined) {
    return null;
  }
  return { state, agentId, sentence, widened: words(fields["widened"]) };
}

/** The draft an answer started or opened, by id, or null. */
export function startedDraftId(payload: unknown): string | null {
  return said(fieldsOf(payload)?.["draft_id"]) ?? null;
}

/** One template the gallery offers, by the fields a draft needs to start from it. */
export interface TemplateChoice {
  readonly templateId: string;
  readonly name: string;
  readonly summary?: string;
}

export function readTemplates(payload: unknown): readonly TemplateChoice[] {
  const items = fieldsOf(payload)?.["items"];
  if (!Array.isArray(items)) {
    return [];
  }
  const seen = new Set<string>();
  const kept: TemplateChoice[] = [];
  for (const one of items) {
    const fields = fieldsOf(one);
    const templateId = said(fields?.["template_id"]);
    const name = said(fields?.["display_name"]);
    if (templateId === undefined || name === undefined || seen.has(templateId)) {
      continue;
    }
    seen.add(templateId);
    const summary = said(fields?.["summary"]);
    kept.push({ templateId, name, ...(summary === undefined ? {} : { summary }) });
  }
  return kept;
}

// ------------------------------------------------------------------------ the document
/**
 * The draft with one section's submission put into it, which is what a save sends.
 *
 * A section declares part of an object another section also declares, `authority` today, so an
 * object a section submits is merged over the draft's rather than replacing it; anything else is
 * replaced. The section's schema decided what it could submit, so nothing here names a field.
 */
export function withSection(document: Readonly<Record<string, unknown>>, submitted: unknown): Record<string, unknown> {
  const next: Record<string, unknown> = { ...document };
  const part = fieldsOf(submitted);
  if (part === null) {
    return next;
  }
  for (const [name, value] of Object.entries(part)) {
    const held = fieldsOf(next[name]);
    const given = fieldsOf(value);
    next[name] = held !== null && given !== null ? { ...held, ...given } : value;
  }
  return next;
}

// ------------------------------------------------------------------------ the words
/** A draft's state as a person reads it. A word nobody here has heard of is drawn as itself. */
export const STATE_WORDS: Readonly<Record<string, string>> = Object.freeze({
  draft: "Draft",
  checked: "Checked",
  waiting: "Waiting for a second approver",
  declined: "Sent back",
  published: "Published",
});

export function stateWords(state: string): string {
  return STATE_WORDS[state] ?? state;
}

export const KIND_WORDS: Readonly<Record<string, string>> = Object.freeze({
  new: "New agent",
  edit: "Change to an agent",
});

export function kindWords(kind: string): string {
  return KIND_WORDS[kind] ?? kind;
}

/** What each act on a revision reads as, in the draft's history. */
export const ACT_WORDS: Readonly<Record<string, string>> = Object.freeze({
  checked: "Checked",
  requested: "Asked for a second approver",
  approved: "Approved by a second person",
  declined: "Sent back by a second person",
  published: "Published",
});

export const NOTHING_IS_LIVE =
  "Nothing in a draft is live. Every save is kept as its own version, and the agent changes only when a checked version is published.";

/** Confirmations, each saying what will happen before it happens. */
export const START_SCRATCH_QUESTION = "Start a new agent from scratch?";
export const START_TEMPLATE_QUESTION = (name: string): string => `Start a new agent from ${name}?`;
export const START_CONSEQUENCE =
  "A draft is made for you alone. Nothing is live until it is checked and published, and it starts at Shadow either way.";
export const EDIT_QUESTION = (name: string): string => `Edit ${name} as a draft?`;
export const EDIT_CONSEQUENCE =
  "A draft is made from the agent as it is now. The agent keeps working as it is until the draft is checked and published.";
/** What each of the form's sections is called in a question, by the API's own word for it. */
export const SECTION_WORDS: Readonly<Record<string, string>> = Object.freeze({
  identity: "name and summary",
  persona: "instructions",
  knowledge: "knowledge",
  skills: "skills",
  tools: "tools and permissions",
  leash: "supervision",
  tests: "test questions",
});
export const SAVE_QUESTION = (section: string): string => `Save the ${SECTION_WORDS[section] ?? section} section?`;
export const SAVE_CONSEQUENCE = "It is kept as a new version of this draft. Nothing is live, and earlier versions are kept.";
export const CHECK_QUESTION = "Check this draft?";
export const CHECK_CONSEQUENCE =
  "The latest version is checked against this install. A version that passes can be published; nothing else changes.";
export const REHEARSE_QUESTION = "Rehearse this draft as you?";
export const REHEARSE_CONSEQUENCE =
  "It runs through the real permission checks as you, at Shadow. Nothing is carried out and no record is read.";
export const DRAW_QUESTION = "Turn this drawing into a skill document?";
export const DRAW_CONSEQUENCE =
  "The server writes the skill document the drawing is. Nothing is kept: add it on the Skills page to have it reviewed.";
export const PUBLISH_QUESTION = (name: string): string => `Publish ${name}?`;
export const PUBLISH_CONSEQUENCE =
  "If it reaches no further than before, it is published now, starting at Shadow. If it reaches further, it waits for a second person to approve it.";
export const APPROVE_QUESTION = (name: string): string => `Approve and publish ${name}?`;
export const APPROVE_CONSEQUENCE =
  "It is published now, starting at Shadow. You are approving everything listed as reaching further, as the second person.";
export const DECLINE_QUESTION = (name: string): string => `Send ${name} back?`;
export const DECLINE_CONSEQUENCE = "Nothing is published. Its author can change it and ask again.";
export const KEEP_LABEL = "Not now";

/** Said before a form is submitted, so nobody learns the format from a refusal. */
export const PROCEDURE_NAME_HINT = "Lower-case letters, digits and hyphens, starting with a letter: look-up-an-invoice.";
export const PROCEDURE_DESCRIPTION_HINT = "One sentence beginning with \"Use when\": Use when somebody asks about one invoice.";
export const FORM_HINT =
  "Each section is saved on its own. The address, version and publisher are set when it is published, whatever the form shows.";
