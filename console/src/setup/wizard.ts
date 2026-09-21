/**
 * The setup wizard's screens as this console draws them, copied from `brain.setup_wizard`.
 *
 * **A copy, and checked against the original on every run.** The wizard is defined once, in
 * Python, and nothing serves it over HTTP: `POST /setup/appointment` takes the finished answers
 * and no route describes the screens. So the console carries the screen order, each question's
 * name, whether it is required, whether it is secret, its length ceiling and its closed list of
 * choices, and `tests/first-run.test.tsx` reads every one of those back out of
 * `src/brain/setup_wizard.py`, and every sentence below out of `brain.locale.MESSAGES`, so a
 * screen added or a question renamed there fails here rather than posting answers the route
 * drops. Rejected: a route that serves the wizard's shape. It is a change to `src/brain`, and the
 * shape is a fact about the code at one commit, which is exactly what a source-reading test
 * checks without a server.
 *
 * **Nothing here validates an answer.** No required check, no address shape, no list
 * membership. `brain.setup_wizard.problems_with` is the one judge and its findings come back as
 * a 422 by step, field and catalogue key; a second copy of the rules in a browser is a second
 * place for them to be subtly wrong, and the copy that disagrees is the one a person meets
 * first. The length ceiling is carried only as the input's own `maxLength`, so a paste stops
 * where the server would refuse it.
 *
 * **English only, and that is a gap rather than a decision.** `brain.locale.MESSAGES` carries
 * every one of these in two languages. This console has no language selection anywhere, so
 * the English column is the one copied.
 *
 * Task ids: M42.5.14
 */

import type { components } from "../api/schema";

/** The wizard's step identifiers, exactly as the API document spells them. */
export type StepKey = components["schemas"]["StepId"];

/** What `POST /setup/appointment` takes. */
export type AppointmentAsked = components["schemas"]["AppointmentAsked"];
/** What it answers on success. */
export type AppointedView = components["schemas"]["AppointedView"];
/** What it answers when the answers have problems, with nobody appointed. */
export type ProblemsView = components["schemas"]["ProblemsView"];
/** What it answers when the running install does not carry a setting, with nobody appointed. */
export type UnkeptView = components["schemas"]["UnkeptView"];
/** What `POST /setup/sign-in` takes beside the token. */
export type FinishAsked = components["schemas"]["FinishAsked"];
/** What it answers on success. */
export type SignInView = components["schemas"]["SignInView"];

/**
 * Where first run is drawn in this console. Not `/setup`, because `/setup/appointment` and
 * `/setup/sign-in` are the API's, and a reverse proxy routing `/setup` to the application would
 * then swallow the page or the page's address would shadow the routes. Not a registered
 * Keycloak value either: the callback returns here through the pending sign-in's `returnTo`.
 */
export const FIRST_RUN_PATH = "/first-run";

/** Where the appointment is served, outside the API prefix: `brain.setup_routes.APPOINTMENT_PATH`. */
export const APPOINTMENT_PATH = "/setup/appointment";

/** Where the finishing screen is served: `brain.sign_in_routes.FINISH_PATH`. */
export const FINISH_PATH = "/setup/sign-in";

/** `brain.setup_wizard.MAX_ANSWER_CHARS`. */
export const MAX_ANSWER_CHARS = 200;

/** `brain.setup_wizard.MAX_KEY_CHARS`, for a pasted provider key. */
export const MAX_KEY_CHARS = 1000;

/** One question on one screen. */
export interface Question {
  /** The field name the route reads, and the suffix of its catalogue label key. */
  readonly name: string;
  /** `field.<name>.label` in English. */
  readonly label: string;
  /** False for a question whose need depends on another answer. */
  readonly required: boolean;
  /** True for an answer the review screen never repeats back. */
  readonly secret: boolean;
  /** The longest the route accepts. */
  readonly maxChars: number;
  /** The closed list, when the question has one, in the order the wizard declares it. */
  readonly choices: readonly string[] | null;
}

/** One screen that asks something. */
export interface Screen {
  readonly key: StepKey;
  /** `setup.step.<key>.title` in English. */
  readonly title: string;
  readonly questions: readonly Question[];
  /** Declared on the wizard rather than derived from every question being optional. */
  readonly skippable: boolean;
}

function question(
  name: string,
  label: string,
  options: Partial<Omit<Question, "name" | "label">> = {},
): Question {
  return Object.freeze({
    name,
    label,
    required: options.required ?? true,
    secret: options.secret ?? false,
    maxChars: options.maxChars ?? MAX_ANSWER_CHARS,
    choices: options.choices ?? null,
  });
}

