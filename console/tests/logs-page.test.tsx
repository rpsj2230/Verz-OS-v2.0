/**
 * The Logs screen: a row by its event, place, reference and exception type; a field shown as the API
 * sent it; an event whose name was not kept said in words; filters that are requests; older rows from
 * the cursor; and the sentences about what the log never keeps, each gated on the field that says so.
 *
 * Mounted on its own at its address, against a stand-in API. The shapes are read from
 * `brain.log_routes` itself, and so are the query parameters the route declares.
 *
 * Task ids: M27.8.14
 */

import { fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import {
  DEBUG_IS_NOT_KEPT,
  INFO_IS_A_SAMPLE,
  LOGS_API_PATH,
  LOGS_PATH,
  LOGS_PAGE_SIZE,
  NAME_NOT_KEPT,
  NO_ENTRIES,
  NO_MORE_ENTRIES,
  SHOW_NEWER,
  SHOW_OLDER,
  WORKER_OUTPUT_IS_NOT_KEPT,
  filtersFrom,
  logsApiPath,
} from "../src/pages/logsQuery";
import { button, json, mountPage, settled, type Answer } from "./support/pageHarness";
import { backendModelFields } from "./support/python";
import { readRepoFile } from "./support/repo";

const LIST = `GET /api/v1${LOGS_API_PATH}`;
const ROUTES = "src/brain/log_routes.py";

function entry(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    at: "2019-03-06T08:30:00Z",
    last_at: "2019-03-06T08:31:00Z",
    level: "warning",
    event: "request failed",
    origin: "brain.app:747",
    reference: "REFERENCE-SENTINEL",
    error_type: null,
    repeats: 12,
    fields: { outcome: "denied", detail: "[masked:str/medium]" },
    ...overrides,
  };
}

function page(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    start: "2019-03-05T09:00:00Z",
    end: "2019-03-06T09:00:00Z",
    items: [entry(), entry({ level: "error", event: null, origin: "brain.cache:374", error_type: "TimeoutError", repeats: 1, fields: {} })],
    next_cursor: null,
    kept_for_days: 30,
    debug_is_not_kept: true,
    info_is_a_sample: true,
    worker_output_is_not_kept: true,
    ...overrides,
  };
}

async function logsPage(answers: Record<string, Answer>) {
  return mountPage(
    LOGS_PATH,
    async () => {
      const { Logs } = await import("../src/pages/Logs");
      return <Logs />;
    },
    answers,
  );
}

