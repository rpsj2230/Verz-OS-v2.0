/**
 * Every empty list says what would add a row and which role does it, in the same words for every reader.
 *
 * `docs/admin-console-architecture.md` 5.2 asks an empty list to say what would put a row there and
 * who may do it, and rule R1 bounds that: the sentence is true for every reader and says nothing of why
 * the list is empty, because a company with none and a reader whose reach covers none are one event to
 * a browser. Until 2026-10-15 each page wrote its own empty sentence in its own words. A third of them
 * said what a row is and not how to get one, and none of them named who does it, so a person looking at
 * an empty People list had to ask somebody what would have to happen.
 *
 * **The shape is the guard.** `kit/states.tsx` `EmptyList` takes `adds`, the act that makes a row, and
 * `by`, who does it, as props the type requires, and `ListPage` and `operations/parts.tsx` `WholeList`
 * take them as `emptyAdds` and `emptyBy`. A page cannot draw an empty list without both. `by` is the
 * platform's six roles, from `kit/roles.ts`, or the install itself for a list that fills itself, so a
 * role cannot be invented. This file holds the three things a type cannot:
 *
 * 1. **Nothing draws an empty list some other way.** `EmptyState` stays, for the three things that are
 *    not an empty list (a search that matched nothing, a page that is not there, a state that is not a
 *    list), and each use is named below with its reason. A new `<EmptyState` is a failure until it is.
 * 2. **The vocabulary is the product's.** The six role ids and their words are read against
 *    `brain.identity.roles.Role`, so a seventh role added there fails here.
 * 3. **Every registered page that has a list says it that way when the list is empty**, mounted the way
 *    `tests/screen-states.test.tsx` mounts it, and the words name no cause.
 *
 * **What this does not decide.** Whether the named role is the one whose grant lets the press work: a
 * role grants no capability (`brain.identity.roles.NO_ROLE_IMPLIES_A_CAPABILITY`), so the sentence says
 * who the screen is designed for (`brain.console.screens.Screen.intended_for`), and the grant decides.
 *
 * Task ids: M27.15.69
 */

import ts from "typescript";
import { beforeAll, describe, expect, test } from "vitest";
import { loadConsole } from "./support/auth";
import { PAGES } from "./support/pageCases";
import { ACTS, ASKING, emptyAnswers, NO_EMPTY_SENTENCE } from "./support/screenStateRules";
import { collapse, mountIn } from "./support/screenStates";
import { A_STATE_IS_NOT_A_LIST, BARE_LISTS, BARE_STATES } from "./support/bareEmpties";
import { readRepoFile } from "./support/repo";
import { consoleSourcePaths, parseConsoleSource } from "./support/typescript";
import { PLATFORM_ROLES, ROLE_WORDS } from "../src/components/kit/roles";
import { BY_THE_INSTALL, THE_INSTALL_RECORDS_THESE, whoAdds } from "../src/components/kit/states";

/**
 * Words that say why a list is empty. The sentence is the same for every reader and every reason, so
 * none of these may appear in it: each is a reason, and a reason is a fact about rows the reader may
 * not see.
 */
export const CAUSE_WORDS =
  /\b(because|permission|permitted|not allowed|access denied|denied|hidden|withheld|refused|you may not|you cannot|you do not have|restricted|forbidden)\b/iu;

