/**
 * An approval opened on a phone, and the frame it opens in, held to what a phone actually does.
 *
 * `tests/approvals-page.test.tsx` holds the card to a phone's width and `tests/phone-width.test.tsx`
 * holds every page's values and the navigation's links. This file is what those two left open,
 * found by opening an approval inside the shell in Chrome at 320, 360 and 390 pixels on
 * 2026-09-16 with the console's own stylesheets, and each test is one of the findings:
 *
 * - the navigation was a wrapping row of twenty-nine links, 716 pixels tall at 360, so the card
 *   began 1003 pixels down and the first screen of an approval opened from a chat message held
 *   only the menu. After: the navigation is 95 pixels tall and the card begins at 385;
 * - Sign out was 41 pixels tall at 360 and 65 at 320, where its two words folded onto two lines,
 *   and each theme option was 20. After: 44 each;
 * - the reason field on a card was 15 pixels, under the size at which a phone's browser zooms
 *   the whole page in when a field takes focus. After: 16;
 * - a confirmed decision drew its sentence at the top of a page the person had scrolled down,
 *   after removing the button they pressed.
 *
 * No page scrolled sideways at any of the three widths either before or after.
 *
 * **The measurements are not the tests, and the tests do not pretend to be measurements.** jsdom
 * lays nothing out, so what is asserted is the declaration a phone applies to the rendered
 * element, through `support/cascade.ts`, which is the method `tests/phone-width.test.tsx`
 * argues for. The harness that measured is not committed, for the reason that file gives.
 *
 * Task ids: M40.6.1.5, M40.1.2.3
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  approvalAddress,
  APPROVALS_ADDRESS,
  APPROVE_LABEL,
  APPROVED_SENTENCE,
  REJECT_LABEL,
  REJECTED_SENTENCE,
} from "../src/pages/Approvals";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";
import {
  appliesAt,
  consoleRules,
  declared,
  pixels,
  specificity,
  type OrderedRule,
} from "./support/cascade";
import { COMPANY_CONSOLE, NAVIGATION_ADDRESS } from "./support/navigation";
import { backendPublicMessages } from "./support/python";
import { readConsoleFile } from "./support/repo";

const CONSOLE_ORIGIN = "https://console.test";
const QUEUE_API = "/api/v1/approvals";

/** The narrowest phone reflow is judged at, the phone the other files use, and a desktop. */
const SMALLEST_PHONE_PX = 320;
const PHONE_PX = 360;
const WIDE_PX = 1280;
/** The smallest tap target, in CSS pixels. */
const TAP_TARGET_PX = 44;
/** Below this, a phone's browser zooms the page in when a field takes focus. */
const FIELD_ZOOM_THRESHOLD_PX = 16;

const RULES: readonly OrderedRule[] = consoleRules();

/** The design tokens, so a length written as a token is compared as the length it stands for. */
const TOKENS: Readonly<Record<string, string>> = Object.fromEntries(
  RULES.filter((rule) => rule.selector === ":root" && rule.atRule === "").flatMap((rule) =>
    Object.entries(rule.declarations).filter(([property]) => property.startsWith("--")),
  ),
);

function resolved(value: string | undefined): string {
  return (value ?? "").replace(/var\((--[\w-]+)\)/g, (whole, name: string) => TOKENS[name] ?? whole);
}

beforeAll(async () => {
  await import("../src/pages/Approvals");
}, 60_000);

interface Answer {
  readonly status?: number;
  readonly body: unknown;
}

/**
 * The console at one address; a list of answers is given in order and its last repeated.
 *
 * The shell asks which console it is before it draws more than the reader's own work, so the
 * stand-in API gives the company console unless a test says otherwise, and the mount waits for
 * that answer as well as for the card: the frame's tests below are about the whole menu.
 */
async function consoleAt(
  path: string,
  given: Readonly<Record<string, Answer | readonly Answer[]>>,
): Promise<HTMLElement> {
  const answers: Readonly<Record<string, Answer | readonly Answer[]>> = {
    [NAVIGATION_ADDRESS]: { body: COMPANY_CONSOLE },
    ...given,
  };
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
      const list = Array.isArray(entry) ? (entry as readonly Answer[]) : [entry as Answer];
      const answer = list[Math.min(seen, list.length - 1)] as Answer;
      return new Response(JSON.stringify(answer.body), {
        status: answer.status ?? 200,
        headers: { "content-type": "application/json" },
      });
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (!container.querySelector("article.approval-card")) {
      throw new Error("the card has not arrived");
    }
    if (container.querySelector('nav [role="status"]')) {
      throw new Error("the menu has not been answered yet");
    }
  });
  return container;
}

