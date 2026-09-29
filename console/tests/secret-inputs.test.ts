/**
 * Every input a credential is typed into is the kit's secret field, and that field is masked.
 *
 * Found on the owner's install on 2026-09-29: the API key field on a credential's profile was
 * `type="text"`, so a pasted key showed in clear, and Connect Lark and the first-run staff list
 * check each drew their own plain text inputs for a secret. `ui/secret-field.tsx` is masked now and
 * is the one place a password input is allowed (`scripts/check-boundaries.mjs`); this file holds
 * every other input that is named like a credential to it, by reading the source as a syntax tree.
 *
 * Task ids: M27.8.7, M27.10.2
 */

import ts from "typescript";
import { describe, expect, test } from "vitest";
import { consoleSourcePaths, parseConsoleSource } from "./support/typescript";

/** What a credential's input is called by its `id`, `name` or `htmlFor`. */
const CREDENTIAL = /secret|password|passphrase|token|api[_-]?key|encrypt[_-]?key|private[_-]?key/i;

/** The file allowed to render the masked input itself. */
const THE_SECRET_FIELD = "src/components/ui/secret-field.tsx";

interface Input {
  readonly file: string;
  readonly line: number;
  readonly names: readonly string[];
  readonly type: string;
}

/** The text an attribute's value spells, for a string or a template with no gaps, else "". */
function attributeText(attribute: ts.JsxAttribute): string {
  const value = attribute.initializer;
  if (value === undefined) {
    return "";
  }
  if (ts.isStringLiteral(value)) {
    return value.text;
  }
  if (ts.isJsxExpression(value) && value.expression !== undefined) {
    const inner = value.expression;
    if (ts.isStringLiteral(inner) || ts.isNoSubstitutionTemplateLiteral(inner)) {
      return inner.text;
    }
    if (ts.isTemplateExpression(inner)) {
      return [inner.head.text, ...inner.templateSpans.map((span) => span.literal.text)].join("");
    }
  }
  return "";
}

/** Every `<input>` and `<Input>` in one file, with the names it is addressed by and its type. */
function inputsIn(file: string): Input[] {
  const source = parseConsoleSource(file);
  const found: Input[] = [];
  const visit = (node: ts.Node): void => {
    if ((ts.isJsxSelfClosingElement(node) || ts.isJsxOpeningElement(node)) && ["input", "Input"].includes(node.tagName.getText(source))) {
      const attributes = node.attributes.properties.filter(ts.isJsxAttribute);
      const text = (name: string): string => {
        const one = attributes.find((attribute) => attribute.name.getText(source) === name);
        return one === undefined ? "" : attributeText(one);
      };
      found.push({
        file,
        line: source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1,
        names: [text("id"), text("name"), text("aria-label")].filter((one) => one !== ""),
        type: text("type"),
      });
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return found;
}

const EVERY_INPUT = consoleSourcePaths("src")
  .filter((one) => one.endsWith(".tsx"))
  .flatMap(inputsIn);

describe("an input a credential is typed into", () => {
  test("is the kit's secret field and nothing else, anywhere in the console", () => {
    // What breaks if this is deleted: a page draws its own text input for a key or a secret again,
    // which shows the value while it is typed and holds it in React state, as Connect Lark and the
    // first-run staff list check did until 2026-09-29.
    const credentialInputs = EVERY_INPUT.filter(
      (one) => one.file !== THE_SECRET_FIELD && one.type !== "checkbox" && one.names.some((name) => CREDENTIAL.test(name)),
    );
    expect(credentialInputs.map((one) => `${one.file}:${String(one.line)} ${one.names.join(" ")}`)).toEqual([]);
  });

  test("the check reads real inputs, so an empty answer above is a finding about the code", () => {
    // What breaks if this is deleted: a walker that found no inputs at all would pass the test
    // above on every console, including one full of plain text inputs for secrets.
    expect(EVERY_INPUT.length).toBeGreaterThan(20);
    expect(EVERY_INPUT.some((one) => one.names.some((name) => /app_id/.test(name)))).toBe(true);
    expect(inputsIn(THE_SECRET_FIELD).map((one) => one.type)).toEqual(["password"]);
  });

  test("the secret field is masked, and is the only password input in the console", () => {
    // What breaks if this is deleted: the field goes back to `type="text"` and the Credentials
    // screen shows a pasted API key in clear, which is what the owner found.
    const masked = EVERY_INPUT.filter((one) => one.type === "password").map((one) => one.file);
    expect(masked).toEqual([THE_SECRET_FIELD]);
  });
});
