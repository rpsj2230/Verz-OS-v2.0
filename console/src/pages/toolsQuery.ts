/**
 * What the Tools screen asks for and says. No React.
 *
 * `brain.tool_routes` answers every tool this install registers, with the capability a caller
 * must hold for it, whether it reads, writes or does something that cannot be taken back, the
 * owner's sensitive effect it names, its result contract and the highest rung a leash on it
 * keeps; and where it is switched off, for the install or for a department's people. The page
 * throws a switch only through the API, which decides who may throw which one from the reader's
 * own `admin:tool` grant.
 *
 * **`docs/screens.html` draws no Tools screen**, so this is drawn in the register of the Features
 * screen: a card per tool, and the facts about what a switch is said in words under them, each a
 * field on the answer so the sentence leaves the page in the commit that makes it false.
 *
 * Task ids: M12.1.1, M12.1.3, M12.1.4, M12.3.8, M12.4.3
 */

import type { components } from "../api/schema";

export type ToolsBody = components["schemas"]["ToolsPage"];
export type ToolRow = components["schemas"]["CatalogueToolView"];
export type StopRow = components["schemas"]["ToolStopView"];

/** Where the API keeps this screen. */
export const TOOLS_API_PATH = "/tools";

/** The console address. */
export const TOOLS_PATH = "/tools";

export const TOOLS_LABEL = "Tools";
export const TOOLS_CRUMB = "Govern › Tools";
export const TOOLS_LEDE =
  "Every tool an agent, a workflow or an automation can call on this install: what a person must " +
  "hold for it to be offered, and what it does. A tool switched off here is refused at every call.";

export const READING_TOOLS = "Reading the tools this install offers.";
export const NO_TOOLS = "This install registers no tool yet.";
export const UNREADABLE_ANSWER =
  "The API answered in a shape this console does not read, so no tool is listed. The console and " +
  "the API are probably from different releases.";

export const ON = "On";
export const OFF_FOR_THE_INSTALL = "Off for the install";
export const NO_LONGER_OFFERED =
  "This install no longer registers this tool. It is listed because its catalogue row is kept, so " +
  "a stop on it still has something to name.";
export const KEEP_IT = "Leave it as it is";
export const SWITCH_OFF_FOR_THE_INSTALL = "Switch off for the install";
export const SWITCH_ON_FOR_THE_INSTALL = "Switch back on for the install";
export const REASON_LABEL = "Why it is safe to start again";
export const NOTE_LABEL = "A note for other administrators (optional)";

/** The words the three effects are drawn with, and what each means. */
export const EFFECT_WORDS: Readonly<Record<string, string>> = {
  read: "Read",
  write: "Write",
  irreversible: "Irreversible",
};
export const EFFECT_SENTENCES: Readonly<Record<string, string>> = {
  read: "Reads and changes nothing.",
  write: "Changes something, and its leash decides whether a person sees it first.",
  irreversible:
    "Cannot be taken back: every call waits for a person to approve the exact prepared action, " +
    "whatever its leash says.",
};

/** The owner's seven sensitive effects, as a sentence each. */
export const SENSITIVE_EFFECT_SENTENCES: Readonly<Record<string, string>> = {
  client_message: "It sends a message to a client.",
  quotation: "It issues a quotation.",
  dns_or_hosting: "It changes DNS or hosting.",
  financial_record: "It changes a financial record.",
  deletion: "It deletes information.",
  publication: "It publishes content.",
  production_change: "It changes a production system.",
};

/** A rung as the leash screens spell it. */
export const RUNG_WORDS: Readonly<Record<string, string>> = {
  shadow: "Shadow",
  assisted: "Assisted",
  autonomous: "Autonomous",
};

/** The three facts the answer carries about what a switch is. */
export const A_SWITCH_ONLY_NARROWS =
  "A switch can only stop a tool. Nothing here can let an agent do more than the person it acts " +
  "for, and a department's stop cannot reopen a tool switched off for the whole install.";
export const THE_ASKER_IS_NEVER_TOLD =
  "The person whose call is refused is told only that it could not be done. The Logs screen names " +
  "the tool and whether the install or a department stopped it.";
