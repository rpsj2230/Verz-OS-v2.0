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
 * Task ids: M27.8.5, M27.15.73
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
  // An API's specification and mapping, the one form on Add an API, above its review list.
  "src/pages/connectors/CustomConnectorsPage.tsx": [{ pattern: "/connectors/new-api", index: 0, writes: true }],
  "src/components/DataStewardCard.tsx": [{ pattern: "/people", index: 1, writes: true }],
  // A memory's edit opens in place on My workspace, the first form on the page once opened.
  "src/pages/MyWorkspace.tsx": [{ pattern: "/me", opener: "Edit", index: 0, writes: true }],
  // The one form checks a published head; the ledger's filters are on the Audit log's own page.
  "src/pages/audit/VerifyPage.tsx": [{ pattern: "/audit/verify", index: 0, writes: true }],
  // The one form names a trace and says why; sending it writes the row recording who read it.
  "src/pages/audit/TracePage.tsx": [{ pattern: "/audit/trace", index: 0, writes: true }],
  // One column's editor (a rule, or a mark for an uploaded table), the one form on a table's page;
  // and on the module's first page, the naming form and then the upload.
  "src/pages/classification/ClassificationPage.tsx": [
    { pattern: "/classification/:entity/:column", index: 0, writes: true },
    { pattern: "/classification", index: 0, writes: false },
    { pattern: "/classification", index: 1, writes: true },
  ],
  "src/pages/operations/DataTransferPage.tsx": [{ pattern: "/import-export", index: 0, writes: true }],
  // One knob's figure, behind its row's Change button on Rate limits.
  "src/pages/operations/LimitSettings.tsx": [{ pattern: "/limits", opener: "Change", index: 0, writes: true }],
  // Index 0 on every page drawing a long list is `components/ListControls.tsx`' search form, which
  // is not in the page's file and sends nothing but a read. Then the lead, a team's add, creating a
  // team, creating a department and drawing a scope. The rename form is one form in the source,
  // drawn for a department or a team, and opens above the lead's form; the department's stands for
  // both, and tests/govern-people-pages.test.tsx submits the team's blank.
  // The Routing page draws the matrix whole, with no search form, so the golden question is first.
  "src/pages/models/GoldenQuestions.tsx": [{ pattern: "/routing", index: 0, writes: true }],
  // Add a step opens above the matrix, so it is then the first form.
  "src/pages/models/AddStep.tsx": [{ pattern: "/routing", opener: "Add a step", index: 0, writes: true }],
  // Under Advanced after the golden question: the residency rule, and a level's numbers once opened,
  // which draws above the residency form.
  "src/components/RoutingSettings.tsx": [
    { pattern: "/routing", index: 1, writes: true },
    { pattern: "/routing", opener: "Edit numbers", index: 1, writes: true },
  ],
  // Adding a provider opens above the provider cards.
  "src/pages/models/AddProvider.tsx": [{ pattern: "/models", opener: "Add a provider", index: 0, writes: true }],
  // A provider's Profile: the terms form, and the key form above it once Replace key is pressed.
  "src/pages/models/ProviderProfile.tsx": [{ pattern: "/models/:provider/:view", index: 0, writes: true }],
  "src/components/ProviderKeyForm.tsx": [{ pattern: "/models/:provider/:view", opener: "Replace key", index: 0, writes: true }],
  "src/pages/credentials/SetValueForm.tsx": [{ pattern: "/credentials/:family/:name/:view", index: 0, writes: true }],
  // The Profile is a view at its own address, so the pin's form is on that page case with no opener.
  // The Permissions card draws the tools block's three choices (judged elsewhere) and then the
  // preview as a person in its footer, above the model card, so the preview is fourth and the pin
  // fifth.
  "src/components/AgentModelPin.tsx": [{ pattern: "/agents/:agentId/:tab", index: 3, writes: true }],
  "src/pages/agents/AgentCapabilities.tsx": [{ pattern: "/agents/:agentId/:tab", index: 2, writes: true }],
  // A person's Access view: the preview through an agent, under the grants, roles and placements.
  "src/pages/people/PersonPreview.tsx": [{ pattern: "/people/:personId/:view", index: 0, writes: true }],
  // The Dashboard opens first, and its one form is the monthly budget, drawn for a reader of
  // everybody's spend.
  "src/pages/agents/AgentSpend.tsx": [{ pattern: "/agents/:agentId", index: 0, writes: true }],
  // A model's price opens on its row in the prices card, under the providers and the matrix, which
  // draw no form of their own (M27.12.5).
  "src/components/ModelPrices.tsx": [{ pattern: "/models", opener: "Set price", index: 0, writes: true }],
  // The grant and pack forms of an open subject, then the grant to several, which is drawn under
  // the list once it is opened and so sits after the list's search.
  "src/pages/prompts/PromptsPage.tsx": [{ pattern: "/prompts", opener: "Edit instructions", index: 0, writes: true }],
  // The connect form is in a drawer, judged below; the credential form is the one form on the page.
  "src/pages/staff-sources/SyncCredential.tsx": [{ pattern: "/staff_sources", index: 0, writes: true }],
  // A channel's Profile is a view at its own address: its set-up form, then its test message.
  "src/pages/channels/ChannelProfile.tsx": [
    { pattern: "/channels/:name/:view", index: 0, writes: true },
    { pattern: "/channels/:name/:view", index: 1, writes: true },
  ],
};

