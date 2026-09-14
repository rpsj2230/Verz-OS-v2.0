/**
 * The builder's form: generated from the manifest's JSON Schema, one section at a time.
 *
 * M20.1.2 is "forms generated from the manifest JSON Schema via react-jsonschema-form". Two
 * things have to be true for that sentence and they are asserted separately. The schema has to
 * be the manifest's, which is `tests/unit/test_builder_form.py` holding
 * `fixtures/manifest-form.json` equal to what `brain.builder.form` cuts out of
 * `TemplateManifest.model_json_schema()`. And the form has to be generated from that schema
 * rather than written, which is this file: every control on every section is a field that
 * section's schema declares, a field the schema gains is a control with no change to the
 * console, the model's bound on a name is the bound the rendered input enforces, and neither of
 * the form's modules names a manifest field anywhere in its code.
 *
 * The expected controls are worked out by walking the schema rather than listed, because a list
 * of ids written here would be a hand-written description of the form, which is the thing being
 * ruled out.
 *
 * **Two of these tests were wrong the first time, and a mutation run is what said so.** The
 * check on the modules' code read string literals only, so a field named as an object key,
 * `{ persona: ... }`, passed it: a key is an identifier. And every test rendered one section at
 * a time, so a form that drew the first section's schema under every heading passed all of
 * them. Both are fixed below and both mutations are now caught by name.
 *
 * Task ids: M20.1.2
 */

import { fireEvent, render } from "@testing-library/react";
import type { RJSFSchema } from "@rjsf/utils";
import ts from "typescript";
import { describe, expect, test } from "vitest";
import { ManifestForm } from "../src/components/ManifestForm";
import {
  MANIFEST_FORM_SCHEMA,
  UnreadableManifestForm,
  readManifestForm,
  sectionData,
  type ManifestSection,
} from "../src/components/manifestSections";
import { CHECK_THESE_ANSWERS } from "../src/components/SchemaForm";
import {
  backendDisplayNameChars,
  backendFormVersion,
  backendManifestPaths,
  backendSections,
} from "./support/python";
import { readConsoleFile } from "./support/repo";
import { parseConsoleSource } from "./support/typescript";

function theDocument(): { schema: string; sections: { section: string; schema: unknown }[] } {
  return JSON.parse(readConsoleFile("tests/fixtures/manifest-form.json"));
}

function sections(): readonly ManifestSection[] {
  return readManifestForm(theDocument());
}

function section(name: string): ManifestSection {
  const found = sections().find((one) => one.section === name);
  if (found === undefined) {
    throw new Error(`The builder form has no section called ${name}.`);
  }
  return found;
}

function controlIds(container: HTMLElement): string[] {
  return [...container.querySelectorAll("input, select, textarea")].map((element) => element.id);
}

/**
 * The controls a section's schema declares, in the order the form library lays them out.
 *
 * One per field that is not a list, named by the section and the path to the field. A list
 * starts with no items and so with no control until somebody adds one.
 */
function declaredControls(one: ManifestSection): string[] {
  const definitions = (one.schema.$defs ?? {}) as Record<string, RJSFSchema>;
  const ids: string[] = [];
  const walk = (schema: RJSFSchema, path: readonly string[]): void => {
    const named = typeof schema.$ref === "string" ? schema.$ref.split("/").pop() : undefined;
    const resolved: RJSFSchema =
      named === undefined ? schema : { ...definitions[named], ...schema };
    if (resolved.type === "object" && resolved.properties !== undefined) {
      for (const [name, property] of Object.entries(resolved.properties)) {
        walk(property as RJSFSchema, [...path, name]);
      }
      return;
    }
    if (resolved.type !== "array") {
      ids.push([one.section, ...path].join("_"));
    }
  };
  walk(one.schema, []);
  return ids;
}

