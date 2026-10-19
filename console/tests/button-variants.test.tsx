/**
 * The button's variants as the owner's design of record names them: primary, quiet and danger, with
 * outline, secondary and link beside them, and no other name anywhere in the console.
 *
 * **Structure, not text.** Every JSX element that is a button (`Button`, and the two dialog buttons
 * that wrap it) and every `buttonVariants({ variant })` call in `src` is parsed, and its `variant` is
 * required to be a string literal in the named set, or a conditional whose two branches are. A
 * computed name (`variant={row.kind}`) is refused because a type cannot see through data, and a
 * button's look is a statement about the act, never about a row. shadcn/ui's `default`, `ghost` and
 * `destructive` are refused by name, because they describe how the button looks and the day somebody
 * pastes a component copied from the template they come straight back.
 *
 * Task ids: M27.15.71
 */

import ts from "typescript";
import { describe, expect, test } from "vitest";
import { render } from "@testing-library/react";
import { BUTTON_VARIANTS, Button } from "../src/components/ui/button";
import { consoleSourcePaths, parseConsoleSource } from "./support/typescript";

/** The names a page may use. Written out here, so a rename in the component moves this test. */
const NAMED = ["primary", "outline", "secondary", "quiet", "danger", "link"];

/** Elements that draw a button and take its `variant` as theirs. */
const BUTTON_TAGS = new Set(["Button", "AlertDialogAction", "AlertDialogCancel"]);

/** What a `variant` value may be: a literal in the set, or a conditional of two such. */
function problemWith(value: ts.Expression | undefined, source: ts.SourceFile): string | null {
  if (value === undefined) {
    return "no value";
  }
  if (ts.isParenthesizedExpression(value)) {
    return problemWith(value.expression, source);
  }
  if (ts.isConditionalExpression(value)) {
    return problemWith(value.whenTrue, source) ?? problemWith(value.whenFalse, source);
  }
  // The component layer's wrappers (the dialogs' action and cancel) pass the caller's `variant` on,
  // typed against the button's own props, so the caller is where the literal is checked.
  if (ts.isIdentifier(value) && value.text === "variant" && /(^|[\\/])components[\\/]ui[\\/]/.test(source.fileName)) {
    return null;
  }
  if (ts.isStringLiteral(value) || ts.isNoSubstitutionTemplateLiteral(value)) {
    return NAMED.includes(value.text) ? null : `"${value.text}" is not a named variant`;
  }
  return `${value.getText(source)} is computed, and a button's variant is written where it is drawn`;
}

/** Every button variant written in one parsed file that is not a named one. */
export function unnamedButtonVariants(source: ts.SourceFile): string[] {
  const found: string[] = [];
  const visit = (node: ts.Node): void => {
    if ((ts.isJsxSelfClosingElement(node) || ts.isJsxOpeningElement(node)) && BUTTON_TAGS.has(node.tagName.getText(source))) {
      for (const attribute of node.attributes.properties) {
        if (ts.isJsxAttribute(attribute) && attribute.name.getText(source) === "variant" && attribute.initializer) {
          const inner = ts.isJsxExpression(attribute.initializer) ? attribute.initializer.expression : attribute.initializer;
          const problem = problemWith(inner, source);
          if (problem !== null) {
            found.push(`${source.fileName}: ${problem}`);
          }
        }
      }
    }
    if (ts.isCallExpression(node) && node.expression.getText(source) === "buttonVariants") {
      const options = node.arguments[0];
      if (options !== undefined && ts.isObjectLiteralExpression(options)) {
        for (const property of options.properties) {
          if (ts.isPropertyAssignment(property) && property.name.getText(source) === "variant") {
            const problem = problemWith(property.initializer, source);
            if (problem !== null) {
              found.push(`${source.fileName}: ${problem}`);
            }
          }
        }
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return found;
}

describe("the button's variants", () => {
  test("the component offers primary, outline, secondary, quiet, danger and link, and nothing else", () => {
    // What breaks if this is deleted: the set a page may choose from changes without anybody having
    // decided it, and the sweep below checks pages against a list nobody is holding to the component.
    expect([...BUTTON_VARIANTS]).toEqual(NAMED);
  });

  test("every button in the console names one of them", () => {
    // What breaks if this is deleted: a page that pastes `variant="destructive"` or `variant="ghost"`
    // from shadcn/ui (type-checked away only where the value is a literal), or one that computes the
    // look from a row, and the console grows a third and fourth way of drawing the same act.
    const paths = consoleSourcePaths("src");
    expect(paths.length).toBeGreaterThan(200);
    const found = paths.flatMap((path) => unnamedButtonVariants(parseConsoleSource(path)));
    expect(found).toEqual([]);
  });

  test("the sweep refuses the template's names and a computed one, and accepts the named ones", () => {
    // What breaks if this is deleted: the sweep above is satisfied by a reader that finds nothing.
    const parse = (code: string) =>
      ts.createSourceFile("example.tsx", code, ts.ScriptTarget.ES2022, true, ts.ScriptKind.TSX);
    expect(unnamedButtonVariants(parse('const a = <Button variant="ghost">x</Button>;'))).toHaveLength(1);
    expect(unnamedButtonVariants(parse('const a = <Button variant="destructive">x</Button>;'))).toHaveLength(1);
    expect(unnamedButtonVariants(parse('const a = <Button variant="default">x</Button>;'))).toHaveLength(1);
    expect(unnamedButtonVariants(parse("const a = <Button variant={row.kind}>x</Button>;"))).toHaveLength(1);
    expect(unnamedButtonVariants(parse('const a = <AlertDialogAction variant={on ? "danger" : "ghost"}>x</AlertDialogAction>;'))).toHaveLength(1);
    expect(unnamedButtonVariants(parse('const a = buttonVariants({ variant: "ghost" });'))).toHaveLength(1);
    expect(unnamedButtonVariants(parse('const a = <Button variant={on ? "danger" : "quiet"}>x</Button>;'))).toEqual([]);
    // A pass-through of a typed `variant` is the component layer's alone, never a page's.
    const passed = 'const a = <Button variant={variant} asChild>x</Button>;';
    const layer = (name: string) => ts.createSourceFile(name, passed, ts.ScriptTarget.ES2022, true, ts.ScriptKind.TSX);
    expect(unnamedButtonVariants(layer("src/components/ui/alert-dialog.tsx"))).toEqual([]);
    expect(unnamedButtonVariants(layer("src/pages/agents/AgentsPage.tsx"))).toHaveLength(1);
    expect(unnamedButtonVariants(parse('const a = <Badge variant="destructive">x</Badge>; const b = <Button>y</Button>;'))).toEqual([]);
  });

  test("primary, quiet and danger are drawn as three different buttons and a bare button is primary", () => {
    // What breaks if this is deleted: a danger button drawn exactly like the primary one, or a quiet
    // action as loud as the act a page is for (M27.15.71).
    const drawn = render(
      <div>
        <Button>Save</Button>
        <Button variant="quiet">Cancel</Button>
        <Button variant="danger">Remove</Button>
      </div>,
    );
    const buttons = [...drawn.container.querySelectorAll("button")];
    expect(buttons.map((one) => one.getAttribute("data-variant"))).toEqual(["primary", "quiet", "danger"]);
    expect(new Set(buttons.map((one) => one.className)).size).toBe(3);
    drawn.unmount();
  });
});