/** The uses of `<EmptyState` that are not an empty list, by `file title`, and which of three they are. */
export const NOT_AN_EMPTY_LIST: Readonly<Record<string, string>> = {
  "src/components/kit/ListPage.tsx NOTHING_MATCHES":
    "A narrowed result: the reader's own search or filter matched nothing, which describes their question over " +
    "their own rows and is a different sentence from an unnarrowed list being empty.",
  "src/pages/approvals/ApprovalsPage.tsx NOTHING_MATCHES":
    "A narrowed result: the reader's own search or filter matched nothing, so the list itself is not empty.",
  "src/pages/audit/AuditPage.tsx NOTHING_MATCHES":
    "A narrowed result: the reader's own filters matched no entry in the period, so the ledger is not empty.",
  "src/pages/audit/AuditSubjectPage.tsx NOTHING_MATCHES":
    "A narrowed result: the reader's own filters matched no entry for this subject.",
  "src/pages/learning/LearningPage.tsx NOTHING_MATCHES":
    "A narrowed result: the reader's own choices matched nothing in the tier.",
  "src/pages/memory/MemoryDetailPage.tsx NOTHING_MATCHES":
    "A narrowed result: the reader's own search or kind matched nothing they may read.",
  "src/pages/operations/ArtifactsPage.tsx NOTHING_MATCHES":
    "A narrowed result: the reader's own search or kind matched no artifact.",
  "src/pages/operations/JobDetailPage.tsx NOTHING_MATCHES":
    "A narrowed result: the reader's own search or filter matched no run of this job.",
  "src/pages/reports/AdoptionPage.tsx NOTHING_MATCHES":
    "A narrowed result: the reader's own search or filter matched no department.",
  "src/pages/requirement-checks/RequirementChecksPage.tsx NOTHING_MATCHES":
    "A narrowed result: the reader's own search or standing matched no requirement.",
  '"Nothing matches"':
    "A narrowed result: the words the reader typed matched no capability. The vocabulary itself is not empty, " +
    "which the list above it says in its own empty sentence.",
  "src/pages/operations/LogsPage.tsx NO_ENTRIES":
    "A narrowed result: the log is always read through a level, a period and a search, so what is empty is " +
    "the reader's own question, and its sentence tells them to change one of the three.",
  "src/pages/models/ProviderDetailPage.tsx": "A page that is not there: the address names no provider the reader may see.",
  "src/pages/departments/DepartmentDetailPage.tsx": "A page that is not there: the address names no department the reader may see.",
  "src/pages/skills/SkillDetailPage.tsx NO_SUCH_SKILL": "A page that is not there: the address names no skill the reader may see.",
  "src/pages/department/DepartmentHomePage.tsx": "A state that is not a list: this page is a department console's own and the reader has none.",
  "src/pages/channels/ChannelDashboard.tsx": "A state that is not a list: this release cannot receive on the channel, or it is not set up, so there is no list yet.",
  "src/pages/connectors/ConnectorDashboard.tsx NOT_CONNECTED_TITLE": "A state that is not a list: the source is not connected, so it has no figures.",
  "src/pages/company/CompanyPages.tsx WITHHELD": "A state that is not a list: the figure is not shown to this reader, which is one sentence for the whole page.",
  "src/pages/settings/SettingsPage.tsx NO_SETTINGS": "A state that is not a list: the answer carried no group of settings, which is a fault in the answer and not an empty table.",
  "src/pages/webhooks/WebhooksPage.tsx NOT_MANAGEABLE_TITLE": "A state that is not a list: this reader does not hold the grant that manages subscribers, and the page says what the grant is.",
};

interface Hit {
  readonly key: string;
  readonly where: string;
}

function everyNode(source: ts.SourceFile): ts.Node[] {
  const nodes: ts.Node[] = [];
  const visit = (node: ts.Node): void => {
    nodes.push(node);
    node.forEachChild(visit);
  };
  source.forEachChild(visit);
  return nodes;
}

const SCREEN_DIRECTORIES = ["src/pages", "src/components"] as const;

/** Every `<EmptyState` outside the file that defines it, keyed by file and what its title is. */
export function emptyStatesWritten(): Hit[] {
  const hits: Hit[] = [];
  for (const file of SCREEN_DIRECTORIES.flatMap((directory) => consoleSourcePaths(directory))) {
    if (file === "src/components/kit/states.tsx") {
      continue;
    }
    const source = parseConsoleSource(file);
    for (const node of everyNode(source)) {
      if ((ts.isJsxSelfClosingElement(node) || ts.isJsxOpeningElement(node)) && node.tagName.getText(source) === "EmptyState") {
        const title = node.attributes.properties.find((one) => ts.isJsxAttribute(one) && one.name.getText(source) === "title");
        const text =
          title !== undefined && ts.isJsxAttribute(title) && title.initializer !== undefined
            ? title.initializer.getText(source).replace(/^\{|\}$/gu, "")
            : "";
        const line = source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1;
        hits.push({ key: `${file} ${text}`, where: `${file}:${String(line)}` });
      }
    }
  }
  return hits;
}

