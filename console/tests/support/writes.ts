/**
 * Every write the console can send, read out of its source, and the way a person reaches each one.
 *
 * `docs/admin-console.md` has three rules about writes: a destructive one is confirmed, a write is
 * validated before it is sent, and every control is proved to reach the system. Each needs the
 * same list first, which is every call in `src/pages` and `src/components` that sends something
 * other than a GET, and a list written by hand is the list that misses the next one. So it is read
 * from the syntax tree, by `tests/destructive-confirmed.test.ts` and
 * `tests/validated-before-write.test.tsx`, and the API addresses it names are the ones
 * `docs/console-audit.md` follows to their proofs.
 *
 * **What "reached through a confirmation" means here.** A write is a call. The function that
 * makes it is followed outwards: an immediately invoked body executes where it sits, a function
 * handed to `useCallback` or kept in a constant is followed to every place its name is used, and
 * the walk ends at the first JSX attribute it meets. The write is confirmed when every walk ends
 * at `onConfirm` on `<ConfirmAction>`, and not confirmed when any walk ends anywhere else, which
 * is reported as the attribute and the element it ended at so a reader can see the button.
 *
 * **It fails towards reporting.** A use this cannot follow (a function stored in an object, a
 * method, a name used outside any JSX) is reported as unconfirmed with what it found, never passed.
 * A dependency array is the one use skipped, because naming a function there calls nothing.
 *
 * Task ids: M27.8.4, M27.8.5, M27.8.17
 */

import ts from "typescript";
import { consoleSourcePaths, parseConsoleSource } from "./typescript";

/** One call that sends a write. */
export interface WriteSite {
  /** Forward-slashed, relative to `console/`. */
  readonly file: string;
  readonly line: number;
  /** The HTTP method, or STREAM for `openStream`, which always posts. */
  readonly method: string;
  /** The source text of the address argument, exactly as written. */
  readonly address: string;
  /** `file address`, which is how an allowlist names a write. */
  readonly key: string;
  /** Where each way of reaching the call ended, as `attribute on <Element>`. */
  readonly reachedFrom: readonly string[];
  /** True when every way of reaching it ended at a confirmation's `onConfirm`. */
  readonly confirmed: boolean;
}

/** The directories whose files can hold a control. `src/api` and `src/auth` hold none. */
export const CONTROL_DIRECTORIES = ["src/pages", "src/components"] as const;

const HOOKS_WITH_DEPENDENCIES = new Set(["useCallback", "useMemo", "useEffect", "useLayoutEffect"]);
const CONFIRMED = "onConfirm on <ConfirmAction>";

function everyNode(source: ts.SourceFile): ts.Node[] {
  const nodes: ts.Node[] = [];
  const visit = (node: ts.Node): void => {
    nodes.push(node);
    node.forEachChild(visit);
  };
  source.forEachChild(visit);
  return nodes;
}

function methodOf(call: ts.CallExpression, source: ts.SourceFile): string | null {
  const callee = call.expression.getText(source);
  if (callee === "openStream") {
    return "STREAM";
  }
  if (callee !== "request") {
    return null;
  }
  const options = call.arguments[1];
  if (options === undefined || !ts.isObjectLiteralExpression(options)) {
    return null;
  }
  for (const property of options.properties) {
    if (
      ts.isPropertyAssignment(property) &&
      property.name.getText(source) === "method" &&
      ts.isStringLiteral(property.initializer) &&
      property.initializer.text !== "GET"
    ) {
      return property.initializer.text;
    }
  }
  return null;
}

function isFunctionLike(node: ts.Node): node is ts.ArrowFunction | ts.FunctionExpression | ts.FunctionDeclaration {
  return ts.isArrowFunction(node) || ts.isFunctionExpression(node) || ts.isFunctionDeclaration(node);
}

function unwrapParentheses(node: ts.Node): ts.Node {
  let at = node;
  while (at.parent !== undefined && ts.isParenthesizedExpression(at.parent)) {
    at = at.parent;
  }
  return at;
}

