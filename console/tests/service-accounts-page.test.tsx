/**
 * Service accounts on the shared page kit: the list of the reader's own accounts, one account's
 * page, and the four acts (register, issue a key shown once, revoke, retire), each confirmed.
 *
 * The failures worth testing are not layout ones: a key reaching anywhere but the drawer that
 * issued it, a write sent without its confirmation, a body naming an owner, a form saying what it
 * accepts only after a refusal, a handle or an id in page text outside Advanced, and an act called
 * "coming soon" whose route has arrived.
 *
 * **Reachable means through the application's own route table**, as `connectors-page.test.tsx`
 * mounts it, so a test passes only if the address resolves.
 *
 * Task ids: M27.11.5, M27.15.26, M27.16.1
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { HINTS, KEPT_LABEL, REVIEW } from "../src/pages/service-accounts/AccountActs";
import { ACT_LABELS, NOT_HELD_MARK, UNAVAILABLE } from "../src/pages/service-accounts/serviceAccountActions";
import { BLANK_SENTENCES } from "../src/pages/serviceAccountsQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { apiDocument, declaredPropertyNames, declaredRequestBodySchema } from "./support/openapi";
import { installRadixStubs } from "./support/radix";

const CONSOLE_ORIGIN = "https://console.test";
const SECRET = "brn.KEY-SENTINEL.9f3c";
const HANDLE = "hdl_sentinel_1";

beforeAll(async () => {
  installRadixStubs();
  await import("../src/pages/ServiceAccount");
}, 60_000);

function anAccount(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    client_id: "svc_weekly_report",
    label: "Weekly report",
    ceiling: ["read:client.hours", "read:client.margin"],
    lapses_at: "2999-03-04T09:00:00Z",
    created_at: "2019-03-04T09:00:00Z",
    keys: [{ handle: HANDLE, label: "Reporting server", issued_at: "2019-03-04T09:00:00Z", lapses_at: "2999-03-04T09:00:00Z" }],
    not_held_now: ["read:client.margin"],
    ...over,
  };
}

const LIST = { items: [anAccount()], truncated: false, next_cursor: null, reach: "REACH", ownership: "OWNERSHIP" };

interface Mounted {
  readonly container: HTMLElement;
  readonly idp: FakeIdp;
  readonly router: ReturnType<typeof createMemoryRouter>;
}

async function consoleAt(path: string, gets: Readonly<Record<string, { status?: number; body: unknown }>> = {}): Promise<Mounted> {
  const answers: Record<string, { status?: number; body: unknown }> = {
    "/api/v1/govern/service-accounts": { body: LIST },
    "/api/v1/govern/service-accounts/svc_weekly_report": { body: anAccount() },
    ...gets,
  };
  const idp = fakeIdentityProvider({
    api(url, init) {
      const pathname = new URL(url, CONSOLE_ORIGIN).pathname;
      const reply = (body: unknown, status = 200) =>
        new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
      if (init?.method === "POST") {
        if (pathname === "/api/v1/govern/service-accounts/keys") {
          return reply({ client_id: "svc_weekly_report", handle: "hdl_new", key: SECRET, lapses_at: "2999-01-01T00:00:00Z", shown_once: "SHOWN-ONCE" }, 201);
        }
        if (pathname === "/api/v1/govern/service-accounts") {
          return reply({ ...anAccount({ client_id: "svc_new", label: "", keys: [] }) }, 201);
        }
        return reply({ told: "TOLD-SENTENCE" });
      }
      const answer = answers[pathname];
      return answer === undefined ? null : reply(answer.body, answer.status ?? 200);
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const { container } = render(<RouterProvider router={router} />);
  await settle(container);
  return { container, idp, router };
}

async function settle(container: HTMLElement): Promise<void> {
  await waitFor(() => {
    if (!container.querySelector("h1") || container.querySelector('[data-slot="loading-state"]')) {
      throw new Error("the page is still asking");
    }
  });
}

function posts(idp: FakeIdp): { path: string; body: unknown }[] {
  return idp.calls
    .filter((call) => call.init?.method === "POST" && new URL(call.url, CONSOLE_ORIGIN).pathname.startsWith("/api/"))
    .map((call) => ({
      path: new URL(call.url, CONSOLE_ORIGIN).pathname,
      body: call.init?.body === undefined ? undefined : (JSON.parse(String(call.init.body)) as unknown),
    }));
}

function outsideAdvanced(container: HTMLElement): string {
  const copy = container.cloneNode(true) as HTMLElement;
  copy.querySelectorAll('[data-slot="advanced"]').forEach((one) => {
    one.remove();
  });
  return copy.textContent ?? "";
}

async function confirmIn(name: string): Promise<void> {
  const dialog = await screen.findByRole("alertdialog");
  await act(async () => {
    fireEvent.click(within(dialog).getByRole("button", { name }));
  });
}

describe("what this module agrees with the API about", () => {
  test("no act the module calls coming soon has a route, and every body it sends is one the API declares", () => {
    // What breaks if this is deleted: "coming soon" said after the route lands, or a registration
    // that sends an owner field the route would take as lending somebody else's reach.
    const paths = Object.keys((apiDocument()["paths"] ?? {}) as Record<string, unknown>);
    for (const [one, { retiredBy }] of Object.entries(UNAVAILABLE)) {
      expect(paths.filter((path) => retiredBy.test(path)), one).toEqual([]);
    }
    expect(UNAVAILABLE.changeEnd.retiredBy.test("/api/v1/govern/service-accounts/{client_id}/end")).toBe(true);
    expect(paths).toContain("/api/v1/govern/service-accounts/{client_id}");
    const registration = declaredPropertyNames(declaredRequestBodySchema("/api/v1/govern/service-accounts", "post"));
    expect(registration).not.toContain("owner");
    expect(registration).not.toContain("owner_principal_id");
  });
});

describe("the list", () => {
  test("draws the reader's accounts by name, with no key handle, and each capability they cannot use marked", async () => {
    // What breaks if this is deleted: identifiers back in the table, or a ceiling drawn as if every
    // capability worked when the owner no longer holds one.
    const { container } = await consoleAt("/service-accounts");

    const text = outsideAdvanced(container);
    expect(text).toContain("Weekly report");
    expect(text).toContain("read:client.hours");
    expect(text).not.toContain(HANDLE);
    const chips = [...container.querySelectorAll('[data-slot="chip"]')].map((one) => one.textContent);
    expect(chips).toContain(`read:client.margin ${NOT_HELD_MARK}`);
    expect(chips).toContain("read:client.hours");
  });

  test("registering says what every field accepts first, refuses blanks beside them, and sends no owner", async () => {
    // What breaks if this is deleted: a form that teaches its format only by refusing, a blank sent
    // to the API, or a registration sent without its confirmation.
    const { container, idp, router } = await consoleAt("/service-accounts");

    await act(async () => {
      fireEvent.click(screen.getAllByRole("button", { name: new RegExp(ACT_LABELS.register) })[0] as HTMLElement);
    });
    const drawer = await screen.findByRole("dialog");
    expect(drawer.textContent).toContain(HINTS.client_id);
    expect(drawer.textContent).toContain(HINTS.ceiling);
    await act(async () => {
      fireEvent.click(within(drawer).getByRole("button", { name: REVIEW }));
    });
    expect(drawer.textContent).toContain(BLANK_SENTENCES.client_id);
    expect(drawer.textContent).toContain(BLANK_SENTENCES.ceiling);
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(posts(idp)).toEqual([]);

    fireEvent.change(within(drawer).getByLabelText("Account ID"), { target: { value: "svc_new" } });
    fireEvent.change(within(drawer).getByLabelText("Capabilities it may use"), { target: { value: "read:client.hours" } });
    fireEvent.change(within(drawer).getByLabelText("Stops working after"), { target: { value: "2999-01-01" } });
    await act(async () => {
      fireEvent.click(within(drawer).getByRole("button", { name: REVIEW }));
    });
    expect(posts(idp)).toEqual([]);
    await confirmIn(ACT_LABELS.register);

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/service-accounts/svc_new");
    });
    const [sent] = posts(idp);
    expect(sent?.path).toBe("/api/v1/govern/service-accounts");
    expect(Object.keys(sent?.body as object).sort()).toEqual(["ceiling", "client_id", "label", "not_after"]);
    expect(container).toBeTruthy();
  });
});

describe("one account's page", () => {
  test("shows its figures and keys, keeps handles in Advanced, and offers changing the end date as not yet available", async () => {
    // What breaks if this is deleted: a handle in page text, or an inert control drawn as live.
    const { container } = await consoleAt("/service-accounts/svc_weekly_report");

    expect(container.querySelector("h1")?.textContent).toBe("Weekly report");
    expect(outsideAdvanced(container)).not.toContain(HANDLE);
    expect(container.querySelector('[data-slot="advanced"]')?.textContent).toContain(HANDLE);
    expect(outsideAdvanced(container)).toContain("Reporting server");
    const unavailable = container.querySelector("[data-unavailable]");
    expect(unavailable?.textContent).toContain(ACT_LABELS.changeEnd);
  });

  test("revoking a key sends its handle only from the confirmation, and the page reads the account again", async () => {
    // What breaks if this is deleted: a revocation from one press, or a page that goes on drawing
    // a revoked key.
    const { idp } = await consoleAt("/service-accounts/svc_weekly_report");
    const before = idp.calls.filter((call) => new URL(call.url, CONSOLE_ORIGIN).pathname === "/api/v1/govern/service-accounts/svc_weekly_report").length;

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Revoke Reporting server" }));
    });
    expect(posts(idp)).toEqual([]);
    await confirmIn("Revoke key");

    await waitFor(() => {
      expect(posts(idp)).toEqual([{ path: "/api/v1/govern/service-accounts/keys/revoke", body: { handle: HANDLE } }]);
    });
    await waitFor(() => {
      const after = idp.calls.filter((call) => new URL(call.url, CONSOLE_ORIGIN).pathname === "/api/v1/govern/service-accounts/svc_weekly_report").length;
      expect(after).toBeGreaterThan(before);
    });
  });

  test("an issued key is shown once in its drawer and is gone from the page once kept", async () => {
    // What breaks if this is deleted: the key stays in the page after it was kept, or is drawn
    // anywhere but the answer that issued it.
    const { container, idp } = await consoleAt("/service-accounts/svc_weekly_report");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: new RegExp(`^${ACT_LABELS.issue}$`) }));
    });
    const drawer = await screen.findByRole("dialog");
    expect(drawer.textContent).toContain(HINTS.key_not_after);
    fireEvent.change(within(drawer).getByLabelText("Key stops working after"), { target: { value: "2999-01-01" } });
    await act(async () => {
      fireEvent.click(within(drawer).getByRole("button", { name: REVIEW }));
    });
    await confirmIn(ACT_LABELS.issue);
    await waitFor(() => {
      expect(screen.getByRole("dialog").textContent).toContain(SECRET);
    });
    expect(container.textContent).not.toContain(SECRET);

    await act(async () => {
      fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: KEPT_LABEL }));
    });
    await waitFor(() => {
      expect(document.body.textContent).not.toContain(SECRET);
    });
    expect(posts(idp).map((one) => one.path)).toEqual(["/api/v1/govern/service-accounts/keys"]);
  });

  test("retiring the account is confirmed and returns to the list", async () => {
    // What breaks if this is deleted: a retirement from one press, or a page left drawing an
    // account that no longer works.
    const { idp, router } = await consoleAt("/service-accounts/svc_weekly_report");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: ACT_LABELS.retire }));
    });
    expect(posts(idp)).toEqual([]);
    await confirmIn(ACT_LABELS.retire);

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/service-accounts");
    });
    expect(posts(idp)).toEqual([{ path: "/api/v1/govern/service-accounts/retire", body: { client_id: "svc_weekly_report" } }]);
  });

  test("an account the reader may not open is the API's sentence and nothing else", async () => {
    // What breaks if this is deleted: another person's account drawn, or a refusal worded
    // differently from an absence.
    const { container } = await consoleAt("/service-accounts/svc_someone_else", {
      "/api/v1/govern/service-accounts/svc_someone_else": {
        status: 404,
        body: { message: "I could not find that.", trace_id: "TRACE-SENTINEL" },
      },
    });

    expect(container.textContent).toContain("TRACE-SENTINEL");
    expect(container.textContent).not.toContain("svc_someone_else");
  });
});
