/**
 * The console's language, dates and figures: that its formatters write what the Python ones write,
 * that English stands when nothing is served, and that a served language is drawn and can be chosen.
 *
 * The cases are `tests/unit/test_console_locale.py`'s own output, committed as a fixture and held
 * to the Python functions by that file, so a browser formatter that drifts from `brain.locale.format_*`
 * is a red build here and not a date written two ways on one page.
 *
 * Task ids: M35.1.1.1, M35.1.1.2
 */

import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { readConsoleFile } from "./support/repo";
import {
  chosen,
  ENGLISH_RULES,
  fill,
  formatDate,
  formatDay,
  formatMoney,
  formatNumber,
  formatTimestamp,
  msg,
  readLocales,
  rules,
  unsetCurrency,
  type LocaleRules,
  type ServedLocales,
} from "../src/locale";

interface Case {
  readonly kind: "date" | "timestamp" | "number" | "money";
  readonly rules: LocaleRules;
  readonly input: Record<string, unknown>;
  readonly expected: string;
}

const fixture = JSON.parse(readConsoleFile("tests/fixtures/console-locale.json")) as {
  cases: Case[];
  served: ServedLocales;
};

function written(one: Case): string {
  switch (one.kind) {
    case "date":
      return formatDate(one.input as { year: number; month: number; day: number }, one.rules);
    case "timestamp":
      return formatTimestamp(String(one.input.iso), one.rules, String(one.input.zone));
    case "number":
      return formatNumber(String(one.input.value), one.rules);
    case "money":
      return formatMoney(String(one.input.value), String(one.input.code), one.rules);
  }
}

describe("the browser writes what the Python functions write", () => {
  test("every case the Python side wrote down comes out the same here", () => {
    // What breaks if this is deleted: a date, a time or a figure is written one way in an API
    // answer and another on a page, and the order a reader learns to trust is the wrong one.
    const differing = fixture.cases.filter((one) => written(one) !== one.expected);
    expect(differing.map((one) => [one.kind, one.input, written(one), one.expected])).toEqual([]);
    expect(fixture.cases.length).toBeGreaterThan(60);
  });

  test("a date is written in the order its rules say and not the browser's region", () => {
    // What breaks if this is deleted: the order is read from the browser, and 08/09 is the eighth of
    // September for one reader and the ninth of August for the next.
    const day = { year: 2026, month: 9, day: 8 };
    const dayFirst: LocaleRules = { ...ENGLISH_RULES, dateOrder: "dmy", dateMarks: [".", ".", ""] };

    expect(formatDate(day, ENGLISH_RULES)).toBe("2026-09-08");
    expect(formatDate(day, dayFirst)).toBe("08.09.2026");
  });

  test("a moment is written on the clock of the install's zone, daylight saving included", () => {
    // What breaks if this is deleted: a timestamp is shown in the viewer's zone, or an hour out
    // for half of every year.
    expect(formatTimestamp("2026-07-15T03:05:00Z", ENGLISH_RULES, "America/New_York")).toBe("2026-07-14 23:05");
    expect(formatTimestamp("2026-01-15T03:05:00Z", ENGLISH_RULES, "America/New_York")).toBe("2026-01-14 22:05");
    expect(formatDay("2026-09-08T23:59:00Z", ENGLISH_RULES, "Asia/Singapore")).toBe("2026-09-09");
  });

  test("a clock that reports midnight as hour 24 is written as 00", () => {
    // What breaks if this is deleted: an engine that says 24 for midnight writes "2026-09-09 24:00",
    // a time that does not exist, for every moment in the first hour of the day.
    const real = Intl.DateTimeFormat;
    const parts = [
      { type: "year", value: "2026" },
      { type: "month", value: "9" },
      { type: "day", value: "9" },
      { type: "literal", value: ", " },
      { type: "hour", value: "24" },
      { type: "minute", value: "5" },
    ];
    class Midnight {
      formatToParts(): typeof parts {
        return parts;
      }
    }
    vi.stubGlobal("Intl", { ...Intl, DateTimeFormat: Midnight });
    try {
      expect(formatTimestamp("2026-09-09T00:05:00Z", ENGLISH_RULES, "UTC")).toBe("2026-09-09 00:05");
    } finally {
      vi.unstubAllGlobals();
      expect(Intl.DateTimeFormat).toBe(real);
    }
  });

  test("a value that is not a moment or a figure is shown as it came and never throws", () => {
    // What breaks if this is deleted: one malformed row throws while a list is being drawn and the
    // page is blank, or a figure is invented where the API sent none.
    expect(formatTimestamp("")).toBe("");
    expect(formatTimestamp("not a date")).toBe("not a date");
    expect(formatNumber("12abc")).toBe("12abc");
    expect(formatNumber(Number.NaN)).toBe("NaN");
  });

  test("money carries a code and never a symbol, and an unset currency is named as such", () => {
    // What breaks if this is deleted: a sign the console invented stands for money nobody named.
    expect(formatMoney("1234.5", "SGD", ENGLISH_RULES)).toBe("1,234.5 SGD");
    expect(formatMoney("1234.5", "dollars", ENGLISH_RULES)).toBe("1,234.5");
    expect(unsetCurrency("XXX")).toBe(true);
    expect(unsetCurrency("SGD")).toBe(false);
  });
});

