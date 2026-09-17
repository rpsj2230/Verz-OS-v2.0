# The console

The browser application. React and Vite, a typed client generated from the API's own
OpenAPI document, sign-in through Keycloak with authorisation code and PKCE, a light and
dark theme driven by tokens, and two screens: the overview, which renders
`GET /api/v1/me`, and the records grid, which renders `GET /api/v1/records/{entity}`.

Task ids: M32.5.1.1, M32.5.1.2, M32.5.1.3, M32.5.1.4, M32.5.2.1, M32.5.2.2, M32.5.2.3,
M32.5.2.4.

**This has been installed, generated, typechecked, built and tested. It has still never
been opened in a browser.** `npm install`, `npm run api:generate`, `npm run typecheck`,
`npm run check:boundaries`, `npm run build` and `npm test` all run clean, on Node 24. What
no check in this directory can reach is the rendering itself: no page has been painted, no
colour contrast measured, and no sign-in performed against a real Keycloak. The sections at
the end say exactly what that leaves unverified and what a reviewer still has to check.

A note on spelling, so the inconsistency does not read as carelessness: prose is British,
and protocol identifiers are spelled the way the protocol spells them. `authorization_code`
and `authorization_endpoint` are names in somebody else's specification and are not ours to
anglicise.

---

## The rule this console is built around

**The console is not a trust boundary.** Every permission decision belongs to the API.

A console that hides a button is a courtesy. A console that decides what may be fetched is
a second permission model, computed from a copy of the rules that nobody keeps in step with
the real ones, in the one place an attacker can edit. When the two disagree, the browser's
copy is the one that quietly wins in a support conversation and the one that quietly loses
in an incident.

Concretely, in this codebase:

- Nothing reads the contents of a token. Not for a name, not for a role, not for an expiry.
  The console holds an opaque string, sends it, and does what the API answers.
- The navigation is whichever console the API says this reader is given, and the browser
  never filters it. Filtering it by role would mean reading a token to decide what exists.
  `src/layout/Shell.tsx` argues this at length.
- `src/api/client.ts` has no allow-list of paths and no check of anything about the caller.
- A 404 is rendered with the API's own words and no interpretation. `handle_brain_error`
  maps DENIED and ABSENT to the same status with the same body, deliberately, and the way
  a console breaks that is never by writing "access denied": it is by being helpful.
  "You may not have permission to view this" turns one status code back into two answers.

The test of whether a client-side guard is doing security work: remove it and see whether
what the server returns changes. Remove `RequireSession` and requests go out with no bearer
token, the API refuses them, and the console shows refusals instead of a sign-in prompt.
Nothing is exposed. That is the correct amount of power for a browser to have.

`scripts/check-boundaries.mjs` turns the parts of this that are mechanical into a check.

---

## Running it

```
npm install
npm run api:generate      # needs uv and this repository; no server, no network
npm run dev
```

`npm run api:generate` runs two steps. The first is Python and exports the API's internal
OpenAPI document into `src/api/generated/`; the second turns it into TypeScript types. On
Windows, `npm run` executes scripts through `cmd.exe`, so the `&&` inside the script works
even though typing the same thing into PowerShell 5.1 would be a parser error. If you run
the halves by hand, run them as two commands.

Other scripts: `npm run build` (typecheck then bundle), `npm run typecheck`,
`npm run preview`, `npm run check:boundaries`, `npm test` (`npm run test:watch` while
working).

**`npm run build` fails until you have generated the schema at least once.** The error is
`Cannot find module './generated/schema'` from `src/api/schema.ts`, and that file's comment
says what to do about it. This is deliberate: see below.

---

## The typed client

### Generation is a development-time step, and cannot be anything else

`brain.app.create_app` sets `openapi_url=None` when the environment is production. There is
no schema route on a deployed instance, so a console that generated its client by fetching
one would work against staging and fail against production. That closed route is not an
oversight to work around: `brain.openapi.A_SCHEMA_IS_A_PERMISSION_MAP` explains that the
generated document is a complete inventory of paths, operations, models and field names,
and that serving it unauthenticated in a permission-aware system tells an attacker exactly
which door is worth their time. It was served that way once.

So `scripts/export-openapi.py` builds the document from the application object in this
repository, at the commit the console is being built against. `FastAPI.openapi()` does not
consult `openapi_url`, so this works even against a production-configured `Settings`, and
`create_app` builds routes only, so no socket is opened and no database is touched.

It exports the **internal** document, not the public projection. The public one is
deliberately just the already-unauthenticated routes with its component schemas pruned;
generating a client from it would produce a typed client for the health check, for ever,
and the omission would look like an empty API rather than the wrong audience.

### What there is to be typed against

Two operations, both under `/api/v1` and both behind the gate:

- `GET /api/v1/me`, which answers who the bearer token belongs to, at what assurance, on
  which channel ceiling, and the digest of the reach the request was computed at. It
  deliberately publishes no list of capabilities: see `brain.api_routes.CallerView`.
- `GET /api/v1/records/{entity}`, which answers a page of records already through the
  redactor. `RecordPage` is `Page` plus the payload's own fields, and it never carries a
  total, because a count behind a permission predicate tells the reader how many rows they
  were not shown.

**This section used to say there was nothing at all**, and that was true until the routes
landed on 2026-09-06. It is worth knowing what is still missing rather than assuming the
surface is finished: the deployed application has no signature verifier and no entitlement
store wired, so it refuses every credential, and it registers no row tool, so every entity
answers 404. Both refusals are the correct fail-closed behaviour and neither is useful yet.

### Types, not a generated runtime client

`openapi-typescript` emits types and no runtime code. The transport is `src/api/client.ts`,
about eighty lines, hand-written.

Rejected: a generated runtime client such as `openapi-typescript-codegen` or
`@hey-api/openapi-ts`. They bring their own base URL handling, their own retries and their
own opinion about what a status code means, and the opinion this system needs about 404 is
not one any generator holds. A generated client that treats 404 as "not found" and says so
in a default error message reintroduces the distinction the error taxonomy exists to remove.

The cost is that `request<T>()` takes the response type from the caller rather than
deriving it from the path, so a call site can name a path and a type that do not go
together. That is a real hole and it is the accepted trade. If the call sites outgrow it,
`openapi-fetch` types the pair together, uses the same generated types, and is a change to
one file rather than a rewrite.

### The generated output is not committed

`src/api/generated/` is ignored. A committed copy is correct until somebody changes a
response model without rerunning the generator, and from then on the console compiles
against an API that no longer exists while every check stays green. Regenerating needs no
server and no network, so keeping a stale copy for convenience buys nothing.

The consequence is that the build fails on a fresh checkout until the generator runs. That
is the loud failure and it was chosen over the quiet one.

**If CI is ever added for this directory, the Python export step must run before the
JavaScript build.** No CI has been added here; see the last section.

### The lock text is checked rather than trusted

`brain.core.redaction.LOCK_TEXT` is the only definition of what a withheld field says. The
console renders the lock itself, so it holds a copy in `src/ui/Lock.tsx`. There is no
shared artefact between Python and a browser bundle to carry the string, so the export
script compares the two on every run and refuses to generate anything if they have drifted.
It matches the whole export statement rather than searching for the word, because a check a
comment can satisfy is not a check.

---

## Sign-in

### It matches the realm exactly

Everything below is a fact about `ops/keycloak/realm-export.json`, which was imported and
read back against Keycloak 26.0 on 2026-09-06.

| The realm says | The console does |
| --- | --- |
| `clientId: brain-console` | Hard-coded in `src/auth/constants.ts`, not configurable |
| `publicClient: true` | No client secret anywhere; PKCE instead |
| `standardFlowEnabled: true` | `response_type=code`, and no other path exists |
| `implicitFlowEnabled: false` | No fragment handling, no fallback |
| `directAccessGrantsEnabled: false` | No sign-in form, no password field, ever |
| `pkce.code.challenge.method: S256` | S256, never `plain` |
| `redirectUris: .../auth/callback` | The router's `/auth/callback`, exact match |
| `post.logout.redirect.uris: .../signed-out` | The router's `/signed-out`, exact match |
| `revokeRefreshToken` with `refreshTokenMaxReuse: 0` | Refresh is single-flight |
| `accessTokenLifespan: 300` | Refreshed thirty seconds before expiry |

