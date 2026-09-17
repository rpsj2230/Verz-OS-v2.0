/**
 * The Import and export screen: what can move, the export form, its confirmation, and what happens
 * to the document.
 *
 * Mounted directly on a memory router at its own address, for the reason
 * `tests/sessions-page.test.tsx` gives. The failures worth testing look like the screen working: an
 * export sent without its confirmation, a body key the route does not declare, a last day that is
 * not included, a document drawn on the screen, and a form offered to a reader the API said may
 * not export.
 *
 * Task ids: M27.8.16
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, test, vi } from "vitest";
import {
  EXPORT_LABEL,
  KEEP_LABEL,
  NOT_EXPORTABLE,
  NO_EXPORTS,
  READING_DATA_TRANSFER,
} from "../src/pages/DataTransfer";
import {
  CHAIN_BROKEN,
  NOT_A_CHAIN,
  READABLE_WINDOW,
  windowOf,
  type DataTransferBody,
} from "../src/pages/dataTransferQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { declaredRequestBodySchema } from "./support/openapi";

const LISTING = "/api/v1/data-transfer";
const TAKE = "/api/v1/data-transfer/exports";
const CONSOLE_ORIGIN = "https://console.test";
const DOCUMENT = '{"format":"brain.audit.export.v1"}\n{"seq":0,"DOCUMENT-SENTINEL":true}\n';
const EXPORT_TOLD = "An export is a copy of the company's records.";
const DOCUMENT_TOLD = "The document is handed to you once and is not kept on the server.";

beforeAll(async () => {
  await import("../src/pages/DataTransfer");
}, 60_000);

afterEach(() => {
  vi.unstubAllGlobals();
});

function listing(overrides: Partial<DataTransferBody> = {}): DataTransferBody {
  return {
    catalogue: [
      { key: "audit_trail", label: "Audit trail", direction: "export", carries: "A window", runs: true, told: "Checkable without this system." },
      { key: "knowledge", label: "Knowledge", direction: "export", carries: "Items", runs: false, told: "Not available yet. Nothing stores an item." },
      { key: "skills", label: "Skills", direction: "import", carries: "A skill", runs: false, told: "Not available yet. Nothing stores a skill." },
    ],
    reasons: ["legal_discovery", "regulatory_request"],
    exportable: true,
    form: "chain",
    form_told: "CHAIN-FORM-TOLD",
    exports: [],
    export_told: EXPORT_TOLD,
    document_told: DOCUMENT_TOLD,
    own_exports_told: "The exports listed here are the ones you took.",
    max_entries: 50000,
    ...overrides,
  };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

async function mount(
  answer: (url: URL) => Response | null,
): Promise<{ container: HTMLElement; idp: FakeIdp }> {
  const idp = fakeIdentityProvider({
    api(url) {
      return answer(new URL(url, CONSOLE_ORIGIN));
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { DataTransfer } = await import("../src/pages/DataTransfer");
  const router = createMemoryRouter([{ path: "/import-export", element: <DataTransfer /> }], {
    initialEntries: ["/import-export"],
  });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (container.textContent?.includes(READING_DATA_TRANSFER)) {
      throw new Error("still reading");
    }
  });
  return { container, idp };
}

function posts(idp: FakeIdp): { url: URL; body: unknown }[] {
  return idp.calls
    .filter((call) => call.init?.method === "POST" && new URL(call.url, CONSOLE_ORIGIN).pathname.startsWith("/api/"))
    .map((call) => ({
      url: new URL(call.url, CONSOLE_ORIGIN),
      body: JSON.parse(String(call.init?.body ?? "null")) as unknown,
    }));
}

function field(container: HTMLElement, label: string): HTMLInputElement | HTMLSelectElement {
  const found = [...container.querySelectorAll("label")].find((one) => one.textContent?.trim().startsWith(label));
  const control = found?.querySelector("input, select");
  if (!control) {
    throw new Error(`no field labelled ${label}`);
  }
  return control as HTMLInputElement | HTMLSelectElement;
}

function button(scope: ParentNode, name: string): HTMLButtonElement {
  const found = [...scope.querySelectorAll("button")].find((one) => one.textContent === name);
  if (!found) {
    throw new Error(`no button named ${name}`);
  }
  return found as HTMLButtonElement;
}

function fill(container: HTMLElement): void {
  fireEvent.change(field(container, "Reason"), { target: { value: "regulatory_request" } });
  fireEvent.change(field(container, "Reference of the written request"), { target: { value: "MATTER-1" } });
  fireEvent.change(field(container, "First day"), { target: { value: "2019-03-04" } });
  fireEvent.change(field(container, "Last day"), { target: { value: "2019-03-05" } });
}

describe("what the import and export screen shows", () => {
  test("every data set is listed with whether it can move today and why not", async () => {
    // What breaks if this is deleted: a data set that cannot move drawn with no reason, which reads
    // as an option somebody forgot to switch on.
    const { container } = await mount((url) => (url.pathname === LISTING ? json(listing()) : null));
    expect(container.querySelector('[aria-label="Export"]')?.textContent).toContain("Not available yet. Nothing stores an item.");
    expect(container.querySelector('[aria-label="Import"]')?.textContent).toContain("Nothing stores a skill.");
    expect(container.textContent).toContain(NO_EXPORTS);
  });

  test("a reader who may not export is told why and offered no form", async () => {
    // What breaks if this is deleted: the export form drawn for a reader the route will refuse.
    const { container } = await mount((url) =>
      url.pathname === LISTING ? json(listing({ exportable: false })) : null,
    );
    expect(container.textContent).toContain(NOT_EXPORTABLE);
    expect(container.querySelector(`[aria-label="${EXPORT_LABEL}"]`)).toBeNull();
  });

  test("a reader who takes the entries they may read is told so, and their exports name no window or verdict", async () => {
    // What breaks if this is deleted: a readable export drawn with an empty window and a verdict of
    // broken, which reads as a tampered ledger, or the screen promising a chain the reader will not
    // receive.
    const { container } = await mount((url) =>
      url.pathname === LISTING
        ? json(
            listing({
              form: "readable",
              form_told: "READABLE-FORM-TOLD",
              exports: [
                {
                  export_id: "22222222-2222-4222-8222-222222222222",
                  data_set: "audit_trail",
                  reason: "regulatory_request",
                  reason_reference: "MATTER-2",
                  produced_at: "2019-03-06T00:00:00Z",
                  form: "readable",
                  first_seq: null,
                  last_seq: null,
                  entries: 3,
                  verified: null,
                  document_digest: "b".repeat(64),
                },
              ],
            }),
          )
        : null,
    );
    expect(container.textContent).toContain("READABLE-FORM-TOLD");
    expect(container.textContent).not.toContain("CHAIN-FORM-TOLD");
    const row = container.querySelector('[aria-label="Your exports"] tbody tr');
    expect(row?.textContent).toContain(READABLE_WINDOW);
    expect(row?.textContent).toContain(NOT_A_CHAIN);
    expect(row?.textContent).not.toContain(CHAIN_BROKEN);
  });

  test("a window of whole days includes the last day chosen", () => {
    // What breaks if this is deleted: the last day's entries are left out of every export.
    expect(windowOf("2019-03-04", "2019-03-05")).toEqual({
      since: "2019-03-04T00:00:00.000Z",
      until: "2019-03-06T00:00:00.000Z",
    });
    expect(windowOf("", "2019-03-05")).toBeNull();
  });
});

describe("what the import and export screen does", () => {
  test("an export is confirmed in the API's words, sends the route's five fields, and saves the document as a file", async () => {
    // What breaks if this is deleted: an export taken with no second step, a body key the route
    // refuses, or the document drawn on the screen rather than saved.
    const created = vi.fn(() => "blob:document");
    const revoked = vi.fn();
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: created, revokeObjectURL: revoked }));
    const clicked = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const { container, idp } = await mount((url) => {
      if (url.pathname === TAKE) {
        return json({
          export: {
            export_id: "11111111-1111-4111-8111-111111111111",
            data_set: "audit_trail",
            reason: "regulatory_request",
            reason_reference: "MATTER-1",
            produced_at: "2019-03-06T00:00:00Z",
            form: "chain",
            first_seq: 0,
            last_seq: 1,
            entries: 2,
            verified: true,
            document_digest: "a".repeat(64),
          },
          filename: "audit_trail-0-1.jsonl",
          document: DOCUMENT,
          told: "The export was recorded in the audit trail under your name.",
        });
      }
      return url.pathname === LISTING ? json(listing()) : null;
    });
    const declared = declaredRequestBodySchema(TAKE, "post");

    fill(container);
    fireEvent.submit(container.querySelector(`[aria-label="${EXPORT_LABEL}"]`) as HTMLFormElement);
    const panel = container.querySelector(".confirm") as HTMLElement;
    expect(panel.textContent).toContain(EXPORT_TOLD);
    expect(panel.textContent).toContain(DOCUMENT_TOLD);
    expect(posts(idp)).toEqual([]);

    fireEvent.click(button(panel, EXPORT_LABEL));
    await waitFor(() => {
      expect(container.textContent).toContain("recorded in the audit trail under your name");
    });
    const [sent] = posts(idp);
    expect(Object.keys(sent?.body as object).sort()).toEqual(Object.keys(declared["properties"] as object).sort());
    expect(sent?.body).toEqual({
      data_set: "audit_trail",
      reason: "regulatory_request",
      reason_reference: "MATTER-1",
      since: "2019-03-04T00:00:00.000Z",
      until: "2019-03-06T00:00:00.000Z",
    });
    expect(created).toHaveBeenCalledTimes(1);
    expect(clicked).toHaveBeenCalledTimes(1);
    expect(revoked).toHaveBeenCalledWith("blob:document");
    expect(container.innerHTML).not.toContain("DOCUMENT-SENTINEL");
    clicked.mockRestore();
  });

  test("keeping things sends nothing, and a refused window is shown beside the days", async () => {
    // What breaks if this is deleted: a cancel that exports anyway, or a 422 about the window drawn
    // as a generic failure.
    const { container, idp } = await mount((url) => {
      if (url.pathname === TAKE) {
        return json({ problems: [{ field: "window", code: "window_refused", message: "Nothing was recorded in this window." }] }, 422);
      }
      return url.pathname === LISTING ? json(listing()) : null;
    });
    fill(container);
    fireEvent.submit(container.querySelector(`[aria-label="${EXPORT_LABEL}"]`) as HTMLFormElement);
    fireEvent.click(button(container.querySelector(".confirm") as HTMLElement, KEEP_LABEL));
    expect(container.querySelector(".confirm")).toBeNull();
    expect(posts(idp)).toEqual([]);

    fireEvent.submit(container.querySelector(`[aria-label="${EXPORT_LABEL}"]`) as HTMLFormElement);
    fireEvent.click(button(container.querySelector(".confirm") as HTMLElement, EXPORT_LABEL));
    await waitFor(() => {
      expect(container.querySelector('[aria-label="Problems with window"]')?.textContent).toContain(
        "Nothing was recorded in this window.",
      );
    });
  });
});