/** The name a function is kept under, or null when it runs where it is written. */
function bindingOf(fn: ts.ArrowFunction | ts.FunctionExpression | ts.FunctionDeclaration, source: ts.SourceFile):
  | { readonly kind: "name"; readonly name: string }
  | { readonly kind: "inline" }
  | { readonly kind: "unfollowable"; readonly why: string } {
  if (ts.isFunctionDeclaration(fn)) {
    return fn.name === undefined ? { kind: "unfollowable", why: "an anonymous function declaration" } : { kind: "name", name: fn.name.text };
  }
  const outer = unwrapParentheses(fn);
  const parent = outer.parent;
  if (parent === undefined) {
    return { kind: "unfollowable", why: "a function with no parent" };
  }
  if (ts.isVariableDeclaration(parent) && ts.isIdentifier(parent.name)) {
    return { kind: "name", name: parent.name.text };
  }
  if (ts.isCallExpression(parent)) {
    if (parent.expression === outer) {
      // Immediately invoked: it runs where it sits.
      return { kind: "inline" };
    }
    const callee = parent.expression.getText(source);
    if (callee === "useCallback" && ts.isVariableDeclaration(parent.parent) && ts.isIdentifier(parent.parent.name)) {
      return { kind: "name", name: parent.parent.name.text };
    }
    // Handed to something that calls it from where it sits: `.map`, `.then`, a setter.
    return { kind: "inline" };
  }
  if (ts.isJsxExpression(parent)) {
    return { kind: "inline" };
  }
  return { kind: "unfollowable", why: `a function kept in ${ts.SyntaxKind[parent.kind]}` };
}

function isDependencyArrayUse(identifier: ts.Identifier, source: ts.SourceFile): boolean {
  const array = identifier.parent;
  if (array === undefined || !ts.isArrayLiteralExpression(array)) {
    return false;
  }
  const call = array.parent;
  return (
    call !== undefined &&
    ts.isCallExpression(call) &&
    call.arguments.indexOf(array) >= 1 &&
    HOOKS_WITH_DEPENDENCIES.has(call.expression.getText(source))
  );
}

function tagOf(attribute: ts.JsxAttribute, source: ts.SourceFile): string {
  const element = attribute.parent.parent;
  return element.tagName.getText(source);
}

/**
 * The places a function returned from a hook is called, when `use` is it being handed out.
 *
 * `pages/Retention.tsx` keeps its one write in `useWrite`, which returns `{ busy, failure, send }`,
 * and every control calls `write.send(...)`. Following `send` outwards from the return statement
 * would reach the hook's callers rather than the calls, so a use that is a property of a returned
 * object is followed to `x.send` on every `const x = useWrite(...)` instead. Null when `use` is
 * anything else.
 */
function returnedAs(use: ts.Identifier, source: ts.SourceFile): ts.Node[] | null {
  const property = use.parent;
  const isProperty =
    property !== undefined &&
    (ts.isShorthandPropertyAssignment(property) || (ts.isPropertyAssignment(property) && property.initializer === use));
  if (!isProperty) {
    return null;
  }
  const literal = property.parent;
  const returned = literal?.parent;
  if (literal === undefined || !ts.isObjectLiteralExpression(literal) || returned === undefined || !ts.isReturnStatement(returned)) {
    return null;
  }
  let hook: ts.Node | undefined = returned.parent;
  while (hook !== undefined && !isFunctionLike(hook)) {
    hook = hook.parent;
  }
  if (hook === undefined || !ts.isFunctionDeclaration(hook) || hook.name === undefined) {
    return null;
  }
  const hookName = hook.name.text;
  const member = property.name.getText(source);
  const holders = everyNode(source)
    .filter(
      (one): one is ts.VariableDeclaration =>
        ts.isVariableDeclaration(one) &&
        ts.isIdentifier(one.name) &&
        one.initializer !== undefined &&
        ts.isCallExpression(one.initializer) &&
        one.initializer.expression.getText(source) === hookName,
    )
    .map((one) => one.name.getText(source));
  return everyNode(source).filter(
    (one) =>
      ts.isPropertyAccessExpression(one) &&
      one.name.text === member &&
      holders.includes(one.expression.getText(source)),
  );
}

