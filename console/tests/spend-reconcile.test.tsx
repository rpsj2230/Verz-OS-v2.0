/**
 * Metered spend held against a provider's invoice, under the Spend report: drawn from what the API
 * sent, asked only when the form is judged, and never computed here.
 *
 * Task ids: M21.4.1
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  CURRENCY_NEEDED,
  DOES_NOT_RECONCILE,
  NOT_ATTRIBUTED,
  PERIOD_NEEDED,
  PERIOD_ORDER,
  PROVIDER_NEEDED,
  RECONCILE_HEADING,
  RECONCILES,
  WITHHELD_PROVIDERS,
  lastMonth,
} from "../src/pages/reports/SpendReconcile";
import { providersPath } from "../src/pages/spendQuery";
import { AMOUNT_NEEDED, BUDGET_FORMAT } from "../src/pages/agents/AgentSpend";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";
import { COMPANY_CONSOLE, NAVIGATION_ADDRESS } from "./support/navigation";
import { PAGES } from "./support/pageCases";
import { installRadixStubs } from "./support/radix";

beforeAll(() => {
  installRadixStubs();
});

const API = "/api/v1";
const PROVIDERS = `${API}/report/spend/providers`;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", "x-trace-id": "trace-spend" } });
}

function providers(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    since: "2026-09-01",
    until: "2026-10-01",
    currency: "SGD",
    withheld: false,
    providers: [
      { provider: "anthropic", requests: 12, metered_minor: 400000, reconciliation: null },
      { provider: "openai", requests: 3, metered_minor: 25000, reconciliation: null },
    ],
    not_attributed_minor: 1500,
    not_attributed_requests: 2,
    told: "A cost row names its model and not its provider.",
    ...over,
  };
}

function reconciled(within: boolean): Record<string, unknown> {
  const withInvoice = providers();
  const lines = withInvoice["providers"] as Record<string, unknown>[];
  return {
    ...withInvoice,
    providers: [
      {
        ...lines[0],
        reconciliation: {
          currency: "USD",
          invoice_minor: 200000,
          metered_in_invoice_minor: within ? 200000 : 210000,
          difference_minor: within ? 0 : 10000,
          difference_percent: within ? 0 : 5,
          tolerance_percent: 2,
          within_tolerance: within,
          rate: "0.5",
        },
      },
      lines[1],
    ],
  };
}

async function mounted(first: unknown, second?: { readonly status: number; readonly body: unknown }) {
  cleanup();
  localStorage.clear();
  sessionStorage.clear();
  const asked: string[] = [];
  const base = PAGES["/spend"]?.answers ?? {};
  const idp = fakeIdentityProvider({
    api(url) {
      const parsed = new URL(url, "https://console.test");
      if (parsed.pathname === NAVIGATION_ADDRESS) {
        return json(COMPANY_CONSOLE);
      }
      if (parsed.pathname === PROVIDERS) {
        asked.push(`${parsed.pathname}${parsed.search}`);
        return parsed.search.includes("provider=") && second !== undefined ? json(second.body, second.status) : json(first);
      }
      return parsed.pathname in base ? json((base as Record<string, unknown>)[parsed.pathname]) : null;
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: ["/spend"] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => expect(container.querySelector("[data-slot='report-page']")).not.toBeNull(), { timeout: 10_000 });
  await waitFor(() => expect(container.querySelector("[data-slot='spend-reconcile']")).not.toBeNull(), { timeout: 10_000 });
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 50));
  });
  return { container, asked, text: () => container.querySelector("[data-slot='spend-reconcile']")?.textContent ?? "" };
}

function typed(form: HTMLFormElement, label: string, value: string): void {
  const field = [...form.querySelectorAll("label")].find((one) => one.textContent === label);
  const id = field?.getAttribute("for");
  const input = id === null || id === undefined ? null : form.ownerDocument.getElementById(id);
  if (!(input instanceof HTMLInputElement || input instanceof HTMLSelectElement)) {
    throw new Error(`No field labelled ${label}.`);
  }
  fireEvent.change(input, { target: { value } });
}

function formOf(container: Element): HTMLFormElement {
  const form = container.querySelector<HTMLFormElement>("form[data-slot='spend-reconcile-form']");
  if (form === null) {
    throw new Error("No reconciliation form.");
  }
  return form;
}

function said(form: HTMLFormElement): string {
  return form.querySelector('[role="alert"]')?.textContent ?? "";
}

describe("the invoice card", () => {
  test("draws each provider's metered spend and what no provider can be given, as the API sent them", async () => {
    // What breaks if this is deleted: a provider line drawn from a different field, or the
    // not-attributed amount dropped, so the lines no longer add up to the period.
    const page = await mounted(providers());
    expect(page.container.textContent).toContain(RECONCILE_HEADING);
    expect(page.text()).toContain("anthropic");
    expect(page.text()).toContain("SGD 4000.00");
    expect(page.text()).toContain("openai");
    expect(page.text()).toContain(`${NOT_ATTRIBUTED}SGD 15.00`);
  });

  test("a withheld answer says so and draws no figure and no form", async () => {
    // What breaks if this is deleted: a department reader is offered a form that the API will
    // answer with nothing, or sees the lines the API did not send.
    const page = await mounted(providers({ withheld: true, providers: [], not_attributed_minor: 0 }));
    expect(page.text()).toContain(WITHHELD_PROVIDERS);
    expect(page.container.querySelector("form[data-slot='spend-reconcile-form']")).toBeNull();
  });

  test("the first window asked is last calendar month, in UTC days", async () => {
    // What breaks if this is deleted: an invoice period that starts on the wrong day.
    expect(lastMonth(new Date(Date.UTC(2026, 9, 22)))).toEqual({ since: "2026-09-01", until: "2026-10-01" });
    expect(lastMonth(new Date(Date.UTC(2026, 0, 5)))).toEqual({ since: "2025-12-01", until: "2026-01-01" });
    const page = await mounted(providers());
    expect(page.asked[0]).toMatch(/^\/api\/v1\/report\/spend\/providers\?since=\d{4}-\d{2}-01&until=\d{4}-\d{2}-01$/u);
  });

  test("a form sent blank or wrong says what to fill in and asks nothing more", async () => {
    // What breaks if this is deleted: a blank invoice is held against the meter, or the API is
    // asked a question that cannot have an answer.
    const page = await mounted(providers());
    const form = formOf(page.container);
    const before = page.asked.length;
    fireEvent.submit(form);
    expect(said(form)).toBe(PROVIDER_NEEDED);
    typed(form, "Provider", "anthropic");
    fireEvent.submit(form);
    expect(said(form)).toBe(AMOUNT_NEEDED);
    typed(form, "Invoice total", "ten dollars");
    fireEvent.submit(form);
    expect(said(form)).toBe(BUDGET_FORMAT);
    typed(form, "Invoice total", "2000");
    fireEvent.submit(form);
    expect(said(form)).toBe(CURRENCY_NEEDED);
    typed(form, "Billing period starts", "1 September");
    typed(form, "Invoice currency", "USD");
    fireEvent.submit(form);
    expect(said(form)).toBe(PERIOD_NEEDED);
    typed(form, "Billing period starts", "2026-10-01");
    typed(form, "Billing period ends the day before", "2026-09-01");
    fireEvent.submit(form);
    expect(said(form)).toBe(PERIOD_ORDER);
    expect(page.asked.length).toBe(before);
  });

  test("a valid invoice is asked with the provider, the amount in minor units, the currency and the rate, and the verdict is drawn", async () => {
    // What breaks if this is deleted: the amount sent in major units, the rate dropped, or a
    // verdict computed in the browser instead of read.
    const page = await mounted(providers(), { status: 200, body: reconciled(true) });
    const form = formOf(page.container);
    typed(form, "Provider", "anthropic");
    typed(form, "Invoice total", "2000");
    typed(form, "Invoice currency", "usd");
    typed(form, "Rate, if the invoice is in another currency than this install", "0.5");
    fireEvent.submit(form);
    await waitFor(() => expect(page.text()).toContain(RECONCILES));
    expect(page.asked.at(-1)).toContain("provider=anthropic&invoice_minor=200000&invoice_currency=USD&rate=0.5");
    expect(page.text()).toContain("Rate used: 0.5.");
    expect(page.text()).toContain("held to 2%");
  });

  test("a verdict outside the tolerance says so with the difference", async () => {
    // What breaks if this is deleted: an invoice five per cent away reads as reconciled.
    const page = await mounted(providers(), { status: 200, body: reconciled(false) });
    const form = formOf(page.container);
    typed(form, "Provider", "anthropic");
    typed(form, "Invoice total", "2000");
    typed(form, "Invoice currency", "USD");
    fireEvent.submit(form);
    await waitFor(() => expect(page.text()).toContain(DOES_NOT_RECONCILE));
    expect(page.text()).toContain("difference USD 100.00 (5%)");
  });

  test("the API's refusal is drawn in its own words", async () => {
    // What breaks if this is deleted: a missing rate answered with a verdict, or with a blank.
    const page = await mounted(providers(), { status: 422, body: { message: "The invoice is in another currency than this install, so type the rate." } });
    const form = formOf(page.container);
    typed(form, "Provider", "anthropic");
    typed(form, "Invoice total", "2000");
    typed(form, "Invoice currency", "USD");
    fireEvent.submit(form);
    await waitFor(() => expect(page.container.textContent).toContain("type the rate"));
  });

  test("the request is built with no invoice fields until an invoice is given", () => {
    expect(providersPath("2026-09-01", "2026-10-01")).toBe("/report/spend/providers?since=2026-09-01&until=2026-10-01");
    expect(providersPath("2026-09-01", "2026-10-01", { provider: "a b", invoiceMinor: 5, currency: "USD", rate: " " })).toBe(
      "/report/spend/providers?since=2026-09-01&until=2026-10-01&provider=a%20b&invoice_minor=5&invoice_currency=USD",
    );
  });
});
