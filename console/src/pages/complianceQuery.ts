/**
 * What the Compliance screen asks the API for and sends it, and how each form is judged before it
 * is sent. No React.
 *
 * One route module answers the screen, `brain.compliance_routes`, and it asks one authority,
 * `admin:compliance`, on every read and write. Nothing here decides who may act: a caller without
 * the authority is refused by the route in the standard way, and the page draws that refusal like
 * any other.
 *
 * **Every reference is checked against the route's own pattern before it is sent.** A named
 * person, an evidence reference and a rationale reference are all `brain.audit.ledger.IDENTIFIER`
 * on the route's body, and `tests/compliance-page.test.tsx` reads that pattern out of the generated
 * OpenAPI document, so a pattern that drifted is a failed test rather than a 422 in front of the
 * person recording a breach.
 *
 * **Awareness is checked the way `brain.audit.compliance.Awareness` checks it**, because a refusal
 * there arrives after the confirmation: an estimate needs its earliest possible moment, which may
 * not be later than the estimate, and an observed time has none. Neither may be in the future.
 * The clock itself is never computed here; `clock_starts_at` is the server's, and the page draws it.
 *
 * **Nothing about what happened is asked or drawn.** The routes take references to where the
 * evidence and the reasoning are written and never a description, for `brain.tables.compliance`'s
 * reason, so no form here has a free-text box.
 *
 * Task ids: M24.2.2, M24.2.3, M24.2.4
 */

import type { components } from "../api/schema";

export type TopicsAnswer = components["schemas"]["TopicsView"];
export type Topic = components["schemas"]["TopicView"];
export type Tally = components["schemas"]["TallyView"];
export type Named = components["schemas"]["NamedView"];
export type NameBody = components["schemas"]["NameBody"];
export type RegisterAnswer = components["schemas"]["brain__compliance_routes__RegisterView"];
export type RegisterRow = components["schemas"]["RegisterRowView"];
export type BreachesAnswer = components["schemas"]["BreachesView"];
export type Breach = components["schemas"]["BreachView"];
export type Obligation = components["schemas"]["ObligationView"];
export type OpenBody = components["schemas"]["OpenBody"];
export type AssessBody = components["schemas"]["AssessBody"];
export type NotifiedBody = components["schemas"]["NotifiedBody"];
export type ExceptionBody = components["schemas"]["ExceptionBody"];

export const TOPICS_API_PATH = "/govern/compliance/topics";
export const REGISTER_API_PATH = "/govern/compliance/register";
export const BREACHES_API_PATH = "/govern/compliance/breaches";

/** Where the person a topic is routed to is named. */
export function topicApiPath(topic: string): string {
  return `${TOPICS_API_PATH}/${encodeURIComponent(topic)}`;
}

/** The steps a case moves through after it is opened, each its own route. */
export type BreachStep = "assessment" | "commission" | "individuals" | "exception" | "close";

export function breachStepApiPath(caseId: string, step: BreachStep): string {
  return `${BREACHES_API_PATH}/${encodeURIComponent(caseId)}/${step}`;
}

/** A reference: a person, where the evidence is, where the reasoning is. `IDENTIFIER`. */
export const IDENTIFIER_PATTERN = "^[A-Za-z0-9_.@-]{1,128}$";
const IDENTIFIER = new RegExp(IDENTIFIER_PATTERN);

export const AWARENESS_BASES = ["observed", "estimated"] as const;
export const AWARENESS_SOURCES = [
  "internal_detection",
  "staff_report",
  "data_intermediary_notice",
  "third_party_report",
  "regulator_notice",
] as const;
export const EXCEPTION_GROUNDS = ["remedial_action", "technological_protection", "commission_direction"] as const;

/** What each closed value is called on the screen. Product text, the same on every install. */
export const SOURCE_LABELS: Readonly<Record<string, string>> = {
  internal_detection: "Our own detection",
  staff_report: "A report from staff",
  data_intermediary_notice: "A notice from a data intermediary",
  third_party_report: "A report from a third party",
  regulator_notice: "A notice from the regulator",
};
export const GROUND_LABELS: Readonly<Record<string, string>> = {
  remedial_action: "Remedial action made significant harm unlikely",
  technological_protection: "The data was protected by technology",
  commission_direction: "The Commission directed that they not be notified",
};
export const OBLIGATION_LABELS: Readonly<Record<string, string>> = {
  assess: "Assess whether it is notifiable",
  notify_commission: "Notify the Commission",
  notify_individuals: "Notify the individuals affected",
};
export const BASIS_LABELS: Readonly<Record<string, string>> = {
  statutory: "required by the Act",
  guideline: "expected by the regulator's guidance",
};