The client id is a constant rather than an environment variable, and that is the decision
in this file most likely to be undone by somebody being helpful. A client id is not a
deployment detail; it is a reference to a specific set of flow settings. Pointing this
console at a different client with a browser-side setting would silently move it to a
client that may have implicit enabled or a direct grant, and nothing in the browser can
tell the difference, because the browser is not the thing being protected.

What the console does take from the deployment is `INSTALL_OIDC_CLIENT_ID`, served in the
runtime document described below and defaulting to the client the shipped realm defines. That
is a different thing from a browser-side setting: it is the same register the realm import
reads, so the client the console asks for and the client the realm creates cannot disagree.

### Tokens live in memory

No token is written to any browser storage. The only things stored are the PKCE verifier
and the `state` value, in the tab's session store, because they must survive a full page
navigation, and they are deleted the moment they are read.

Rejected: a refresh token in the local store so that a reload is seamless. The realm gives
an SSO session ten hours, so that would be a ten-hour credential readable by any script on
the origin, and an XSS bug would stop being a session hijack and become a portable
credential.

Rejected: silent renewal in a hidden iframe. It is the older answer to the same problem and
browsers have blocked the third-party cookie it depends on.

The cost is a page load. Reloading the tab loses the token and the console bounces through
Keycloak again. That bounce is a top-level navigation carrying a first-party cookie, so it
is invisible while the SSO session is alive.

### Known gap: the cross-tab refresh race

Refresh is single-flight **within one tab**. Two tabs cannot await each other's promise, and
with `revokeRefreshToken` and `refreshTokenMaxReuse: 0` a refresh token presented after it
has been exchanged invalidates the chain. Two tabs whose tokens expire at about the same
time can therefore sign each other out.

This is not fixed and it is not hidden. The two ways to fix it:

1. Elect one refreshing tab with a `BroadcastChannel` and share the result. Perhaps thirty
   lines, and it narrows the window rather than closing it.
2. Move token custody to a backend-for-frontend, so the browser holds a cookie and never a
   refresh token. That closes it completely, and it changes `brain-console` from a public
   client to a confidential one, which is a realm change and somebody else's decision.

Neither was written speculatively. Option 2 in particular is a design decision about the
whole deployment, not a console detail.

### Known gap: nobody can sign in yet

`redirectUris` and `webOrigins` in the realm are `https://brain.example.invalid`, and the
file says the placeholders are deliberate, because a real hostname in a file that is copied
between environments becomes a stale redirect URI, which is an open redirect. That is the
right call and it means that **as committed, the realm cannot complete a sign-in from any
address, including localhost.** Before the console can be used at all, somebody with access
to Keycloak has to register the real origin and, for local work, the development origin.

That is why the dev server sets `strictPort`. A dev server that quietly moves from 5173 to
5174 produces a Keycloak error page that reads as a realm misconfiguration rather than as a
second copy of `npm run dev`.

### Something a reviewer should check in the realm, not here

The audience mapper that puts `brain-api` into the `aud` claim is declared inside the
`brain-api` client's own `protocolMappers`. A client's dedicated mappers apply to tokens
issued **for that client**, and `brain-api` has every flow disabled, so it never requests a
token. If that is right, tokens minted for `brain-console` will not carry `aud: brain-api`,
and `validate_token` will refuse every one of them for `WRONG_AUDIENCE` after a sign-in that
appeared to succeed.

I could not test this: it needs a running Keycloak and a running API, and I had neither.
The fix, if the reading is correct, is to move that mapper onto a client scope that
`brain-console` actually has, such as `brain-identity`, or onto `brain-console`'s own
mappers. **This is a note about the realm file, which I did not touch.**

The console does handle the symptom without hiding it: a 401 forgets the session, the guard
starts a fresh sign-in, and `MAX_SIGN_IN_ATTEMPTS` turns what would be an infinite redirect
loop into a readable message.

### Other decisions

**Hand-written, not `keycloak-js` or `oidc-client-ts`.** The dangerous part of an OIDC
client is ID token validation, and this console does not do any: it never reads the ID
token, so that whole class of bug is absent rather than handled. What remains is a redirect
with a PKCE challenge, a `state` comparison, a form post to the token endpoint and a
refresh. That is small enough to read in one sitting, and reading it is the only review
available for a dependency nobody here could install or audit either. `keycloak-js` in
particular defaults to iframe-based session checking that third-party cookie policy has
already broken.

This is a genuine trade and it can go the other way. If a reviewer would rather depend on
`oidc-client-ts`, the shape of `src/auth/session.ts` is close to its API and the swap is
contained.

**No `nonce`.** A nonce binds an ID token to a request, and it is worth what the check on
the way back is worth. This console never reads the ID token, so a nonce it never verifies
would be decoration that reads as protection. Anything that starts reading the ID token
must add both halves in the same change.

**The ID token is kept, and never parsed.** It is sent as `id_token_hint` at sign-out so
Keycloak can end the specific session without showing its confirmation page. When there is
none, `client_id` is sent instead, which Keycloak 26 also accepts as a condition for
honouring `post_logout_redirect_uri`.

**Sign-out is not local.** Forgetting the token here while the SSO session lives on is the
bug that looks like a feature: the next visit signs straight back in with no prompt, which
on a shared machine is not a sign-out at all.

---

## Routing and layout

`createBrowserRouter` with four top-level routes: the callback, the signed-out page, first run at
`/first-run`, and everything else behind `RequireSession` inside the shell. First run sits
outside the guard and signs in before it asks for the setup code, because the code is held in
memory only and the sign-in redirect would end that memory; `src/pages/FirstRun.tsx` argues it.
The dev server proxies `/setup` beside `/api`, because the wizard's two routes are served
outside the API prefix.

Inside the shell there are three: the overview at `/`, the records screen at `/records` and
`/records/{entity}`, and the console's own not-found page. The records screen is the only one
loaded on demand, because it is the only one that reaches the table and form libraries, and
what that saves is measured further down.

The two sign-in routes sit outside the guard, and both would be bugs inside it: the
callback is where a session comes from, so guarding it is a loop, and the signed-out page
exists because there is no session, so guarding it would sign the person back in and undo
what they just did.

**Whatever serves the built files must return `index.html` for an unknown path.** Every
route here is client-side. Without that fallback a deep link 404s, and so does
`/auth/callback`, which means sign-in completes at Keycloak and lands on a page that does
not exist.

**What serves them is the application itself**, at the root of the install's web address.
`src/brain/console_static.py` copies this directory's `dist/` into the application image and
serves it, with the fallback above, as the router's "nothing matched" handler. That module
carries the argument for one image rather than a static container beside it; the short version
is that one origin is the security design here rather than a convenience.

The console and the API therefore share an origin by construction: the realm registers
`https://<the web address>/auth/callback`, and the API serves `/api/v1` on that same host.
That is why the API base is a path and why `BRAIN_CORS_ORIGINS` can stay empty. The dev server
proxies `/api` to reproduce the same shape locally rather than making every laptop the only
place cross-origin behaviour is ever exercised. Splitting the two in a deployment means
changing `BRAIN_CORS_ORIGINS` on the API **and** `webOrigins` in the realm, neither of which
fails loudly on its own.

### Configuration arrives at runtime, not at build time

The issuer, the client id and the API base come from `/api/console.js`, a two-hundred-byte
document the application serves from `brain.install`, loaded by a blocking script in
`index.html` before the bundle. Nothing about a company is compiled into the JavaScript.

