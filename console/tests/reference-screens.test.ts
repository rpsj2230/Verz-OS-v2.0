/**
 * The reference screenshots are held in the docs, each console page they cover records what was
 * adapted and what was refused, and the two rejections the design keeps are true of the pages.
 *
 * `docs/reference-screens/index.json` is the record. The screenshots were compared and adapted and
 * never copied (CONB-50), and nothing used to say which page was adapted from which screen or what
 * was turned down, so the next person to read a page could not tell a deliberate refusal from an
 * omission. These tests hold the record to the code from both sides: a page the screenshots cover
 * needs a record, a record needs a page, and a refusal the record claims has to be true of the page.
 *
 * **The two rejections are asserted on the page's syntax tree and on the route table**, never on a
 * sentence the page says about itself. The Profile's own note, "there is deliberately no single on
 * and off switch", is in a string a test searching for text would find while a switch was added
 * beside it. So the learning section is read as JSX and refuses a switch, a checkbox or a toggle by
 * element, the rest of the console refuses one named for learning, and the routes and the API refuse
 * an address for operating a computer or riding a session.
 *
 * **The screenshot files themselves are not in the repository yet**, and the index says so for each
 * (`file` is null and `why_not_held` says why). The tests below hold what can be held now: that every
 * image the register names is listed, that a file the index says is held exists, and that one that is
 * not held says why. They do not pretend the images are there.
 *
 * Task ids: M27.15.83, M27.11.7, M27.11.12, M27.11.14
 */

import { existsSync } from "node:fs";
import { join } from "node:path";
import ts from "typescript";
import { describe, expect, test } from "vitest";
import { apiDocument } from "./support/openapi";
import { REPO_ROOT, readConsoleFile, readRepoFile } from "./support/repo";
import { drawnScreens } from "./support/routeTable";
import { consoleSourcePaths, parseConsoleSource } from "./support/typescript";

const FOLDER = "docs/reference-screens";

interface Screenshot {
  readonly id: string;
  readonly named_by_register: boolean;
  readonly shows: string;
  readonly pages: readonly string[];
  readonly no_page_because?: string;
  readonly file: string | null;
  readonly why_not_held?: string;
}

interface Rejection {
  readonly id: string;
  readonly words: string;
  readonly kept_at: readonly { readonly address: string; readonly section: string }[];
}

interface PageRecord {
  readonly address: string;
  readonly section: string | null;
  readonly screenshots: readonly string[];
  readonly requirements: readonly string[];
  readonly adapted: readonly string[];
  readonly refused: readonly string[];
  readonly rejections: readonly string[];
  readonly not_yet?: readonly string[];
  readonly reason: string;
}

interface Index {
  readonly screenshots: readonly Screenshot[];
  readonly rejections: readonly Rejection[];
  readonly records: readonly PageRecord[];
}

const index = JSON.parse(readRepoFile(`${FOLDER}/index.json`)) as Index;

interface Row {
  readonly id: string;
  readonly source: string;
}

/** The register's rows that name a screenshot as their source: id to the image's file stem. */
function requirementsFromScreenshots(): Map<string, string> {
  const rows = (JSON.parse(readRepoFile("docs/requirements/register.json")) as { requirements: Row[] })
    .requirements;
  const found = new Map<string, string>();
  for (const row of rows) {
    const named = /screenshot (image-\d+)\./.exec(row.source);
    if (named !== null) {
      found.set(row.id, named[1] as string);
    }
  }
  return found;
}

/** The agent page's views and sections, as the page file spells them. */
function agentSections(): Set<string> {
  const page = readConsoleFile("src/pages/agents/AgentDetailPage.tsx");
  const views = /export const VIEWS = \[([^\]]*)\]/.exec(page)?.[1] ?? "";
  const found = new Set([...views.matchAll(/"(\w+)"/g)].map((one) => one[1] as string));
  for (const one of page.matchAll(/export const \w+_TAB = "(\w+)"/g)) {
    found.add(one[1] as string);
  }
  const automations = /export const AUTOMATIONS_TAB = "(\w+)"/.exec(
    readConsoleFile("src/pages/automationGalleryQuery.ts"),
  );
  found.add(automations?.[1] ?? "");
  found.delete("");
  return found;
}

const AGENT_TABS = "/agents/:agentId/:tab";

