/**
 * What the Quick answers screen asks for and says. No React.
 *
 * `brain.rule_routes` lists the fast-lane rules a reader may see, adds one at a place the
 * administrator may write, tries a candidate against a question without saving it, and retires
 * one. This module holds the addresses, the readers of those shapes, the request bodies, and every
 * sentence the page shows.
 *
 * **Who may do what is the API's answer, drawn as the API sent it.** The list holds only the rules
 * at places the reader's grant admits, and a refusal of a rule another department wrote arrives as
 * the sentence a missing rule gets. Nothing here filters a rule out or decides a place is out of
 * reach, because a second answer in the browser to who may see a rule is the copy an attacker
 * edits.
 *
 * **No figure counts the rules.** A count of the rules listed beside a total would say how many
 * rules other departments hold, so the page draws the rules and nothing counted. See
 * `NO_FIGURE_HERE_COUNTS_WHAT_THE_READER_WAS_NOT_SHOWN`.
 *
 * **The rule's machine names are kept, and each is said in words beside its box.** A rule is a
 * question shape over a table's columns, and the columns are named as the Fields page names them,
 * so the box takes the name and the hint says what it is for. Rejected: a picker of tables and
 * columns, which would need a read of every table the administrator may change on a screen whose
 * subject is rules; the API refuses a rule that names nothing it serves, and the Try it button says
 * so before anything is saved.
 *
 * Task ids: M6.5.1
 */

import type { components } from "../api/schema";

export type RulesBody = components["schemas"]["FastRulesView"];
export type RuleShown = components["schemas"]["FastRuleView"];
export type RuleAsked = components["schemas"]["FastRuleAsked"];
export type RuleTried = components["schemas"]["FastRuleTried"];
export type RuleWritten = components["schemas"]["FastRuleWritten"];
export type RuleTrial = components["schemas"]["FastRuleTrial"];

/** Written down because "3 of your 12 rules" is the easy version of this page. */
export const NO_FIGURE_HERE_COUNTS_WHAT_THE_READER_WAS_NOT_SHOWN =
  "The list holds the rules at the places this reader's grant admits, chosen by the API. A count " +
  "of them beside any total would say how many rules other departments hold, so nothing on the " +
  "page is a count of rules.";

/** Where the API keeps the rules. */
export const RULES_API_PATH = "/rules";

/** Where a candidate is tried. */
export const TRY_API_PATH = "/rules/test";

/** The console address. */
export const RULES_PATH = "/rules";

/** The route one rule is retired at. */
export function retireApiPath(ruleId: string): string {
  return `${RULES_API_PATH}/${encodeURIComponent(ruleId)}/retire`;
}

/** Where an uploaded table's rows are read from, which is what most rules answer from. */
export const UPLOADED_TABLES = "tables";

export const RULES_LABEL = "Quick answers";
export const RULES_LEDE =
  "A question asked in exactly these words is answered straight from a table, with no model. A rule answers from the next question after it is added, and stops from the next question after it is retired.";

export const READING_RULES = "Reading the quick answers you may see.";
export const NO_RULES_TITLE = "No quick answers yet";
export const NO_RULES = "No question is answered this way where you work. Add one below and it answers from the next question.";
export const UNREADABLE_ANSWER =
  "The API answered in a shape this console does not read, so no rule is shown. The console and the API are probably from different releases.";

export const LIVE_HEADING = "In use";
export const ADD_HEADING = "Add a quick answer";
export const ADD_LEDE = "Try it with a real question first. Trying it saves nothing.";
export const WHOLE_COMPANY = "Whole company";
export const ASKED_BY = "Asked by";
export const ANSWERS_WITH = "Answers with";
export const FROM_TABLE = "from";
export const ADDED_BY = "Added by";

export const NAME_LABEL = "Short name";
export const NAME_HINT = "Lower-case letters, digits and underscores, such as hourly_rate.";
export const DEPARTMENT_LABEL = "Department";
export const DEPARTMENT_HINT_INSTALL = "The department whose people it answers. Leave it empty to answer everybody in the company.";
export const DEPARTMENT_HINT = "The department whose people it answers.";
export const TEMPLATE_LABEL = "Question words";
export const TEMPLATE_HINT = 'The question exactly as people ask it, with the part that changes in braces, such as "what is the rate for {name}".';
export const SLOT_LABEL = "The part that changes";
export const SLOT_HINT = "The word inside the braces, such as name.";
export const ENTITY_LABEL = "Table";
export const ENTITY_HINT = "The table's name as the Fields page shows it.";
export const MATCH_LABEL = "Look it up in";
export const MATCH_HINT = "The column the part in braces is found in.";
export const ANSWER_LABEL = "Answer with";
export const ANSWER_HINT = "The column whose value is the answer.";
export const SOURCE_LABEL = "Where the table lives";
export const SOURCE_HINT = `Uploaded tables are "${UPLOADED_TABLES}".`;
export const QUESTION_LABEL = "A question to try it with";
export const QUESTION_HINT = "Asked as you, so it answers only what you may read yourself.";

