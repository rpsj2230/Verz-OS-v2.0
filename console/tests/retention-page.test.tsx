/**
 * Retention, legal holds and erasure on the page kit: the four views, the release and its
 * withdrawal, legal holds placed and lifted, the export log, and erasure requests filed and drawn as
 * they finished, each on a page of its own.
 *
 * Mounted through the page's own route file. The failures worth testing are the ones that look like
 * the screen working: a write sent without its confirmation, a confirmation that does not say what
 * the sweep will then do, a control drawn for somebody the API said may not act, a form that says
 * what it takes only after a refusal, and a hold that fails the route's own pattern only after it
 * was sent.
 *
 * Task ids: M27.7.24, M27.16.1
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  DO_NOT_FILE,
  ERASURE_FORM_LABEL,
  FILE_ERASURE_LABEL,
  HOLD_FORM_LABEL,
  LIFT_LABEL,
  PLACE_LABEL,
  RELEASE_LABEL,
  REVIEW_HOLD,
  REVIEW_REQUEST,
  WITHDRAW_LABEL,
} from "../src/pages/retention/RetentionActs";
import { NO_ERASURE, NO_HOLD } from "../src/pages/retention/RetentionDetail";
import {
  erasureAddress,
  ERASE_NOT_YOURS,
  FILE_ERASURE,
  holdAddress,
  HOLD_NOT_YOURS,
  NO_REPORT,
  PLACE_HOLD,
  READING_RETENTION,
  viewAddress,
} from "../src/pages/retention/RetentionPage";
import {
  REFERENCE_PATTERN,
  erasureBody,
  erasureProblems,
  type ErasureQueue,
  type ErasureRequest,
  type ExportLog,
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
import { installRadixStubs } from "./support/radix";
import { chooseInMenu, confirmWith } from "./support/rowMenu";

const CONSOLE_ORIGIN = "https://console.test";
const REPORT_OPERATION = "/api/v1/govern/retention";
const CONTROLS_OPERATION = "/api/v1/govern/retention/controls";
const RELEASE_OPERATION = "/api/v1/govern/retention/release";
const WITHDRAWAL_OPERATION = "/api/v1/govern/retention/withdrawal";
const HOLD_OPERATION = "/api/v1/govern/legal-holds";
const LIFT_OPERATION = "/api/v1/govern/legal-holds/lift";
const ERASURES_OPERATION = "/api/v1/govern/erasures";
const EXPORT_LOG_OPERATION = "/api/v1/govern/retention/exports";

beforeAll(async () => {
  installRadixStubs();
  await import("../src/pages/Retention");
}, 60_000);

function controls(overrides: Partial<Controls> = {}): Controls {
  return {
    may_release: true,
    may_hold: true,
    may_erase: true,
    may_read_exports: true,
    erasing: "ERASING-SENTENCE",
    exports_not_yours: "EXPORTS-NOT-YOURS",
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
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

interface Stand {
  report: Report | null;
  controls: Controls;
  queue?: ErasureQueue;
  exports?: ExportLog;
}

async function mount(stand: Stand, path = "/retention"): Promise<{ container: HTMLElement; idp: FakeIdp }> {
  const idp = fakeIdentityProvider({
    api(url, init) {
      const at = new URL(url, CONSOLE_ORIGIN).pathname;
      if (init?.method === "POST") {
        const answers: Record<string, unknown> = {
          [RELEASE_OPERATION]: { release_id: "22222222-2222-4222-8222-222222222222", after_report: stand.report?.report_id, released_at: "2019-03-05T10:00:00Z" },
          [WITHDRAWAL_OPERATION]: { withdrawn_at: "2019-03-05T10:00:00Z" },
          [HOLD_OPERATION]: { hold_id: "matter-9", placed_at: "2019-03-05T10:00:00Z" },
          [LIFT_OPERATION]: { hold_id: "matter-7", lifted_at: "2019-03-05T10:00:00Z" },
          [ERASURES_OPERATION]: { request_id: "r-new", subject_id: "u_1", requested_at: "2019-03-05T10:00:00Z" },
        };
        return at in answers ? json(answers[at]) : null;
      }
      const reads: Record<string, unknown> = {
        [REPORT_OPERATION]: { report: stand.report },
        [CONTROLS_OPERATION]: stand.controls,
        [ERASURES_OPERATION]: stand.queue ?? { requests: [], people: {} },
        [EXPORT_LOG_OPERATION]: stand.exports ?? { exports: [], people: {} },
      };
      return at in reads ? json(reads[at]) : null;
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/pages/Retention.route");
  const router = createMemoryRouter(routes.map((one) => ({ path: `/${one.path}`, element: one.element })), { initialEntries: [path] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if ((container.textContent ?? "").includes(READING_RETENTION) || container.querySelector("h1") === null) {
      throw new Error("still reading");
    }
  });
  return { container, idp };
}

function posts(idp: FakeIdp): { path: string; body: unknown }[] {
  return idp.calls
    .filter((call) => call.init?.method === "POST" && new URL(call.url, CONSOLE_ORIGIN).pathname.startsWith("/api/"))
    .map((call) => ({ path: new URL(call.url, CONSOLE_ORIGIN).pathname, body: call.init?.body === undefined ? undefined : (JSON.parse(String(call.init.body)) as unknown) }));
}

function asked(idp: FakeIdp, operation: string): number {
  return idp.urls.filter((url) => new URL(url, CONSOLE_ORIGIN).pathname === operation).length;
}

async function drawerForm(label: string): Promise<HTMLFormElement> {
  return (await screen.findByRole("form", { name: label })) as HTMLFormElement;
}

function type(form: HTMLElement, name: string, value: string): void {
  fireEvent.change(form.querySelector(`[name="${name}"]`) as HTMLInputElement, { target: { value } });
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
    // What breaks if this is deleted: the sweep is released on the first press, or the confirmation
    // does not say what the next run removes.
    const { container, idp } = await mount({ report: report(), controls: controls() });
    fireEvent.click(screen.getByRole("button", { name: RELEASE_LABEL }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain("7 items were past their window in ledger");
    expect(dialog.textContent).toContain("RELEASING-SENTENCE");
    expect(posts(idp)).toEqual([]);
    await confirmWith(RELEASE_LABEL);

    await waitFor(() => {
      expect(container.textContent).toContain("The sweep was released at");
    });
    expect(posts(idp)).toEqual([{ path: RELEASE_OPERATION, body: { after_report: report().report_id } }]);
    expect(releaseCounts(report(), "then")).not.toContain("recording");
  });

  test("a reader the API says may not release is drawn no release, and a released sweep offers only the withdrawal", async () => {
    // What breaks if this is deleted: a control drawn for somebody the API said may not act, or a
    // second release offered on a released sweep.
    await mount({ report: report(), controls: controls({ may_release: false }) });
    expect(screen.queryByRole("button", { name: RELEASE_LABEL })).toBeNull();

    const released = await mount({ report: report({ released: true }), controls: controls() });
    expect(within(released.container).queryByRole("button", { name: RELEASE_LABEL })).toBeNull();
    fireEvent.click(within(released.container).getByRole("button", { name: WITHDRAW_LABEL }));
    await confirmWith(WITHDRAW_LABEL);
    await waitFor(() => {
      expect(posts(released.idp)).toEqual([{ path: WITHDRAWAL_OPERATION, body: undefined }]);
    });
  });

  test("no report is one sentence, and the windows are still drawn as the API sent them", async () => {
    const { container } = await mount({ report: null, controls: controls() });
    expect(container.textContent).toContain(NO_REPORT);
    expect(container.textContent).toContain("PAYLOAD-BECAUSE");
    expect(screen.queryByRole("button", { name: RELEASE_LABEL })).toBeNull();
  });
});

describe("legal holds", () => {
  test("a hold says what each field takes, and one with problems says what to change and sends nothing", async () => {
    // What breaks if this is deleted: validation only on the server, after the confirmation, or a
    // form that says what it accepts only after a refusal.
    const { idp } = await mount({ report: report(), controls: controls() }, viewAddress("holds"));
    fireEvent.click(screen.getByRole("button", { name: PLACE_HOLD }));
    const form = await drawerForm(HOLD_FORM_LABEL);
    expect(form.textContent).toContain("such as the matter number it is for");
    fireEvent.click(screen.getByRole("button", { name: REVIEW_HOLD }));
    await waitFor(() => {
      expect(form.textContent).toContain("A hold that names nobody holds nothing.");
    });
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(posts(idp)).toEqual([]);
  });

  test("a valid hold is confirmed with who it covers and the API's sentence, then sent as the route declares", async () => {
    const { idp } = await mount({ report: report(), controls: controls() }, viewAddress("holds"));
    fireEvent.click(screen.getByRole("button", { name: PLACE_HOLD }));
    const form = await drawerForm(HOLD_FORM_LABEL);
    type(form, "hold_id", "matter-9");
    type(form, "reason_code", "litigation");
    type(form, "subjects", "u_1, u_2");
    fireEvent.submit(form);
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain("Place legal hold matter-9 over 2 named people?");
    expect(dialog.textContent).toContain("HOLDING-SENTENCE");
    await confirmWith(PLACE_LABEL);

    await waitFor(() => {
      expect(posts(idp)).toHaveLength(1);
    });
    expect(posts(idp)[0]).toEqual({
      path: HOLD_OPERATION,
      body: { hold_id: "matter-9", reason_code: "litigation", subjects: ["u_1", "u_2"], actors: [], all_subjects: false },
    });
  });

  test("lifting a hold from its row is confirmed with the API's sentence, then sent by reference", async () => {
    const { idp } = await mount({ report: report(), controls: controls() }, viewAddress("holds"));
    await chooseInMenu(screen.getByRole("button", { name: "Actions for legal hold matter-7" }), LIFT_LABEL);
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain("LIFTING-SENTENCE");
    expect(posts(idp)).toEqual([]);
    await confirmWith(LIFT_LABEL);
    await waitFor(() => {
      expect(posts(idp)).toEqual([{ path: LIFT_OPERATION, body: { hold_id: "matter-7" } }]);
    });
  });

  test("a hold has its own page, and one the report does not cite is one sentence", async () => {
    // What breaks if this is deleted: a hold's page reaches past what the report cites, or says
    // whether a guessed reference exists.
    const shown = await mount({ report: report(), controls: controls() }, holdAddress("matter-7"));
    expect(shown.container.querySelector("h1")?.textContent).toBe("Legal hold matter-7");
    expect(shown.container.textContent).toContain("HOLDING-SENTENCE");

    const absent = await mount({ report: report(), controls: controls() }, holdAddress("matter-99"));
    expect(absent.container.querySelector("h1")?.textContent).toBe(NO_HOLD);
  });

  test("a reader the API says may not hold is drawn no control and told why", async () => {
    const { container } = await mount({ report: report(), controls: controls({ may_hold: false }) }, viewAddress("holds"));
    expect(container.textContent).toContain(HOLD_NOT_YOURS);
    expect(screen.queryByRole("button", { name: PLACE_HOLD })).toBeNull();
  });
});

describe("exports", () => {
  test("a reader who may not read exports is told so in the API's sentence, and the log is never asked for", async () => {
    const { container, idp } = await mount({ report: report(), controls: controls({ may_read_exports: false }) }, viewAddress("exports"));
    expect(container.textContent).toContain("EXPORTS-NOT-YOURS");
    expect(asked(idp, EXPORT_LOG_OPERATION)).toBe(0);
  });

  test("an export is drawn with who took it by name, why, and what it holds", async () => {
    const { container } = await mount(
      {
        report: report(),
        controls: controls(),
        exports: {
          exports: [
            {
              export_id: "e-1",
              data_set: "access_certification",
              requested_by: "u_exporter_19",
              reason: "regulatory_request",
              reason_reference: "AUDIT-1",
              produced_at: "2019-03-05T10:00:00Z",
              form: "readable",
              first_seq: null,
              last_seq: null,
              entries: 4,
              verified: null,
              document_digest: "d".repeat(64),
            },
          ],
          people: { u_exporter_19: "Ezra Exporter" },
        } as ExportLog,
      },
      viewAddress("exports"),
    );
    await waitFor(() => {
      expect(container.textContent).toContain("Ezra Exporter");
    });
    expect(container.textContent).toContain("AUDIT-1");
    expect(container.textContent).toContain("access certification");
    expect(container.textContent).not.toContain("u_exporter_19");
  });
});

describe("erasure requests", () => {
  test("a request is checked against the patterns the route itself declares", () => {
    // What breaks if this is deleted: a pattern here drifts from the table's, and a request the page
    // accepted is refused with a 422 after the administrator confirmed an erasure.
    const body = declaredRequestBodySchema(ERASURES_OPERATION, "post");
    expect(Object.keys(body["properties"] as object).sort()).toEqual(
      Object.keys(erasureBody({ subject: "a", reference: "b" })).sort(),
    );
    expect(declaredPropertySchema(ERASURES_OPERATION, "post", "subject_id")["pattern"]).toBe(
      IDENTIFIER_PATTERN,
    );
    expect(declaredPropertySchema(ERASURES_OPERATION, "post", "reason_reference")["pattern"]).toBe(
      REFERENCE_PATTERN,
    );
    expect(erasureProblems({ subject: "u leaver", reference: "because she left" })).toHaveLength(2);
    expect(erasureProblems({ subject: " u_leaver ", reference: "DSAR-7" })).toEqual([]);
  });

});

describe("erasure requests on the page", () => {
  test("a request with problems says what to change and sends nothing", async () => {
    const { idp } = await mount({ report: null, controls: controls() }, viewAddress("erasures"));
    fireEvent.click(screen.getByRole("button", { name: FILE_ERASURE }));
    const form = await drawerForm(ERASURE_FORM_LABEL);
    expect(form.textContent).toContain("such as DSAR-2019/004");
    fireEvent.click(screen.getByRole("button", { name: REVIEW_REQUEST }));
    await waitFor(() => {
      expect(form.textContent).toContain("matter or ticket reference");
    });
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(posts(idp)).toEqual([]);
  });

  test("a valid request is confirmed with the person and the API's sentence, then sent", async () => {
    // What breaks if this is deleted: an erasure is filed on the first click.
    const { idp } = await mount({ report: null, controls: controls() }, viewAddress("erasures"));
    fireEvent.click(screen.getByRole("button", { name: FILE_ERASURE }));
    const form = await drawerForm(ERASURE_FORM_LABEL);
    type(form, "subject_id", " u_leaver ");
    type(form, "reason_reference", "DSAR-7");
    fireEvent.submit(form);
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain("u_leaver");
    expect(dialog.textContent).toContain("ERASING-SENTENCE");
    expect(within(dialog).getByRole("button", { name: DO_NOT_FILE })).toBeTruthy();
    await confirmWith(FILE_ERASURE_LABEL);
    await waitFor(() => {
      expect(posts(idp)).toEqual([{ path: ERASURES_OPERATION, body: { subject_id: "u_leaver", reason_reference: "DSAR-7" } }]);
    });
  });

  test("a reader the API says may not erase is drawn no control and told why", async () => {
    const { container } = await mount({ report: null, controls: controls({ may_erase: false }) }, viewAddress("erasures"));
    expect(container.textContent).toContain(ERASE_NOT_YOURS);
    expect(screen.queryByRole("button", { name: FILE_ERASURE })).toBeNull();
  });

  test("a finished request's own page says store by store what was removed, retired, kept and not reached", async () => {
    // What breaks if this is deleted: a request that finished incomplete reads as erased, with
    // nothing saying which store still holds the person's data.
    const finished: ErasureRequest = {
      request_id: "r-1",
      subject_id: "u_leaver",
      reason_reference: "DSAR-7",
      requested_by: "u_filer_3",
      requested_at: "2019-03-04T09:00:00Z",
      finished_at: "2019-03-04T10:00:00Z",
      outcome: "incomplete",
      stores: [
        { store: "memory", disposition: "retire", reached: true, removed: 0, retired: 3, kept: 0, because: "" },
        { store: "ledger", disposition: "retained", reached: true, removed: 0, retired: 0, kept: 0, because: "" },
        { store: "cache", disposition: "remove", reached: false, removed: 0, retired: 0, kept: 0, because: "UNREACHED" },
      ],
      holds: [],
    } as ErasureRequest;
    const { container } = await mount({ report: null, controls: controls(), queue: { requests: [finished], people: { u_filer_3: "Fiona Filer" } } as ErasureQueue }, erasureAddress("r-1"));
    expect(container.textContent).toContain("memory: 3 retired and still stored");
    expect(container.textContent).toContain("cache: not reached, because UNREACHED");
    expect(container.textContent).toContain("Not reached by any erasure: ledger.");
    expect(container.textContent).toContain("Fiona Filer");

    const absent = await mount({ report: null, controls: controls() }, erasureAddress("r-9"));
    expect(absent.container.querySelector("h1")?.textContent).toBe(NO_ERASURE);
  });
});