describe("the screenshots are listed, and what is held is on disk", () => {
  test("every image the register names as a source is in the index, and none is listed twice", () => {
    // What breaks if this is deleted: a requirement traced to a screenshot the docs never list, so
    // the screenshot can be lost without anything noticing it had requirements behind it.
    const named = new Set(requirementsFromScreenshots().values());
    const listed = index.screenshots.map((one) => one.id);
    expect(named.size, "the register names screenshots").toBeGreaterThan(0);
    expect(new Set(listed).size).toBe(listed.length);
    expect([...named].filter((one) => !listed.includes(one))).toEqual([]);
    expect(index.screenshots.filter((one) => one.named_by_register).map((one) => one.id).sort()).toEqual(
      [...named].sort(),
    );
  });

  test("an image the index says is held is a file in the folder, and one that is not says why", () => {
    // What breaks if this is deleted: a held image that is not there, or an image missing with no
    // word about it, which reads as covered. This holds what is true today (nothing is held, each
    // says why) and the day an image is copied in, that it was copied under the name recorded.
    for (const shot of index.screenshots) {
      if (shot.file === null) {
        expect(shot.why_not_held ?? "", `${shot.id} says why it is not held`).toMatch(/\S{4,}/);
      } else {
        expect(existsSync(join(REPO_ROOT, FOLDER, shot.file)), `${shot.id} is held at ${shot.file}`).toBe(true);
      }
    }
  });

  test("an image covering no page says which page it is waiting for, and one covering a page has no such note", () => {
    // What breaks if this is deleted: an image with an empty page list and no reason, which is a
    // screenshot nothing is built from and nothing says so.
    for (const shot of index.screenshots) {
      if (shot.pages.length === 0) {
        expect(shot.no_page_because ?? "", `${shot.id} says why no page`).toMatch(/\S{4,}/);
      } else {
        expect(shot.no_page_because, `${shot.id} covers a page and needs no excuse`).toBeUndefined();
      }
    }
  });
});

describe("every covered page has a record, and every record is a page", () => {
  const routes = [...drawnScreens().keys()];

  test("every address a screenshot covers, and every address a record is for, is in the route table", () => {
    // What breaks if this is deleted: a record for a page that was renamed or never built, which
    // says a screen was adapted when there is no screen.
    const covered = new Set(index.screenshots.flatMap((one) => one.pages));
    const recorded = new Set(index.records.map((one) => one.address));
    expect(routes.length, "the route table was read").toBeGreaterThan(40);
    expect([...covered, ...recorded].filter((one) => !routes.includes(one))).toEqual([]);
  });

  test("every page a screenshot covers has a record, and every record sits on a screenshot's page", () => {
    // What breaks if this is deleted: a covered page nobody recorded what was adapted or refused
    // on (the leaf), or a record for a page no screenshot covers.
    const covered = new Set(index.screenshots.flatMap((one) => one.pages));
    const recorded = new Set(index.records.map((one) => one.address));
    expect([...covered].filter((one) => !recorded.has(one))).toEqual([]);
    expect([...recorded].filter((one) => !covered.has(one))).toEqual([]);
  });

  test("each record names screenshots that cover its page, and says what was adapted, what was refused and why", () => {
    // What breaks if this is deleted: a record that lists nothing refused, which is the half of the
    // leaf that is easiest to leave out, or one that cites a screenshot that does not cover it.
    const ids = new Map(index.screenshots.map((one) => [one.id, one]));
    for (const one of index.records) {
      const where = `${one.address} ${one.section ?? ""}`.trim();
      expect(one.adapted.length, `${where}: what was adapted`).toBeGreaterThan(0);
      expect(one.refused.length, `${where}: what was refused`).toBeGreaterThan(0);
      expect(one.reason, `${where}: why`).toMatch(/\S{4,}/);
      expect(one.screenshots.length, `${where}: a screenshot`).toBeGreaterThan(0);
      for (const shot of one.screenshots) {
        expect(ids.get(shot)?.pages, `${where}: ${shot} covers it`).toContain(one.address);
      }
    }
  });

  test("a record is one page or one named section of the agent page, listed once", () => {
    // What breaks if this is deleted: two records for one section that disagree, or a section name
    // the agent page does not have, which is a record for a screen that is not there.
    const sections = agentSections();
    expect(sections.size).toBeGreaterThanOrEqual(7);
    const seen = new Set<string>();
    for (const one of index.records) {
      const key = `${one.address}#${one.section ?? ""}`;
      expect(seen.has(key), `${key} is recorded once`).toBe(false);
      seen.add(key);
      if (one.section === null) {
        expect(one.address.includes(":tab"), `${key}: a tab address names its tab`).toBe(false);
      } else {
        expect(sections.has(one.section), `${key}: the agent page has that section`).toBe(true);
      }
    }
  });

  test("every requirement a record answers comes from one of its own screenshots", () => {
    // What breaks if this is deleted: a record answering a requirement that was asked of another
    // screen, so the register and the record trace to different pictures.
    const fromScreens = requirementsFromScreenshots();
    for (const one of index.records) {
      for (const requirement of one.requirements) {
        const image = fromScreens.get(requirement);
        expect(image, `${requirement} is a requirement taken from a screenshot`).toBeDefined();
        expect(one.screenshots, `${requirement} in ${one.address}`).toContain(image);
      }
    }
  });

  test("the audit finds a covered page with no record when one is taken out", () => {
    // What breaks if this is deleted: the two tests above can be satisfied by a comparison that
    // always passes. This runs the same comparison over an index with the connectors record removed.
    const without = index.records.filter((one) => one.address !== "/connectors");
    const covered = new Set(index.screenshots.flatMap((one) => one.pages));
    const recorded = new Set(without.map((one) => one.address));
    expect([...covered].filter((one) => !recorded.has(one))).toEqual(["/connectors"]);
  });
});

