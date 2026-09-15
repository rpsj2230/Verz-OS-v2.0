/**
 * The approvals page: that a card is readable on a phone, and that the page draws what the API
 * returned and nothing else.
 *
 * **Readable on a phone is asserted as rules, because jsdom has no layout engine.** Nothing here
 * measures a rendered width; a test that claimed to would be measuring zero. What is asserted
 * is the set of rules that make a 360 pixel screen hold the page without scrolling sideways,
 * each read out of the stylesheet with comments stripped and each paired with the markup that
 * carries its class, because a rule for a class nothing renders and a class no rule styles are
 * both a layout that looks tested. The rules are: one column unless a `min-width` query says the
 * screen is wider, no width anywhere that a phone cannot hold, every long value allowed to
 * break, and a tap target no shorter than 44 pixels. `tests/data-table.test.tsx` makes the same
 * two-halves argument about the table's scrolling wrapper.
 *
 * **Reachable means through the application's own route table**, signed in through the real
 * session modules and answered by a stand-in API, as `tests/agents-roster.test.tsx` does.
 *
 * **"Nothing else" is compared as markup.** A body carrying a count, a tool call and a state
 * beside the cards renders byte for byte what the same cards render alone.
 *
 * **Deciding is driven through the buttons a person presses**, against a stand-in API that
 * answers the decision and then answers the queue again without the decided card. The body sent
 * is compared with the route's own document, and the reasons with the Python enum.
 *
 * Task ids: M35.3.1.2, M35.3.1.1
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  APPROVALS_ADDRESS,
  APPROVALS_HEADING,
  APPROVE_LABEL,
  approvalAddress,
  APPROVED_SENTENCE,
  MORE_APPROVALS,
  NO_APPROVALS,
  REJECT_LABEL,
  REJECTED_SENTENCE,
} from "../src/pages/Approvals";
import {
  decisionBody,
  readApprovalCard,
  readApprovalQueue,
  readDecision,
  REJECTION_REASONS,
} from "../src/pages/approvalsQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { asPythonName, backendHiddenCountNames, membersOf } from "./support/agentWorkspace";
import { consoleRules, declared } from "./support/cascade";
import { parseCss, type CssRule } from "./support/css";
import {
  declaredParameterNames,
  declaredProperty,
  declaredPropertyNames,
  declaredPropertySchema,
  declaredRequestBodySchema,
  declaredResponseSchema,
  resolvedSchema,
} from "./support/openapi";
import { backendEnumMembers, backendModelFields, backendPublicMessages } from "./support/python";
import { readConsoleFile } from "./support/repo";
import { parseConsoleSource, staticImportGraph } from "./support/typescript";

const CONSOLE_ORIGIN = "https://console.test";
const QUEUE_API = "/api/v1/approvals";
const QUEUE_ROUTE = "/api/v1/approvals";
const CARD_ROUTE = "/api/v1/approvals/{suspension_id}";
const ROUTE_MODULE = "src/brain/approval_routes.py";
const PAGE_MODULE = "src/pages/Approvals.tsx";
const SHEET = "src/styles/approvals.css";

/** The narrowest phone this page is held to, in CSS pixels. */
const PHONE_WIDTH_PX = 360;
/** The smallest tap target, in CSS pixels. */
const TAP_TARGET_PX = 44;
/** CSS pixels in one rem at the default root size, which the console does not change. */
const PX_PER_REM = 16;

/** The split page is transformed once, before anything is timed. */
beforeAll(async () => {
  await import("../src/pages/Approvals");
}, 60_000);

interface Answer {
  readonly status?: number;
  readonly body: unknown;
  readonly traceId?: string;
}

interface Mounted {
  readonly container: HTMLElement;
  readonly idp: FakeIdp;
}

/**
 * The console at one address over a stand-in API. An address given a list of answers gives them in
 * order and repeats the last, which is how a queue asked again after a decision comes back without
 * the card that was decided.
 */
