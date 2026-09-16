/**
 * What the Prompts screen asks for and says. No React.
 *
 * `brain.prompt_routes` answers two kinds of instruction. The system instructions, the house rules
 * every agent opens with and the answer lengths, are product text: shown so an administrator knows
 * what every agent is told, and never editable. An agent's own instructions are its persona,
 * versioned the way the product versions an agent: the template's signed text at a version, and
 * this install's change recorded against it with who set it and when.
 *
 * **`docs/screens.html` SCREEN 5 draws "System prompt and role: versioned"** among what a template
 * carries, and a local edit recorded as a divergence rather than lost at the next update. This
 * screen is that sentence made editable, and says what the platform does not yet do: nothing sends
 * a prompt to a model, so an edit changes what an agent would be given rather than an answer
 * anybody has received.
 *
 * **Nothing here decides who may read or edit.** `editable` only decides whether a button is drawn,
 * and the edit route asks every question again. Client-side, the only check is the length the API
 * states, so a person is told before they send; every other refusal is the API's sentence.
 *
 * Task ids: M27.8.9
 */

import type { components } from "../api/schema";

export type PromptsBody = components["schemas"]["PromptsPage"];
export type AgentInstructions = components["schemas"]["AgentInstructionsView"];

export const PROMPTS_API_PATH = "/govern/prompts";
export const PROMPTS_PATH = "/prompts";
export const PROMPTS_LABEL = "Prompts";
export const PROMPTS_CRUMB = "Govern › Prompts";
export const PROMPTS_LEDE =
  "The instructions every agent is given: the system's own, which no install can change, and each " +
  "agent's, which an administrator can replace here.";

export const READING_PROMPTS = "Reading the instructions.";
export const NO_AGENTS = "There is no agent whose instructions this screen can show you.";
export const THE_BRAIN_COULD_NOT_BE_REACHED = "The Brain could not be reached";
export const UNREADABLE_ANSWER =
  "The API answered in a shape this console does not read, so no instructions are listed. The " +
  "console and the API are probably from different releases.";

export const SYSTEM_HEADING = "System instructions";
export const HOUSE_RULES_HEADING = "Every agent opens with these rules";
export const LENGTHS_HEADING = "How long an answer may be";
export const SYSTEM_INSTRUCTIONS_ARE_PRODUCT_TEXT =
  "These are part of the product and are the same on every install. They cannot be edited here, " +
  "because one of them is what stops a model saying that something was withheld; they change only " +
  "with a release.";
export const NO_MODEL_IS_CALLED_YET =
  "Nothing in the platform sends a prompt to a model yet. An edit changes what an agent would be " +
  "given from the next request, and no answer anybody has received.";
export const EVERY_CHANGE_IS_IN_THE_AUDIT_TRAIL =
  "An agent keeps its current instructions and who set them, not the ones before. Every edit and " +
  "give-back, and who made it, is kept in the audit trail, without the words.";
export const EDITING_SWITCHED_OFF =
  "Editing instructions is switched off on this install. An administrator switches it on under " +
  "Install, Features. Instructions already changed can still be given back to their template.";
export const NOT_INSTALLED =
  "This agent has no install record, so its instructions have no template to be recorded against " +
  "and cannot be edited here.";

export const EDIT = "Edit instructions";
export const SAVE = "Replace instructions";
export const CANCEL = "Cancel";
export const GIVE_BACK = "Give back to template";
export const KEEP_IT = "Leave them as they are";
export const TEMPLATE_INSTRUCTIONS = "The template's instructions";

export function editPath(agentId: string): string {
  return `${PROMPTS_API_PATH}/${encodeURIComponent(agentId)}`;
}
export function giveBackPath(agentId: string): string {
  return `${PROMPTS_API_PATH}/${encodeURIComponent(agentId)}/give-back`;
}

/** Who set the instructions in force, in words. */
export function setWords(row: AgentInstructions, when: (value: string) => string): string {
  if (!row.installed) {
    return NOT_INSTALLED;
  }
  const at = row.set_at ? ` at ${when(row.set_at)}` : "";
  const source = row.template_id ? `${row.template_id} version ${String(row.template_version)}` : "";
  return row.overridden
    ? `This install's own instructions, set by ${row.set_by ?? "somebody"}${at}, in place of ${source}.`
    : `The template's instructions, from ${source}, signed by ${row.set_by ?? "its publisher"}${at}.`;
}

/** Why the text in the editor cannot be sent yet, or null. The API decides everything else. */
export function lengthProblem(text: string, maxChars: number): string | null {
  const length = text.trim().length;
  if (length === 0) {
    return "Instructions cannot be empty. To use the template's, give them back instead.";
  }
  if (length > maxChars) {
    return `Instructions are at most ${String(maxChars)} characters, and these are ${String(length)}.`;
  }
  return null;
}

export function editQuestion(row: AgentInstructions): string {
  return `Replace ${row.display_name}'s instructions?`;
}

export function editConsequence(row: AgentInstructions): string {
  return (
    `From the next request, ${row.display_name} is given the new instructions instead of the ones ` +
    `in force. The change is recorded against ${row.template_id ?? "its template"} as set by you, and ` +
    "the instructions it replaces are not kept."
  );
}

export function giveBackQuestion(row: AgentInstructions): string {
  return `Give ${row.display_name}'s instructions back to its template?`;
}

export function giveBackConsequence(row: AgentInstructions): string {
  return (
    `From the next request, ${row.display_name} is given the instructions ${row.template_id ?? "its template"} ` +
    "ships with, and this install's own instructions are not kept."
  );
}

export function readPrompts(payload: unknown): PromptsBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { agents?: unknown; house_rules?: unknown; max_chars?: unknown };
  if (!Array.isArray(body.agents) || !Array.isArray(body.house_rules)) {
    return null;
  }
  if (typeof body.max_chars !== "number") {
    return null;
  }
  return payload as PromptsBody;
}