That is not tidiness. Vite inlines every `VITE_`-prefixed value as plain text, so a bundle
built with an issuer set is a bundle only the company owning that issuer can install, and this
product publishes one image for every client. `tests/config.test.tsx` refuses
`import.meta.env` anywhere under `src/`, and `tests/unit/test_console_served.py` refuses it
again from the suite that gates a deploy.

**The navigation is the API's answer, and never the token's.** Reading roles out of the token
and hiding sections would be one line and would put a permission model in the browser. Since
2026-09-17 the shell asks `GET /api/v1/console/navigation` which console a reader is given: the
company console, whose menu is the shell's own constant, or a department's, whose menu the API
sends narrowed to what the reader holds. Until the answer arrives, and if it fails, only the
reader's own work is listed. `tests/shell-navigation.test.tsx` mounts two sessions with
different tokens and one answer and asserts the markup is one string, and
`tests/department-console.test.tsx` holds the department's menu and the fallback.

---

## The screens

Two, and each shows what one route answered.

### Overview, at `/`

`GET /api/v1/me`, rendered as the caller's own facts and nothing else. No name is read out of
a token anywhere in this console, so this page is the only thing that knows who is signed in,
and it knows because it asked.

The fields it renders are checked against `brain.api_routes.CallerView` in the Python source
rather than against a list here, so a field added to that model fails a test instead of
arriving and being dropped. Four of the values are short closed-vocabulary words and render
through `Chip`, which has one appearance and no tone; nothing on the page turns a value into
a colour or into a sentence. `assurance` is the one somebody will want to explain, because it
is the fact a person can act on, and a sentence about signing in again with a second factor
would be a mapping from a value to a meaning written in a browser and out of step with the
API within a release.

A null `primary_department` contributes nothing at all: no row, no label, no dash. And there
is no lock on this page. `/me` sends no `locked`, so a lock here could only have been derived
from a null, which would be the console asserting a refusal nobody made in the one appearance
that is supposed to mean something exact.

The lock sample that used to be on this page is gone, as its own comment asked.

### Records, at `/records` and `/records/{entity}`

`GET /api/v1/records/{entity}`, through the grid, with the query asked through a generated
form. The address is the whole of the state, so a link can be shared and the colleague who
opens it gets the same question asked with their own grants.

- **The entity is typed, never chosen from a list.** There is no catalogue route, and a list
  in the console would publish the guess it was built from. The route answers an unclassified
  entity, an unregistered one, an ambiguous one and one whose rows this caller reaches no
  column of with one 404 and one sentence, precisely so an installation cannot be mapped by
  trying names, and this screen must not undo that by being helpful about spelling.
- **A withheld field still gets a column.** This is the half that fails silently:
  `brain.core.redaction` deletes a withheld key from the record and reports the field in
  `locked`, so a column list derived from the rows alone has nowhere to render the lock, and
  the one thing the screen exists to show disappears with nothing looking wrong. Columns are
  the keys that arrived plus the fields that were locked, sorted, so the order is a function
  of the names and not of the order a source returned its columns in.
- **Two callers sent different fields each get a packed grid.** No column is reserved for a
  field that did not arrive. The sharpest placeholder is not an element, it is a space, and
  `graph.ts` makes the same argument at length about rows on a canvas.
- **No column offers a filter**, because the route declares one query parameter and it is
  `limit`. A filter box would send `filter.owner`, FastAPI would drop it without a word, and
  the grid would show unfiltered rows to somebody reading them as the matching ones.
  `tests/records-page.test.tsx` reads the declared parameter names out of the API's own
  OpenAPI document and asserts the console sends nothing else.
- **The limit is the one control a person has**, and its bounds are the route's. They are
  checked against `brain.knowledge.rows.MAX_ROW_LIMIT` and against the generated document, so
  the form cannot offer a number the route refuses. A number outside them in a hand-edited
  address is treated as unstated rather than clamped: answering a different question from the
  one in the address is the failure this console is arranged against, in miniature.

**What a person cannot tell on this screen, and it is a gap rather than a rule.**
`RecordPage` carries `truncated`, which says there is more without saying how much more, and
`readPage` in `paging.ts` keeps two fields and drops it. So twenty-five rows of a larger set
look like the whole of it, and the pager's Next button is disabled because the route sends no
cursor. What a person has instead is the limit, which they can raise to five hundred.
Carrying `truncated` through the envelope, the hook and the grid is the fix; it is three
modules and their tests, and it is not a change to make in the commit that first mounts any
of them.

**Mounting a form forces the Content-Security-Policy question that the section on generated
forms parks.** `@rjsf/validator-ajv8` compiles each schema with `new Function`, so under the
policy proposed further down the validation throws and stops. Nothing is decided here either,
because the decision still belongs with whoever writes the policy, but it is no longer
hypothetical: there is a form on a page now, and the cheapest answer remains dropping
client-side validation, because the console is not a trust boundary and the API validates
what it is sent whatever this form believed.

---

## Theme

Tokens in `src/theme/tokens.css`; nothing else defines a colour. Three states, because a
person can choose light, choose dark, or choose nothing and follow the machine, and the
third is the default that two-position toggles have to lie about.

The stored choice is applied by a blocking script in `index.html` before the first paint,
which is the only way to avoid the flash of the wrong theme. That script cannot import a
module and still block paint, so the storage key is written twice;
`scripts/check-boundaries.mjs` asserts the two literals match.

Rejected: `light-dark()`, which would state each colour pair once instead of writing the
dark block twice. Its support is fine by now and its failure mode is not: a browser that
does not know the function treats the declaration as invalid, so the page falls back to no
colour rather than to a wrong colour and renders as unreadable text on an unpainted
background. I could not open this in a browser to find out.

**The lock is the part of the theme that is a rule rather than a preference.** A withheld
field renders through `src/ui/Lock.tsx`, which takes no props, into a single `.lock` class
with no modifiers. `brain.core.redaction.render_lock` takes no arguments for exactly this
reason: a lock that varied by field or by reason would make its own shape a side channel,
and two people comparing screens could read off which of them was refused for which reason.
`.lock--out-of-scope` would be that leak written in CSS. The lock's colours differ between
light and dark because the whole page does; they never differ between two fields on one
screen.

---

## The component layer

Four leaves, in `src/components/` and `src/ui/`. **Two of them are now mounted, on the pages
described in the next section, and two are not.** The grid, the generated form and the chip
are on `/records` and `/`, against the two routes the API actually serves. The canvas is not,
and the badge and status primitives are not, because nothing under `/api/v1` returns a graph
or a state word, and a screen filled with an invented run would make this console look
further along than it is. Everything unmounted is exercised by the suite and by nothing else,
which is stated again in "What is NOT done" so that nobody has to infer it.

The rule they all serve is the one the redaction module states twice, once for records and
once for fields, and the two halves are different rules that keep getting collapsed into one:

- **A whole record the caller may not see is dropped rather than emptied.** A husk announces
  that the record exists. So a step missing from a trace graph has no node, no outline and no
  gap, and a row missing from a page has nothing standing in for it.
- **A field inside a record whose existence was already disclosed renders a lock.** The API
  put the field in the schema and named it in `locked`; the console's job is to render the one
  appearance `render_lock` has, and never a second one that varies by reason.

### Grids

`components/DataTable.tsx`, `paging.ts` and `useServerPage.ts`. TanStack Table v9 with no
feature registered, so a client-side page or filter is a type error rather than a behaviour,
and a cursor-paged hook that drops the API's total on the way in. Their own files argue the
detail.

### Generated forms

`components/SchemaForm.tsx` and `formSchema.ts`, on `@rjsf/core` with the ajv8 validator.

The plain-HTML theme, not a design-system theme: `@rjsf/core` emits `.rjsf-field`,
`.control-label` and `.form-control`, which `styles/app.css` paints from tokens. Two of the
library's own templates are replaced, and both for the same reason: its submit button is
styled `btn btn-info` and its error list is a red panel, which is a severity variant of the
thing `ui/Notice.tsx` deliberately has exactly one of.

A generated form is the only screen here whose fields nobody chose, so three things are
properties of the assembly rather than habits:

