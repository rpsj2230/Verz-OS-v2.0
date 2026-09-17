/**
 * What is in the first response, and what is not.
 *
 * The component layer weighs more than the application it sits in: `@rjsf/core` with the
 * ajv validator measured 608 kB and `@xyflow/react` 258 kB, against 267 kB for everything
 * else. Mounting them eagerly puts all of it in front of every person who opens the console,
 * including the one who only ever reads the overview, and it happens before the sign-in
 * redirect has been decided.
 *
 * **This is asserted on the source rather than on the build output**, for the reason
 * `support/css.ts` exists: a number in a build log is checked by a person once. The static
 * import graph from `main.tsx` is the thing that decides what lands in the entry chunk, so
 * the graph is what the test reads. A dynamic `import()` is not followed, because it is the
 * split point; a static import of the same module is, and that is the mutation this catches.
 *
 * The refusal has a sibling: a console that imported none of these libraries anywhere would
 * satisfy the first test for ever. So the second one reads the records page's own graph and
 * insists the libraries really are reached from there.
 *
 * Task ids: M32.5.1.2
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, test } from "vitest";
import { packageOf, staticImportGraph } from "./support/typescript";

/** The entry the bundler starts from. `index.html` names it in a module script tag. */
const ENTRY = "src/main.tsx";

/**
 * The libraries the component layer brings, and the ones worth splitting a route for.
 *
 * The second line is the shadcn/ui foundation's (M27.10.2). `react-hook-form`, `zod` and
 * `@hookform/resolvers` weighed 214.8, 110.2 kB and more unminified in the design spike's Agents
 * route, and they belong to a page with a form, never to the first response. `cmdk` is the command
 * palette, which opens on a key and can arrive with it. Left out on purpose: `radix-ui`, which the
 * shell will put in the entry because its menu and header are built from it, and `sonner`, whose
 * toast region has to exist before its first message for a screen reader to announce it
 * (`components/ui/sonner.tsx`).
 */
const HEAVY = [
  "@rjsf/core",
  "@rjsf/validator-ajv8",
  "@tanstack/react-table",
  "@xyflow/react",
  "react-hook-form",
  "zod",
  "@hookform/resolvers",
  "cmdk",
];

describe("what the entry chunk reaches", () => {
  test("no heavy component library is reachable from the entry without a dynamic import", () => {
    // What breaks if this is deleted: the split, silently. A page is added, somebody writes
    // `import { Records } from "./pages/Records"` at the top of App.tsx because that is what
    // every other import there looks like, and the entry chunk triples. Nothing fails, no
    // screen changes, and the cost lands on whoever opens the console on a phone. The graph
    // is read from the source because a bundle size is a number in a log and this is a
    // property.
    const reached = new Set(staticImportGraph(ENTRY).packages);
    expect(HEAVY.filter((library) => reached.has(library))).toEqual([]);
  });

  test("the entry still reaches the shell, the overview and the one place that fetches", () => {
    // What breaks if this is deleted: the test above passes because the walker stopped at
    // the first file. A graph that reaches nothing contains nothing, so the refusal is
    // satisfied by a broken resolver, and this is the sibling that proves the walk is real.
    const files = staticImportGraph(ENTRY).files;
    expect(files).toContain("src/App.tsx");
    expect(files).toContain("src/layout/Shell.tsx");
    expect(files).toContain("src/pages/Overview.tsx");
    expect(files).toContain("src/api/client.ts");
    expect(files).not.toContain("src/pages/Records.tsx");
  });

  test("the component layer's heavy libraries are real and reachable from where they belong", () => {
    // What breaks if this is deleted: the four names added to the refusal above being names of
    // nothing, which the refusal would accept for ever. The palette's library is reached from the
    // palette, and the form libraries are dependencies the console really installs; no page mounts a
    // form on them yet, and the first one to do so must be a lazy route.
    const palette = new Set(staticImportGraph("src/components/ui/command.tsx").packages);
    expect(palette.has("cmdk")).toBe(true);

    const declared = JSON.parse(readFileSync(resolve(process.cwd(), "package.json"), "utf8")) as {
      dependencies: Record<string, string>;
    };
    for (const library of ["react-hook-form", "zod", "@hookform/resolvers", "cmdk"]) {
      expect(declared.dependencies[library], library).toMatch(/^\d+\.\d+\.\d+$/);
    }
  });

  test("the split route is the one that reaches the libraries", () => {
    // What breaks if this is deleted: a refusal with nothing behind it. A console that had
    // dropped the table and the form entirely would pass the first test and would have
    // nothing to split, and the allow-list above would be a leftover rather than a rule.
    const reached = new Set(staticImportGraph("src/pages/Records.tsx").packages);
    expect(reached.has("@rjsf/core")).toBe(true);
    expect(reached.has("@tanstack/react-table")).toBe(true);
  });
});

describe("reading a specifier", () => {
  test("a package name keeps its scope and drops the path inside it", () => {
    // What breaks if this is deleted: the graph above reports `@xyflow/react/dist/base.css`
    // as a package and the allow-list, which names `@xyflow/react`, stops matching it. The
    // refusal would then pass with the library imported, which is the direction that reads
    // as a pass.
    expect(packageOf("@xyflow/react/dist/base.css")).toBe("@xyflow/react");
    expect(packageOf("react-dom/client")).toBe("react-dom");
    expect(packageOf("react")).toBe("react");
  });
});
