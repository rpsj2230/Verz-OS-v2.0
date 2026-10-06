/**
 * The navigation, which is the API's answer and never the token's.
 *
 * **This is the positive statement of the rule that the console does not decide what
 * exists.** The obvious alternative is to read the roles out of the token and show each
 * person only the sections they can use. That is one line, it works, and it puts a
 * permission model in the browser: the console would be deciding what exists, from a copy
 * of the rules nobody keeps in step, computed from a token this code has no business
 * reading.
 *
 * Since 2026-09-17 the shell asks `GET /api/v1/console/navigation` which console a reader is
 * given, so the menu is no longer identical for everybody: it is identical for everybody the API
 * gives the same answer, whatever their token says. Since 2026-09-28 the company console's menu is
 * in that answer too, in the nine module groups of the console plan, and a section somebody cannot
 * use answers with the API's own refusal, which is the same answer they would get for a section
 * that does not exist. The department console and the menu before an answer arrives are held in
 * `tests/department-console.test.tsx`.
 *
 * Task ids: M32.5.1.2, M27.10.1
 */

import { MemoryRouter } from "react-router-dom";
import { render, waitFor } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { fakeIdentityProvider, loadConsole, signIn, type LoadedConsole } from "./support/auth";
import { answerNavigation, COMPANY_CONSOLE } from "./support/navigation";
import { OWN_WORK_HEADING } from "../src/routes/registry";

/** A signed-in console whose stand-in API answers the navigation with `body`. */
async function consoleAnswering(
  body: unknown = COMPANY_CONSOLE,
  tokens?: Parameters<typeof signIn>[1],
): Promise<LoadedConsole> {
  const idp = fakeIdentityProvider({ api: (url) => answerNavigation(url, body) });
  const loaded = await loadConsole({ idp });
  await signIn(loaded, tokens);
  return loaded;
}

/** The navigation landmark's markup, from a shell rendered at one address, once it has answered. */
async function navigationAt(path: string): Promise<string> {
  const { Shell } = await import("../src/layout/Shell");
  const { container } = render(
    <MemoryRouter initialEntries={[path]}>
      <Shell />
    </MemoryRouter>,
  );
  const nav = container.querySelector("nav");
  if (!nav) {
    throw new Error("The shell rendered no navigation landmark, so there is nothing to compare.");
  }
  await waitFor(() => {
    if (nav.querySelector('[role="status"]')) {
      throw new Error("the menu has not been answered yet");
    }
  });
  return nav.outerHTML;
}

/** Where the navigation points, ignoring which entry is marked as current. */
function targets(navMarkup: string): { href: string; label: string }[] {
  const holder = document.createElement("div");
  holder.innerHTML = navMarkup;
  return [...holder.querySelectorAll("a")].map((link) => ({
    href: link.getAttribute("href") ?? "",
    label: link.textContent ?? "",
  }));
}

