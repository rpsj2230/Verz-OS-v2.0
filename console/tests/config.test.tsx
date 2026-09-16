/**
 * What this installation is, where the console learns it, and the refusal to start when it
 * is wrong.
 *
 * **These values used to be compiled in.** Vite inlines every `VITE_`-prefixed value into
 * the bundle as plain text, so a console built with an issuer set was a console only the
 * company owning that issuer could install, and this product ships one image to every
 * client. They arrive at runtime now, from the document `brain.console_static` serves, and
 * the first group below is the one that holds that true rather than merely described.
 *
 * **Problems are collected and shown rather than thrown.** Throwing at module load in a
 * Vite application produces a blank page and a stack trace in a console nobody has open,
 * and the reported symptom is "the site is down". Naming the setting on the screen puts the
 * message in front of the person who set it.
 *
 * The trailing-slash rule is the one that looks pedantic and is not.
 * `brain.identity.oidc.validate_token` compares `iss` by exact string equality and
 * explicitly refuses to normalise, because a forgiving comparison is how
 * `https://idp.example.com.attacker.net/` gets accepted. A console configured with a
 * trailing slash therefore signs somebody in successfully and then has every token refused
 * by the API, for a reason no browser error mentions.
 *
 * Task ids: M32.5.1.3
 */

import { readdirSync } from "node:fs";
import { join } from "node:path";
import { render } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import { CONSOLE_ROOT, readConsoleFile, readRepoFile, extractOne } from "./support/repo";
import { stubLocation, stubNoServedConfig, stubServedConfig } from "./support/auth";

async function configuredWith(
  issuer: string | undefined,
  apiBaseUrl?: string,
): Promise<typeof import("../src/config")> {
  vi.resetModules();
  stubServedConfig({ issuer: issuer ?? "", apiBaseUrl });
  return await import("../src/config");
}

describe("where the configuration comes from", () => {
  test("no setting reaches the console through the bundle", async () => {
    // What breaks if this is deleted: somebody adds `import.meta.env.VITE_SOMETHING` back,
    // Vite compiles that client's value into the JavaScript, and the image stops being
    // installable anywhere else with nothing in any build saying so. Asserted over every
    // source file rather than over `config.ts` alone, because the next one to do it will be
    // a different file.
    const offenders: string[] = [];
    for (const file of sourceFiles()) {
      if (/import\.meta\.env/.test(readConsoleFile(file))) {
        offenders.push(file);
      }
    }

    expect(offenders).toEqual([]);
  });

  test("the global the console reads is the one the application writes", async () => {
    // What breaks if this is deleted: the two spellings drift, the console finds nothing on
    // the window, and it reports itself unconfigured on an installation that is configured
    // perfectly. Read out of the Python rather than restated, so this is not a constant
    // compared with itself.
    const served = extractOne(
      readRepoFile("src/brain/console_static.py"),
      /^CONSOLE_CONFIG_GLOBAL: Final = "([^"]+)"$/m,
      "CONSOLE_CONFIG_GLOBAL in brain.console_static",
    );
    const { CONFIG_GLOBAL } = await import("../src/config");

    expect(CONFIG_GLOBAL).toBe(served);
  });

  test("the path the page loads the document from is the one the application serves", async () => {
    // What breaks if this is deleted: index.html asks for a path the application does not
    // answer, the script tag 404s silently, and every install reports itself unconfigured.
    // Both ends are read from source: the HTML that asks and the Python that answers.
    const servedPath = extractOne(
      readRepoFile("src/brain/console_static.py"),
      /^CONSOLE_CONFIG_PATH: Final = "([^"]+)"$/m,
      "CONSOLE_CONFIG_PATH in brain.console_static",
    );
    const asked = extractOne(
      readConsoleFile("index.html"),
      /<script src="([^"]+console\.js)"><\/script>/,
      "the configuration script tag in index.html",
    );
    const { CONFIG_DOCUMENT_PATH } = await import("../src/config");

    expect(asked).toBe(servedPath);
    expect(CONFIG_DOCUMENT_PATH).toBe(servedPath);
  });

  test("a console served no document says so rather than blaming the issuer", async () => {
    // What breaks if this is deleted: a dropped script tag, or a proxy that does not pass
    // /api through, reports "the issuer is not set" and sends whoever reads it to look at
    // Keycloak, which is configured correctly. The two failures are different and must not
    // read the same.
    vi.resetModules();
    stubNoServedConfig();
    const config = await import("../src/config");

    expect(config.configProblems.join(" ")).toContain("/api/console.js");
  });
});

