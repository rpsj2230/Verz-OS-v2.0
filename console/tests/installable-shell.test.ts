/**
 * The installable shell: what the manifest has to say, and the one thing it must not.
 *
 * An approval arrives at eleven at night and gets answered from a home screen rather than
 * from a browser tab somebody has to find, which is the whole of what M35.3.2.1 asks for.
 * The interesting half is what installing must not bring with it.
 *
 * Task ids: M35.3.2.1
 */

import { readFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";

const CONSOLE_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const MANIFEST = join(CONSOLE_ROOT, "public", "manifest.webmanifest");
const INDEX = join(CONSOLE_ROOT, "index.html");
const TOKENS = join(CONSOLE_ROOT, "src", "theme", "tokens.css");

async function manifest(): Promise<Record<string, unknown>> {
  return JSON.parse(await readFile(MANIFEST, "utf8")) as Record<string, unknown>;
}

describe("the installable shell", () => {
  test("the manifest declares what a platform needs to install it", async () => {
    // What breaks if this is deleted: a manifest missing any one of these is served, parsed
    // and ignored, and the install prompt never appears. Nothing errors and nothing logs;
    // the feature is simply absent, which is the shape of failure this file exists for.
    const declared = await manifest();

    expect(declared.name).toBe("Company Brain");
    expect(declared.start_url).toBe("/");
    expect(declared.scope).toBe("/");
    expect(declared.display).toBe("standalone");
    expect(Array.isArray(declared.icons)).toBe(true);
    expect((declared.icons as unknown[]).length).toBeGreaterThan(0);
  });

  test("a maskable icon is declared as well as an ordinary one", async () => {
    // What breaks if this is deleted: a platform that crops icons to a circle crops the
    // rounded corners off the ordinary one, and the result is a home screen icon with the
    // corners cut away. The two are separate files because one image cannot satisfy both.
    const icons = (await manifest()).icons as { purpose?: string }[];
    const purposes = new Set(icons.map((icon) => icon.purpose));

    expect(purposes.has("any")).toBe(true);
    expect(purposes.has("maskable")).toBe(true);
  });

  test("the manifest's colours are the ones the light theme actually uses", async () => {
    // What breaks if this is deleted: the splash screen a platform paints from the manifest
    // is a colour nothing else in the console uses, so the application flashes one shade and
    // settles on another every time it opens. Read from the token file rather than compared
    // against a literal here, so a palette change moves both.
    const tokens = await readFile(TOKENS, "utf8");
    const background = /--bg:\s*(#[0-9a-f]{6})/i.exec(tokens);
    const declared = await manifest();

    expect(background).not.toBeNull();
    expect(declared.background_color).toBe(background?.[1]);
    expect(declared.theme_color).toBe(background?.[1]);
  });

  test("the page links the manifest and an icon", async () => {
    // What breaks if this is deleted: the manifest sits in the build output and no browser
    // ever reads it, because nothing points at it. The file being present is not the
    // feature; the link is.
    const html = await readFile(INDEX, "utf8");

    expect(html).toContain('rel="manifest"');
    expect(html).toContain("/manifest.webmanifest");
    expect(html).toContain('rel="apple-touch-icon"');
  });

  test("nothing registers a service worker and the manifest declares no offline behaviour", async () => {
    // **The decision this file is really about.** The obvious next step after a manifest is
    // to cache the shell for offline use, and every guide says to. An offline cache of this
    // console is a copy of a client's data on somebody's phone: readable after they leave
    // the company, after their grants are revoked, and after the row it came from was
    // deleted. That is the disclosure the whole permission model exists to prevent,
    // arriving through a performance feature.
    //
    // What breaks if this is deleted: the rule survives only as a comment, and a comment is
    // what somebody deletes while adding the thing it argues against.
    const html = await readFile(INDEX, "utf8");
    const declared = await manifest();

    expect(html).not.toContain("navigator.serviceWorker");
    expect(html).not.toContain("registerSW");
    expect(Object.keys(declared)).not.toContain("serviceworker");
    expect(html).toContain("There is no service worker");
  });
});