/** The allowlist key an `<EmptyState` falls under: its file and title, its file alone, or its title alone. */
export function allowedAs(hit: Hit): string | undefined {
  const [file, ...rest] = hit.key.split(" ");
  const title = rest.join(" ");
  return [hit.key, file ?? "", title].find((one) => one in NOT_AN_EMPTY_LIST);
}

/**
 * Every empty list a screen file writes, as the act and the who it gives, in source text.
 *
 * Three elements draw one: `<EmptyList adds by>`, and the two that hand their `emptyAdds` and `emptyBy`
 * to it, `ListPage` and the operations screens' `WholeList`. Any element carrying either of those two
 * props is read the same way, so a third that does the same is read without being named.
 */
export function emptyListsWritten(): { where: string; props: Record<string, ts.Expression | ts.StringLiteral | null> }[] {
  const found: { where: string; props: Record<string, ts.Expression | ts.StringLiteral | null> }[] = [];
  for (const file of SCREEN_DIRECTORIES.flatMap((directory) => consoleSourcePaths(directory))) {
    const source = parseConsoleSource(file);
    for (const node of everyNode(source)) {
      if (!(ts.isJsxSelfClosingElement(node) || ts.isJsxOpeningElement(node))) {
        continue;
      }
      const props: Record<string, ts.Expression | ts.StringLiteral | null> = {};
      for (const property of node.attributes.properties) {
        if (!ts.isJsxAttribute(property)) {
          continue;
        }
        const value = property.initializer;
        const name = property.name.getText(source);
        props[name === "emptyAdds" ? "adds" : name === "emptyBy" ? "by" : name] =
          value === undefined ? null : ts.isJsxExpression(value) ? (value.expression ?? null) : ts.isStringLiteral(value) ? value : null;
      }
      const draws = node.tagName.getText(source) === "EmptyList" || "adds" in props && node.attributes.properties.some((one) => ts.isJsxAttribute(one) && one.name.getText(source) === "emptyAdds");
      if (draws) {
        found.push({ where: `${file}:${String(source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1)}`, props });
      }
    }
  }
  return found;
}

describe("the vocabulary an empty list names is the product's", () => {
  test("the six role ids and their words are the ones brain.identity.roles.Role declares", () => {
    // What breaks if this is deleted: a role added to or renamed in `roles.py` while the console goes on
    // saying the old six, so an empty list names a role that no longer exists or leaves one out.
    const source = readRepoFile("src/brain/identity/roles.py");
    const enumBody = /class Role\(enum\.StrEnum\):[\s\S]*?\n\n\n/u.exec(source)?.[0] ?? "";
    const ids = [...enumBody.matchAll(/^\s+[A-Z_]+ = "([a-z_]+)"$/gmu)].map((one) => one[1] ?? "");
    expect(ids.length).toBeGreaterThan(0);
    expect([...PLATFORM_ROLES].sort()).toEqual([...ids].sort());
    expect(Object.keys(ROLE_WORDS).sort()).toEqual([...ids].sort());
    const count = /^ROLE_COUNT: Final = (\d+)$/mu.exec(source)?.[1];
    expect(PLATFORM_ROLES.length).toBe(Number(count));
  });

  test("who adds a row is said in one sentence, the same for every reader", () => {
    // What breaks if this is deleted: the sentence changed to carry a count, a reader or a reason, or a
    // list of roles joined so that one reads as the only one. The install's sentence is the sibling.
    expect(whoAdds(["super_admin"])).toBe("A Super Admin adds one.");
    expect(whoAdds(["super_admin", "department_admin"])).toBe("A Super Admin or a Department admin adds one.");
    expect(whoAdds(["auditor", "department_admin", "member"])).toBe("An Auditor, a Department admin or a Member adds one.");
    expect(whoAdds(BY_THE_INSTALL)).toBe(THE_INSTALL_RECORDS_THESE);
    for (const sentence of [whoAdds(["approver"]), whoAdds(BY_THE_INSTALL)]) {
      expect(CAUSE_WORDS.test(sentence), sentence).toBe(false);
    }
  });
});