/**
 * Every screen that asks something, in the wizard's order.
 *
 * `review` and `finish` ask nothing and are drawn by the page rather than listed here; their
 * titles are below. The staff sources are `STAFF_SOURCE_BROKERS`' keys, the profiles are
 * `MODEL_PROFILES`, and the providers are `brain.ops.provider_keys.PROVIDER_SLOTS`' slugs.
 */
export const SCREENS: readonly Screen[] = Object.freeze([
  {
    key: "setup_code",
    title: "Enter the setup code",
    questions: [question("setup_code", "Setup code", { secret: true })],
    skippable: false,
  },
  {
    key: "company",
    title: "Your company",
    questions: [
      question("company_name", "Company name"),
      question("product_name", "What your staff will call this system", { required: false }),
      question("web_address", "Web address of this system"),
      question("logo_url", "Web address of your logo", { required: false }),
    ],
    skippable: false,
  },
  {
    key: "administrator",
    title: "The first administrator",
    questions: [question("full_name", "Full name"), question("work_address", "Work email address")],
    skippable: false,
  },
  {
    key: "data_steward",
    title: "The data steward",
    questions: [
      question("steward_full_name", "The data steward's full name", { required: false }),
      question("steward_work_address", "The data steward's work email address", {
        required: false,
      }),
      question("steward_is_administrator", "The first administrator is the data steward as well", {
        required: false,
        choices: ["no", "yes"],
      }),
    ],
    skippable: false,
  },
  {
    key: "staff_source",
    title: "Your staff list",
    questions: [
      question("staff_source", "Where your staff list comes from", {
        choices: ["google_workspace", "microsoft_entra", "lark", "spreadsheet"],
      }),
      question("staff_source_location", "Where that list is: your domain, your tenant, or which Lark", {
        required: false,
      }),
    ],
    skippable: false,
  },
  {
    key: "model_provider",
    title: "How questions are answered",
    questions: [
      question("model_profile", "Where questions are answered", { choices: ["local", "hosted"] }),
      question("model_provider", "Model provider", {
        required: false,
        choices: ["anthropic", "openai", "moonshot", "deepseek"],
      }),
      question("provider_key", "Key from your provider account", {
        required: false,
        secret: true,
        maxChars: MAX_KEY_CHARS,
      }),
    ],
    skippable: false,
  },
  {
    key: "connections",
    title: "Data sources",
    questions: [question("connections", "Data sources to connect later", { required: false })],
    skippable: true,
  },
] satisfies Screen[]);

/**
 * Said under the data steward screen, beside its questions, and not a catalogue sentence: it is
 * what the choice means rather than a problem with an answer. See
 * `brain.setup_wizard.THE_STEWARD_IS_ANOTHER_PERSON_UNLESS_SOMEBODY_SAYS_OTHERWISE`.
 */
export const DATA_STEWARD_EXPLAINED =
  "The data steward is the person every read of your company's data begins with. They can grant " +
  "those reads to other people, and every source you connect is granted to them. The administrator " +
  "runs the system and reads none of your data. Name somebody else, or answer yes to make the " +
  "administrator the data steward as well, which puts both in one account.";

/** `setup.step.review.title`. */
export const REVIEW_TITLE = "Check this before anything is written";

/** `setup.step.finish.title`. */
export const FINISH_TITLE = "Setup is complete";

/**
 * Every catalogue sentence the route can name in a problem, and the review screen's states.
 *
 * Keyed by catalogue key because that is what a 422 carries. Checked against
 * `brain.locale.MESSAGES` both ways, so a key the wizard gains fails a test.
 */
export const MESSAGES: Readonly<Record<string, string>> = Object.freeze({
  "setup.error.blank": "This is needed before setup can continue",
  "setup.error.too_long": "That is longer than this screen accepts. Shorten it and try again",
  "setup.error.unknown_choice": "Choose one of the options shown",
  "setup.error.not_absolute": "Enter a whole web address, beginning with http:// or https://",
  "setup.error.not_an_address": "Enter the work email address this person signs in with",
  "setup.error.not_a_source_name":
    "Use each source's short name, in lower case, separated by commas",
  "setup.error.provider_needed":
    "Choose which provider answers questions, or keep them on your own hardware",
  "setup.error.key_needed": "This provider needs a key from your own account with them",
  "setup.error.location_needed": "Say where this list is, so it can be read",
  "setup.error.location_unusable": "Enter only the domain, the tenant ID, or larksuite.com or feishu.cn",
  "setup.error.location_not_wanted": "A spreadsheet is read from the file itself, so leave this empty",
  "setup.error.key_not_wanted":
    "Nothing would use a key here, because questions stay on your own hardware",
  "setup.error.steward_needed":
    "Name the data steward here, or answer yes below if the administrator is the steward",
  "setup.error.steward_not_wanted": "Leave this empty, because the administrator is the data steward",
  "setup.error.steward_is_administrator":
    "That is the administrator's address. Name somebody else, or answer yes below",
  "setup.error.refused": "That code was not accepted. Check the line the installer printed",
  "setup.review.supplied": "Supplied",
  "setup.review.not_given": "Not given",
  "setup.review.skipped": "Skipped",
});

