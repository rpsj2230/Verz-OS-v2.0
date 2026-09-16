/**
 * The route table, and the two things that sit outside it.
 *
 * **Configuration is checked before anything renders.** A console pointed at no identity
 * provider cannot sign anybody in, and the useful thing to do about that is say so on the
 * screen, naming the variable, to the person who deployed it. The alternative is a
 * redirect to `undefined/.well-known/openid-configuration` and a browser error nobody can
 * act on.
 *
 * **The sign-in routes sit outside the guard.** `/auth/callback` is where a session comes
 * from, so guarding it would be a loop; `/signed-out` exists because there is no session,
 * so guarding it would sign the person back in and undo what they just did. Their paths
 * are registered in Keycloak and are not free choices; see `src/auth/constants.ts`.
 *
 * **Client-side routing needs the server to co-operate.** Every path here is served by the
 * same `index.html`, so whatever hosts the built files must return `index.html` for an
 * unknown path rather than a 404. Without that, a deep link fails and, worse, so does
 * `/auth/callback`, which means sign-in completes at the identity provider and then lands
 * on a page that does not exist. The README says this again where a deployer will see it.
 *
 * **The records route is loaded on demand, and this is the one place that decision is
 * expressed.** It is the only route that mounts the table library and the form library, and
 * those weigh 608 kB against an application of 267 kB. Loaded eagerly they are in the first
 * response for everybody, including a person who only ever opens the overview, and the
 * download happens before the sign-in redirect has even been decided. A static import here
 * is therefore the change that undoes the split: `tests/bundle-split.test.ts` walks the
 * static import graph from `main.tsx` and fails when either library is reachable without a
 * dynamic import. The measurement is in the README.
 *
 * Rejected: splitting every route. `Overview` and `NotFound` reach nothing the shell does
 * not already reach, so a chunk for either buys a round trip and saves no bytes. A split is
 * worth what it removes from the entry, and these remove nothing.
 */

import { lazy } from "react";
import {
  createBrowserRouter,
  Link,
  RouterProvider,
  type RouteObject,
} from "react-router-dom";
import { CALLBACK_PATH, SIGNED_OUT_PATH } from "./auth/constants";
import { RequireSession } from "./auth/RequireSession";
import { CallbackRoute, SignedOutRoute } from "./auth/routes";
import { configProblems } from "./config";
import { Shell } from "./layout/Shell";
import { Adoption } from "./pages/Adoption";
import { Agents } from "./pages/Agents";
import { AgentTemplates } from "./pages/AgentTemplates";
import { Ask } from "./pages/Ask";
import { Capabilities } from "./pages/Capabilities";
import { Capacity } from "./pages/Capacity";
import { Connectors } from "./pages/Connectors";
import { Roles } from "./pages/Roles";
import { Scopes } from "./pages/Scopes";
import { Skills } from "./pages/Skills";
import { Audit } from "./pages/Audit";
import { Sessions } from "./pages/Sessions";
import { SignInLinks } from "./pages/SignInLinks";
import { Knowledge } from "./pages/Knowledge";
import { Learning } from "./pages/Learning";
import { Memory } from "./pages/Memory";
import { StaffSources } from "./pages/StaffSources";
import { Install } from "./pages/Install";
import { Limits } from "./pages/Limits";
import { Recovery } from "./pages/Recovery";
import { Updates } from "./pages/Updates";
import { ServiceLevels } from "./pages/ServiceLevels";
import { Spend } from "./pages/Spend";
import { NotFound } from "./pages/NotFound";
import { FirstRun } from "./pages/FirstRun";
import { Overview } from "./pages/Overview";
import { FIRST_RUN_PATH } from "./setup/wizard";
import { Notice } from "./ui/Notice";

/**
 * The records screen, fetched when somebody asks for it.
 *
 * Written as a dynamic import with a named export rather than a default one, because every
 * module in this console exports by name and a single default export here would be the one
 * exception a reader has to notice. `Shell` supplies the boundary this suspends against, so
 * the frame and the navigation paint before the chunk arrives: a menu that waited for a
 * page's code would be a menu whose contents depended on a network request, which is the
 * shape the navigation is not allowed to have.
 */
