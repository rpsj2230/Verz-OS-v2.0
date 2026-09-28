/**
 * A form that writes is judged before anything is sent, and a form sent blank says what to fill in.
 *
 * `docs/admin-console.md`: "Validation happens before the write, and an error says what to do about
 * it." Every file under `src/pages` and `src/components` that holds both a write and a form is read
 * out of the source, and every form in it is named below. Each is opened on its page with the
 * page's usual answers, every field in it emptied, and submitted, and any confirmation that opens is
 * pressed. Nothing may be sent but a read. A form that writes must also not have asked to be
 * confirmed, and must have said something of at least three words it was not saying before.
 *
 * **What it found on 2026-09-17.** Registering a webhook subscriber with every field empty opened a
 * confirmation asking to register "this subscriber" at "this address", and pressing it sent the
 * empty registration to the API. The API refused it in good words, but only after a person had
 * agreed to it. Blank fields are now said beside their fields first, in the API's own sentences.
 * And the classification review, on a document with one column, answered every submission with
 * "schema is invalid" and an ajv path, because a JSON Schema enum may not be empty.
 *
 * **Blank is the case held, not every case.** A value of the wrong shape is the API's to judge and
 * its sentences to say, and several of these forms deliberately leave it there rather than keeping
 * a second copy of a rule. What no form may do is send, or ask to send, nothing at all.
 *
 * Task ids: M27.8.5
 */

import { fireEvent } from "@testing-library/react";
import ts from "typescript";
import { beforeAll, describe, expect, test } from "vitest";
import { PAGES } from "./support/pageCases";
import { mountIn } from "./support/screenStates";
import { consoleSourcePaths, parseConsoleSource } from "./support/typescript";
import { CONTROL_DIRECTORIES, everyWrite } from "./support/writes";

interface FormCase {
  /** The page case it is opened on. */
  readonly pattern: string;
  /** A button pressed first, by its text or the start of its accessible name, when the form is behind one. */
  readonly opener?: string;
  /** Which form on the page, in document order, once the opener has been pressed. */
  readonly index: number;
  /** Whether its submit leads to a write, or it only narrows or navigates. */
  readonly writes: boolean;
}

