/**
 * What the plugin panel on the Features page asks for and says. No React.
 *
 * `brain.plugin_routes` answers which extension points exist and which plugins this install has
 * recorded, and moves a recorded plugin between its states. The panel lists both and turns a
 * state only through the API, which asks for `admin:plugin` over everything whatever the page
 * drew. Nothing here decides who may: a reader the API refuses sees the API's refusal.
 *
 * **A recorded plugin is not a loaded one, and the panel says so only while the API does.** The
 * sentence is a field on the answer (`no_plugin_is_loaded`), so it leaves the page in the commit
 * that makes it false.
 *
 * Task ids: M29.2.1, M29.2.2, M29.2.3
 */

import type { components } from "../api/schema";

export type PluginsBody = components["schemas"]["PluginsPage"];
export type PluginRow = components["schemas"]["PluginView"];
export type PointRow = components["schemas"]["PointView"];

/** Where the API keeps this panel. */
export const PLUGINS_API_PATH = "/install/plugins";

export const PLUGINS_TITLE = "Plugins";
export const READING_PLUGINS = "Reading which plugins are recorded.";
export const NO_PLUGINS = "No plugin is recorded on this install.";
export const NO_PLUGINS_TITLE = "No plugins recorded";
export const UNREADABLE_PLUGINS =
  "The API answered in a shape this console does not read, so no plugin is listed. The console " +
  "and the API are probably from different releases.";
export const NOT_LOADED =
  "A plugin recorded here is not loaded or run: the record is what a runner will read.";
export const SWITCHED_OFF =
  "Recording plugins is switched off. Switch on Record plugins on this install in the list above to add, enable, upgrade or return one. A plugin already recorded can still be switched off and removed.";

export const MANIFEST_LABEL = "Manifest (JSON)";
export const RECORD = "Record plugin";
export const NOT_JSON = "That is not JSON, so nothing was sent.";
export const NOT_CHANGED = "The plugin was not changed";
export const POINTS_HEADING = "Where a plugin may plug in";

/** The acts a plugin in a state offers. Enabling is a separate act from recording. */
export type Verb = "enable" | "disable" | "remove";

export const VERB_LABEL: Readonly<Record<Verb, string>> = {
  enable: "Switch on",
  disable: "Switch off",
  remove: "Remove",
};

/** Which acts a state offers: a plugin is removed only once it is off. */
export function verbsFor(state: string): readonly Verb[] {
  switch (state) {
    case "installed":
      return ["enable"];
    case "enabled":
      return ["disable"];
    case "disabled":
      return ["enable", "remove"];
    default:
      return [];
  }
}

/** The API route one act is posted to. */
export function verbPath(pluginId: string, verb: Verb): string {
  return `${PLUGINS_API_PATH}/${encodeURIComponent(pluginId)}/${verb}`;
}

/** The sentence an act ends with, in the words the panel uses for the state. */
export function movedSentence(pluginId: string, verb: Verb): string {
  const done: Readonly<Record<Verb, string>> = {
    enable: "switched on",
    disable: "switched off",
    remove: "removed",
  };
  return `"${pluginId}" is now ${done[verb]}.`;
}

/** Read `brain.plugin_routes.PluginsPage`, or null for a shape this console does not read. */
export function readPlugins(payload: unknown): PluginsBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { points?: unknown; plugins?: unknown };
  if (!Array.isArray(body.points) || !Array.isArray(body.plugins)) {
    return null;
  }
  return payload as PluginsBody;
}

/** The manifest a person pasted, or null when it is not a JSON object. */
export function readManifest(text: string): Record<string, unknown> | null {
  try {
    const parsed: unknown = JSON.parse(text);
    return typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}
