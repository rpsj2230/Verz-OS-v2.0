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

/** Every section, for everyone. See the note above before adding a condition to this. */
const SECTIONS: readonly { to: string; label: string }[] = [
  { to: "/", label: "Overview" },
  { to: "/ask", label: "Ask" },
  { to: "/records", label: "Records" },
  { to: "/routing", label: "Routing" },
  // Connectors sits in Operate, which is where `docs/screens.html` SCREEN 9 puts it: beside
  // the overview, live runs and models, and above the Govern group. Under the design's own
  // label rather than the registry's title, because `brain.ops.console_design.navigation_gaps`
  // compares this list against the design on the label. Written out rather than spread from
  // `pages/connectorsQuery.ts`, because that sweep reads the rows in this file.
  { to: "/connectors", label: "Connectors" },
  { to: "/classification", label: "Classification" },
  { to: "/approvals", label: "Approvals" },
  { to: "/service-levels", label: "Service levels" },
  { to: "/spend", label: "Spend" },
  { to: "/adoption", label: "Adoption" },
  // The govern group, in the order `brain.console.screens` registers it and under the titles
  // that registry gives it. Flat, for the reason the install group below is flat.
  { to: "/people", label: "People and grants" },
  { to: "/staff_sources", label: "Staff sources" },
  { to: "/roles", label: "Roles" },
  { to: "/capabilities", label: "Capabilities" },
  { to: "/scopes", label: "Scopes and departments" },
  // Agents, in Govern and under the design's own label, which is what
  // `brain.ops.console_design.navigation_gaps` compares this list against: SCREEN 4 calls it
  // "Agents & leashes" and sits it beside People and Scopes. The design draws a count badge
  // beside it and there is none here, for the reason given below about the skills badge.
  { to: "/agents", label: "Agents and leashes" },
  // Skills, in Govern and under the design's own label, which SCREEN 6 spells "Skills &
  // templates". The design draws a badge beside it carrying the number awaiting review and
  // there is none here: a badge is a figure from a request, this list is a constant that
  // renders before anything is fetched, and a menu whose contents depend on a response is the
  // shape the note above says the navigation is not allowed to have. The same number is on the
  // screen itself, where it is the count of the entries listed directly beneath it.
  { to: "/skills", label: "Skills and templates" },
  // The catalogue, flat and immediately under the section it belongs to. `docs/screens.html`
  // SCREEN 5 addresses it as "Skills & templates › Templates", which is a child of the row
  // above; this list has no nesting, and inventing some for one page would make the shape of
  // the menu a claim decided here, which is the argument the install group already makes
  // about its own five entries. A section rather than a link from the roster alone, because
  // `tests/phone-width.test.tsx` holds every page under the shell to being reachable from the
  // menu: a page a person can only find by knowing where it is linked from is a page nobody
  // finds.
  { to: "/agent-templates", label: "Agent templates" },
  // The install group, in the order `brain.console.screens` lists it and under the titles that
  // registry gives it. Five flat entries rather than one heading with five under it, because
  // this list has no nesting and inventing some for one group would make the shape of the menu
  // a claim about which screens belong together, decided here rather than by the registry that
  // already decides it. See `pages/installQuery.ts`.
  ...INSTALL_SECTIONS,
];

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
          <ul>
            {SECTIONS.map((section) => (
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
