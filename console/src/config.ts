/**
 * What this installation is, read at runtime, and a refusal to start when it is wrong.
 *
 * **These values used to be compiled in, and that made one image serve one client.** Vite
 * inlines every `VITE_`-prefixed value into the bundle as plain text at build time, so a
 * console built with `VITE_KEYCLOAK_ISSUER` set was a console that could only ever be
 * installed at the company whose Keycloak that was. This product ships one image to every
 * client, so the two values that differ between installations arrive at runtime instead,
 * from `brain.console_static`, which reads them through `brain.install.value_of` like every
 * other installation setting. See `brain.console_static.NO_INSTALLS_VALUES_ARE_BUILT_INTO_THE_BUNDLE`.
 *
 * **Read synchronously from a global rather than fetched.** `index.html` loads
 * `/api/console.js` as a blocking script before the module bundle, so the object is present
 * by the time this module is evaluated. Rejected: fetching a JSON document, which is the
 * tidier shape and makes configuration asynchronous. Every consumer here is synchronous
 * (`config.issuer` is read at module scope in `auth/discovery.ts`, `config.apiBaseUrl` on
 * every request in `api/client.ts`), so a promise would either turn all of them async or
 * render the application once with nothing configured and again with it, which is a flash of
 * a broken console on every load.
 *
 * **Everything here is public.** The document is served unauthenticated and names the
 * identity provider and the client id, which is exactly what a public client with PKCE is
 * allowed to have in the open: `brain-console` has no secret to leak, because a browser
 * cannot keep one.
 *
 * **Problems are collected rather than thrown.** A misconfigured console should say which
 * setting is wrong, on the screen, to the person who deployed it. Throwing at module load in
 * a Vite application produces a blank page and a stack trace in a console nobody has open,
 * and the reported symptom is "the site is down". `configProblems` is checked once, in
 * `App`, before anything that would use these values renders.
 *
 * The one validation that looks pedantic is the trailing slash on the issuer, and it is the
 * one that has a cost attached. `brain.identity.oidc.validate_token` compares `iss` by exact
 * string equality, and explicitly rejects normalising trailing slashes, because a forgiving
 * comparison is how `https://idp.example.com.attacker.net/` gets accepted. So a console
 * configured with a trailing slash builds a discovery URL with a doubled slash, some servers
 * answer it, and the tokens that come back are then refused by the API for a reason no
 * browser error mentions. Refusing it here costs one line and saves that.
 */

import { KEYCLOAK_CLIENT_ID } from "./auth/constants";

/**
 * The global `/api/console.js` assigns, named once here.
 *
 * The spelling is a fact about `brain.console_static.CONSOLE_CONFIG_GLOBAL` rather than a
 * free choice, and `tests/console-config.test.ts` reads it out of that module so the two
 * cannot drift into a console that silently finds nothing and reports itself unconfigured.
 */
export const CONFIG_GLOBAL = "__BRAIN_CONFIG__";

/** Where the document comes from. Written down for the message shown when it is missing. */
export const CONFIG_DOCUMENT_PATH = "/api/console.js";

/** The shape the served document has. Every field is optional because it arrives untyped. */
interface ServedConfig {
  readonly apiBaseUrl?: unknown;
  readonly issuer?: unknown;
  readonly clientId?: unknown;
}

/**
 * The fallback API base, and why one exists at all when the issuer has none.
 *
 * The console and the API share an origin, so the base is a path and the path is the API's
 * own versioned prefix, which is a fact about this product rather than about an installation.
 * A wrong guess here is a 404 on the first request, which is legible. A guessed identity
 * provider is a browser redirected to a host nobody chose, which is not, so that one has no
 * default at all.
 */
const DEFAULT_API_BASE_URL = "/api/v1";

/**
 * Hosts where an insecure issuer is allowed. Only a loopback address, and only because a
 * developer running Keycloak locally has no certificate for it. Any other host over plain
 * HTTP means the token is readable in transit by everyone between here and there.
 */
const LOOPBACK_ISSUER_PREFIXES = ["http://localhost:", "http://127.0.0.1:"];

export interface Config {
  /** Where the API is. A path, because the console is served from the API's own origin. */
  readonly apiBaseUrl: string;
  /** The realm's issuer, with no trailing slash. Discovery is appended to it. */
  readonly issuer: string;
  /**
   * The realm client this console authenticates as, from `INSTALL_OIDC_CLIENT_ID`.
   *
   * Served rather than constant because the install register already declares it as a
   * setting, and two spellings of one value is the drift this file exists to remove. It
   * still defaults to `KEYCLOAK_CLIENT_ID`, which is the client the shipped realm defines
   * and whose flow settings every line of `src/auth` assumes: a deployment that renames it
   * has renamed the realm's client too, and one that sets nothing gets the product's own.
   */
  readonly clientId: string;
}

/** Whatever the served document put on the window, or an empty object when it served none. */
function served(): ServedConfig {
  const value = (globalThis as Record<string, unknown>)[CONFIG_GLOBAL];
  return typeof value === "object" && value !== null ? (value as ServedConfig) : {};
}

/** A served field as a string, or empty when it is absent or is not one. */
function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function readIssuer(raw: string, problems: string[]): string {
  if (!raw) {
    problems.push(
      "INSTALL_OIDC_ISSUER is not set on this installation. It is the realm's issuer URL, " +
        "for example https://keycloak.example.com/realms/brain. There is no default, " +
        "because a guessed identity provider is worse than a stopped console.",
    );
    return "";
  }
  if (raw.endsWith("/")) {
    problems.push(
      `INSTALL_OIDC_ISSUER ends with a slash (${raw}). The API compares the issuer by ` +
        "exact string equality and will refuse every token minted under a different " +
        "spelling of the same URL. Remove the trailing slash.",
    );
    return "";
  }
  const secure =
    raw.startsWith("https://") ||
    LOOPBACK_ISSUER_PREFIXES.some((prefix) => raw.startsWith(prefix));
  if (!secure) {
    problems.push(
      `INSTALL_OIDC_ISSUER is not https (${raw}). An access token sent over plain HTTP ` +
        "is readable by everything between this browser and the identity provider.",
    );
    return "";
  }
  return raw;
}

const problems: string[] = [];
const document_ = served();

// A missing document is its own problem and is named as one. Without this the console
// reports "the issuer is not set" when what actually happened is that the script tag in
// index.html was dropped or the application is not serving the document, and the person
// reading that message goes looking in the wrong system.
if (Object.keys(document_).length === 0) {
  problems.push(
    `This console could not read ${CONFIG_DOCUMENT_PATH}, so it does not know which ` +
      "installation it belongs to. That document is served by the application itself; a " +
      "console reached through something that does not proxy it cannot sign anybody in.",
  );
}

export const config: Config = Object.freeze({
  apiBaseUrl: text(document_.apiBaseUrl) || DEFAULT_API_BASE_URL,
  issuer: readIssuer(text(document_.issuer), problems),
  clientId: text(document_.clientId) || KEYCLOAK_CLIENT_ID,
});

/** Empty when the console is configured. Rendered as the whole page when it is not. */
export const configProblems: readonly string[] = Object.freeze(problems);
