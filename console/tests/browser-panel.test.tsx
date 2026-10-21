/**
 * The browser panel on the Features page: the websites an administrator declared, the permissions
 * signed for them, the acts each offers, and the forms that declare and sign.
 *
 * Mounted through the Features page, because that is where the panel is drawn. The shapes are read
 * from `brain.browser_routes` itself, so a renamed field fails here.
 *
 * Task ids: M19.2.4, M19.6.7, M19.7.3, M19.9.7
 */

import { act, fireEvent, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  BROWSER_API_PATH,
  EXCEPTIONS_API_PATH,
  NOT_JSON,
  OPENS_NO_BROWSER,
  readDays,
  retirePath,
  revokePath,
  SWITCHED_OFF,
  TARGETS_API_PATH,
} from "../src/pages/browserQuery";
import { FEATURES_API_PATH, FEATURES_PATH } from "../src/pages/featuresQuery";
import { button, json, mountPage, settled, type Answer } from "./support/pageHarness";
import { backendModelFields } from "./support/python";
import { installRadixStubs } from "./support/radix";

beforeAll(() => {
  installRadixStubs();
});

const FEATURES = `GET /api/v1${FEATURES_API_PATH}`;
const BROWSER = `GET /api/v1${BROWSER_API_PATH}`;
const ROUTES = "src/brain/browser_routes.py";

function target(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    name: "books",
    origins: ["https://books.example"],
    api_tools: ["ledger.list_invoices"],
    surfaces: [
      {
        name: "filing",
        origin: "https://books.example",
        path: "/filing",
        verbs: ["open", "submit"],
        reads: [],
        read_back: "",
        controls: ['submit button "File"'],
      },
    ],
    bindings: [
      {
        placeholder: "{{secret:login}}",
        origin: "https://books.example",
        kind: "password",
        path: "browser/creds/books",
      },
    ],
    declared_by: "u_admin",
    declared_at: "2019-03-04T09:00:00Z",
    ...overrides,
  };
}

function grant(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    seq: 7,
    kind: "exception",
    target: "books",
    what: "filing",
    signed_by: "u_admin",
    reason: "THE-SIGNED-REASON",
    expires_at: "2999-01-01T09:00:00Z",
    ...overrides,
  };
}

function page(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    targets: [target()],
    unreadable: [],
    grants: [grant()],
    declarations_are_on: true,
    most_days: 90,
    ...overrides,
  };
}

const FEATURE_LIST = { features: [], components_are_chosen_by_the_profile: true, plugins_have_no_loader: true };

async function featuresPage(answers: Record<string, Answer>) {
  return mountPage(
    FEATURES_PATH,
    async () => {
      const { Features } = await import("../src/pages/Features");
      return <Features />;
    },
    { [FEATURES]: () => json(FEATURE_LIST), ...answers },
  );
}

describe("what the browser panel draws", () => {
  test("a declared website with its pages, controls, sign-in and API, and a permission with who signed it", async () => {
    // What breaks if this is deleted: a website drawn without the control a write is done on or the
    // origin its sign-in works on, or a permission drawn without who signed it and why.
    const { container } = await featuresPage({ [BROWSER]: () => json(page()) });
    const text = container.textContent ?? "";
    expect(text).toContain("books");
    expect(text).toContain("Opens only https://books.example");
    expect(text).toContain('submit button "File"');
    expect(text).toContain("{{secret:login}} (password) on https://books.example");
    expect(text).toContain("Already has an API: ledger.list_invoices");
    expect(text).toContain("THE-SIGNED-REASON");
    expect(text).toContain("Signed by u_admin");
  });

  test("the forms leave when declaring is off, and the page always says declaring opens no browser", async () => {
    // What breaks if this is deleted: forms the route will refuse are offered, or the page lets
    // an administrator think declaring a website lets an agent open it.
    const on = await featuresPage({ [BROWSER]: () => json(page()) });
    expect(on.container.textContent).toContain(OPENS_NO_BROWSER);
    expect(on.container.textContent).not.toContain(SWITCHED_OFF);
    expect(on.container.querySelector("#browser-declaration")).not.toBeNull();
    const off = await featuresPage({ [BROWSER]: () => json(page({ declarations_are_on: false })) });
    expect(off.container.textContent).toContain(SWITCHED_OFF);
    expect(off.container.textContent).toContain(OPENS_NO_BROWSER);
    expect(off.container.querySelector("#browser-declaration")).toBeNull();
  });

  test("a declaration this release cannot read is named and not drawn as a website", async () => {
    // What breaks if this is deleted: a person is not told to declare it again.
    const { container } = await featuresPage({
      [BROWSER]: () => json(page({ targets: [], unreadable: ["stale_site"] })),
    });
    expect(container.textContent).toContain("stale_site");
    expect(container.textContent).toContain("No websites declared");
  });

  test("the vault references are in Advanced and not on the page", async () => {
    // What breaks if this is deleted: vault paths drawn for every administrator at a glance.
    const { container } = await featuresPage({ [BROWSER]: () => json(page()) });
    const panel = container.querySelector('[data-slot="browser-panel"]');
    const copy = panel?.cloneNode(true) as HTMLElement;
    copy.querySelectorAll('[data-slot="advanced"]').forEach((one) => {
      one.remove();
    });
    expect(copy.textContent).not.toContain("browser/creds/books");
    expect(panel?.querySelector('[data-slot="advanced"]')?.textContent).toContain("browser/creds/books");
  });
});

