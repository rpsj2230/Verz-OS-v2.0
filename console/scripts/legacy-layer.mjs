/**
 * Put every stylesheet the console had before the component layer into the `legacy` cascade layer,
 * at build time, without editing one of them.
 *
 * **Why the build does it rather than the sheets.** The obvious change is to wrap each file's
 * contents in `@layer legacy { ... }`. Three things decide against it. The tests that hold the
 * old pages to a phone's width and to their colours read these files from disk through
 * `tests/support/css.ts` and `tests/support/cascade.ts`, which report a rule's innermost at-rule,
 * so every top-level rule would come back sitting inside `@layer legacy` and the cascade reader
 * would treat it as a media query that never matches: the phone tests would pass for the wrong
 * reason or fail for one unrelated to layout. Two of the sheets are imported by page and
 * component modules rather than by `main.tsx`, so an `@import ... layer(legacy)` in the entry
 * stylesheet would pull them into the first response and still leave the page's own import
 * unlayered. And the canvas library's `base.css` is not ours to edit.
 *
 * **Why these four and not a rule about a directory.** The list is every sheet that was unlayered
 * when `theme/tailwind.css` arrived, and the property that keeps an old page unchanged is that all
 * of them move into the same layer together, so their order among themselves is exactly what it
 * was. A sheet added to `src/styles/` later is not automatically old: a new page is styled with
 * class names and has no sheet. `tests/tailwind-foundation.test.ts` fails when a stylesheet
 * appears under `src/` that is neither in this list nor one of the component layer's own, so
 * adding one is a decision somebody makes rather than a default.
 *
 * Task ids: M27.10.2
 */

/** The cascade layer the old sheets are moved into. Declared in order in `src/theme/tailwind.css`. */
export const LEGACY_LAYER = "legacy";

/** Every stylesheet the console had before the component layer, as a path suffix of its module id. */
export const LEGACY_SHEETS = [
  "/src/styles/app.css",
  "/src/styles/approvals.css",
  "/src/styles/agent-workspace.css",
  "/node_modules/@xyflow/react/dist/base.css",
];

/** Forward slashes and no query string, so a Windows path and a Vite id compare alike. */
export function normalisedId(id) {
  return id.split("?")[0].split("\\").join("/");
}

/** Whether a module id is one of the old sheets. */
export function isLegacySheet(id) {
  const path = normalisedId(id);
  return LEGACY_SHEETS.some((suffix) => path.endsWith(suffix));
}

/** The sheet's text inside the legacy layer. */
export function inLegacyLayer(css) {
  return `@layer ${LEGACY_LAYER} {\n${css}\n}\n`;
}

/**
 * The Vite plugin. `enforce: "pre"` so the wrapping happens before Vite's own CSS handling
 * compiles and bundles the sheet, and before Tailwind's plugin looks at it.
 */
export function legacyLayer() {
  return {
    name: "brain:legacy-layer",
    enforce: "pre",
    transform(code, id) {
      if (!isLegacySheet(id)) {
        return null;
      }
      return { code: inLegacyLayer(code), map: null };
    },
  };
}
