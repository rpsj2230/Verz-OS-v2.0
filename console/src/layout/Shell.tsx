/**
 * The frame every signed-in page renders inside: a header, a navigation list, and the
 * page itself.
 *
 * **Which menu is drawn is the API's answer, and this file makes no permission decision.** The
 * obvious way to give a department admin a smaller menu is to read the roles out of the token and
 * show each person only the sections they can use. That is one line, it works, and it puts a
 * permission model in the browser: the console would then be deciding what exists, using a copy
 * of the rules that nobody keeps in step with the real ones, computed from a token this code has
 * no business reading. When the two disagree, the browser's copy is the one an attacker edits and
 * the one a support conversation trusts. `scripts/check-boundaries.mjs` refuses the names such a
 * check is usually given.
 *
 * So the shell asks. `GET /api/v1/console/navigation` is `brain.navigation_routes`, which serves
 * `brain.console.department_console.console_for`: the company console for a reader who holds some
 * screen across the whole install, and a department's console, with `docs/screens.html` SCREEN 2's
 * menu narrowed to what they hold, for everybody else. This note said until 2026-09-17 that the
 * navigation was the same for everybody because the API's half was not served; it is served now,
 * and the answer replaces the list rather than filtering it here.
 *
 * **The company console's menu is still a constant, and it is the same for everybody given it.**
 * `GROUPS` below is SCREEN 1's menu, `brain.ops.console_design` compares it with the design, and a
 * person who opens a section they cannot use gets the API's answer to that question, which is the
 * same answer a section that does not exist gets. The department console's menu is not written
 * here at all: it is narrowed per reader, so it arrives in the answer, and its labels live in
 * `brain.console.department_console.DEPARTMENT_NAVIGATION`.
 *
 * **Until the answer arrives, and if it fails, the menu is the reader's own work and nothing
 * else.** Use is on every console, so it is drawn at once; the rest waits. Drawing the company
 * console while waiting would offer a department admin every screen about this server for as
 * long as the request took, and for good if it failed. See
 * `navigationQuery.A_MENU_NOBODY_ANSWERED_OFFERS_ONLY_YOUR_OWN_WORK`.
 *
 * The skip link is first in the DOM on purpose. Without one, reaching the page content
 * from the keyboard means tabbing through every navigation item on every page.
 *
 * **The suspense boundary is around the page and not around the frame.** A route whose code
 * arrives on demand has to suspend somewhere, and putting the boundary outside the header would
 * make the frame wait for a chunk. The menu's own request is separate from the page's, so the
 * page inside the frame renders whether the menu has answered or not.
 *
 * **Under the header, a sign-in without a second factor is said once for every page.**
 * `layout/SignInStrength.tsx` asks `GET /me` and draws a banner only when the API says signing in
 * again with a second factor would give this person back something they hold. It sits outside
 * `main`, so it is part of the frame and not of any page's own states.
 */

import { Suspense } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useResource } from "../api/useResource";
import { ThemeControl } from "../theme/ThemeControl";
import { signOut } from "../auth/session";
import { INSTALL_SECTIONS } from "../pages/installQuery";
import { Chip } from "../ui/Chip";
import { NAVIGATION_API_PATH, menuFor, readNavigation, type NavGroup } from "./navigationQuery";
import { SignInStrength } from "./SignInStrength";

/** Said in the menu while the API has not answered which console this is. */
export const MENU_LOADING = "Loading the rest of the menu.";

/** Said in the menu when the API's answer could not be had or could not be read. */
export const MENU_UNAVAILABLE =
  "The rest of the menu could not be loaded, so only the screens about your own work are listed.";

/**
 * The screens a person works in rather than administers, on every console.
 *
 * Written once and used by both menus, and drawn before the API has answered, because asking,
 * deciding an approval and reading records are the reader's own work whichever console they are
 * given. The design gives these to a member's own workspace, and an administrator of a company or
 * of a department also needs them.
 */
export const USE: NavGroup = {
  heading: "Use",
  sections: [
    { to: "/ask", label: "Ask" },
    { to: "/me", label: "My workspace" },
    { to: "/approvals", label: "Approvals" },
    { to: "/records", label: "Records" },
  ],
};

/**
 * Every section, for everyone, grouped by what the person opening it is trying to do. See the
 * note above before adding a condition to this.
 *
 * **The groups and their order are the design's, not this file's.** `docs/screens.html` SCREEN 1
 * draws the company console's menu as Operate, Govern and Report, and names what sits in each.
 * Until 2026-09-16 this was one flat list of twenty-six entries in the order screens happened to
 * be built, and the owner's standard in `docs/admin-console.md` refuses exactly that: navigation
 * grouped by what an administrator is trying to do, "not by which module happens to serve it".
 * `brain.ops.console_design` compares these groups with the design's on every traceability run,
 * and reports an item the design names that is missing from its group or sits under another.
 *
 * **Labels are the design's where the design has one**, because that comparison is on the label:
 * "Scopes" rather than the screen's own heading "Scopes and departments", which the page keeps.
 * Rows are written out as `{ to, label }` literals rather than spread from a page module, because
 * the check reads the rows in this file. The install group is spread, and is the one group the
 * design does not draw, so there is nothing for it to be compared with.
 *
 * **Two groups the design does not draw, and why they exist.** Use, which is `USE` above. Install
 * holds the screens about this server, which the owner's standard lists (version, backup, limits)
 * and the design predates, and it is on this console only: a department's console offers no
 * screen whose subject is the installation. Both come after the design's three, so the design's
 * reading order is the menu's reading order.
 *
 * **No count badges.** The design draws a number beside several entries. A badge is a figure
 * from a second request per entry, and a number beside an entry is the one place a count of
 * something the reader may not open could reach the frame of every page. Each number is on its
 * screen instead, beside the entries it counts.
 */