const Records = lazy(async () => ({ default: (await import("./pages/Records")).Records }));

/**
 * The routing matrix, fetched when somebody asks for it, for the same reason and by the same
 * measurement.
 *
 * It mounts the same two libraries the records screen does, so an eager import here would
 * undo the split whatever `Records` did: the chunk would simply arrive through this module
 * instead. `tests/bundle-split.test.ts` walks the static graph from `main.tsx` and does not
 * care which route reached the library.
 */
const Matrix = lazy(async () => ({ default: (await import("./pages/Matrix")).Matrix }));

/**
 * The classification screen, fetched when somebody asks for it, and split for the same
 * measurement again.
 *
 * It mounts the same two libraries, so an eager import here would undo the split whatever
 * the other two routes did: the chunk would simply arrive through this module instead.
 * `tests/bundle-split.test.ts` walks the static graph from `main.tsx` and does not care
 * which route reached the library.
 */
const Classification = lazy(async () => ({
  default: (await import("./pages/Classification")).Classification,
}));

/**
 * One agent's workspace, fetched when somebody opens an agent.
 *
 * Split for a smaller reason than the three above, and the reason is written in the stylesheet
 * rather than here. It mounts neither heavy library, so an eager import would not triple the
 * entry; what it would do is put the workspace's three components and `agent-workspace.css` in
 * the first response for everybody, and that sheet is imported by the components precisely so
 * that somebody who never opens an agent does not download it. `tests/agent-page.test.tsx`
 * walks the static graph from `main.tsx` and fails when either is reachable from it.
 */
const Agent = lazy(async () => ({ default: (await import("./pages/Agent")).Agent }));

/**
 * The approvals page, fetched when somebody opens it, for the workspace's reason: it imports
 * `approvals.css`, and a person who never opens approvals should not download it.
 */
const Approvals = lazy(async () => ({
  default: (await import("./pages/Approvals")).Approvals,
}));

/**
 * The people and grants page, fetched when somebody asks for it.
 *
 * It mounts the form library to write a grant, so an eager import here would put `@rjsf/core`
 * and the ajv validator back in the entry chunk for everybody, which is the measurement the
 * records and matrix routes are split for. `tests/bundle-split.test.ts` walks the static graph
 * from `main.tsx` and does not care which route reached the library.
 *
 * The other three Govern pages are imported statically below. None of them mounts a heavy
 * library or a stylesheet of its own, so a chunk for any of them would buy a round trip and
 * save no bytes, which is this file's rule for `Overview` and `Agents`.
 */
const People = lazy(async () => ({ default: (await import("./pages/People")).People }));

/**
 * Shown when a page throws while rendering.
 *
 * It deliberately does not print the error. A rendering failure is a bug in this console,
 * and the details belong in the browser's own console where a developer will look, not on
 * a page in front of somebody who cannot act on them and might screenshot them into a
 * chat. The reference a person needs for a support conversation is the trace id on a
 * failed request, which is a different thing and is shown where it exists.
 */
function RouteError() {
  return (
    <div className="centred-panel">
      <Notice title="Something went wrong on this page">
        <p>Reloading may help. If it keeps happening, this is a bug in the console.</p>
        <p>
          <Link to="/">Back to the overview</Link>
        </p>
      </Notice>
    </div>
  );
}

function ConfigurationProblems() {
  return (
    <div className="centred-panel">
      <Notice title="This console is not configured">
        <ul>
          {configProblems.map((problem) => (
            <li key={problem}>{problem}</li>
          ))}
        </ul>
        <p className="note">
          These are build-time settings. See <code>console/.env.example</code>.
        </p>
      </Notice>
    </div>
  );
}

/**
 * The routes themselves, separated from the router that mounts them.
 *
 * The table is data and the browser router is one binding of it. Exporting the data means
 * a test can mount the same table on a memory router and ask what a given address renders,
 * which is the only way to check that a deep link resolves and that an unknown one reaches
 * the console's own not-found page. A test that declared its own copy of this table would
 * be testing the copy.
 */
