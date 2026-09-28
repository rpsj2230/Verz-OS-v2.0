/**
 * The frame every signed-in page renders inside: the sidebar, a header, and the page itself.
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
 * `brain.console.department_console.console_for`: the company console, with its whole menu, for a
 * reader who holds some screen across the whole install, and a department's console, with
 * `docs/screens.html` SCREEN 2's menu narrowed to what they hold, for everybody else.
 *
 * **Neither menu is written here, since 2026-09-28.** The company console's menu was a constant in
 * this file, fifty-six entries in five groups, and every pull request that added a page edited it;
 * on that day two of them jammed on the same lines. Both menus are Python declarations now, in the
 * nine module groups of `docs/admin-console-architecture.md` Part 2.2, served by the API and
 * measured against the design by `brain.ops.console_design`. The one group the browser holds is the
 * reader's own work, which each page that belongs in it declares in its own route file
 * (`routes/registry.ts`). Adding a page edits neither this file nor `App.tsx`.
 *
 * **Until the answer arrives, and if it fails, the menu is the reader's own work and nothing
 * else.** Use is on every console, so it is drawn at once; the rest waits. Drawing the company
 * console while waiting would offer a department admin every screen about this server for as
 * long as the request took, and for good if it failed. See
 * `navigationQuery.A_MENU_NOBODY_ANSWERED_OFFERS_ONLY_YOUR_OWN_WORK`.
 *
 * **On a phone the menu is behind a visible Menu button, the first control after the skip link.**
 * Until 2026-09-28 the menu was a strip of every link above the page; with forty entries in nine
 * groups a strip stops being usable, so below 768 pixels the sidebar is a drawer
 * (`components/ui/sidebar.tsx`) that the Menu button opens, that holds every entry, and that gives
 * focus back to the button when it closes. On a wider screen the sidebar sits beside the page and
 * the same button collapses it.
 *
 * The skip link is first in the DOM on purpose. Without one, reaching the page content from the
 * keyboard means tabbing through every navigation item on every page.
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
 *
 * **The frame is the component layer and the page is not yet.** The sidebar is built from
 * `components/ui/sidebar.tsx` with Tailwind's utilities; the column holding the header and the page
 * carries `data-legacy`, so the pages that exist keep the stylesheets they were drawn with.
 *
 * Task ids: M27.10.1, M27.7.29
 */

import { Suspense } from "react";
import { Outlet } from "react-router-dom";
import { useResource } from "../api/useResource";
import { SidebarProvider } from "../components/ui/sidebar";
import { ThemeControl } from "../theme/ThemeControl";
import { signOut } from "../auth/session";
import { OWN_WORK } from "../routes/registry";
import { Chip } from "../ui/Chip";
import { ConsoleSidebar, MenuButton, type MenuState } from "./ConsoleSidebar";
import { ModuleTabs } from "./ModuleTabs";
import { NAVIGATION_API_PATH, menuFor, readNavigation } from "./navigationQuery";
import { SignInStrength } from "./SignInStrength";

export { MENU_LOADING, MENU_UNAVAILABLE } from "./ConsoleSidebar";

export function Shell() {
  const answer = useResource<unknown>(NAVIGATION_API_PATH);
  const given = answer.data === null ? null : readNavigation(answer.data);
  const groups = menuFor(given, OWN_WORK);
  const departments = given?.console === "department" ? given.departments : [];
  const state: MenuState = answer.busy ? "loading" : given === null ? "unavailable" : "answered";

  return (
    <SidebarProvider>
      <a className="skip-link" href="#main">
        Skip to content
      </a>

      <ConsoleSidebar groups={groups} state={state} console={given?.console ?? null} />

      <div className="flex min-w-0 flex-1 flex-col" data-legacy>
        <header className="shell__header">
          <div className="shell__header-start">
            <MenuButton />
            {departments.length > 0 ? <Chip label={departments.join(", ")} /> : null}
          </div>
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

        <main id="main" className="shell__main">
          <ModuleTabs groups={groups} />
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
    </SidebarProvider>
  );
}