async function consoleAt(
  path: string,
  answers: Readonly<Record<string, Answer | readonly Answer[]>>,
): Promise<Mounted> {
  const asked: Record<string, number> = {};
  const idp = fakeIdentityProvider({
    api(url) {
      const pathname = new URL(url, CONSOLE_ORIGIN).pathname;
      const entry = answers[pathname];
      if (entry === undefined) {
        return null;
      }
      const seen = asked[pathname] ?? 0;
      asked[pathname] = seen + 1;
      const answer: Answer | undefined = Array.isArray(entry)
        ? (entry as readonly Answer[])[Math.min(seen, (entry as readonly Answer[]).length - 1)]
        : (entry as Answer);
      if (answer === undefined) {
        return null;
      }
      return new Response(JSON.stringify(answer.body), {
        status: answer.status ?? 200,
        headers: {
          "content-type": "application/json",
          ...(answer.traceId ? { "x-trace-id": answer.traceId } : {}),
        },
      });
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (!container.querySelector("h1")) {
      throw new Error("the page has not arrived");
    }
  });
  await waitFor(() => {
    if (container.querySelector('p.note[role="status"]')) {
      throw new Error("the page is still asking");
    }
  });
  return { container, idp };
}

const LONG_TOKEN = "https://files.example.invalid/" + "x".repeat(240);
const ARTEFACT = `ticket.update_status on ticket\nagent: agent_test\neffect: write\n  note: ${LONG_TOKEN}`;

function wireCard(id: string, overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    suspension_id: id,
    artefact: ARTEFACT,
    runs_as: "u_asker_with_a_long_identifier_that_does_not_break_on_its_own",
    raised_at: "2019-03-04T09:00:00Z",
    expires_at: "2019-03-04T13:00:00Z",
    ...overrides,
  };
}

function page(container: HTMLElement): HTMLElement {
  const found = container.querySelector<HTMLElement>("article.page");
  if (!found) {
    throw new Error("No page was rendered.");
  }
  return found;
}

async function queueMarkup(body: unknown): Promise<string> {
  const { container } = await consoleAt(APPROVALS_ADDRESS, { [QUEUE_API]: { body } });
  return page(container).innerHTML;
}

function textOf(markup: string): string {
  const holder = document.createElement("div");
  holder.innerHTML = markup;
  return holder.textContent ?? "";
}

/** What a person reads on the page apart from the cards, whose times are digits by nature. */
function textOutsideCards(markup: string): string {
  const holder = document.createElement("div");
  holder.innerHTML = markup;
  holder.querySelectorAll("article.approval-card").forEach((card) => card.remove());
  return holder.textContent ?? "";
}

// ------------------------------------------------------------------ the stylesheet, read

/** Every rule in a sheet whose selector names one of these classes. */
function rulesFor(rules: readonly CssRule[], className: string): CssRule[] {
  return rules.filter((rule) =>
    rule.selector.split(",").some((one) => new RegExp(`\\.${className}(?![\\w-])`).test(one)),
  );
}

/** The one rule for a class outside any at-rule. Throws when there is none, or more than one. */
function baseRule(rules: readonly CssRule[], className: string): CssRule {
  const found = rulesFor(rules, className).filter((rule) => rule.atRule === "");
  if (found.length !== 1) {
    throw new Error(`Expected one base rule for .${className}, found ${found.length}.`);
  }
  return found[0] as CssRule;
}

/** A CSS length in pixels, or `undefined` for a value that is not an absolute length. */
function pixels(value: string): number | undefined {
  const match = /^(-?\d*\.?\d+)(px|rem|em)$/.exec(value.trim());
  if (!match) {
    return undefined;
  }
  const amount = Number(match[1]);
  return match[2] === "px" ? amount : amount * PX_PER_REM;
}

/** Every absolute length in a declaration's value, in pixels. */
function lengthsIn(value: string): number[] {
  return [...value.matchAll(/-?\d*\.?\d+(?:px|rem|em)\b/g)]
    .map((match) => pixels(match[0]))
    .filter((one): one is number => one !== undefined);
}

/** The narrowest screen an at-rule applies to: 0 for none, the figure for a `min-width` query. */
function narrowestScreen(atRule: string): number {
  if (atRule === "") {
    return 0;
  }
  const match = /^@media \(min-width: ([^)]+)\)$/.exec(atRule);
  const figure = match ? pixels(match[1] ?? "") : undefined;
  if (figure === undefined) {
    throw new Error(`${atRule} is not a min-width query, so a phone is not the base case here.`);
  }
  return figure;
}

const WIDTH_PROPERTIES = [
  "width",
  "min-width",
  "inline-size",
  "min-inline-size",
  "flex-basis",
  "grid-template-columns",
  "grid-auto-columns",
];

/** Declarations that can show an element somewhere other than where the markup puts it. */
const REORDERING = [
  "order",
  "grid-area",
  "grid-row",
  "grid-column",
  "grid-row-start",
  "grid-column-start",
  "grid-template-areas",
  "flex-direction",
  "position",
  "float",
];

