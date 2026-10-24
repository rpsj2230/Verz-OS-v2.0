/**
 * The language, dates and figures the console draws, as the install set them (M35.1.1.1, M35.1.1.2).
 *
 * **The rules come from the server and are applied here.** `brain.console_static.served_locale`
 * sends each enabled language's rules (`brain.locale.LocaleRules`) and the console's catalogue
 * (`brain.console_messages`), the install's time zone and its currency, in the same blocking
 * document the install's names and accent arrive in. Nothing is decided here: the functions below
 * are `brain.locale.format_date`, `format_timestamp`, `format_number` and `format_money` written
 * once more for a browser, and `tests/locale.test.ts` holds them to the cases
 * `tests/unit/test_console_locale.py` makes the Python ones produce. A date on a page and the same
 * date in an API answer are therefore the same characters, which is the point of the unambiguous
 * order the product ships.
 *
 * **English is the default and needs nothing served.** `msg(key, english)` returns the English it
 * was given unless the chosen language has an entry for the key, so every page and every test that
 * names a constant renders what it always rendered, and a document that fails to load leaves the
 * console in English and not blank. The default language of an install is its first enabled
 * locale, which is English unless `INSTALL_LOCALES` says otherwise.
 *
 * **A person's choice is kept in this browser, as their theme is.** It is a property of the
 * screen and not of the person's access, so it is not an API call and it holds no token. Changing
 * it reloads the page, because the words are looked up when a module is first read: the constants
 * the pages and their tests share are fixed at that moment, and a language that changed under a
 * mounted page would leave half of it in each.
 *
 * Rejected: a context provider with hooks for every string. The pages draw their words from
 * exported constants that their tests import by name, so a hook would have meant changing every
 * page and every test to move one word. Rejected: `Intl` for the date and the number. It writes
 * what a browser's region writes, which is the day-first or month-first ambiguity
 * `brain.locale.A_DATE_THAT_CAN_BE_READ_TWO_WAYS_WILL_BE` exists to refuse; `Intl` is used only to
 * read the parts of a moment in a zone, which is a fact and not a style.
 *
 * Task ids: M35.1.1.1, M35.1.1.2
 */

import { CONFIG_GLOBAL } from "../configGlobal";

/** How one language writes a date and a figure, as `brain.locale.LocaleRules` states it. */
export interface LocaleRules {
  readonly tag: string;
  readonly endonym: string;
  readonly direction: "ltr" | "rtl";
  /** The order the three parts of a date are written in. */
  readonly dateOrder: "ymd" | "dmy" | "mdy";
  /** What follows each part, in the order written. */
  readonly dateMarks: readonly [string, string, string];
  readonly decimalPoint: string;
  readonly groupSeparator: string;
  readonly groupSize: number;
}

/** One enabled language: its rules and the console's sentences in it. */
export interface ServedLocale extends LocaleRules {
  readonly messages: Readonly<Record<string, string>>;
}

/** What the document carries. */
export interface ServedLocales {
  readonly default: string;
  readonly timeZone: string;
  readonly currency: string;
  readonly locales: readonly ServedLocale[];
}

/** Where the person's choice is kept. A property of the screen, like the theme. */
export const LOCALE_STORAGE_KEY = "brain.locale";

/** The rules English has when nothing is served: `brain.locale.SHIPPED`'s first entry. */
export const ENGLISH_RULES: LocaleRules = Object.freeze<LocaleRules>({
  tag: "en",
  endonym: "English",
  direction: "ltr",
  dateOrder: "ymd",
  dateMarks: ["-", "-", ""] as const,
  decimalPoint: ".",
  groupSeparator: ",",
  groupSize: 3,
});

/** UTC is nobody's local time, so an install that chose no zone shows something visibly unset. */
const UNSET_ZONE = "UTC";
/** The ISO 4217 code meaning no currency, as `brain.locale.NO_CURRENCY_CODE`. */
export const NO_CURRENCY = "XXX";

const CODE = /^[A-Z]{3}$/;
const PLAIN_NUMBER = /^-?\d+(?:\.\d+)?$/;

function isRules(value: unknown): value is ServedLocale {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const one = value as Record<string, unknown>;
  const marks = one.dateMarks;
  return (
    typeof one.tag === "string" &&
    typeof one.endonym === "string" &&
    (one.direction === "ltr" || one.direction === "rtl") &&
    (one.dateOrder === "ymd" || one.dateOrder === "dmy" || one.dateOrder === "mdy") &&
    Array.isArray(marks) &&
    marks.length === 3 &&
    marks.every((mark) => typeof mark === "string") &&
    typeof one.decimalPoint === "string" &&
    typeof one.groupSeparator === "string" &&
    typeof one.groupSize === "number" &&
    one.groupSize >= 2 &&
    typeof one.messages === "object" &&
    one.messages !== null
  );
}

