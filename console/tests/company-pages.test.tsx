/**
 * The whole-company pages draw what `brain.company_routes` sent and nothing else: the estate's rows
 * and the filters its answer offered, the activity's entries by name, and the company's spend, or
 * that it is withheld. A filter the answer offered nothing for is not drawn, a filter chosen is sent
 * to the API rather than applied here, and a withheld figure is never drawn as a number.
 *
 * Task ids: M33.1.1.1, M33.1.1.2, M33.1.1.3
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  DEPARTMENT_FILTER,
  INCOMPLETE,
  KIND_FILTER,
  NO_CEILING,
  OLDER,
  ORDER_FILTER,
  PERSON_FILTER,
  WITHHELD,
} from "../src/pages/company/CompanyPages";
import { readConsumption } from "../src/pages/companyQuery";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";
import { COMPANY_CONSOLE, NAVIGATION_ADDRESS, addressesOf } from "./support/navigation";
import { installRadixStubs } from "./support/radix";

beforeAll(() => {
  installRadixStubs();
});

const API = "/api/v1";
const ESTATE = `${API}/company/estate`;
const ACTIVITY = `${API}/company/activity`;
const CONSUMPTION = `${API}/company/consumption`;

interface Mounted {
  readonly root: () => Element;
  /** Every company address asked, with its query, in order. */
  readonly asked: string[];
  readonly text: () => string;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", "x-trace-id": "trace-company" } });
}

async function pageAt(address: string, answers: Readonly<Record<string, unknown>>): Promise<Mounted> {
  cleanup();
  localStorage.clear();
  sessionStorage.clear();
  const asked: string[] = [];
  const idp = fakeIdentityProvider({
    api(url) {
      const parsed = new URL(url, "https://console.test");
      if (parsed.pathname.startsWith(`${API}/company/`)) {
        asked.push(`${parsed.pathname}${parsed.search}`);
      }
      if (parsed.pathname === NAVIGATION_ADDRESS) {
        return json(COMPANY_CONSOLE);
      }
      return parsed.pathname in answers ? json(answers[parsed.pathname]) : null;
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [address] });
  const { container } = render(<RouterProvider router={router} />);
  const root = (): Element => container.querySelector("main#main") ?? container;
  await waitFor(
    () => {
      expect(root().querySelector("[data-slot='company-page']")).not.toBeNull();
      expect(root().querySelector("[role='status']")).toBeNull();
    },
    { timeout: 10_000 },
  );
  return { root, asked, text: () => root().querySelector("[data-slot='company-page']")?.textContent ?? "" };
}

function select(root: Element, label: string): HTMLSelectElement | null {
  for (const one of root.querySelectorAll("label")) {
    if (one.textContent === label) {
      const id = one.getAttribute("for");
      // By id through the document rather than a selector: React's ids carry colons.
      const found = id === null ? null : root.ownerDocument.getElementById(id);
      return found instanceof HTMLSelectElement ? found : null;
    }
  }
  return null;
}

function options(control: HTMLSelectElement | null): string[] {
  return [...(control?.options ?? [])].map((one) => one.value).filter((one) => one !== "");
}

function estate(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    items: [
      { kind: "agent", item_id: "a_finance", label: "Finance desk" },
      { kind: "knowledge", item_id: "k_policy", label: "k_policy" },
    ],
    kinds: ["agent", "skill", "knowledge", "connector"],
    departments: ["finance"],
    people: ["u_ana"],
    names: { u_ana: "Ana Lim" },
    ...over,
  };
}

function activity(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    items: [
      {
        at: "2019-03-04T09:00:00Z",
        action: "grant",
        actor_id: "u_ana",
        subject_kind: "principal",
        subject_id: "u_ben",
        details: {},
      },
    ],
    next_cursor: null,
    departments: ["finance", "support"],
    actors: ["u_ana"],
    people: { u_ana: "Ana Lim", u_ben: "Ben Tan" },
    ...over,
  };
}

function consumption(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    currency: "SGD",
    since: "2019-02-02T09:00:00Z",
    until: "2019-03-04T09:00:00Z",
    withheld: false,
    spend_minor: 80000,
    by_department: [
      { department: "finance", spend_minor: 50000 },
      { department: "support", spend_minor: 30000 },
    ],
    incomplete: false,
    ceiling_set: false,
    ...over,
  };
}

describe("the menu", () => {
  test("the company console offers the three company pages as tabs of one entry", () => {
    expect(addressesOf(COMPANY_CONSOLE)).toEqual(expect.arrayContaining(["/company/estate", "/company/activity", "/company/consumption"]));
  });
});