describe("nothing draws an empty list any other way", () => {
  test("every EmptyState a screen writes is a narrowed result, a page that is not there or a state, and is named", () => {
    // What breaks if this is deleted: a page that goes back to `<EmptyState title="No agents" />`, which
    // says what is missing and neither how to add one nor who does it, and passes every other test.
    const found = emptyStatesWritten().filter((one) => allowedAs(one) === undefined);
    expect(found.map((one) => `${one.key} (${one.where})`)).toEqual([]);
  });

  test("every allowed EmptyState is still written, and says in words why it is not an empty list", () => {
    // What breaks if this is deleted: the allowlist outliving the line it excuses, so it excuses the
    // next `<EmptyState` written there.
    const written = emptyStatesWritten();
    for (const [key, reason] of Object.entries(NOT_AN_EMPTY_LIST)) {
      expect(
        written.some((one) => allowedAs(one) === key),
        `${key} is allowed and is no longer written`,
      ).toBe(true);
      expect(reason.split(" ").length, `${key} is allowed without a reason`).toBeGreaterThan(8);
    }
  });

  test("every EmptyList a page writes gives an act that adds a row and a who from the vocabulary", () => {
    // What breaks if this is deleted: `adds=""` or `by={[]}`, which satisfy the type and say nothing.
    // The type holds the roles to the six; this holds that the sentence is a sentence and the roles
    // are named at least once.
    const lists = emptyListsWritten();
    expect(lists.length).toBeGreaterThan(50);
    for (const list of lists) {
      const adds = list.props["adds"];
      expect(adds, `${list.where} has no adds`).toBeDefined();
      if (adds !== undefined && adds !== null && ts.isStringLiteral(adds)) {
        expect(adds.text.split(" ").length, `${list.where} adds is not a sentence`).toBeGreaterThanOrEqual(6);
        expect(adds.text.endsWith("."), `${list.where} adds does not end a sentence`).toBe(true);
        expect(CAUSE_WORDS.test(adds.text), `${list.where} says why: ${adds.text}`).toBe(false);
      }
      const by = list.props["by"];
      expect(by, `${list.where} has no by`).toBeDefined();
      expect(by, `${list.where} has an empty by`).not.toBeNull();
      if (by !== undefined && by !== null && ts.isArrayLiteralExpression(by)) {
        expect(by.elements.length, `${list.where} names no role`).toBeGreaterThan(0);
      }
    }
  });
});

/** A sentence that says a list is empty: it begins No, Nothing, Nobody or None, or says there is none. */
export const SAYS_NOTHING_IS_THERE = /^\s*(No|Nothing|Nobody|None|There (is|are) no|You have no|You do not)\b/u;

/** Every sentence under `root` that says nothing is there and is not inside an empty list or an empty state. */
export function bareEmptySentences(root: Element): string[] {
  const inside = new Set<Element>([...root.querySelectorAll('[data-slot="empty-list"] *, [data-slot="empty-state"] *')]);
  const found = new Set<string>();
  for (const element of root.querySelectorAll("p, li, td, span, div, h3")) {
    if (inside.has(element)) {
      continue;
    }
    const own = [...element.childNodes].some((one) => one.nodeType === Node.TEXT_NODE && collapse(one.textContent ?? "") !== "");
    const text = collapse(element.textContent ?? "");
    if (own && SAYS_NOTHING_IS_THERE.test(text) && text.length < 200) {
      found.add(text);
    }
  }
  return [...found].sort();
}