function wireCard(id: string, artefact = "ticket.update_status on ticket"): Record<string, unknown> {
  return {
    suspension_id: id,
    artefact,
    runs_as: "u_asker",
    raised_at: "2019-03-04T09:00:00Z",
    expires_at: "2019-03-04T13:00:00Z",
  };
}

function button(root: Element, label: string): HTMLButtonElement {
  const found = [...root.querySelectorAll("button")].find((one) => one.textContent === label);
  if (!found) {
    throw new Error(`No button labelled ${label}.`);
  }
  return found;
}

function one(root: ParentNode, selector: string): Element {
  const found = root.querySelector(selector);
  if (!found) {
    throw new Error(`Nothing matches ${selector}.`);
  }
  return found;
}

/** The nearest element, from this one up, that a width declares a sideways scroll on. */
function sidewaysScroller(element: Element, width: number): Element | null {
  for (let at: Element | null = element; at !== null; at = at.parentElement) {
    const overflow = declared(at, "overflow-x", RULES, width) ?? declared(at, "overflow", RULES, width);
    if (overflow !== undefined && /\b(auto|scroll)\b/.test(overflow)) {
      return at;
    }
  }
  return null;
}

/**
 * Which of `font` and `font-size` sets this element's size at this width, and to what.
 *
 * `support/cascade.ts` reads one property at a time and knows nothing of shorthands, and `font:
 * inherit` is a shorthand that resets the size to the parent's, so asking it for `font-size`
 * alone would find a 16 pixel declaration that a later `font` in a stronger rule had undone. The
 * winning rule is taken across both names, and inside that rule the later of the two wins,
 * because `parseCss` keeps declarations in source order.
 */
function fontSizeFrom(element: Element, width: number): { property: string; value: string } {
  let best: { rank: [number, number, number]; order: number; rule: OrderedRule } | undefined;
  for (const rule of RULES) {
    if (!appliesAt(rule.atRule, width)) {
      continue;
    }
    if (rule.declarations["font"] === undefined && rule.declarations["font-size"] === undefined) {
      continue;
    }
    for (const part of rule.selector.split(",")) {
      const selector = part.trim();
      let hit = false;
      try {
        hit = element.matches(selector);
      } catch {
        hit = false;
      }
      if (!hit) {
        continue;
      }
      const rank = specificity(selector);
      const compared = best === undefined ? 1 : rank[0] - best.rank[0] || rank[1] - best.rank[1] || rank[2] - best.rank[2];
      if (best === undefined || compared > 0 || (compared === 0 && rule.order >= best.order)) {
        best = { rank, order: rule.order, rule };
      }
    }
  }
  if (best === undefined) {
    throw new Error("No rule sets this field's font, so it is whatever the browser's own sheet says.");
  }
  const last = Object.keys(best.rule.declarations)
    .filter((property) => property === "font" || property === "font-size")
    .at(-1) as string;
  return { property: last, value: best.rule.declarations[last] ?? "" };
}

// ------------------------------------------------------------------------ the frame

