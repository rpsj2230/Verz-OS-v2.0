/**
 * The install's accent, put where `tokens.css` reads it.
 *
 * **Nothing here decides a colour.** The six values were derived on the server by
 * `brain.locale.accent_set` from `INSTALL_ACCENT_COLOUR` and measured there against every surface
 * they are drawn on, in both themes, and they arrive through `/api/console.js` like the issuer does.
 * This module copies them onto the root element as the `--install-accent-*` custom properties that
 * `tokens.css` builds `--brand`, `--brand-ink`, `--acc-text` and `--acc-wash` from, and it does
 * nothing else. A browser-side derivation was the spike's shape and was rejected: it would be a
 * second copy of the contrast arithmetic, and the copy in the browser is the one no test in the
 * suite that gates a deploy can see.
 *
 * **Through the style object, not a `<style>` element.** A Content-Security-Policy without
 * `'unsafe-inline'` in `style-src` refuses an inserted stylesheet and does not govern the CSS
 * object model, so setting properties this way keeps working under the stricter policy if the
 * console ever gets one.
 *
 * **None removes all six.** The fallback in `tokens.css` is the design's own ink, which reads, so a
 * console sent no accent, or one it could not read, draws in that rather than in whatever a previous
 * configuration left on the element.
 *
 * Task ids: M27.10.4
 */

import { INSTALL_ACCENT_KEYS, type InstallAccent } from "../config";

/** The custom property each served value is written to. `tokens.css` reads exactly these. */
export const INSTALL_ACCENT_PROPERTIES: Readonly<Record<keyof InstallAccent, string>> = {
  fill: "--install-accent-fill",
  onFill: "--install-accent-on-fill",
  textLight: "--install-accent-text-light",
  textDark: "--install-accent-text-dark",
  washLight: "--install-accent-wash-light",
  washDark: "--install-accent-wash-dark",
};

export function applyInstallAccent(
  accent: InstallAccent | null,
  root: HTMLElement = globalThis.document.documentElement,
): void {
  for (const key of INSTALL_ACCENT_KEYS) {
    const property = INSTALL_ACCENT_PROPERTIES[key];
    if (accent === null) {
      root.style.removeProperty(property);
    } else {
      root.style.setProperty(property, accent[key]);
    }
  }
}