- **A withheld field is replaced whole**, by a field that renders `ui/Lock.tsx` and a title.
  Not `ui:readonly` and not `ui:disabled`, which are the library's own one-word answers to
  this case and are both wrong: a read-only input renders the value, and a disabled one is a
  control in the tab order carrying that value in the DOM. Replacing the widget alone would
  leave the library's field template around it, and the description, help, error and
  described-by slots in that template are four places a reason could be shown beside a lock.
- **A withheld name is removed from `required` and stripped from the submitted data.** The
  second is a write rather than a read: a form library hands back a whole object, a locked
  property arrives in it empty, and an endpoint that writes what it is given would replace a
  figure this caller was never permitted to read with nothing.
- **A property whose format asks for a secret is dropped rather than rendered.**
  `scripts/check-boundaries.mjs` refuses a password input in this console's source, and a form
  assembled from a payload is the way round a check that reads source. Rendering it as an
  ordinary text box would be worse than dropping it.

**The validator needs `unsafe-eval`, and that has to be decided before a form is mounted.**
`@rjsf/validator-ajv8` compiles each schema into a function with `new Function`, at
`node_modules/ajv/dist/compile/index.js:89`. Under the Content-Security-Policy this README
proposes further down, that call throws and the form stops validating. Four ways out, and the
last one is the one this console's own argument points at:

1. Add `'unsafe-eval'` to `script-src`. It buys client-side validation at the cost of the
   single most useful directive in the policy, for the whole application, for ever.
2. Ajv's standalone code generation, which precompiles validators at build time. It cannot
   work here: the schema arrives at run time from the API, and precompiling needs it at build
   time. This is the answer for a fixed schema and this leaf is about generated forms.
3. Write a validator against `ValidatorType`, which is a small interface, that interprets the
   schema instead of compiling it. Real work, and a third description of JSON Schema
   semantics in a system that already has two.
4. Do not validate in the browser. **The console is not a trust boundary**, so client-side
   validation is a courtesy and never a check: the API validates what it is sent and refuses
   what it does not like, and it would do that whatever this form believed. What is lost is
   the round trip, which is worth something and is worth less than the directive.

Nothing is decided here, because the decision belongs with whoever writes the CSP and mounts
the first form, and both of those are the same person. The validator is wired as the library
ships it so that the choice is visible rather than pre-empted.

### Canvases

`components/GraphCanvas.tsx`, `TraceGraph.tsx` and `graph.ts`, on `@xyflow/react`.

One mount, for the same reason there is one `fetch`: two would be two sets of interaction
flags and the second is where somebody leaves `nodesConnectable` on. It is read-only as a
shape rather than as a setting, because the nodes and edges are props with no change handlers
and there is nowhere for a change to go.

`graph.ts` holds the two rules a drawing library will not keep for you:

- **An edge whose other end did not arrive is dropped with the node.** A payload filtered for
  a caller carries one easily, because the edge is a fact about the step they hold. Drawn, it
  is an arrow that leaves a node and ends nowhere, which says a step is there.
- **The layout is a function of what arrived.** The sharpest placeholder is not an element, it
  is a space: a layout that gave every node an edge mentioned a column would leave a gap
  exactly where the withheld step was. Rows are packed from the surviving nodes, so two
  callers entitled to different subsets each get a graph with no hole in it.

Deliberately no layout library. `dagre` and `elkjs` both draw better and neither has its
placement rule anywhere a reviewer would read it, and the placement rule is the property.

`base.css` is imported rather than `style.css`: the first is the mechanics, the second adds a
visual theme with its own colours. The library reads its colours through variables with a
`-default` fallback, so `styles/app.css` points the un-suffixed names at tokens and the canvas
follows this console's theme. **The vendor stylesheet is not covered by the theme tests**,
which read this project's two stylesheets and nothing else; `base.css` still contains a
hard-coded grey for the attribution link, which is overridden, and colours for the minimap and
the resize control, which are components this console does not mount.

### What these dependencies weigh

Measured on 2026-09-06. The first row is `npm run build`, which is the whole application with
React in it and none of these components reachable. The other three are `vite build` over a
throwaway entry importing the component, with React, React DOM and the JSX runtime declared
external, so each figure is what mounting that component would add rather than a total.

| Entry | Bundle | Gzipped |
| --- | --- | --- |
| The application as it stands | 267.01 kB | 85.74 kB |
| plus `SchemaForm` (`@rjsf/core`, `ajv`, `lodash`) | 607.75 kB | 166.85 kB |
| plus `GraphCanvas` (`@xyflow/react`, `zustand`) | 257.96 kB | 72.17 kB |
| plus both | 866.18 kB | 238.90 kB |

Roughly tripling the bundle is a real cost and it is worth knowing before either is mounted:
the answer is a route-level split, which is a change to `App.tsx` at the point somebody adds
the screen rather than something to do speculatively now. The throwaway entry and its config
were deleted; they are recorded here because the numbers are the point, not the files.

### What the split actually saved

Measured on 2026-09-06, after the records screen was mounted. Every row is `npm run build`
over the real application rather than over a throwaway entry, so these are totals and the
table above is not.

| Build | Entry chunk | Gzipped | Loaded on demand |
| --- | --- | --- | --- |
| Before: nothing mounted | 267.01 kB | 85.74 kB | none |
| After: records route split | 270.44 kB | 86.99 kB | 444.73 kB (148.78 kB gzipped) |
| Measured and reverted: records route imported eagerly | 716.96 kB | 236.22 kB | none |
| Measured and reverted: records route split, query form removed | 270.42 kB | 86.98 kB | 37.71 kB (12.34 kB gzipped) |

The split leaves the first response 3.43 kB larger than it was with no screens at all, and
the alternative was 449.95 kB larger. Vite prints its own 500 kB warning on the eager build,
which is the shape of the argument in one line. The `Records` chunk arrives when somebody
opens the section, and the shell paints before it does: the suspense boundary is inside
`Shell`, around the outlet, so the header and the navigation never wait for a network
response. A menu that waited would be a menu whose contents could in principle depend on what
came back.

**The last row is the one to argue with.** The grid and the whole records page are 37.71 kB;
the generated query form is the other 407 kB, for two fields. That is the honest cost of
mounting `@rjsf/core` on a two-input form, and it is written here rather than left in a build
log because the decision should be reversible by whoever disagrees. The case for keeping it:
it is the leaf the library was chosen for, the form's bounds come from the route's own
document and are checked against it, and the split means nobody pays for it until they open
the section. The case against: the schema is assembled by this console rather than sent by
the API, so the property that justifies a form library, that nobody read this form before it
rendered, is not actually present on this screen; and the ajv validator needs `unsafe-eval`,
which is a security decision nobody has taken yet. Replacing it with two hand-written inputs
is a change to one file, and `tests/records-page.test.tsx` would keep the bounds honest
either way, because it checks the constants against the Python module and the OpenAPI
document rather than against the form.

**The split is checked as a property of the source, not as a number in a build log.**
`tests/bundle-split.test.ts` walks the static import graph from `src/main.tsx`, does not
follow `import()`, and fails when `@rjsf/core`, `@rjsf/validator-ajv8`, `@tanstack/react-table`
or `@xyflow/react` is reachable. A static import of the records page is the change that
undoes all of this, it is one line, and it is the line that test exists to refuse.

`TraceGraph` imports the one empty-page sentence from `DataTable.tsx` rather than spelling it
again, because two spellings of one sentence is two sentences and the second is the one
somebody later makes more helpful. That import costs nothing: an entry importing only that
constant builds to 0.17 kB, so the grid is tree-shaken away.

## The component layer: shadcn/ui on Radix, with Tailwind (M27.10.2, M27.10.4)

The owner chose shadcn/ui on its Radix base with Tailwind CSS v4 on 2026-09-17 and approved the
design spike's look; `docs/admin-console-architecture.md` 5.7 records the choice. This section is
the foundation that decision needs, and **no page is restyled by it**: the shell, the navigation and
every screen render exactly as they did, which is measured below rather than assumed. The shell is
the next package and is built from these parts.