describe("every registered page that has a list says it that way when the list is empty", () => {
  beforeAll(async () => {
    await loadConsole();
  }, 60_000);

  const withLists = ASKING.filter(
    (pattern) => ACTS[pattern] === undefined && !(pattern in NO_EMPTY_SENTENCE) && emptyAnswers(pattern) !== null,
  );

  test("the pages read here are the ones screen-states holds to an empty sentence", () => {
    // What breaks if this is deleted: the page set being filtered to nothing by a rename in
    // `support/screenStateRules.tsx`, after which the test below runs over no page at all.
    expect(withLists.length).toBeGreaterThan(40);
  });

  test("the backlog names only pages that are registered, each with a sentence, and states argue why", () => {
    // What breaks if this is deleted: a record left naming an address that no longer exists, which
    // would excuse a page nobody reads, and an empty `BARE_STATES` reason.
    for (const record of [BARE_STATES, BARE_LISTS]) {
      for (const [pattern, sentences] of Object.entries(record)) {
        expect(PAGES[pattern], `${pattern} is not a registered page`).toBeDefined();
        expect(sentences.length, `${pattern} names no sentence`).toBeGreaterThan(0);
      }
    }
    expect(A_STATE_IS_NOT_A_LIST.split(" ").length).toBeGreaterThan(20);
  });

  test.each(withLists)(
    "%s draws every empty list with an act and a who, and no reason, and no new bare paragraph",
    async (pattern) => {
      // What breaks if this is deleted: an empty list drawn as a paragraph that says what is missing and
      // neither how to add one nor who does it, which a type cannot see because it was never an
      // `EmptyState`; or an empty list that names a cause.
      const page = PAGES[pattern];
      if (page === undefined) {
        throw new Error(`${pattern} has no page case.`);
      }
      const mounted = await mountIn(pattern, page.address, { kind: "answered", answers: emptyAnswers(pattern) ?? {} });
      for (const list of mounted.root.querySelectorAll('[data-slot="empty-list"]')) {
        const adds = list.querySelector('[data-slot="empty-adds"]')?.textContent ?? "";
        const by = list.querySelector('[data-slot="empty-by"]')?.textContent ?? "";
        expect(adds.trim().length, `${pattern}: no act that adds a row`).toBeGreaterThan(0);
        expect(by.trim().length, `${pattern}: no who`).toBeGreaterThan(0);
        expect(
          by === THE_INSTALL_RECORDS_THESE || Object.values(ROLE_WORDS).some((word) => by.includes(word)),
          `${pattern}: "${by}" names no role of the product and is not the install's sentence`,
        ).toBe(true);
        expect(CAUSE_WORDS.test(list.textContent ?? ""), `${pattern} says why a list is empty: ${list.textContent ?? ""}`).toBe(false);
      }
      const recorded = [...(BARE_STATES[pattern] ?? []), ...(BARE_LISTS[pattern] ?? [])].sort();
      expect(bareEmptySentences(mounted.root), `${pattern}: the paragraphs that say nothing is there`).toEqual(recorded);
    },
    60_000,
  );

  test("the empty-list element is drawn somewhere, so the check above is not over an empty set", async () => {
    // What breaks if this is deleted: `EmptyList` losing its `data-slot` in a rename, after which the
    // loop over `[data-slot="empty-list"]` above visits nothing on every page and passes.
    const people = "/people";
    const page = PAGES[people];
    if (page === undefined) {
      throw new Error("/people has no page case.");
    }
    const mounted = await mountIn(people, page.address, { kind: "answered", answers: emptyAnswers(people) ?? {} });
    const list = mounted.root.querySelector('[data-slot="empty-list"]');
    expect(list).not.toBeNull();
    expect(list?.querySelector('[data-slot="empty-by"]')?.textContent).toBe("A Super Admin or a Department admin adds one.");
  }, 60_000);
});