describe("Everything", () => {
  test("draws the rows the API sent, by the words each is known by, and asks with no filter", async () => {
    const page = await pageAt("/company/estate", { [ESTATE]: estate() });

    expect(page.text()).toContain("Finance desk");
    expect(page.text()).toContain("k_policy");
    expect(page.asked).toEqual([ESTATE]);
  });

  test("offers the departments and people the answer carried, and a choice is sent to the API", async () => {
    const page = await pageAt("/company/estate", { [ESTATE]: estate() });
    const department = select(page.root(), DEPARTMENT_FILTER);

    expect(options(department)).toEqual(["finance"]);
    expect(options(select(page.root(), PERSON_FILTER))).toEqual(["u_ana"]);
    expect(options(select(page.root(), KIND_FILTER))).toEqual(["agent", "skill", "knowledge", "connector"]);
    fireEvent.change(department as HTMLSelectElement, { target: { value: "finance" } });
    await waitFor(() => {
      expect(page.asked).toContain(`${ESTATE}?department=finance`);
    });
  });

  test("a filter the answer offered nothing for is not drawn", async () => {
    const page = await pageAt("/company/estate", { [ESTATE]: estate({ departments: [], people: [] }) });

    expect(select(page.root(), DEPARTMENT_FILTER)).toBeNull();
    expect(select(page.root(), PERSON_FILTER)).toBeNull();
    expect(select(page.root(), KIND_FILTER)).not.toBeNull();
  });

  test("the filters in the address are sent as they are, and nothing is narrowed in the browser", async () => {
    const page = await pageAt("/company/estate?department=finance&person=u_ana", { [ESTATE]: estate() });

    expect(page.asked).toEqual([`${ESTATE}?department=finance&person=u_ana`]);
    // Both rows are drawn although only one is in finance: the API narrows, and the page draws.
    expect(page.text()).toContain("Finance desk");
    expect(page.text()).toContain("k_policy");
  });
});

describe("Activity", () => {
  test("names the people on the rows and offers the actors and departments the answer carried", async () => {
    const page = await pageAt("/company/activity", { [ACTIVITY]: activity() });

    expect(page.text()).toContain("Ana Lim");
    expect(page.text()).toContain("Ben Tan");
    expect(options(select(page.root(), DEPARTMENT_FILTER))).toEqual(["finance", "support"]);
    expect(options(select(page.root(), PERSON_FILTER))).toEqual(["u_ana"]);
    expect(page.asked).toEqual([ACTIVITY]);
  });

  test("the search and the order are sent to the API, and the estate, whose route takes neither, draws neither", async () => {
    const page = await pageAt("/company/activity", { [ACTIVITY]: activity() });
    const order = select(page.root(), ORDER_FILTER);
    expect(options(order)).toEqual(["newest", "oldest"]);
    fireEvent.change(order as HTMLSelectElement, { target: { value: "oldest" } });
    await waitFor(() => {
      expect(page.asked).toContain(`${ACTIVITY}?order=oldest`);
    });
    const box = page.root().querySelector('input[type="search"]');
    expect(box).not.toBeNull();
    fireEvent.change(box as HTMLInputElement, { target: { value: "grant" } });
    await waitFor(() => {
      expect(page.asked).toContain(`${ACTIVITY}?order=oldest&q=grant`);
    });

    const estatePage = await pageAt("/company/estate", { [ESTATE]: estate() });
    expect(estatePage.root().querySelector('input[type="search"]')).toBeNull();
    expect(select(estatePage.root(), ORDER_FILTER)).toBeNull();
  });

  test("a cursor offers older entries and asks from it, and none is offered without one", async () => {
    const without = await pageAt("/company/activity", { [ACTIVITY]: activity() });
    expect(without.text()).not.toContain(OLDER);

    const page = await pageAt("/company/activity?department=finance", { [ACTIVITY]: activity({ next_cursor: "c_next" }) });
    const older = [...page.root().querySelectorAll("button")].find((one) => one.textContent === OLDER);
    expect(older).toBeDefined();
    fireEvent.click(older as HTMLButtonElement);
    await waitFor(() => {
      expect(page.asked).toContain(`${ACTIVITY}?cursor=c_next&department=finance`);
    });
  });
});

describe("Consumption", () => {
  test("draws the company's figure and each department's line as the API sent them", async () => {
    const page = await pageAt("/company/consumption", { [CONSUMPTION]: consumption() });

    expect(page.text()).toContain("SGD 800.00");
    expect(page.text()).toContain("SGD 500.00");
    expect(page.text()).toContain("SGD 300.00");
    expect(page.text()).toContain(NO_CEILING);
    expect(page.text()).not.toContain(INCOMPLETE);
    expect(page.asked).toEqual([`${CONSUMPTION}?days=30`]);
  });

  test("a withheld figure is said to be withheld and no number is drawn, whatever else the body holds", async () => {
    const page = await pageAt("/company/consumption", {
      [CONSUMPTION]: consumption({ withheld: true, spend_minor: 123456, by_department: [{ department: "finance", spend_minor: 999 }] }),
    });

    expect(page.text()).toContain(WITHHELD);
    expect(page.text()).not.toContain("1234.56");
    expect(page.text()).not.toContain("finance");
    expect(readConsumption(consumption({ withheld: true }))).toEqual({
      withheld: true,
      since: "2019-02-02T09:00:00Z",
      until: "2019-03-04T09:00:00Z",
    });
  });

  test("a load that came back full is said beside the figure", async () => {
    const page = await pageAt("/company/consumption", { [CONSUMPTION]: consumption({ incomplete: true }) });

    expect(page.text()).toContain(INCOMPLETE);
  });
});