/** Whether one of those declarations, with this value, actually moves anything. */
function reorders(property: string, value: string): boolean {
  if (property === "flex-direction") {
    return value.endsWith("-reverse");
  }
  if (property === "position") {
    return value === "absolute" || value === "fixed";
  }
  if (property === "float") {
    return value !== "none";
  }
  if (property === "order") {
    return value !== "0";
  }
  return true;
}

describe("an approval card on a phone", () => {
  const sheet = parseCss(readConsoleFile(SHEET));

  test("the queue is one column at a phone's width, and only a query for a wider screen adds one", () => {
    // What breaks if this is deleted: two cards side by side on a phone, each half of 360
    // pixels, or a desktop grid with a `max-width` query patched over it, where the phone is
    // the case the next edit forgets. The base rule is asserted, every other rule for the list
    // must sit in a `min-width` query, and the markup is asserted to carry the class the rule
    // styles, because neither half is evidence about the other.
    const list = baseRule(sheet, "approval-list");
    expect(list.declarations["display"]).toBe("grid");
    expect(list.declarations["grid-template-columns"]).toBe("minmax(0, 1fr)");

    for (const rule of sheet.filter((one) => one.atRule !== "")) {
      expect(() => narrowestScreen(rule.atRule)).not.toThrow();
    }
    const wider = rulesFor(sheet, "approval-list").filter((rule) => rule.atRule !== "");
    expect(wider.length).toBeGreaterThan(0);
    for (const rule of wider) {
      expect(narrowestScreen(rule.atRule)).toBeGreaterThan(PHONE_WIDTH_PX);
    }
  });

  test("no width in the approvals stylesheet is wider than the screen it applies to", () => {
    // What breaks if this is deleted: a `min-width: 24rem` on a card, or a track of `400px`,
    // and a page that scrolls sideways on every phone while looking right on the screen it
    // was written on. A value inside a `min-width` query is held to that query's own width,
    // and nowhere may a line be told not to wrap.
    const checked: string[] = [];
    for (const rule of sheet) {
      const screen = Math.max(narrowestScreen(rule.atRule), PHONE_WIDTH_PX);
      for (const [property, value] of Object.entries(rule.declarations)) {
        expect(`${rule.selector} ${property}: ${value}`).not.toMatch(/white-space: nowrap/);
        if (!WIDTH_PROPERTIES.includes(property)) {
          continue;
        }
        checked.push(`${rule.selector} ${property}`);
        for (const length of lengthsIn(value)) {
          expect(length, `${rule.selector} { ${property}: ${value} }`).toBeLessThanOrEqual(screen);
        }
      }
    }
    // A sheet with no width declarations at all would pass the loop above for nothing.
    expect(checked).toEqual(expect.arrayContaining([".approval-list grid-template-columns"]));
  });

  test("a long unbroken value breaks inside its card and the artefact keeps its own lines", async () => {
    // What breaks if this is deleted: a 240 character address in an artefact, or a long
    // principal id, pushing the card past the screen's edge. `pre` keeps a long line long;
    // `pre-wrap` keeps the artefact's line breaks and lets a line wrap, and `overflow-wrap:
    // anywhere` breaks a token with no spaces in it. The card itself may shrink below its
    // content. Each rule is paired with the element in the rendered card that carries it.
    const card = baseRule(sheet, "approval-card");
    expect(card.declarations["min-width"]).toBe("0");
    expect(card.declarations["max-width"]).toBe("100%");

    const artefact = baseRule(sheet, "approval-card__artefact");
    expect(artefact.declarations["white-space"]).toBe("pre-wrap");
    expect(artefact.declarations["overflow-wrap"]).toBe("anywhere");
    expect(baseRule(sheet, "approval-card__value").declarations["overflow-wrap"]).toBe("anywhere");

    const { container } = await consoleAt(APPROVALS_ADDRESS, {
      [QUEUE_API]: { body: { items: [wireCard("sus_1")] } },
    });
    const drawn = page(container).querySelector("ul.approval-list > li > article.approval-card");
    expect(drawn).not.toBeNull();
    expect(drawn?.querySelector("pre.approval-card__artefact")?.textContent).toBe(ARTEFACT);
    const values = [...(drawn?.querySelectorAll("dd.approval-card__value") ?? [])];
    expect(values.map((value) => value.textContent)).toContain(wireCard("sus_1")["runs_as"]);
  });

  test("a card opens with what will happen, and no rule a phone applies moves it later", async () => {
    // What breaks if this is deleted: a card whose first lines on a phone are who it runs as
    // and when it was raised, with the action being approved below the fold, or a stylesheet
    // `order` that puts it there while the markup still reads correctly to a screen reader.
    // Reading order is the markup, so the markup is asserted exactly. Visual order is the
    // markup only while nothing reorders it, so every declaration that could is refused on the
    // card and on everything inside it, at a phone's width, through the whole cascade.
    const { container } = await consoleAt(APPROVALS_ADDRESS, {
      [QUEUE_API]: { body: { items: [wireCard("sus_1")] } },
    });
    const drawn = page(container).querySelector("article.approval-card");
    expect(drawn).not.toBeNull();
    expect([...(drawn as Element).children].map((child) => child.getAttribute("class"))).toEqual([
      "approval-card__artefact",
      "approval-card__facts",
      "approval-card__decision",
      "approval-card__link",
    ]);

    const rules = consoleRules();
    const moved: string[] = [];
    for (const element of [drawn as Element, ...(drawn as Element).querySelectorAll("*")]) {
      for (const property of REORDERING) {
        const value = declared(element, property, rules, PHONE_WIDTH_PX);
        if (value !== undefined && reorders(property, value)) {
          moved.push(`${element.getAttribute("class") ?? element.tagName} { ${property}: ${value} }`);
        }
      }
    }
    expect(moved).toEqual([]);
  });

  test("a card's link and a section in the navigation are at least a thumb tall on a phone", async () => {
    // What breaks if this is deleted: a link a cursor can hit and a thumb cannot. The card's
    // link is held in the approvals sheet at every width. The navigation's links are read
    // through the cascade a 360 pixel screen applies to the link actually rendered, because the
    // shell's phone layout is its base rule rather than a query, and a height on a class
    // nothing renders is a tap target on nothing.
    const link = baseRule(sheet, "approval-card__link");
    expect(pixels(link.declarations["min-height"] ?? "")).toBeGreaterThanOrEqual(TAP_TARGET_PX);
    expect(link.declarations["display"]).toMatch(/flex|block/);

    const { container } = await consoleAt(APPROVALS_ADDRESS, {
      [QUEUE_API]: { body: { items: [wireCard("sus_1")] } },
    });
    expect(page(container).querySelector("article.approval-card a.approval-card__link")).not.toBeNull();
    const navLink = container.querySelector("nav a.shell__nav-link");
    expect(navLink).not.toBeNull();
    const height = declared(navLink as Element, "min-height", consoleRules(), PHONE_WIDTH_PX);
    expect(pixels(height ?? "")).toBeGreaterThanOrEqual(TAP_TARGET_PX);
  });

  test("the approvals sheet arrives with the page and is not in the first response", () => {
    // What breaks if this is deleted: the rules above held against a sheet nothing imports, or
    // a sheet imported by the entry, which every person downloads whether or not they ever
    // open approvals.
    const entry = new Set(staticImportGraph("src/main.tsx").files);
    expect([PAGE_MODULE, SHEET].filter((file) => entry.has(file))).toEqual([]);
    expect(staticImportGraph(PAGE_MODULE).files).toContain(SHEET);
  });
});