### What was added

| Package | Version | Licence | Where it ends up |
| --- | --- | --- | --- |
| `tailwindcss`, `@tailwindcss/vite` | 4.3.3 | MIT | the build; nothing at run time |
| `@tailwindcss/node`, `@tailwindcss/oxide` | 4.3.3 | MIT | the tests only (`tests/support/tailwind.ts`) |
| `radix-ui` | 1.6.7 | MIT | the components' primitives |
| `class-variance-authority` | 0.7.1 | Apache-2.0 | variants |
| `clsx`, `tailwind-merge` | 2.1.1, 3.7.0 | MIT | `lib/utils.ts`'s `cn` |
| `lucide-react` | 1.46.0 | ISC | icons, one module per icon imported |
| `sonner` | 2.0.8 | MIT | the toast region |
| `cmdk` | 1.1.1 | MIT | the command palette |
| `react-hook-form`, `zod`, `@hookform/resolvers` | 7.88.0, 4.6.5, 5.9.1 | MIT | nothing yet: the first validated form is a later package's, and must be a lazy route |
| `tw-animate-css` | 1.4.0 | MIT | the open and close animations |
| `@fontsource/ibm-plex-sans`, `@fontsource/ibm-plex-mono`, `@fontsource/poppins` | 5.2.8, 5.2.7, 5.2.7 | OFL-1.1 | 18 font files in `dist/assets`, 157.50 kB of them woff2 |

Every version is exact, for the reason the rest of this directory's are. The versions are the design
spike's wherever the spike used the package, so what the owner approved is what is built; the spike
imported the `cn` package where this uses `clsx` and `tailwind-merge`, which is shadcn/ui's own
`lib/utils.ts` and what every component copied from it assumes. The pins this console already had
did not move: React 19.1.0, React DOM 19.1.0, Vite 6.4.3, react-router-dom 6.30.6 and
`@tanstack/react-table` 9.2.4, and the lockfile changed the version of no existing package (compared
entry by entry: none changed, none removed). **Nothing is fetched from a CDN**: the fonts are imported
from `@fontsource` in `theme/tailwind.css` and served from this origin, because an install may have no
route to a font host and a font fetched from one tells a third party each time somebody opens the
console. Installing into a fresh worktree took 64 seconds for the existing lockfile and 89 seconds
more for the new set (75 and 14), on this machine with its own `node_modules`.

**shadcn/ui's CLI is not a dependency.** Its `tailwind.css` supplies nine state variants and one
utility the components use, and those are copied into `theme/tailwind.css`; its other utilities
(scroll fade, shimmer) are not used and are not copied. There is no `components.json`, because the
components import each other by relative path, which is what `tests/support/typescript.ts`'s import
graph follows. An upstream change arrives by generating the component in a scratch project with
`shadcn add` and diffing it against the copy here, and every local change is listed at the top of the
file it was made in, so it can be re-applied.

### Licences

Everything added is MIT, ISC, Apache-2.0 or OFL-1.1, and no purchase is involved. The texts are the
`LICENSE` or `LICENSE.md` file in each package under `node_modules/`. Two are recorded here as well,
because they are not only depended on but copied or shipped:

- **shadcn/ui**, MIT, Copyright (c) 2023 shadcn. Every file in `src/components/ui/` except
  `explained.tsx`, `secret-field.tsx` and `focus-return.ts` is a modified copy of a shadcn/ui
  component. The MIT licence asks that its copyright notice and permission notice be included in all
  copies or substantial portions; the notice is the line above and the permission text is
  shadcn/ui's `LICENSE.md` (https://github.com/shadcn-ui/ui/blob/main/LICENSE.md), which is the
  standard MIT text.
- **IBM Plex Sans and IBM Plex Mono** (Copyright 2017 and 2019 IBM Corp.) and **Poppins** (Copyright
  2020 The Poppins Project Authors), all under the SIL Open Font Licence 1.1, which allows bundling
  with software and asks that the copyright notice and the licence travel with the fonts. The texts
  are `node_modules/@fontsource/<font>/LICENSE`.

**What is not done about either**: the built image carries `dist/` and not `node_modules/`, so neither
notice is inside the image today. A notices file served beside the bundle is the fix, and it belongs
with whoever next touches the Dockerfile's console stage.

### The cascade, and how the old pages stay as they were

Three mechanisms, each held by `tests/tailwind-foundation.test.ts`:

1. **The old sheets are in a `legacy` cascade layer**, between Tailwind's reset and its utilities
   (`@layer theme, base, legacy, components, utilities`). They were unlayered, and an unlayered rule
   beats every layered one, so `app.css`'s `a`, `h2` and `code` rules would otherwise beat a class on
   a new component. `scripts/legacy-layer.mjs` wraps `app.css`, `approvals.css`, `agent-workspace.css`
   and `@xyflow/react/dist/base.css` at build time, so the files and the tests that read them are
   unchanged, and all four move together so their order among themselves is what it was.
   `tokens.css` stays unlayered: a token has to beat Tailwind's variable of the same name.
2. **Tailwind's reset applies to the new components and not to the old pages.** Loaded globally it
   takes the weight off headings, the bullets off lists and the underline off links, which the old
   sheets never set because the browser did; `theme/preflight.css` narrows every rule to elements
   carrying `data-slot`, their contents, and not an element inside `[data-legacy]`. **The shell that
   comes next must put `data-legacy` on the element that renders an old page**, because the sidebar's
   provider is a `data-slot` element around the whole application.
3. **Tailwind generates no utility named like an old class.** It reads `src/components/ui` only
   (`source(none)` and one `@source`), and `@source not inline("grid")` refuses the one collision
   there is: every data table sits in `.grid`, which Tailwind would make `display: grid` in a layer
   that now outranks `app.css`. The test compiles every class name an old sheet or an old page uses
   and asserts none comes out as a rule, and proves the exclusion is load-bearing by compiling without
   it.

**Measured in Chrome, not inferred from the suite, which applies no stylesheet.** Every registered
page's rendered markup (62 pages, from the same stand-in answers `phone-width.test.tsx` uses) was
painted with the stylesheets of the build before this change and of the build after it, with every
component's utilities in the bundle, at 360 and 1280 pixels, in the light theme, the machine's dark
theme and an explicit dark choice: 372 comparisons, 68,898 elements, every computed property except
custom properties and every element box compared, against origin/main at f32c385. **No difference.**
The same run against the earlier base e14969a compared 68,718 elements with the same result. Two
negative controls, taken on that earlier base, show the comparison would have seen one: the same
build with Tailwind's reset global changed 1,641 computed properties on the overview alone, and with
the `grid` exclusion removed every records table's display turned from flex to grid. The harness is
outside version control (it is a browser run, and this directory commits no browser); the numbers are
the record.

**Known leak in the other direction.** An old element rule still reaches a bare element inside a new
component for any property the component leaves unset (a `p` inside a card takes `app.css`'s margin).
The copied dialog, sheet, popover and empty-state parts set margin and size on their own headings and
paragraphs for that reason; a page that moves puts its own classes on what it adds.

### The theme

`tokens.css` carries the design of record's tokens beside the old ones, in the same three blocks, with
names that do not meet the old ones: shadcn/ui's `--border`, `--accent` and `--radius` are already
the old pages' names, so the class names are mapped straight onto the design's tokens in
`theme/tailwind.css`'s `@theme inline` rather than through shadcn/ui's variables, and Tailwind's
`--font-sans`, `--text-*` and `--radius-lg` are restated inline so a utility never reads the old
value of the same name. `tests/design-tokens.test.ts` holds the vocabularies apart. Tailwind's
palette is removed (`--color-*: initial`), so a class can name only a token, and
`scripts/check-boundaries.mjs` refuses a palette class or an arbitrary colour in the source.

Two measured departures from `docs/screens.html`, both in the tokens file's own comment: `--dim` is
the design's grey moved a tenth of the way to its ink, because the design's value is 4.02 to 1 on the
sunk surface a muted label sits on, and `--faint` is kept and mapped to no class, because it is below
4.5 to 1 on every surface in both themes. `brain.locale.READ_PAIRS` now measures the design's pairs.

**The accent is the install's.** `INSTALL_ACCENT_COLOUR` (default `#2563eb` in `brain.install`, which
is the product's and no company's) is turned by `brain.locale.accent_set` into six colours, the fill,
the text on it, the accent as text in each theme and a wash in each theme, each measured at 4.5 to 1
against every surface it is drawn on, and served in `/api/console.js`. `theme/accent.ts` puts them on
the root element before the first render, through the style object rather than a `<style>` element.
With no accent served, the tokens fall back to the design's own ink, which reads. The focus ring on
every new component is the accent's text colour at full strength, so its contrast is the derivation's.

