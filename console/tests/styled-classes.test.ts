/**
 * Every class the console's markup uses has a style rule behind it.
 *
 * A class with no rule is a page that looks the way nobody designed it, and nothing else notices:
 * jsdom applies no stylesheet, the type checker sees a string, and the page still renders. Three
 * shapes of it were found on 2026-10-14 by the first run of this test, in a tree whose every other
 * guard was green. `bg-surface` and `text-ink-3` were written as if the palette had those names and
 * it has `bg-panel` and `text-dim`, so a selected segment and two lines of secondary text drew
 * unstyled. `text-danger` and `text-danger-text` were the same mistake for red, so a failed field
 * said so in the body colour. And about two dozen BEM names (`ask__result`, `ask__thread`,
 * `button--link`) were hooks for a stylesheet nobody wrote, some of them leftovers of a page
 * rebuilt since, which a reader took for styling that was meant to apply.
 *
 * **What counts as a rule.** A class selector in a stylesheet under `src`, or a Tailwind utility
 * that the build emits. The second is decided by compiling the component layer the way
 * `support/tailwind.ts` does and keeping only the utilities the scanner found: the scanner reads
 * `components/ui`, `components/kit`, `layout` and the kit modules under `pages/*`, **and not** the
 * older pages in `src/pages` or the files in `src/components`, so a utility written only there is
 * emitted by nothing and is a rule that does not exist. Any utility some scanned file also writes
 * is emitted, and styles every page, which is how the stylesheet really behaves.
 *
 * **What is allowed to have none, and why each is not a gap.** Tailwind's own markers (`group`,
 * `peer`, and their named forms) emit no CSS by design; they name an element for a `group-hover:`
 * variant elsewhere to point at. A BEM block is styled when its elements or modifiers are
 * (`procedure-step` has `procedure-step__field`), because the block name is the namespace. A
 * handful of names are structural hooks that tests and the first-run flow query, each recorded
 * below with the test that queries it. **An allowlist entry that no longer applies fails**, so the
 * list cannot outlive its reasons, and a name must still be used in markup and still have no rule
 * for its entry to stand.
 *
 * **What this cannot see.** A class held in a constant and passed to `className` by name, and a class
 * built whole from a variable. `support/classTokens.ts` says which positions are read. It also cannot
 * say whether a rule does what its name promises; that is the painted page, which the README records.
 *
 * Task ids: M27.15.72
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, test } from "vitest";
import { type ClassUse, classUsesInText, everyClassUse } from "./support/classTokens";
import { stripComments } from "./support/css";
import { CONSOLE_ROOT } from "./support/repo";
import { compileLayer, cssForEachClass } from "./support/tailwind";

/** Tailwind's markers: `group`, `peer` and the named `group/card`, which emit nothing by design. */
const TAILWIND_MARKER = /^(group|peer)(\/[\w-]+)?$/u;

/**
 * Names with no rule that something queries, and the test that does.
 *
 * Each is a structural hook rather than a style. They are kept as hooks because the tests below
 * select on them, and a class is the only attribute those tests have for a section that has no
 * landmark role of its own.
 */
export const STRUCTURAL_HOOKS: Readonly<Record<string, string>> = {
  confirm:
    "The in-page confirmation's section. tests/first-run.test.tsx, tests/automation-gallery.test.tsx and eleven more " +
    "select `section.confirm` to find the buttons of an open confirmation, and the section has no role of its own.",
  roster:
    "The list a staff-list check and the records finder draw. tests/long-lists.test.tsx selects `.roster` to find " +
    "its checkboxes, and tests/tailwind-foundation.test.ts uses the name as the example of an old page's class.",
  ask__provenance:
    "The block of an answer that says what it was based on. tests/ask-page.test.tsx and tests/skip-to-answer.test.tsx " +
    "select `.ask__provenance` to read its heading, and nothing else marks it.",
  ask__threads:
    "The list of earlier conversations. tests/ask-conversations.test.tsx selects `.ask__threads button` to read " +
    "the titles in the order drawn.",
  ask__attach:
    "The form that names a document on a conversation. tests/ask-attach.test.tsx selects `form.ask__attach` to find it.",
  "ask__dictation-status":
    "The live line that says what the microphone is doing. tests/ask-dictation.test.tsx selects it to read the " +
    "words and to assert its status role.",
  cited__passage:
    "A passage of a cited document. tests/ask-citations.test.tsx counts `.cited__passage` and its `--cited` " +
    "modifier, which is styled, to prove only the followed passage is marked.",
};