// -------------------------------------------------------------------------- what is drawn

describe("the approvals queue", () => {
  test("the queue draws the cards the API returned, in its order, each with what will happen", async () => {
    // What breaks if this is deleted: every refusal below is satisfied by a page that draws
    // nothing. The order is the API's, which put the soonest to lapse first.
    const { container } = await consoleAt(APPROVALS_ADDRESS, {
      [QUEUE_API]: { body: { items: [wireCard("sus_b"), wireCard("sus_a", { artefact: "second" })] } },
    });

    expect(container.querySelector("h1")?.textContent).toBe(APPROVALS_HEADING);
    const cards = [...page(container).querySelectorAll("article.approval-card")];
    expect(cards.map((card) => card.querySelector("pre")?.textContent)).toEqual([ARTEFACT, "second"]);
    expect(cards.map((card) => card.querySelector("a")?.getAttribute("href"))).toEqual([
      "/approvals/sus_b",
      "/approvals/sus_a",
    ]);
    expect([...cards[0]!.querySelectorAll("time")].map((time) => time.getAttribute("dateTime"))).toEqual([
      "2019-03-04T09:00:00Z",
      "2019-03-04T13:00:00Z",
    ]);
    expect(cards.map((card) => card.querySelectorAll("button.approval-card__action").length)).toEqual([2, 2]);
  });

  test("a count, a tool call or a state the API sends beside a card reaches nothing on the page", async () => {
    // What breaks if this is deleted: "1 of 47", or the capability and arguments `Card` was
    // built to keep off the screen, arriving because a route sent a field and a renderer was
    // generous. The leaky body must render byte for byte what the bare cards render.
    const bare = { items: [wireCard("sus_1")] };
    const leaky = {
      items: [
        {
          ...wireCard("sus_1"),
          capability: "write:ticket.status",
          arguments: { status: "CANARY-ARGS" },
          state: "pending",
          hidden_count: 4700,
        },
      ],
      total: 4700,
      hidden: 4700,
    };

    expect(readApprovalQueue(leaky)).toEqual(readApprovalQueue(bare));
    const markup = await queueMarkup(leaky);
    expect(markup).toBe(await queueMarkup(bare));
    expect(markup).not.toMatch(/4700|CANARY-ARGS|write:ticket/);
  });

  test("the answer and a card hold exactly the route's card fields and nothing about what was left out", () => {
    // What breaks if this is deleted: a `hiddenCount` on the answer, or a sixth card field
    // carrying the call. The card's members are compared with the Python model's own fields,
    // read from its source, and the forbidden names are `brain.ops.jobs`' own list.
    const forbidden = new Set(backendHiddenCountNames());
    const source = parseConsoleSource("src/pages/approvalsQuery.ts");

    expect(membersOf(source, "ApprovalQueueAnswer")).toEqual(["cards", "truncated"]);
    const cardMembers = membersOf(source, "ApprovalCardView");
    expect(cardMembers.map(asPythonName)).toEqual(backendModelFields(ROUTE_MODULE, "ApprovalCardView"));
    expect([...cardMembers, "cards", "truncated"].filter((member) => forbidden.has(asPythonName(member)))).toEqual([]);
  });

  test("a card that does not say what it is is not drawn, and an approval is drawn once", () => {
    // What breaks if this is deleted: a card with no artefact, which an approver would be
    // approving blind, or two cards for one approval whose keys collide. The artefact is kept
    // byte for byte, leading spaces included. The sibling card is carried.
    const spaced = "  indented first line\nsecond";
    const answer = readApprovalQueue({
      items: [
        wireCard("sus_1", { artefact: spaced }),
        wireCard("sus_1", { artefact: "a second copy" }),
        wireCard("", {}),
        wireCard("no_artefact", { artefact: "   " }),
        wireCard("no_runs_as", { runs_as: undefined }),
        wireCard("bad_time", { expires_at: "not a time" }),
        wireCard("no_raised", { raised_at: null }),
        { ...wireCard("numbered"), suspension_id: 7 },
        "sus_1",
        null,
      ],
    });

    expect(answer?.cards.map((card) => [card.suspensionId, card.artefact])).toEqual([["sus_1", spaced]]);
    expect(readApprovalCard(wireCard("sus_2"))?.runsAs).toBe(wireCard("sus_2")["runs_as"]);
  });

  test("an empty queue is one sentence, whatever else the body says, and it has no number in it", async () => {
    // What breaks if this is deleted: an empty queue that says why it is empty or counts what
    // it withheld. Nothing in the store and nothing in this reader's reach are one screen.
    const empty = await queueMarkup({ items: [] });

    expect(empty).toBe(await queueMarkup({ items: [], total: 12, hidden: 12 }));
    expect(empty).toContain(NO_APPROVALS);
    expect(textOf(empty)).not.toMatch(/\d/);
    expect(await queueMarkup({ items: [wireCard("sus_1")] })).not.toContain(NO_APPROVALS);
  });

  test("a body that is not a queue draws no list and composes no sentence about it", async () => {
    // What breaks if this is deleted: another API's body drawn as an empty queue, which tells
    // a person nothing is waiting on them on no evidence.
    for (const unreadable of [null, [], {}, { items: "sus_1" }]) {
      expect(readApprovalQueue(unreadable)).toBeNull();
    }
    expect(readApprovalQueue({ items: [] })).toEqual({ cards: [], truncated: false });

    const markup = await queueMarkup({});
    expect(markup).not.toContain(NO_APPROVALS);
    expect(markup).not.toContain("approval-list");
  });

  test("a truncated queue says there is more, without a figure, and only when the API says exactly that", async () => {
    // What breaks if this is deleted: "and 12 more", or a truncation claim read out of a
    // string or a number.
    const truncated = await queueMarkup({ items: [wireCard("sus_1")], truncated: true });
    expect(truncated).toContain(MORE_APPROVALS);
    expect(textOutsideCards(truncated)).not.toMatch(/\d/);
    expect(textOutsideCards(truncated)).toContain(MORE_APPROVALS);
    expect(await queueMarkup({ items: [wireCard("sus_1")] })).not.toContain(MORE_APPROVALS);

    for (const notTrue of [false, "true", 1, undefined]) {
      expect(readApprovalQueue({ items: [], truncated: notTrue })?.truncated).toBe(false);
    }
  });

  test("a refusal is the API's own sentence and its reference, with no queue drawn", async () => {
    // What breaks if this is deleted: a page that explains a refusal in its own words, or
    // draws an empty queue over one.
    const sentence = backendPublicMessages()["FAILED"];
    expect(sentence).toBeTruthy();

    const { container } = await consoleAt(APPROVALS_ADDRESS, {
      [QUEUE_API]: { status: 500, body: { message: sentence }, traceId: "trace-queue" },
    });

    expect(container.querySelector(".notice__body")?.textContent).toBe(sentence);
    expect(container.querySelector(".notice__trace code")?.textContent).toBe("trace-queue");
    expect(container.querySelector("ul.approval-list")).toBeNull();
    expect(container.textContent).not.toContain(NO_APPROVALS);
  });

  test("every name the page reads is a name the routes declare, and a card declares no more", () => {
    // What breaks if this is deleted: the page and the routes drifting apart on a name, or a
    // route that started sending a card's call or state. The card's set is exact.
    const queue = declaredResponseSchema(QUEUE_ROUTE, "get");
    const card = ["artefact", "expires_at", "raised_at", "runs_as", "suspension_id"];

    expect(declaredPropertyNames(queue)).toEqual(expect.arrayContaining(["items", "truncated"]));
    expect(declaredPropertyNames(declaredProperty(queue, "items"))).toEqual(card);
    expect(declaredPropertyNames(declaredResponseSchema(CARD_ROUTE, "get"))).toEqual(card);
    expect(declaredParameterNames(CARD_ROUTE, "get", "path")).toEqual(["suspension_id"]);
  });
});