/** Every form in a file that also holds a write, by file. The count is checked against the source. */
const FORMS: Readonly<Record<string, readonly FormCase[]>> = {
  // The connect form is the first form on the staff sources page; the credential form follows it.
  "src/components/ConnectStaffSource.tsx": [{ pattern: "/staff_sources", index: 0, writes: true }],
  "src/components/DataStewardCard.tsx": [{ pattern: "/people", index: 1, writes: true }],
  // Index 0 is the ledger's filter bar, which only narrows; index 1 checks a published head.
  "src/pages/Audit.tsx": [
    { pattern: "/audit", index: 0, writes: false },
    { pattern: "/audit", index: 1, writes: true },
  ],
  // The naming form, then one column's editor (a rule, or a mark for an uploaded table); and on
  // the page with nothing named, the naming form and then the upload.
  "src/pages/Classification.tsx": [
    { pattern: "/classification/:entity/:column", index: 0, writes: false },
    { pattern: "/classification/:entity/:column", index: 1, writes: true },
    { pattern: "/classification", index: 1, writes: true },
  ],
  "src/pages/DataTransfer.tsx": [{ pattern: "/import-export", index: 0, writes: true }],
  // Index 0 on every page drawing a long list is `components/ListControls.tsx`' search form, which
  // is not in the page's file and sends nothing but a read. Then the lead, a team's add, creating a
  // team, creating a department and drawing a scope. The rename form is one form in the source,
  // drawn for a department or a team, and opens above the lead's form; the department's stands for
  // both, and tests/govern-people-pages.test.tsx submits the team's blank.
  "src/pages/Departments.tsx": [
    { pattern: "/departments", index: 1, writes: true },
    { pattern: "/departments", index: 2, writes: true },
    { pattern: "/departments", index: 3, writes: true },
    { pattern: "/departments", index: 4, writes: true },
    { pattern: "/departments", index: 5, writes: true },
    { pattern: "/departments", opener: "Rename department", index: 1, writes: true },
  ],
  "src/pages/Elevation.tsx": [{ pattern: "/elevation", index: 0, writes: true }],
  // The Add a document card sits above the library, so its form comes before the list's search.
  "src/pages/Knowledge.tsx": [{ pattern: "/library", index: 0, writes: true }],
  // After Add a document: a web page by its link, then many documents at once.
  "src/pages/KnowledgeIntake.tsx": [
    { pattern: "/library", index: 1, writes: true },
    { pattern: "/library", index: 2, writes: true },
  ],
  // The lifecycle cards sit between the intake cards and the library. Opening a document draws
  // its four acts' forms above the capture form, in the order the card lists them; unopened,
  // the capture form and a solution's decision follow the two intake forms.
  "src/components/KnowledgeLifecycle.tsx": [
    { pattern: "/library", opener: "Open", index: 3, writes: true },
    { pattern: "/library", opener: "Open", index: 4, writes: true },
    { pattern: "/library", opener: "Open", index: 5, writes: true },
    { pattern: "/library", opener: "Open", index: 6, writes: true },
    { pattern: "/library", index: 3, writes: true },
    { pattern: "/library", index: 4, writes: true },
  ],
  "src/pages/AccessRequests.tsx": [{ pattern: "/access-requests", index: 0, writes: true }],
  // Index 0 on the Routing page is the matrix's search form, which only narrows. On a step's page its
  // numbers and then where it sits follow; the golden question and the residency rule come after.
  "src/pages/models/RungEditor.tsx": [
    { pattern: "/routing/:rungId", index: 1, writes: true },
    { pattern: "/routing/:rungId", index: 2, writes: true },
  ],
  "src/pages/models/GoldenQuestions.tsx": [{ pattern: "/routing", index: 1, writes: true }],
  // Add a step opens above the matrix, so it is then the first form.
  "src/pages/models/AddStep.tsx": [{ pattern: "/routing", opener: "Add a step", index: 0, writes: true }],
  // Under Advanced after the golden question: the residency rule, and a level's numbers once opened,
  // which draws above the residency form.
  "src/components/RoutingSettings.tsx": [
    { pattern: "/routing", index: 2, writes: true },
    { pattern: "/routing", opener: "Edit numbers", index: 2, writes: true },
  ],
  // Adding a provider opens above the list, whose search form then follows it.
  "src/pages/models/AddProvider.tsx": [{ pattern: "/models", opener: "Add a provider", index: 0, writes: true }],
  // A provider's Profile: the terms form, and the key form above it once Replace key is pressed.
  "src/pages/models/ProviderProfile.tsx": [{ pattern: "/models/:provider/:view", index: 0, writes: true }],
  "src/components/ProviderKeyForm.tsx": [{ pattern: "/models/:provider/:view", opener: "Replace key", index: 0, writes: true }],
  "src/pages/credentials/SetValueForm.tsx": [{ pattern: "/credentials/:family/:name/:view", index: 0, writes: true }],
  // The Profile is a view at its own address, so the pin's form is on that page case with no opener.
  "src/components/AgentModelPin.tsx": [{ pattern: "/agents/:agentId/:tab", index: 0, writes: true }],
  // A model's price opens on its row in the prices card, above the register's forms (M27.12.5).
  // The prices card is under the providers list, after the list's search form.
  "src/components/ModelPrices.tsx": [{ pattern: "/models", opener: "Set price", index: 1, writes: true }],
  "src/pages/Notifications.tsx": [
    { pattern: "/notifications", index: 0, writes: true },
    { pattern: "/notifications", index: 1, writes: true },
    { pattern: "/notifications", index: 2, writes: true },
  ],
  // The grant and pack forms of an open subject, then the grant to several, which is drawn under
  // the list once it is opened and so sits after the list's search.
  "src/pages/People.tsx": [
    { pattern: "/people/:subject", index: 1, writes: true },
    { pattern: "/people/:subject", index: 2, writes: true },
    { pattern: "/people", opener: "Grant to several people", index: 1, writes: true },
  ],
  "src/pages/Prompts.tsx": [{ pattern: "/prompts", opener: "Edit instructions", index: 0, writes: true }],
  "src/pages/RequirementChecks.tsx": [{ pattern: "/requirement-checks", index: 0, writes: true }],
  // One form in the source, drawn twice (appoint and deputy); the first stands for both.
  "src/pages/RoleControls.tsx": [{ pattern: "/roles", index: 0, writes: true }],
  // After the appointment and deputy forms: the directory group mapping.
  "src/pages/GroupRules.tsx": [{ pattern: "/roles", index: 2, writes: true }],
  "src/pages/Retention.tsx": [
    { pattern: "/retention", index: 0, writes: true },
    { pattern: "/retention", index: 1, writes: true },
    { pattern: "/retention", index: 2, writes: true },
  ],
  "src/pages/SignInLinks.tsx": [{ pattern: "/sign-in-links", index: 1, writes: true }],
  // Index 1 is the registration until an account's Issue a key opens its form above it.
  "src/pages/ServiceAccounts.tsx": [
    { pattern: "/service-accounts", index: 1, writes: true },
    { pattern: "/service-accounts", opener: "Issue a key", index: 1, writes: true },
  ],
  "src/pages/StaffSources.tsx": [{ pattern: "/staff_sources", index: 1, writes: true }],
  // The naming form, then the four forms of the one open case, then the form that opens a case.
  "src/pages/Compliance.tsx": [
    { pattern: "/compliance", index: 0, writes: true },
    { pattern: "/compliance", index: 1, writes: true },
    { pattern: "/compliance", index: 2, writes: true },
    { pattern: "/compliance", index: 3, writes: true },
    { pattern: "/compliance", index: 4, writes: true },
    { pattern: "/compliance", index: 5, writes: true },
  ],
  // Index 0 is the bound people's search bar, which only narrows; then the webhook channel's set-up
  // and its test message. The Slack card, not received, draws no form.
  "src/pages/Channels.tsx": [
    { pattern: "/channels", index: 1, writes: true },
    { pattern: "/channels", index: 2, writes: true },
  ],
  "src/pages/Webhooks.tsx": [
    { pattern: "/webhooks", index: 0, writes: false },
    { pattern: "/webhooks", opener: "Replace secret", index: 1, writes: true },
    { pattern: "/webhooks", index: 1, writes: true },
  ],
};

