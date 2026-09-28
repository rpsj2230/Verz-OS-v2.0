/**
 * What the Features screen asks for and says. No React.
 *
 * `brain.feature_routes` answers which genuinely new features this install has switched on, and
 * `brain.ops.features` declares them. The page lists each with what switching it on does, what
 * stays true while it is off, which functions read the switch, and who last turned it. It turns
 * one only through the API, which asks for `admin:feature` over everything whatever the page drew.
 *
 * **`docs/screens.html` draws no Features screen**, so this is drawn in the register of the
 * Install screens beside it: a card per feature and the facts the screen cannot change said in
 * words under them. The three things it cannot do are fields on the answer, so each sentence
 * leaves the page in the commit that makes it false.
 *
 * Task ids: none
 */

import type { components } from "../api/schema";

export type FeaturesBody = components["schemas"]["FeaturesPage"];
export type FeatureRow = components["schemas"]["FeatureView"];

/** Where the API keeps this screen. */
export const FEATURES_API_PATH = "/install/features";

/** The console address. */
export const FEATURES_PATH = "/features";

export const FEATURES_LABEL = "Features";
export const FEATURES_LEDE =
  "New features ship switched off on every install. Switch one on here once you have read what it does.";

export const READING_FEATURES = "Reading which features are switched on.";
/** An install that declares no feature to switch, which is a sentence rather than an empty page. */
export const NO_FEATURES = "This install declares no feature that can be switched.";
export const THE_BRAIN_COULD_NOT_BE_REACHED = "The Brain could not be reached";
export const UNREADABLE_ANSWER =
  "The API answered in a shape this console does not read, so no feature is listed. The console " +
  "and the API are probably from different releases.";

export const ON = "On";
export const OFF = "Off";
export const SWITCH_ON = "Switch on";
export const SWITCH_OFF = "Switch off";
export const KEEP_IT = "Leave it as it is";
export const NEVER_CHANGED = "Never switched on this install.";
export const NO_FEATURES_TITLE = "No features to switch";

/** What is not a switch here, in one sentence, said while the API says both of its facts. */
export const NOT_SWITCHED_HERE =
  "Optional components are chosen by the install profile on the server, and plugins are not loaded yet, so neither is a switch here.";

/** The API route one switch is posted to. */
export function switchPath(name: string): string {
  return `${FEATURES_API_PATH}/${encodeURIComponent(name)}`;
}

/** The confirmation question, naming the feature and the direction. */
export function switchQuestion(row: FeatureRow): string {
  return row.on ? `Switch off "${row.title}"?` : `Switch on "${row.title}"?`;
}

/** What happens, in the product's own sentence for that direction. */
export function switchConsequence(row: FeatureRow): string {
  return row.on ? row.while_off : row.what;
}

/** What a success says. */
export function switchedSentence(row: FeatureRow): string {
  return `"${row.title}" is now switched ${row.on ? "on" : "off"}.`;
}

/** Read `brain.feature_routes.FeaturesPage`, or null for a shape this console does not read. */
export function readFeatures(payload: unknown): FeaturesBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { features?: unknown };
  if (!Array.isArray(body.features)) {
    return null;
  }
  return payload as FeaturesBody;
}

/** Read one switched feature out of a write's answer, or null. */
export function readFeature(payload: unknown): FeatureRow | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const row = payload as { name?: unknown; on?: unknown; title?: unknown };
  return typeof row.name === "string" && typeof row.on === "boolean" && typeof row.title === "string"
    ? (payload as FeatureRow)
    : null;
}
