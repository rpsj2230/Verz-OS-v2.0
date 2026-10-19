/**
 * The bundle carries each bundled font's licence notice, assembled from the packages themselves.
 *
 * The Open Font Licence lets the console bundle and serve its fonts on one condition, that the
 * copyright notice and licence travel with them. `scripts/font-licences.mjs` writes
 * `font-licences.txt` into the bundle from each `@fontsource/*` dependency's own `LICENSE`, and
 * `brain.ops.bundle_audit` fails a built bundle whose font family has no section in it. These tests
 * hold the writing half: that a notice is made for every font package the manifest names and for no
 * other, that a package with no licence text or a different licence stops the build rather than
 * getting a false notice, and that the plugin is actually in the build.
 *
 * Task ids: M27.15.75
 */

import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, test } from "vitest";
// The plugin is plain JavaScript: it runs in Node under Vite, outside the typechecked sources.
import {
  FONT_LICENCES_FILE,
  bundledFontPackages,
  fontLicenceText,
  fontLicences,
} from "../scripts/font-licences.mjs";
import { CONSOLE_ROOT, readConsoleFile } from "./support/repo";

const OFL_TEXT = "Copyright 2020 Somebody\n\nSIL OPEN FONT LICENSE Version 1.1 - 26 February 2007\n...";

/** A console-shaped directory: a manifest and the licence files its font packages carry. */
function root(dependencies: Record<string, string>, licences: Record<string, string>): string {
  const dir = mkdtempSync(join(tmpdir(), "font-licences-"));
  writeFileSync(join(dir, "package.json"), JSON.stringify({ dependencies }));
  for (const [name, text] of Object.entries(licences)) {
    mkdirSync(join(dir, "node_modules", name), { recursive: true });
    writeFileSync(join(dir, "node_modules", name, "LICENSE"), text);
  }
  return dir;
}

describe("the font licence notices", () => {
  test("every font package the real manifest depends on has a section carrying the licence", () => {
    // What breaks if this is deleted: a font added to package.json ships with no notice, or the
    // notice names only the fonts somebody remembered, and the Open Font Licence's one condition
    // is broken in every copy the install serves.
    const manifest = JSON.parse(readFileSync(join(CONSOLE_ROOT, "package.json"), "utf8")) as {
      dependencies: Record<string, string>;
    };
    const expected = Object.keys(manifest.dependencies).filter((name) => name.startsWith("@fontsource/"));
    expect(expected.length).toBeGreaterThanOrEqual(3);
    expect(bundledFontPackages(manifest)).toEqual([...expected].sort());
    const text = fontLicenceText(CONSOLE_ROOT);
    const headings = [...text.matchAll(/^(@fontsource\/[a-z0-9-]+)$/gm)].map((match) => match[1]);
    expect(headings).toEqual([...expected].sort());
    expect(text.match(/SIL OPEN FONT LICENSE Version 1\.1/gi)?.length).toBe(expected.length);
  });

  test("a section is the package's own licence text and nothing paraphrased", () => {
    // What breaks if this is deleted: a notice written in the plugin's own words, which says the
    // licence is the OFL without being it.
    const dir = root({ "@fontsource/alpha": "1.0.0", react: "1.0.0" }, { "@fontsource/alpha": OFL_TEXT });
    const text = fontLicenceText(dir);
    expect(text).toContain(OFL_TEXT);
    expect(text).toContain("@fontsource/alpha\n-----------------\n");
    expect(text).not.toContain("react");
  });

  test("a font package with no licence file stops the build instead of being noticed falsely", () => {
    // What breaks if this is deleted: a font bundled with no notice, because a missing file was
    // read as an empty one.
    const dir = root({ "@fontsource/alpha": "1.0.0" }, {});
    expect(() => fontLicenceText(dir)).toThrow(/ships no LICENSE file/);
  });

  test("a font package whose licence is not the Open Font Licence stops the build", () => {
    // What breaks if this is deleted: the notice says every font is under the OFL while one
    // package's own file says something else, which is a false statement shipped in the bundle.
    const dir = root({ "@fontsource/alpha": "1.0.0" }, { "@fontsource/alpha": "All rights reserved." });
    expect(() => fontLicenceText(dir)).toThrow(/not the SIL Open Font Licence/);
  });

  test("a console that bundles no font package has nothing to write and says so", () => {
    // What breaks if this is deleted: an empty notice is written, and the audit's "every family has
    // a section" passes over a console whose fonts came from somewhere that is not a package.
    const dir = root({ react: "1.0.0" }, {});
    expect(() => fontLicenceText(dir)).toThrow(/bundles no font package/);
  });

  test("the plugin emits the notice at the fixed address the audit and the install read", () => {
    // What breaks if this is deleted: the file is written under a hashed name, or from the working
    // directory rather than the project root, and the audit finds no notice for any font.
    const dir = root({ "@fontsource/alpha": "1.0.0" }, { "@fontsource/alpha": OFL_TEXT });
    const plugin = fontLicences();
    plugin.configResolved({ root: dir });
    const emitted: { type: string; fileName: string; source: string }[] = [];
    plugin.generateBundle.call({ emitFile: (file: (typeof emitted)[number]) => emitted.push(file) });
    expect(FONT_LICENCES_FILE).toBe("font-licences.txt");
    expect(emitted).toEqual([{ type: "asset", fileName: "font-licences.txt", source: fontLicenceText(dir) }]);
  });

  test("the build configuration runs the plugin", () => {
    // What breaks if this is deleted: the plugin is written and tested and the build never calls
    // it, so every bundle ships fonts with no notice and only the CI audit says so.
    expect(readConsoleFile("vite.config.ts")).toMatch(/plugins:\s*\[[^\]]*\bfontLicences\(\)[^\]]*\]/);
  });
});