// ------------------------------------------------------------------ the two kept rejections
const SWITCHES = new Set(["Switch", "Checkbox", "Toggle", "ToggleGroup", "RadioGroup", "Radio"]);

/** The function declaration with this name, which is thrown for when it is not there. */
function functionNamed(source: ts.SourceFile, name: string): ts.FunctionDeclaration {
  let found: ts.FunctionDeclaration | undefined;
  const walk = (node: ts.Node): void => {
    if (ts.isFunctionDeclaration(node) && node.name?.text === name) {
      found = node;
    }
    ts.forEachChild(node, walk);
  };
  walk(source);
  if (found === undefined) {
    throw new Error(`${source.fileName} declares no function ${name}, so a rule about it would be vacuous`);
  }
  return found;
}

interface Element {
  readonly tag: string;
  readonly attributes: ReadonlyMap<string, string>;
}

/** Every JSX element under a node, with its attributes' source text. */
function elementsIn(node: ts.Node, source: ts.SourceFile): Element[] {
  const found: Element[] = [];
  const walk = (one: ts.Node): void => {
    if (ts.isJsxOpeningElement(one) || ts.isJsxSelfClosingElement(one)) {
      const attributes = new Map<string, string>();
      for (const attribute of one.attributes.properties) {
        if (ts.isJsxAttribute(attribute)) {
          attributes.set(attribute.name.getText(source), attribute.initializer?.getText(source) ?? "");
        }
      }
      found.push({ tag: one.tagName.getText(source), attributes });
    }
    ts.forEachChild(one, walk);
  };
  walk(node);
  return found;
}

function controlsOf(element: Element): boolean {
  return (
    SWITCHES.has(element.tag) ||
    (element.tag === "input" && /checkbox|radio/.test(element.attributes.get("type") ?? ""))
  );
}

