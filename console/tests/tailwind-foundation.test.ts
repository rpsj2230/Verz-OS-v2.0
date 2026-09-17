/**
 * The component layer arrives without repainting a page that already exists.
 *
 * Three mechanisms keep that true, and each has a test here because each fails silently. The old
 * stylesheets are moved into a `legacy` cascade layer between Tailwind's reset and its utilities, by
 * a plugin at build time rather than an edit to each sheet. Tailwind's reset is narrowed to the new
 * components, because the old sheets were written against the browser's own defaults. And Tailwind is
 * kept from generating a utility whose name is one of the old pages' own class names, because a
 * utility now outranks every old rule.
 *
 * **What these cannot see is the painted page.** jsdom applies no stylesheet, so the proof that an old
 * page looks the same was taken in Chrome, over every registered page's rendered markup with the
 * stylesheets of the build before and after, and is recorded in the README with the negative controls
 * that show the comparison would have caught a difference. These tests hold the mechanisms that
 * measurement depended on.
 *
 * Task ids: M27.10.2
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import ts from "typescript";
import { describe, expect, test } from "vitest";
// @ts-expect-error The plugin is a plain module with no type declarations, as `vite.config.ts` uses it.
import { LEGACY_LAYER, LEGACY_SHEETS, inLegacyLayer, isLegacySheet, legacyLayer } from "../scripts/legacy-layer.mjs";
import { CONSOLE_SHEETS, selectorList } from "./support/cascade";
import { parseCss, stripComments } from "./support/css";
import { CONSOLE_ROOT, readConsoleFile } from "./support/repo";
import { compileLayer, compiledRules, TAILWIND_ENTRY } from "./support/tailwind";
import { parseConsoleSource } from "./support/typescript";

/** The sheets the component layer brought, which are not old and must not be wrapped. */
const COMPONENT_LAYER_SHEETS = ["src/theme/tailwind.css", "src/theme/preflight.css"];

/** Every stylesheet under `src`, relative to the console. */
function sheetsUnderSrc(): string[] {
  const found: string[] = [];
  const walk = (directory: string): void => {
    for (const name of readdirSync(directory)) {
      const full = join(directory, name);
      if (statSync(full).isDirectory()) {
        walk(full);
      } else if (name.endsWith(".css")) {
        found.push(relative(CONSOLE_ROOT, full).split("\\").join("/"));
      }
    }
  };
  walk(join(CONSOLE_ROOT, "src"));
  return found.sort();
}

/** The one `@layer a, b, c;` statement in the entry, as its names in order. */
function declaredLayerOrder(): string[] {
  const statements = [...stripComments(readConsoleFile(TAILWIND_ENTRY)).matchAll(/@layer\s+([\w\s,-]+);/g)];
  expect(statements).toHaveLength(1);
  return (statements[0]?.[1] ?? "").split(",").map((one) => one.trim());
}

/** The directories the component layer added, whose class names are meant to be utilities. */
const COMPONENT_LAYER_DIRECTORIES = ["src/components/ui", "src/hooks", "src/lib"];

/**
 * Every class name an old page can carry: the old sheets' class selectors, and every word of every
 * string inside a `className` attribute in the old sources, including the static parts of a template.
 */
function oldClassNames(): string[] {
  const names = new Set<string>();
  for (const sheet of CONSOLE_SHEETS) {
    for (const match of stripComments(readConsoleFile(sheet)).matchAll(/\.(-?[_a-zA-Z][\w-]*)/g)) {
      if (match[1]) {
        names.add(match[1]);
      }
    }
  }
  const words = (text: string): void => {
    for (const word of text.split(/\s+/)) {
      if (/^[a-z][a-z0-9_-]*$/.test(word)) {
        names.add(word);
      }
    }
  };
  const walk = (directory: string): void => {
    for (const name of readdirSync(join(CONSOLE_ROOT, directory))) {
      const path = `${directory}/${name}`;
      if (statSync(join(CONSOLE_ROOT, path)).isDirectory()) {
        if (!COMPONENT_LAYER_DIRECTORIES.includes(path) && name !== "generated") {
          walk(path);
        }
      } else if (/\.tsx$/.test(name)) {
        const strings = (node: ts.Node): void => {
          if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
            words(node.text);
          } else if (ts.isTemplateExpression(node)) {
            words(node.head.text);
            node.templateSpans.forEach((span) => words(span.literal.text));
          }
          ts.forEachChild(node, strings);
        };
        const visit = (node: ts.Node): void => {
          if (ts.isJsxAttribute(node) && node.name.getText() === "className" && node.initializer) {
            strings(node.initializer);
          }
          ts.forEachChild(node, visit);
        };
        visit(parseConsoleSource(path));
      }
    }
  };
  walk("src");
  return [...names].sort();
}