const GROUPS: readonly NavGroup[] = [
  {
    heading: "Operate",
    sections: [
      { to: "/", label: "Overview" },
      { to: "/runs", label: "Live runs" },
      { to: "/jobs", label: "Scheduled jobs" },
      { to: "/errors", label: "Errors" },
      { to: "/logs", label: "Logs" },
      { to: "/models", label: "Models and health" },
      { to: "/connectors", label: "Connectors" },
      { to: "/webhooks", label: "Webhooks" },
      { to: "/notifications", label: "Notifications and email" },
      { to: "/routing", label: "Routing" },
    ],
  },
  {
    heading: "Govern",
    sections: [
      { to: "/people", label: "People and grants" },
      // SCREEN 10 draws the organisation as a card on People and grants, so its full-width screen
      // sits directly beneath that row.
      { to: "/departments", label: "Departments and teams" },
      { to: "/sessions", label: "Sessions" },
      { to: "/sign-in-links", label: "Sign-in links" },
      { to: "/access_review", label: "Access review" },
      { to: "/elevation", label: "Elevation requests" },
      { to: "/staff_sources", label: "Staff sources" },
      { to: "/roles", label: "Roles" },
      { to: "/capabilities", label: "Capabilities" },
      { to: "/scopes", label: "Scopes" },
      { to: "/agents", label: "Agents and leashes" },
      { to: "/skills", label: "Skills and templates" },
      // SCREEN 5 addresses the catalogue as "Skills & templates > Templates", a child of the
      // row above, so it sits directly beneath it.
      { to: "/agent-templates", label: "Agent templates" },
      // An agent's instructions are part of what an agent is, so they sit under the agent rows.
      { to: "/prompts", label: "Prompts" },
      { to: "/library", label: "Knowledge" },
      { to: "/learning", label: "Learning" },
      // Memory is not in SCREEN 1's menu: the design draws it inside one agent. It is registered
      // under Govern in `brain.console.screens` and is read per person, so it sits under the
      // design's own Govern entries rather than inventing a place. See `pages/Memory.tsx`.
      { to: "/memory", label: "Memory" },
      { to: "/artifacts", label: "Artifacts" },
      { to: "/retention", label: "Retention and erasure" },
      { to: "/audit", label: "Audit" },
      { to: "/import-export", label: "Import and export" },
      { to: "/subscribers", label: "Subscribers and notifications" },
      { to: "/classification", label: "Classification" },
    ],
  },
  {
    heading: "Report",
    sections: [
      { to: "/questions", label: "Questions and gaps" },
      { to: "/usage", label: "Usage and cost" },
      { to: "/quality", label: "Quality and canaries" },
      { to: "/service-levels", label: "Service levels" },
      { to: "/spend", label: "Spend" },
      { to: "/adoption", label: "Adoption" },
    ],
  },
  USE,
  {
    heading: "Install",
    sections: [...INSTALL_SECTIONS, { to: "/storage", label: "Storage" }],
  },
];

/** The id a group's heading carries, so its list can name it. */
function headingId(heading: string): string {
  return `nav-${heading.toLowerCase()}`;
}

export function Shell() {
  const answer = useResource<unknown>(NAVIGATION_API_PATH);
  const given = answer.data === null ? null : readNavigation(answer.data);
  const groups = menuFor(given, GROUPS, USE);
  const departments = given?.console === "department" ? given.departments : [];

  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>

      <header className="shell__header">
        <span className="shell__brand">
          Company Brain
          {departments.length > 0 ? (
            <>
              {" "}
              <Chip label={departments.join(", ")} />
            </>
          ) : null}
        </span>
        <div className="shell__header-actions">
          <ThemeControl />
          <button
            type="button"
            className="button"
            onClick={() => {
              void signOut();
            }}
          >
            Sign out
          </button>
        </div>
      </header>

      <SignInStrength />

      <div className="shell__body">
        <nav className="shell__nav" aria-label="Sections">
          {answer.busy ? (
            <p className="note" role="status">
              {MENU_LOADING}
            </p>
          ) : null}
          {!answer.busy && given === null ? <p className="note">{MENU_UNAVAILABLE}</p> : null}
          {groups.map((group) => (
            <div key={group.heading} className="shell__nav-group">
              <h2 id={headingId(group.heading)} className="shell__nav-heading">
                {group.heading}
              </h2>
              <ul aria-labelledby={headingId(group.heading)}>
                {group.sections.map((section) => (
                  <li key={section.to}>
                    <NavLink
                      to={section.to}
                      end={section.to === "/"}
                      className={({ isActive }) =>
                        isActive ? "shell__nav-link shell__nav-link--current" : "shell__nav-link"
                      }
                    >
                      {section.label}
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>

        <main id="main" className="shell__main">
          <Suspense
            fallback={
              <p className="note" role="status">
                Loading.
              </p>
            }
          >
            <Outlet />
          </Suspense>
        </main>
      </div>
    </div>
  );
}