export const TRY = "Try it";
export const ADD = "Add";
export const RETIRE = "Retire";
export const KEEP = "Keep it";
export const RETIRE_QUESTION = "Retire this quick answer?";
export const RETIRE_CONSEQUENCE =
  "From the next question, these words are answered the usual way instead. The rule is kept in the record of what answered each question, and cannot be brought back; add it again if you need it.";

export const NOT_ADDED = "The quick answer was not added";
export const NOT_TRIED = "The quick answer could not be tried";
export const NOT_RETIRED = "The quick answer was not retired";
export const FILL_EVERY_BOX = "Fill in every box before trying or adding the rule.";
export const NEEDS_A_QUESTION = "Write a question to try it with.";

/** The empty form, with the department the API says the reader works in. */
export interface RuleDraft {
  readonly name: string;
  readonly department: string;
  readonly template: string;
  readonly slot: string;
  readonly source: string;
  readonly entity: string;
  readonly matchField: string;
  readonly answerField: string;
  readonly question: string;
}

export function emptyDraft(ownDepartment: string | null): RuleDraft {
  return {
    name: "",
    department: ownDepartment ?? "",
    template: "",
    slot: "",
    source: UPLOADED_TABLES,
    entity: "",
    matchField: "",
    answerField: "",
    question: "",
  };
}

/** The rule the API is sent, or null while a box is empty. A blank department is the company. */
export function ruleBody(draft: RuleDraft): RuleAsked | null {
  const fields = [draft.name, draft.template, draft.slot, draft.source, draft.entity, draft.matchField, draft.answerField];
  if (fields.some((one) => one.trim() === "")) {
    return null;
  }
  const department = draft.department.trim();
  return {
    name: draft.name.trim(),
    department: department === "" ? null : department,
    template: draft.template.trim(),
    slot: draft.slot.trim(),
    source: draft.source.trim(),
    entity: draft.entity.trim(),
    match_field: draft.matchField.trim(),
    answer_field: draft.answerField.trim(),
  };
}

/** The rule and the question to try it with, or null while either is incomplete. */
export function trialBody(draft: RuleDraft): RuleTried | null {
  const rule = ruleBody(draft);
  const question = draft.question.trim();
  return rule === null || question === "" ? null : { ...rule, question };
}

/** Where a rule answers, in words. */
export function placeOf(rule: RuleShown): string {
  return rule.department ?? WHOLE_COMPANY;
}

function isRule(item: unknown): item is RuleShown {
  if (typeof item !== "object" || item === null) {
    return false;
  }
  const one = item as Record<string, unknown>;
  return (
    typeof one["rule_id"] === "string" &&
    typeof one["template"] === "string" &&
    typeof one["entity"] === "string" &&
    typeof one["answer_field"] === "string" &&
    (one["department"] === null || typeof one["department"] === "string")
  );
}

/** Read `FastRulesView`, or null for a shape this console does not know. */
export function readRules(payload: unknown): RulesBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { rules?: unknown; may_write_install?: unknown };
  if (!Array.isArray(body.rules) || !body.rules.every(isRule) || typeof body.may_write_install !== "boolean") {
    return null;
  }
  return payload as RulesBody;
}

/** Read `FastRuleWritten`, or null. */
export function readWritten(payload: unknown): RuleWritten | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { done?: unknown; told?: unknown };
  return typeof body.done === "boolean" && typeof body.told === "string" ? (payload as RuleWritten) : null;
}

/** Read `FastRuleTrial`, or null. */
export function readTrial(payload: unknown): RuleTrial | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { matches?: unknown; told?: unknown; answer?: unknown };
  return typeof body.matches === "boolean" && typeof body.told === "string" && (body.answer === null || typeof body.answer === "string")
    ? (payload as RuleTrial)
    : null;
}
