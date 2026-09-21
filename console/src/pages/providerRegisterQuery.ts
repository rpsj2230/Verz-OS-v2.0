/**
 * The provider register as the Models screen reads and writes it.
 *
 * `brain.provider_routes` lists each provider with its registry row (processing region, residency,
 * storage location, retention and training terms, the signed agreement, the lane overrides) and
 * what it has been sent by category with counts (M5.6.4, M5.5.3, M5.1.3).
 * `brain.provider_registry_routes` records terms, adds an OpenAI-compatible provider with its key
 * (M5.7.2), retires an added one, and exports the register as one document.
 *
 * **The key is typed once, sent once and never drawn back.** It is a plain field with autocomplete
 * and spelling off, as the webhook secret's is (a password field is the sign-in boundary's, and
 * this is not a sign-in), it leaves this page only in the add request's body and is cleared when
 * the request returns, and nothing the API answers carries it.
 *
 * **Blank is judged here before a confirmation opens, and only blank.** Whether an address is
 * plain https, a name is free or an override fits the answer lane's budget is the API's to say, in
 * its own words beside the field.
 *
 * Task ids: M5.6.4, M5.7.2, M5.1.3, M5.5.3
 */

import type { FieldProblem } from "../api/errors";
import { PROVIDERS_API_PATH } from "./modelsQuery";

export const ADD_PROVIDER_API_PATH = PROVIDERS_API_PATH;
export const REGISTER_API_PATH = "/models/providers-register";

/** Where one provider's terms are recorded. */
export function termsApiPath(provider: string): string {
  return `${PROVIDERS_API_PATH}/${encodeURIComponent(provider)}/terms`;
}

/** Where one added provider is retired. */
export function retireProviderApiPath(provider: string): string {
  return `${PROVIDERS_API_PATH}/${encodeURIComponent(provider)}/retire`;
}

export interface LaneOverrideRow {
  readonly lane: string;
  readonly timeout_seconds: number | null;
  readonly attempts: number | null;
}

export interface Registered {
  readonly label: string;
  readonly kind: "builtin" | "openai_compatible";
  readonly base_url: string | null;
  readonly models: readonly string[];
  readonly processing_region: string;
  readonly residency_class: string;
  readonly storage_location: string;
  readonly retention_terms: string;
  readonly training_terms: string;
  readonly agreement_url: string | null;
  readonly lane_overrides: readonly LaneOverrideRow[];
}

export interface Disclosed {
  readonly category: string;
  readonly told: string;
  readonly attempts: number;
}

export interface RegisterRow {
  readonly provider: string;
  readonly description: string;
  readonly registered: Registered | null;
  readonly disclosed: readonly Disclosed[];
}

