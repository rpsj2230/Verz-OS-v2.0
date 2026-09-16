/**
 * A destructive write is sent only from a confirmation, and every confirmation says what will
 * happen and to what.
 *
 * `docs/admin-console.md`: "A destructive action is confirmed, and says what will happen and to
 * what." On 2026-09-17 every write in `src/pages` and `src/components` was read out of the source
 * by `support/writes.ts` and followed to the control that sends it. Twenty-two writes; thirteen went
 * through `components/ConfirmAction.tsx`; two that end or overwrite something did not. Taking a grant
 * away on the People screen was one press of a button beside the capability, and saving a routing
 * rung's numbers was the form's own submit. Both now ask first. The other seven are recorded below
 * with the reason each is not destructive.
 *
 * **What destructive means here.** A write that ends, removes, retires, replaces, overwrites or
 * switches off something that exists. Adding a grant, binding a sign-in, asking a question and
 * appointing the first administrator of an empty install end nothing, and each is recorded as
 * such rather than confirmed, because a confirmation in front of every write is a confirmation
 * people learn to click through, which costs the ones that matter.
 *
 * **The allowlist is a gate, not a note.** An entry naming a write that has gone, or a write that
 * is now confirmed, fails, so the list cannot grow quietly and cannot outlive its reason.
 *
 * **What this cannot see.** Whether the words a confirmation shows are true. That is each page's
 * own test, and for the rung editor it is the reason its consequence says the row changes and the
 * routing does not.
 *
 * Task ids: M27.8.4
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import ts from "typescript";
import { describe, expect, test } from "vitest";
import { CONSOLE_ROOT } from "./support/repo";
import { consoleSourcePaths } from "./support/typescript";
import { CONTROL_DIRECTORIES, everyConfirmation, everyWrite } from "./support/writes";

/**
 * Writes sent without a confirmation, keyed `file address` as `support/writes.ts` spells them, and
 * why each one is not destructive.
 */
const NOT_DESTRUCTIVE: Readonly<Record<string, string>> = {
  "src/pages/Approvals.tsx approvalDecisionApiPath(suspensionId)":
    "Deciding an approval is the answer to a question the card has already asked. The artefact and " +
    "its facts are drawn above the two buttons, which tests/approvals-page.test.tsx holds, so the " +
    "card is the statement of what will happen and to what, and a second step would ask the approver " +
    "to confirm a confirmation. A rejection's button stays disabled until a reason is chosen.",
  "src/pages/Ask.tsx ANSWER_API_PATH":
    "Asking a question changes nothing an administrator manages: the answer is computed for the " +
    "reader and nothing they hold is ended or replaced.",
  "src/pages/Classification.tsx reviewApiPath(entity, row.column)":
    "A review is a dry run. brain.classification_routes stores nothing and holds no handle of " +
    "anything stored, which tests/unit/test_classification_routes.py proves, so there is nothing " +
    "for the review to destroy.",
  "src/pages/FirstRun.tsx FINISH_PATH":
    "Binds the installer's own sign-in to the first administrator on an install that has none, " +
    "once; a second use is refused, so nothing existing is replaced.",
  "src/pages/FirstRun.tsx APPOINTMENT_PATH":
    "Appoints the first administrator of an install that has none. The wizard's review screen is " +
    "the statement of everything sent, and nothing existing is ended or replaced.",
  "src/pages/People.tsx GRANTS_API_PATH":
    "Writes a new grant. Entitlements are additive only, a grant replaces nothing, and taking one " +
    "back is the removal beside it, which is confirmed.",
  "src/pages/Skills.tsx SKILLS_API_PATH":
    "Adds a skill to the library undecided. A second import of the same bytes is refused by the " +
    "table's key rather than written over, so nothing existing is replaced, and the skill reaches no " +
    "agent until somebody else approves it and an administrator assigns it, both of which are confirmed.",
  "src/pages/SignInLinks.tsx LINK_API_PATH":
    "Binds a sign-in to a person. A subject already bound elsewhere is refused with a 409 rather " +
    "than re-pointed, so nothing existing is replaced; unlinking is the destructive act and it is " +
    "confirmed.",
};

