/**
 * Every form this console generates from a schema is drawn by react-jsonschema-form, through one
 * component.
 *
 * `SchemaForm` is where the library's own markup, words and withheld-field handling are replaced
 * by the console's, and `schema-form.test.tsx` holds each of those. That only covers every
 * generated form if every generated form goes through it. **So the claim is asserted on the
 * source rather than on a page**: the library's form and its validator are imported by
 * `SchemaForm.tsx` and by no other module, and no second library that builds a form from a schema
 * is a dependency. A page that imported `@rjsf/core` for itself would draw the library's
 * Bootstrap markup and its English, and show a withheld field as an empty input; a second
 * generator would do all of that and more, and neither would fail any other test.
 *
 * The forms built by hand from the kit (`react-hook-form`, in the agent builder) are not
 * generated from a schema, and are not what this is about.
 *
 * Task ids: M32.5.2.2
 */

import { readdirSync, readFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { describe, expect, test } from "vitest";

const ROOT = resolve(__dirname, "..");
const SOURCE = join(ROOT, "src");

/** The one module that may draw a generated form, relative to the console's root. */
const THE_DOOR = "src/components/SchemaForm.tsx";

/** What draws a form from a schema and validates what was typed into it. */
const THE_LIBRARY = ["@rjsf/core", "@rjsf/validator-ajv8"];

/** Other libraries that generate a form from a schema. None may be a dependency. */
const OTHER_GENERATORS = [
  "react-jsonschema-form",
  "@jsonforms/core",
  "@jsonforms/react",
  "uniforms",
  "uniforms-bridge-json-schema",
  "@formily/core",
  "@formily/react",
  "@data-driven-forms/react-form-renderer",
  "react-schema-form",
];

function sourceFiles(): string[] {
  return readdirSync(SOURCE, { recursive: true, encoding: "utf-8" })
    .filter((one) => /\.(ts|tsx)$/.test(one))
    .map((one) => join(SOURCE, one))
    .filter((one) => !one.includes(`${join("src", "api", "generated")}`));
}

function importsTheLibrary(text: string): boolean {
  return THE_LIBRARY.some(
    (name) => text.includes(`from "${name}"`) || text.includes(`import("${name}")`),
  );
}

describe("every generated form is drawn by react-jsonschema-form through one door", () => {
  test("the library's form and validator are imported by SchemaForm and by no other module", () => {
    // What breaks if this is deleted: a page can import the library's form for itself and draw a
    // generated form with the library's markup and words, and a withheld field as an input, with
    // every test of SchemaForm still green. Equality rather than "includes", so a console that
    // imported the library nowhere fails too: then nothing generates a form with it at all.
    const importers = sourceFiles()
      .filter((one) => importsTheLibrary(readFileSync(one, "utf-8")))
      .map((one) => relative(ROOT, one).split("\\").join("/"));
    expect(importers).toEqual([THE_DOOR]);
  });

  test("the library is a dependency and no other form generator is", () => {
    // What breaks if this is deleted: a second generator can arrive as a dependency and draw a
    // form this console never styled, never worded and never taught about a withheld field.
    const manifest = JSON.parse(readFileSync(join(ROOT, "package.json"), "utf-8")) as {
      dependencies: Record<string, string>;
      devDependencies?: Record<string, string>;
    };
    const declared = new Set([
      ...Object.keys(manifest.dependencies),
      ...Object.keys(manifest.devDependencies ?? {}),
    ]);
    for (const name of THE_LIBRARY) {
      expect(declared.has(name)).toBe(true);
    }
    expect(OTHER_GENERATORS.filter((name) => declared.has(name))).toEqual([]);
  });
});
