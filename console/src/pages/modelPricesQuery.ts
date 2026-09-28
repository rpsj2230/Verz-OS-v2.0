/**
 * What a million tokens cost on each model, read and set on the Models screen (M27.12.5).
 *
 * `brain.provider_routes` serves `GET /models/prices` and writes `PUT /models/prices`, and
 * `brain.ops.usage_store` costs every model call at these prices when its request finishes. A call
 * to a model with no price, or a price in another currency than the install's, is not costed, so
 * the card says of every model whether its calls are, in words.
 *
 * **A price is typed in whole currency per million tokens and sent in minor units.** Providers quote
 * "3.00 per million input tokens", and the API counts money in minor units
 * (`brain.ops.budgets.MONEY_IS_COUNTED_IN_MINOR_UNITS`). The shift is two decimal places, the
 * console's own rule for money (`spendQuery.majorUnits`), done on the digits as text so that 0.075
 * stays 0.075 and never becomes the nearest binary fraction. See `A_PRICE_IS_SHIFTED_AS_TEXT`.
 *
 * **Blank is judged here and the rest is the API's.** A form sent blank says what to fill in before
 * anything is sent; a figure the API refuses (negative, too many places, too large) comes back in
 * its own sentences.
 *
 * Task ids: M27.12.5
 */

import type { FieldProblem } from "../api/errors";
import { providerName } from "./modelsQuery";
import { UNSET_CURRENCY } from "./spendQuery";

/** Why a price is converted on its digits rather than multiplied. */
export const A_PRICE_IS_SHIFTED_AS_TEXT =
  "A price such as 0.075 is not a binary fraction, and 0.075 * 100 is 7.499999999999999 in " +
  "a browser. Moving the decimal point two places on the digits is exact, so the price the API " +
  "keeps is the one that was typed.";

export const PRICES_API_PATH = "/models/prices";

export interface ModelPriceRow {
  readonly provider: string;
  readonly model: string;
  readonly on_ladder: boolean;
  readonly input_minor_per_million: string | null;
  readonly output_minor_per_million: string | null;
  readonly currency: string | null;
  readonly costed: boolean;
}

export interface PricesBody {
  readonly currency: string;
  readonly models: readonly ModelPriceRow[];
}

function text(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

/** The API's answer, or null for one this page cannot read. */
export function readPrices(payload: unknown): PricesBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { currency?: unknown; models?: unknown };
  if (typeof body.currency !== "string" || !Array.isArray(body.models)) {
    return null;
  }
  const models: ModelPriceRow[] = [];
  for (const one of body.models as unknown[]) {
    if (typeof one !== "object" || one === null) {
      return null;
    }
    const row = one as Record<string, unknown>;
    const provider = text(row["provider"]);
    const model = text(row["model"]);
    if (provider === null || model === null) {
      return null;
    }
    models.push({
      provider,
      model,
      on_ladder: row["on_ladder"] === true,
      input_minor_per_million: text(row["input_minor_per_million"]),
      output_minor_per_million: text(row["output_minor_per_million"]),
      currency: text(row["currency"]),
      costed: row["costed"] === true,
    });
  }
  return { currency: body.currency, models };
}

const DECIMAL = /^(\d+)(?:\.(\d+))?$/;

function tidy(whole: string, fraction: string): string {
  const head = whole.replace(/^0+(?=\d)/, "");
  const tail = fraction.replace(/0+$/, "");
  return tail === "" ? head : `${head}.${tail}`;
}

/** Whole currency as minor units, two places to the right, or null for text that is no figure. */
export function minorFromMajor(typed: string): string | null {
  const found = DECIMAL.exec(typed.trim());
  if (found === null) {
    return null;
  }
  const fraction = (found[2] ?? "").padEnd(2, "0");
  return tidy(`${found[1] ?? "0"}${fraction.slice(0, 2)}`, fraction.slice(2));
}

/** Minor units as whole currency, two places to the left. The API's own text goes in. */
export function majorFromMinor(minor: string): string {
  const found = DECIMAL.exec(minor.trim());
  if (found === null) {
    return minor;
  }
  const whole = (found[1] ?? "0").padStart(3, "0");
  const fraction = `${whole.slice(-2)}${found[2] ?? ""}`;
  const shown = tidy(whole.slice(0, -2), fraction);
  // Two places at least, as every other amount on the console is drawn.
  const [head, tail = ""] = shown.split(".");
  return `${head ?? "0"}.${tail.padEnd(2, "0")}`;
}

export const PRICES_HEADING = "Prices";
export const SET_PRICE = "Set price";
export const SAVE_PRICE = "Save price";
export const KEEP_PRICE = "Keep it as it is";
export const INPUT_LABEL = "Per million tokens sent";
export const OUTPUT_LABEL = "Per million tokens received";
export const NO_MODELS = "No step on the failover matrix names a model yet, and no model has a price.";
export const COSTED = "Costed";
export const NOT_PRICED = "No price, so its calls are not costed";
export const NOT_IN_USE = "Not used by any step";
export const BLANK_PRICE = "Give a price, such as 3.00, or 0 for a model that costs nothing per token.";
export const NOT_A_PRICE = "Give the price as a number, such as 3.00 or 0.075.";

/** What the card says first: the currency, and what a missing price means. */
export function pricesLede(currency: string): string {
  const unit = currency === UNSET_CURRENCY ? "the install's currency" : currency;
  return (
    `What a million tokens cost on each model, in ${unit}, from your provider's price list. Each ` +
    "call's cost is recorded at these prices. A call to a model with no price is not costed."
  );
}

/** Said instead of the controls while the install has no currency to price in. */
export const CHOOSE_A_CURRENCY_FIRST =
  "Choose the install's currency on Install, Settings before setting a price.";

/** Whether a model's calls are costed, in words. */
export function costedWords(row: ModelPriceRow, currency: string): string {
  if (row.costed) {
    return COSTED;
  }
  if (row.currency !== null && row.currency !== currency) {
    return `Priced in ${row.currency}, so not costed until it is priced in ${currency}`;
  }
  return NOT_PRICED;
}

/** One price in whole currency, or a dash for none. */
export function priceWords(minor: string | null): string {
  return minor === null ? "-" : majorFromMinor(minor);
}

/** The model as a person reads it: the provider's name, then the model. */
export function modelWords(row: ModelPriceRow): string {
  return `${providerName(row.provider)} ${row.model}`;
}

/** Blank or non-numeric fields, said beside their fields before anything is sent. */
export function priceProblems(input: string, output: string): FieldProblem[] {
  const found: FieldProblem[] = [];
  for (const [field, typed] of [
    ["input_minor_per_million", input],
    ["output_minor_per_million", output],
  ] as const) {
    if (typed.trim() === "") {
      found.push({ field, code: "blank", message: BLANK_PRICE });
    } else if (minorFromMajor(typed) === null) {
      found.push({ field, code: "not_a_number", message: NOT_A_PRICE });
    }
  }
  return found;
}

/** The body `PUT /models/prices` takes: the model and its two prices in minor units. */
export function priceBody(
  row: ModelPriceRow,
  input: string,
  output: string,
): {
  provider: string;
  model: string;
  input_minor_per_million: string;
  output_minor_per_million: string;
} {
  return {
    provider: row.provider,
    model: row.model,
    input_minor_per_million: minorFromMajor(input) ?? input,
    output_minor_per_million: minorFromMajor(output) ?? output,
  };
}

/** Said once a price is saved. */
export function pricedSentence(row: ModelPriceRow): string {
  return `${modelWords(row)} is priced, and its calls are costed from the next one.`;
}