### Content-Security-Policy

**No policy is served today** (see "What is NOT done"), so nothing in this change is blocked. The
policy proposed there already has `style-src 'self' 'unsafe-inline'`, and it needs it: `sonner`
inserts its stylesheet as a `<style>` element and Radix's scroll lock does the same, which the design
spike measured in Chrome with these same versions (four violations under `style-src 'self'`, none with
`'unsafe-inline'`); it was not re-measured here, because no page mounts either yet. `script-src` is
untouched: nothing added evaluates code, the accent is applied through the CSS object model, and
`zod` is not reachable from any page (the spike ran it with `jitless`, which the first form that
imports it must set too).

### What these parts weigh

`npm run build`, measured 2026-09-17, with Vite's own figures.

| Build | Entry JS | Gzipped | Entry CSS | Gzipped |
| --- | --- | --- | --- | --- |
| Before (origin/main f32c385) | 601.56 kB | 170.60 kB | 13.63 kB | 3.04 kB |
| After: tokens, reset, every component's utilities and the fonts' faces | 602.25 kB | 170.88 kB | 84.13 kB | 14.23 kB |

The script barely moves because no page imports a component yet; the 0.69 kB is `theme/accent.ts` and
the accent reading in `config.ts`. The stylesheet grows by 70.50 kB (11.19 kB gzipped) because
Tailwind emits every utility the component directory uses whether or not a page mounts it, and the 18
font files are fetched only when something is drawn in their face. `tests/bundle-split.test.ts` now
refuses `react-hook-form`, `zod`, `@hookform/resolvers` and `cmdk` in the entry; `radix-ui` and
`sonner` are expected there once the shell lands.

### How the four jsdom layout tests move when the first page is restyled

Measured now, with no page restyled: `phone-width.test.tsx` (124 tests), `approvals-phone.test.tsx`
(8), `status-primitives.test.tsx` (15) and `theme.test.ts` (12) all pass unchanged. They read the old
stylesheets from disk, which is correct for as long as the pages they render are styled by those
sheets. In the commit that restyles the first page:

1. **`phone-width.test.tsx` and `approvals-phone.test.tsx`** read `CONSOLE_SHEETS` through
   `support/cascade.ts`. Hand `declared()` the rules from `compiledRules((await compileLayer()).css)`
   (`support/tailwind.ts`) concatenated after `consoleRules()`, so a restyled element's utilities are
   seen and an old one's rules still are. `tests/ui-structure.test.tsx` is the worked example: it reads
   a drawer's width and a table's overflow at 360 pixels that way. Where the menu moves to the Menu
   button (5.1), the "navigation above the page" test changes to the Menu-button property in the same
   commit, and `ui-structure.test.tsx`'s phone sidebar test already holds that property for the part.
   Order between the two rule sets is not modelled by the reader, so a claim that a utility beats an
   old rule belongs in the browser comparison above, not in these tests.
2. **`status-primitives.test.tsx`** holds "one rule per tone" over `app.css`. A restyled status moves
   that rule to the component's own tone map, and the test's "no component writes a colour" already
   reads `src/components`; `tests/ui-rules.test.ts` holds the compiled half (every colour a component
   paints reads a token) and the badge's `variant` is held as its `tone` is.
3. **`theme.test.ts`** keeps its three-state tests on `tokens.css` unchanged. Its "no stylesheet outside
   the tokens file names a colour" reads `app.css` only; `tests/tailwind-foundation.test.ts` extends it
   to `tailwind.css` and `preflight.css`, and it must extend to any sheet a moved page brings, which
   the "a new stylesheet under src is a decision" test forces somebody to notice.
4. **Anything that moves to a browser instead goes to W1.6's harness**, and the old test is changed in
   the commit that adds its replacement, never deleted ahead of it.

## What is NOT done

- **No browser has run any of this.** The suite below runs under jsdom, which parses CSS
  and matches selectors but does not evaluate a media query or compute a colour from a
  custom property. So "an explicit light choice wins on a dark machine" is checked as a
  fact about the rule and the selector, not as a painted page, and nothing here measures
  contrast. Phone widths were measured once, by hand, in headless Chrome on 2026-09-15, and
  the figures are in `styles/app.css`. `tests/phone-width.test.tsx` holds the declarations
  that measurement depended on, through a reader that applies width queries itself, and no
  committed test opens a browser.
- **No CI job, and `.github/` was not touched.** Whether this repository grows a JavaScript
  pipeline is a decision that has not been made, and making it by adding a workflow file
  would be making it quietly.
- ~~**Not in the Dockerfile and not in any compose file.**~~ Done. The Dockerfile builds this
  directory in its own Node stage on the Node major CI checks it with, and the runtime image
  carries `dist/`. `brain.console_static` serves it at the root of the install's web address,
  which is the origin the realm's registered redirect URI is derived from, so the two cannot
  disagree. No compose file changed and no service was added: see that module for why one
  image rather than a static container beside it, and `tests/unit/test_console_served.py` for
  what is held.
- **No Content-Security-Policy.** A meta tag cannot express `frame-ancestors` and cannot be
  templated per deployment without failing open when the variable is missing, so the policy
  belongs on the response headers of whatever serves these files. A starting point:
  `default-src 'self'; connect-src 'self' <keycloak origin>; img-src 'self' data:;
  style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'`. Note that the
  pre-paint theme script is inline and needs its hash in `script-src`, that
  `style-src 'unsafe-inline'` is there because Vite injects styles that way in development
  and because React Flow positions every node with an inline `style` attribute, which a CSP
  covers, and that **the policy as written stops a generated form's validation from running
  at all**. See the ajv note in the component layer section.
- **No canvas on any page.** `GraphCanvas` and `TraceGraph` are built, tested and mounted
  nowhere, and that is a decision rather than an oversight: nothing under `/api/v1` returns a
  graph, so the only thing to draw would be a run this console invented, and an invented run
  on a screen is the thing somebody screenshots. `@xyflow/react` is therefore in no chunk of
  `dist/` at all. The same goes for `Badge` and `Status`: the only state vocabulary the API
  has is `HealthState`, which appears on `/health/ready`, and that route is outside the
  versioned prefix, is unauthenticated, and answers with the names of this installation's
  dependencies. Putting it on a signed-in screen is a decision about what an operator's
  facts are worth to a reader, and nobody has made it.
- **The Activity page is gone.** It was a route that said it was not built yet, which was
  honest while it was the only way for the navigation to have two entries. Now that a second
  section answers a real route, a placeholder holding a slot in the menu is worse than no
  page: every address in this console now shows something the API said.
- **The procedure canvas and the manifest form exist as components, and nothing mounts them.**
  M20.2.1, M20.2.2 and M20.1.2 were built on 2026-09-14. `TraceGraph` draws only a
  `CompletedRun`, which only `readCompletedRun` produces. `ProcedureCanvas` draws a bounded
  procedure through the same single read-only React Flow mount, connects steps with dropdowns
  beside the drawing rather than by dragging, and sends a drawing `brain.builder.procedure`
  turns into a SKILL.md. `ManifestForm` renders the seven manifest sections from the schema
  `brain.builder.form` generates, and names no manifest field of its own. No route serves a
  trace, the form document, an author's tools or a SKILL.md, and no page mounts any of the
  three, so what exists is both halves meeting at the checked fixtures under
  `tests/fixtures/`, and nothing a person can open yet.