/**
 * Files holding a write and a form that are not opened here, and why.
 *
 * Checked, not trusted: an entry for a file that no longer holds both fails the first test.
 */
const JUDGED_ELSEWHERE: Readonly<Record<string, string>> = {
  "src/pages/agents/AgentLeash.tsx":
    "Both forms are choices from lists the API sent, a setting and a rung, and a verdict from the " +
    "ledger's four; nothing is typed, so nothing can be sent blank, and Change is disabled until a " +
    "different rung is chosen. tests/agent-leash.test.tsx holds that every write is sent only from " +
    "its confirmation, and the leash block is inside the Profile, whose page case mounts no leash.",
  "src/pages/agents/AgentTools.tsx":
    "Its forms are choices from lists the API sent, a tool or a connector the reader may attach or " +
    "detach; nothing is typed, so nothing can be sent blank. tests/agent-tools.test.tsx holds that " +
    "every press is sent only from its confirmation, and the block is inside the Profile, whose page " +
    "case mounts it with nothing typed.",
  "src/pages/agents/AgentMemory.tsx":
    "The one form corrects a memory, opened from its row in the Memory section at its own address, " +
    "which no page case mounts. tests/agent-memory.test.tsx submits it blank and holds that nothing " +
    "is sent and what to type is said beside it, and a correction is sent only from its confirmation.",
  "src/pages/compliance/ComplianceActs.tsx":
    "Naming a person, opening a case and each step of a case are forms inside drawers opened from the " +
    "Compliance views and a case's own page, outside the main landmark these cases read. Each says what " +
    "its fields take before anything is sent, and tests/compliance-page.test.tsx submits the naming, " +
    "the opening, the assessment and a notification blank and holds that no confirmation opens and " +
    "nothing is sent.",
  "src/pages/compliance/EscalationQueues.tsx":
    "Naming who answers for an escalation queue is a form inside a drawer opened from the Escalation " +
    "queues view, outside the main landmark these cases read. It says what each field takes before " +
    "anything is sent, and tests/compliance-page.test.tsx submits it blank and holds that no " +
    "confirmation opens and nothing is sent.",
  "src/pages/retention/RetentionActs.tsx":
    "The hold, lift and erasure forms are inside drawers opened from the Legal holds and Erasure " +
    "requests views, outside the main landmark these cases read. Each says what its fields take before " +
    "anything is sent, and tests/retention-page.test.tsx submits the hold and the erasure blank and " +
    "holds that no confirmation opens, nothing is sent and what to change is said beside the fields.",
  "src/pages/review/ElevationActs.tsx":
    "The ask form is inside the Ask for access drawer opened from the page header, outside the main " +
    "landmark these cases read. It says what each field takes before anything is sent, and " +
    "tests/review-pages.test.tsx submits it blank and holds that no confirmation opens, nothing is sent " +
    "and each blank field is named beside it.",
  "src/pages/review/CertificationExport.tsx":
    "The export form is inside the drawer opened from the Access review header, outside the main " +
    "landmark these cases read. tests/review-pages.test.tsx submits it blank and holds that no " +
    "confirmation opens, nothing is sent and the reason and the reference are each said to be needed.",
  "src/pages/people/WorkEmail.tsx":
    "The work email form is inside the Add work email drawer opened from a person's Overview, outside " +
    "the main landmark these cases read. tests/people-access-pages.test.tsx submits it blank and holds " +
    "that nothing is sent and what to type is said beside the field.",
  "src/pages/access-requests/AccessRequestsPage.tsx":
    "The ask form is inside the Ask for access drawer opened from the page header, outside the main " +
    "landmark these cases read. tests/access-requests-page.test.tsx submits it blank and holds that " +
    "nothing is sent and the blank field is named beside it.",
  "src/pages/models/RungEditor.tsx":
    "A step's numbers and where it sits are two forms inside the step's drawer, opened at its own address " +
    "over the matrix and drawn outside the main landmark these cases read. tests/models-module.test.tsx " +
    "submits each blank and holds that no confirmation opens, nothing is sent, and what to fill in is " +
    "said beside the field.",
  "src/pages/requirement-checks/RecordDrawer.tsx":
    "The record form is inside a requirement's drawer, opened from its row and drawn outside the main " +
    "landmark these cases read. tests/requirement-checks-page.test.tsx submits it blank and holds that " +
    "nothing is sent and the outcome and the note are each told what to fill in beside the field.",
  "src/pages/webhooks/WebhookActs.tsx":
    "The registration and the secret replacement are inside drawers opened from the page header or a " +
    "subscriber's page, outside the main landmark these cases read. tests/webhooks-page.test.tsx submits " +
    "each blank and holds that no confirmation opens, nothing is sent, and the API's own blank sentence " +
    "is said beside each field.",
  "src/pages/notifications/RelayActs.tsx":
    "The relay, password and test message forms are inside drawers opened from the relay card, outside " +
    "the main landmark these cases read. tests/notifications-page.test.tsx submits each of the three blank " +
    "and holds that no confirmation opens, nothing is sent, and the API's own blank sentence is said " +
    "beside the field.",
  "src/components/ConnectSource.tsx":
    "Its form is inside the Connect a source drawer, which is drawn outside the page's main landmark " +
    "these cases read, and inside first run, which is mounted outside the session guard. " +
    "tests/connectors-page.test.tsx opens the drawer, submits it blank, and holds that no " +
    "confirmation opens, nothing is sent and the API's blank sentences are said beside the fields.",
  "src/pages/sessions/SignInLinksPage.tsx":
    "The link form is inside the Link a sign-in drawer opened from the page header, outside the " +
    "main landmark these cases read. tests/sign-in-links-page.test.tsx submits it blank and holds " +
    "that nothing is sent and a sentence saying what to enter is drawn beside each field.",
  "src/pages/agent-templates/AgentTemplateDetailPage.tsx":
    "The install form's fields are a name the template already fills in and a tick, and a blank name " +
    "installs under the template's own name, which the hint under it says before anything is sent. " +
    "Submitting opens the confirmation and sends nothing; tests/agent-templates.test.tsx holds that " +
    "the install is sent only from the confirmation, with the digest the page read.",
  "src/pages/service-accounts/AccountActs.tsx":
    "The register and issue forms are inside drawers opened from the page header, a row's menu and an " +
    "account's page, outside the main landmark these cases read. Each says what every field accepts " +
    "before it is sent, and tests/service-accounts-page.test.tsx submits each blank and holds that no " +
    "confirmation opens, nothing is sent, and the blank sentences are said beside their fields.",
  "src/pages/connectors/SourceActs.tsx":
    "The edit and the key forms are inside drawers opened from a source's Manage menu, outside the " +
    "main landmark these cases read. tests/connectors-page.test.tsx submits each blank and holds " +
    "that no confirmation opens, nothing is sent, and the API's own blank sentence is said.",
  "src/pages/staff-sources/ConnectDrawer.tsx":
    "The connect form is inside the drawer opened from the page's Connect a source button, outside the " +
    "main landmark these cases read. tests/staff-sources-page.test.tsx opens the drawer, submits it " +
    "blank, and holds that no confirmation opens, nothing is sent and each empty box is named beside it.",
  "src/pages/settings/SettingsPage.tsx":
    "Each editable row's form sends one value, from a confirmation, and says under the field what it " +
    "accepts; the API judges it with setting_problem before anything is written, answering 422 with a " +
    "sentence drawn beside the field. " +
    "tests/unit/test_settings_routes.py holds a refused value writing no row; the page case draws " +
    "no editable row, so no form is opened here.",
  "src/pages/skills/SkillForms.tsx":
    "Every form here opens behind a press the page cases do not make: Add a skill's drawer, Edit as a " +
    "new version, or the Profile's assign and categories cards. Each says what it accepts above its " +
    "fields, and a blank one cannot be sent: Add stays disabled until packageProblem accepts a package, " +
    "Import until importProblem accepts the repository and commit or the address, the written " +
    "procedure's Import until procedureProblem accepts a chosen file, and Save until the edit has " +
    "text, which tests/skills-page.test.tsx holds for Add and for the procedure. The assign form only " +
    "opens a confirmation naming an agent the API listed.",
  "src/pages/people/GrantDrawers.tsx": "Every form here opens in a drawer, which the kit renders outside the page's main landmark where " +
    "this harness looks. Each is submitted blank in tests/people-access-pages.test.tsx, which holds " +
    "that nothing is sent and that the form says, beside each field, what to fill in and in what form.",
  "src/pages/people/MoveDrawer.tsx": "Its one form opens in a drawer, which the kit renders outside the page's main landmark where " +
    "this harness looks. It is submitted blank in tests/people-access-pages.test.tsx, which holds " +
    "that nothing is sent and that the form says which department to choose.",
  "src/pages/people/PersonPlacements.tsx": "Every form here opens in a drawer, which the kit renders outside the page's main landmark where " +
    "this harness looks. Each is submitted blank in tests/people-access-pages.test.tsx, which holds " +
    "that nothing is sent and that the form says, beside each field, what to fill in and in what form.",
  "src/pages/people/PersonSessions.tsx": "Every form here opens in a drawer, which the kit renders outside the page's main landmark where " +
    "this harness looks. Each is submitted blank in tests/people-access-pages.test.tsx, which holds " +
    "that nothing is sent and that the form says, beside each field, what to fill in and in what form.",
  "src/pages/departments/StructureDrawers.tsx": "Every form here opens in a drawer, which the kit renders outside the page's main landmark where " +
    "this harness looks. Each is submitted blank in tests/people-access-pages.test.tsx, which holds " +
    "that nothing is sent and that the form says, beside each field, what to fill in and in what form.",
  "src/pages/roles/RoleDrawers.tsx": "Every form here opens in a drawer, which the kit renders outside the page's main landmark where " +
    "this harness looks. Each is submitted blank in tests/people-access-pages.test.tsx, which holds " +
    "that nothing is sent and that the form says, beside each field, what to fill in and in what form.",
  "src/pages/roles/PacksPage.tsx": "Every form here opens in a drawer, which the kit renders outside the page's main landmark where " +
    "this harness looks. Each is submitted blank in tests/people-access-pages.test.tsx, which holds " +
    "that nothing is sent and that the form says, beside each field, what to fill in and in what form.",
  "src/pages/Ask.tsx":
    "The question form cannot be sent blank by a person: its only submit button is disabled until " +
    "askBody accepts the text, and the field's maxLength stops a question longer than the route " +
    "takes. The second test below holds the button disabled for an empty question.",
  "src/pages/knowledge/addForms.tsx":
    "Every form here is drawn in a drawer from the Add menu, which renders outside the page's main " +
    "landmark where these cases look. tests/knowledge-page.test.tsx submits each one blank and holds " +
    "that nothing is sent and each says what to fill in, the file forms naming types and sizes first.",
  "src/pages/knowledge/actForms.tsx":
    "Every form here is drawn in a drawer from a document's header, outside the page's main landmark " +
    "where these cases look. tests/knowledge-page.test.tsx submits each one blank or with a past date " +
    "and holds that nothing is sent and each says what to fill in before anything is confirmed.",
  "src/pages/knowledge/SolutionsPage.tsx":
    "The capture form is drawn in a drawer outside the page's main landmark, and a decision's form is " +
    "one per waiting solution. tests/knowledge-page.test.tsx submits the capture blank and a decision " +
    "with no review date, and holds that nothing is sent and each says what to fill in.",
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