/** The class selectors a compiled stylesheet defines a rule for, unescaped, without pseudo parts. */
function simpleClassSelectors(css: string): Set<string> {
  const found = new Set<string>();
  for (const rule of parseCss(css)) {
    for (const part of selectorList(rule.selector)) {
      const match = /^\.((?:\\.|[\w-])+)$/.exec(part);
      if (match?.[1]) {
        found.add(match[1].replace(/\\(.)/g, "$1"));
      }
    }
  }
  return found;
}

describe("the cascade order", () => {
  test("the old sheets sit between the reset and the utilities", () => {
    // What breaks if this is deleted: the one statement that makes the migration incremental. With
    // `legacy` after `utilities`, every old element rule (`a`, `h2`, `code`) beats a class on a new
    // component; before `base`, the reset beats the old pages' own rules for every property both set.
    // The order is read out of the entry, not restated.
    expect(declaredLayerOrder()).toEqual(["theme", "base", LEGACY_LAYER, "components", "utilities"]);
  });

  test("the entry imports the stylesheet that declares the order before any sheet that uses a layer", () => {
    // What breaks if this is deleted: a layer's position is fixed where it is first named. If
    // `app.css`, wrapped in `@layer legacy`, reached the bundle before `tailwind.css`, `legacy` would
    // be the lowest layer of all and the reset would outrank the old pages. The bundle keeps import
    // order, so the order of `main.tsx`'s imports is the property.
    const imports = parseConsoleSource("src/main.tsx")
      .statements.filter(ts.isImportDeclaration)
      .map((statement) => (statement.moduleSpecifier as ts.StringLiteral).text);
    const at = (specifier: string) => imports.indexOf(specifier);

    expect(at("./theme/tokens.css")).toBe(0);
    expect(at("./theme/tailwind.css")).toBe(1);
    expect(at("./styles/app.css")).toBe(2);
    expect(at("./App")).toBeGreaterThan(at("./styles/app.css"));
  });

  test("every sheet the console had is wrapped in the legacy layer, and the component layer's are not", () => {
    // What breaks if this is deleted: an old sheet left unlayered beats every utility whatever its
    // specificity, so a new component on the approvals page would lose to `approvals.css`; and a
    // component sheet wrapped by mistake would sink below its own utilities' base. Checked with the
    // ids Vite hands the plugin on this machine, which are Windows paths.
    for (const sheet of CONSOLE_SHEETS.filter((one) => one !== "src/theme/tokens.css")) {
      expect(isLegacySheet(join(CONSOLE_ROOT, sheet)), sheet).toBe(true);
    }
    expect(isLegacySheet(join(CONSOLE_ROOT, "node_modules/@xyflow/react/dist/base.css"))).toBe(true);
    expect(isLegacySheet(`${join(CONSOLE_ROOT, "src/styles/app.css")}?used`)).toBe(true);

    for (const sheet of ["src/theme/tokens.css", ...COMPONENT_LAYER_SHEETS]) {
      expect(isLegacySheet(join(CONSOLE_ROOT, sheet)), sheet).toBe(false);
    }
    expect(isLegacySheet(join(CONSOLE_ROOT, "node_modules/@fontsource/ibm-plex-sans/latin-400.css"))).toBe(false);
    expect(LEGACY_SHEETS).toHaveLength(4);
  });

  test("the plugin wraps an old sheet whole and changes nothing inside it", () => {
    // What breaks if this is deleted: a wrapper that dropped a line, or one that wrapped each rule
    // separately and lost the order between them, would pass the test above. The transform's output
    // is the sheet itself between an opening and a closing brace, and a sheet it does not own is
    // passed through untouched.
    const plugin = legacyLayer();
    const app = readConsoleFile("src/styles/app.css");
    const id = join(CONSOLE_ROOT, "src/styles/app.css");

    const wrapped = plugin.transform(app, id);
    expect(wrapped.code).toBe(inLegacyLayer(app));
    expect(wrapped.code.startsWith(`@layer ${LEGACY_LAYER} {\n${app}`)).toBe(true);
    expect(parseCss(wrapped.code).length).toBe(parseCss(app).length);
    expect(plugin.transform("a{}", join(CONSOLE_ROOT, TAILWIND_ENTRY))).toBeNull();
    expect(plugin.enforce).toBe("pre");
  });

  test("a new stylesheet under src is a decision, not a default", () => {
    // What breaks if this is deleted: a sheet added next month is neither old nor the component
    // layer's, sits unlayered above every utility, and repaints the new components wherever its
    // selectors reach. The list below is every sheet there is; adding one fails here until somebody
    // says which side it is on.
    const known = [...CONSOLE_SHEETS, ...COMPONENT_LAYER_SHEETS].sort();
    expect(sheetsUnderSrc()).toEqual(known);
  });
});

