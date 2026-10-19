/**
 * Carry each bundled font's licence notice in the bundle, assembled at build time from the
 * packages the console depends on.
 *
 * **Why the build does it and nobody types a notice.** The interface fonts are `@fontsource`
 * packages under the SIL Open Font Licence 1.1, which allows bundling and redistribution on one
 * condition that matters here: the copyright notice and the licence text must accompany every copy
 * of the font software. A hand-written notice names the fonts somebody remembered; this one is
 * read from `package.json`'s dependencies, so a font added next month brings its own notice or
 * stops the build, and a font dropped takes its notice with it. The notice is the package's own
 * `LICENSE` file, never a paraphrase, because the licence is the text and not a description of it.
 *
 * **Why a file in the bundle rather than a page in the console.** The condition is about the
 * copies that leave: the bundle is the copy an install serves and a person can save. A plain text
 * file at a fixed address, served like any other file the bundle carries, is readable without the
 * console's sign-in and without a script, which a licence page behind the application is not.
 *
 * **A package with no licence text, or one that is not the Open Font Licence, stops the build.**
 * Writing "licensed under the OFL" about a package whose file says otherwise would be a false
 * notice, which is worse than none. The check on the other side is
 * `brain.ops.bundle_audit`, which fails a built bundle whose font has no section here.
 *
 * Task ids: M27.15.75
 */

import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

/** Where the notices are written, at the root of the bundle. */
export const FONT_LICENCES_FILE = "font-licences.txt";

/** The scope the interface's fonts come from. */
const SCOPE = "@fontsource/";

/** What a fontsource licence file says when it is the Open Font Licence. */
const OFL = /SIL OPEN FONT LICENSE Version 1\.1/i;

/** The `@fontsource/*` packages a manifest depends on, in a stable order. */
export function bundledFontPackages(manifest) {
  return Object.keys(manifest.dependencies ?? {})
    .filter((name) => name.startsWith(SCOPE))
    .sort();
}

/**
 * The notices text for every bundled font package under `root`, one section each. A section's first
 * line is the package name on a line of its own: `brain.ops.bundle_audit` reads those headings to
 * decide which font files are covered.
 */
export function fontLicenceText(root) {
  const manifest = JSON.parse(readFileSync(join(root, "package.json"), "utf8"));
  const packages = bundledFontPackages(manifest);
  if (packages.length === 0) {
    throw new Error("the console bundles no font package, so there is no notice to write");
  }
  const sections = packages.map((name) => {
    const file = join(root, "node_modules", name, "LICENSE");
    if (!existsSync(file)) {
      throw new Error(`${name} ships no LICENSE file, and a font may not be bundled without its notice`);
    }
    const text = readFileSync(file, "utf8").trim();
    if (!OFL.test(text)) {
      throw new Error(`${name}'s LICENSE is not the SIL Open Font Licence 1.1, which the notice below states`);
    }
    return `${name}\n${"-".repeat(name.length)}\n${text}\n`;
  });
  const lead =
    "Fonts bundled with this console, each under the SIL Open Font Licence 1.1.\n" +
    "The notice and licence of each are reproduced as its package carries them.\n";
  return `${lead}\n${sections.join("\n")}`;
}

/** The Vite plugin: emits `FONT_LICENCES_FILE` into the bundle. */
export function fontLicences() {
  let root = process.cwd();
  return {
    name: "brain:font-licences",
    configResolved(config) {
      root = config.root;
    },
    generateBundle() {
      this.emitFile({ type: "asset", fileName: FONT_LICENCES_FILE, source: fontLicenceText(root) });
    },
  };
}
