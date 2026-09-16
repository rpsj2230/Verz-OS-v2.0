/**
 * The frame every signed-in page renders inside: a header, a navigation list, and the
 * page itself.
 *
 * **The navigation is the same for everybody, and that is a decision rather than an
 * omission.** The obvious alternative is to read the roles out of the token and show each
 * person only the sections they can use. That is one line, it works, and it puts a
 * permission model in the browser: the console would then be deciding what exists, using a
 * copy of the rules that nobody keeps in step with the real ones, computed from a token
 * this code has no business reading. When the two disagree, the browser's copy is the one
 * an attacker edits and the one a support conversation trusts.
 *
 * So every section is listed, and a person who opens one they cannot use gets the API's
 * answer to that question, which is the same answer they would get for a section that does
 * not exist. Nothing is disclosed by the list itself: it names the console's own pages,
 * not the company's data, and it is identical in every deployment.
 *
 * When hiding a section is genuinely worth it, the way to do it is to ask the API which
 * surfaces are available and render what it says. That keeps the decision on the side that
 * owns it. What must never happen is a role check in this file, computed here from a
 * token; `scripts/check-boundaries.mjs` refuses the names such a check is usually given.
 *
 * **The API's half of that already exists and is not served.** `brain.console.screens.
 * navigation` takes an `EntitlementSet` and nothing else, returns the screens and no count of
 * what it withheld, and is reachable from no route: `brain.launch` reads it and no request
 * does. So the menu a browser can compute from grants today is none, and a section added here
 * is added to a list rather than to a registry. When that navigation is served, this constant
 * is what the route's answer replaces, and the argument above is why it is a replacement
 * rather than a filter applied here.
 *
 * The skip link is first in the DOM on purpose. Without one, reaching the page content
 * from the keyboard means tabbing through every navigation item on every page.
 *
 * **The suspense boundary is around the page and not around the frame.** A route whose code
 * arrives on demand has to suspend somewhere, and putting the boundary outside the header
 * would mean the navigation itself waited for a network response. A menu that appears late
 * is a menu whose contents could in principle depend on what came back, and this file's
 * whole claim is that they cannot: the list is a constant, it renders before anything is
 * fetched, and it is the same list whether the page inside it ever loads or not.
 */

import { Suspense } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { ThemeControl } from "../theme/ThemeControl";
import { signOut } from "../auth/session";
import { INSTALL_SECTIONS } from "../pages/installQuery";

/** One entry in the menu. */
interface NavSection {
  readonly to: string;
  readonly label: string;
}

/** A heading in the menu and the sections under it. */
interface NavGroup {
  readonly heading: string;
  readonly sections: readonly NavSection[];
}

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
 * **Two groups the design does not draw, and why they exist.** Use holds the screens a person
 * works in rather than administers (asking, deciding an approval, reading records), which the
 * design gives a member's own workspace and which an administrator also needs. Install holds the
 * screens about this server, which the owner's standard lists (version, backup, limits) and the
 * design predates. Both come after the design's three, so the design's reading order is the
 * menu's reading order.
 *
 * **No count badges.** The design draws a number beside several entries. A badge is a figure
 * from a request, this list is a constant that renders before anything is fetched, and a menu
 * whose contents depend on a response is the shape the note above says it may not have. Each
 * number is on its screen instead, beside the entries it counts.
 */
const GROUPS: readonly NavGroup[] = [
  {
    heading: "Operate",
    sections: [
      { to: "/", label: "Overview" },
      { to: "/runs", label: "Live runs" },
      { to: "/jobs", label: "Scheduled jobs" },
      { to: "/errors", label: "Errors" },
      { to: "/models", label: "Models and health" },
      { to: "/connectors", label: "Connectors" },
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
  {
    heading: "Use",
    sections: [
      { to: "/ask", label: "Ask" },
      { to: "/me", label: "My workspace" },
      { to: "/approvals", label: "Approvals" },
      { to: "/records", label: "Records" },
    ],
  },
  {
    heading: "Install",
    sections: INSTALL_SECTIONS,
  },
];

/** The id a group's heading carries, so its list can name it. */
function headingId(heading: string): string {
  return `nav-${heading.toLowerCase()}`;
}

export function Shell() {
  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>

      <header className="shell__header">
        <span className="shell__brand">Company Brain</span>
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

      <div className="shell__body">
        <nav className="shell__nav" aria-label="Sections">
          {GROUPS.map((group) => (
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