describe("what the console draws when nothing is served", () => {
  test("English stands, with the English rules, UTC and no currency", () => {
    // What breaks if this is deleted: a document that fails to load leaves the console blank or in
    // a language nobody chose, and every test that names a constant reads different words.
    expect(msg("console.nothing.at_all", "Plain English")).toBe("Plain English");
    expect(rules).toEqual(ENGLISH_RULES);
  });

  test("a sentence's blanks are filled by name and an unknown name is left as written", () => {
    // What breaks if this is deleted: a translation with a differently spelled blank renders a
    // sentence with a word missing and nothing on the page says so.
    expect(fill("{spent} of {ceiling}", { spent: "1", ceiling: "2" })).toBe("1 of 2");
    expect(fill("{spent} of {ceiling}", { spent: "1" })).toBe("1 of {ceiling}");
  });
});

describe("the served document", () => {
  test("is read only when it has languages and each has the shape the rules need", () => {
    // What breaks if this is deleted: half a document is applied, and a date is written with marks
    // that were never sent.
    expect(readLocales(undefined)).toBeNull();
    expect(readLocales({ default: "en", locales: [] })).toBeNull();
    expect(readLocales({ default: "en", locales: [{ tag: "en", dateMarks: ["-", "-"] }] })).toBeNull();
    const read = readLocales(fixture.served);
    expect(read?.locales.map((one) => one.tag)).toEqual(["en", "zh-Hans"]);
    expect(Object.keys(read?.locales[1]?.messages ?? {}).length).toBeGreaterThan(90);
  });

  test("a zone or a currency that is not usable is replaced by the unset one", () => {
    // What breaks if this is deleted: a bad currency is printed beside every figure.
    const read = readLocales({ ...fixture.served, timeZone: "", currency: "dollars" });
    expect(read?.timeZone).toBe("UTC");
    expect(read?.currency).toBe("XXX");
  });

  test("a person's choice wins when the install offers it, and the default stands when it does not", () => {
    // What breaks if this is deleted: a stale choice of a language the install withdrew draws the
    // console in a language it no longer carries, or the choice is ignored.
    const served = readLocales(fixture.served);
    expect(chosen(served, "zh-hans")?.tag).toBe("zh-Hans");
    expect(chosen(served, "fr")?.tag).toBe("en");
    expect(chosen(served, "")?.tag).toBe("en");
    expect(chosen(null, "zh-Hans")).toBeNull();
  });

  test("the document's named default is used when the choice is not offered, wherever it is listed", () => {
    // What breaks if this is deleted: the language that happens to be listed first is drawn for a
    // person with no choice, and the install's stated default is ignored.
    const served = readLocales({ ...fixture.served, default: "zh-Hans" });
    expect(chosen(served, "")?.tag).toBe("zh-Hans");
    expect(chosen(served, "fr")?.tag).toBe("zh-Hans");
    expect(chosen(served, "en")?.tag).toBe("en");
  });
});

describe("a served language is drawn", () => {
  beforeEach(() => {
    vi.resetModules();
    window.localStorage.clear();
    (globalThis as Record<string, unknown>).__BRAIN_CONFIG__ = { locale: fixture.served };
  });
  afterEach(() => {
    delete (globalThis as Record<string, unknown>).__BRAIN_CONFIG__;
    window.localStorage.clear();
    document.documentElement.removeAttribute("lang");
    document.documentElement.removeAttribute("dir");
    vi.resetModules();
  });

  test("the sentences, the date marks and the page's language follow the person's choice", async () => {
    // What breaks if this is deleted: the choice is kept and nothing is drawn in it, or a screen
    // reader pronounces Chinese words in English.
    window.localStorage.setItem("brain.locale", "zh-Hans");
    const locale = await import("../src/locale");
    const chinese = fixture.served.locales[1]?.messages ?? {};

    expect(locale.msg("console.approvals.approve_label", "Approve")).toBe(chinese["console.approvals.approve_label"]);
    expect(locale.msg("console.approvals.approve_label", "Approve")).not.toBe("Approve");
    expect(locale.formatDate({ year: 2026, month: 9, day: 8 })).toBe("2026年09月08日");
    expect(document.documentElement.lang).toBe("zh-Hans");
    expect(document.documentElement.dir).toBe("ltr");
  });

  test("with no choice the install's first language is drawn, and it is English here", async () => {
    // What breaks if this is deleted: the console opens in Chinese for a person who never asked.
    const locale = await import("../src/locale");

    expect(locale.msg("console.approvals.approve_label", "Approve")).toBe("Approve");
    expect(locale.activeTag).toBe("en");
    expect(locale.offered.map((one) => one.tag)).toEqual(["en", "zh-Hans"]);
  });

  test("choosing a language keeps it and reads the page again", async () => {
    // What breaks if this is deleted: the switch changes nothing until the person reloads by hand,
    // or changes the words under a mounted page and leaves half of it in each language.
    const reload = vi.fn();
    vi.stubGlobal("location", { ...window.location, reload });
    const locale = await import("../src/locale");

    locale.chooseLocale("zh-Hans");

    expect(window.localStorage.getItem("brain.locale")).toBe("zh-Hans");
    expect(reload).toHaveBeenCalledTimes(1);
    vi.unstubAllGlobals();
  });
});