/** A closed value's label, or the value itself when the vocabulary has outgrown this console. */
export function labelOf(labels: Readonly<Record<string, string>>, value: string): string {
  return labels[value] ?? value;
}

// ----------------------------------------------------------------------------- the tally
/**
 * The month's tally in one sentence. A suppressed tally says only that it is suppressed, because a
 * total below the cohort is the count `InterceptionTally.report` exists not to release.
 */
export function tallySentence(tally: Tally, label: (topic: string) => string): string {
  if (tally.suppressed || tally.total === null) {
    return `For ${tally.period}, the count is suppressed: too few questions were intercepted to show one without pointing at somebody.`;
  }
  const parts = Object.entries(tally.by_topic ?? {}).map(([topic, n]) => `${label(topic)} ${String(n)}`);
  const breakdown = parts.length === 0 ? "" : `: ${parts.join(", ")}`;
  return `For ${tally.period}, ${String(tally.total)} questions were intercepted${breakdown}.`;
}

// ------------------------------------------------------------------------- naming a person
export interface NameForm {
  readonly topic: string;
  readonly principalId: string;
}

export const EMPTY_NAME: NameForm = { topic: "", principalId: "" };

export function nameProblems(form: NameForm, topics: readonly string[]): readonly string[] {
  const problems: string[] = [];
  if (!topics.includes(form.topic)) {
    problems.push("Choose the topic whose questions this person should receive.");
  }
  if (!IDENTIFIER.test(form.principalId.trim())) {
    problems.push(
      "Give the person's reference exactly as the People screen shows it, with no spaces: up to " +
        "128 letters, digits, dots, dashes, underscores or at signs.",
    );
  }
  return problems;
}

export function nameBody(form: NameForm): NameBody {
  return { principal_id: form.principalId.trim() };
}

// ----------------------------------------------------------------------------- instants
/**
 * An instant typed into a local date and time box, as the ISO string the route takes, or null.
 * The box has no zone, so it is read in the browser's, which is where the person typing it is.
 */
export function instantOf(local: string): string | null {
  if (local.trim() === "") {
    return null;
  }
  const parsed = new Date(local);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}

// --------------------------------------------------------------------------- opening a case
export interface OpenForm {
  readonly becameAwareAt: string;
  readonly basis: string;
  readonly source: string;
  readonly evidenceReference: string;
  readonly earliestPossibleAt: string;
}

export const EMPTY_OPEN: OpenForm = {
  becameAwareAt: "",
  basis: "",
  source: "",
  evidenceReference: "",
  earliestPossibleAt: "",
};

/** Everything wrong with a case before it is opened, each a sentence saying what to do. */
export function openProblems(form: OpenForm, now: Date): readonly string[] {
  const problems: string[] = [];
  const aware = instantOf(form.becameAwareAt);
  if (aware === null) {
    problems.push("Give the date and time there was first reason to believe a breach had happened.");
  } else if (new Date(aware).getTime() > now.getTime()) {
    problems.push("The moment of awareness cannot be in the future.");
  }
  if (!(AWARENESS_BASES as readonly string[]).includes(form.basis)) {
    problems.push("Say whether that moment was observed from a record, or is an estimate.");
  }
  if (!(AWARENESS_SOURCES as readonly string[]).includes(form.source)) {
    problems.push("Choose where the reason to believe came from.");
  }
  if (!IDENTIFIER.test(form.evidenceReference.trim())) {
    problems.push(
      "Give a reference to where the evidence is, such as the alert or ticket number, with no " +
        "spaces and no description of what happened.",
    );
  }
  if (form.basis === "estimated") {
    const earliest = instantOf(form.earliestPossibleAt);
    if (earliest === null) {
      problems.push(
        "An estimate needs the earliest moment it could have been. The clock runs from there, not " +
          "from the estimate.",
      );
    } else if (aware !== null && new Date(earliest).getTime() > new Date(aware).getTime()) {
      problems.push("The earliest possible moment cannot be later than the estimate itself.");
    }
  }
  return problems;
}

