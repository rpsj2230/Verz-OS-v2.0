/**
 * Getting round this console without a mouse.
 *
 * **Every control here is a native element, and that is the whole of the keyboard story.**
 * A `button` is focusable, is announced as a button, and activates on Enter and Space
 * without anybody writing a handler; a `div` with an `onClick` does none of those and looks
 * identical to the person who added it. So the property worth asserting is not that some
 * keyboard handler exists, it is that nothing in the frame needs one.
 *
 * `scripts/check-boundaries.mjs` refuses the two source patterns that break this, a click
 * handler on an element the keyboard cannot reach and a positive `tabIndex`. This file asks
 * the rendered question instead: what actually takes focus, in what order, and is the ring
 * that shows it defined in both themes. Neither check subsumes the other. The script reads
 * source and cannot see what renders; these tests render and cannot see a file nobody
 * imported.
 *
 * The skip link is the one piece of markup that exists only for this. Without it, reaching
 * the page content from the keyboard means tabbing past every navigation item, on every
 * page, every time.
 *
 * Task ids: M35.2.2.1, M35.2.2.2
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { MemoryRouter } from "react-router-dom";
import { render } from "@testing-library/react";
import { describe, expect, test } from "vitest";

/** Elements a browser puts in the tab order without being asked. */
const NATIVE_CONTROLS = new Set(["A", "BUTTON", "INPUT", "SELECT", "TEXTAREA"]);

/** Everything the tab key would stop on, in document order. */
function focusables(root: HTMLElement): HTMLElement[] {
  const candidates = root.querySelectorAll<HTMLElement>(
    "a[href], button, input, select, textarea, [tabindex]",
  );
  return [...candidates].filter((element) => element.getAttribute("tabindex") !== "-1");
}

async function renderShell(): Promise<HTMLElement> {
  const { Shell } = await import("../src/layout/Shell");
  const { container } = render(
    <MemoryRouter initialEntries={["/"]}>
      <Shell />
    </MemoryRouter>,
  );
  return container;
}

/**
 * The token stylesheet, read from disk rather than imported.
 *
 * Imported, Vite would hand back a processed string and the test would be asserting on
 * whatever the pipeline produced. Read from `process.cwd()`, which vitest sets to the
 * console directory, so this is the file a person edits.
 */
function tokens(): string {
  return readFileSync(resolve(process.cwd(), "src/theme/tokens.css"), "utf8");
}

describe("getting round without a mouse", () => {
  test("the first thing the tab key reaches is the skip link, and it goes somewhere", async () => {
    // What breaks if this is deleted: the skip link keeps working while quietly moving down
    // the DOM, which makes it useless. A skip link that is not first is a control somebody
    // reaches after tabbing past the thing it exists to skip.
    const container = await renderShell();
    const [first] = focusables(container);

    expect(first).toBeDefined();
    expect(first.tagName).toBe("A");
    expect(first.textContent).toMatch(/skip/i);

    const target = first.getAttribute("href") ?? "";
    expect(target.startsWith("#")).toBe(true);
    expect(container.querySelector(target)).not.toBeNull();
  });

  test("everything the tab key reaches is a native control", async () => {
    // What breaks if this is deleted: a div with a click handler renders identically, works
    // for a mouse, and does not exist for anybody else. The boundary script refuses that
    // pattern in source; this is the same claim asked of what actually rendered, which is
    // what catches it arriving through a component from a library.
    const container = await renderShell();
    const reachable = focusables(container);

    expect(reachable.length).toBeGreaterThan(1);
    for (const element of reachable) {
      expect(NATIVE_CONTROLS.has(element.tagName)).toBe(true);
    }
  });

  test("nothing in the frame reorders the tab order", async () => {
    // What breaks if this is deleted: one positive tabindex lifts an element ahead of every
    // control with a zero, which is all of them, and the resulting order is not the one
    // anybody reading the markup would predict.
    const container = await renderShell();

    for (const element of focusables(container)) {
      const declared = element.getAttribute("tabindex");
      expect(declared === null || Number(declared) <= 0).toBe(true);
    }
  });

  test("the focus colour is defined in every theme the console has", () => {
    // What breaks if this is deleted: the ring is drawn in a colour that only exists in the
    // light palette, so on a dark screen the outline is whatever a missing custom property
    // falls back to, which is nothing at all. The boundary script asserts a ring is drawn;
    // this asserts it can be seen.
    const css = tokens();
    const blocks = [
      /:root\s*\{[^}]*--focus:/,
      /@media \(prefers-color-scheme: dark\)[^{]*\{\s*:root:not\(\[data-theme="light"\]\)\s*\{[^}]*--focus:/,
      /:root\[data-theme="dark"\]\s*\{[^}]*--focus:/,
    ];

    for (const block of blocks) {
      expect(block.test(css)).toBe(true);
    }
  });
});
