/**
 * Every class name the console's markup uses, read out of its source with the line it is written on.
 *
 * A class is written in four shapes here and all four are read: a string in a `className` attribute,
 * a `className` or `class` property of an object handed to a component, the string arguments of
 * `cn`, `clsx` and `twMerge`, and the base string and the `variants` values of a `cva` call (its
 * `defaultVariants` and its variant names are words about the component, not classes, and are not
 * read). Inside each, only the positions that become a class are followed: the right of `&&`, both
 * branches of a conditional, an array's elements, the keys of an object handed to `cn`. A test on the
 * left of `&&` (`tone === "plain" && "border-line"`) is not a class and is skipped, which is the
 * mistake a pattern over the text makes and a reading of the tree does not.
 *
 * A template's dynamic parts are not guessed at: the word that touches a `${}` is a fragment of a
 * name, not a name, so it is dropped rather than reported.
 *
 * **What this does not read.** A class held in a constant and handed to `className` by name
 * (`const TONE = { ok: "text-ok" }`) is not a class list here, because a record of strings is not
 * necessarily one. That is the loss this reading accepts, and it is why `tests/styled-classes.test.ts`
 * also compiles every name it does find rather than trusting a count.
 *
 * **Why the syntax tree and not a pattern.** The same reason as `support/typescript.ts`: a doc
 * comment that quotes a class name to forbid it would satisfy a text search for it.
 *
 * Task ids: M27.15.72
 */

import ts from "typescript";
import { consoleSourcePaths, parseConsoleSource } from "./typescript";

/** One class name as written, and where. */
export interface ClassUse {
  /** Forward-slashed, relative to `console/`. */
  readonly file: string;
  readonly line: number;
  readonly name: string;
}

/** The calls whose arguments are class lists. */
export const CLASS_CALLS: ReadonlySet<string> = new Set(["cn", "clsx", "twMerge"]);

/** The attribute and property names whose value is a class list. */
export const CLASS_PROPERTIES: ReadonlySet<string> = new Set(["className", "class"]);

/** The directory whose markup is the console's. */
export const MARKUP_ROOT = "src";

interface Piece {
  readonly text: string;
  readonly node: ts.Node;
  /** A substitution touches the start of the text. */
  readonly opens: boolean;
  /** A substitution touches the end of the text. */
  readonly closes: boolean;
}

function everyNode(source: ts.SourceFile): ts.Node[] {
  const nodes: ts.Node[] = [];
  const visit = (node: ts.Node): void => {
    nodes.push(node);
    node.forEachChild(visit);
  };
  source.forEachChild(visit);
  return nodes;
}

/** The class words in one piece of literal text; the words a substitution cuts are dropped. */
function wordsOf(piece: Piece): string[] {
  const words = piece.text.split(/\s+/u).filter((one) => one !== "");
  if (piece.opens && words.length > 0 && !/^\s/u.test(piece.text)) {
    words.shift();
  }
  if (piece.closes && words.length > 0 && !/\s$/u.test(piece.text)) {
    words.pop();
  }
  return words;
}

/** The literal text that becomes a class in one expression, following only the positions that do. */
function classPieces(expression: ts.Node | undefined, source: ts.SourceFile, keysAreClasses: boolean): Piece[] {
  if (expression === undefined) {
    return [];
  }
  if (ts.isStringLiteral(expression) || ts.isNoSubstitutionTemplateLiteral(expression)) {
    return [{ text: expression.text, node: expression, opens: false, closes: false }];
  }
  if (ts.isTemplateExpression(expression)) {
    const pieces: Piece[] = [{ text: expression.head.text, node: expression.head, opens: false, closes: true }];
    expression.templateSpans.forEach((span, at) => {
      pieces.push(...classPieces(span.expression, source, keysAreClasses));
      pieces.push({
        text: span.literal.text,
        node: span.literal,
        opens: true,
        closes: at < expression.templateSpans.length - 1,
      });
    });
    return pieces;
  }
  if (ts.isParenthesizedExpression(expression) || ts.isAsExpression(expression) || ts.isNonNullExpression(expression)) {
    return classPieces(expression.expression, source, keysAreClasses);
  }
  if (ts.isJsxExpression(expression)) {
    return classPieces(expression.expression, source, keysAreClasses);
  }
  if (ts.isBinaryExpression(expression)) {
    const operator = expression.operatorToken.kind;
    if (operator === ts.SyntaxKind.AmpersandAmpersandToken) {
      return classPieces(expression.right, source, keysAreClasses);
    }
    if (operator === ts.SyntaxKind.BarBarToken || operator === ts.SyntaxKind.QuestionQuestionToken) {
      return [...classPieces(expression.left, source, keysAreClasses), ...classPieces(expression.right, source, keysAreClasses)];
    }
    return [];
  }
  if (ts.isConditionalExpression(expression)) {
    return [
      ...classPieces(expression.whenTrue, source, keysAreClasses),
      ...classPieces(expression.whenFalse, source, keysAreClasses),
    ];
  }
  if (ts.isArrayLiteralExpression(expression)) {
    return expression.elements.flatMap((one) => classPieces(one, source, keysAreClasses));
  }
  if (ts.isObjectLiteralExpression(expression) && keysAreClasses) {
    // `cn({ "text-crit": failed })`: the key is the class and the value is the condition.
    return expression.properties.flatMap((one) =>
      ts.isPropertyAssignment(one) && (ts.isStringLiteral(one.name) || ts.isNoSubstitutionTemplateLiteral(one.name))
        ? [{ text: one.name.text, node: one.name, opens: false, closes: false }]
        : [],
    );
  }
  return [];
}

