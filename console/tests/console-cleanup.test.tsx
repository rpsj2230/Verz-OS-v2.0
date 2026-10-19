/**
 * What an administrator does not need is not on any page: no internal identifier in the text, no
 * developer's word for how the thing is built, no panel drawn twice, and every removal recorded with
 * its reason in `docs/console-cleanup.md`.
 *
 * **Read from the rendered pages, not from the source.** Every page the console registers is mounted
 * through the real route table and shell with the stand-in API of `support/pageCases.ts`, once with the
 * rows the fixtures carry and once with every list emptied, and the text it drew is read sentence by
 * sentence. A source search would find the word in a comment that explains why it is refused and miss
 * the identifier a page builds from a row, and an administrator reads the page. The Advanced section
 * (`kit/Advanced`) is the one place an identifier may appear, because it exists to quote one in a
 * support request, and it is removed before the text is read.
 *
 * **What is refused.** A UUID; a snake_case token; a schema-qualified table name; an address of the
 * API or a route parameter in braces; an acronym or word that says how the console is built (API,
 * JSON, HTTP, SQL, TODO, endpoint, payload, stub, backend and their kin); a stray `null`, `undefined`,
 * `NaN` or `[object` that is a bug drawn as text; and a heading drawn twice on one page, which is a
 * panel drawn twice. "Coming soon" is refused everywhere except as the lead of the kit's own note and
 * disabled-action reason, which is the owner's wording for a screen that is not built yet.
 *
 * **A small allowlist, each entry with its reason, and checked in both directions.** Some pages
 * exist to show an administrator exactly such a thing: the webhook address to paste into a chat
 * vendor, the name of a tool they put in a manifest, the API a connector is being added for. Each is
 * named by page and rule with why, and an entry that no longer matches anything on its page is refused,
 * so an excuse cannot outlive the thing it excused.
 *
 * **What was removed, and why, is a document.** `docs/console-cleanup.md` is held here to name each
 * removal with its reason, so a later cleanup has a record to extend and an excuse here has somewhere
 * to be argued.
 *
 * Task ids: M27.16.2
 */

import { readFileSync } from "node:fs";
import { afterEach, describe, expect, test } from "vitest";
import { cleanup } from "@testing-library/react";
import { COMPANY_CONSOLE, NAVIGATION_ADDRESS } from "./support/navigation";
import { PAGES } from "./support/pageCases";
import { emptyAnswers } from "./support/screenStateRules";
import { mountIn, sentencesOf } from "./support/screenStates";
import { REPO_ROOT, readRepoFile } from "./support/repo";

/** The console's namespaces, read out of the schema's own list so a new one is refused the day it exists. */
function schemaNames(): string[] {
  const source = readRepoFile("src/brain/db.py");
  const block = /SCHEMAS: dict\[str, str\] = \{([\s\S]*?)\n\}/.exec(source)?.[1];
  if (block === undefined) {
    throw new Error("Could not find SCHEMAS in src/brain/db.py; the cleanup sweep would check nothing.");
  }
  const names = [...block.matchAll(/^\s{4}"(\w+)":/gm)].map((one) => one[1] ?? "");
  if (names.length < 5) {
    throw new Error("SCHEMAS has too few names; the parser is stale.");
  }
  return names;
}

export type RuleId = "uuid" | "principal" | "snake" | "table" | "route" | "wording" | "bug";

interface Rule {
  readonly id: RuleId;
  /** Any one matching refuses the sentence. More than one where cases must differ. */
  readonly patterns: readonly RegExp[];
  readonly what: string;
}

