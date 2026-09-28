/**
 * The API's answer about which console a reader is given, as the tests that mount the shell send it.
 *
 * The shell asks `GET /api/v1/console/navigation` before it draws anything but the reader's own
 * work, so every test that looks at the menu has to answer that request. Written once, here, in
 * the shape `brain.navigation_routes.NavigationView` sends.
 *
 * **Both menus are read out of the Python declaration, never typed here.** `COMPANY_NAVIGATION`
 * and `DEPARTMENT_NAVIGATION` in `brain.console.department_console` are what the route serves, and
 * the group headings are `brain.console.screens.ModuleGroup`'s. A copy typed into this file would
 * be a third menu that drifts from both, and every shell test would pass against a menu the API
 * never sends. The department answer here is the declaration whole, which is what a reader holding
 * every screen in one department is sent.
 *
 * Task ids: M27.10.1
 */

import { readRepoFile } from "./repo";

/** Where the shell asks, as the stand-in API sees the path. */
export const NAVIGATION_ADDRESS = "/api/v1/console/navigation";

interface Tab {
  key: string;
  label: string;
  to: string;
}

interface Entry extends Tab {
  tabs: Tab[];
}

interface Section {
  group: string;
  heading: string;
  entries: Entry[];
}

/** Each `ModuleGroup` member's value and heading, read from `brain.console.screens`. */
function moduleGroups(): Map<string, { key: string; heading: string }> {
  const screens = readRepoFile("src/brain/console/screens.py");
  const enumBody = screens.slice(screens.indexOf("class ModuleGroup("), screens.indexOf("_MODULE_HEADINGS"));
  const found = new Map<string, { key: string; heading: string }>();
  for (const one of enumBody.matchAll(/^ {4}([A-Z]+) = "([a-z]+)"$/gm)) {
    found.set(one[1] as string, { key: one[2] as string, heading: "" });
  }
  for (const one of screens.matchAll(/ModuleGroup\.([A-Z]+): "([^"]+)"/g)) {
    const member = found.get(one[1] as string);
    if (member !== undefined) {
      member.heading = one[2] as string;
    }
  }
  return found;
}

/** A page's three arguments, in the order and spelling the declaration uses. */
const PAGE = /Page\(\s*label="([^"]+)",\s*to="([^"]+)"(?:,\s*key="([^"]*)")?,?\s*\)/y;
const ONE = /_one\(\s*"([^"]+)",\s*"([^"]+)"(?:,\s*"([^"]*)")?,?\s*\)/y;

/**
 * One declaration's sections, read token by token: a group opens a section, `Entry(label=...)`
 * opens an entry whose pages follow, and `_one(...)` is an entry of one page.
 */
function readSections(text: string): Section[] {
  const groups = moduleGroups();
  const sections: Section[] = [];
  let entry: Entry | null = null;
  const token = /group=ModuleGroup\.([A-Z]+)|department_section\(\s*ModuleGroup\.([A-Z]+)|Entry\(\s*label="([^"]+)"|Page\(|_one\(/g;
  for (let found = token.exec(text); found !== null; found = token.exec(text)) {
    const member = found[1] ?? found[2];
    const section = sections.at(-1);
    if (member !== undefined) {
      const group = groups.get(member);
      if (group === undefined) {
        throw new Error(`ModuleGroup.${member} is not in brain.console.screens.`);
      }
      sections.push({ group: group.key, heading: group.heading, entries: [] });
      entry = null;
    } else if (found[3] !== undefined && section !== undefined) {
      entry = { key: "", label: found[3], to: "", tabs: [] };
      section.entries.push(entry);
    } else if (found[0].startsWith("Page(") && entry !== null) {
      PAGE.lastIndex = found.index;
      const page = PAGE.exec(text);
      if (page === null) {
        throw new Error(`A Page( at ${String(found.index)} is not written as label, to and key.`);
      }
      entry.tabs.push({ key: page[3] ?? "", label: page[1] as string, to: page[2] as string });
    } else if (found[0].startsWith("_one(") && section !== undefined) {
      ONE.lastIndex = found.index;
      const one = ONE.exec(text);
      if (one === null) {
        throw new Error(`A _one( at ${String(found.index)} is not written as label, to and key.`);
      }
      entry = null;
      const label = one[1] as string;
      section.entries.push({ key: one[3] ?? "", label, to: one[2] as string, tabs: [{ key: one[3] ?? "", label, to: one[2] as string }] });
    }
  }
  // An entry opens its first page, and lists its pages as tabs only when it has several.
  for (const section of sections) {
    section.entries = section.entries.map((one) => {
      const first = one.tabs[0];
      if (first === undefined) {
        throw new Error(`${one.label} has no page.`);
      }
      return { key: first.key, label: one.label, to: first.to, tabs: one.tabs.length > 1 ? one.tabs : [] };
    });
  }
  return sections;
}

/** The declared menu named, as the route serves its sections. */
export function declaredNavigation(which: "company" | "department"): Section[] {
  const declared = readRepoFile("src/brain/console/department_console.py");
  const company = declared.indexOf("COMPANY_NAVIGATION: Final");
  const department = declared.indexOf("DEPARTMENT_NAVIGATION: Final");
  const end = declared.indexOf("@dataclass(frozen=True)\nclass ConsoleNavigation");
  if (company < 0 || department < company || end < department) {
    throw new Error("brain.console.department_console no longer declares its two menus in the order this reads.");
  }
  return readSections(which === "company" ? declared.slice(company, department) : declared.slice(department, end));
}

/** The company console's answer: its whole menu, the same for everybody given it. */
export const COMPANY_CONSOLE = Object.freeze({
  console: "company",
  departments: [] as string[],
  sections: declaredNavigation("company"),
});

/** SCREEN 2's menu for one department, as `brain.console.department_console` declares it. */
export function departmentConsole(department = "maintenance"): Record<string, unknown> {
  return {
    console: "department",
    departments: [department],
    sections: declaredNavigation("department"),
  };
}

/** Every address a menu answer offers: each entry's own, and each of its tabs'. */
export function addressesOf(body: { sections: unknown }): string[] {
  const sections = body.sections as Section[];
  return sections.flatMap((one) => one.entries.flatMap((entry) => [entry.to, ...entry.tabs.map((tab) => tab.to)]));
}

/** The navigation request answered with `body`, or null for any other request. */
export function answerNavigation(url: string, body: unknown = COMPANY_CONSOLE): Response | null {
  if (new URL(url, "https://console.test").pathname !== NAVIGATION_ADDRESS) {
    return null;
  }
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}