/**
 * Files holding a write and a form that are not opened here, and why.
 *
 * Checked, not trusted: an entry for a file that no longer holds both fails the first test.
 */
const JUDGED_ELSEWHERE: Readonly<Record<string, string>> = {
  "src/components/ConnectSource.tsx":
    "Its form is inside the Connect a source drawer, which is drawn outside the page's main landmark " +
    "these cases read, and inside first run, which is mounted outside the session guard. " +
    "tests/connectors-page.test.tsx opens the drawer, submits it blank, and holds that no " +
    "confirmation opens, nothing is sent and the API's blank sentences are said beside the fields.",
  "src/pages/connectors/SourceActs.tsx":
    "The edit and the key forms are inside drawers opened from a source's Manage menu, outside the " +
    "main landmark these cases read. tests/connectors-page.test.tsx submits each blank and holds " +
    "that no confirmation opens, nothing is sent, and the API's own blank sentence is said.",
  "src/components/ConnectLark.tsx":
    "Its Test and Save buttons stay disabled until an App ID and an App Secret are typed, so a " +
    "blank form cannot be sent. What is typed is judged by the API before anything reaches Lark: " +
    "input_problems answers 422 by field for a malformed App ID, secret or Base link, which " +
    "tests/unit/test_lark_connect.py holds with nothing sent to " +
    "the fake Lark server, and tests/lark-connect.test.tsx drives the form.",
  "src/pages/Settings.tsx":
    "Each editable row's form sends one value, from a confirmation, and the API judges it with " +
    "setting_problem before anything is written, answering 422 with a sentence drawn beside the field. " +
    "tests/unit/test_settings_routes.py holds a refused value writing no row; the page case draws " +
    "no editable row, so no form is opened here.",
  "src/pages/skills/SkillForms.tsx":
    "Every form here opens behind a press the page cases do not make: Add a skill's drawer, Edit as a " +
    "new version, or the Profile's assign and categories cards. Each says what it accepts above its " +
    "fields, and a blank one cannot be sent: Add stays disabled until packageProblem accepts a package, " +
    "Import until importProblem accepts the repository and commit or the address, and Save until the " +
    "edit has text, which tests/skills-page.test.tsx holds for Add. The assign form only opens a " +
    "confirmation naming an agent the API listed.",
  "src/pages/Ask.tsx":
    "The question form cannot be sent blank by a person: its only submit button is disabled until " +
    "askBody accepts the text, and the field's maxLength stops a question longer than the route " +
    "takes. The second test below holds the button disabled for an empty question.",
  "src/pages/FirstRun.tsx":
    "The wizard's step forms move between steps and send nothing. Its one write is the review " +
    "screen's button after every step, and the API's problems are drawn beside the fields they " +
    "name, which tests/first-run.test.tsx holds in 'problems with the answers are drawn beside the " +
    "fields they name'. It is mounted outside the session guard behind a sign-in these cases do not make.",
};

/** How many `<form>` and `<SchemaForm>` elements a file writes. */
function formsWrittenIn(file: string): number {
  const source = parseConsoleSource(file);
  let count = 0;
  const visit = (node: ts.Node): void => {
    if (
      (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) &&
      ["form", "SchemaForm"].includes(node.tagName.getText(source))
    ) {
      count += 1;
    }
    node.forEachChild(visit);
  };
  source.forEachChild(visit);
  return count;
}

/** Empty every field a person types or chooses in. Boxes to tick are left as they are. */
function blank(form: HTMLFormElement): void {
  for (const field of form.querySelectorAll<HTMLInputElement>("input, textarea, select")) {
    if (["checkbox", "radio", "hidden", "submit", "button"].includes(field.type)) {
      continue;
    }
    fireEvent.change(field, { target: { value: "" } });
  }
}