describe("taking back", () => {
  test("retiring posts to the website's own address and the list is read again", async () => {
    // What breaks if this is deleted: a retirement sent to the wrong website or never re-read.
    let retired = false;
    const { container, sent } = await featuresPage({
      [BROWSER]: () => json(page({ targets: retired ? [] : [target()] })),
      [`POST /api/v1${retirePath("books")}`]: () => {
        retired = true;
        return json({ name: "books" });
      },
    });
    await act(async () => {
      fireEvent.click(button(container, "Retire: books"));
    });
    await waitFor(() => {
      expect(container.textContent).toContain('"books" is retired.');
    });
    await settled(container);
    expect(sent.filter((one) => one.method === "POST").map((one) => one.path)).toEqual([
      `/api/v1${retirePath("books")}`,
    ]);
    expect(container.textContent).toContain("No websites declared");
  });

  test("revoking posts to the permission's own address", async () => {
    // What breaks if this is deleted: a revoke that ends a different permission.
    const { container, sent } = await featuresPage({
      [BROWSER]: () => json(page()),
      [`POST /api/v1${revokePath(7)}`]: () => json({ seq: 7 }),
    });
    await act(async () => {
      fireEvent.click(button(container, "Revoke: exception filing"));
    });
    await waitFor(() => {
      expect(sent.some((one) => one.method === "POST")).toBe(true);
    });
    expect(sent.filter((one) => one.method === "POST").map((one) => one.path)).toEqual([
      `/api/v1${revokePath(7)}`,
    ]);
  });

  test("retiring and revoking are offered with declaring switched off", async () => {
    // What breaks if this is deleted: a permission signed while the switch was on cannot be
    // withdrawn with it off.
    const { container } = await featuresPage({ [BROWSER]: () => json(page({ declarations_are_on: false })) });
    expect(button(container, "Retire: books")).toBeTruthy();
    expect(button(container, "Revoke: exception filing")).toBeTruthy();
  });
});

describe("declaring and signing", () => {
  test("text that is not JSON is told so and nothing is sent", async () => {
    // What breaks if this is deleted: a half-typed declaration posted, or silence.
    const { container, sent } = await featuresPage({ [BROWSER]: () => json(page()) });
    fireEvent.change(container.querySelector("#browser-declaration") as HTMLTextAreaElement, {
      target: { value: "{not json" },
    });
    await act(async () => {
      fireEvent.click(button(container, "Declare website"));
    });
    expect(container.textContent).toContain(NOT_JSON);
    expect(sent.filter((one) => one.method === "POST")).toHaveLength(0);
  });

  test("a declaration is posted as the document typed and a refusal is the API's sentence", async () => {
    // What breaks if this is deleted: a document altered on the way, or a refusal replaced by a
    // console sentence that says less than the API's.
    const { container, sent } = await featuresPage({
      [BROWSER]: () => json(page()),
      [`POST /api/v1${TARGETS_API_PATH}`]: () => json({ message: "REFUSED-BY-THE-CODEC", trace_id: "T-1" }, 404),
    });
    fireEvent.change(container.querySelector("#browser-declaration") as HTMLTextAreaElement, {
      target: { value: '{"name": "books"}' },
    });
    await act(async () => {
      fireEvent.click(button(container, "Declare website"));
    });
    await waitFor(() => {
      expect(container.textContent).toContain("REFUSED-BY-THE-CODEC");
    });
    expect(sent.filter((one) => one.method === "POST").map((one) => one.body)).toEqual([
      { declaration: { name: "books" } },
    ]);
  });

  test("an exception is posted with its days as a number and a number out of range is told so", async () => {
    // What breaks if this is deleted: days sent as text, or a length past the quarter posted to
    // be refused by the table.
    const { container, sent } = await featuresPage({
      [BROWSER]: () => json(page()),
      [`POST /api/v1${EXCEPTIONS_API_PATH}`]: () => json(grant()),
    });
    const fill = (id: string, value: string): void => {
      fireEvent.change(container.querySelector(`#browser-${id}`) as HTMLInputElement, { target: { value } });
    };
    fill("exception-target", "books");
    fill("exception-surface", "filing");
    fill("exception-days", "91");
    fill("exception-reason", "the nightly filing runs unattended");
    await act(async () => {
      fireEvent.click(button(container, "Sign exception"));
    });
    expect(container.textContent).toContain("Days is a whole number from 1 to 90.");
    expect(sent.filter((one) => one.method === "POST")).toHaveLength(0);
    fill("exception-days", "30");
    await act(async () => {
      fireEvent.click(button(container, "Sign exception"));
    });
    await waitFor(() => {
      expect(sent.some((one) => one.method === "POST")).toBe(true);
    });
    expect(sent.filter((one) => one.method === "POST").map((one) => one.body)).toEqual([
      {
        target: "books",
        surface: "filing",
        days: 30,
        reason: "the nightly filing runs unattended",
      },
    ]);
  });

  test("days are whole numbers inside the range the API gives", () => {
    // What breaks if this is deleted: 0, 1.5 and 91 are posted.
    expect(readDays("1", 90)).toBe(1);
    expect(readDays("90", 90)).toBe(90);
    expect(readDays("0", 90)).toBeNull();
    expect(readDays("91", 90)).toBeNull();
    expect(readDays("1.5", 90)).toBeNull();
    expect(readDays("", 90)).toBeNull();
  });
});

describe("the shapes", () => {
  test("every field the panel reads is a field the route declares", () => {
    // What breaks if this is deleted: a field renamed in `brain.browser_routes` that the panel goes
    // on reading, which renders as an empty sentence in production.
    expect(Object.keys(page()).sort()).toEqual(backendModelFields(ROUTES, "BrowserPage").sort());
    expect(Object.keys(target()).sort()).toEqual(backendModelFields(ROUTES, "BrowserTargetView").sort());
    expect(Object.keys(grant()).sort()).toEqual(backendModelFields(ROUTES, "BrowserGrantView").sort());
  });
});