/** Where every way of reaching `node` ends. */
function reachesOf(node: ts.Node, source: ts.SourceFile, seen: Set<string>): string[] {
  let at: ts.Node | undefined = node.parent;
  while (at !== undefined) {
    if (ts.isJsxAttribute(at)) {
      return [`${at.name.getText(source)} on <${tagOf(at, source)}>`];
    }
    if (isFunctionLike(at)) {
      const binding = bindingOf(at, source);
      if (binding.kind === "unfollowable") {
        return [binding.why];
      }
      if (binding.kind === "name") {
        if (seen.has(binding.name)) {
          return [];
        }
        seen.add(binding.name);
        const uses = everyNode(source).filter(
          (one): one is ts.Identifier =>
            ts.isIdentifier(one) &&
            one.text === binding.name &&
            !(one.parent !== undefined && (ts.isVariableDeclaration(one.parent) || ts.isFunctionDeclaration(one.parent)) && one.parent.name === one) &&
            !isDependencyArrayUse(one, source),
        );
        if (uses.length === 0) {
          return [`${binding.name}, which nothing uses`];
        }
        return uses.flatMap((use) => {
          const handedOut = returnedAs(use, source);
          return handedOut === null ? reachesOf(use, source, seen) : handedOut.flatMap((one) => reachesOf(one, source, seen));
        });
      }
    }
    at = at.parent;
  }
  return ["the module itself"];
}

/** Every write call in one file. */
export function writesIn(file: string): WriteSite[] {
  const source = parseConsoleSource(file);
  const sites: WriteSite[] = [];
  for (const node of everyNode(source)) {
    if (!ts.isCallExpression(node)) {
      continue;
    }
    const method = methodOf(node, source);
    if (method === null) {
      continue;
    }
    const address = node.arguments[0]?.getText(source) ?? "";
    const reachedFrom = [...new Set(reachesOf(node, source, new Set()))];
    sites.push({
      file,
      line: source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1,
      method,
      address,
      key: `${file} ${address}`,
      reachedFrom,
      confirmed: reachedFrom.length > 0 && reachedFrom.every((one) => one === CONFIRMED),
    });
  }
  return sites;
}

let readOnce: WriteSite[] | null = null;

/**
 * Every write call in every file that can hold a control.
 *
 * Read once per test file and kept: the reading parses every page and component, which takes
 * seconds on a machine running the whole suite at once, and the source cannot change mid-run.
 */
export function everyWrite(): WriteSite[] {
  readOnce ??= CONTROL_DIRECTORIES.flatMap((directory) => consoleSourcePaths(directory)).flatMap(writesIn);
  return readOnce;
}

/** One `<ConfirmAction>` as written: its attributes by name, as source text. */
export interface Confirmation {
  readonly file: string;
  readonly line: number;
  readonly attributes: Readonly<Record<string, ts.Expression | ts.StringLiteral | null>>;
}

/** Every `<ConfirmAction>` written in a file that can hold a control. */
export function everyConfirmation(): Confirmation[] {
  const found: Confirmation[] = [];
  for (const file of CONTROL_DIRECTORIES.flatMap((directory) => consoleSourcePaths(directory))) {
    const source = parseConsoleSource(file);
    for (const node of everyNode(source)) {
      if (!(ts.isJsxSelfClosingElement(node) || ts.isJsxOpeningElement(node)) || node.tagName.getText(source) !== "ConfirmAction") {
        continue;
      }
      const attributes: Record<string, ts.Expression | ts.StringLiteral | null> = {};
      for (const property of node.attributes.properties) {
        if (!ts.isJsxAttribute(property)) {
          continue;
        }
        const initialiser = property.initializer;
        attributes[property.name.getText(source)] =
          initialiser === undefined
            ? null
            : ts.isJsxExpression(initialiser)
              ? (initialiser.expression ?? null)
              : ts.isStringLiteral(initialiser)
                ? initialiser
                : null;
      }
      found.push({
        file,
        line: source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1,
        attributes,
      });
    }
  }
  return found;
}
