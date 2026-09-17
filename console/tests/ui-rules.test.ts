/**
 * The product's rules, held over every component in `src/components/ui` rather than over the ones
 * somebody remembered: no totals, no cookie, no colour a token did not name, a focus ring whose
 * contrast is known, a badge whose colour is never chosen from data, and every part the package
 * promised present and tested.
 *
 * **Why over the directory.** These components are copied, and the next one will be copied from
 * shadcn/ui or from a template built on it, arriving with shadcn/ui's habits: a count in a pager, a
 * cookie for the sidebar, a literal overlay colour, a half-opacity focus ring. Each rule below reads
 * every file in the directory, so a component pasted next month is held the day it lands.
 *
 * **Structure, not text.** Comments in these files quote the very things they refuse ("Page 1 of
 * 10", `document.cookie`), so the source is read with its comments removed by the TypeScript printer,
 * and class names are read from the calls and attributes that carry them, then compiled by Tailwind.
 *
 * Task ids: M27.10.2, M27.10.4
 */

import { readdirSync } from "node:fs";
import { join } from "node:path";
import ts from "typescript";
import { describe, expect, test } from "vitest";
import { compileLayer, compiledRules, cssForEachClass } from "./support/tailwind";
import { CONSOLE_ROOT } from "./support/repo";
import { consoleSourcePaths, parseConsoleSource } from "./support/typescript";

const UI = "src/components/ui";

/** Every component module in the directory. */
function componentPaths(): string[] {
  return consoleSourcePaths(UI);
}

/** A file's code with its comments removed, so an explanation cannot satisfy or fail a rule. */
function codeOf(source: ts.SourceFile): string {
  return ts.createPrinter({ removeComments: true }).printFile(source);
}