/** How many times a non-GET `method:` or an `openStream(` call is written in the control files. */
function writesSpelledInText(): number {
  let count = 0;
  for (const file of CONTROL_DIRECTORIES.flatMap((directory) => consoleSourcePaths(directory))) {
    const source = ts.createSourceFile(file, readFileSync(join(CONSOLE_ROOT, file), "utf8"), ts.ScriptTarget.ES2022, true, ts.ScriptKind.TSX);
    const visit = (node: ts.Node): void => {
      if (
        ts.isPropertyAssignment(node) &&
        node.name.getText(source) === "method" &&
        ts.isStringLiteral(node.initializer) &&
        node.initializer.text !== "GET"
      ) {
        count += 1;
      }
      if (ts.isCallExpression(node) && node.expression.getText(source) === "openStream") {
        count += 1;
      }
      node.forEachChild(visit);
    };
    source.forEachChild(visit);
  }
  return count;
}

describe("a destructive write is confirmed", () => {
  test("every write the control files spell is one the reading found, so the rules below read a real list", () => {
    // What breaks if this is deleted: the reading in `support/writes.ts` quietly missing a write
    // shaped differently from the ones it knows, after which every test here passes over a list with
    // a hole in it. Counted a second, simpler way, from the syntax rather than from the calls.
    const writes = everyWrite();
    expect(writes.length).toBeGreaterThan(0);
    expect(writes.length).toBe(writesSpelledInText());
    for (const write of writes) {
      expect(write.address, `${write.file}:${String(write.line)}`).not.toBe("");
      expect(write.reachedFrom.length, write.key).toBeGreaterThan(0);
    }
  }, 60_000);

  test("every write sent without a confirmation is recorded as not destructive, with its reason", () => {
    // What breaks if this is deleted: the People screen's removal as it was, one press taking a
    // grant away, or a new switch-off added beside a list with nothing between the press and the
    // write. And the list of excuses growing without anybody writing down why.
    const unconfirmed = everyWrite().filter((write) => !write.confirmed);
    const excused = Object.keys(NOT_DESTRUCTIVE);
    expect(
      unconfirmed.filter((write) => !excused.includes(write.key)).map((write) => `${write.key} <- ${write.reachedFrom.join(" | ")}`),
    ).toEqual([]);
    expect(excused.filter((key) => !unconfirmed.some((write) => write.key === key))).toEqual([]);
    for (const [key, reason] of Object.entries(NOT_DESTRUCTIVE)) {
      expect(reason.split(" ").length, `${key} is excused without a reason`).toBeGreaterThan(10);
    }
  }, 60_000);

  test("the removal of a grant and the save of a routing rung are sent only from a confirmation", () => {
    // What breaks if this is deleted: the positive half of the rule above. A reading that reported
    // every write as unconfirmed would satisfy it with a longer allowlist, so the two writes this
    // test was written for are named and must be found confirmed.
    const confirmed = everyWrite().filter((write) => write.confirmed).map((write) => write.key);
    expect(confirmed).toContain("src/pages/People.tsx REMOVAL_API_PATH");
    expect(confirmed).toContain("src/pages/Matrix.tsx rungApiPath(rung.id)");
    expect(confirmed).toContain("src/pages/Sessions.tsx END_SESSION_API_PATH");
  }, 60_000);

  test("every confirmation names what it asks about, says what will happen, and offers a way out", () => {
    // What breaks if this is deleted: a confirmation that asks "Are you sure?" over a button reading
    // OK, which is a second click and not a confirmation. Each is read from the source: a question,
    // a consequence, a verb for the act and one for keeping things as they are, none of them empty,
    // and a written-out question ending in a question mark.
    const confirmations = everyConfirmation();
    expect(confirmations.length).toBeGreaterThan(0);
    for (const one of confirmations) {
      const where = `${one.file}:${String(one.line)}`;
      for (const name of ["question", "consequence", "confirmLabel", "cancelLabel", "onConfirm", "onCancel"]) {
        const value = one.attributes[name];
        expect(value, `${where} has no ${name}`).toBeDefined();
        expect(value, `${where} has an empty ${name}`).not.toBeNull();
        if (value !== null && value !== undefined && ts.isStringLiteral(value)) {
          expect(value.text.trim(), `${where} ${name}`).not.toBe("");
        }
      }
      const question = one.attributes["question"];
      if (question !== null && question !== undefined && ts.isStringLiteral(question)) {
        expect(question.text.endsWith("?"), where).toBe(true);
      }
      expect(one.attributes["question"]?.getText(), where).not.toBe(one.attributes["consequence"]?.getText());
    }
  }, 60_000);
});