// ---------------------------------------------------------------------- one approval

describe("one approval on its own", () => {
  test("one approval asks its own address, encoded, and draws its card with no link to itself", async () => {
    // What breaks if this is deleted: the page a chat link lands on asking the whole queue, or
    // an id with a slash in it asking a different address.
    const { container, idp } = await consoleAt(approvalAddress("sus/1"), {
      [`${QUEUE_API}/sus%2F1`]: { body: wireCard("sus/1") },
    });

    const asked = idp.urls
      .map((url) => new URL(url, CONSOLE_ORIGIN).pathname)
      .filter((path) => path.startsWith(QUEUE_API));
    expect(asked).toEqual([`${QUEUE_API}/sus%2F1`]);
    const cards = page(container).querySelectorAll("article.approval-card");
    expect(cards).toHaveLength(1);
    expect(cards[0]?.querySelector("pre")?.textContent).toBe(ARTEFACT);
    expect(cards[0]?.querySelector("a")).toBeNull();
  });

  test("an approval that is not the reader's is the API's sentence and nothing else", async () => {
    // What breaks if this is deleted: "you cannot decide this one", which says the approval
    // exists. The sentence is the one the Python side sends for an absent thing.
    const sentence = backendPublicMessages()["ABSENT"];
    const { container } = await consoleAt(approvalAddress("sus_1"), {
      [`${QUEUE_API}/sus_1`]: { status: 404, body: { message: sentence }, traceId: "trace-one" },
    });

    expect(container.querySelector(".notice__body")?.textContent).toBe(sentence);
    expect(page(container).querySelector("article.approval-card")).toBeNull();
  });

  test("approvals are in the navigation, for everybody, at the address a card links to", async () => {
    // What breaks if this is deleted: a queue reachable only by typing its address, which on a
    // phone is a queue nobody reaches.
    const { container } = await consoleAt("/", { [QUEUE_API]: { body: { items: [] } } });
    const nav = [...container.querySelectorAll("nav a")].map((link) => [
      link.textContent ?? "",
      link.getAttribute("href") ?? "",
    ]);

    expect(nav).toContainEqual([APPROVALS_HEADING, APPROVALS_ADDRESS]);
    expect(approvalAddress("sus_1").startsWith(`${APPROVALS_ADDRESS}/`)).toBe(true);
  });
});

