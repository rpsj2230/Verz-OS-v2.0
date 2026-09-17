/**
 * Which declaration a screen of a given width applies to an element, read out of the console's
 * own stylesheets, so a test can ask what a phone is told without pretending to lay anything out.
 *
 * **This is a cascade and not a layout, and the difference is the whole of what it can prove.**
 * jsdom matches selectors and computes no box, so no test here can say a page is 360 pixels
 * wide. What it can say is which `white-space`, `overflow-wrap`, `min-height` or
 * `flex-direction` wins for a rendered element when the media queries a phone matches are
 * applied and the ones it does not match are not, and those are the declarations that decide
 * whether a long value pushes the page sideways. The measurement that the declarations do what
 * they are argued to do was taken in a real browser and is recorded in `styles/app.css`.
 *
 * **Rejected: jsdom's own `getComputedStyle`.** It reads stylesheets that are attached to the
 * document, and these are read from disk, because an imported sheet arrives through Vite's
 * pipeline as whatever it produced. It also ignores media queries entirely, which is the one
 * input this module exists to vary.
 *
 * What it models, and deliberately nothing more:
 * - a rule outside any at-rule applies at every width, a `min-width` or `max-width` query
 *   applies where it matches, and any other query about width throws rather than guessing;
 * - a query about something other than width (`prefers-color-scheme`, `prefers-reduced-motion`)
 *   is treated as not matching, which is right for every property a layout test reads;
 * - the winner is the highest specificity and then the latest rule, across the sheets in the
 *   order a page receives them. `!important` is not modelled; the one sheet using it does so
 *   inside `prefers-reduced-motion`, which is never applied here.
 *
 * A selector jsdom cannot match, such as one with a pseudo-element, is treated as not matching
 * an element, which is what a pseudo-element selector does to the element itself.
 */

import { parseCss, type CssRule } from "./css";
import { readConsoleFile } from "./repo";

/** CSS pixels in one rem at the default root size, which the console does not change. */
export const PX_PER_REM = 16;

/**
 * Every stylesheet in the console, in the order a page importing all of them receives them:
 * the tokens and the application sheet from the entry, then the sheets a page imports.
 */
export const CONSOLE_SHEETS = [
  "src/theme/tokens.css",
  "src/styles/app.css",
  "src/styles/approvals.css",
  "src/styles/agent-workspace.css",
] as const;

export interface OrderedRule extends CssRule {
  /** The sheet the rule came from, relative to the console. */
  readonly sheet: string;
  /** Its position across every sheet, which breaks a tie in specificity. */
  readonly order: number;
}

/** Every rule in the named sheets, numbered in the order a page receives them. */
export function consoleRules(sheets: readonly string[] = CONSOLE_SHEETS): OrderedRule[] {
  const rules: OrderedRule[] = [];
  for (const sheet of sheets) {
    for (const rule of parseCss(readConsoleFile(sheet))) {
      rules.push({ ...rule, sheet, order: rules.length });
    }
  }
  return rules;
}

/** A CSS length in pixels, or `undefined` for a value that is not an absolute length. */
export function pixels(value: string): number | undefined {
  const match = /^(-?\d*\.?\d+)(px|rem|em)$/.exec(value.trim());
  if (!match) {
    return undefined;
  }
  const amount = Number(match[1]);
  return match[2] === "px" ? amount : amount * PX_PER_REM;
}

/** The two shapes of width query this console may write, and nothing else. */
const WIDTH_QUERY = /^@media \((min|max)-width: ([^)]+)\)$/;

/** Whether an at-rule applies to a screen this many CSS pixels wide. */
export function appliesAt(atRule: string, width: number): boolean {
  if (atRule === "") {
    return true;
  }
  const match = WIDTH_QUERY.exec(atRule);
  if (match) {
    const figure = pixels(match[2] ?? "");
    if (figure === undefined) {
      throw new Error(`${atRule} has a width this reader cannot turn into pixels.`);
    }
    return match[1] === "min" ? width >= figure : width <= figure;
  }
  if (/width/.test(atRule)) {
    throw new Error(`${atRule} asks about width in a shape this reader does not model.`);
  }
  return false;
}