/** Every class name a component writes: the strings inside `cn()`, `cva()` and `className`. */
function classNamesIn(source: ts.SourceFile): string[] {
  const found: string[] = [];
  const strings = (node: ts.Node): void => {
    const parent = node.parent;
    const isKey = parent !== undefined && ts.isPropertyAssignment(parent) && parent.name === node;
    const isCompared =
      parent !== undefined &&
      ts.isBinaryExpression(parent) &&
      [ts.SyntaxKind.EqualsEqualsEqualsToken, ts.SyntaxKind.ExclamationEqualsEqualsToken].includes(parent.operatorToken.kind);
    if (ts.isPropertyAssignment(node) && node.name.getText(source) === "defaultVariants") {
      return;
    }
    if ((ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) && !isKey && !isCompared) {
      found.push(...node.text.split(/\s+/).filter((one) => one !== ""));
    }
    ts.forEachChild(node, strings);
  };
  const visit = (node: ts.Node): void => {
    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && ["cn", "cva"].includes(node.expression.text)) {
      node.arguments.forEach(strings);
    } else if (ts.isJsxAttribute(node) && node.name.getText(source) === "className" && node.initializer) {
      strings(node.initializer);
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return found;
}

/** Phrasings that are a count of rows, pages, results or a selection. */
const A_COUNT = [
  /(?:\d|\}|\$\{[^}]*\})\s+of\s+(?:\d|\{|\$\{)/i,
  /\brows?\(s\)/i,
  /\b(?:selected|results?|matches|hidden|more)\b\s*(?:\(|\{|\$\{)/i,
  /(?:\{|\$\{)[^}]*\}\s*(?:selected|results?|matches|rows?|items?|more|hidden)\b/i,
  /\bpage\s+(?:\d|\{|\$\{)/i,
];

function countsIn(code: string): string[] {
  return A_COUNT.flatMap((pattern) => {
    const match = pattern.exec(code);
    return match ? [match[0]] : [];
  });
}

/** Badges whose `variant` is computed rather than written, in one parsed file. */
function computedBadgeVariants(source: ts.SourceFile): string[] {
  const found: string[] = [];
  const visit = (node: ts.Node): void => {
    if ((ts.isJsxSelfClosingElement(node) || ts.isJsxOpeningElement(node)) && node.tagName.getText(source) === "Badge") {
      for (const attribute of node.attributes.properties) {
        if (ts.isJsxAttribute(attribute) && attribute.name.getText(source) === "variant" && attribute.initializer) {
          const inner = ts.isJsxExpression(attribute.initializer) ? attribute.initializer.expression : attribute.initializer;
          if (!inner || !ts.isStringLiteral(inner)) {
            found.push(`${source.fileName}: variant=${attribute.initializer.getText(source)}`);
          }
        }
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return found;
}

describe("no totals", () => {
  test("no component in the layer draws a count of rows, pages, results or a selection", () => {
    // What breaks if this is deleted: rule R2, the one `CLAUDE.md` calls the easiest to break by
    // accident. shadcn/ui's data table says "Page 1 of 10" and "3 of 47 row(s) selected", and its
    // faceted filter prints a count beside each option; each is a total computed behind a permission
    // predicate, which tells a reader how many things they were not shown. The spike removed all three,
    // and this holds the directory to it with comments removed, because the comments here quote them.
    const found = componentPaths().flatMap((path) => countsIn(codeOf(parseConsoleSource(path))).map((hit) => `${path}: ${hit}`));
    expect(found).toEqual([]);
  });

  test("the count detector finds the phrasings shadcn/ui ships", () => {
    // What breaks if this is deleted: the test above is satisfied by a detector that finds nothing.
    // These are the spike's three removals as shadcn/ui wrote them, and a sibling that is not a count.
    const shipped = [
      "<div>Page {table.getState().pagination.pageIndex + 1} of {table.getPageCount()}</div>",
      "<div>{table.getFilteredSelectedRowModel().rows.length} of {table.getFilteredRowModel().rows.length} row(s) selected.</div>",
      "<span>{facets.get(option.value)} results</span>",
      "const label = `${selected.length} selected`;",
    ];
    for (const snippet of shipped) {
      expect(countsIn(snippet), snippet).not.toEqual([]);
    }
    expect(countsIn('<p className="m-0 text-sm">A value is stored. It is never shown.</p>')).toEqual([]);
  });

  test("the sidebar has no badge and the palette prints no number of its own", () => {
    // What breaks if this is deleted: the two places in this directory a number would sit beside the
    // navigation. The badge is not exported at all, and the palette's markup, rendered as the tests in
    // `ui-overlays.test.tsx` render it, carries no digit that is not in an item's own label.
    const sidebar = codeOf(parseConsoleSource(`${UI}/sidebar.tsx`));
    expect(sidebar).not.toMatch(/function SidebarMenuBadge/);
    expect(sidebar).toMatch(/function SidebarMenuButton/);
    expect(codeOf(parseConsoleSource(`${UI}/command.tsx`))).not.toMatch(/\.length/);
  });
});

describe("what a component may write", () => {
  test("no component writes a cookie", () => {
    // What breaks if this is deleted: shadcn/ui's sidebar writes `sidebar_state` to `document.cookie`
    // on every toggle. A cookie travels to the API with every request and outlives the tab, and this
    // console keeps nothing in the browser but the theme. `scripts/check-boundaries.mjs` refuses the
    // spelling everywhere; this reads the code with its comments removed.
    const writers = componentPaths().filter((path) => /document\s*\.\s*cookie/.test(codeOf(parseConsoleSource(path))));
    expect(writers).toEqual([]);
    expect(/document\s*\.\s*cookie/.test('document.cookie = "sidebar_state=true"')).toBe(true);
  });

  test("a badge's colour is written at the call site and never chosen from data", () => {
    // What breaks if this is deleted: `<Badge variant={row.restricted ? "destructive" : "secondary"}>`,
    // which turns a fact about what one person may see into a colour another person's screen does not
    // have. `tests/status-primitives.test.tsx` holds the same rule for the old badge's `tone`; this is
    // the new badge's spelling of it, read across every source file. The sibling proves the reader
    // finds the line it refuses.
    const computed = consoleSourcePaths("src").flatMap((path) => computedBadgeVariants(parseConsoleSource(path)));
    expect(computed).toEqual([]);

    const offending = ts.createSourceFile(
      "example.tsx",
      'const a = <Badge variant={row.restricted ? "destructive" : "secondary"}>x</Badge>; const b = <Badge variant="outline">y</Badge>;',
      ts.ScriptTarget.ES2022,
      true,
      ts.ScriptKind.TSX,
    );
    expect(computedBadgeVariants(offending)).toHaveLength(1);
  });
});

describe("colour", () => {
  test("every class a component writes is one Tailwind can compile", async () => {
    // What breaks if this is deleted: the silent half of removing Tailwind's palette. `bg-red-500`,
    // `text-white` or `text-faint` compile to nothing at all, so the element simply loses its colour
    // and nothing fails. Every class in every component is handed to Tailwind's own design system,
    // and only the grouping markers, which exist to be referred to rather than to style, may compile
    // to nothing.
    const markers = /^(?:group|peer)(?:\/[\w-]+)?$/;
    const classes = [...new Set(componentPaths().flatMap((path) => classNamesIn(parseConsoleSource(path))))].filter((one) => !markers.test(one));
    expect(classes.length).toBeGreaterThan(200);

    const compiled = await cssForEachClass(classes);
    const nothing = classes.filter((_, index) => compiled[index] === null);
    expect(nothing).toEqual([]);

    const [palette, token] = await cssForEachClass(["bg-red-500", "bg-crit-wash"]);
    expect(palette).toBeNull();
    expect(token).not.toBeNull();
  });

  test("every colour a component paints reads a token, except the darkness of a shadow", async () => {
    // What breaks if this is deleted: an arbitrary value such as `bg-[#fff]` or `text-[rgb(0,0,0)]`,
    // which compiles perfectly and is a second palette that is wrong in whichever theme its author was
    // not using. Read from the compiled rules, so it covers every way a colour can be spelled in a
    // class. Tailwind's shadow scale is black at a small opacity, which is a darkness rather than a
    // colour a reader reads, and is the one exception. Transparent is no colour, and the optimiser
    // spells it `#0000`.
    const layer = await compileLayer();
    const literal = /#(?!0000\b)[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(|\boklch\(|\boklab\(/;
    const found: string[] = [];
    for (const rule of compiledRules(layer.css)) {
      if (!rule.selector.startsWith(".") || rule.atRule.startsWith("@supports")) {
        continue;
      }
      for (const [property, value] of Object.entries(rule.declarations)) {
        if (!literal.test(value) || /shadow/.test(property)) {
          continue;
        }
        found.push(`${rule.selector} { ${property}: ${value} }`);
      }
    }
    expect(found).toEqual([]);
  });

  test("a component's focus ring is the accent's text colour at full strength", async () => {
    // What breaks if this is deleted: shadcn/ui's `ring-ring/50`, a ring at half opacity whose
    // contrast against the page nobody can state. The accent's text colour is measured at 4.5 to 1
    // against every surface in both themes before it is served (`brain.locale.accent_set`), so a ring
    // drawn in it at full strength inherits a known figure. Read from the compiled rules for every
    // focus ring class the components write.
    const rings = [
      ...new Set(
        componentPaths()
          .flatMap((path) => classNamesIn(parseConsoleSource(path)))
          .filter((one) => /^focus-visible:ring-/.test(one) && !/^focus-visible:ring-\d/.test(one)),
      ),
    ];
    expect(rings).toEqual(["focus-visible:ring-ring"]);

    const [css] = await cssForEachClass(rings);
    expect(css).toMatch(/--tw-ring-color:\s*var\(--acc-text\)/);
    expect(css).not.toMatch(/color-mix/);
  });
});

describe("the parts this package promised", () => {
  /** The parts M27.10.2's foundation lists, as the files shadcn/ui's layout names them. */
  const PROMISED = [
    "alert-dialog",
    "badge",
    "breadcrumb",
    "button",
    "card",
    "checkbox",
    "command",
    "dialog",
    "dropdown-menu",
    "empty",
    "explained",
    "input",
    "label",
    "popover",
    "scroll-area",
    "secret-field",
    "select",
    "separator",
    "sheet",
    "sidebar",
    "skeleton",
    "sonner",
    "switch",
    "table",
    "tabs",
    "textarea",
    "tooltip",
  ];

  test("every promised part exists and a component test imports it", () => {
    // What breaks if this is deleted: a part claimed in the commit that nothing exercises, which is a
    // draft nobody has run. Each file must exist and be imported by one of the component test files,
    // and nothing in the directory may be neither promised nor a helper.
    const present = readdirSync(join(CONSOLE_ROOT, UI)).map((name) => name.replace(/\.tsx?$/, ""));
    expect(present.filter((name) => name !== "focus-return").sort()).toEqual([...PROMISED].sort());

    const imported = new Set<string>();
    for (const file of ["tests/ui-controls.test.tsx", "tests/ui-overlays.test.tsx", "tests/ui-structure.test.tsx"]) {
      for (const statement of parseConsoleSource(file).statements) {
        if (ts.isImportDeclaration(statement) && ts.isStringLiteral(statement.moduleSpecifier)) {
          const match = /components\/ui\/([\w-]+)$/.exec(statement.moduleSpecifier.text);
          if (match?.[1]) {
            imported.add(match[1]);
          }
        }
      }
    }
    expect(PROMISED.filter((name) => !imported.has(name))).toEqual([]);
  });
});
