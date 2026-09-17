/**
 * The install's accent, from the served configuration document to the root element.
 *
 * The colours are derived and measured on the server (`brain.locale.accent_set`, tested in
 * `tests/unit/test_locale.py` with a pale, a mid and a dark accent in both themes) and served by
 * `brain.console_static.served_accent`. What is held here is the console's half: it reads the six
 * names the server writes, it refuses anything that is not a colour in the server's spelling without
 * stopping the console, and it puts them where `tokens.css` reads them before the first render.
 *
 * Task ids: M27.10.4
 */

import { afterEach, describe, expect, test, vi } from "vitest";
import { CONFIG_GLOBAL } from "../src/config";
import { fakeIdentityProvider, ISSUER, stubLocation } from "./support/auth";
import { extractOne, readRepoFile } from "./support/repo";

/** An accent in the server's shape. The values are arbitrary colours no company is known by. */
const SERVED = {
  fill: "#1f7a5c",
  onFill: "#ffffff",
  textLight: "#1f7a5c",
  textDark: "#62a58e",
  washLight: "#e4f0ec",
  washDark: "#172720",
};

async function freshConfig(accent: unknown): Promise<typeof import("../src/config")> {
  vi.resetModules();
  vi.stubGlobal(CONFIG_GLOBAL, Object.freeze({ issuer: ISSUER, accent }));
  return await import("../src/config");
}

afterEach(() => {
  document.documentElement.removeAttribute("style");
  document.body.innerHTML = "";
});

describe("reading the served accent", () => {
  test("the console reads the six names the server writes", async () => {
    // What breaks if this is deleted: the two sides of one document spelling a name differently, so
    // the console reads nothing and every install is drawn in the neutral fallback, which reads well
    // enough that nobody reports it. The server's names are read out of `brain.console_static`.
    const source = readRepoFile("src/brain/console_static.py");
    const body = extractOne(source, /def served_accent[\s\S]*?return \{([\s\S]*?)\n {4}\}/, "served_accent's document");
    const served = [...body.matchAll(/"(\w+)":/g)].map((match) => match[1]);
    const { INSTALL_ACCENT_KEYS } = await freshConfig(SERVED);

    expect(served).toEqual([...INSTALL_ACCENT_KEYS]);
  });

  test("a served accent arrives whole", async () => {
    // What breaks if this is deleted: the sibling of every refusal below. A reader that returned null
    // for everything would pass all of them and no install would ever see its colour.
    const config = await freshConfig(SERVED);

    expect(config.config.accent).toEqual(SERVED);
    expect(config.configProblems).toEqual([]);
  });

  test("an accent with a value missing or not a colour is none, and the console still starts", async () => {
    // What breaks if this is deleted: five colours of six painting a fill whose text colour was never
    // sent, or a value such as `red; background: url(x)` handed to the style engine. And a malformed
    // tint must not become a configuration problem, which replaces the whole console with a list.
    const { onFill: _dropped, ...partial } = SERVED;
    for (const accent of [partial, { ...SERVED, textDark: "red" }, { ...SERVED, fill: "#1f7a5c80" }, "#1f7a5c", null, undefined]) {
      const config = await freshConfig(accent);
      expect(config.config.accent, JSON.stringify(accent)).toBeNull();
      expect(config.configProblems).toEqual([]);
    }
  });
});

describe("putting the accent where the tokens read it", () => {
  test("each served colour is set on the root element under the name the tokens read", async () => {
    // What breaks if this is deleted: the accent read and never applied. The property names are the
    // ones `tests/design-tokens.test.ts` holds against `tokens.css`, so this and that together are the
    // path from the document to a painted token.
    const { applyInstallAccent, INSTALL_ACCENT_PROPERTIES } = await import("../src/theme/accent");
    applyInstallAccent(SERVED);

    const style = document.documentElement.style;
    expect(style.getPropertyValue(INSTALL_ACCENT_PROPERTIES.fill)).toBe(SERVED.fill);
    expect(style.getPropertyValue(INSTALL_ACCENT_PROPERTIES.onFill)).toBe(SERVED.onFill);
    expect(style.getPropertyValue(INSTALL_ACCENT_PROPERTIES.textLight)).toBe(SERVED.textLight);
    expect(style.getPropertyValue(INSTALL_ACCENT_PROPERTIES.textDark)).toBe(SERVED.textDark);
    expect(style.getPropertyValue(INSTALL_ACCENT_PROPERTIES.washLight)).toBe(SERVED.washLight);
    expect(style.getPropertyValue(INSTALL_ACCENT_PROPERTIES.washDark)).toBe(SERVED.washDark);
  });

  test("no accent takes every accent property off the root, so the neutral fallback applies", async () => {
    // What breaks if this is deleted: a console told "no accent" keeping whatever an earlier call
    // left, which on a page that reconfigures is the previous install's colour.
    const { applyInstallAccent, INSTALL_ACCENT_PROPERTIES } = await import("../src/theme/accent");
    applyInstallAccent(SERVED);
    applyInstallAccent(null);

    for (const property of Object.values(INSTALL_ACCENT_PROPERTIES)) {
      expect(document.documentElement.style.getPropertyValue(property), property).toBe("");
    }
  });

  test("the served accent is on the root element before anything renders", async () => {
    // What breaks if this is deleted: `main.tsx` forgetting the call, which paints every component in
    // the fallback on every install and fails nothing else in the suite, because only `main.tsx`
    // connects the configuration to the page.
    vi.resetModules();
    vi.stubGlobal(CONFIG_GLOBAL, Object.freeze({ issuer: ISSUER, accent: SERVED }));
    stubLocation("/");
    vi.stubGlobal("fetch", fakeIdentityProvider().fetch);
    document.body.innerHTML = '<div id="root"></div>';

    await import("../src/main");

    expect(document.documentElement.style.getPropertyValue("--install-accent-fill")).toBe(SERVED.fill);
  });
});
