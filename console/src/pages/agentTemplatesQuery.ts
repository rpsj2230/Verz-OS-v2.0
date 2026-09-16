/**
 * What the template gallery asks the API for, and how an answer becomes the cards it draws.
 *
 * **The catalogue is the API's and nothing here decides who may read it.** `GET
 * /api/v1/agent-templates` is answered behind the Skills and templates screen's own read, and
 * a reader without it gets the refusal that screen gives, in its words. This file has nothing
 * to filter with and filters nothing: it drops a card that does not say which template it is,
 * and a second card for a template already read, and carries the rest in the order they
 * arrived.
 *
 * **Six fields a card, and none of them is an install count.** The design's card carries "4
 * installed" beside each template, and the API deliberately sends no such number: the agents
 * installed from a template are agents, and a count of them is a count of rows this reader may
 * not be able to open. So there is nothing here to read one out of, and a body carrying one
 * reaches nothing.
 *
 * **`origin` is carried because the two kinds are not interchangeable.** A built-in template
 * is one of the twenty-three this product ships and carries no signature, because nobody has
 * published it; a published one is a row this installation signed. A gallery that merged them
 * would let the second wear the first's authority, and a person choosing a role would have no
 * way to tell what they were installing.
 *
 * Rejected: an install control. `brain.agents.install` needs a signing key and a wizard, and
 * no route serves either, so a button here would be a control that does nothing. A gallery
 * that offers a one-step install and cannot perform one is worse than a gallery that offers
 * none, which is `brain.console.agent_tabs.Control`'s argument about an attach button beside
 * an unapproved skill, one surface along.
 *
 * This closes no leaf and says so positionally, because the word "not" on a line parsed for
 * ids is a claim: M39.6.1.3 is the work breakdown's only template gallery and it is a gallery
 * of common *automations* with a one-step install, which is a different thing from a catalogue
 * of agent roles and is drawn on an agent's Automations tab by `components/AutomationGallery.tsx`
 * over `brain.automation_gallery_routes`. What this
 * serves is the read `brain.agents.catalogue` and `brain.agents.template` already hold and no
 * screen showed.
 *
 * Task ids: none
 */

/** Where the catalogue is asked for, under the API base. */
export const TEMPLATES_API_PATH = "/agent-templates";

/** One template somebody could install, as `brain.agent_routes.TemplateEntry` sends one. */
export interface TemplateCard {
  readonly templateId: string;
  /** The published version, which is what an install would pin. */
  readonly version: number;
  readonly displayName: string;
  /** One sentence saying what the role is for. Absent when the template carries none. */
  readonly summary?: string;
  readonly publishedBy: string;
  /** `brain.agent_routes.Origin`, rendered as it arrived. */
  readonly origin: string;
}

/** The gallery as this console holds it. Two fields, and neither is a count. */
export interface TemplateGalleryAnswer {
  readonly cards: readonly TemplateCard[];
  /** There are more templates than the answer carried. Never how many. */
  readonly truncated: boolean;
}

type Fields = Readonly<Record<string, unknown>>;

function fieldsOf(value: unknown): Fields | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  // A cast at the boundary, where proving a structural match buys nothing: every field is
  // read back through `said` or `published` below, which narrow everything this widens.
  return value as Fields;
}

function said(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

/** A published version: a whole number from one, as `ManifestIdentity.version` is. */
function published(value: unknown): number | undefined {
  return typeof value === "number" && Number.isInteger(value) && value >= 1 ? value : undefined;
}

/**
 * The gallery out of a response body, or `null` when the body is not a gallery.
 *
 * `null` rather than an empty list, for `readRoster`'s reason: an empty list is a claim that
 * this installation offers no templates, and a body that is not a gallery makes no claim at
 * all.
 *
 * A card with no version is dropped rather than drawn, because a template with no version is
 * one nothing could be pinned to, and the number beside the name is the whole of what a person
 * checks before installing.
 */
export function readTemplates(payload: unknown): TemplateGalleryAnswer | null {
  const fields = fieldsOf(payload);
  const items = fields?.["items"];
  if (fields === null || !Array.isArray(items)) {
    return null;
  }
  const seen = new Set<string>();
  const cards: TemplateCard[] = [];
  for (const item of items as readonly unknown[]) {
    const entry = fieldsOf(item);
    const templateId = said(entry?.["template_id"]);
    const displayName = said(entry?.["display_name"]);
    const version = published(entry?.["version"]);
    const publishedBy = said(entry?.["published_by"]);
    const origin = said(entry?.["origin"]);
    if (
      templateId === undefined ||
      displayName === undefined ||
      version === undefined ||
      publishedBy === undefined ||
      origin === undefined ||
      seen.has(templateId)
    ) {
      continue;
    }
    seen.add(templateId);
    const summary = said(entry?.["summary"]);
    cards.push({
      templateId,
      version,
      displayName,
      publishedBy,
      origin,
      ...(summary === undefined ? {} : { summary }),
    });
  }
  return { cards, truncated: fields["truncated"] === true };
}