/**
 * A key the console has no sentence for. Shown rather than the key itself, so a wizard that
 * gained a message this build lacks still says something a person can act on.
 */
export const UNKNOWN_PROBLEM = "Check this answer";

/** The sentence for one catalogue key. */
export function messageFor(key: string): string {
  return MESSAGES[key] ?? UNKNOWN_PROBLEM;
}

/**
 * The one sentence every refusal before the answers is shown as.
 *
 * `brain.setup_routes.EVERY_REFUSAL_BEFORE_THE_ANSWERS_IS_ONE_ANSWER` makes a finished
 * install, a wrong, blank or expired code, an install with no code and a lost race one 404 with
 * one body. The console keeps that property by not reading the body at all: whatever the API's
 * message says, this is what is drawn, and it names no reason. "Check the code" would be the
 * helpful version, and on a finished install it would tell whoever found the address that the
 * code was the thing standing in their way.
 */
export const SETUP_REFUSED_MESSAGE =
  "Setup cannot continue from here with what was sent. Nothing was written.";

/** Why the 404 is drawn from a constant rather than from the response. */
export const A_SETUP_REFUSAL_NAMES_NO_REASON =
  "Every refusal before the answers is one 404 on the server, and a console that chose a " +
  "sentence from the body, the status or the step would rebuild the reasons the server spent " +
  "a route making indistinguishable. The 404 is one constant sentence and nothing else.";

/** Whether a screen keeps anything past the visit, which is `Step.stores`. */
export function stores(screen: Screen): boolean {
  return screen.questions.some((one) => !one.secret);
}

/** What a person has typed so far, by screen and field. */
export type Answers = Readonly<Partial<Record<StepKey, Readonly<Record<string, string>>>>>;

/**
 * The appointment body: the code, every storing screen not skipped, and the skipped ones.
 *
 * Every question of a screen is sent, blank ones included, so an unvisited screen comes back
 * as a blank problem against each required field rather than as one "not given" against the
 * screen: the first says which box to fill. The setup code's own screen is never in `answers`,
 * because it stores nothing and the route does not read it there.
 */
export function appointmentBody(
  setupCode: string,
  answers: Answers,
  skipped: ReadonlySet<StepKey>,
): AppointmentAsked {
  const sent: Record<string, Record<string, string>> = {};
  for (const screen of SCREENS) {
    if (!stores(screen) || skipped.has(screen.key)) {
      continue;
    }
    const given = answers[screen.key] ?? {};
    sent[screen.key] = Object.fromEntries(
      screen.questions.map((one) => [one.name, given[one.name] ?? ""]),
    );
  }
  return {
    setup_code: setupCode,
    answers: sent,
    skipped: SCREENS.filter((screen) => skipped.has(screen.key)).map((screen) => screen.key),
  };
}

/** The finishing screen's body. The token travels as the bearer header, never in here. */
export function finishBody(setupCode: string, principalId: string): FinishAsked {
  return { setup_code: setupCode, principal_id: principalId };
}

/** Problems grouped for drawing: by `step.field`, and by step for a problem with no field. */
export interface Placed {
  readonly byField: Readonly<Record<string, readonly string[]>>;
  readonly byStep: Readonly<Partial<Record<StepKey, readonly string[]>>>;
}

/** Where each problem is drawn. A field the screen does not ask is drawn against the screen. */
export function placeProblems(problems: ProblemsView["problems"]): Placed {
  const byField: Record<string, string[]> = {};
  const byStep: Partial<Record<StepKey, string[]>> = {};
  for (const one of problems) {
    const screen = SCREENS.find((candidate) => candidate.key === one.step);
    const asked = screen?.questions.some((candidate) => candidate.name === one.field) ?? false;
    const sentence = messageFor(one.key);
    if (asked) {
      (byField[`${one.step}.${one.field}`] ??= []).push(sentence);
    } else {
      (byStep[one.step] ??= []).push(sentence);
    }
  }
  return { byField, byStep };
}
