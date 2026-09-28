/**
 * The Models screen's prices: each model with what a million tokens cost and whether its calls are
 * costed, and a price set from its row, checked, confirmed and sent in minor units (M27.12.5).
 *
 * Task ids: M27.12.5
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  BLANK_PRICE,
  CHOOSE_A_CURRENCY_FIRST,
  COSTED,
  NOT_PRICED,
  SAVE_PRICE,
  SET_PRICE,
  majorFromMinor,
  minorFromMajor,
} from "../src/pages/modelPricesQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { PAGES } from "./support/pageCases";
import { backendModelFields } from "./support/python";

beforeAll(async () => {
  await import("../src/pages/Models");
}, 60_000);

const PRICES_PATH = "/api/v1/models/prices";

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
}

const PRICES = {
  currency: "SGD",
  models: [
    {
      provider: "anthropic",
      model: "claude-sonnet-5",
      on_ladder: true,
      input_minor_per_million: "300",
      output_minor_per_million: "1500",
      currency: "SGD",
      costed: true,
    },
    {
      provider: "openai",
      model: "gpt-5",
      on_ladder: true,
      input_minor_per_million: null,
      output_minor_per_million: null,
      currency: null,
      costed: false,
    },
  ],
};

async function mounted(answers: Record<string, unknown>): Promise<{ container: HTMLElement; idp: FakeIdp }> {
  const idp = fakeIdentityProvider({
    api(url, init) {
      const pathname = new URL(url, "https://console.test").pathname;
      if (pathname === PRICES_PATH && (init?.method ?? "GET") === "PUT") {
        return json({ ...PRICES, models: PRICES.models.map((one) => ({ ...one, costed: true })) });
      }
      return pathname in answers ? json(answers[pathname]) : null;
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: ["/models"] });
  const { container } = render(<RouterProvider router={router} />);
  return { container, idp };
}

function writes(idp: FakeIdp): { method: string; path: string; body: unknown }[] {
  return idp.calls
    .filter((call) => String(call.url).includes("/api/v1/") && (call.init?.method ?? "GET") !== "GET")
    .map((call) => ({
      method: call.init?.method ?? "GET",
      path: new URL(String(call.url), "https://console.test").pathname,
      body: typeof call.init?.body === "string" ? (JSON.parse(call.init.body) as unknown) : null,
    }));
}

function pricesTable(container: HTMLElement): string[] {
  const table = [...container.querySelectorAll("table")].find(
    (one) => one.querySelector("caption")?.textContent === "What a million tokens cost on each model",
  );
  return [...(table?.querySelectorAll("tbody tr") ?? [])].map((row) => row.textContent ?? "");
}

describe("the prices card", () => {
  test("each model is drawn with its price in whole currency and whether its calls are costed", async () => {
    // What breaks if this is deleted: an administrator cannot see which models' calls leave no
    // cost, or a price is drawn in minor units and read as a hundred times what it is.
    const { container } = await mounted({ ...PAGES["/models"]?.answers, [PRICES_PATH]: PRICES });
    await waitFor(() => {
      if (pricesTable(container).length === 0) {
        throw new Error("the prices have not arrived");
      }
    });
    const rows = pricesTable(container);
    expect(rows[0]).toContain("3.00");
    expect(rows[0]).toContain("15.00");
    expect(rows[0]).toContain(COSTED);
    expect(rows[1]).toContain(NOT_PRICED);
  });

  test("a price is checked for blanks, confirmed, and sent in minor units per million", async () => {
    // What breaks if this is deleted: a blank price is sent, a price is sent from an unconfirmed
    // press, or 0.075 reaches the API as 7.499999999999999.
    const { container, idp } = await mounted({ ...PAGES["/models"]?.answers, [PRICES_PATH]: PRICES });
    await waitFor(() => {
      const open = [...container.querySelectorAll("button")].find((one) =>
        (one.getAttribute("aria-label") ?? "").startsWith(`${SET_PRICE}: OpenAI`),
      );
      if (open === undefined) {
        throw new Error("the prices have not arrived");
      }
      fireEvent.click(open);
    });
    const form = container.querySelector('form[aria-label^="Price of"]') as HTMLFormElement;
    const field = (name: string) => form.querySelector(`[name="${name}"]`) as HTMLInputElement;

    fireEvent.submit(form);
    expect(container.textContent).toContain(BLANK_PRICE);
    expect(container.querySelector(".confirm")).toBeNull();

    fireEvent.change(field("input_minor_per_million"), { target: { value: "0.00075" } });
    fireEvent.change(field("output_minor_per_million"), { target: { value: "10" } });
    fireEvent.submit(form);
    expect(writes(idp)).toEqual([]);
    const confirm = [...container.querySelectorAll(".confirm button")].filter((one) => one.textContent === SAVE_PRICE);
    fireEvent.click(confirm[0] as HTMLElement);
    await waitFor(() => {
      if (writes(idp).length === 0) {
        throw new Error("nothing sent");
      }
    });

    expect(writes(idp)).toEqual([
      {
        method: "PUT",
        path: PRICES_PATH,
        body: {
          provider: "openai",
          model: "gpt-5",
          input_minor_per_million: "0.075",
          output_minor_per_million: "1000",
        },
      },
    ]);
    await waitFor(() => {
      expect(container.textContent).toContain("is priced, and its calls are costed from the next one.");
    });
  });

  test("with no currency chosen the card sends the administrator to Settings and offers no control", async () => {
    // What breaks if this is deleted: a price is offered in no currency, which the API refuses
    // after the administrator has typed it.
    const { container } = await mounted({
      ...PAGES["/models"]?.answers,
      [PRICES_PATH]: { ...PRICES, currency: "XXX" },
    });
    await waitFor(() => {
      if (pricesTable(container).length === 0) {
        throw new Error("the prices have not arrived");
      }
    });
    expect(container.textContent).toContain(CHOOSE_A_CURRENCY_FIRST);
    expect(
      [...container.querySelectorAll("button")].some((one) => (one.getAttribute("aria-label") ?? "").startsWith(SET_PRICE)),
    ).toBe(false);
  });

  test("whole currency and minor units convert on the digits, both ways", () => {
    // What breaks if this is deleted: the conversion multiplies a float, and a cheap model's price
    // is kept at the nearest binary fraction or off by a factor of a hundred.
    expect(minorFromMajor("3")).toBe("300");
    expect(minorFromMajor("3.5")).toBe("350");
    expect(minorFromMajor("0.00075")).toBe("0.075");
    expect(minorFromMajor("0")).toBe("0");
    expect(minorFromMajor("-1")).toBeNull();
    expect(minorFromMajor("1e3")).toBeNull();
    expect(majorFromMinor("300")).toBe("3.00");
    expect(majorFromMinor("0.075")).toBe("0.00075");
    expect(majorFromMinor("5")).toBe("0.05");
    expect(majorFromMinor("1500")).toBe("15.00");
  });

  test("the card reads the fields the API serves and sends the fields it takes", () => {
    // What breaks if this is deleted: a field renamed in `brain.provider_routes` reads as missing,
    // and every model is drawn unpriced.
    const served = backendModelFields("src/brain/provider_routes.py", "ModelPriceView");
    expect([...served].sort()).toEqual(Object.keys(PRICES.models[0] ?? {}).sort());
    const taken = backendModelFields("src/brain/provider_routes.py", "PriceAsked");
    expect([...taken].sort()).toEqual(["input_minor_per_million", "model", "output_minor_per_million", "provider"]);
  });
});