describe("what Tailwind generates", () => {
  test("Tailwind reads the component directory and nothing else", async () => {
    // What breaks if this is deleted: with automatic detection Tailwind reads every file in the
    // console, comments included, and generates a rule for every word that happens to be a utility.
    // Every one of those rules outranks the old pages. Reading `components/ui` alone keeps the set
    // of generated rules to the classes the new components actually use.
    const layer = await compileLayer();

    expect(layer.detectionOff).toBe(true);
    expect(layer.sources.map((one) => relative(join(CONSOLE_ROOT, "src", "theme"), join(one.base, one.pattern)).split("\\").join("/"))).toEqual([
      "../components/ui",
    ]);
    expect(layer.candidates).toContain("bg-primary");
  });

  test("no class name an old page uses comes out as a utility, whatever Tailwind reads", async () => {
    // What breaks if this is deleted: every data table on an old page is wrapped in `.grid`, which
    // `app.css` makes a flex column, and Tailwind's `grid` is `display: grid` in a layer that now
    // outranks `app.css`. Measured in Chrome with the exclusion removed: every table's display turned
    // from flex to grid. So every class name any old sheet or old source uses is compiled here as if
    // Tailwind had read it, and none may produce a rule of its own.
    const names = oldClassNames();
    expect(names).toContain("grid");
    expect(names).toContain("shell__nav");

    const generated = simpleClassSelectors((await compileLayer(undefined, names)).css);
    expect(names.filter((name) => generated.has(name))).toEqual([]);
  });

  test("the exclusion is what stops the collision, not an accident of what is read", async () => {
    // What breaks if this is deleted: the test above is satisfied by a compiler that generates
    // nothing. Remove the `@source not inline` line and the same compile produces `.grid`, so the
    // line is load-bearing and the check above is watching.
    const entry = readConsoleFile(TAILWIND_ENTRY);
    const withoutExclusion = entry.replace(/@source not inline\("grid"\);/, "");
    expect(withoutExclusion).not.toBe(entry);

    const generated = simpleClassSelectors((await compileLayer(withoutExclusion, ["grid"])).css);
    expect(generated.has("grid")).toBe(true);
  });

  test("a utility never reads a custom property the old sheets read", async () => {
    // What breaks if this is deleted: Tailwind's `text-sm` reads `--text-sm`, its `font-sans` reads
    // `--font-sans` and its `rounded-lg` reads `--radius-lg`, and `tokens.css` defines all three for
    // the old pages, unlayered, so they win. A component would render in the old pages' 13 pixel type
    // and system font with every test here green. `@theme inline` is what prevents it; this reads
    // every `var()` in the compiled utilities against the vocabulary the old sheets speak.
    const oldVocabulary = new Set<string>();
    for (const sheet of CONSOLE_SHEETS.filter((one) => one !== "src/theme/tokens.css")) {
      for (const match of stripComments(readConsoleFile(sheet)).matchAll(/var\((--[\w-]+)/g)) {
        if (match[1]) {
          oldVocabulary.add(match[1]);
        }
      }
    }
    expect(oldVocabulary.has("--text-sm")).toBe(true);

    const layer = await compileLayer();
    const read = new Set<string>();
    for (const rule of compiledRules(layer.css)) {
      for (const value of Object.values(rule.declarations)) {
        for (const match of value.matchAll(/var\((--[\w-]+)/g)) {
          if (match[1]) {
            read.add(match[1]);
          }
        }
      }
    }
    expect(read.has("--brand")).toBe(true);
    expect([...read].filter((name) => oldVocabulary.has(name)).sort()).toEqual([]);
  });
});

describe("the reset's scope", () => {
  /** The scope, read out of the reset's first rule rather than restated. */
  function scope(): string {
    const first = parseCss(readConsoleFile("src/theme/preflight.css"))[0];
    const selector = selectorList(first?.selector ?? "")[0] ?? "";
    expect(selector.startsWith(":where(")).toBe(true);
    return selector;
  }

  test("the reset reaches a component and its contents", () => {
    // What breaks if this is deleted: a scope that stopped at the component's own element would leave
    // an icon inside a button, or a row inside a table, on the browser's defaults, which is a button
    // with a grey face and a table with gaps between its borders.
    document.body.innerHTML = '<button data-slot="button"><svg></svg><span>Save</span></button>';
    const button = document.querySelector("button") as Element;

    expect(button.matches(scope())).toBe(true);
    expect((button.querySelector("svg") as Element).matches(scope())).toBe(true);
    expect((button.querySelector("span") as Element).matches(scope())).toBe(true);
  });

  test("the reset does not reach an old page, even inside the new frame", () => {
    // What breaks if this is deleted: the sidebar's provider wraps the whole application in a
    // `data-slot` element, so a scope of "inside a component" alone would put every old page under
    // the reset the day the shell lands: headings unbolded, lists unbulleted, links not underlined.
    // Measured in Chrome with the reset global: 1,641 computed properties changed on the overview.
    document.body.innerHTML =
      '<ul class="roster"><li><a href="/x">x</a></li></ul>' +
      '<div data-slot="sidebar-wrapper"><main data-legacy><h2>Old</h2><ul class="roster"><li>y</li></ul></main></div>';
    const [outside, inside] = [...document.querySelectorAll("ul.roster")];

    expect((outside as Element).matches(scope())).toBe(false);
    expect((document.querySelector("a") as Element).matches(scope())).toBe(false);
    expect((inside as Element).matches(scope())).toBe(false);
    expect((document.querySelector("h2") as Element).matches(scope())).toBe(false);
    expect((document.querySelector("main") as Element).matches(scope())).toBe(false);
    expect((document.querySelector('[data-slot="sidebar-wrapper"]') as Element).matches(scope())).toBe(true);
  });

  test("a new component placed on an old page inside the frame is reset again", () => {
    // What breaks if this is deleted: the exception above swallowed the components it should not,
    // so a new button placed on an old page renders with the platform's button face.
    document.body.innerHTML =
      '<div data-slot="sidebar-wrapper"><main data-legacy><section><button data-slot="button"><svg></svg></button></section></main></div>';

    expect((document.querySelector("button") as Element).matches(scope())).toBe(true);
    expect((document.querySelector("svg") as Element).matches(scope())).toBe(true);
    expect((document.querySelector("section") as Element).matches(scope())).toBe(false);
  });

  test("every rule of the reset is narrowed, and no stylesheet of the component layer names a colour", () => {
    // What breaks if this is deleted: one rule copied from Tailwind without the scope resets the
    // whole document for that property, which is the global reset back again one property at a time.
    // And a literal colour in either sheet is a second palette outside `tokens.css`, which
    // `theme.test.ts` holds for `app.css` and nothing held for these.
    const reset = parseCss(readConsoleFile("src/theme/preflight.css"));
    expect(reset.length).toBeGreaterThan(10);
    for (const rule of reset) {
      for (const part of selectorList(rule.selector)) {
        expect(part.trim().startsWith(scope()), part).toBe(true);
      }
    }
    for (const sheet of COMPONENT_LAYER_SHEETS) {
      const literals = parseCss(readConsoleFile(sheet)).flatMap((rule) =>
        Object.entries(rule.declarations)
          .filter(([, value]) => /#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(|\bcolor-mix\(|\boklch\(/.test(value))
          .map(([property, value]) => `${sheet} ${rule.selector} { ${property}: ${value} }`),
      );
      expect(literals).toEqual([]);
    }
  });
});
