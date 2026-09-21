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
  "src/components/ConnectSource.tsx": [{ pattern: "/connectors", index: 0, writes: true }],
  "src/components/DataStewardCard.tsx": [{ pattern: "/people", index: 1, writes: true }],
  // Index 0 is the ledger's filter bar, which only narrows; index 1 checks a published head.
  "src/pages/Audit.tsx": [
    { pattern: "/audit", index: 0, writes: false },
    { pattern: "/audit", index: 1, writes: true },
  ],
  "src/pages/Classification.tsx": [
    { pattern: "/classification/:entity/:column", index: 0, writes: false },
    { pattern: "/classification/:entity/:column", index: 1, writes: true },
  ],
  "src/pages/DataTransfer.tsx": [{ pattern: "/import-export", index: 0, writes: true }],
  // Index 0 on every page drawing a long list is `components/ListControls.tsx`' search form, which
  // is not in the page's file and sends nothing but a read.
  "src/pages/Departments.tsx": [
    { pattern: "/departments", index: 1, writes: true },
    { pattern: "/departments", index: 2, writes: true },
  ],
  "src/pages/Elevation.tsx": [{ pattern: "/elevation", index: 0, writes: true }],
  "src/pages/AccessRequests.tsx": [{ pattern: "/access-requests", index: 0, writes: true }],
  "src/pages/Matrix.tsx": [{ pattern: "/routing/:rungId", index: 1, writes: true }],
  // After the matrix's own search form: the golden question, then the rung to add.
  "src/components/MatrixGate.tsx": [
    { pattern: "/routing", index: 1, writes: true },
    { pattern: "/routing", index: 2, writes: true },
  ],
  // The add form is the only form until a provider's terms are opened, which draws theirs first.
  "src/components/ProviderRegister.tsx": [
    { pattern: "/models", index: 0, writes: true },
    { pattern: "/models", opener: "Record terms", index: 0, writes: true },
  ],
  "src/components/AgentModelPin.tsx": [{ pattern: "/agents/:agentId", opener: "Profile", index: 0, writes: true }],
  "src/pages/Notifications.tsx": [
    { pattern: "/notifications", index: 0, writes: true },
    { pattern: "/notifications", index: 1, writes: true },
    { pattern: "/notifications", index: 2, writes: true },
  ],
  "src/pages/People.tsx": [
    { pattern: "/people/:subject", index: 1, writes: true },
    { pattern: "/people/:subject", index: 2, writes: true },
  ],
  "src/pages/Prompts.tsx": [{ pattern: "/prompts", opener: "Edit instructions", index: 0, writes: true }],
  "src/pages/RequirementChecks.tsx": [{ pattern: "/requirement-checks", index: 0, writes: true }],
  // One form in the source, drawn twice (appoint and deputy); the first stands for both.
  "src/pages/RoleControls.tsx": [{ pattern: "/roles", index: 0, writes: true }],
  "src/pages/Retention.tsx": [
    { pattern: "/retention", index: 0, writes: true },
    { pattern: "/retention", index: 1, writes: true },
    { pattern: "/retention", index: 2, writes: true },
  ],
  "src/pages/SignInLinks.tsx": [{ pattern: "/sign-in-links", index: 1, writes: true }],
  "src/pages/StaffSources.tsx": [{ pattern: "/staff_sources", index: 0, writes: true }],
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
  "src/pages/Settings.tsx":
    "Each branding row's form sends one value, and the API judges it with branding_problem before " +
    "anything is written, answering 422 with a sentence drawn beside the field. " +
    "tests/unit/test_settings_routes.py holds a refused value writing no row; the page case draws " +
    "no editable row, so no form is opened here.",
  "src/pages/Skills.tsx":
    "Neither form is drawn with the page's usual answers, which offer no add and no approved skill. " +
    "The add form's submit is disabled until packageProblem accepts a package, which " +
    "tests/skills-page.test.tsx holds for an empty paste and an oversized one. The assign form's " +
    "select holds only agents the API listed and its button is disabled without one.",
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
      const opened = new Set(forms.map((one) => `${one.opener ?? ""}#${String(one.index)}`));
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