/**
 * Every name and piece of text a module's code carries: identifiers, string literals, template
 * text and JSX text. Identifiers are read as well as strings because a field named as an object
 * key names it just as plainly, and comments are not read because prose about a field is not
 * code naming one.
 */
function wordsIn(path: string): string[] {
  const found: string[] = [];
  const visit = (node: ts.Node): void => {
    if (
      ts.isIdentifier(node) ||
      ts.isStringLiteral(node) ||
      ts.isNoSubstitutionTemplateLiteral(node) ||
      ts.isJsxText(node)
    ) {
      found.push(node.text.trim());
    } else if (ts.isTemplateExpression(node)) {
      found.push(node.head.text, ...node.templateSpans.map((span) => span.literal.text));
    }
    node.forEachChild(visit);
  };
  parseConsoleSource(path).forEachChild(visit);
  return found;
}

describe("a form generated from the manifest schema", () => {
  test("every control on a section is a field its schema declares, and every declared field is a control", () => {
    // What breaks if this is deleted: the leaf's own claim, section by section. A control that
    // no field declares was written by somebody, and a declared field with no control is a part
    // of the manifest nobody building an agent can set. The sections are rendered together, as
    // a page would render them, so a section that drew another section's schema fails here.
    const all = sections();
    const container = render(<ManifestForm caption="An agent" sections={all} />).container;

    for (const one of all) {
      const region = container.querySelector(`section[aria-label="${one.section}"]`);
      expect(region, one.section).toBeInstanceOf(HTMLElement);
      expect(controlIds(region as HTMLElement), one.section).toEqual(declaredControls(one));
    }
  });

  test("a field the schema gains is a control and a field it loses is gone, with no change to the console", () => {
    // What breaks if this is deleted: every test here passes for a form that renders today's
    // manifest from memory. Handing the same component a schema with a field added and a field
    // removed is what "generated" has to survive.
    const identity = section("identity");
    const changed = structuredClone(identity.schema) as RJSFSchema;
    const holder = (changed.properties as Record<string, RJSFSchema>)["identity"] as RJSFSchema;
    const fields = holder.properties as Record<string, RJSFSchema>;
    fields["nickname"] = { type: "string", title: "Nickname" };
    delete fields["summary"];
    const reshaped: ManifestSection = { section: "identity", schema: changed };

    const container = render(<ManifestForm caption="An agent" sections={[reshaped]} />).container;
    const ids = controlIds(container);

    expect(ids).toContain("identity_identity_nickname");
    expect(ids).not.toContain("identity_identity_summary");
    expect(ids).toEqual(declaredControls(reshaped));
  });

  test("the model's bound on a name is the bound the rendered form enforces", () => {
    // What breaks if this is deleted: the bound reaches the schema and not the browser. The
    // figure is read from `brain.agents.model`, so this is the model's own limit arriving at an
    // input through the generated schema: one character over is refused by the form and exactly
    // the limit is submitted.
    const bound = backendDisplayNameChars();
    const submitted: unknown[] = [];
    const container = render(
      <ManifestForm
        caption="An agent"
        sections={[section("identity")]}
        onSubmit={(_, data) => submitted.push(data)}
      />,
    ).container;
    const fill = (id: string, value: string): void => {
      fireEvent.change(container.querySelector(`#${id}`) as Element, { target: { value } });
    };
    const submit = (): void => {
      fireEvent.submit(container.querySelector("form") as HTMLFormElement);
    };

    fill("identity_identity_template_id", "support_triage");
    fill("identity_identity_version", "1");
    fill("identity_identity_published_by", "author");
    fill("identity_identity_display_name", "x".repeat(bound + 1));
    submit();
    expect(submitted).toHaveLength(0);
    expect(container.querySelector(".notice__title")?.textContent).toBe(CHECK_THESE_ANSWERS);

    fill("identity_identity_display_name", "x".repeat(bound));
    submit();
    expect(submitted).toHaveLength(1);
  });

  test("nothing in the form's modules names a manifest field, so every field on the screen came from the schema", () => {
    // What breaks if this is deleted: a field quietly written into the component, a `ui:widget`
    // for `persona` or a label for `display_name`, which is correct until the model renames it.
    // The manifest's paths are read out of `brain.agents.template`, and every identifier and
    // piece of text in both modules' code is compared with them.
    const segments = new Set(backendManifestPaths().flatMap((path) => path.split(".")));
    expect(segments.has("display_name")).toBe(true);

    for (const file of ["src/components/ManifestForm.tsx", "src/components/manifestSections.ts"]) {
      const words = wordsIn(file);
      expect(words.length, file).toBeGreaterThan(0);
      expect(
        words.filter((word) => segments.has(word)),
        file,
      ).toEqual([]);
    }
  });
});