describe("the frame an approval opens in, on a phone", () => {
  test("the page is laid out at the phone's own width, and a person can still zoom it", () => {
    // What breaks if this is deleted: every phone rule in every sheet at once, because without a
    // viewport declaration a phone lays the page out 980 pixels wide and shrinks it, and no media
    // query written for 360 ever applies. And the other half: `maximum-scale=1` or
    // `user-scalable=no` stops somebody with poor eyesight zooming into the artefact they are
    // approving, which is the one text on the page they must be able to read.
    const html = readConsoleFile("index.html");
    const metas = [...html.matchAll(/<meta\s+name="viewport"\s+content="([^"]*)"\s*\/?>/g)];
    expect(metas).toHaveLength(1);

    const content = Object.fromEntries(
      (metas[0]?.[1] ?? "").split(",").map((pair) => pair.split("=").map((side) => side.trim())),
    );
    expect(content).toEqual({ width: "device-width", "initial-scale": "1" });
  });

  test("on a phone the navigation is one strip that scrolls inside itself, so the page starts on the first screen", async () => {
    // What breaks if this is deleted: the wrapping row coming back, which measured 716 pixels of
    // links above a card on a 360 pixel phone. Each property is the one that made the difference:
    // the groups side by side rather than stacked, each group's links on one line, a group that
    // does not shrink to fit, and the strip as the thing that scrolls. The last is asserted from
    // every link outwards, because a strip that did not scroll would push the whole page sideways
    // instead, which is the defect `tests/phone-width.test.tsx` exists to catch.
    const container = await consoleAt(approvalAddress("sus_1"), {
      [`${QUEUE_API}/sus_1`]: { body: wireCard("sus_1") },
    });
    const nav = one(container, "nav.shell__nav");
    const groups = [...nav.querySelectorAll(".shell__nav-group")];
    const links = [...nav.querySelectorAll("a")];
    expect(groups.length).toBeGreaterThan(1);
    expect(links.length).toBeGreaterThan(groups.length);

    expect(declared(nav, "display", RULES, PHONE_PX)).toBe("flex");
    expect(declared(nav, "flex-direction", RULES, PHONE_PX) ?? "row").toBe("row");
    for (const group of groups) {
      expect(declared(group, "flex", RULES, PHONE_PX)).toBe("0 0 auto");
      expect(declared(one(group, "ul"), "flex-wrap", RULES, PHONE_PX)).toBe("nowrap");
    }
    for (const link of links) {
      expect(declared(link, "white-space", RULES, PHONE_PX), link.textContent ?? "").toBe("nowrap");
      expect(sidewaysScroller(link, PHONE_PX), link.textContent ?? "").toBe(nav);
      expect(sidewaysScroller(link, SMALLEST_PHONE_PX), link.textContent ?? "").toBe(nav);
    }
    expect(sidewaysScroller(one(container, "article.approval-card"), PHONE_PX)).toBeNull();
  });

  test("a wider screen keeps the sidebar, whose links wrap inside it and which does not scroll sideways", async () => {
    // What breaks if this is deleted: the strip applied at every width, so a desktop sidebar
    // becomes one line of links scrolling sideways inside a 15rem column. The positive half of
    // the test above, which a sheet with no query at all would pass.
    const container = await consoleAt(approvalAddress("sus_1"), {
      [`${QUEUE_API}/sus_1`]: { body: wireCard("sus_1") },
    });
    const nav = one(container, "nav.shell__nav");

    expect(declared(nav, "display", RULES, WIDE_PX)).toBe("block");
    expect(sidewaysScroller(nav, WIDE_PX)).toBeNull();
    expect(declared(one(nav, "ul"), "flex-direction", RULES, WIDE_PX)).toBe("column");
    expect(declared(one(nav, "a"), "white-space", RULES, WIDE_PX)).toBe("normal");
    const second = nav.querySelectorAll(".shell__nav-group")[1] as Element;
    expect(pixels(resolved(declared(second, "margin-top", RULES, WIDE_PX)))).toBeGreaterThan(0);
  });

  test("every control in the frame's header is a thumb tall on a phone, and Sign out never folds onto two lines", async () => {
    // What breaks if this is deleted: Sign out at 41 pixels and each theme option at 20, in the
    // frame of every page. The theme's radio is a dozen pixels across, so the label around it is
    // the target, and it is asserted to hold the radio so the height is on what a thumb presses.
    // The header's actions wrap, so at 320 pixels Sign out moves to a line of its own rather
    // than folding its two words.
    const container = await consoleAt(approvalAddress("sus_1"), {
      [`${QUEUE_API}/sus_1`]: { body: wireCard("sus_1") },
    });
    const header = one(container, "header.shell__header");
    const signOut = button(header, "Sign out");
    const options = [...header.querySelectorAll("label.theme-control__option")];

    for (const width of [SMALLEST_PHONE_PX, PHONE_PX]) {
      expect(pixels(declared(signOut, "min-height", RULES, width) ?? "")).toBeGreaterThanOrEqual(TAP_TARGET_PX);
      expect(declared(signOut, "white-space", RULES, width)).toBe("nowrap");
      expect(declared(one(header, ".shell__header-actions"), "flex-wrap", RULES, width)).toBe("wrap");
      expect(options.length).toBeGreaterThan(1);
      for (const option of options) {
        expect(option.querySelector('input[type="radio"]')).not.toBeNull();
        expect(pixels(declared(option, "min-height", RULES, width) ?? "")).toBeGreaterThanOrEqual(TAP_TARGET_PX);
      }
    }
  });

  test("nothing a 320 pixel phone applies is wider than it", () => {
    // What breaks if this is deleted: a width between 320 and 360 pixels, which every other file
    // here passes because it judges at 360, and which scrolls sideways on the smallest phones
    // still in use and on a larger one zoomed to twice its size. 320 is the width reflow is
    // judged at. A token is compared as the length it stands for.
    const properties = ["width", "min-width", "inline-size", "min-inline-size", "flex-basis", "grid-template-columns"];
    const checked: string[] = [];
    for (const rule of RULES) {
      if (!appliesAt(rule.atRule, SMALLEST_PHONE_PX)) {
        continue;
      }
      for (const property of properties) {
        const value = rule.declarations[property];
        if (value === undefined) {
          continue;
        }
        checked.push(`${rule.selector} ${property}`);
        for (const length of resolved(value).matchAll(/-?\d*\.?\d+(?:px|rem|em)\b/g)) {
          expect(pixels(length[0]) ?? 0, `${rule.selector} { ${property}: ${value} }`).toBeLessThanOrEqual(
            SMALLEST_PHONE_PX,
          );
        }
      }
    }
    expect(checked).toEqual(expect.arrayContaining([".approval-list grid-template-columns", ".form-control width"]));
  });
});