describe("no single on and off switch for learning", () => {
  test("the learning section of the Profile and of Memory draw four tiers and no switch", () => {
    // What breaks if this is deleted: a switch is added to the section that shows what may be
    // learnt, and the note beside it saying there deliberately is none stays, which no test of the
    // note would catch. The section is read as JSX, so the element is what is refused.
    const sections: readonly [string, string][] = [
      ["src/pages/agents/AgentProfile.tsx", "Learning"],
      ["src/pages/agents/AgentMemory.tsx", "Tiers"],
    ];
    for (const [file, name] of sections) {
      const source = parseConsoleSource(file);
      const section = functionNamed(source, name);
      const drawn = elementsIn(section, source);
      expect(drawn.filter(controlsOf).map((one) => one.tag), `${name} in ${file}`).toEqual([]);
      expect(drawn.map((one) => one.tag), `${name} draws the tiers as a list`).toContain("ol");
      const fours: number[] = [];
      const walk = (node: ts.Node): void => {
        if (ts.isArrayLiteralExpression(node)) {
          fours.push(node.elements.length);
        }
        ts.forEachChild(node, walk);
      };
      walk(section);
      expect(fours, `${name} holds an array of four tiers`).toContain(4);
    }
  });

  test("no switch, checkbox or toggle anywhere in the console is named for learning", () => {
    // What breaks if this is deleted: the one-switch design moves to a page the test above does not
    // read. Every control of that kind in the console's source is read, and one whose id, label or
    // name says learning, adapting or learnt is refused.
    const named = /learn|adaptive/i;
    const offending: string[] = [];
    let controls = 0;
    for (const file of consoleSourcePaths("src").filter((one) => one.endsWith(".tsx"))) {
      const source = parseConsoleSource(file);
      for (const element of elementsIn(source, source).filter(controlsOf)) {
        controls += 1;
        const written = [...element.attributes.entries()]
          .filter(([name]) => ["id", "name", "aria-label", "aria-labelledby", "label", "data-slot"].includes(name))
          .map(([, value]) => value)
          .join(" ");
        if (named.test(written)) {
          offending.push(`${file}: <${element.tag} ${written}>`);
        }
      }
    }
    expect(controls, "the console has switches and checkboxes, so this read some").toBeGreaterThan(5);
    expect(offending).toEqual([]);
  });

  test("the rule would find a learning switch if one were drawn", () => {
    // What breaks if this is deleted: the two tests above can pass because the reader cannot see a
    // switch at all. This reads a section written with one and requires it found.
    const written = ts.createSourceFile(
      "learning.tsx",
      `function Learning() { return <section><Switch id="agent-learning" /><ol>{[1,2,3,4].map((n) => <li key={n} />)}</ol></section>; }`,
      ts.ScriptTarget.ES2022,
      true,
      ts.ScriptKind.TSX,
    );
    const drawn = elementsIn(functionNamed(written, "Learning"), written);
    expect(drawn.filter(controlsOf).map((one) => one.tag)).toEqual(["Switch"]);
    expect(drawn.filter(controlsOf)[0]?.attributes.get("id")).toMatch(/learn/i);
  });

  test("both rejections are recorded on the pages that keep them, and those pages are real sections", () => {
    // What breaks if this is deleted: a rejection the record says is kept at a page that has no
    // record of keeping it, so the owner's refusal exists only in a sentence.
    const sections = agentSections();
    expect(index.rejections.map((one) => one.id).sort()).toEqual([
      "no-browser-operator-on-the-users-session",
      "no-single-learning-toggle",
    ]);
    for (const rejection of index.rejections) {
      expect(rejection.kept_at.length).toBeGreaterThan(0);
      for (const place of rejection.kept_at) {
        const record = index.records.find((one) => one.address === place.address && one.section === place.section);
        expect(record, `${rejection.id} at ${place.address} ${place.section}`).toBeDefined();
        expect(record?.rejections).toContain(rejection.id);
        expect(sections.has(place.section)).toBe(true);
      }
    }
  });
});

describe("no browser operator riding the person's own session", () => {
  test("no console address and no API address is for operating a computer or riding a session", () => {
    // What breaks if this is deleted: a route that hands a person's own signed-in browser to an
    // agent is added, and nothing in the page tests would see it because it is a route, not a card.
    const forbidden = /operator|computer[-_]?use|own[-_]session|desktop|remote[-_]?control|take[-_]?over/i;
    expect([...drawnScreens().keys()].filter((one) => forbidden.test(one))).toEqual([]);
    const paths = Object.keys((apiDocument() as { paths: Record<string, unknown> }).paths);
    expect(paths.length, "the API document was read").toBeGreaterThan(100);
    expect(paths.filter((one) => forbidden.test(one))).toEqual([]);
    expect("/agents/:agentId/computer-use").toMatch(forbidden);
  });

  test("the Profile offers no control for operating a computer, and its browser is the sealed one", () => {
    // What breaks if this is deleted: a switch drawn for computer use before the product can run an
    // isolated one, or the browsing card's words drifting from a sealed browser to the person's own.
    const source = parseConsoleSource("src/pages/agents/AgentProfile.tsx");
    const computer = functionNamed(source, "ComputerUse");
    const drawn = elementsIn(computer, source);
    expect(drawn.filter(controlsOf)).toEqual([]);
    expect(drawn.map((one) => one.tag).filter((tag) => tag === "Button" || tag === "button")).toEqual([]);
    expect(drawn.map((one) => one.tag)).toContain("Explanation");

    const browser = functionNamed(source, "BrowserUse");
    const card = elementsIn(browser, source).find((one) => one.tag === "SectionCard");
    const lede = card?.attributes.get("lede") ?? "";
    expect(lede).toMatch(/sealed browser/);
    expect(lede).toMatch(/thrown away/);
    expect(lede).not.toMatch(/your own|their own|signed.in|session/i);
  });

  test("the Profile record states both rejections it keeps", () => {
    // What breaks if this is deleted: the record for the page that keeps them says neither, so the
    // next reader of the page is not told these absences are deliberate.
    const profile = index.records.find((one) => one.address === AGENT_TABS && one.section === "profile");
    expect(profile?.rejections.sort()).toEqual([
      "no-browser-operator-on-the-users-session",
      "no-single-learning-toggle",
    ]);
    expect(profile?.refused.some((one) => /single on and off switch for learning/.test(one))).toBe(true);
    expect(profile?.refused.some((one) => /own session/.test(one))).toBe(true);
  });
});
