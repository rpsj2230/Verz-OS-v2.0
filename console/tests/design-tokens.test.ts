/**
 * The design of record's tokens, in the three theme states, beside the old ones and apart from them.
 *
 * `tests/theme.test.ts` already holds the three states for the whole token file: every token on the
 * unstamped root, the `:not([data-theme="light"])` guard, and the two dark blocks identical. What it
 * cannot say is anything about which tokens are the design's, because it does not know, and that is
 * the half held here: that each design token really has a dark value, that the accent's four tokens
 * are built from the install's configuration and never from a colour written in this repository, and
 * that the two vocabularies stay apart.
 *
 * The contrast of each pair is measured in Python, by `brain.locale.READ_PAIRS` against this same
 * file (`tests/unit/test_locale.py`), because that is the suite that gates a deploy.
 *
 * Task ids: M27.10.4
 */

import { describe, expect, test } from "vitest";
import { INSTALL_ACCENT_PROPERTIES } from "../src/theme/accent";
import { customProperties, parseCss, stripComments, type CssRule } from "./support/css";
import { readConsoleFile } from "./support/repo";

/** The design of record's colour tokens, as `docs/screens.html` names them. */
const DESIGN_COLOURS = [
  "--ground",
  "--panel",
  "--sunk",
  "--line",
  "--ink",
  "--body",
  "--dim",
  "--faint",
  "--ok",
  "--ok-w",
  "--warn",
  "--warn-w",
  "--crit",
  "--crit-w",
  "--lock",
  "--lock-w",
  "--scrim",
];

/** The four tokens the install's accent is drawn through. */
const ACCENT_TOKENS = ["--brand", "--brand-ink", "--acc-text", "--acc-wash"];

function tokenRules(): CssRule[] {
  return parseCss(readConsoleFile("src/theme/tokens.css"));
}

function only(rules: CssRule[], predicate: (rule: CssRule) => boolean): Record<string, string> {
  const found = rules.filter(predicate);
  expect(found).toHaveLength(1);
  return customProperties(found[0] as CssRule);
}

const light = () => only(tokenRules(), (rule) => rule.atRule === "" && rule.selector === ":root");
const machineDark = () => only(tokenRules(), (rule) => /prefers-color-scheme:\s*dark/.test(rule.atRule));
const chosenDark = () => only(tokenRules(), (rule) => rule.atRule === "" && rule.selector.includes('[data-theme="dark"]'));

describe("the design of record's tokens", () => {
  test("every design colour has a light value and a different dark value in both dark blocks", () => {
    // What breaks if this is deleted: a design token defined on the root and forgotten in the dark
    // blocks keeps its light value on a dark page, so a panel is white under light text. The general
    // theme test cannot see it, because a token that is simply absent from both dark blocks keeps
    // them identical and keeps every token defined on the root.
    const [day, machine, chosen] = [light(), machineDark(), chosenDark()];
    for (const token of DESIGN_COLOURS) {
      expect(day[token], token).toBeDefined();
      expect(machine[token], token).toBeDefined();
      expect(machine[token], token).not.toBe(day[token]);
      expect(chosen[token], token).toBe(machine[token]);
    }
  });

  test("the accent is drawn from the install's configuration in both themes and has no colour of its own", () => {
    // What breaks if this is deleted: a company's orange written here as the fallback, which is one
    // company's details in the product (`CLAUDE.md`) and the colour every other install would see
    // until it set its own. Each accent token reads an `--install-accent-*` property first and falls
    // back to another design token, never to a literal; and the dark blocks read the dark variants.
    const day = light();
    for (const token of ACCENT_TOKENS) {
      expect(day[token], token).toMatch(/^var\(--install-accent-[a-z-]+, var\(--[a-z-]+\)\)$/);
    }
    for (const block of [machineDark(), chosenDark()]) {
      expect(block["--acc-text"]).toMatch(/^var\(--install-accent-text-dark, var\(--[a-z-]+\)\)$/);
      expect(block["--acc-wash"]).toMatch(/^var\(--install-accent-wash-dark, var\(--[a-z-]+\)\)$/);
      expect(block["--brand"]).toBeUndefined();
    }
  });

  test("the install accent properties the tokens read are exactly the ones the console writes", () => {
    // What breaks if this is deleted: `theme/accent.ts` writing `--install-accent-text` while this
    // file reads `--install-accent-text-light`, so every install is drawn in the neutral fallback, and
    // it reads, so nobody notices. Both directions, so a property written and never read fails too.
    const read = new Set<string>();
    for (const rule of tokenRules()) {
      for (const value of Object.values(rule.declarations)) {
        for (const match of value.matchAll(/var\((--install-accent-[a-z-]+)/g)) {
          if (match[1]) {
            read.add(match[1]);
          }
        }
      }
    }
    expect([...read].sort()).toEqual(Object.values(INSTALL_ACCENT_PROPERTIES).sort());
  });

  test("the old pages' sheets and the component layer's mapping read two vocabularies that do not meet", () => {
    // What breaks if this is deleted: the incremental migration. If `app.css` read a design token, a
    // change to the design would repaint an old page; if the mapping pointed a class at an old token,
    // a new component would take the old pages' cool grey. Read from both sides rather than listed.
    const oldReads = new Set<string>();
    for (const sheet of ["src/styles/app.css", "src/styles/approvals.css", "src/styles/agent-workspace.css"]) {
      for (const match of stripComments(readConsoleFile(sheet)).matchAll(/var\((--[\w-]+)/g)) {
        if (match[1]) {
          oldReads.add(match[1]);
        }
      }
    }
    const mapping = stripComments(readConsoleFile("src/theme/tailwind.css"));
    const newReads = new Set<string>();
    for (const match of mapping.matchAll(/--(?:color|font|radius)-[\w-]+:\s*(?:calc\()?var\((--[\w-]+)\)/g)) {
      if (match[1]) {
        newReads.add(match[1]);
      }
    }
    expect(oldReads.has("--border")).toBe(true);
    expect(newReads.has("--line")).toBe(true);
    expect([...newReads].filter((name) => oldReads.has(name))).toEqual([]);
    expect([...newReads].filter((name) => light()[name] === undefined)).toEqual([]);
  });

  test("no class can name the design's faint grey", () => {
    // What breaks if this is deleted: `text-faint` compiling to a colour that measures 2.22 to 1 on
    // the sunk surface. The design uses it for labels and it is below the text floor on every surface
    // in both themes, so it is in the token file as the design has it and mapped to no utility.
    // `tests/unit/test_locale.py` holds the measurement.
    expect(light()["--faint"]).toBeDefined();
    expect(stripComments(readConsoleFile("src/theme/tailwind.css"))).not.toMatch(/--color-[\w-]*:\s*var\(--faint\)/);
  });
});