/** The served document's locale block, or nothing when it is absent or does not have the shape. */
export function readLocales(value: unknown): ServedLocales | null {
  if (typeof value !== "object" || value === null) {
    return null;
  }
  const given = value as Record<string, unknown>;
  const locales = Array.isArray(given.locales) ? given.locales.filter(isRules) : [];
  if (locales.length === 0 || typeof given.default !== "string") {
    return null;
  }
  return Object.freeze({
    default: given.default,
    timeZone: typeof given.timeZone === "string" && given.timeZone !== "" ? given.timeZone : UNSET_ZONE,
    currency:
      typeof given.currency === "string" && CODE.test(given.currency) ? given.currency : NO_CURRENCY,
    locales: Object.freeze(locales),
  });
}

function servedLocales(): ServedLocales | null {
  const document_ = (globalThis as Record<string, unknown>)[CONFIG_GLOBAL];
  if (typeof document_ !== "object" || document_ === null) {
    return null;
  }
  return readLocales((document_ as Record<string, unknown>).locale);
}

function storedChoice(): string {
  try {
    return globalThis.localStorage?.getItem(LOCALE_STORAGE_KEY) ?? "";
  } catch {
    // Storage can throw (a private window, blocked site data); the default language stands.
    return "";
  }
}

/** The language this page is drawn in: the person's choice if the install offers it, else its default. */
export function chosen(served: ServedLocales | null, choice: string): ServedLocale | null {
  if (served === null) {
    return null;
  }
  const wanted = choice.trim().toLowerCase();
  return (
    served.locales.find((one) => one.tag.toLowerCase() === wanted) ??
    served.locales.find((one) => one.tag === served.default) ??
    served.locales[0] ??
    null
  );
}

const served = servedLocales();
const active = chosen(served, storedChoice());

/** The rules figures and dates are written by on this page. English when nothing is served. */
export const rules: LocaleRules = active ?? ENGLISH_RULES;

/** The install's time zone, or UTC when none was served. */
export const timeZone: string = served?.timeZone ?? UNSET_ZONE;

/** The install's currency code, or `XXX` (no currency) when none was served. */
export const currency: string = served?.currency ?? NO_CURRENCY;

/** The languages this install offers, with the names their speakers use for them. */
export const offered: readonly { readonly tag: string; readonly endonym: string }[] = (served?.locales ?? []).map(
  (one) => ({ tag: one.tag, endonym: one.endonym }),
);

/** The tag in use now, for the switcher to mark. */
export const activeTag: string = active?.tag ?? ENGLISH_RULES.tag;

if (active !== null && typeof document !== "undefined") {
  // Screen readers pronounce a page by its declared language, and the direction is the script's.
  document.documentElement.lang = active.tag;
  document.documentElement.dir = active.direction;
}

/**
 * One sentence in the language in use, or the English it was written with.
 *
 * The English is written at the call and is the same words as the catalogue's English entry,
 * which `tests/unit/test_console_messages.py` holds in both directions. A key the chosen
 * language does not have is returned in English and not as an error: the catalogue has no gaps
 * (`brain.locale.catalogue_gaps` is a red build), so this only happens for a key a page invented.
 */
export function msg(key: string, english: string): string {
  return active?.messages[key] ?? english;
}

/**
 * A sentence with its blanks filled: `{name}` is replaced by the value of that name.
 *
 * The same placeholder grammar `brain.locale.PLACEHOLDER` states, and nothing cleverer: a format
 * specifier inside a translated string would be a second grammar for a translator to get wrong. A
 * name with no value is left as written, so a mistake shows on the page instead of reading as a
 * sentence with a word missing.
 */
export function fill(template: string, values: Readonly<Record<string, string>>): string {
  return template.replace(/\{([a-z_]+)\}/g, (whole: string, name: string) => values[name] ?? whole);
}

/** Keep a person's choice and read the page again in it. */
export function chooseLocale(tag: string): void {
  try {
    globalThis.localStorage?.setItem(LOCALE_STORAGE_KEY, tag);
  } catch {
    // A blocked store means the choice cannot be kept; the page stays as it is.
    return;
  }
  globalThis.location?.reload();
}

// -------------------------------------------------------------------------------- rendering

function pad(value: number, width: number): string {
  return String(value).padStart(width, "0");
}