/** Selector specificity as (ids, classes and attributes and pseudo-classes, types). */
export function specificity(selector: string): [number, number, number] {
  const bare = selector.replace(/::[\w-]+(\([^)]*\))?/g, "");
  const count = (pattern: RegExp) => (bare.match(pattern) ?? []).length;
  const ids = count(/#[\w-]+/g);
  const classes =
    count(/\.[\w-]+/g) + count(/\[[^\]]*\]/g) + count(/:(?!not\(|is\(|where\()[\w-]+/g);
  const stripped = bare
    .replace(/\[[^\]]*\]/g, " ")
    .replace(/[.#:][\w-]+/g, " ")
    .replace(/[()]/g, " ");
  const types = (stripped.match(/(^|[\s>+~])[a-zA-Z][\w-]*/g) ?? []).length;
  return [ids, classes, types];
}

function outranks(a: [number, number, number], b: [number, number, number]): number {
  for (let index = 0; index < 3; index += 1) {
    const difference = (a[index] ?? 0) - (b[index] ?? 0);
    if (difference !== 0) {
      return difference;
    }
  }
  return 0;
}

function matches(element: Element, selector: string): boolean {
  try {
    return element.matches(selector);
  } catch {
    return false;
  }
}

/**
 * A selector list split at its top-level commas.
 *
 * The console's own sheets never put a list inside `:where()` or `:is()`, so splitting at every
 * comma was enough for them. The stylesheet Tailwind compiles for the component layer does
 * (`theme/preflight.css` narrows every rule with `:where(a, b, c)`), and a naive split hands the
 * browser's matcher an unbalanced fragment, which jsdom's matcher accepts and matches, so a reset
 * meant for an image was reported as applying to a drawer.
 */
export function selectorList(selector: string): string[] {
  const parts: string[] = [];
  let depth = 0;
  let start = 0;
  for (let index = 0; index < selector.length; index += 1) {
    const character = selector[index];
    if (character === "(" || character === "[") {
      depth += 1;
    } else if (character === ")" || character === "]") {
      depth -= 1;
    } else if (character === "," && depth === 0) {
      parts.push(selector.slice(start, index).trim());
      start = index + 1;
    }
  }
  parts.push(selector.slice(start).trim());
  return parts;
}

/** The value of one property declared for this element at this width, or `undefined`. */
export function declared(
  element: Element,
  property: string,
  rules: readonly OrderedRule[],
  width: number,
): string | undefined {
  let best: { rank: [number, number, number]; order: number; value: string } | undefined;
  for (const rule of rules) {
    const value = rule.declarations[property];
    if (value === undefined || !appliesAt(rule.atRule, width)) {
      continue;
    }
    for (const selector of selectorList(rule.selector)) {
      if (!matches(element, selector)) {
        continue;
      }
      const rank = specificity(selector);
      const beats =
        best === undefined ||
        outranks(rank, best.rank) > 0 ||
        (outranks(rank, best.rank) === 0 && rule.order >= best.order);
      if (beats) {
        best = { rank, order: rule.order, value };
      }
    }
  }
  return best?.value;
}

/**
 * An inherited property's value: the element's own declaration, or the nearest ancestor's.
 *
 * `initial` supplies what a browser's own stylesheet gives an element nobody styled, such as
 * `white-space: pre` on a `pre`, because an inherited value that ignored it would call the
 * one element most likely to hold a long line a wrapping one.
 */
export function inherited(
  element: Element,
  property: string,
  rules: readonly OrderedRule[],
  width: number,
  initial: (element: Element) => string | undefined = () => undefined,
): string | undefined {
  for (let at: Element | null = element; at !== null; at = at.parentElement) {
    const value = declared(at, property, rules, width) ?? initial(at);
    if (value !== undefined) {
      return value;
    }
  }
  return undefined;
}