describe("what the Logs screen draws", () => {
  test("a row by its event, place, reference, exception and repeats, with its fields as sent", async () => {
    // What breaks if this is deleted: a warning an administrator was told the reference of that
    // cannot be found on the page, or a field drawn differently from how the API redacted it.
    const { container } = await logsPage({ [LIST]: () => json(page()) });

    const text = container.textContent ?? "";
    expect(text).toContain("request failed");
    expect(text).toContain("brain.app:747");
    expect(text).toContain("REFERENCE-SENTINEL");
    expect(text).toContain("12 times");
    expect(text).toContain("[masked:str/medium]");
    expect(text).toContain("TimeoutError");
    expect(text).toContain(NAME_NOT_KEPT);
    expect(text).toContain(NO_MORE_ENTRIES);
    expect(text).toContain(DEBUG_IS_NOT_KEPT);
    expect(text).toContain(INFO_IS_A_SAMPLE);
    expect(text).toContain(WORKER_OUTPUT_IS_NOT_KEPT);
    expect(text).not.toMatch(/\bof \d+\b|showing/i);
  });

  test("nothing kept is a sentence, and a sentence about what is not kept leaves when the API stops sending it", async () => {
    // What breaks if this is deleted: an empty table that reads as not loaded, or a page that goes
    // on saying the worker's output is not kept after it is.
    const { container } = await logsPage({
      [LIST]: () => json(page({ items: [], worker_output_is_not_kept: false })),
    });

    expect(container.querySelectorAll("table")).toHaveLength(0);
    expect(container.textContent).toContain(NO_ENTRIES);
    expect(container.textContent).not.toContain(WORKER_OUTPUT_IS_NOT_KEPT);
  });

  test("a refusal is the API's own sentence and never an empty table", async () => {
    // What breaks if this is deleted: an administrator missing the capability is shown an empty log
    // and believes nothing went wrong.
    const { container } = await logsPage({
      [LIST]: () => json({ message: "I could not find that.", trace_id: "t-1" }, 404),
    });

    expect(container.textContent).toContain("I could not find that.");
    expect(container.textContent).not.toContain(NO_ENTRIES);
    expect(container.querySelectorAll("table")).toHaveLength(0);
  });

  test("the level, the period and a search chosen on the page are carried to the request, and a cursor fetches older rows", async () => {
    // What breaks if this is deleted: a filter that changes the address and not the request, or a
    // control that fetches the first page again.
    const { container, sent } = await logsPage({
      [LIST]: (_body, url) =>
        url.searchParams.get("cursor") === "c1"
          ? json(page({ items: [entry({ event: "older.row" })] }))
          : json(page({ next_cursor: "c1" })),
    });
    fireEvent.change(container.querySelectorAll("select")[0] as HTMLSelectElement, { target: { value: "error" } });
    await settled(container);
    fireEvent.change(container.querySelectorAll("select")[1] as HTMLSelectElement, { target: { value: "hour" } });
    await settled(container);
    fireEvent.change(container.querySelector("input[type=search]") as HTMLInputElement, { target: { value: " cache " } });
    fireEvent.submit(container.querySelector("input[type=search]")?.closest("form") as HTMLFormElement);
    await waitFor(() => {
      expect(sent.at(-1)?.path).toContain("event=cache");
    });
    await settled(container);

    const first = new URL(`https://console.test${sent.at(-1)?.path ?? ""}`);
    expect(first.searchParams.get("level")).toBe("error");
    expect(first.searchParams.get("event")).toBe("cache");
    expect(first.searchParams.has("cursor")).toBe(false);
    expect(first.searchParams.get("limit")).toBe(String(LOGS_PAGE_SIZE));
    const start = Date.parse(first.searchParams.get("start") ?? "");
    const end = Date.parse(first.searchParams.get("end") ?? "");
    expect(end - start).toBe(60 * 60 * 1000);

    fireEvent.click(button(container, SHOW_OLDER));
    await waitFor(() => {
      expect(container.textContent).toContain("older.row");
    });
    const older = new URL(`https://console.test${sent.at(-1)?.path ?? ""}`);
    expect(older.searchParams.get("cursor")).toBe("c1");
    expect(older.searchParams.get("start")).toBe(first.searchParams.get("start"));
    expect(older.searchParams.get("level")).toBe("error");
  });

  test("oldest first is carried to the request, and the control then fetches newer rows", async () => {
    // What breaks if this is deleted: an order chosen on the page that reorders nothing the route
    // reads, or a pager still labelled older while walking forward.
    const { container, sent } = await logsPage({
      [LIST]: (_body, url) =>
        url.searchParams.get("cursor") === "c1"
          ? json(page({ items: [entry({ event: "newer.row" })] }))
          : json(page({ next_cursor: "c1" })),
    });
    const order = [...container.querySelectorAll("select")].find((one) =>
      one.closest("label")?.textContent?.startsWith("Order"),
    ) as HTMLSelectElement;
    fireEvent.change(order, { target: { value: "oldest" } });
    await waitFor(() => {
      expect(sent.at(-1)?.path).toContain("order=oldest");
    });
    await settled(container);

    fireEvent.click(button(container, SHOW_NEWER));
    await waitFor(() => {
      expect(container.textContent).toContain("newer.row");
    });
    const newer = new URL(`https://console.test${sent.at(-1)?.path ?? ""}`);
    expect(newer.searchParams.get("cursor")).toBe("c1");
    expect(newer.searchParams.get("order")).toBe("oldest");
  });

  test("every parameter the page sends is one the route declares, and every field it reads is one the route sends", () => {
    // What breaks if this is deleted: a renamed parameter FastAPI discards without a word, so the
    // page shows every level while saying it shows errors; or a renamed field read as empty.
    const path = logsApiPath(filtersFrom(new URLSearchParams("level=error&event=x&period=week")), new Date(), "c1");
    const sentNames = [...new URL(`https://console.test${path}`).searchParams.keys()].sort();
    const route = readRepoFile(ROUTES);
    const signature = /async def logs\(([\s\S]*?)\) -> LogPage:/.exec(route)?.[1] ?? "";
    for (const name of sentNames) {
      expect(signature).toMatch(new RegExp(`\\b${name}:`));
    }
    expect(LOGS_PAGE_SIZE).toBeLessThanOrEqual(Number(/^MAX_PAGE: Final = (\d+)$/m.exec(readRepoFile("src/brain/ops/log_store.py"))?.[1]));

    const body = page();
    expect(Object.keys(body).sort()).toEqual(backendModelFields(ROUTES, "LogPage").sort());
    const row = (body.items as Record<string, unknown>[])[0] ?? {};
    expect(Object.keys(row).sort()).toEqual(backendModelFields(ROUTES, "LogEntryView").sort());
  });
});
