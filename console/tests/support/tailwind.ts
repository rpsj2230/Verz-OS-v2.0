/**
 * The stylesheet Tailwind compiles for the component layer, compiled here the way the build compiles
 * it, so a test can ask what a class name does rather than what it is called.
 *
 * **Why this exists, and what it is for next.** The console's layout tests read its stylesheets from
 * disk (`support/css.ts`, `support/cascade.ts`), and a component styled with utility classes has no
 * stylesheet on disk: its rules exist only once Tailwind has compiled the class names it found. A
 * test that read `app.css` for a component's width would pass or fail for reasons that have nothing
 * to do with the component. So this runs Tailwind's own compiler over `src/theme/tailwind.css`, with
 * the same scanner the Vite plugin uses over the same `@source` directories, and optimises the result
 * with the same Lightning CSS step, which also turns Tailwind's range media queries into the
 * `min-width` shape `support/cascade.ts` reads. The rules come back numbered for that reader. This is
 * the half of re-pointing `phone-width` and `approvals-phone` that the first restyled page needs
 * (5.7 of the console plan, and the README's section on the component layer).
 *
 * **What it models, and what it does not.** A rule directly inside a cascade layer is read as a rule
 * at the top level. The layers' own order is not modelled, so a comparison between a utility and an
 * old sheet's rule is not something to ask this; it is asked of the build in a browser, which is what
 * the README records. `@supports` and non-width media queries are treated as not applying, as
 * `support/cascade.ts` already does.
 *
 * Task ids: none
 */

import { __unstable__loadDesignSystem, compile, optimize } from "@tailwindcss/node";
import { Scanner } from "@tailwindcss/oxide";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { parseCss } from "./css";
import type { OrderedRule } from "./cascade";
import { CONSOLE_ROOT } from "./repo";

/** The component layer's stylesheet, relative to the console. */
export const TAILWIND_ENTRY = "src/theme/tailwind.css";

const ENTRY_PATH = join(CONSOLE_ROOT, ...TAILWIND_ENTRY.split("/"));

export interface CompiledLayer {
  /** The CSS the build would emit for the entry, before minification. */
  readonly css: string;
  /** Every class-name candidate the scanner found in the `@source` directories. */
  readonly candidates: readonly string[];
  /** The directories Tailwind was told to read, as the compiler resolved them. */
  readonly sources: readonly { base: string; pattern: string; negated: boolean }[];
  /** Whether automatic source detection is off, which `source(none)` asks for. */
  readonly detectionOff: boolean;
}

/**
 * Compile an entry stylesheet as the Vite plugin does, with `extra` candidates added to the scanned
 * ones. The text may be a variant of the real entry, which is how a test proves a line is
 * load-bearing: compile without it and watch what comes out.
 */
export async function compileLayer(source: string = readFileSync(ENTRY_PATH, "utf8"), extra: readonly string[] = []): Promise<CompiledLayer> {
  const compiler = await compile(source, { base: dirname(ENTRY_PATH), onDependency: () => {}, shouldRewriteUrls: true });
  const sources = compiler.sources.map((one) => ({ base: one.base, pattern: one.pattern, negated: one.negated }));
  const scanner = new Scanner({ sources: [...sources] });
  const candidates = scanner.scan();
  const built = compiler.build([...candidates, ...extra]);
  return {
    css: optimize(built, { minify: false }).code,
    candidates,
    sources,
    detectionOff: compiler.root === "none",
  };
}

/**
 * The compiled rules in the shape `support/cascade.ts` reads: a rule directly inside a layer is
 * reported at the top level, and every other at-rule is left for the reader to judge.
 */
export function compiledRules(css: string): OrderedRule[] {
  return parseCss(css).map((rule, order) => ({
    ...rule,
    atRule: rule.atRule.startsWith("@layer") ? "" : rule.atRule,
    sheet: TAILWIND_ENTRY,
    order,
  }));
}

/** For each class name, the CSS it compiles to, or null when Tailwind makes nothing of it. */
export async function cssForEachClass(classes: readonly string[]): Promise<(string | null)[]> {
  const system = await __unstable__loadDesignSystem(readFileSync(ENTRY_PATH, "utf8"), { base: dirname(ENTRY_PATH) });
  return system.candidatesToCss([...classes]);
}