export interface RegisterBody {
  readonly editable: boolean;
  readonly providers: readonly RegisterRow[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function readRegistered(value: unknown): Registered | null {
  if (!isRecord(value) || typeof value["label"] !== "string") {
    return null;
  }
  const kind = value["kind"] === "openai_compatible" ? "openai_compatible" : "builtin";
  const overrides = Array.isArray(value["lane_overrides"]) ? value["lane_overrides"] : [];
  return {
    label: value["label"],
    kind,
    base_url: typeof value["base_url"] === "string" ? value["base_url"] : null,
    models: Array.isArray(value["models"])
      ? value["models"].filter((one: unknown): one is string => typeof one === "string")
      : [],
    processing_region: text(value["processing_region"]),
    residency_class: text(value["residency_class"]),
    storage_location: text(value["storage_location"]),
    retention_terms: text(value["retention_terms"]),
    training_terms: text(value["training_terms"]),
    agreement_url: typeof value["agreement_url"] === "string" ? value["agreement_url"] : null,
    lane_overrides: overrides.flatMap((one: unknown) =>
      isRecord(one) && typeof one["lane"] === "string"
        ? [
            {
              lane: one["lane"],
              timeout_seconds: typeof one["timeout_seconds"] === "number" ? one["timeout_seconds"] : null,
              attempts: typeof one["attempts"] === "number" ? one["attempts"] : null,
            },
          ]
        : [],
    ),
  };
}

/** The providers answer as the register reads it, or null when it is not one. */
export function readRegister(payload: unknown): RegisterBody | null {
  if (!isRecord(payload) || !Array.isArray(payload["providers"])) {
    return null;
  }
  return {
    editable: payload["editable"] === true,
    providers: payload["providers"].flatMap((one: unknown) => {
      if (!isRecord(one) || typeof one["provider"] !== "string") {
        return [];
      }
      const disclosed = Array.isArray(one["disclosed"]) ? one["disclosed"] : [];
      return [
        {
          provider: one["provider"],
          description: text(one["description"]),
          registered: readRegistered(one["registered"]),
          disclosed: disclosed.flatMap((entry: unknown) =>
            isRecord(entry) && typeof entry["category"] === "string" && typeof entry["attempts"] === "number"
              ? [{ category: entry["category"], told: text(entry["told"]), attempts: entry["attempts"] }]
              : [],
          ),
        },
      ];
    }),
  };
}

/** The exported register: the name to save it under and the document. */
export function readRegisterDocument(payload: unknown): { filename: string; document: string } | null {
  if (!isRecord(payload) || typeof payload["filename"] !== "string" || typeof payload["document"] !== "string") {
    return null;
  }
  return { filename: payload["filename"], document: payload["document"] };
}

// ------------------------------------------------------------------------------ the words

export const REGISTER_HEADING = "Provider register";
export const REGISTER_LEDE =
  "Where each provider processes what it is sent, what the company agreed with it, and how many " +
  "model calls carried each kind of data. Counts are calls, not people.";
export const DOWNLOAD_REGISTER = "Download the register";
export const NOT_RECORDED = "Not recorded";
export const NOTHING_SENT = "Nothing recorded";
export const RECORD_TERMS = "Record terms";
export const SAVE_TERMS = "Save these terms";
export const KEEP_TERMS = "Keep the terms as they are";
export const RETIRE_PROVIDER = "Retire";
export const KEEP_PROVIDER = "Keep the provider";
export const ADD_PROVIDER_HEADING = "Add an OpenAI-compatible provider";
export const ADD_PROVIDER = "Add this provider";
export const DO_NOT_ADD = "Do not add it";
export const ADD_PROVIDER_NOTE =
  "The address is fixed once added: to point a provider somewhere else, retire it and add it " +
  "again with its key. The key is kept in the secrets vault and never shown again.";
export const REGISTER_SAVED = "The register was saved as a file.";

export function termsQuestion(provider: string): string {
  return `Record new terms for ${provider}?`;
}

export function termsConsequence(provider: string, asked: TermsAsked): string {
  return (
    `${provider} will be recorded as processing in ${asked.processing_region} ` +
    `(${asked.residency_class.replace("_", " ")}). A region-pinned provider can answer questions ` +
    "that must stay in that region; the lane overrides apply from the next call."
  );
}

export function retireQuestion(provider: string): string {
  return `Retire ${provider}?`;
}

export const RETIRE_CONSEQUENCE =
  "Its rungs are left out of the chain from the next call, as a provider this install cannot " +
  "reach. Its key stays in the vault until it is replaced.";

export function addQuestion(asked: AddAsked): string {
  return `Add ${asked.label} (${asked.slug}) at ${asked.base_url}?`;
}

export const ADD_CONSEQUENCE =
  "Its key is written to the secrets vault first and the provider is listed here. It takes no " +
  "question until a rung names one of its models, which the Routing screen adds through the matrix gate.";

// ------------------------------------------------------------------------------ the forms

export interface TermsAsked {
  readonly processing_region: string;
  readonly residency_class: "global" | "region_pinned" | "on_prem";
  readonly storage_location: string;
  readonly retention_terms: string;
  readonly training_terms: string;
  readonly agreement_url: string | null;
  readonly lane_overrides: Record<string, { timeout_seconds?: number; attempts?: number }>;
}

export interface AddAsked {
  readonly slug: string;
  readonly label: string;
  readonly base_url: string;
  readonly models: readonly string[];
  readonly key: string;
}

export const RESIDENCY_CLASSES: readonly TermsAsked["residency_class"][] = ["global", "region_pinned", "on_prem"];

/** Model names typed one per line or separated by commas. */
export function modelNames(typed: string): string[] {
  return typed
    .split(/[\n,]/)
    .map((one) => one.trim())
    .filter((one) => one !== "");
}

/** The answer lane's override as typed: blank leaves the rung's own numbers. */
export function laneOverrides(timeout: string, attempts: string): TermsAsked["lane_overrides"] {
  const answer: { timeout_seconds?: number; attempts?: number } = {};
  if (timeout.trim() !== "") {
    answer.timeout_seconds = Number(timeout);
  }
  if (attempts.trim() !== "") {
    answer.attempts = Number(attempts);
  }
  return Object.keys(answer).length === 0 ? {} : { answer };
}

/** Terms with a blank region, as the problem a person is told beside it. */
export function blankTermsProblems(region: string): FieldProblem[] {
  return region.trim() === ""
    ? [{ field: "processing_region", code: "blank", message: "Name the region, or global when none is promised." }]
    : [];
}

/** An added provider with a blank field, as the problems a person is told beside each. */
export function blankAddProblems(slug: string, label: string, address: string, models: string, key: string): FieldProblem[] {
  const found: FieldProblem[] = [];
  if (slug.trim() === "") {
    found.push({ field: "slug", code: "blank", message: "Give the provider a short name, like acme_llm." });
  }
  if (label.trim() === "") {
    found.push({ field: "label", code: "blank", message: "Say what the provider is, as people will read it." });
  }
  if (address.trim() === "") {
    found.push({ field: "base_url", code: "blank", message: "Give the https address its interface is served at." });
  }
  if (modelNames(models).length === 0) {
    found.push({ field: "models", code: "blank", message: "List at least one model name it serves." });
  }
  if (key.trim() === "") {
    found.push({ field: "key", code: "blank", message: "Paste the key the provider issued." });
  }
  return found;
}