/** Every stylesheet under `src`, as absolute paths. */
function sheetsUnder(directory: string): string[] {
  return readdirSync(directory).flatMap((name) => {
    const full = join(directory, name);
    if (statSync(full).isDirectory()) {
      return sheetsUnder(full);
    }
    return name.endsWith(".css") ? [full] : [];
  });
}

/**
 * Every class a stylesheet under `src` has a selector for.
 *
 * Comments, `url()` and quoted strings are removed first so a class named in prose, or a file name
 * ending `.css`, is not read as a selector.
 */
function sheetClasses(): Set<string> {
  const names = new Set<string>();
  for (const sheet of sheetsUnder(join(CONSOLE_ROOT, "src"))) {
    const text = stripComments(readFileSync(sheet, "utf8"))
      .replace(/url\([^)]*\)/gu, "")
      .replace(/@import[^;]*;/gu, "")
      .replace(/"[^"]*"|'[^']*'/gu, "");
    for (const match of text.matchAll(/\.(-?[_a-zA-Z][\w-]*)/gu)) {
      names.add(match[1] ?? "");
    }
  }
  if (names.size === 0) {
    throw new Error(`No class selectors found under ${relative(CONSOLE_ROOT, CONSOLE_ROOT)}src; the reading has moved.`);
  }
  return names;
}

/** The names in use, and what each is backed by: a sheet's selector, an emitted utility, both, or nothing. */
async function backing(extra: readonly ClassUse[] = []): Promise<{
  readonly names: readonly string[];
  readonly uses: ReturnType<typeof everyClassUse>;
  readonly ruleOf: ReadonlyMap<string, "sheet" | "utility" | "none">;
  readonly sheet: ReadonlySet<string>;
}> {
  const uses = [...everyClassUse(), ...extra];
  const names = [...new Set(uses.map((one) => one.name))].sort();
  const sheet = sheetClasses();
  const layer = await compileLayer();
  const scanned = new Set(layer.candidates);
  const compiled = await cssForEachClass(names);
  const ruleOf = new Map<string, "sheet" | "utility" | "none">();
  names.forEach((name, at) => {
    const emitted = compiled[at] !== null && compiled[at] !== undefined && scanned.has(name);
    ruleOf.set(name, sheet.has(name) ? "sheet" : emitted ? "utility" : "none");
  });
  return { names, uses, ruleOf, sheet };
}

/** Whether a name's own elements or modifiers are styled, which is what styles a BEM block. */
function blockIsStyled(name: string, sheet: ReadonlySet<string>): boolean {
  return [...sheet].some((one) => one.startsWith(`${name}__`) || one.startsWith(`${name}--`));
}

/** The names that have no rule and no excuse: the failures. */
export async function classesWithoutARule(extra: readonly ClassUse[] = []): Promise<string[]> {
  const { names, uses, ruleOf, sheet } = await backing(extra);
  return names
    .filter(
      (name) =>
        ruleOf.get(name) === "none" &&
        !TAILWIND_MARKER.test(name) &&
        !(name in STRUCTURAL_HOOKS) &&
        !blockIsStyled(name, sheet),
    )
    .map((name) => {
      const first = uses.find((one) => one.name === name);
      return `${name} (${first?.file ?? ""}:${String(first?.line ?? 0)})`;
    });
}

