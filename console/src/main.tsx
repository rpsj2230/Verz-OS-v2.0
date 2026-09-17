/**
 * The entry point: styles, theme, one root.
 *
 * The order matters in two places. `tokens.css` is imported before `app.css` because the
 * second uses the custom properties the first defines, and although the cascade does not
 * care about import order for custom property resolution, a reader does: the file that
 * defines the vocabulary comes before the file that speaks it. And `theme/tailwind.css` is
 * imported before `app.css` because it opens with the statement declaring the order of the
 * cascade layers, and the first place a layer is named is where its position is fixed: were
 * the old sheet first, `legacy` would be the lowest layer rather than the one between the
 * reset and the utilities.
 *
 * The install's accent is put on the root element before the first render for the reason the
 * theme is: a component painted once in the neutral fallback and again in the company's colour
 * is a flash on every load. `theme/accent.ts` says where the colours come from.
 *
 * `initialiseTheme` runs before the first render, and it is deliberately a second
 * application of the same value the blocking script in `index.html` already applied. That
 * script exists to avoid a flash of the wrong theme; this call exists so that the module
 * that owns the preference is the one holding it after startup, rather than the two ending
 * up with different ideas of what is selected.
 *
 * `StrictMode` is on, which double-invokes effects in development. Both places where that
 * would have caused a real problem, starting a sign-in and redeeming a code, are guarded
 * in `src/auth/session.ts` and say so.
 */

// The stylesheets come first, before any module that could import a sheet of its own, because
// the bundle keeps them in the order the module graph reaches them.
import "./theme/tokens.css";
import "./theme/tailwind.css";
import "./styles/app.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { config } from "./config";
import { applyInstallAccent } from "./theme/accent";
import { initialiseTheme } from "./theme/theme";

initialiseTheme();
applyInstallAccent(config.accent);

const container = document.getElementById("root");
if (!container) {
  // index.html and this file are the two halves of one contract. If the element is gone,
  // failing with a sentence beats React failing with a null reference from inside a
  // minified bundle.
  throw new Error('index.html has no element with id "root", so nothing can be rendered.');
}

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
