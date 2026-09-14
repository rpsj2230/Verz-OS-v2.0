/**
 * The facts the agent workspace copies from the Python side, read back out of it, plus the
 * two questions about a TypeScript shape that only a parser can answer.
 *
 * Everything here exists for the reason `support/repo.ts` gives about itself: a constant
 * compared against itself is green for every value it could hold, and this console's agent
 * workspace copies five things. The address prefix, the tab vocabulary and its order, the
 * composition parts, the field source that means a value was set locally, and the list of
 * field names that would tell a reader what they were not shown. Each is read from the
 * module that owns it, and each reader throws when it finds nothing, so a rename fails
 * loudly here instead of quietly turning an assertion into a comparison between two empty
 * things.
 *
 * The two shape questions are which members an interface declares optional, and which
 * members it declares at all. The first is the whole of the disclosure design on these
 * screens: a field that is absent when the reader may not be told, and absent when there is
 * nothing to tell, is one absence, and the day somebody makes `template` on a diff row
 * optional is the day a row can say a path differs while withholding what it differs to.
 * `tsconfig.json` has `exactOptionalPropertyTypes`, so the question a parser answers here is
 * exactly the question the type system is enforcing.
 */

import ts from "typescript";
import { extractOne, readRepoFile } from "./repo";

const WORKSPACE = "src/brain/console/workspace.py";
const TEMPLATE = "src/brain/agents/template.py";
const JOBS = "src/brain/ops/jobs.py";

/**
 * The body of a Python declaration that opens a bracket and closes it on a line of its own.
 *
 * Narrow, and it throws rather than returning what it found so far. A tolerant reader that
 * stopped at the first close bracket would return the first entry of a mapping and every
 * assertion built on it would be a comparison against a set of one.
 */
function blockAfter(source: string, opener: RegExp, what: string): string {
  const found = opener.exec(source);
  if (!found) {
    throw new Error(
      `Could not find ${what} using ${String(opener)}. The Python source has moved, so the ` +
        "console's copy of it is no longer being checked against anything.",
    );
  }
  const after = source.slice(found.index + found[0].length);
  const ends = /^\)/m.exec(after);
  if (!ends) {
    throw new Error(`${what} never closes at the start of a line; the reader is stale.`);
  }
  return after.slice(0, ends.index);
}

/**
 * Which composition part each manifest path supplies, from
 * `brain.console.workspace.PART_OF_PATH`.
 *
 * That mapping is the thing `brain.console.workspace` says was missing when it rejected a
 * second diff: not the diff, which `brain.agents.upgrade` already produces, but the map from
 * a manifest path to the part of the composition it supplies. It is therefore the vocabulary
 * a rendered composition diff groups by, and the console holds no second copy of it.
 */
export function backendPartOfPath(): Record<string, string> {
  const body = blockAfter(
    readRepoFile(WORKSPACE),
    /^PART_OF_PATH: Mapping\[str, Part\] = MappingProxyType\($/m,
    "PART_OF_PATH",
  );
  const mapping: Record<string, string> = {};
  for (const entry of body.matchAll(/"([^"]+)": Part\.([A-Z_]+),/g)) {
    if (entry[1] && entry[2]) {
      mapping[entry[1]] = entry[2];
    }
  }
  if (Object.keys(mapping).length === 0) {
    throw new Error("Parsed no entries from PART_OF_PATH; the reader is stale.");
  }
  return mapping;
}

/**
 * The tab keys in the order `brain.console.workspace.TABS` declares them.
 *
 * The order is information there, in that module's own words: it is the order somebody
 * reads the strip in. A console fixture that invented its own order would be exercising a
 * strip nobody will ever see.
 */
export function backendTabOrder(): string[] {
  const source = readRepoFile(WORKSPACE);
  const body = blockAfter(
    source,
    /^TABS: Final\[tuple\[WorkspaceTab, \.\.\.\]\] = \($/m,
    "TABS",
  );
  const keys = [...body.matchAll(/^\s+Tab\.([A-Z_]+),$/gm)].map((entry) => entry[1] ?? "");
  if (keys.length === 0) {
    throw new Error("Parsed no tabs from TABS; the reader is stale.");
  }
  return keys;
}

/** `brain.console.workspace.TAB_COUNT`, which that module pins so a person can quote it. */
export function backendTabCount(): number {
  return Number(
    extractOne(readRepoFile(WORKSPACE), /^TAB_COUNT: Final = (\d+)$/m, "TAB_COUNT"),
  );
}

/** `brain.console.workspace.DEEP_LINK_PREFIX`, the address every tab of every agent is under. */
export function backendDeepLinkPrefix(): string {
  return extractOne(
    readRepoFile(WORKSPACE),
    /^DEEP_LINK_PREFIX: Final = "([^"]+)"$/m,
    "DEEP_LINK_PREFIX",
  );
}

/** The value of one member of `brain.agents.template.FieldSource`. */
export function backendFieldSource(member: string): string {
  return extractOne(
    readRepoFile(TEMPLATE),
    new RegExp(`^    ${member} = "([^"]+)"$`, "m"),
    `FieldSource.${member}`,
  );
}

/**
 * `brain.ops.jobs.NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT`, the names a field telling a reader
 * what they were not shown arrives under.
 *
 * Read rather than copied, because the point of the list is that it grows: a name added
 * there by somebody who has just found a new way to write "and also what I hid" should
 * tighten this console's check on the same day, without anybody remembering to.
 */
export function backendHiddenCountNames(): string[] {
  const body = blockAfter(
    readRepoFile(JOBS),
    /^NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT: Final\[frozenset\[str\]\] = frozenset\($/m,
    "NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT",
  );
  const names = [...body.matchAll(/"([a-z_]+)"/g)].map((entry) => entry[1] ?? "");
  if (names.length === 0) {
    throw new Error("Parsed no names from NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT; reader is stale.");
  }
  return names;
}

/** `hiddenCount` written the way a Python field name would be, so the two can be compared. */
export function asPythonName(member: string): string {
  return member.replace(/([A-Z])/g, (letter) => `_${letter.toLowerCase()}`);
}

function findInterface(source: ts.SourceFile, name: string): ts.InterfaceDeclaration {
  const found: ts.InterfaceDeclaration[] = [];
  const visit = (node: ts.Node): void => {
    if (ts.isInterfaceDeclaration(node) && node.name.text === name) {
      found.push(node);
    }
    node.forEachChild(visit);
  };
  source.forEachChild(visit);
  const declared = found[0];
  if (!declared) {
    throw new Error(
      `No interface named ${name} in ${source.fileName}. It has been renamed or turned into ` +
        "a type alias, so the shape this checks is no longer being checked.",
    );
  }
  return declared;
}

/** Every member an interface declares, in source order. */
export function membersOf(source: ts.SourceFile, name: string): string[] {
  return findInterface(source, name).members.map((member) => member.name?.getText(source) ?? "");
}

/**
 * The members an interface declares optional, in source order.
 *
 * The question the disclosure design turns on. A required member is a fact that is always
 * there; an optional one is a fact that is absent when the reader may not be told and
 * absent when there is nothing to tell. Moving a member between the two is the change that
 * either leaks or lies, and it is one character.
 */
export function optionalMembersOf(source: ts.SourceFile, name: string): string[] {
  return findInterface(source, name)
    .members.filter((member) => member.questionToken !== undefined)
    .map((member) => member.name?.getText(source) ?? "");
}
