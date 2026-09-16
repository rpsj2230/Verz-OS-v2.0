/**
 * What the Automations tab asks the API for, and how each answer becomes what the gallery draws.
 *
 * **Every decision is the API's, and nothing here could make one.** Whether the gallery opens is
 * the Automations tab's own read, whether a card offers an install is `installable` as
 * `brain.automation_gallery_routes` computed it for this reader, and whether an install is written
 * is decided again by the route, which recomputes the preview and refuses a confirmation that does
 * not match. This file drops what is malformed and carries the rest in the order it arrived.
 *
 * **The confirmation is carried and never computed.** `readPreview` keeps the digest the API sent
 * beside the facts it was computed over, and `installBody` sends exactly that digest back. A
 * console that computed its own would be a second description of what the person agreed to, and
 * the one the server refuses would be the one on the screen.
 *
 * **A 409 is read for its sentence, and a 404 is not read at all.** The route answers a stale
 * confirmation and a second install of the same thing with `NotInstalledView`, which is about the
 * caller's own request and says what to do. Every other refusal is `ErrorBody`, and the gallery
 * shows its sentence exactly as `api/client.ts` shaped it.
 *
 * Task ids: M39.6.1.3
 */

/** The workspace tab this gallery is drawn in, as `brain.console.workspace.Tab` spells it. */
export const AUTOMATIONS_TAB = "automations";

export function automationGalleryApiPath(agentId: string): string {
  return `/agents/${encodeURIComponent(agentId)}/automation-templates`;
}

export function automationPreviewApiPath(agentId: string, templateId: string): string {
  return `/agents/${encodeURIComponent(agentId)}/automation-templates/${encodeURIComponent(templateId)}/preview`;
}

export function automationInstallApiPath(agentId: string): string {
  return `/agents/${encodeURIComponent(agentId)}/automations`;
}

/** One card, as `AutomationTemplateView` sends it. */
export interface AutomationCard {
  readonly templateId: string;
  readonly version: number;
  /** The outcome, in the first person. */
  readonly name: string;
  readonly summary: string;
  /** The cadence once started, in the API's words and with its zone. */
  readonly schedule: string;
  /** The automation this reader already installed from it on this agent. */
  readonly installedAs?: string;
  /** This reader may install it here. Decides whether a button is drawn and nothing else. */
  readonly installable: boolean;
}

/** The gallery as this console holds it. No field is a count. */
export interface AutomationGalleryAnswer {
  readonly cards: readonly AutomationCard[];
  /** What installing does and does not do, in the API's words. */
  readonly installing: string;
}

/** Everything the person confirms, as `InstallPreviewView` sends it. */
export interface InstallPreview {
  readonly templateId: string;
  readonly name: string;
  readonly summary: string;
  readonly schedule: string;
  readonly runsAs: string;
  readonly runsAsName: string;
  readonly startsPaused: boolean;
  readonly pausedBecause: string;
  /** What it would reach, by capability, in the API's order. May be empty, and says so. */
  readonly reach: readonly string[];
  readonly reachRule: string;
  readonly guards: string;
  readonly installing: string;
  /** The digest an install must carry back, exactly as sent. */
  readonly confirmation: string;
}

/** What was installed. */
export interface InstalledAutomation {
  readonly automationId: string;
  readonly name: string;
}

/** Why nothing was installed, in the API's word and sentence. */
export interface NotInstalled {
  readonly outcome: string;
  readonly sentence: string;
  readonly automationId?: string;
}

type Fields = Readonly<Record<string, unknown>>;

function fieldsOf(value: unknown): Fields | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  // A cast at the boundary, where proving a structural match buys nothing: every field is read
  // back through `said`, `published` or a boolean check below, which narrow everything this widens.
  return value as Fields;
}

