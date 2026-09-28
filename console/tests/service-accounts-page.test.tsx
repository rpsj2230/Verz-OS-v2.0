/**
 * The Service accounts screen: the list, registering, a key issued and shown once, a key revoked
 * and an account retired.
 *
 * Mounted directly on a memory router at its own address, for the reason
 * `tests/audit-page.test.tsx` gives. The failures worth testing look like the screen working: a key
 * still on the page after the person said they kept it, a key in a request or in the browser's
 * storage, a body carrying an owner, a revoke or a retire sent from one press, and the API's refusal
 * of an approve or admin capability paraphrased or lost.
 *
 * Task ids: M27.11.5, M27.15.26
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, test, vi } from "vitest";
import {
  CONFIRM_RETIRE_LABEL,
  CONFIRM_REVOKE_LABEL,
  COPIED,
  COPY_LABEL,
  CEILING_LABEL,
  ENDS_LABEL,
  ID_LABEL,
  ISSUE_BUTTON,
  ISSUE_LABEL,
  KEEP_LABEL,
  KEPT_LABEL,
  KEY_ENDS_LABEL,
  NO_ACCOUNTS,
  READING_ACCOUNTS,
  RETIRE_LABEL,
  REVOKE_LABEL,
} from "../src/pages/ServiceAccounts";
import {
  BLANK_SENTENCES,
  endOfDay,
  type AccountRow,
} from "../src/pages/serviceAccountsQuery";
import { routes } from "../src/App";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { LIST_PAGE_SIZE } from "../src/components/listing";
import { declaredParameterSchema, declaredQueryParameters, declaredRequestBodySchema } from "./support/openapi";

const LIST_OPERATION = "/api/v1/govern/service-accounts";
const KEYS_OPERATION = "/api/v1/govern/service-accounts/keys";
const REVOKE_OPERATION = "/api/v1/govern/service-accounts/keys/revoke";
const RETIRE_OPERATION = "/api/v1/govern/service-accounts/retire";
const CONSOLE_ORIGIN = "https://console.test";
const REACH = "A service account acts at your reach, narrowed to the capabilities it lists.";
const OWNERSHIP = "Only its owner may make it, give it a key, take a key away or retire it.";
const SECRET = "brn.h4ndle01.s3cr3t-never-listed-anywhere-else";
const SHOWN_ONCE = "This is the only time the key is shown.";
const NEVER_APPROVE_OR_ADMIN = "A service account can never carry an approve or admin capability.";

beforeAll(async () => {
  await import("../src/pages/ServiceAccounts");
}, 60_000);

afterEach(() => {
  Reflect.deleteProperty(navigator, "clipboard");
});

function account(overrides: Partial<AccountRow> & { client_id: string }): AccountRow {
  return {
    label: "Weekly report",
    ceiling: ["read:invoice", "read:margin"],
    lapses_at: "2999-03-04T09:00:00Z",
    created_at: "2019-03-04T09:00:00Z",
    keys: [],
    not_held_now: ["read:margin"],
    ...overrides,
  };
}

function page(items: AccountRow[]): unknown {
  return { items, truncated: false, reach: REACH, ownership: OWNERSHIP };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

type Answer = (url: URL, init: RequestInit | undefined) => Response | null;

async function mount(answer: Answer): Promise<{ container: HTMLElement; idp: FakeIdp }> {
  const idp = fakeIdentityProvider({
    api(url, init) {
      return answer(new URL(url, CONSOLE_ORIGIN), init);
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { ServiceAccounts } = await import("../src/pages/ServiceAccounts");
  const router = createMemoryRouter([{ path: "/service-accounts", element: <ServiceAccounts /> }], {
    initialEntries: ["/service-accounts"],
  });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (container.textContent?.includes(READING_ACCOUNTS)) {
      throw new Error("still reading");
    }
  });
  return { container, idp };
}

function posts(idp: FakeIdp, operation: string): Record<string, unknown>[] {
  return idp.calls
    .filter((call) => call.init?.method === "POST" && new URL(call.url, CONSOLE_ORIGIN).pathname === operation)
    .map((call) => JSON.parse(String(call.init?.body ?? "null")) as Record<string, unknown>);
}

function listings(idp: FakeIdp): number {
  return idp.calls.filter(
    (call) => (call.init?.method ?? "GET") === "GET" && new URL(call.url, CONSOLE_ORIGIN).pathname === LIST_OPERATION,
  ).length;
}

function buttonNamed(container: HTMLElement, name: string): HTMLButtonElement {
  const found = [...container.querySelectorAll("button")].find(
    (one) => one.textContent === name || one.getAttribute("aria-label")?.startsWith(name),
  );
  if (found === undefined) {
    throw new Error(`no button named ${name}`);
  }
  return found as HTMLButtonElement;
}

function field(container: HTMLElement, label: string): HTMLInputElement | HTMLTextAreaElement {
  const found = [...container.querySelectorAll("label")].find((one) => one.textContent?.startsWith(label));
  const input = found?.querySelector("input, textarea");
  if (!input) {
    throw new Error(`no field labelled ${label}`);
  }
  return input as HTMLInputElement | HTMLTextAreaElement;
}

function formNamed(container: HTMLElement, name: string): HTMLFormElement {
  const found = container.querySelector(`form[aria-label^="${name}"]`);
  if (found === null) {
    throw new Error(`no form named ${name}`);
  }
  return found as HTMLFormElement;
}

describe("what the service accounts screen sends", () => {
  test("every write sends only fields its route declares, and none of them names an owner", async () => {
    // What breaks if this is deleted: a body key a route forbids, which is a 422 in front of an
    // administrator who filled the form in, or an owner field that would lend somebody else's reach.
    const declared = (path: string) =>
      Object.keys(declaredRequestBodySchema(path, "post")["properties"] as object).sort();
    expect(declared(LIST_OPERATION)).toEqual(["ceiling", "client_id", "label", "not_after", "subject"]);
    expect(declared(KEYS_OPERATION)).toEqual(["client_id", "label", "not_after"]);
    expect(declared(REVOKE_OPERATION)).toEqual(["handle"]);
    expect(declared(RETIRE_OPERATION)).toEqual(["client_id"]);
    for (const path of [LIST_OPERATION, KEYS_OPERATION, REVOKE_OPERATION, RETIRE_OPERATION]) {
      expect(declared(path).filter((name) => /owner|principal/.test(name))).toEqual([]);
    }
  });

  test("the listing sends only the parameters its route declares", async () => {
    // What breaks if this is deleted: a page size or a parameter the route refuses, which is a 422
    // where the list should be.
    const declared = new Set(declaredQueryParameters(LIST_OPERATION, "get"));
    const limit = declaredParameterSchema(LIST_OPERATION, "get", "limit");
    const { idp } = await mount((url) => (url.pathname === LIST_OPERATION ? json(page([])) : null));

    const sent = idp.urls
      .filter((url) => new URL(url, CONSOLE_ORIGIN).pathname === LIST_OPERATION)
      .flatMap((url) => [...new URL(url, CONSOLE_ORIGIN).searchParams.keys()]);
    expect(sent.length).toBeGreaterThan(0);
    expect(sent.filter((name) => !declared.has(name))).toEqual([]);
    expect(LIST_PAGE_SIZE).toBeLessThanOrEqual(limit["maximum"] as number);
  });

  test("the screen is in the route table and the menu at its own address", () => {
    // What breaks if this is deleted: a page nobody can open, which is what these routes were before.
    const children = routes.find((one) => one.path === "/")?.children ?? [];
    expect(children.map((one) => one.path)).toContain("service-accounts");
  });
});

describe("what the service accounts screen shows and does", () => {
  test("an account is listed with what it cannot use now, and a key by its handle and never a secret", async () => {
    // What breaks if this is deleted: every refusal below is satisfied by an empty page; and a
    // capability the caller does not hold is shown as if the account could use it.
    const { container } = await mount((url) =>
      url.pathname === LIST_OPERATION
        ? json(
            page([
              account({
                client_id: "svc_weekly_report",
                keys: [{ handle: "h4ndle01", label: "cron", issued_at: "2019-03-04T09:00:00Z", lapses_at: "2999-01-01T00:00:00Z" }],
              }),
            ]),
          )
        : null,
    );

    const accounts = container.querySelector('[aria-label="Your service accounts"]')?.textContent ?? "";
    expect(accounts).toContain("svc_weekly_report");
    expect(accounts).toContain("read:margin (you do not hold it now)");
    expect(accounts).not.toContain("read:invoice (you do not hold it now)");
    const keys = container.querySelector('[aria-label="Live keys"]')?.textContent ?? "";
    expect(keys).toContain("h4ndle01");
    expect(container.textContent).toContain(REACH);
    expect(container.textContent).toContain(OWNERSHIP);
  });

  test("no accounts is said in words rather than drawn as an empty table", async () => {
    // What breaks if this is deleted: an empty page that cannot be told from one still loading.
    const { container } = await mount((url) => (url.pathname === LIST_OPERATION ? json(page([])) : null));
    expect(container.textContent).toContain(NO_ACCOUNTS);
    expect(container.querySelector("table")).toBeNull();
  });

  test("registering sends the account with no owner and says which capabilities it cannot use yet", async () => {
    // What breaks if this is deleted: the form sending an empty subject the route refuses, a day
    // with no time zone the route refuses, or a registration that succeeds silently.
    const { container, idp } = await mount((url, init) => {
      if (url.pathname === LIST_OPERATION && init?.method === "POST") {
        return json(account({ client_id: "svc_weekly_report" }), 201);
      }
      return url.pathname === LIST_OPERATION ? json(page([])) : null;
    });
    const before = listings(idp);

    fireEvent.change(field(container, ID_LABEL), { target: { value: " svc_weekly_report " } });
    fireEvent.change(field(container, CEILING_LABEL), { target: { value: "read:invoice\n\nread:margin\n" } });
    fireEvent.change(field(container, ENDS_LABEL), { target: { value: "2999-03-04" } });
    fireEvent.submit(formNamed(container, "Register a service account"));

    await waitFor(() => {
      expect(posts(idp, LIST_OPERATION)).toHaveLength(1);
    });
    expect(posts(idp, LIST_OPERATION)[0]).toEqual({
      client_id: "svc_weekly_report",
      label: "",
      ceiling: ["read:invoice", "read:margin"],
      not_after: endOfDay("2999-03-04"),
    });
    await waitFor(() => {
      expect(container.textContent).toContain("You do not hold read:margin now");
    });
    await waitFor(() => {
      expect(listings(idp)).toBeGreaterThan(before);
    });
  });

  test("a registration left blank sends nothing and says what to fill in", async () => {
    // What breaks if this is deleted: an empty registration reaching the API, refused only after
    // somebody pressed the button, in words about a field they cannot see.
    const { container, idp } = await mount((url) => (url.pathname === LIST_OPERATION ? json(page([])) : null));

    fireEvent.submit(formNamed(container, "Register a service account"));

    await waitFor(() => {
      expect(container.textContent).toContain(BLANK_SENTENCES.ceiling);
    });
    expect(container.textContent).toContain(BLANK_SENTENCES.client_id);
    expect(container.textContent).toContain(BLANK_SENTENCES.not_after);
    expect(posts(idp, LIST_OPERATION)).toEqual([]);
  });

  test("an approve or admin capability is refused beside the ceiling in the API's own words", async () => {
    // What breaks if this is deleted: the API's refusal of a capability no service account may carry
    // drawn nowhere near the field that holds it, or paraphrased into something that decides here.
    const { container } = await mount((url, init) => {
      if (url.pathname === LIST_OPERATION && init?.method === "POST") {
        return json(
          {
            message: "The request was not accepted.",
            trace_id: "trace-1",
            problems: [{ field: "ceiling", code: "value_error", message: NEVER_APPROVE_OR_ADMIN }],
          },
          422,
        );
      }
      return url.pathname === LIST_OPERATION ? json(page([])) : null;
    });

    fireEvent.change(field(container, ID_LABEL), { target: { value: "svc_nightly" } });
    fireEvent.change(field(container, CEILING_LABEL), { target: { value: "admin:credential" } });
    fireEvent.change(field(container, ENDS_LABEL), { target: { value: "2999-03-04" } });
    fireEvent.submit(formNamed(container, "Register a service account"));

    await waitFor(() => {
      expect(container.querySelector('[aria-label="Problems with ceiling"]')?.textContent).toContain(
        NEVER_APPROVE_OR_ADMIN,
      );
    });
    expect(field(container, CEILING_LABEL).getAttribute("aria-invalid")).toBe("true");
  });

  test("a key is shown once with a copy button, then gone, and is never in a request or the browser's storage", async () => {
    // What breaks if this is deleted: the one place a key can be read being lost before it is
    // copied, or kept after the person said they kept it, or written somewhere a later visitor to
    // this browser could read it back.
    const writeText = vi.fn(async (_text: string) => {});
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    let issued = false;
    const { container, idp } = await mount((url, init) => {
      if (url.pathname === KEYS_OPERATION && init?.method === "POST") {
        issued = true;
        return json(
          { client_id: "svc_weekly_report", handle: "h4ndle01", key: SECRET, lapses_at: "2999-01-01T00:00:00Z", shown_once: SHOWN_ONCE },
          201,
        );
      }
      if (url.pathname === LIST_OPERATION) {
        const keys = issued
          ? [{ handle: "h4ndle01", label: "", issued_at: "2019-03-04T09:00:00Z", lapses_at: "2999-01-01T00:00:00Z" }]
          : [];
        return json(page([account({ client_id: "svc_weekly_report", keys })]));
      }
      return null;
    });

    fireEvent.click(buttonNamed(container, ISSUE_LABEL));
    fireEvent.change(field(container, KEY_ENDS_LABEL), { target: { value: "2999-01-01" } });
    fireEvent.click(buttonNamed(container, ISSUE_BUTTON));

    await waitFor(() => {
      expect(container.querySelector('[aria-label="Key"]')?.textContent).toBe(SECRET);
    });
    expect(posts(idp, KEYS_OPERATION)).toEqual([
      { client_id: "svc_weekly_report", label: "", not_after: endOfDay("2999-01-01") },
    ]);
    expect(container.textContent).toContain(SHOWN_ONCE);
    await waitFor(() => {
      expect(container.querySelector('[aria-label="Live keys"]')?.textContent).toContain("h4ndle01");
    });
    expect(container.querySelector('[aria-label="Live keys"]')?.textContent).not.toContain(SECRET);

    fireEvent.click(buttonNamed(container, COPY_LABEL));
    await waitFor(() => {
      expect(container.textContent).toContain(COPIED);
    });
    expect(writeText).toHaveBeenCalledWith(SECRET);

    fireEvent.click(buttonNamed(container, KEPT_LABEL));
    await waitFor(() => {
      expect(container.textContent).not.toContain(SECRET);
    });
    const sent = idp.calls.map((call) => `${call.url} ${String(call.init?.body ?? "")}`).join("\n");
    expect(sent).not.toContain(SECRET);
    const stored = [localStorage, sessionStorage].flatMap((store) =>
      Object.keys(store).map((name) => `${name}=${store.getItem(name) ?? ""}`),
    );
    expect(stored.join("\n")).not.toContain(SECRET);
  });

  test("a key left without an end sends nothing and says what to choose", async () => {
    // What breaks if this is deleted: a key issue reaching the API with no end, refused in words
    // about a field the person has just looked at and filled in everything else of.
    const { container, idp } = await mount((url) =>
      url.pathname === LIST_OPERATION ? json(page([account({ client_id: "svc_weekly_report" })])) : null,
    );

    fireEvent.click(buttonNamed(container, ISSUE_LABEL));
    fireEvent.click(buttonNamed(container, ISSUE_BUTTON));

    await waitFor(() => {
      expect(container.textContent).toContain(BLANK_SENTENCES.key_not_after);
    });
    expect(posts(idp, KEYS_OPERATION)).toEqual([]);
  });

  test("revoking a key is confirmed first, and sends only its handle", async () => {
    // What breaks if this is deleted: one press stopping an integration, or a revocation that
    // names the account and takes every key it has.
    const { container, idp } = await mount((url, init) => {
      if (url.pathname === REVOKE_OPERATION && init?.method === "POST") {
        return json({ told: "The key is revoked and is refused from its next use." });
      }
      return url.pathname === LIST_OPERATION
        ? json(
            page([
              account({
                client_id: "svc_weekly_report",
                keys: [{ handle: "h4ndle01", label: "", issued_at: "2019-03-04T09:00:00Z", lapses_at: "2999-01-01T00:00:00Z" }],
              }),
            ]),
          )
        : null;
    });

    fireEvent.click(buttonNamed(container, REVOKE_LABEL));
    expect(container.querySelector(".confirm")?.textContent).toContain("Revoke the key h4ndle01 of Weekly report?");
    fireEvent.click(buttonNamed(container, KEEP_LABEL));
    expect(posts(idp, REVOKE_OPERATION)).toEqual([]);

    fireEvent.click(buttonNamed(container, REVOKE_LABEL));
    fireEvent.click(buttonNamed(container, CONFIRM_REVOKE_LABEL));
    await waitFor(() => {
      expect(posts(idp, REVOKE_OPERATION)).toEqual([{ handle: "h4ndle01" }]);
    });
    await waitFor(() => {
      expect(container.textContent).toContain("The key is revoked and is refused from its next use.");
    });
  });

  test("retiring an account is confirmed first, and sends only its id", async () => {
    // What breaks if this is deleted: one press stopping an integration and every key it has.
    const { container, idp } = await mount((url, init) => {
      if (url.pathname === RETIRE_OPERATION && init?.method === "POST") {
        return json({ told: "The account and all its keys are retired." });
      }
      return url.pathname === LIST_OPERATION ? json(page([account({ client_id: "svc_weekly_report" })])) : null;
    });

    fireEvent.click(buttonNamed(container, RETIRE_LABEL));
    expect(container.querySelector(".confirm")?.textContent).toContain("Retire Weekly report?");
    expect(posts(idp, RETIRE_OPERATION)).toEqual([]);
    fireEvent.click(buttonNamed(container, CONFIRM_RETIRE_LABEL));

    await waitFor(() => {
      expect(posts(idp, RETIRE_OPERATION)).toEqual([{ client_id: "svc_weekly_report" }]);
    });
    await waitFor(() => {
      expect(container.textContent).toContain("The account and all its keys are retired.");
    });
  });

  test("a third key refused by the API is said in the API's words", async () => {
    // What breaks if this is deleted: the limit on live keys reaching the person as a bare failure
    // with no sentence saying to revoke the one being replaced first.
    const limit = "svc_weekly_report already has 2 live keys, which is the limit. Revoke the one being replaced first.";
    const { container } = await mount((url, init) => {
      if (url.pathname === KEYS_OPERATION && init?.method === "POST") {
        return json({ message: limit, trace_id: "trace-2" }, 409);
      }
      return url.pathname === LIST_OPERATION ? json(page([account({ client_id: "svc_weekly_report" })])) : null;
    });

    fireEvent.click(buttonNamed(container, ISSUE_LABEL));
    fireEvent.change(field(container, KEY_ENDS_LABEL), { target: { value: "2999-01-01" } });
    fireEvent.click(buttonNamed(container, ISSUE_BUTTON));

    await waitFor(() => {
      expect(container.textContent).toContain(limit);
    });
    expect(container.querySelector('[aria-label="Key"]')).toBeNull();
  });
});
