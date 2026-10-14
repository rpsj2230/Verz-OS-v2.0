/**
 * Asking the API why one act cannot be done, and reading what it answers.
 *
 * `GET /console/explanations/{act}` answers one sentence, the lead a note says first and the form
 * the server registered it in (`brain.explanation_routes.ExplanationView`). The body is the same for
 * every reader, so there is nothing here that depends on who is asking and nothing to cache a person
 * into: the hook asks again at each mount, like every other read in this console.
 *
 * **A body that is not that shape is not read.** `readExplanation` returns null for it, and the
 * component then says the reason could not be read, in a sentence of its own, rather than drawing
 * nothing. An explanation is never hidden: a control that cannot be pressed and says nothing about
 * why is the thing this component exists to prevent.
 *
 * Task ids: M27.15.70
 */

/** What a note says first, kept apart from its sentence. Empty for the other forms. */
export type ExplanationLead = "" | "soon" | "not-yet";

/** One explanation as the API serves it. */
export interface Served {
  readonly act: string;
  readonly form: string;
  readonly lead: ExplanationLead;
  readonly sentence: string;
}

/** The address one act's sentence is asked for at, relative to the API prefix. */
export function explanationApiPath(act: string): string {
  return `/console/explanations/${encodeURIComponent(act)}`;
}

/** The body, or null when it is not the shape the API sends. */
export function readExplanation(body: unknown): Served | null {
  if (typeof body !== "object" || body === null) {
    return null;
  }
  const record = body as Record<string, unknown>;
  const { act, form, lead, sentence } = record;
  if (typeof act !== "string" || typeof form !== "string" || typeof sentence !== "string" || sentence === "") {
    return null;
  }
  if (lead !== "" && lead !== "soon" && lead !== "not-yet") {
    return null;
  }
  return { act, form, lead, sentence };
}

/**
 * Said when the sentence itself could not be read. The one explanation the console types for
 * itself, because the failure to read the others cannot be explained by one of them.
 */
export const EXPLANATION_NOT_READ = "Why this is not available could not be read just now. Reload the page to see it.";