describe("the issuer", () => {
  test("a properly configured console reports no problems", async () => {
    // What breaks if this is deleted: every refusal below is satisfied by a validator that
    // refuses everything, and the console would never start anywhere. This is the sibling
    // that proves a correct value passes.
    const config = await configuredWith("https://keycloak.example.com/realms/brain");

    expect(config.configProblems).toEqual([]);
    expect(config.config.issuer).toBe("https://keycloak.example.com/realms/brain");
  });

  test("an issuer with a trailing slash is refused", async () => {
    // What breaks if this is deleted: the console builds a discovery URL with a doubled
    // slash, some servers answer it, sign-in appears to work, and then the API refuses
    // every token because it compares the issuer by exact string equality. Nothing in the
    // browser mentions a slash.
    const config = await configuredWith("https://keycloak.example.com/realms/brain/");

    expect(config.configProblems).toHaveLength(1);
    expect(config.configProblems[0]).toContain("INSTALL_OIDC_ISSUER");
  });

  test("an issuer that is not https is refused", async () => {
    // What breaks if this is deleted: an access token travels over plain HTTP and is
    // readable by everything between this browser and the identity provider. A deployment
    // that did this would work perfectly, which is why nothing else would catch it.
    const config = await configuredWith("http://keycloak.example.com/realms/brain");

    expect(config.configProblems).toHaveLength(1);
    expect(config.config.issuer).toBe("");
  });

  test("a loopback issuer is allowed for local work", async () => {
    // What breaks if this is deleted: a developer running Keycloak on their own machine,
    // where there is no certificate to have, cannot start the console at all, and the
    // pressure to relax the https rule for everybody arrives immediately.
    for (const issuer of [
      "http://localhost:8080/realms/brain",
      "http://127.0.0.1:8080/realms/brain",
    ]) {
      const config = await configuredWith(issuer);
      expect(config.configProblems).toEqual([]);
    }
  });

  test("a missing issuer is refused rather than guessed", async () => {
    // What breaks if this is deleted: a default identity provider. There is no sensible
    // guess, and a console pointed at the wrong one redirects somebody's browser to a host
    // nobody chose.
    const config = await configuredWith(undefined);

    expect(config.configProblems).toHaveLength(1);
    expect(config.configProblems[0]).toContain("INSTALL_OIDC_ISSUER");
  });
});

describe("the API base", () => {
  test("the served base is used when the document carries one", async () => {
    // What breaks if this is deleted: the document could name a base and the console ignore
    // it, which is the whole point of serving the configuration rather than building it in.
    const config = await configuredWith(
      "https://keycloak.example.com/realms/brain",
      "/api/v9",
    );

    expect(config.config.apiBaseUrl).toBe("/api/v9");
  });

  test("the default API base is the prefix the API actually mounts", async () => {
    // What breaks if this is deleted: the console's fallback and the API's prefix drift
    // apart, and a document served without a base points every request at a path nothing
    // answers. The expected value is read out of the Python rather than restated here, so
    // this is not a constant compared with itself.
    const mounted = extractOne(
      readRepoFile("src/brain/api.py"),
      /^API_PREFIX = "([^"]+)"$/m,
      "API_PREFIX in brain.api",
    );

    const config = await configuredWith("https://keycloak.example.com/realms/brain");
    expect(config.config.apiBaseUrl).toBe(mounted);
  });
});

describe("the client id", () => {
  test("the installation's client id is used when the document carries one", async () => {
    // What breaks if this is deleted: INSTALL_OIDC_CLIENT_ID becomes a setting the install
    // register declares and nothing reads, so an installation whose realm names its client
    // something else signs in against a client that does not exist.
    vi.resetModules();
    stubServedConfig({
      issuer: "https://keycloak.example.com/realms/brain",
      clientId: "brain-console-renamed",
    });
    const config = await import("../src/config");

    expect(config.config.clientId).toBe("brain-console-renamed");
  });

  test("a document naming no client id falls back to the one the shipped realm defines", async () => {
    // What breaks if this is deleted: an older application serving a document without the
    // field leaves the console with no client id at all, and the authorisation request goes
    // out with an empty one. The fallback is the realm's own client, checked against the
    // realm export in auth-realm.test.ts.
    const { KEYCLOAK_CLIENT_ID } = await import("../src/auth/constants");
    const config = await configuredWith("https://keycloak.example.com/realms/brain");

    expect(config.config.clientId).toBe(KEYCLOAK_CLIENT_ID);
  });
});

describe("a console that cannot work", () => {
  test("a misconfigured console names the setting on the screen", async () => {
    // What breaks if this is deleted: the failure becomes a redirect to
    // `undefined/.well-known/openid-configuration` and a browser error nobody can act on.
    // The useful thing to do about a console pointed at no identity provider is to say so,
    // naming the setting, to the person who deployed it.
    stubLocation("/");
    vi.resetModules();
    stubServedConfig({ issuer: "" });
    const { App } = await import("../src/App");

    const { container } = render(<App />);

    expect(container.textContent).toContain("INSTALL_OIDC_ISSUER");
    expect(container.textContent).toContain("not configured");
  });
});

/**
 * Every TypeScript source under `src/`, walked rather than listed.
 *
 * A listed set is a set that stops covering the file somebody adds tomorrow, which is
 * exactly the file the first check in this module is watching for.
 */
function sourceFiles(): string[] {
  const found: string[] = [];
  const walk = (relative: string): void => {
    for (const entry of readdirSync(join(CONSOLE_ROOT, relative), { withFileTypes: true })) {
      const next = `${relative}/${entry.name}`;
      if (entry.isDirectory()) {
        walk(next);
      } else if (/\.tsx?$/.test(entry.name)) {
        found.push(next);
      }
    }
  };
  walk("src");
  return found;
}