function pressFirst(root: Element, label: string): void {
  const found = [...root.querySelectorAll("button")].find(
    (one) => one.textContent === label || (one.getAttribute("aria-label") ?? "").startsWith(label),
  );
  if (found === undefined) {
    throw new Error(`No button named ${label}.`);
  }
  fireEvent.click(found);
}

beforeAll(async () => {
  await import("../src/pages/Matrix");
  await import("../src/pages/Provider");
  await import("../src/pages/Classification");
  await import("../src/pages/People");
}, 120_000);

const CASES = Object.entries(FORMS).flatMap(([file, forms]) =>
  forms.map((one) => [`${file} form ${String(one.index)}${one.opener ? ` behind ${one.opener}` : ""}`, one] as const),
);

describe("a form that writes is judged before it sends", () => {
  test("every form in a file that also holds a write is opened here or judged elsewhere with a reason", () => {
    // What breaks if this is deleted: a form added to a page that writes, which nobody submits
    // blank, because the cases below are a list somebody typed. The list is compared with the
    // source both ways, and a stale excuse fails as loudly as a missing case.
    const writing = new Set(everyWrite().map((write) => write.file));
    const holding = CONTROL_DIRECTORIES.flatMap((directory) => consoleSourcePaths(directory)).filter(
      (file) => writing.has(file) && formsWrittenIn(file) > 0,
    );
    expect([...Object.keys(FORMS), ...Object.keys(JUDGED_ELSEWHERE)].sort()).toEqual([...holding].sort());
    for (const [file, forms] of Object.entries(FORMS)) {
      // Keyed by the page as well: the same index on two pages is two forms, which the
      // classification screen has since its upload was drawn where nothing is named.
      const opened = new Set(
        forms.map((one) => `${one.pattern} ${one.opener ?? ""}#${String(one.index)}`),
      );
      expect(opened.size, `${file} names one form twice`).toBe(forms.length);
      expect(forms.length, `${file} writes ${String(formsWrittenIn(file))} forms`).toBe(formsWrittenIn(file));
    }
    for (const [file, reason] of Object.entries(JUDGED_ELSEWHERE)) {
      expect(reason.split(" ").length, `${file} is excused without a reason`).toBeGreaterThan(10);
    }
  }, 60_000);

  test("the question form cannot be pressed while the question is empty", async () => {
    // What breaks if this is deleted: the reason the ask page is excused above stops being true.
    const page = PAGES["/ask"];
    if (page === undefined) {
      throw new Error("/ask has no page case.");
    }
    const mounted = await mountIn("/ask", page.address, { kind: "answered", answers: {} });
    const submit = mounted.root.querySelector<HTMLButtonElement>("form button[type=submit]");
    expect(submit?.disabled).toBe(true);
    fireEvent.change(mounted.root.querySelector("textarea") as HTMLTextAreaElement, { target: { value: "Which quotes?" } });
    expect(submit?.disabled).toBe(false);
  }, 30_000);

  test.each(CASES)("%s, submitted blank, sends no write and says what to fill in", async (_, one) => {
    // What breaks if this is deleted: a blank registration, grant, hold or export that opens a
    // confirmation about nothing or reaches the API, and a refusal a person meets only after they
    // agreed to it. A form that only narrows a list is held to the first half.
    const page = PAGES[one.pattern];
    if (page === undefined) {
      throw new Error(`${one.pattern} has no page case.`);
    }
    const mounted = await mountIn(one.pattern, page.address, { kind: "answered", answers: page.answers });
    if (one.opener !== undefined) {
      pressFirst(mounted.root, one.opener);
    }
    const opened = await mounted.reread();
    const form = opened.root.querySelectorAll("form")[one.index];
    if (form === undefined) {
      throw new Error(`${one.pattern} has no form at ${String(one.index)}.`);
    }
    const before = new Set(opened.sentences);
    const sentBefore = opened.sent.length;

    blank(form);
    fireEvent.submit(form);
    let after = await mounted.reread();
    const confirmation = after.root.querySelector(".confirm");
    if (confirmation !== null) {
      const buttons = confirmation.querySelectorAll("button");
      fireEvent.click(buttons[buttons.length - 1] as HTMLButtonElement);
      after = await mounted.reread();
    }

    const writes = after.sent.slice(sentBefore).filter((sent) => sent.method !== "GET");
    expect(writes.map((sent) => `${sent.method} ${sent.path}`)).toEqual([]);
    if (one.writes) {
      expect(confirmation, "a blank form asked to be confirmed").toBeNull();
      const said = [...after.sentences].filter((sentence) => !before.has(sentence) && sentence.split(" ").length >= 3);
      expect(said).not.toEqual([]);
    }
  }, 30_000);
});
