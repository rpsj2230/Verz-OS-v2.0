/**
 * The departments' budgets under the company's: drawn from what the API sent, offered only the
 * controls the answer says the reader holds, and each act typed, judged, confirmed and then sent.
 *
 * What breaks if these are deleted is named at each test. The Python half is
 * `tests/unit/test_department_budget_routes.py`, which holds who may write what.
 *
 * Task ids: M21.1.2, M21.1.3
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  ALLOWANCES_GIVEN,
  DEPARTMENT_BUDGETS_HEADING,
  DEPARTMENT_NEEDED,
  GIVE_ALLOWANCES,
  MOVE_MONEY,
  NO_DEPARTMENT_BUDGETS,
  SET_RUN_CEILING,
  SHARE_NEEDED,
  SHARE_THE_BUDGET,
  TWO_DEPARTMENTS_NEEDED,
  UNSHARED,
  shareOf,
} from "../src/pages/company/DepartmentBudgets";
import { readDepartmentBudgets } from "../src/pages/companyQuery";
import { AMOUNT_NEEDED, BUDGET_FORMAT, REASON_NEEDED } from "../src/pages/agents/AgentSpend";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";
import { COMPANY_CONSOLE, NAVIGATION_ADDRESS } from "./support/navigation";
import { installRadixStubs } from "./support/radix";

beforeAll(() => {
  installRadixStubs();
});

const API = "/api/v1";
const CONSUMPTION = `${API}/company/consumption`;
const DEPARTMENTS = `${API}/company/budget/departments`;

interface Sent {
  readonly method: string;
  readonly path: string;
  readonly body: unknown;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", "x-trace-id": "trace-departments" } });
}

const CONSUMPTION_BODY = {
  currency: "SGD",
  since: "2019-02-02T09:00:00Z",
  until: "2019-03-04T09:00:00Z",
  withheld: false,
  spend_minor: 80000,
  by_department: [],
  incomplete: false,
  ceiling_set: true,
  ceiling_minor: 900000,
  may_set_budget: false,
};

function departments(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    currency: "SGD",
    lines: [
      { department: "finance", monthly_minor: 400000, monthly_version: 2, run_ceiling_minor: 2500, run_version: 1 },
      { department: "web", monthly_minor: 250000, monthly_version: 1, run_ceiling_minor: null, run_version: null },
    ],
    may_allocate: true,
    unallocated_minor: 250000,
    ...over,
  };
}

async function mounted(body: unknown, refused?: { readonly status: number; readonly body: unknown }) {
  cleanup();
  localStorage.clear();
  sessionStorage.clear();
  const sent: Sent[] = [];
  const asked = { departments: false };
  const idp = fakeIdentityProvider({
    api(url, init) {
      const parsed = new URL(url, "https://console.test");
      if (parsed.pathname === NAVIGATION_ADDRESS) {
        return json(COMPANY_CONSOLE);
      }
      const method = init?.method ?? "GET";
      if (method !== "GET") {
        sent.push({ method, path: parsed.pathname, body: JSON.parse(String(init?.body ?? "null")) });
        return refused === undefined ? json({ ok: true }) : json(refused.body, refused.status);
      }
      if (parsed.pathname === CONSUMPTION) {
        return json(CONSUMPTION_BODY);
      }
      if (parsed.pathname === DEPARTMENTS) {
        asked.departments = true;
        return json(body);
      }
      return null;
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: ["/company/consumption"] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => expect(container.querySelector("[data-slot='company-page']")).not.toBeNull(), { timeout: 10_000 });
  await waitFor(() => expect(container.querySelector("[role='status']")).toBeNull(), { timeout: 10_000 });
  // The section is asked for once the page has drawn, and answers a moment after it.
  await waitFor(() => expect(asked.departments).toBe(true), { timeout: 10_000 });
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 50));
  });
  return { container, sent, text: () => container.querySelector("[data-slot='company-page']")?.textContent ?? "" };
}

function formNamed(root: Element, title: string, index = 0): HTMLFormElement {
  const found = [...root.querySelectorAll<HTMLFormElement>("form[data-slot='department-budget-action']")].filter(
    (one) => one.getAttribute("aria-label") === title,
  )[index];
  if (found === undefined) {
    throw new Error(`No form named ${title}.`);
  }
  return found;
}

function type(form: HTMLFormElement, label: string, value: string): void {
  const field = [...form.querySelectorAll("label")].find((one) => one.textContent === label);
  const id = field?.getAttribute("for");
  const input = id === null || id === undefined ? null : form.ownerDocument.getElementById(id);
  if (!(input instanceof HTMLInputElement)) {
    throw new Error(`No field labelled ${label}.`);
  }
  fireEvent.change(input, { target: { value } });
}

function said(form: HTMLFormElement): string {
  return form.querySelector('[role="alert"]')?.textContent ?? "";
}

async function confirmed(root: Element): Promise<void> {
  await waitFor(() => expect(root.ownerDocument.querySelector("[data-slot='confirm-dialog']")).not.toBeNull());
  const dialog = root.ownerDocument.querySelector("[data-slot='confirm-dialog']") as Element;
  const buttons = dialog.querySelectorAll("button");
  fireEvent.click(buttons[buttons.length - 1] as HTMLButtonElement);
}

describe("the department budgets section", () => {
  test("a reader who holds the authority over everything is shown every line, what is unshared, and all four controls", async () => {
    // What breaks if this is deleted: the section is drawn without the figures the API sent, or a
    // control the answer said the reader holds is not drawn.
    const page = await mounted(departments());
    expect(page.text()).toContain(DEPARTMENT_BUDGETS_HEADING);
    expect(page.text()).toContain("finance");
    expect(page.text()).toContain("SGD 4000.00");
    expect(page.text()).toContain("SGD 25.00");
    expect(page.text()).toContain(`${UNSHARED}: SGD 2500.00`);
    for (const title of [SHARE_THE_BUDGET, MOVE_MONEY]) {
      expect(formNamed(page.container, title)).toBeTruthy();
    }
    expect(formNamed(page.container, SET_RUN_CEILING, 1)).toBeTruthy();
    expect(formNamed(page.container, GIVE_ALLOWANCES, 1)).toBeTruthy();
  });

  test("a department's own administrator is shown their line and neither the allocation nor the transfer", async () => {
    // What breaks if this is deleted: controls drawn for a reader the API will refuse, which says
    // by the controls offered that the company's money can be moved.
    const page = await mounted(
      departments({ lines: [{ department: "web", monthly_minor: 250000, monthly_version: 1, run_ceiling_minor: null, run_version: null }], may_allocate: false, unallocated_minor: null }),
    );
    expect(page.text()).toContain("web");
    expect(page.text()).not.toContain(UNSHARED);
    expect(() => formNamed(page.container, SHARE_THE_BUDGET)).toThrow();
    expect(() => formNamed(page.container, MOVE_MONEY)).toThrow();
    expect(formNamed(page.container, SET_RUN_CEILING)).toBeTruthy();
  });

  test("a reader with no line and no authority over everything is shown no section at all", async () => {
    // What breaks if this is deleted: an empty heading that tells a reader the company has department budgets.
    const page = await mounted(departments({ lines: [], may_allocate: false, unallocated_minor: null }));
    expect(page.text()).not.toContain(DEPARTMENT_BUDGETS_HEADING);
  });

  test("an administrator over everything with no departments yet is told so and offered the allocation", async () => {
    const page = await mounted(departments({ lines: [] }));
    expect(page.text()).toContain(NO_DEPARTMENT_BUDGETS);
    expect(formNamed(page.container, SHARE_THE_BUDGET)).toBeTruthy();
  });

  test("the body is read as the API spelled it, and a body that is not one is read as nothing", () => {
    // What breaks if this is deleted: a renamed field is drawn as a nought.
    expect(readDepartmentBudgets(departments())).toMatchObject({
      mayAllocate: true,
      unallocatedMinor: 250000,
      lines: [
        { department: "finance", monthlyMinor: 400000, runCeilingMinor: 2500 },
        { department: "web", monthlyMinor: 250000, runCeilingMinor: null },
      ],
    });
    expect(readDepartmentBudgets({ lines: "no" })).toBeNull();
    expect(readDepartmentBudgets(null)).toBeNull();
  });
});

describe("a share typed as a percentage", () => {
  test("is a fraction between nothing and one, and anything else is not one", () => {
    // What breaks if this is deleted: a typed 150 or 0 or "ten" is sent as a share.
    expect(shareOf("40")).toBe(0.4);
    expect(shareOf("12.5")).toBe(0.125);
    expect(shareOf("100")).toBe(1);
    for (const bad of ["", "0", "101", "-5", "ten", "1,5", "12.555"]) {
      expect(shareOf(bad), bad).toBeNull();
    }
  });
});

describe("each act is judged, confirmed and then sent", () => {
  test("every form submitted blank says what to fill in and sends nothing", async () => {
    // What breaks if this is deleted: a blank reason or amount reaches a confirmation about
    // nothing, or the API, which refuses it only after a person agreed.
    const page = await mounted(departments());
    for (const title of [SET_RUN_CEILING, GIVE_ALLOWANCES, SHARE_THE_BUDGET, MOVE_MONEY]) {
      const form = formNamed(page.container, title);
      fireEvent.submit(form);
      expect(said(form), title).toBe(REASON_NEEDED);
    }
    expect(page.container.ownerDocument.querySelector("[data-slot='confirm-dialog']")).toBeNull();
    expect(page.sent).toEqual([]);
  });

  test("a figure that is not one is said beside the form before anything is asked", async () => {
    const page = await mounted(departments());
    const ceiling = formNamed(page.container, SET_RUN_CEILING);
    type(ceiling, "Reason", "A reason");
    fireEvent.submit(ceiling);
    expect(said(ceiling)).toBe(AMOUNT_NEEDED);
    type(ceiling, "Per-run ceiling for finance", "ten dollars");
    fireEvent.submit(ceiling);
    expect(said(ceiling)).toBe(BUDGET_FORMAT);

    const share = formNamed(page.container, SHARE_THE_BUDGET);
    type(share, "Reason", "A reason");
    fireEvent.submit(share);
    expect(said(share)).toBe(DEPARTMENT_NEEDED);
    type(share, "Department", "web");
    type(share, "Share of the company's month (%)", "150");
    fireEvent.submit(share);
    expect(said(share)).toBe(SHARE_NEEDED);

    const move = formNamed(page.container, MOVE_MONEY);
    type(move, "Reason", "A reason");
    type(move, "From department", "web");
    type(move, "To department", "web");
    fireEvent.submit(move);
    expect(said(move)).toBe(TWO_DEPARTMENTS_NEEDED);
    expect(page.sent).toEqual([]);
  });

  test("a per-run ceiling is sent only from its confirmation, to the department's own address, in minor units", async () => {
    // What breaks if this is deleted: a ceiling sent on submit, to the wrong department, or as major units.
    const page = await mounted(departments());
    const form = formNamed(page.container, SET_RUN_CEILING, 1);
    type(form, "Per-run ceiling for web", "12.50");
    type(form, "Reason", "Per run");
    fireEvent.submit(form);
    expect(page.sent).toEqual([]);
    await confirmed(page.container);
    await waitFor(() => expect(page.sent.length).toBe(1));
    expect(page.sent[0]).toEqual({
      method: "PUT",
      path: `${API}/departments/web/budget/run-ceiling`,
      body: { ceiling_minor: 1250, reason: "Per run" },
    });
  });

  test("the allowances, the share and the transfer are each sent from their confirmation with what was typed", async () => {
    const page = await mounted(departments());
    const allowances = formNamed(page.container, GIVE_ALLOWANCES, 0);
    type(allowances, "Reason", "The month");
    fireEvent.submit(allowances);
    await confirmed(page.container);
    await waitFor(() => expect(page.sent.length).toBe(1));
    await waitFor(() => expect(page.text()).toContain(ALLOWANCES_GIVEN));

    const share = formNamed(page.container, SHARE_THE_BUDGET);
    type(share, "Department", "support");
    type(share, "Share of the company's month (%)", "12.5");
    type(share, "Reason", "A new team");
    fireEvent.submit(share);
    await confirmed(page.container);
    await waitFor(() => expect(page.sent.length).toBe(2));

    const move = formNamed(page.container, MOVE_MONEY);
    type(move, "From department", "finance");
    type(move, "To department", "web");
    type(move, "Amount", "100");
    type(move, "Reason", "A launch");
    fireEvent.submit(move);
    await confirmed(page.container);
    await waitFor(() => expect(page.sent.length).toBe(3));

    expect(page.sent).toEqual([
      { method: "POST", path: `${API}/departments/finance/budget/allowances`, body: { reason: "The month" } },
      {
        method: "PUT",
        path: `${API}/company/budget/departments`,
        body: { shares: [{ department: "support", share: 0.125 }], reason: "A new team" },
      },
      {
        method: "POST",
        path: `${API}/company/budget/departments/transfer`,
        body: { from_department: "finance", to_department: "web", amount_minor: 10000, reason: "A launch" },
      },
    ]);
  });

  test("a refusal is drawn in the API's own sentence and nothing is claimed saved", async () => {
    // What breaks if this is deleted: a refused ceiling reads as saved.
    const page = await mounted(departments(), { status: 403, body: { message: "Setting a department's per-run ceiling needs the budget administrator's role over that department." } });
    const form = formNamed(page.container, SET_RUN_CEILING, 1);
    type(form, "Per-run ceiling for web", "5");
    type(form, "Reason", "Per run");
    fireEvent.submit(form);
    await confirmed(page.container);
    await waitFor(() => expect(form.textContent).toContain("needs the budget administrator"));
    expect(form.textContent).not.toContain("is set.");
  });
});