- **No AI co-author and no drafts.** The co-author proposing diffs to a manifest and the draft
  store with its versions are separate leaves, and neither is built.
- **The header still says nothing about who is signed in.** The name is on the overview,
  where it came from `GET /api/v1/me`, and it is not in the corner of every page. Putting it
  in the header would mean the shell fetching on every route or holding the answer past the
  moment it was true, and neither is worth a name in a corner. `tests/shell-navigation.test.tsx`
  asserts the header carries no token material, and that stands.
- **No form is submitted to anything.** The one form on a page collects a query and turns it
  into an address. `SchemaForm`'s `onSubmit` hands back a record with the withheld names
  stripped, and nothing sends one anywhere, because no route accepts a write.
- **No error reporting, no analytics, no telemetry.**
- **`vite.config.ts` is not typechecked**, deliberately: including it would mean adding
  `@types/node` and a second tsconfig. A mistake in it surfaces when the build fails rather
  than when `npm run typecheck` does.
- **Nobody has seen the lock in a browser, and there is now nowhere to look.** The sample
  panel on the overview page has been deleted, as its own comment asked, because a real
  record renders on `/records/{entity}`. The catch is that the deployed application registers
  no row tool, so every entity answers 404 and no lock will render anywhere until one is
  wired. What the suite proves is that the markup in a grid cell is byte-identical to a
  standalone lock; what nobody has done is look at one on a screen.

---

## What is unverified

Everything that needs a browser or a live identity provider. The list is shorter than it
was; items 1, 2, 4 and 5 of the original eight are now verified and are recorded above.

1. **No sign-in has ever been performed against a real Keycloak.** The flow is exercised
   end to end in the suite against a stand-in provider that behaves the way the realm file
   describes, which checks this console's half of the conversation and nothing about
   Keycloak's. It cannot be checked for real until the redirect URIs are registered.
2. **No page has been painted.** jsdom parses the stylesheets and matches selectors, so
   the theme's rules are checked as rules, but it evaluates no media query and computes no
   colour. A stylesheet that is structurally correct and visually broken passes everything
   here.
3. **Colour contrast is estimated, not measured.** The palettes look comfortably above the
   AA threshold by inspection. Nobody has run a contrast checker over them.
4. **No accessibility audit.** There is a skip link, a labelled navigation landmark, a
   radio group with a legend, visible focus rings, `prefers-reduced-motion`, and current
   state marked by more than colour. The suite checks the skip link is first and that the
   current section is marked by `aria-current` rather than only by colour. None of it has
   been through a screen reader.
5. **The cross-tab refresh race is not fixed and is not tested.** Two tabs cannot await
   each other's promise, and a test with one module graph cannot reproduce two tabs. See
   the section above for the two ways to fix it.
6. **No row has ever come back from a real route.** The grid is mounted on
   `GET /api/v1/records/{entity}` and the request it sends is checked against the route's own
   OpenAPI document, but the deployed application registers no row tool, so every entity
   answers 404 for everybody. That is the correct answer for an install with no data plane and
   it is indistinguishable from a refusal, which is the property that matters; what it is not
   is a row on a screen. Everything about how a payload renders, including which fields lock,
   is checked against stand-in bodies in the shape `RecordPage` serialises.
   There is still no endpoint that returns a JSON Schema for a form or a graph for a run. The
   records query form is generated from a schema this console assembles out of the route's own
   parameters, with the bounds checked against the route, so `formShape` runs over a real
   document and never over one carrying a lock. `readGraph` is checked against a shape this
   console proposes and against nothing else, and the failure mode of disagreeing with
   whoever writes that endpoint is quiet: a canvas with nothing on it reads as a permission
   problem.
7. **Nothing on the canvas has been positioned by a browser.** jsdom runs no layout and has
   no `ResizeObserver`, so `tests/setup.ts` supplies one that observes nothing. React Flow
   therefore measures every node as having no size, renders them hidden, and draws no edges
   at all. What the suite reads is which nodes and which text reach the DOM and what the
   placement arithmetic in `graph.ts` computes; that an edge is drawn between two nodes, that
   a node fits inside its box, and that `fitView` frames the graph are all unchecked. The
   node width is the one place the arithmetic and the stylesheet have to agree, and that is
   asserted against the token rather than left to inspection.
8. **The canvas has not been through a screen reader and probably reads badly.** It is a set
   of absolutely positioned boxes inside `role="application"`, which is the shape React Flow
   has. The labels are real text and the group is labelled, and that is the whole of what can
   be claimed. A run that has to be readable without sight most likely wants the same trace
   rendered as a list beside it, and that is a decision rather than an omission.
9. **No form has been submitted to anything but an address.** `onSubmit` hands its caller a
   record with the withheld names stripped, and the one call site turns a query into a link.
   Nothing writes.
10. **The screens have been mounted and never opened.** The pages are exercised through the
    real route table against a stand-in API, in jsdom, which paints nothing. That a grid with
    fifteen columns is readable, that the query form's two fields sit where somebody expects
    them, and that a lock is legible beside a value are all unchecked.
11. **`npm audit` is clean at high and reports two moderate advisories against react-router**,
    both of which cover every version from 6.0.0 to 7.17.0 and are fixed only by the 7.x
    major. One of them, GHSA-wrjc-x8rr-h8h6, is an open redirect through a backslash reaching
    `<Link>` and `useNavigate`, and the records screen is the first place in this console
    where something a person typed reaches `navigate`. Every address it builds is a constant
    `/records/` prefix and one encoded segment, which is asserted against a set of hostile
    entity names; what has not been done is the upgrade, and the second advisory concerns SSR
    hydration, which this application does not do.

---

## What a reviewer must check before this is trusted

1. `npm install`, `npm run api:generate`, `npm run typecheck`, `npm run build`, `npm test`.
   All of these pass as committed; a failure means something in your environment differs,
   most likely the Node version.
2. `npm run check:boundaries`, and read the rules while doing it. A rule nobody can justify
   is one the next person deletes to make a build pass.
3. That the client id in `src/auth/constants.ts` is still the realm's, and that
   `CALLBACK_PATH` and `SIGNED_OUT_PATH` still match the registered URIs character for
   character.
4. The audience mapper question above. It decides whether any token this console obtains is
   accepted by the API at all.
5. That a real sign-in works end to end against a real Keycloak, including a token refresh
   after five minutes and a sign-out that actually ends the SSO session (open the console
   again afterwards: if it signs in with no prompt, the sign-out did not work).
6. That nothing in `src/` reads a token's contents. The boundary check covers the obvious
   spellings and cannot cover an inventive one.
7. That the deployment serves this over HTTPS with a CSP. The `index.html` fallback is no
   longer a deployment question: the application serves it, and `tests/unit/test_console_served.py`
   holds that a deep link, `/first-run` and `/auth/callback` all reach it while no API path or
   method is shadowed. **A CSP is still nobody's**, and the note above about the ajv validator
   needing `unsafe-eval` still applies.

---

## The tests

Vitest, `@testing-library/react` and jsdom, all pinned exactly. `npm test` runs them;
`tests/` holds them, one file per property group, and they are named as property sentences
with a docstring saying what breaks if each is deleted, in the style the Python side uses.

They are not typechecked, which matches the Python side, where `mypy` runs over `src` and
not over `tests`. `tsconfig.json` therefore still covers `src` only, and the decision
recorded in it about not pulling Node's types into the application's typecheck stands.

**The ten tests this section used to ask for all exist.** They are spread across the files
below and several grew siblings, because a guard tested only by its refusals is satisfied
by a function that refuses everything.

