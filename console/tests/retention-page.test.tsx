/**
 * The Retention and erasure screen: the report, the release and its withdrawal, legal holds placed
 * and lifted, and the two records nothing keeps.
 *
 * Mounted directly on a memory router at its own address, for the reason
 * `tests/sessions-page.test.tsx` gives. The failures worth testing are the ones that look like the
 * screen working: a write sent without its confirmation, a confirmation that does not say what the
 * sweep will then do, a control drawn for somebody the API said may not act, and a hold that fails
 * the route's own pattern only after it was sent.
 *
 * **What a hold sends is read against the route's own request body**, so a key or a pattern this
 * console invented is a failure here rather than a 422 in front of an administrator.
 *
 * Task ids: none
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  HOLD_FORM_LABEL,
  HOLD_NOT_YOURS,
  LIFT_FORM_LABEL,
  LIFT_LABEL,
  NO_REPORT,
  PLACE_LABEL,
  READING_RETENTION,
  RELEASE_LABEL,
  RELEASE_NOT_YOURS,
  WITHDRAW_LABEL,
} from "../src/pages/Retention";
import {
  IDENTIFIER_PATTERN,
  MAX_HELD_NAMES,
  REASON_CODE_MAX,
  REASON_CODE_PATTERN,
  holdBody,
  holdProblems,
  releaseCounts,
  type Controls,
  type Report,
} from "../src/pages/retentionQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { declaredPropertySchema, declaredRequestBodySchema } from "./support/openapi";

const CONSOLE_ORIGIN = "https://console.test";
const REPORT_OPERATION = "/api/v1/govern/retention";
const CONTROLS_OPERATION = "/api/v1/govern/retention/controls";
const RELEASE_OPERATION = "/api/v1/govern/retention/release";
const WITHDRAWAL_OPERATION = "/api/v1/govern/retention/withdrawal";
const HOLD_OPERATION = "/api/v1/govern/legal-holds";
const LIFT_OPERATION = "/api/v1/govern/legal-holds/lift";

beforeAll(async () => {
  await import("../src/pages/Retention");
}, 60_000);

function controls(overrides: Partial<Controls> = {}): Controls {
  return {
    may_release: true,
    may_hold: true,
    releasing: "RELEASING-SENTENCE",
    withdrawing: "WITHDRAWING-SENTENCE",
    holding: "HOLDING-SENTENCE",
    lifting: "LIFTING-SENTENCE",
    exports: "EXPORTS-SENTENCE",
    erasures: "ERASURES-SENTENCE",
    kept: [
      { data_class: "payload", lifetime: "fixed_window", days: 30, because: "PAYLOAD-BECAUSE" },
    ],
    ...overrides,
  };
}

function report(overrides: Partial<Report> = {}): Report {
  return {
    report_id: "11111111-1111-4111-8111-111111111111",
    at: "2019-03-04T09:00:00Z",
    report_only: true,
    complete: true,
    failure: null,
    released: false,
    removed: 0,
    removed_by_class: [],
    held_by_class: [],
    queued_by_class: [],
    stores: [
      {
        store: "ledger",
        data_class: "metadata_ledger",
        lifetime: "fixed_window",
        days: 1825,
        reached: true,
        beyond_horizon: 12,
        held: 2,
        due: 7,
        removed: 0,
        queued: 3,
        queued_because: "QUEUED-BECAUSE",
        unreached_because: "",
        oldest_days: 2000,
      },
      {
        store: "recording",
        data_class: "recording",
        lifetime: "fixed_window",
        days: 30,
        reached: false,
        beyond_horizon: 0,
        held: 0,
        due: 0,
        removed: 0,
        queued: 0,
        queued_because: "",
        unreached_because: "UNREACHED-BECAUSE",
        oldest_days: null,
      },
    ],
    holds: [{ hold_id: "matter-7", reason_code: "litigation", company_wide: false }],
    findings: [],
    ...overrides,
  };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

interface Stand {
  report: Report | null;
  controls: Controls;
}

async function mount(stand: Stand): Promise<{ container: HTMLElement; idp: FakeIdp }> {
  const idp = fakeIdentityProvider({
    api(url, init) {
      const path = new URL(url, CONSOLE_ORIGIN).pathname;
      if (init?.method === "POST") {
        if (path === RELEASE_OPERATION) {
          return json({
            release_id: "22222222-2222-4222-8222-222222222222",
            after_report: stand.report?.report_id,
            released_at: "2019-03-05T10:00:00Z",
          });
        }
        if (path === WITHDRAWAL_OPERATION) {
          return json({ withdrawn_at: "2019-03-05T10:00:00Z" });
        }
        if (path === HOLD_OPERATION) {
          return json({ hold_id: "matter-9", placed_at: "2019-03-05T10:00:00Z" });
        }
        if (path === LIFT_OPERATION) {
          return json({ hold_id: "matter-7", lifted_at: "2019-03-05T10:00:00Z" });
        }
        return null;
      }
      if (path === REPORT_OPERATION) {
        return json({ report: stand.report });
      }
      if (path === CONTROLS_OPERATION) {
        return json(stand.controls);
      }
      return null;
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { Retention } = await import("../src/pages/Retention");
  const router = createMemoryRouter([{ path: "/retention", element: <Retention /> }], {
    initialEntries: ["/retention"],
  });
  const { container } = render(<RouterProvider router={router} />);
  await settled(container);
  return { container, idp };
}

async function settled(container: HTMLElement): Promise<void> {
  await waitFor(() => {
    if (container.textContent?.includes(READING_RETENTION) || !container.querySelector("h2")) {
      throw new Error("still reading");
    }
  });
}

function posts(idp: FakeIdp): { path: string; body: unknown }[] {
  return idp.calls
    .filter(
      (call) =>
        call.init?.method === "POST" &&
        new URL(call.url, CONSOLE_ORIGIN).pathname.startsWith("/api/"),
    )
    .map((call) => ({
      path: new URL(call.url, CONSOLE_ORIGIN).pathname,
      body:
        call.init?.body === undefined
          ? undefined
          : (JSON.parse(String(call.init.body)) as unknown),
    }));
}

function button(container: HTMLElement, name: string): HTMLButtonElement | null {
  return (
    ([...container.querySelectorAll("button")].find((one) => one.textContent === name) as
      | HTMLButtonElement
      | undefined) ?? null
  );
}

function field(form: Element, label: string): HTMLInputElement | HTMLTextAreaElement {
  const found = [...form.querySelectorAll("label")].find((one) => one.textContent?.startsWith(label));
  const control = found?.querySelector("input, textarea");
  if (control === null || control === undefined) {
    throw new Error(`no field labelled ${label}`);
  }
  return control as HTMLInputElement;
}

describe("what the retention screen agrees with the API about", () => {
  test("a hold is checked against the patterns and bounds the route itself declares", () => {
    // What breaks if this is deleted: a pattern here drifts from `brain.audit.ledger`'s, and a
    // hold the page accepted is refused with a 422 after the administrator confirmed it.
    const body = declaredRequestBodySchema(HOLD_OPERATION, "post");
    expect(Object.keys(body["properties"] as object).sort()).toEqual(
      Object.keys(holdBody({ holdId: "a", reasonCode: "b", subjects: "", actors: "", everybody: false })).sort(),
    );
    expect(declaredPropertySchema(HOLD_OPERATION, "post", "hold_id")["pattern"]).toBe(
      IDENTIFIER_PATTERN,
    );
    const reason = declaredPropertySchema(HOLD_OPERATION, "post", "reason_code");
    expect(reason["pattern"]).toBe(REASON_CODE_PATTERN);
    expect(reason["maxLength"]).toBe(REASON_CODE_MAX);
    expect(declaredPropertySchema(HOLD_OPERATION, "post", "subjects")["maxItems"]).toBe(
      MAX_HELD_NAMES,
    );
  });

  test("a hold naming nobody, or with a sentence for a reason, is refused before it is sent", () => {
    // What breaks if this is deleted: validation happens only on the server, after the
    // confirmation, which `docs/admin-console.md` refuses.
    expect(
      holdProblems({ holdId: "", reasonCode: "Smith v Jones", subjects: "", actors: "", everybody: false }),
    ).toHaveLength(3);
    expect(
      holdProblems({ holdId: "m-1", reasonCode: "litigation", subjects: "u_1", actors: "", everybody: false }),
    ).toEqual([]);
  });
});

describe("releasing and withdrawing the sweep", () => {
  test("a release is confirmed with the report's counts and the API's sentence, then sent", async () => {
    // What breaks if this is deleted: a release is sent on the first click, or confirmed without
    // saying what the sweep will then remove, which is a deletion somebody agreed to unread.
    const { container, idp } = await mount({ report: report(), controls: controls() });

    fireEvent.click(button(container, RELEASE_LABEL) as HTMLButtonElement);
    expect(posts(idp)).toEqual([]);
    const confirmation = container.querySelector(".confirm")?.textContent ?? "";
    expect(confirmation).toContain("7 items were past their window in ledger");
    expect(confirmation).toContain("3 were queued");
    expect(confirmation).toContain("2 were held");
    expect(confirmation).not.toContain("recording");
    expect(confirmation).toContain("RELEASING-SENTENCE");

    fireEvent.click(
      [...container.querySelectorAll(".confirm button")].find(
        (one) => one.textContent === RELEASE_LABEL,
      ) as HTMLButtonElement,
    );
    await waitFor(() => {
      expect(posts(idp)).toEqual([
        { path: RELEASE_OPERATION, body: { after_report: report().report_id } },
      ]);
    });
    await waitFor(() => {
      expect(container.textContent).toContain("The sweep was released at");
    });
  });

  test("a reader the API says may not release is drawn no control and told why", async () => {
    // What breaks if this is deleted: the button is drawn for everybody the report is shown to,
    // and the route refuses the confirmed write with a sentence that reads like a fault.
    const { container } = await mount({
      report: report(),
      controls: controls({ may_release: false, may_hold: false }),
    });

    expect(button(container, RELEASE_LABEL)).toBeNull();
    expect(container.textContent).toContain(RELEASE_NOT_YOURS);
    expect(container.querySelector(`form[aria-label="${HOLD_FORM_LABEL}"]`)).toBeNull();
    expect(container.textContent).toContain(HOLD_NOT_YOURS);
  });

  test("a released sweep offers the withdrawal and not a second release", async () => {
    // What breaks if this is deleted: a second release is offered and refused as already
    // released, and the one control that stops the sweep acting is missing.
    const { container, idp } = await mount({
      report: report({ released: true }),
      controls: controls(),
    });

    expect(button(container, RELEASE_LABEL)).toBeNull();
    fireEvent.click(button(container, WITHDRAW_LABEL) as HTMLButtonElement);
    expect(container.querySelector(".confirm")?.textContent).toContain("WITHDRAWING-SENTENCE");
    fireEvent.click(
      [...container.querySelectorAll(".confirm button")].find(
        (one) => one.textContent === WITHDRAW_LABEL,
      ) as HTMLButtonElement,
    );
    await waitFor(() => {
      expect(posts(idp).map((one) => one.path)).toEqual([WITHDRAWAL_OPERATION]);
    });
  });

  test("no report draws no release and says either reason in one sentence", async () => {
    // What breaks if this is deleted: a release offered with no report to name, or a sentence
    // telling a department reader that a report exists and is about more than they may see.
    const { container } = await mount({ report: null, controls: controls() });

    expect(container.textContent).toContain(NO_REPORT);
    expect(button(container, RELEASE_LABEL)).toBeNull();
  });

  test("the counts name only the stores the sweep reaches", () => {
    // What breaks if this is deleted: a store the sweep cannot reach is named beside a removal.
    expect(releaseCounts(report(), "then")).toBe(
      "As of then, 7 items were past their window in ledger; 3 were queued for the rule that " +
        "removes them and 2 were held.",
    );
  });
});

describe("legal holds", () => {
  test("a hold with problems says what to change and sends nothing", async () => {
    const { container, idp } = await mount({ report: report(), controls: controls() });
    const form = container.querySelector(`form[aria-label="${HOLD_FORM_LABEL}"]`) as HTMLFormElement;

    fireEvent.submit(form);

    expect(container.querySelector("[role='alert']")?.textContent).toContain("reason code");
    expect(container.querySelector(".confirm")).toBeNull();
    expect(posts(idp)).toEqual([]);
  });

  test("a valid hold is confirmed with who it covers and the API's sentence, then sent", async () => {
    // What breaks if this is deleted: a hold is placed on the first click, or its confirmation
    // does not say that the sweep stops removing anything about the people named.
    const { container, idp } = await mount({ report: report(), controls: controls() });
    const form = container.querySelector(`form[aria-label="${HOLD_FORM_LABEL}"]`) as HTMLFormElement;
    fireEvent.change(field(form, "Reference"), { target: { value: "matter-9" } });
    fireEvent.change(field(form, "Reason code"), { target: { value: "litigation" } });
    fireEvent.change(field(form, "People it covers"), { target: { value: "u_1, u_2" } });

    fireEvent.submit(form);
    const confirmation = container.querySelector(".confirm")?.textContent ?? "";
    expect(confirmation).toContain("Place legal hold matter-9 over 2 named people?");
    expect(confirmation).toContain("HOLDING-SENTENCE");
    expect(posts(idp)).toEqual([]);

    fireEvent.click(
      [...container.querySelectorAll(".confirm button")].find(
        (one) => one.textContent === PLACE_LABEL,
      ) as HTMLButtonElement,
    );
    await waitFor(() => {
      expect(posts(idp)).toEqual([
        {
          path: HOLD_OPERATION,
          body: {
            hold_id: "matter-9",
            reason_code: "litigation",
            subjects: ["u_1", "u_2"],
            actors: [],
            all_subjects: false,
          },
        },
      ]);
    });
  });

  test("lifting a hold is confirmed with the API's sentence, then sent by reference", async () => {
    const { container, idp } = await mount({ report: report(), controls: controls() });
    const form = container.querySelector(`form[aria-label="${LIFT_FORM_LABEL}"]`) as HTMLFormElement;
    fireEvent.change(field(form, "Reference of the hold"), { target: { value: "matter-7" } });

    fireEvent.submit(form);
    expect(container.querySelector(".confirm")?.textContent).toContain("LIFTING-SENTENCE");
    fireEvent.click(
      [...container.querySelectorAll(".confirm button")].find(
        (one) => one.textContent === LIFT_LABEL,
      ) as HTMLButtonElement,
    );
    await waitFor(() => {
      expect(posts(idp)).toEqual([{ path: LIFT_OPERATION, body: { hold_id: "matter-7" } }]);
    });
  });
});

describe("what is kept and what is not recorded", () => {
  test("the windows, the export log and the deletion queue are drawn as the API sent them", async () => {
    // What breaks if this is deleted: the export log or the deletion queue becomes an empty table,
    // which reads as nothing having left and nobody having asked to be forgotten.
    const { container } = await mount({ report: null, controls: controls() });

    expect(container.textContent).toContain("PAYLOAD-BECAUSE");
    expect(container.textContent).toContain("EXPORTS-SENTENCE");
    expect(container.textContent).toContain("ERASURES-SENTENCE");
  });
});
