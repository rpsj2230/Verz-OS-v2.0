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
  "src/pages/approvals/ApprovalCard.tsx approvalDecisionApiPath(suspensionId)":
    "Deciding an approval is the answer to a question the card has already asked. The artefact and " +
    "its facts are drawn above the two buttons, which tests/approvals-page.test.tsx holds, so the " +
    "card is the statement of what will happen and to what, and a second step would ask the approver " +
    "to confirm a confirmation. A rejection's button stays disabled until a reason is chosen.",
  "src/pages/access-requests/AccessRequestsPage.tsx ACCESS_REQUESTS_API_PATH":
    "Sending a request for access ends and replaces nothing: it is addressed to whoever can decide " +
    "it, and the decision is a grant written on the Roles screen, which is where anything changes.",
  "src/pages/audit/VerifyPage.tsx VERIFICATION_API_PATH":
    "Walking the ledger reads every entry and writes nothing: brain.audit_routes.verify_ledger stores no " +
    "report, which tests/unit/test_chain_check.py holds, so there is nothing for a press to destroy.",
  "src/pages/requirement-checks/RecordDrawer.tsx CHECKS_API_PATH":
    "Recording a check appends a row. A later check supersedes an earlier one without editing it and " +
    "nothing is removed, which tests/unit/test_requirement_check_routes.py holds, so nothing existing " +
    "is ended or replaced.",
  "src/pages/knowledge/addForms.tsx uploadPath(place.kind, place.level, place.department)":
    "Adding a document writes a new item. The same file sent again to the same place is the same item " +
    "with the same text, because its reference is a digest of the bytes, the owner and the place, which " +
    "tests/unit/test_knowledge_upload.py holds, so nothing existing is ended or removed.",
  "src/pages/knowledge/parts.tsx taskDonePath(taskId)":
    "Marking a task read closes a notice in the reader's own list: a document handed to them, or a " +
    "promotion or a solution of theirs decided. What it reports is unchanged and in the ledger, and a " +
    "review is never closed this way, which tests/unit/test_knowledge_lifecycle_db.py holds.",
  "src/pages/knowledge/actForms.tsx verificationPath(itemId)":
    "Verifying records that a named person vouched for the document today and when it is next due. " +
    "The earlier verification is kept in the ledger, which records the columns that changed, so " +
    "nothing is lost; tests/unit/test_knowledge_lifecycle_db.py holds the entry.",
  "src/pages/knowledge/actForms.tsx promotionPath(itemId)":
    "Asking for the whole company changes nothing: it raises a card on the Approvals screen, and the " +
    "document widens only when somebody else approves it there, which " +
    "tests/unit/test_knowledge_lifecycle_db.py holds.",
  "src/pages/knowledge/SolutionsPage.tsx SOLUTIONS_API_PATH":
    "Capturing a solution adds a row that waits for somebody else's decision. It answers nothing and " +
    "ends nothing until it is approved.",
  "src/pages/knowledge/SolutionsPage.tsx solutionDecisionPath(one.solutionId)":
    "Deciding a solution is the answer to the question its card asks, as deciding an approval is: the " +
    "problem and the solution are drawn above the two buttons, approving adds a document and refusing " +
    "adds nothing, and both are recorded in the ledger.",
  "src/pages/knowledge/addForms.tsx LINKS_API_PATH":
    "Adding a page by its link writes a new item, and the same page added again to the same place is " +
    "the same item, because its reference is a digest of the bytes, the owner and the place, which " +
    "tests/unit/test_link_intake.py holds, so nothing existing is ended or removed.",
  "src/pages/knowledge/addForms.tsx queuedPath(place.kind, place.level, place.department)":
    "Queueing a file keeps it and a ticket for the worker; the item it becomes is named by a digest " +
    "of the bytes, the owner and the place, as an upload is, which tests/unit/test_ingest_queue.py " +
    "holds, so nothing existing is ended or removed.",
  "src/pages/Ask.tsx ANSWER_API_PATH":
    "Asking a question changes nothing an administrator manages: the answer is computed for the " +
    "reader and nothing they hold is ended or replaced.",
  "src/pages/classification/ClassificationPage.tsx mark === null ? reviewApiPath(entity, row.column) : markReviewApiPath(entity, row.column)":
    "A review of a rule or of a mark is a dry run. brain.classification_routes stores nothing on " +
    "either, which tests/unit/test_classification_routes.py and tests/unit/test_classified_tables.py " +
    "prove, so there is nothing for the review to destroy.",
  "src/pages/classification/ClassificationPage.tsx markApiPath(entity, row.column)":
    "Applying a mark replaces one column's rule, and the press comes after a review of exactly that " +
    "mark whose verdict, widening included, is on the screen above the button. The rule before is " +
    "in the ledger entry 0116's trigger writes and can be marked back the same way, so nothing is " +
    "ended that cannot be restored by the same control.",
  "src/pages/classification/ClassificationPage.tsx tableApiPath(named)":
    "Uploading a table writes its rows under a new version and keeps every earlier version's rows, " +
    "so nothing is deleted, and the marks that stand are kept. The upload is ledgered by 0116's " +
    "trigger under the person who sent it.",
  "src/pages/FirstRun.tsx FINISH_PATH":
    "Binds the installer's own sign-in to the first administrator on an install that has none, " +
    "once; a second use is refused, so nothing existing is replaced.",
  "src/pages/FirstRun.tsx APPOINTMENT_PATH":
    "Appoints the first administrator of an install that has none. The wizard's review screen is " +
    "the statement of everything sent, and nothing existing is ended or replaced.",
  "src/components/StaffListCheck.tsx SIGN_IN_PATH":
    "Asks for the directory's sign-in page during first run. It writes nothing anywhere, so there " +
    "is nothing for it to end or replace.",
  "src/components/StaffListCheck.tsx TRIAL_PATH":
    "Reads the chosen staff list once during first run and shows who it names. Nobody is added " +
    "and nothing is stored, which tests/unit/test_setup_staff_routes.py holds.",
  "src/pages/people/GrantDrawers.tsx GRANTS_API_PATH":
    "Writes a new grant. Entitlements are additive only, a grant replaces nothing, and taking one " +
    "back is the removal on the person's Grants view, which is confirmed.",
  "src/pages/people/GrantDrawers.tsx PACK_ASSIGNMENT_API_PATH":
    "Assigns a capability pack. Entitlements are additive only, an assignment replaces nothing, and " +
    "taking one back is the Remove pack control on the Grants view, which is confirmed.",
  "src/pages/people/GrantDrawers.tsx DIRECTORY_API_PATH":
    "Adds a person by hand to an install with no staff source. The id is minted by the server, so " +
    "no existing person is written over, and the person holds nothing until somebody grants it.",
  "src/pages/people/PersonPlacements.tsx MEMBERSHIP_API_PATH":
    "Places a person in a team of their department. A placement ends nothing and changes nobody's " +
    "access; taking them out is the confirmed control beside the team.",
  "src/pages/people/PersonSessions.tsx LINK_API_PATH":
    "Links a sign-in account to the person whose page it is. An account already linked elsewhere is " +
    "refused with a 409 rather than re-pointed, so nothing existing is replaced; unlinking is confirmed.",
  "src/pages/departments/StructureDrawers.tsx FOUND_API_PATH":
    "Creates a department and its own scope. A short name a live department or scope already has is " +
    "refused rather than taken over, so nothing existing is replaced; retiring one is confirmed.",
  "src/pages/departments/StructureDrawers.tsx ADD_TEAM_API_PATH":
    "Creates a team with nobody in it. A short name a live team already has is refused, and a team " +
    "confers nothing; retiring one is confirmed.",
  "src/pages/departments/StructureDrawers.tsx DRAW_SCOPE_API_PATH":
    "Creates a named scope. A taken short name is refused rather than reused, a scope grants nothing " +
    "on its own, and retiring one is confirmed.",
  "src/pages/departments/StructureDrawers.tsx MEMBERSHIP_API_PATH":
    "Places somebody in a team. It ends nothing and changes nobody's access; taking them out is the " +
    "confirmed control beside their name.",
  "src/pages/roles/RoleDrawers.tsx APPOINTMENT_API_PATH":
    "Appoints somebody to a role. A role grant replaces nothing and grants no capability, and taking " +
    "one away is the removal beside it, which is confirmed.",
  "src/pages/roles/RoleDrawers.tsx DEPUTY_API_PATH":
    "Appoints a deputy for at most thirty days beside the standing holder, who keeps the role; the " +
    "deputy lapses on its own, and removing one is confirmed.",
  "src/pages/roles/RoleDrawers.tsx GROUP_RULES_API_PATH":
    "Maps a directory group to a role. One live rule per group, so a second is refused rather than " +
    "written over, groups only ever add a role, and retiring a rule is confirmed.",
  "src/pages/roles/PacksPage.tsx PACKS_API_PATH":
    "Creates a pack at version 1 that nobody holds until it is assigned. A taken short name is " +
    "refused rather than written over; a new version and a retirement are confirmed.",
  "src/pages/roles/PacksPage.tsx PACK_COPY_API_PATH":
    "Copies a pack under a new short name at version 1. The pack copied is unchanged and nobody holds " +
    "the copy until it is assigned.",
  "src/pages/skills/SkillForms.tsx SKILLS_API_PATH":
    "Adds a skill to the library undecided. A second import of the same bytes is refused by the " +
    "table's key rather than written over, so nothing existing is replaced, and the skill reaches no " +
    "agent until somebody approves it and an administrator assigns it, both of which are confirmed.",
  "src/pages/skills/SkillForms.tsx IMPORT_PATH":
    "Imports a skill from a repository commit or an address into the library undecided, exactly as " +
    "an added package is: the same bytes twice are refused by the key, nothing existing is replaced, " +
    "and it reaches no agent until it is approved and assigned, both of which are confirmed.",
  "src/pages/skills/SkillForms.tsx versionsPath(one.digest)":
    "Saves an edit as a new, undecided version beside the one it came from, which is never changed; " +
    "every agent keeps the version it runs, which tests/unit/test_skill_routes.py holds, so nothing " +
    "existing is ended or replaced.",
  "src/pages/skills/SkillForms.tsx categoriesPath(one.digest)":
    "Sets the labels a skill is filed under. The previous labels are shown in the box before the " +
    "press and can be typed back, the change is a new row that edits none, and a label reaches no " +
    "agent and changes no procedure.",
  "src/pages/sessions/SignInLinksPage.tsx LINK_API_PATH":
    "Binds a sign-in to a person. A subject already bound elsewhere is refused with a 409 rather " +
    "than re-pointed, so nothing existing is replaced; unlinking is the destructive act and it is " +
    "confirmed.",
  "src/pages/staff-sources/ConnectDrawer.tsx path":
    "Sends the connection test and the first sync's dry run, which keep nothing: no setting, no " +
    "credential and no member is written, which tests/unit/test_staff_connect.py holds for both. " +
    "Saving the connection and applying the first sync have their own requests and are confirmed.",
  "src/components/ConnectLark.tsx LARK_TEST_API_PATH":
    "Testing a Lark connection exchanges the pasted credential for a token and makes small reads; " +
    "it writes nothing here or in Lark and keeps nothing it read, which " +
    "tests/unit/test_lark_connect.py holds over the requests a fake Lark server received.",
  "src/pages/channels/ChannelProfile.tsx testApiPath(row.channel)":
    "A test message is one product sentence to one destination, sent once per channel record and " +
    "destination, which tests/unit/test_channel_pipeline.py holds; it ends and replaces nothing.",
  "src/components/MyChannels.tsx myCodeApiPath(row.channel)":
    "Asking for a code binds nothing: the code is shown to the person who asked and does nothing " +
    "until they send it from their own chat. It ends only an older code of theirs for that channel " +
    "that nothing has used, which tests/unit/test_channel_binding.py holds.",
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

  test("the removal of a grant, the save, move and retirement of a routing step, and a provider's switch, check and retirement are sent only from a confirmation", () => {
    // What breaks if this is deleted: the positive half of the rule above. A reading that reported
    // every write as unconfirmed would satisfy it with a longer allowlist, so the writes this test
    // was written for are named and must be found confirmed. A provider switched off moves every
    // department's questions and a check spends tokens under the presser's name, so both are here.
    const confirmed = everyWrite().filter((write) => write.confirmed).map((write) => write.key);
    expect(confirmed).toContain("src/pages/people/PersonGrants.tsx REMOVAL_API_PATH");
    expect(confirmed).toContain("src/pages/models/RungEditor.tsx rungApiPath(rung.id)");
    expect(confirmed).toContain("src/pages/sessions/SessionsPage.tsx END_SESSION_API_PATH");
    expect(confirmed).toContain("src/pages/models/ProvidersPage.tsx providerSwitchApiPath(pending.provider)");
    expect(confirmed).toContain("src/pages/models/ProvidersPage.tsx providerCheckApiPath(pending.provider)");
    expect(confirmed).toContain("src/pages/models/RoutingPage.tsx retireStepApiPath(asked.rungId)");
    expect(confirmed).toContain("src/pages/models/RoutingPage.tsx moveStepApiPath(asked.rungId)");
    expect(confirmed).toContain("src/pages/models/ProviderDetailPage.tsx retireProviderApiPath(pending.provider)");
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