describe("every class the markup uses has a style rule", () => {
  test("the reading finds the classes it should, so the rule below is read over a real list", async () => {
    // What breaks if this is deleted: the reading in `support/classTokens.ts` quietly finding
    // nothing after a rename, after which the test below passes over an empty list.
    const { names, uses, ruleOf } = await backing();
    expect(uses.length).toBeGreaterThan(5_000);
    expect(names.length).toBeGreaterThan(500);
    // A Tailwind utility from a scanned directory, a class from a stylesheet, and one from `cva`.
    expect(ruleOf.get("flex")).toBe("utility");
    expect(ruleOf.get("card")).toBe("sheet");
    expect(ruleOf.get("rounded-lg")).toBe("utility");
  }, 60_000);

  test("every class in the markup is a selector in a stylesheet or a utility the build emits", async () => {
    // What breaks if this is deleted: `bg-surface`, `text-ink-3`, `text-danger` and two dozen BEM
    // hooks, all of which shipped with the suite green because nothing compared a class to a rule.
    expect(await classesWithoutARule()).toEqual([]);
  }, 60_000);

  test("a utility no scanned file writes is reported even though Tailwind could make it", async () => {
    // What breaks if this is deleted: the sweep trusting that a name Tailwind knows is a name the
    // build emits. `bg-ground/37` is a valid utility and nothing writes it in a directory the
    // scanner reads, so it would be emitted by nothing: a page that wrote it would draw unstyled.
    // `flex` is the sibling, written in a scanned directory, and must not be reported.
    const invented = "bg-ground/37";
    const [css] = await cssForEachClass([invented]);
    expect(css, "the utility must be one Tailwind can make, or this proves nothing").not.toBeNull();
    const found = await classesWithoutARule([
      { file: "src/pages/Elsewhere.tsx", line: 1, name: invented },
      { file: "src/pages/Elsewhere.tsx", line: 2, name: "flex" },
    ]);
    expect(found).toContain(`${invented} (src/pages/Elsewhere.tsx:1)`);
    expect(found.filter((one) => one.startsWith("flex "))).toEqual([]);
  }, 60_000);

  test("a class is read from the positions that are classes and from no others", () => {
    // What breaks if this is deleted: the reading in `support/classTokens.ts` changed so that the
    // test of a conditional, the name of a variant or a word cut by a substitution is reported as a
    // class, or so that a real class in a `cva` variant, a `cn` object key or a ternary branch is
    // missed. The first makes the sweep refuse correct code and the second makes it pass broken code.
    const read = (text: string): string[] => classUsesInText(text).map((one) => one.name);
    expect(read(`const a = <p className={cn("flex", tone === "plain" && "border-line", ok ? "text-ok" : "text-crit")} />;`)).toEqual([
      "flex",
      "border-line",
      "text-ok",
      "text-crit",
    ]);
    expect(read(`const a = cn("a", flag === "b");`)).toEqual(["a"]);
    expect(read(`const a = cn({ "text-crit": failed, "font-medium": true }, ["gap-2"]);`)).toEqual(["text-crit", "font-medium", "gap-2"]);
    expect(
      read(
        `const v = cva("inline-flex", { variants: { size: { "icon-sm": "size-8" } }, defaultVariants: { size: "icon-sm" }, compoundVariants: [{ size: "icon-sm", class: "p-0" }] });`,
      ),
    ).toEqual(["inline-flex", "size-8", "p-0"]);
    expect(read("const a = <p className={`m-0 status-${kind} text-dim`} />;")).toEqual(["m-0", "text-dim"]);
    expect(read(`const a = <p className="plain words" title="not-a-class" />;`)).toEqual(["plain", "words"]);
    expect(read(`// className="in-a-comment"\nconst a = 1;`)).toEqual([]);
  });

  test("every structural hook still names a class that is used and has no rule", async () => {
    // What breaks if this is deleted: the allowlist outliving its reasons. A hook that is styled
    // now, or no longer written in the markup, is an excuse for nothing.
    const { names, ruleOf } = await backing();
    for (const [name, reason] of Object.entries(STRUCTURAL_HOOKS)) {
      expect(names, `${name} is allowlisted and is not used in any markup`).toContain(name);
      expect(ruleOf.get(name), `${name} is allowlisted and has a rule now`).toBe("none");
      expect(reason.split(" ").length, `${name} is excused without a reason`).toBeGreaterThan(12);
    }
  }, 60_000);
});