function said(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

function published(value: unknown): number | undefined {
  return typeof value === "number" && Number.isInteger(value) && value >= 1 ? value : undefined;
}

/** A confirmation: the SHA-256 the route computes, and nothing else. */
const DIGEST = /^[0-9a-f]{64}$/;

/**
 * The gallery out of a response body, or `null` when the body is not a gallery.
 *
 * A card missing any fact it is drawn from is dropped rather than drawn with a gap, and a second
 * card for a template already read is dropped, for `readTemplates`' reason.
 */
export function readGallery(payload: unknown): AutomationGalleryAnswer | null {
  const fields = fieldsOf(payload);
  const items = fields?.["items"];
  const installing = said(fields?.["installing"]);
  if (fields === null || !Array.isArray(items) || installing === undefined) {
    return null;
  }
  const seen = new Set<string>();
  const cards: AutomationCard[] = [];
  for (const item of items as readonly unknown[]) {
    const entry = fieldsOf(item);
    const templateId = said(entry?.["template_id"]);
    const version = published(entry?.["version"]);
    const name = said(entry?.["name"]);
    const summary = said(entry?.["summary"]);
    const schedule = said(entry?.["schedule"]);
    if (
      templateId === undefined ||
      version === undefined ||
      name === undefined ||
      summary === undefined ||
      schedule === undefined ||
      seen.has(templateId)
    ) {
      continue;
    }
    seen.add(templateId);
    const installedAs = said(entry?.["installed_as"]);
    cards.push({
      templateId,
      version,
      name,
      summary,
      schedule,
      installable: entry?.["installable"] === true,
      ...(installedAs === undefined ? {} : { installedAs }),
    });
  }
  return { cards, installing };
}

/**
 * A preview out of a response body, or `null` when any fact the person confirms is missing.
 *
 * All or nothing, because a confirmation panel with a fact left out is a person agreeing to
 * something they were not shown, and the digest was computed over the whole of it.
 */
export function readPreview(payload: unknown): InstallPreview | null {
  const fields = fieldsOf(payload);
  if (fields === null) {
    return null;
  }
  const templateId = said(fields["template_id"]);
  const name = said(fields["name"]);
  const summary = said(fields["summary"]);
  const schedule = said(fields["schedule"]);
  const runsAs = said(fields["runs_as"]);
  const runsAsName = said(fields["runs_as_name"]);
  const pausedBecause = said(fields["paused_because"]);
  const reachRule = said(fields["reach_rule"]);
  const guards = said(fields["guards"]);
  const installing = said(fields["installing"]);
  const confirmation = said(fields["confirmation"]);
  const reach = fields["reach"];
  if (
    templateId === undefined ||
    name === undefined ||
    summary === undefined ||
    schedule === undefined ||
    runsAs === undefined ||
    runsAsName === undefined ||
    pausedBecause === undefined ||
    reachRule === undefined ||
    guards === undefined ||
    installing === undefined ||
    confirmation === undefined ||
    !DIGEST.test(confirmation) ||
    typeof fields["starts_paused"] !== "boolean" ||
    !Array.isArray(reach) ||
    !(reach as readonly unknown[]).every((one) => said(one) !== undefined)
  ) {
    return null;
  }
  return {
    templateId,
    name,
    summary,
    schedule,
    runsAs,
    runsAsName,
    startsPaused: fields["starts_paused"],
    pausedBecause,
    reach: reach as readonly string[],
    reachRule,
    guards,
    installing,
    confirmation,
  };
}

/** The body an install sends: which template, and the digest the person confirmed. Nothing else. */
export function installBody(preview: InstallPreview): { template_id: string; confirmation: string } {
  return { template_id: preview.templateId, confirmation: preview.confirmation };
}

export function readInstalled(payload: unknown): InstalledAutomation | null {
  const fields = fieldsOf(payload);
  const automationId = said(fields?.["automation_id"]);
  const name = said(fields?.["name"]);
  return automationId === undefined || name === undefined ? null : { automationId, name };
}

export function readNotInstalled(payload: unknown): NotInstalled | null {
  const fields = fieldsOf(payload);
  const outcome = said(fields?.["outcome"]);
  const sentence = said(fields?.["sentence"]);
  if (outcome === undefined || sentence === undefined) {
    return null;
  }
  const automationId = said(fields?.["automation_id"]);
  return { outcome, sentence, ...(automationId === undefined ? {} : { automationId }) };
}