/** The request body for a case that has no problems. An observed time carries no earliest bound. */
export function openBody(form: OpenForm): OpenBody {
  const body: OpenBody = {
    became_aware_at: instantOf(form.becameAwareAt) ?? "",
    basis: form.basis as OpenBody["basis"],
    source: form.source as OpenBody["source"],
    evidence_reference: form.evidenceReference.trim(),
  };
  return form.basis === "estimated" ? { ...body, earliest_possible_at: instantOf(form.earliestPossibleAt) } : body;
}

// ------------------------------------------------------------------------ the assessment
export interface AssessForm {
  /** "yes", "no" or blank for not chosen. */
  readonly harm: string;
  readonly rationaleReference: string;
  /** Blank means not yet established, which is never zero. */
  readonly affectedCount: string;
}

export const EMPTY_ASSESS: AssessForm = { harm: "", rationaleReference: "", affectedCount: "" };

export function assessProblems(form: AssessForm): readonly string[] {
  const problems: string[] = [];
  if (form.harm !== "yes" && form.harm !== "no") {
    problems.push("Say whether the breach is likely to result in significant harm. It is your judgement to record.");
  }
  if (!IDENTIFIER.test(form.rationaleReference.trim())) {
    problems.push("Give a reference to where the reasoning is written, with no spaces and no reasoning itself.");
  }
  const count = form.affectedCount.trim();
  if (count !== "" && !/^\d+$/.test(count)) {
    problems.push("Give the number affected as a whole number, or leave it blank if it is not yet known.");
  }
  return problems;
}

export function assessBody(form: AssessForm): AssessBody {
  const count = form.affectedCount.trim();
  return {
    significant_harm: form.harm === "yes",
    rationale_reference: form.rationaleReference.trim(),
    affected_count: count === "" ? null : Number(count),
  };
}

// ------------------------------------------------------------------------- a notification
/** Everything wrong with the moment a notification was made. */
export function notifiedProblems(local: string, now: Date): readonly string[] {
  const at = instantOf(local);
  if (at === null) {
    return ["Give the date and time the notification was made."];
  }
  return new Date(at).getTime() > now.getTime() ? ["A notification cannot be recorded in the future."] : [];
}

export function notifiedBody(local: string): NotifiedBody {
  return { at: instantOf(local) };
}

// --------------------------------------------------------------------------- an exception
export interface ExceptionForm {
  readonly ground: string;
  readonly rationaleReference: string;
}

export const EMPTY_EXCEPTION: ExceptionForm = { ground: "", rationaleReference: "" };

export function exceptionProblems(form: ExceptionForm): readonly string[] {
  const problems: string[] = [];
  if (!(EXCEPTION_GROUNDS as readonly string[]).includes(form.ground)) {
    problems.push("Choose the ground the decision not to notify the individuals is filed under.");
  }
  if (!IDENTIFIER.test(form.rationaleReference.trim())) {
    problems.push("Give a reference to where the decision is reasoned, with no spaces and no reasoning itself.");
  }
  return problems;
}

export function exceptionBody(form: ExceptionForm): ExceptionBody {
  return { ground: form.ground as ExceptionBody["ground"], rationale_reference: form.rationaleReference.trim() };
}

// ------------------------------------------------------------------------------- a case
/** Where one obligation stands, in words. `at` renders an instant the page's way. */
export function obligationSentence(one: Obligation, at: (instant: string) => string): string {
  const what = `${labelOf(OBLIGATION_LABELS, one.kind)}, ${labelOf(BASIS_LABELS, one.basis)}`;
  const due = one.due_before === null ? "no deadline can be computed yet" : `due before ${at(one.due_before)}`;
  const flags = [
    one.satisfied ? (one.satisfied_late ? "done, late" : "done") : one.overdue ? "overdue" : "open",
    one.out_of_order ? "done out of order" : "",
  ].filter((flag) => flag !== "");
  return `${what}: ${due}; ${flags.join(", ")}.`;
}

/** Whether a case still takes steps. A closed case is a record. */
export function isOpen(one: Breach): boolean {
  return one.closed_at === null;
}