export const routes: RouteObject[] = [
  { path: CALLBACK_PATH, element: <CallbackRoute />, errorElement: <RouteError /> },
  { path: SIGNED_OUT_PATH, element: <SignedOutRoute />, errorElement: <RouteError /> },
  // First run, outside the guard for the callback's reason and one of its own: the guard would
  // sign the installer in and then load the overview, whose `/me` refuses a sign-in bound to
  // nobody, which on a fresh install is every sign-in. The page signs in itself, first. See
  // `pages/FirstRun.tsx`.
  { path: FIRST_RUN_PATH, element: <FirstRun />, errorElement: <RouteError /> },
  {
    path: "/",
    element: (
      <RequireSession>
        <Shell />
      </RequireSession>
    ),
    errorElement: <RouteError />,
    children: [
      { index: true, element: <Overview /> },
      // One path and no parameter, which is the whole of what this route has to get right. A
      // question is not a segment and not a query: it is the most sensitive value in the
      // request and it travels in a POST body, so there is no address here that could carry
      // one and no history entry that could keep one. Eager rather than split, because the
      // page mounts neither heavy library and imports no stylesheet of its own.
      { path: "ask", element: <Ask /> },
      // Two paths and one component. The entity is a path segment rather than a query
      // parameter because it is what the screen is about, and the same screen with none
      // named is where somebody arrives from the menu: it has the form and no grid, because
      // there is no question to ask yet.
      { path: "records", element: <Records /> },
      { path: "records/:entity", element: <Records /> },
      // Two paths and one component again. The rung being edited is a path segment because
      // it is what the screen is about, and the same screen with none named is the matrix on
      // its own: it has the grid and no form, because no rung has been opened.
      { path: "routing", element: <Matrix /> },
      // Connectors, which `docs/screens.html` SCREEN 9 puts in Operate beside the overview,
      // live runs and models. One path and no parameter: a source has no sub-object here, and
      // the path is the screen's key in `brain.console.screens`. Eager rather than split, for
      // the install screens' reason: it mounts neither heavy library and no stylesheet.
      { path: "connectors", element: <Connectors /> },
      { path: "routing/:rungId", element: <Matrix /> },
      // Three paths and one component. The document is a path segment because it is what
      // the screen is about, the column is one because it is which rule is being argued
      // about, and the bare path is where somebody arrives from the menu: it has the form
      // and no grid, because no document has been named. There is no route that lists the
      // classified documents, so naming one is how a person gets anywhere at all.
      { path: "classification", element: <Classification /> },
      { path: "classification/:entity", element: <Classification /> },
      { path: "classification/:entity/:column", element: <Classification /> },
      // The roster, which is where the workspace's way back lands. A different component
      // from the workspace rather than a third path on it, because it is a listing and the
      // workspace is one agent, and the rules for the two differ: see `pages/agentsQuery.ts`.
      { path: "agents", element: <Agents /> },
      // The catalogue, at an address of its own rather than under `agents/`, because an agent
      // slug is a path segment there and a template is not an agent: `agents/templates` would
      // be the workspace of an agent called templates on the day somebody names one that.
      { path: "agent-templates", element: <AgentTemplates /> },
      // Two paths and one component, at the address `brain.console.workspace.deep_link`
      // spells: an agent, and one tab of it. The bare agent opens the first tab its strip
      // holds, and so does a tab the strip does not hold, because `resolve` gives those one
      // answer.
      { path: "agents/:agentId", element: <Agent /> },
      { path: "agents/:agentId/:tab", element: <Agent /> },
      // The queue, and one approval on its own, which is where a link from a chat lands.
      { path: "approvals", element: <Approvals /> },
      { path: "approvals/:suspensionId", element: <Approvals /> },
      // The five install screens. One path each and no parameter on any of them, because none
      // of them has a sub-object to open: `brain.install_routes` gives the same argument for
      // its own addresses. Each path is the screen's key in `brain.console.screens`, which is
      // what `brain.ops.console_screens.routed_screen_keys` matches the registry against, so a
      // prettier address would take these off that list while leaving them reachable. Eager
      // rather than split: each mounts neither heavy library and imports no stylesheet of its
      // own, so a chunk for any of them would buy a round trip and save no bytes.
      { path: "install", element: <Install /> },
      { path: "updates", element: <Updates /> },
      { path: "recovery", element: <Recovery /> },
      { path: "limits", element: <Limits /> },
      { path: "connections", element: <Capacity /> },
      // The three Report screens. One path each and no parameter on any of them: each is a
      // reading of a window, the window is the request rather than the address, and there is
      // nothing on these pages a person could open. Eager rather than split, because none of
      // the three mounts a heavy library or a stylesheet of its own.
      { path: "service-levels", element: <ServiceLevels /> },
      { path: "spend", element: <Spend /> },
      { path: "adoption", element: <Adoption /> },
      // The four Govern screens. Two paths and one component for People, at the address one
      // subject's page has: the bare path is where somebody arrives from the menu and the
      // segment is the subject key, resolved against the page rather than against a route of
      // its own. See `pages/People.tsx`. The other three are one path each, because there is
      // nothing on them a person opens: a role, a capability and a scope are each shown whole.
      { path: "people", element: <People /> },
      { path: "people/:subject", element: <People /> },
      // Staff sources, at the screen's own key so `brain.ops.console_screens.routed_screen_keys`
      // matches this address against the registry. One path and no parameter: a source is shown
      // whole, and the trial is a request this page makes rather than a thing somebody opens.
      { path: "staff_sources", element: <StaffSources /> },
      // Sessions and sign-in links, beside People in Govern, which is where `docs/screens.html`
      // SCREEN 10 puts what happens to a person's sign-ins. One path each and no parameter: a
      // session and a link are each ended or unlinked from the listing rather than opened. The
      // sessions path is the screen's key in `brain.console.screens`, so
      // `brain.ops.console_screens.routed_screen_keys` matches it; sign-in links have no registry
      // key, and the page cites `brain.console.sign_in_links` instead.
      { path: "sessions", element: <Sessions /> },
      { path: "sign-in-links", element: <SignInLinks /> },
      // Audit, the last item of Govern in `docs/screens.html`. One path, with its filters and an
      // open subject's history as query parameters of the address rather than path segments, so
      // a colleague can be sent the view and the back button undoes a filter. The path is the
      // screen's key in `brain.console.screens`.
      { path: "audit", element: <Audit /> },
      { path: "roles", element: <Roles /> },
      // Skills, SCREEN 6 of `docs/screens.html`. Two paths and one component, at the address
      // one skill's page has: the bare path is where somebody arrives from the menu and the
      // segment is the skill's name, resolved against the page rather than against a route of
      // its own. See `pages/Skills.tsx`. Eager rather than split, for `Roles`' reason.
      { path: "skills", element: <Skills /> },
      { path: "skills/:name", element: <Skills /> },
      // Knowledge, SCREEN 7 of `docs/screens.html`, at the screen's own key in
      // `brain.console.screens` so `brain.ops.console_screens.routed_screen_keys` matches this
      // address. One path: an item has no page of its own, because this screen says an item
      // exists and how widely it reaches and nothing more. Eager, for `Roles`' reason.
      { path: "library", element: <Knowledge /> },
      // Learning, SCREEN 8. One path: the review is one page and a learning has no address.
      { path: "learning", element: <Learning /> },
      // Memory, read one person at a time. The bare path asks for a reference and the segment is
      // that person's memory, resolved by the API and never listed. A Govern screen rather than a
      // tab inside an agent, although SCREEN 13 draws it there: see `pages/Memory.tsx`.
      { path: "memory", element: <Memory /> },
      { path: "memory/:subject", element: <Memory /> },
      { path: "capabilities", element: <Capabilities /> },
      { path: "scopes", element: <Scopes /> },
      { path: "*", element: <NotFound /> },
    ],
  },
];

const router = createBrowserRouter(routes);

export function App() {
  if (configProblems.length > 0) {
    return <ConfigurationProblems />;
  }
  return <RouterProvider router={router} />;
}