export const EVERY_CHANGE_IS_IN_THE_AUDIT_TRAIL =
  "Every switch, and who threw it, is kept in the audit trail. A reason typed here is not.";

/** One stop in words. */
export function stopSentence(stop: StopRow, when: (value: string) => string): string {
  const where = stop.department === null || stop.department === undefined ? "the install" : stop.department;
  const note = stop.reason === null || stop.reason === undefined ? "" : ` Note: ${stop.reason}`;
  return `Switched off for ${where} by ${stop.switched_off_by} at ${when(stop.switched_off_at)}.${note}`;
}

/** Whether this tool is stopped for this department, as this reader is shown it. */
export function stoppedFor(row: ToolRow, department: string): boolean {
  return row.stopped_for.some((one) => one.department === department);
}

/** One switch a reader may throw from this page. */
export interface SwitchChoice {
  readonly tool: string;
  /** Null for the install. */
  readonly department: string | null;
  /** The direction: true to start the tool again. */
  readonly on: boolean;
}

/** The switches this reader may throw on this tool, install first, then each department. */
export function choicesFor(row: ToolRow, body: ToolsBody): SwitchChoice[] {
  const choices: SwitchChoice[] = [];
  if (body.may_switch_install) {
    choices.push({ tool: row.name, department: null, on: row.off_for_install !== null && row.off_for_install !== undefined });
  }
  for (const department of body.departments) {
    choices.push({ tool: row.name, department, on: stoppedFor(row, department) });
  }
  return choices;
}

/** The button a choice is drawn as. */
export function choiceLabel(choice: SwitchChoice): string {
  if (choice.department === null) {
    return choice.on ? SWITCH_ON_FOR_THE_INSTALL : SWITCH_OFF_FOR_THE_INSTALL;
  }
  return choice.on ? `Start again for ${choice.department}` : `Stop for ${choice.department}`;
}

/** The confirmation question, naming the tool, the place and the direction. */
export function choiceQuestion(choice: SwitchChoice): string {
  const where = choice.department === null ? "the whole install" : choice.department;
  return choice.on ? `Start "${choice.tool}" again for ${where}?` : `Switch off "${choice.tool}" for ${where}?`;
}

/** What happens, for the direction and the place. */
export function choiceConsequence(choice: SwitchChoice): string {
  const whose =
    choice.department === null
      ? "every agent, workflow and automation on this install"
      : `every agent, workflow and automation acting for somebody in ${choice.department}`;
  return choice.on
    ? `Calls to it from ${whose} run again at the next call.`
    : `Calls to it from ${whose} are refused from the next call until somebody starts it again.`;
}

/** The API route a switch is posted to. */
export function switchPath(name: string): string {
  return `${TOOLS_API_PATH}/${encodeURIComponent(name)}/switch`;
}

/** The body a choice is posted with. */
export function switchBody(choice: SwitchChoice, reason: string): { on: boolean; department: string | null; reason: string | null } {
  const trimmed = reason.trim();
  return { on: choice.on, department: choice.department, reason: trimmed === "" ? null : trimmed };
}

/** What a success says, with whether anything changed. */
export function switchedSentence(choice: SwitchChoice, changed: boolean): string {
  const where = choice.department === null ? "the install" : choice.department;
  if (!changed) {
    return `Nothing changed: "${choice.tool}" was already ${choice.on ? "on" : "off"} for ${where}.`;
  }
  return choice.on ? `"${choice.tool}" is on again for ${where}.` : `"${choice.tool}" is switched off for ${where}.`;
}

/** Read `brain.tool_routes.ToolsPage`, or null for a shape this console does not read. */
export function readTools(payload: unknown): ToolsBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { tools?: unknown; departments?: unknown; may_switch_install?: unknown };
  if (!Array.isArray(body.tools) || !Array.isArray(body.departments) || typeof body.may_switch_install !== "boolean") {
    return null;
  }
  return payload as ToolsBody;
}

/** Read whether a switch changed anything, or null for an unreadable answer. */
export function readChanged(payload: unknown): boolean | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const changed = (payload as { changed?: unknown }).changed;
  return typeof changed === "boolean" ? changed : null;
}