describe("what a section is given and what it sends", () => {
  test("a section submits its own fields and none that another section holds", () => {
    // What breaks if this is deleted: saving the knowledge section writes the tool lists nobody on
    // that screen was shown, because `authority` is edited in two sections and the form library
    // submits whatever it was handed. The draft is cut to what the section's schema declares.
    const draft = {
      identity: { display_name: "Triage" },
      persona: "Answers tickets.",
      authority: { scope: { clauses: [] }, allowed_tools: ["helpdesk.read_ticket"] },
    };
    const knowledge = section("knowledge");
    expect(sectionData(knowledge.schema, draft)).toEqual({ authority: { scope: { clauses: [] } } });

    const submitted: [string, unknown][] = [];
    const container = render(
      <ManifestForm
        caption="An agent"
        sections={[knowledge]}
        draft={draft}
        onSubmit={(name, data) => submitted.push([name, data])}
      />,
    ).container;
    fireEvent.submit(container.querySelector("form") as HTMLFormElement);

    expect(submitted).toHaveLength(1);
    const [name, data] = submitted[0] as [string, Record<string, unknown>];
    expect(name).toBe("knowledge");
    expect(Object.keys(data["authority"] as object)).toEqual(["scope"]);
    expect(data).not.toHaveProperty("identity");
    expect(data).not.toHaveProperty("persona");
  });

  test("two sections that declare an object of the same name share no id on one page", () => {
    // What breaks if this is deleted: the knowledge and tools sections both hold `authority`, the
    // library names controls after their paths, and one page gets two elements with one id, so a
    // label points at the wrong input for anybody using a screen reader.
    const container = render(<ManifestForm caption="An agent" sections={sections()} />).container;
    const ids = [...container.querySelectorAll("[id]")].map((element) => element.id);

    expect(ids.length).toBeGreaterThan(0);
    expect(new Set(ids).size).toBe(ids.length);
  });
});

describe("reading the document", () => {
  test("the sections are the builder's seven, in its order, in the version this console reads", () => {
    // What breaks if this is deleted: the console renders a section list or a document version the
    // builder does not declare, and a section goes missing with every other test here still green.
    expect(sections().map((one) => one.section)).toEqual(backendSections());
    expect(MANIFEST_FORM_SCHEMA).toBe(backendFormVersion());
  });

  test("a body that is not the form is refused rather than rendered as a shorter form", () => {
    // What breaks if this is deleted: a broken or newer body renders as a form with a section
    // missing, and a shorter form looks exactly like a complete one. The good document is the
    // positive sibling.
    const good = theDocument();
    const first = good.sections[0];
    const bodies: unknown[] = [
      null,
      { ...good, schema: "brain.builder.form.v0" },
      { ...good, sections: [] },
      { ...good, sections: [...good.sections, first] },
      { ...good, sections: [{ section: "identity", schema: { type: "string" } }] },
      { ...good, sections: [{ section: "", schema: first?.schema }] },
    ];
    for (const body of bodies) {
      expect(() => readManifestForm(body)).toThrow(UnreadableManifestForm);
    }
    expect(readManifestForm(good)).toHaveLength(backendSections().length);
  });
});