export function rules(): readonly Rule[] {
  return [
    { id: "uuid", patterns: [/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i], what: "a unique identifier" },
    // A person's id as the platform spells it. Never excused on any page, so a page that is allowed
    // snake_case tool names cannot also print who did something by their id.
    { id: "principal", patterns: [/\b(?:u|p)_[A-Za-z0-9][A-Za-z0-9_-]*\b/], what: "a person's identifier" },
    { id: "snake", patterns: [/\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b/], what: "a snake_case identifier" },
    { id: "table", patterns: [new RegExp(`\\b(?:${schemaNames().join("|")})\\.[a-z_]{3,}\\b`)], what: "a table's name" },
    { id: "route", patterns: [/\/api\/|\/v1\/|\{[a-z_]+\}/], what: "an address of the API or a route's parameter" },
    {
      id: "wording",
      // Acronyms are matched as written, so an address that begins "https" is not one, and the plain
      // words are matched whatever their case unless they sit inside an address.
      patterns: [
        /\b(?:API|JSON|HTTP|SQL|TODO|YAML|UUID|ORM|NaN)\b/,
        /(?<![\w/:.-])(?:endpoint|payload|stub|backend|frontend|front-end|server-side|client-side|traceback|stack trace)\b/i,
      ],
      what: "a word for how the console is built",
    },
    { id: "bug", patterns: [/\[object\b|\bundefined\b|\bnull\b/], what: "a value drawn as text by mistake" },
  ];
}

// ------------------------------------------------------------------------------- the allowlist

const TOOL_NAMES =
  "A tool is named by what it is called in the agent's manifest and on the approval card that asks " +
  "whether it may run, and an administrator reads and writes that name, so it is drawn as it is.";
const FIELD_NAMES =
  "This page is the console's plain view of a table's own columns and fields, whose names are what a " +
  "grant, a policy row and a support conversation use, so it draws them unchanged (the page's own " +
  "comment argues it).";
const A_NAME_TYPED =
  "A name an administrator types when they write a rule or a connector, shown as an example of the " +
  "form it takes, or an account's own name.";
const AN_ADDRESS_TO_PASTE =
  "The address an administrator copies into the chat vendor's settings. It is the thing the page is for, " +
  "so it is drawn whole.";
const ADDING_AN_API =
  "This is where an administrator hands the product another company's API. The words are the " +
  "subject of the page, not how the console was built.";
const PASTE_A_DOCUMENT =
  "These inputs take a pasted document and the format is the instruction: the field would be unusable " +
  "without saying what to paste.";

/** Page, rule and why an administrator needs to see it. Checked: each must still match on its page. */
export const ALLOWED: Readonly<Record<string, Partial<Record<RuleId, string>>>> = {
  "/tools": { snake: TOOL_NAMES },
  "/tools/:name": { snake: TOOL_NAMES },
  "/approvals": { snake: TOOL_NAMES },
  "/approvals/:suspensionId": { snake: TOOL_NAMES },
  "/agents/drafts/:draftId": { snake: TOOL_NAMES },
  "/classification": { snake: FIELD_NAMES },
  "/classification/:entity": { snake: FIELD_NAMES },
  "/classification/:entity/:column": { snake: FIELD_NAMES },
  "/records/:entity": { snake: FIELD_NAMES },
  "/rules": { snake: A_NAME_TYPED, route: A_NAME_TYPED },
  "/service-accounts/:clientId": { snake: A_NAME_TYPED },
  "/channels/:name/:view": { route: AN_ADDRESS_TO_PASTE },
  "/connectors": { wording: ADDING_AN_API },
  "/connectors/new-api": { wording: ADDING_AN_API },
  "/features": { wording: PASTE_A_DOCUMENT },
};

// ----------------------------------------------------------------------------------- the walk

/** What each page's walk found, for the aggregate tests that read the whole console. */
const FOUND = new Map<string, Set<RuleId>>();
const HEADED = new Set<string>();

/** The text a page drew, sentence by sentence, outside Advanced. */
export function sentencesOutsideAdvanced(root: Element): string[] {
  const copy = root.cloneNode(true) as Element;
  copy.querySelectorAll("[data-slot='advanced']").forEach((one) => {
    one.remove();
  });
  return [...sentencesOf(copy)];
}

/** Every refusal in a list of sentences, as the rule it broke and the sentence. */
export function refusals(sentences: readonly string[]): { rule: RuleId; sentence: string }[] {
  const found: { rule: RuleId; sentence: string }[] = [];
  for (const whole of sentences) {
    // `Coming soon: ` leads the kit's note and a disabled action's reason, which the owner asked for;
    // anywhere else in a sentence it is refused below.
    const sentence = whole.replace(/^Coming soon: /, "");
    for (const one of rules()) {
      if (one.patterns.some((pattern) => pattern.test(sentence))) {
        found.push({ rule: one.id, sentence: whole });
      }
    }
    if (/coming soon/i.test(sentence)) {
      found.push({ rule: "wording", sentence: whole });
    }
  }
  return found;
}

/** Every string a stand-in answer carries, which is data the page was handed and did not write. */
export function dataIn(value: unknown, into: Set<string> = new Set()): Set<string> {
  if (typeof value === "string") {
    into.add(value);
  } else if (Array.isArray(value)) {
    value.forEach((one) => dataIn(one, into));
  } else if (typeof value === "object" && value !== null) {
    Object.values(value).forEach((one) => dataIn(one, into));
  }
  return into;
}

/**
 * Headings drawn more than once on a page, outside any visually hidden heading and outside what the
 * answer itself carried: a document whose first section has the document's own name is the data
 * repeating, not a panel drawn twice.
 */
export function repeatedHeadings(root: Element, data: ReadonlySet<string> = new Set()): string[] {
  const seen = new Map<string, number>();
  root.querySelectorAll("h1, h2, h3, h4").forEach((heading) => {
    if (heading.closest(".sr-only") !== null || heading.classList.contains("sr-only")) {
      return;
    }
    const text = (heading.textContent ?? "").replace(/\s+/g, " ").trim();
    if (data.has(text)) {
      return;
    }
    seen.set(text, (seen.get(text) ?? 0) + 1);
  });
  return [...seen].filter(([, count]) => count > 1).map(([text]) => text);
}

afterEach(() => {
  cleanup();
});

describe("what an administrator does not need is not on any page", () => {
  test.each(Object.keys(PAGES))("%s draws no internal identifier, no developer's word and no panel twice", async (pattern) => {
    // What breaks if this is deleted: the cleanup stops being held. A page that prints a UUID, a
    // principal's id, a table's name, "the API" or a heading twice is exactly what the owner asked to
    // have removed, and nothing else in the suite reads the words a page draws as an administrator
    // reads them.
    const page = PAGES[pattern];
    if (page === undefined) {
      throw new Error(`${pattern} has no page case.`);
    }
    const found = new Set<RuleId>();
    const states: Record<string, unknown>[] = [page.answers];
    const empty = emptyAnswers(pattern);
    if (empty !== null) {
      states.push(empty);
    }
    for (const answers of states) {
      const mounted = await mountIn(
        pattern,
        page.address,
        { kind: "answered", answers },
        false,
        page.answers[NAVIGATION_ADDRESS] ?? COMPANY_CONSOLE,
      );
      const allowed = ALLOWED[pattern] ?? {};
      const broken = refusals(sentencesOutsideAdvanced(mounted.root));
      for (const one of broken) {
        found.add(one.rule);
      }
      const unexcused = broken.filter((one) => allowed[one.rule] === undefined);
      expect(unexcused, `${pattern} says what an administrator does not need`).toEqual([]);
      expect(repeatedHeadings(mounted.root, dataIn(answers)), `${pattern} draws a heading twice`).toEqual([]);
      if (mounted.root.querySelector("h1, h2") !== null) {
        HEADED.add(pattern);
      }
    }
    FOUND.set(pattern, found);
  }, 60_000);

  test("every excuse still excuses something, and says why in a sentence", () => {
    // What breaks if this is deleted: an allowlist that only grows. An entry for a page that has been
    // cleaned stays on it for ever, and the next identifier added there is waved through.
    for (const [pattern, byRule] of Object.entries(ALLOWED)) {
      expect(PAGES[pattern], `${pattern} is excused but is not a page`).toBeDefined();
      for (const [rule, reason] of Object.entries(byRule)) {
        expect(FOUND.get(pattern)?.has(rule as RuleId), `${pattern} no longer draws ${rule}, so the excuse is stale`).toBe(true);
        expect((reason ?? "").split(" ").length, `${pattern}: the reason is not a reason`).toBeGreaterThan(10);
      }
    }
  });

  test("the sweep read the whole console, not a corner of it", () => {
    // What breaks if this is deleted: a walk that mounts nothing passes every rule above.
    expect(FOUND.size).toBeGreaterThan(100);
    expect(HEADED.size).toBeGreaterThan(60);
  });
});

describe("the rules refuse what they say they refuse and let plain words through", () => {
  test("each rule finds its own kind of text and none finds an ordinary sentence", () => {
    // What breaks if this is deleted: the sweep above is satisfied by rules that match nothing. Each
    // line is a thing an administrator was shown on the owner's install, with a sibling that is not.
    const refused: Record<RuleId, string> = {
      uuid: "Agent 6f1c2d3e-aaaa-4bbb-8ccc-1234567890ab is waiting",
      principal: "Stopped by u_admin 6 Mar 2019",
      snake: "Held by principal_id for this person",
      table: "Written to ops.acceptance_runs last night",
      route: "Sent to /api/v1/agents when you press Save",
      wording: "According to the API, nothing is waiting",
      bug: "Spent undefined this month",
    };
    for (const [rule, sentence] of Object.entries(refused)) {
      expect(refusals([sentence]).map((one) => one.rule), sentence).toContain(rule);
    }
    expect(refusals(["Coming soon: starting a rehearsal from here."])).toEqual([]);
    expect(refusals(["It is coming soon to the console."]).map((one) => one.rule)).toContain("wording");
    expect(
      refusals([
        "Nothing is waiting on you.",
        "Last 7 days",
        "Stopped 6 Mar 2019, 17:00.",
        "Rows of one kind of record, as this install holds them.",
        "The agent needs a second person to approve it.",
      ]),
    ).toEqual([]);
  });

  test("a heading drawn twice is found, and one hidden from the eye does not count", () => {
    // What breaks if this is deleted: duplicate panels pass the sweep, or a visually hidden heading
    // that labels a region is counted as a second copy.
    const document_ = new DOMParser().parseFromString(
      "<main><h1>Subscribers</h1><section><h2>Subscribers</h2></section><section><h2 class='sr-only'>Jobs</h2><h1>Jobs</h1></section></main>",
      "text/html",
    );
    expect(repeatedHeadings(document_.body)).toEqual(["Subscribers"]);
    // A heading the answer itself carried, twice, is the data repeating and not a panel drawn twice.
    expect(repeatedHeadings(document_.body, new Set(["Subscribers"]))).toEqual([]);
  });
});

describe("every removal is recorded with its reason", () => {
  test("docs/console-cleanup.md names what was removed, from where and why, and every excuse here is argued there", () => {
    // What breaks if this is deleted: the leaf asks that each removal be recorded with its reason, and
    // a cleanup nobody can read the reasons for is one the next person undoes to tidy a screen.
    const record = readFileSync(`${REPO_ROOT}/docs/console-cleanup.md`, "utf8");
    expect(record).toContain("# What the console no longer shows");
    const removed = record.slice(record.indexOf("## What was removed"), record.indexOf("## What is excused"));
    const removals = removed.split("\n").filter((line) => /^\| (?!What was removed|---)/.test(line));
    expect(removals.length).toBeGreaterThan(5);
    for (const line of removals) {
      const cells = line
        .split("|")
        .map((cell) => cell.trim())
        .filter((cell) => cell !== "");
      expect(cells.length, line).toBe(3);
      expect((cells[2] ?? "").split(" ").length, `no reason in: ${line}`).toBeGreaterThan(5);
    }
    for (const pattern of Object.keys(ALLOWED)) {
      expect(record, `${pattern} is excused here and not argued in the record`).toContain(`\`${pattern}\``);
    }
  });
});