// ------------------------------------------------------------------------- the card

describe("deciding an approval on a phone", () => {
  test("the reason a rejection needs is chosen in a field large enough that the phone does not zoom the page", async () => {
    // What breaks if this is deleted: a 15 pixel select, which a phone's browser answers by
    // zooming the page in when it takes focus and leaving it zoomed, so somebody choosing why
    // they reject an approval is left looking at a magnified corner of the card. Read from the
    // rendered field through `font` as well as `font-size`, because the shorthand resets the
    // size and a 16 pixel declaration it overrides would pass a reader that looked at one name.
    const container = await consoleAt(APPROVALS_ADDRESS, { [QUEUE_API]: { body: { items: [wireCard("sus_1")] } } });
    const select = one(container, "article.approval-card select");

    for (const width of [SMALLEST_PHONE_PX, PHONE_PX]) {
      const size = fontSizeFrom(select, width);
      expect(size.property).toBe("font-size");
      expect(pixels(resolved(size.value)) ?? 0).toBeGreaterThanOrEqual(FIELD_ZOOM_THRESHOLD_PX);
    }
  });

  test("a confirmed decision puts focus on the sentence saying so, in the queue and on a card opened from a link", async () => {
    // What breaks if this is deleted: on a phone the person has scrolled to the card, the queue
    // is asked again without it and the button they pressed is gone, and "Approved." is drawn at
    // the top of a page they are not looking at. Focus on the sentence scrolls it onto the
    // screen and has a screen reader read it. Both views, because the card on its own is where a
    // link from a chat message lands and loses its buttons rather than its card.
    const queue = await consoleAt(APPROVALS_ADDRESS, {
      [QUEUE_API]: [{ body: { items: [wireCard("sus_1"), wireCard("sus_2")] } }, { body: { items: [wireCard("sus_2")] } }],
      [`${QUEUE_API}/sus_1/decision`]: { body: { suspension_id: "sus_1", verdict: "approved" } },
    });
    fireEvent.click(button(one(queue, "article.approval-card"), APPROVE_LABEL));

    await waitFor(() => {
      expect(document.activeElement?.textContent).toBe(APPROVED_SENTENCE);
    });
    expect(document.activeElement?.tagName).toBe("P");
    expect(document.activeElement?.getAttribute("tabindex")).toBe("-1");

    const single = await consoleAt(approvalAddress("sus_1"), {
      [`${QUEUE_API}/sus_1`]: { body: wireCard("sus_1") },
      [`${QUEUE_API}/sus_1/decision`]: { body: { suspension_id: "sus_1", verdict: "rejected" } },
    });
    const card = one(single, "article.approval-card");
    fireEvent.change(one(card, "select"), { target: { value: "wrong_target" } });
    fireEvent.click(button(card, REJECT_LABEL));

    await waitFor(() => {
      expect(document.activeElement?.textContent).toBe(REJECTED_SENTENCE);
    });
    expect(single.contains(document.activeElement)).toBe(true);
  });

  test("a refused decision takes focus nowhere and is answered inside the card, beside the buttons that are still there", async () => {
    // What breaks if this is deleted: focus moved on any answer rather than on a confirmed one,
    // which on a refusal would scroll a phone away from the card the person still has to deal
    // with, or a refusal drawn at the top of the page where a phone does not show it. The
    // sentence is the API's own for an absent thing.
    const sentence = backendPublicMessages()["ABSENT"];
    const container = await consoleAt(approvalAddress("sus_1"), {
      [`${QUEUE_API}/sus_1`]: { body: wireCard("sus_1") },
      [`${QUEUE_API}/sus_1/decision`]: { status: 404, body: { message: sentence } },
    });
    const card = one(container, "article.approval-card");
    const before = document.activeElement;

    fireEvent.click(button(card, APPROVE_LABEL));

    await waitFor(() => {
      expect(card.querySelector(".approval-card__decision .notice__body")?.textContent).toBe(sentence);
    });
    expect(document.activeElement).toBe(before);
    expect(container.querySelector("p.note[tabindex]")).toBeNull();
    expect(button(card, APPROVE_LABEL).disabled).toBe(false);
  });
});