/** A calendar date as the locale writes it: `brain.locale.format_date`. */
export function formatDate(
  when: { readonly year: number; readonly month: number; readonly day: number },
  rule: LocaleRules = rules,
): string {
  const parts = {
    ymd: [when.year, when.month, when.day],
    dmy: [when.day, when.month, when.year],
    mdy: [when.month, when.day, when.year],
  }[rule.dateOrder];
  const widths = { ymd: [4, 2, 2], dmy: [2, 2, 4], mdy: [2, 2, 4] }[rule.dateOrder];
  return parts
    .map((part, index) => `${pad(part, widths[index] ?? 2)}${rule.dateMarks[index] ?? ""}`)
    .join("");
}

/**
 * The parts of a moment in a zone. `Intl` is asked only for the numbers on the clock there; how
 * they are written is the locale's rules and never the browser's region.
 */
function clockIn(moment: Date, zone: string): { year: number; month: number; day: number; hour: number; minute: number } {
  const found: Record<string, number> = {};
  const formatter = new Intl.DateTimeFormat("en-US", {
    timeZone: zone,
    year: "numeric",
    month: "numeric",
    day: "numeric",
    hour: "numeric",
    minute: "numeric",
    hourCycle: "h23",
  });
  for (const part of formatter.formatToParts(moment)) {
    if (part.type !== "literal") {
      found[part.type] = Number(part.value);
    }
  }
  return {
    year: found.year ?? 0,
    month: found.month ?? 0,
    day: found.day ?? 0,
    hour: (found.hour ?? 0) % 24,
    minute: found.minute ?? 0,
  };
}

/**
 * One moment, as a date and a time in a zone: `brain.locale.format_timestamp`.
 *
 * A value that is not a moment is returned as it came, which is what a row with no date shows
 * (an empty string) and what an address that is not a date shows, and never a thrown error in
 * the middle of drawing a list.
 */
export function formatTimestamp(value: string | Date, rule: LocaleRules = rules, zone: string = timeZone): string {
  const moment = value instanceof Date ? value : new Date(value);
  if (typeof value === "string" && (value === "" || Number.isNaN(moment.getTime()))) {
    return value;
  }
  if (Number.isNaN(moment.getTime())) {
    return "";
  }
  const at = clockIn(moment, zone);
  return `${formatDate(at, rule)} ${pad(at.hour, 2)}:${pad(at.minute, 2)}`;
}

/** A moment as a date only, in the zone: `brain.locale.format_date` on the local day. */
export function formatDay(value: string | Date, rule: LocaleRules = rules, zone: string = timeZone): string {
  const moment = value instanceof Date ? value : new Date(value);
  if (typeof value === "string" && (value === "" || Number.isNaN(moment.getTime()))) {
    return value;
  }
  return Number.isNaN(moment.getTime()) ? "" : formatDate(clockIn(moment, zone), rule);
}

/**
 * One figure, grouped and pointed as the locale writes it: `brain.locale.format_number`.
 *
 * The places are whatever the value carries, and a string keeps them exactly. A value that is not a
 * plain decimal is returned as it came, because inventing a figure is worse than showing the one
 * the API sent.
 */
export function formatNumber(value: number | string, rule: LocaleRules = rules): string {
  const text = typeof value === "number" ? (Number.isFinite(value) ? String(value) : "") : value.trim();
  if (!PLAIN_NUMBER.test(text)) {
    return String(value);
  }
  const negative = text.startsWith("-");
  const [whole = "", fraction = ""] = (negative ? text.slice(1) : text).split(".");
  const groups: string[] = [];
  let rest = whole;
  while (rest.length > rule.groupSize) {
    groups.unshift(rest.slice(-rule.groupSize));
    rest = rest.slice(0, -rule.groupSize);
  }
  groups.unshift(rest);
  const grouped = groups.join(rule.groupSeparator);
  const body = fraction === "" ? grouped : `${grouped}${rule.decimalPoint}${fraction}`;
  return `${negative ? "-" : ""}${body}`;
}

/**
 * A figure and the currency it is in, as a code and never a symbol: `brain.locale.format_money`.
 *
 * Exactly the Python function, so an install with no currency shows `XXX` beside the figure, as
 * the API's own text does. A page that would rather say nothing about money it cannot name
 * decides that itself (`unsetCurrency`); this does not, because two rules for the same figure
 * would drift. A code that is not three capital letters is dropped and the figure stands alone.
 */
export function formatMoney(amount: number | string, code: string = currency, rule: LocaleRules = rules): string {
  const figure = formatNumber(amount, rule);
  return CODE.test(code) ? `${figure} ${code}` : figure;
}

/** Whether the install chose no currency, so a page may leave the unit off rather than print `XXX`. */
export function unsetCurrency(code: string = currency): boolean {
  return code === NO_CURRENCY;
}