/** The class strings of a `cva` call: its base, and the values under `variants` at any depth. */
function cvaPieces(call: ts.CallExpression, source: ts.SourceFile): Piece[] {
  const pieces = classPieces(call.arguments[0], source, false);
  const config = call.arguments[1];
  if (config === undefined || !ts.isObjectLiteralExpression(config)) {
    return pieces;
  }
  const values = (node: ts.Node): Piece[] => {
    if (ts.isObjectLiteralExpression(node)) {
      return node.properties.flatMap((one) => (ts.isPropertyAssignment(one) ? values(one.initializer) : []));
    }
    return classPieces(node, source, false);
  };
  for (const property of config.properties) {
    if (!ts.isPropertyAssignment(property)) {
      continue;
    }
    const name = property.name.getText(source);
    if (name === "variants") {
      pieces.push(...values(property.initializer));
    }
    if (name === "compoundVariants" && ts.isArrayLiteralExpression(property.initializer)) {
      for (const entry of property.initializer.elements) {
        if (!ts.isObjectLiteralExpression(entry)) {
          continue;
        }
        for (const field of entry.properties) {
          if (ts.isPropertyAssignment(field) && CLASS_PROPERTIES.has(field.name.getText(source))) {
            pieces.push(...classPieces(field.initializer, source, false));
          }
        }
      }
    }
  }
  return pieces;
}

/** Every piece of literal class text in one file. */
function piecesIn(source: ts.SourceFile): Piece[] {
  const pieces: Piece[] = [];
  for (const node of everyNode(source)) {
    if (ts.isJsxAttribute(node) && CLASS_PROPERTIES.has(node.name.getText(source))) {
      pieces.push(...classPieces(node.initializer, source, false));
    } else if (ts.isPropertyAssignment(node) && CLASS_PROPERTIES.has(node.name.getText(source))) {
      pieces.push(...classPieces(node.initializer, source, false));
    } else if (ts.isCallExpression(node)) {
      const callee = node.expression.getText(source);
      if (CLASS_CALLS.has(callee)) {
        node.arguments.forEach((one) => pieces.push(...classPieces(one, source, true)));
      } else if (callee === "cva") {
        pieces.push(...cvaPieces(node, source));
      }
    }
  }
  return pieces;
}

/** Every class name written in one file, one entry per written use. */
export function classUsesIn(file: string): ClassUse[] {
  return classUsesInSource(parseConsoleSource(file));
}

/** The same reading over source text written elsewhere, so a test can say what each shape yields. */
export function classUsesInText(text: string, file = "src/example.tsx"): ClassUse[] {
  return classUsesInSource(ts.createSourceFile(file, text, ts.ScriptTarget.ES2022, true, ts.ScriptKind.TSX));
}

function classUsesInSource(source: ts.SourceFile): ClassUse[] {
  const file = source.fileName;
  const seen = new Set<string>();
  const uses: ClassUse[] = [];
  for (const piece of piecesIn(source)) {
    const line = source.getLineAndCharacterOfPosition(piece.node.getStart(source)).line + 1;
    for (const name of wordsOf(piece)) {
      const key = `${String(line)} ${name}`;
      if (!seen.has(key)) {
        seen.add(key);
        uses.push({ file, line, name });
      }
    }
  }
  return uses;
}

/** Every class name used anywhere in the console's source, in a stable order. */
export function everyClassUse(): ClassUse[] {
  return consoleSourcePaths(MARKUP_ROOT).flatMap(classUsesIn);
}