describe("the navigation", () => {
  test("the navigation is identical for every session the API gives the same answer", async () => {
    // What breaks if this is deleted: the rule that this console does not decide what
    // exists. A filter here would need a token to be read, would be a second permission
    // model computed in the one place an attacker can edit, and would leak by omission:
    // the shape of the menu would tell each person what they are not allowed to see. Two
    // sessions with different tokens and one answer must draw one menu, and that menu must be
    // the company console's whole, Platform included, so this is not passing because both
    // sessions were shown only their own work.
    const seen = new Set<string>();

    await consoleAnswering(COMPANY_CONSOLE, { accessToken: "TOKEN-FOR-ONE-PERSON", idToken: "ID-ONE" });
    seen.add(await navigationAt("/"));

    await consoleAnswering(COMPANY_CONSOLE, {
      accessToken: "A-DIFFERENT-TOKEN-ENTIRELY",
      idToken: "ID-TWO",
      expiresIn: 900,
    });
    seen.add(await navigationAt("/"));

    expect([...seen]).toHaveLength(1);
    expect(targets([...seen][0] ?? "").map((one) => one.href)).toContain("/updates");
  });

  test("the navigation lists the same sections on every page", async () => {
    // What breaks if this is deleted: a section that appears only once you are already in
    // it, which is the same disclosure by a slower route. Where the links point is
    // compared rather than the whole markup, because the current entry is legitimately
    // marked and that mark is the one thing that should differ.
    await consoleAnswering();
    const onOverview = targets(await navigationAt("/"));
    const onRecords = targets(await navigationAt("/records"));

    expect(onOverview.length).toBeGreaterThan(1);
    expect(onRecords).toEqual(onOverview);
  });

  test("the navigation is grouped under the design's headings, in the design's order", async () => {
    // What breaks if this is deleted: the menu goes back to one flat list in the order screens
    // happened to be built, which is what the owner opened on 2026-09-16 and what
    // `docs/admin-console.md` refuses: navigation grouped by what an administrator is trying to
    // do, not by which module serves it. `docs/screens.html` SCREEN 1 draws the reader's own work
    // and then the nine module groups of the console plan, in that order, one entry per module.
    // Each list is asserted to be named by its own heading, because a heading beside a list that
    // nothing ties to it reads as grouped and is announced as one long list.
    await consoleAnswering();
    const holder = document.createElement("div");
    holder.innerHTML = await navigationAt("/");

    const headings = [...holder.querySelectorAll("nav h2")].map((one) => one.textContent);
    expect(headings).toEqual([OWN_WORK_HEADING, ...COMPANY_CONSOLE.sections.map((one) => one.heading)]);
    expect(headings.slice(0, 4)).toEqual(["Use", "Home", "People and access", "Agents and AI"]);
    expect(headings.at(-1)).toBe("Platform");

    const under = (heading: string): string[] => {
      const title = [...holder.querySelectorAll("nav h2")].find((one) => one.textContent === heading);
      const list = holder.querySelector(`ul[aria-labelledby="${title?.id ?? "missing"}"]`);
      return [...(list?.querySelectorAll("a") ?? [])].map((link) => link.textContent ?? "");
    };
    // The Super Admin's view across the install sits beside the Dashboard (M33.1.1.1 to M33.1.1.3).
    expect(under("Home")).toEqual(["Dashboard", "Whole company"]);
    expect(under("Knowledge and data")).toContain("Connectors");
    expect(under("People and access")).toContain("Roles and permissions");
    expect(under("People and access")).not.toContain("Capabilities");
    expect(under("Agents and AI")).toContain("Models and routing");
    expect(under("Reports")).toContain("Usage and cost");
    expect(under("Platform")).toContain("Version and updates");

    // Every link sits in exactly one group, so grouping neither hid a section nor listed one twice.
    const grouped = headings.flatMap((heading) => under(heading ?? ""));
    const all = targets(holder.innerHTML).map((one) => one.label);
    expect([...grouped].sort()).toEqual([...all].sort());
  });

  test("a group holding the page is open and the others are folded, with every entry still in the markup", async () => {
    // What breaks if this is deleted: either the menu is forty rows long on every page, which is the
    // clutter the owner asked to be rid of, or a folded group drops its entries from the markup and
    // the menu says different things on different pages. The group that holds the page is open, the
    // others are folded behind a button that says whether it is open, and a folded group's list is
    // hidden rather than removed.
    await consoleAnswering();
    const holder = document.createElement("div");
    holder.innerHTML = await navigationAt("/capabilities");

    const toggle = (heading: string): Element | null =>
      [...holder.querySelectorAll("nav h2")].find((one) => one.textContent === heading)?.querySelector("button") ?? null;
    const list = (heading: string): Element | null =>
      holder.querySelector(`ul[aria-labelledby="${[...holder.querySelectorAll("nav h2")].find((one) => one.textContent === heading)?.id ?? "missing"}"]`);

    expect(toggle("People and access")?.getAttribute("aria-expanded")).toBe("true");
    expect(list("People and access")?.hasAttribute("hidden")).toBe(false);
    expect(toggle("Platform")?.getAttribute("aria-expanded")).toBe("false");
    expect(list("Platform")?.hasAttribute("hidden")).toBe(true);
    expect(list("Platform")?.querySelectorAll("a").length).toBeGreaterThan(0);
    expect(toggle("Platform")?.tagName).toBe("BUTTON");
  });

  test("a page that is one of a module's tabs marks the module's entry and draws the module's pages as tabs", async () => {
    // What breaks if this is deleted: a module of several pages is one entry, so Capabilities, a tab
    // of Roles and permissions, has no entry of its own; without this the entry goes unmarked on its
    // own tabs, or the tabs are not drawn and Capabilities cannot be reached from anywhere.
    await consoleAnswering();
    const { Shell } = await import("../src/layout/Shell");
    const { container } = render(
      <MemoryRouter initialEntries={["/capabilities"]}>
        <Shell />
      </MemoryRouter>,
    );
    await waitFor(() => {
      if (container.querySelector('nav [role="status"]')) {
        throw new Error("the menu has not been answered yet");
      }
    });

    const menu = container.querySelector('nav[aria-label="Sections"]');
    const marked = [...(menu?.querySelectorAll("a[aria-current]") ?? [])].map((one) => one.textContent);
    expect(marked).toEqual(["Roles and permissions"]);

    const tabs = container.querySelector('main nav[aria-label="Roles and permissions"]');
    expect([...(tabs?.querySelectorAll("a") ?? [])].map((one) => one.getAttribute("href"))).toEqual([
      "/roles",
      "/capabilities",
      "/scopes",
      "/packs",
    ]);
    expect(tabs?.querySelector('a[aria-current="page"]')?.textContent).toBe("Capabilities");
  });

  test("the current section is marked by more than a colour", async () => {
    // What breaks if this is deleted: the only signal of where you are becomes a colour,
    // which is invisible to a screen reader and to anyone who cannot distinguish the two
    // shades. This is the accessibility half of the same list.
    await consoleAnswering();
    const holder = document.createElement("div");
    holder.innerHTML = await navigationAt("/records");
    const current = [...holder.querySelectorAll("a")].filter(
      (link) => link.getAttribute("aria-current") === "page",
    );

    expect(current.map((link) => link.textContent)).toEqual(["Records"]);
  });

  test("a section stays current at an address inside it", async () => {
    // What breaks if this is deleted: `end` on the section links. With exact matching
    // everywhere, opening anything nested under a section unmarks that section, so the
    // person is somewhere the menu says they are not. The root entry is the one that needs
    // exact matching, because a prefix match on "/" would otherwise mark it everywhere. The
    // address below is a real one: the entity is a path segment on the records route, so
    // this is where a person spends most of their time rather than an invented depth.
    await consoleAnswering();
    const holder = document.createElement("div");
    holder.innerHTML = await navigationAt("/records/clients");
    const current = [...holder.querySelectorAll("a")].filter(
      (link) => link.getAttribute("aria-current") === "page",
    );

    expect(current.map((link) => link.textContent)).toEqual(["Records"]);
  });

  test("the header says nothing about who is signed in", async () => {
    // What breaks if this is deleted: a name in the corner. The only way to know who is
    // signed in without asking the API is to read the token, which is the one thing this
    // console must never do. When an endpoint exists that says who the caller is, that is
    // where a name comes from.
    const loaded: LoadedConsole = await loadConsole();
    await signIn(loaded, {
      accessToken: "PERSON-SENTINEL-ACCESS",
      idToken: "PERSON-SENTINEL-ID",
      refreshToken: "PERSON-SENTINEL-REFRESH",
    });

    const { Shell } = await import("../src/layout/Shell");
    const { container } = render(
      <MemoryRouter initialEntries={["/"]}>
        <Shell />
      </MemoryRouter>,
    );

    expect(container.textContent).not.toContain("PERSON-SENTINEL");
    expect(container.innerHTML).not.toContain("PERSON-SENTINEL");
  });

  test("the shell offers a way past the navigation from the keyboard", async () => {
    // What breaks if this is deleted: reaching the page content from the keyboard means
    // tabbing through every navigation item on every page. The skip link is first in the
    // DOM on purpose, and being first is the part that a later reordering breaks.
    await loadConsole();
    const { Shell } = await import("../src/layout/Shell");
    const { container } = render(
      <MemoryRouter initialEntries={["/"]}>
        <Shell />
      </MemoryRouter>,
    );

    const firstFocusable = container.querySelector("a, button, input");
    expect(firstFocusable?.getAttribute("href")).toBe("#main");
    expect(container.querySelector("#main")?.tagName).toBe("MAIN");
  });
});