// -------------------------------------------------------------------------- deciding

const DECISION_ROUTE = "/api/v1/approvals/{suspension_id}/decision";

/** Every POST the console made under the approvals API, with its parsed body. */
function posts(idp: FakeIdp): { path: string; body: unknown }[] {
  return idp.calls
    .filter((call) => call.init?.method === "POST")
    .map((call) => ({ path: new URL(call.url, CONSOLE_ORIGIN).pathname, body: call.init?.body }))
    .filter((call) => call.path.startsWith(QUEUE_API))
    .map((call) => ({ path: call.path, body: JSON.parse(String(call.body)) as unknown }));
}

function button(root: Element, label: string): HTMLButtonElement {
  const found = [...root.querySelectorAll("button")].find((one) => one.textContent === label);
  if (!found) {
    throw new Error(`No button labelled ${label}.`);
  }
  return found;
}

describe("deciding an approval", () => {
  test("approving a card in the queue sends that card's approval, and the queue is asked again without it", async () => {
    // What breaks if this is deleted: a button that approves the wrong card, sends a body the
    // route does not take, or leaves the decided card on the screen to be pressed again. The
    // queue's second answer is what the API says after the decision, and the page draws it.
    const { container, idp } = await consoleAt(APPROVALS_ADDRESS, {
      [QUEUE_API]: [
        { body: { items: [wireCard("sus_1"), wireCard("sus_2", { artefact: "second" })] } },
        { body: { items: [wireCard("sus_2", { artefact: "second" })] } },
      ],
      [`${QUEUE_API}/sus_1/decision`]: { body: { suspension_id: "sus_1", verdict: "approved" } },
    });
    const first = page(container).querySelectorAll("article.approval-card")[0] as Element;

    fireEvent.click(button(first, APPROVE_LABEL));

    await waitFor(() => {
      expect(page(container).querySelectorAll("article.approval-card pre")[0]?.textContent).toBe("second");
    });
    expect(page(container).querySelectorAll("article.approval-card")).toHaveLength(1);
    expect(posts(idp)).toEqual([{ path: `${QUEUE_API}/sus_1/decision`, body: { verdict: "approved" } }]);
    expect(idp.urls.filter((url) => new URL(url, CONSOLE_ORIGIN).pathname === QUEUE_API)).toHaveLength(2);
    expect(page(container).textContent).toContain(APPROVED_SENTENCE);
  });

  test("a rejection is not sent until a reason is chosen, and is then sent with that reason", async () => {
    // What breaks if this is deleted: a reject button that sends a rejection with no why, which
    // the route refuses after a round trip, or one that sends the wrong code. After the answer
    // confirms it, the card on its own says so and offers nothing more to press.
    const { container, idp } = await consoleAt(approvalAddress("sus_1"), {
      [`${QUEUE_API}/sus_1`]: { body: wireCard("sus_1") },
      [`${QUEUE_API}/sus_1/decision`]: { body: { suspension_id: "sus_1", verdict: "rejected" } },
    });
    const card = page(container).querySelector("article.approval-card") as Element;

    expect(button(card, REJECT_LABEL).disabled).toBe(true);
    fireEvent.click(button(card, REJECT_LABEL));
    expect(posts(idp)).toEqual([]);

    fireEvent.change(card.querySelector("select") as HTMLSelectElement, { target: { value: "wrong_target" } });
    expect(button(card, REJECT_LABEL).disabled).toBe(false);
    fireEvent.click(button(card, REJECT_LABEL));

    await waitFor(() => {
      expect(page(container).textContent).toContain(REJECTED_SENTENCE);
    });
    expect(posts(idp)).toEqual([
      { path: `${QUEUE_API}/sus_1/decision`, body: { verdict: "rejected", reason_code: "wrong_target" } },
    ]);
    expect(page(container).querySelector("article.approval-card button")).toBeNull();
  });

  test("a decision the API refuses shows the API's sentence and claims nothing was decided", async () => {
    // What breaks if this is deleted: "Approved." on a card somebody else had already decided,
    // or a refusal in the page's own words that tells the reader why. The sentence is the one
    // the Python side sends for an absent thing, and the buttons stay where they were.
    const sentence = backendPublicMessages()["ABSENT"];
    const { container } = await consoleAt(approvalAddress("sus_1"), {
      [`${QUEUE_API}/sus_1`]: { body: wireCard("sus_1") },
      [`${QUEUE_API}/sus_1/decision`]: { status: 404, body: { message: sentence }, traceId: "trace-decide" },
    });
    const card = page(container).querySelector("article.approval-card") as Element;

    fireEvent.click(button(card, APPROVE_LABEL));

    await waitFor(() => {
      expect(card.querySelector(".notice__body")?.textContent).toBe(sentence);
    });
    expect(card.querySelector(".notice__trace code")?.textContent).toBe("trace-decide");
    expect(page(container).textContent).not.toContain(APPROVED_SENTENCE);
    expect(button(card, APPROVE_LABEL).disabled).toBe(false);
  });

  test("the reasons offered are the route's reasons, and the body and the answer are the route's shapes", () => {
    // What breaks if this is deleted: a reason the console offers that the route refuses, a
    // reason the route takes that nobody can pick, or a body key the route does not declare.
    // Held against the Python enum and against the route's own document, both ways.
    const reasons = Object.values(backendEnumMembers("src/brain/approval_routes.py", "RejectionReason")).sort();
    expect(Object.keys(REJECTION_REASONS).sort()).toEqual(reasons);

    const reasonSchema = declaredPropertySchema(DECISION_ROUTE, "post", "reason_code");
    const reference = (reasonSchema["anyOf"] as Record<string, unknown>[] | undefined)?.find(
      (one) => typeof one["$ref"] === "string",
    );
    expect(reference).toBeDefined();
    expect([...(resolvedSchema(reference as Record<string, unknown>)["enum"] as string[])].sort()).toEqual(reasons);
    expect([...(declaredPropertySchema(DECISION_ROUTE, "post", "verdict")["enum"] as string[])].sort()).toEqual([
      "approved",
      "rejected",
    ]);

    const declared = declaredPropertyNames(declaredRequestBodySchema(DECISION_ROUTE, "post"));
    for (const reason of reasons) {
      const body = decisionBody({ verdict: "rejected", reasonCode: reason });
      expect(body).toEqual({ verdict: "rejected", reason_code: reason });
      expect(Object.keys(body ?? {}).filter((key) => !declared.includes(key))).toEqual([]);
    }
    expect(decisionBody({ verdict: "approved" })).toEqual({ verdict: "approved" });
    expect(decisionBody({ verdict: "rejected", reasonCode: "" })).toBeNull();
    expect(decisionBody({ verdict: "rejected", reasonCode: "constructor" })).toBeNull();

    expect(declaredPropertyNames(declaredResponseSchema(DECISION_ROUTE, "post"))).toEqual(["suspension_id", "verdict"]);
    expect(readDecision({ suspension_id: "sus_1", verdict: "approved" }, "sus_1")).toBe("approved");
    expect(readDecision({ suspension_id: "sus_2", verdict: "approved" }, "sus_1")).toBeNull();
    expect(readDecision({ suspension_id: "sus_1", verdict: "taken_over" }, "sus_1")).toBeNull();
  });

  test("the decision's controls are a thumb tall and wrap inside the card at a phone's width", async () => {
    // What breaks if this is deleted: two buttons a cursor can hit and a thumb cannot, or a
    // reason field that holds its row open past the edge of a 360 pixel card. The rules are read
    // out of the sheet and paired with the rendered markup that carries each class.
    const sheet = parseCss(readConsoleFile(SHEET));
    expect(pixels(baseRule(sheet, "approval-card__action").declarations["min-height"] ?? "")).toBeGreaterThanOrEqual(
      TAP_TARGET_PX,
    );
    expect(pixels(baseRule(sheet, "approval-card__choice").declarations["min-height"] ?? "")).toBeGreaterThanOrEqual(
      TAP_TARGET_PX,
    );
    expect(baseRule(sheet, "approval-card__decision").declarations["flex-wrap"]).toBe("wrap");
    const reason = baseRule(sheet, "approval-card__reason");
    expect(reason.declarations["min-width"]).toBe("0");
    expect(reason.declarations["flex"]).toBe("1 1 100%");

    const { container } = await consoleAt(APPROVALS_ADDRESS, {
      [QUEUE_API]: { body: { items: [wireCard("sus_1")] } },
    });
    const drawn = page(container).querySelector("article.approval-card > div.approval-card__decision");
    expect(drawn).not.toBeNull();
    expect(
      [...(drawn as Element).querySelectorAll("button.button.approval-card__action")].map((one) => one.textContent),
    ).toEqual([APPROVE_LABEL, REJECT_LABEL]);
    expect((drawn as Element).querySelector("label.approval-card__reason > select.form-control.approval-card__choice")).not.toBeNull();
  });
});
