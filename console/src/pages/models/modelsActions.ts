/**
 * What can be done in the Models and routing module, where each act is sent, and the few acts this
 * product does not offer, each with the sentence that says so.
 *
 * **Measured against the routes on 2026-09-28, and every act the owner listed works.** Adding and
 * retiring a provider, adding or replacing its key, testing it, switching it, recording its terms,
 * and adding, editing, retiring and moving a step, adding and retiring a golden question, and
 * exporting the routing configuration each have a route (`brain.provider_routes`,
 * `brain.provider_registry_routes`, `brain.routing_routes`, `brain.credential_routes`). Retiring and
 * moving a step, the export and a provider's figures were built for this page.
 *
 * **One act is not built, and its sentence says so** (`UNAVAILABLE`): renaming a provider added
 * from the console. `tests/models-module.test.tsx` reads each `retiredBy` pattern against the API
 * document, so the sentence cannot outlive the route that retires it.
 *
 * **Three acts are not offered at all, by design, and are sentences rather than controls**
 * (`NOT_OFFERED`): retiring a built-in provider, which is the product's; bringing a retired step
 * back, which would take a position the live matrix may have given to another; and resetting a
 * provider's rest after failures, which is replayed from its calls and would be a second state.
 *
 * Task ids: M27.16.1, M27.15.38, M5.3.3
 */

import { listPath, NO_QUESTION } from "../../components/listing";
import { MATRIX_API_PATH, MATRIX_PATH } from "../matrixQuery";
import { MODELS_PATH, PROVIDERS_API_PATH } from "../modelsQuery";

/** Why each act that has no route cannot be pressed, and the API path whose arrival retires it. */
export const UNAVAILABLE = Object.freeze({
  rename: {
    reason: "Coming soon: renaming a provider added here. Today, retire it and add it again with its key.",
    retiredBy: /^\/api\/v1\/models\/providers\/\{[^}]+\}\/(label|rename)$/,
  },
});

/** What this product does not offer, said where the control would otherwise be. */
export const NOT_OFFERED = Object.freeze({
  builtInRetire: "A built-in provider cannot be retired. Turn it off to stop every question going to it.",
  stepRestore: "A retired step does not come back. Add it again as a new step.",
  restReset: "A provider resting after failures comes back by itself once a test call answers.",
});

/** Where the acts this module links to are done, as console addresses. */
export const WORKS_AT = Object.freeze({
  routing: MATRIX_PATH,
  providers: MODELS_PATH,
  spend: "/spend",
  audit: "/audit",
});

/** The module's name, which is its entry in the menu. */
export const MODULE_LABEL = "Models and routing";

/** The three views of a provider, in the owner's order. The first is the bare address. */
export const PROVIDER_VIEWS = ["dashboard", "profile", "about"] as const;
export type ProviderView = (typeof PROVIDER_VIEWS)[number];

export const PROVIDER_VIEW_LABELS: Readonly<Record<ProviderView, string>> = Object.freeze({
  dashboard: "Dashboard",
  profile: "Profile",
  about: "About",
});

/** Where one provider's page is. Built from a literal prefix and an encoded slug. */
export function providerAddress(provider: string, view: string = PROVIDER_VIEWS[0]): string {
  const base = `${MODELS_PATH}/${encodeURIComponent(provider)}`;
  return view === PROVIDER_VIEWS[0] ? base : `${base}/${encodeURIComponent(view)}`;
}

/** Which view an address opens. Anything else opens the Dashboard, and says nothing. */
export function viewFor(view: string | undefined): ProviderView {
  return view === "profile" || view === "about" ? view : "dashboard";
}

/** The providers list narrowed to one provider, which is how its page asks for it. */
export function providerApiPath(provider: string): string {
  return listPath(PROVIDERS_API_PATH, { ...NO_QUESTION, filters: { provider } }, null, 1);
}

/** One provider's figures. */
export function providerStatsApiPath(provider: string): string {
  return `${PROVIDERS_API_PATH}/${encodeURIComponent(provider)}/stats`;
}

/** The ledger's entries that can name this provider: its setting subjects, found by its name. */
export function providerHistoryApiPath(provider: string): string {
  const query = new URLSearchParams({ subject_kind: "setting", q: provider, limit: "50" });
  return `/audit?${query.toString()}`;
}

/** The routing configuration, without keys. */
export const EXPORT_API_PATH = "/routing/export";

/** Where a step is retired, and moved. */
export function retireStepApiPath(rungId: string): string {
  return `${MATRIX_API_PATH}/${encodeURIComponent(rungId)}/retire`;
}

export function moveStepApiPath(rungId: string): string {
  return `${MATRIX_API_PATH}/${encodeURIComponent(rungId)}/move`;
}


/**
 * Hand a document the API wrote to the browser as a file. False when this browser cannot make one.
 * `kit/EntityTable.saveCsv`'s shape, for a Markdown register or a JSON export rather than a CSV.
 */
export function saveText(filename: string, text: string, type: string, into: Document = globalThis.document): boolean {
  if (typeof URL.createObjectURL !== "function") {
    return false;
  }
  const address = URL.createObjectURL(new Blob([text], { type }));
  const link = into.createElement("a");
  link.href = address;
  link.download = filename;
  into.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(address);
  return true;
}