| File | What it holds |
| --- | --- |
| `tests/lock.test.tsx` | The lock is identical in every context, takes no props, says what the backend says, and its class has no modifiers. |
| `tests/theme.test.ts` | Three states, the `:not([data-theme="light"])` guard, every token defined on the bare `:root`, and the two dark blocks in step. |
| `tests/auth-realm.test.ts` | Every constant in `src/auth/constants.ts` against `ops/keycloak/realm-export.json`. |
| `tests/auth-pkce.test.ts` | The S256 challenge against the RFC 7636 vector, single use, and the attempt window. |
| `tests/auth-session.test.ts` | No token in any store, `state` verified, single-flight refresh, the return-address guard, the loop guard, sign-out. |
| `tests/api-errors.test.tsx` | The fallback sentences against `brain.core.errors`, a bodiless failure worded by what answered and never only "Something went wrong.", the problems a failure carries, and that nothing is added to a 404 on the way to the screen. |
| `tests/field-problems.test.tsx` | A validation refusal drawn beside the input each problem names, on a hand-built form and a generated one, the problems no input holds listed under the notice, and a write the API accepts drawing none of it. |
| `tests/second-factor.test.tsx` | A 404 with `second_factor_needed` shows the API's sentence and a sign-in that sends `prompt=login`, the same 404 without the flag shows neither, and the shell's banner is drawn from `GET /me`'s flag and nothing else. |
| `tests/api-client.test.ts` | The bearer token, no cookies, no allow-list, a refusal as a value, and what a 401 does. |
| `tests/shell-navigation.test.tsx` | The navigation is identical for every session the API gives one answer, on every page, and names nobody. |
| `tests/routing.test.tsx` | Deep links, the console's own 404, and the two routes that must stay outside the guard. |
| `tests/config.test.tsx` | The issuer rules, and that a misconfigured console names the variable on the screen. |
| `tests/startup.test.ts` | `src/main.tsx`, which nothing else reaches: the theme applied before the first render, and the contract with `index.html`. |
| `tests/data-table.test.tsx` | The grid renders the page it was handed: no slicing, no filtering, no count, and one lock per withheld cell. |
| `tests/server-paging.test.tsx` | The cursor, the query string, the total that reaches nothing, and the locked-cell reader. |
| `tests/status-primitives.test.tsx` | The chip, the badge and the tone table, and that no other module turns a value into a colour. |
| `tests/schema-form.test.tsx` | A generated form: the lock in place of a withheld field, the value that is never written back, the field the API did not send, and the credential nobody collects. |
| `tests/trace-graph.test.tsx` | The canvas: the dangling edge, the packed layout, the absent step with no placeholder, and the read-only surface. |
| `tests/overview-page.test.tsx` | The caller's own facts against `CallerView` in the Python source, absence contributing nothing, no invented lock, and a failure in the API's own words. |
| `tests/records-page.test.tsx` | The request against the route's declared parameters, the column a withheld field still gets, the chrome that does not change with the number of rows, and the bounds against `brain.knowledge.rows`. |
| `tests/bundle-split.test.ts` | The static import graph from `main.tsx`, and the four libraries that must not be in it. |
| `tests/phone-width.test.tsx` | Every registered route at a phone's width, read through `support/cascade.ts`: no `max-width` query in any sheet, no width wider than the phone, the navigation above the page and a thumb tall, and every value the API sent able to break. |
| `tests/tailwind-foundation.test.ts` | The cascade layer order, the old sheets wrapped whole and the new ones not, the reset's scope against the browser's own selector engine, Tailwind reading one directory, and no old class name compiling to a utility. |
| `tests/design-tokens.test.ts` | The design of record's tokens in three states, the accent drawn only from the install's configuration, the old and new vocabularies apart, and no class able to name the faint grey. |
| `tests/accent.test.ts` | The six accent names read as the server writes them, a malformed accent refused without stopping the console, and the colours on the root element before the first render. |
| `tests/ui-controls.test.tsx` | Button, badge, input, textarea, label, checkbox (a dash, never a tick, for "some selected"), switch, select, and the write-once secret field, from the keyboard. |
| `tests/ui-overlays.test.tsx` | Dialog, confirmation, drawer, popover, menu, tooltip, command palette and toast region: focus in, Escape out, and focus back to the opener however the overlay was opened. |
| `tests/ui-structure.test.tsx` | Sidebar at desktop and phone width, tabs, breadcrumb, table, card, drawer and dialog widths read from the compiled stylesheet at 360 pixels, scroll area, separator, skeleton, empty state and explanation panel. |
| `tests/ui-rules.test.ts` | Over every component: no totals, no cookie, every class compiles, every colour reads a token, the focus ring at full strength, a badge's colour never chosen from data, and every promised part present and tested. |

**Several constants are checked against the thing they are a copy of, not against
themselves.** That is the point of `tests/support/python.ts` and the realm parsing in
`tests/auth-realm.test.ts`: a test that imports `LOCK_TEXT` and compares it with
`LOCK_TEXT` is green for every value the constant could hold. The lock text and the failure
sentences come out of the Python source, the client id and the registered paths out of the
realm export, the PKCE vector out of RFC 7636, and the default API base out of
`.env.example`.

**Stylesheets are parsed rather than searched.** Both style files name the thing they
forbid in a comment in order to forbid it, so a substring search for
`:root:not([data-theme="light"])` or for `.lock--out-of-scope` would be satisfied by the
comment with the real rule gone. `tests/support/css.ts` strips comments and reads rules,
and the theme test hands the selector it found to the browser's own matcher.

**The request is checked against the API's own document, not against a spelling here.**
`tests/support/openapi.ts` reads `src/api/generated/openapi.internal.json`, which
`scripts/export-openapi.py` produces straight out of `create_app`. The query parameters the
console sends and the bounds its form offers are both compared with it, because a type is
erased at build time and a console that sent a parameter no route declares would compile,
build and ship, with a filter that silently does nothing at the other end.

**Parsing extends to the component layer, for the same reason.** `Badge.tsx` writes out
`tone={ok ? "positive" : "critical"}` as the shape to refuse and `Status.tsx` writes out
`denied: "critical"`, so `tests/status-primitives.test.tsx` parses every `.tsx` under `src`
rather than searching it. `GraphCanvas.tsx` states in prose the very flags it sets, so
`tests/trace-graph.test.tsx` reads its JSX attributes out of the syntax tree.
`tests/support/typescript.ts` is where all of that lives.

**Twenty-four mutations were run against the generated form and the canvas on 2026-09-06,
and all twenty-four were caught by a specifically named test.** Each source file was restored
byte-identically afterwards and checked by md5. The four the brief asked for are in there:
a reason tooltip on a withheld field, a placeholder node for a step that did not arrive, a
node count above the canvas, and a colour literal in a component. Three of the twenty-four
were caught by tests that already existed rather than by the new ones, which is the useful
result: the colour literal in `WithheldField` and in `StepNode` were both caught by
`no component in the shared layers writes a colour`, and a `.lock--out-of-scope` rule added
to the stylesheet was caught by `the lock carries one class name and the stylesheet gives it
no modifiers`. The rules written for the theme and the lock held over two libraries neither
of them had heard of, and nobody had to extend them.

Two of them are worth recording for what they showed rather than for passing. Replacing
`ui:field` with the library's own `ui:readonly`, which is the one-word answer to "this field
is not editable", put the withheld value into the DOM as an input's `value` attribute, and
five tests failed. And keeping a locked field in the schema's `required` list left the form
unsubmittable for the person who could not fill it and submittable for the person who could,
which is a difference two people comparing screens can read off.

**Fifty-one mutations were run against this suite and fifty were caught by a specifically
named test.** The one survivor is `end={section.to === "/"}` in `src/layout/Shell.tsx`
changed to `end={false}`: measured against react-router-dom 6.30, a prefix match on `/`
requires a `/` at the boundary, so the two spellings mark exactly the same link current at
every address this console has. The expression is defensive against a router upgrade that
changes that rule, and the test that would fail the moment it changed is
`the current section is marked by more than a colour`. Changing `end` for the *other*
sections is not equivalent and is caught.
