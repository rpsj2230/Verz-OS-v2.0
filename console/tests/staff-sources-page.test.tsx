/**
 * The Staff sources page on the shared page kit: the status at the top, connecting or switching the
 * source in a drawer, the sync credential, the recent runs and the agents waiting for an owner.
 *
 * The failures worth testing are the ones that look like the page working: a trial fetched with the
 * page, which would contact a company's directory whenever anybody opened it; a count beside a list
 * narrowed per reader; an identifier in the page's text; a write sent without its confirmation or
 * with a blank field; a credential drawn back; and a page that does not read again after a write.
 *
 * **Reachable means through the application's own route table**, signed in through the real session
 * modules and answered by a stand-in API, so a test passes only if the address resolves.
 *
 * Task ids: M1.6.12, M1.8.6, M1.8.9, M27.7.2, M27.16.1
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { CREDENTIAL_BLANK, STAFF_SOURCES_API_PATH, TRIAL_API_PATH } from "../src/pages/staffSourcesQuery";
import { STAFF_SOURCES_HEADING } from "../src/pages/StaffSources";
import {
  CONNECT_A_SOURCE,
  HELD,
  HOW_TO_CONNECT,
  NO_RUNS,
  NO_SOURCE,
  NOT_HELD,
  SOURCE_IN_USE,
  SWITCH_SOURCE,
  TRY_A_READ,
  WOULD_ADD_LABEL,
} from "../src/pages/staff-sources/StaffSourcesPage";
import {
  APPLY_FIRST_SYNC,
  FOR_EXAMPLE,
  SAVE_AND_CONNECT,
  SHOW_FIRST_SYNC,
  STEPS_ONLY,
  TEST_CONNECTION,
  fillInBox,
} from "../src/pages/staff-sources/ConnectDrawer";
import { NEW_CREDENTIAL, REPLACE_CREDENTIAL } from "../src/pages/staff-sources/SyncCredential";
import { NO_TRANSFERS, TAKE_ON } from "../src/pages/staff-sources/Transfers";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { operation } from "./support/openapi";
import { installRadixStubs } from "./support/radix";

const CONSOLE_ORIGIN = "https://console.test";
const BASE = "/api/v1/govern/staff_sources";

/** Strings nothing else could contain, so finding one anywhere is a leak. */
const SECRET = "SENTINEL-app-secret-typed-9d2e";
const AGENT_ID = "a_quotes_sentinel";
const OWNER_ID = "u_gone_sentinel";

beforeAll(async () => {
  installRadixStubs();
  await import("../src/pages/StaffSources");
}, 60_000);

// ------------------------------------------------------------------------------ the answers

function lark(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    source: "lark",
    title: "Lark (or Feishu)",
    where: "open.larksuite.com/app",
    steps: ["Sign in to open.larksuite.com/app.", 'Copy the App ID and App Secret from "Credentials & Basic Info".'],
    fields: [
      { key: "location", label: "Platform", help: "larksuite.com or feishu.cn.", secret: false, example: "larksuite.com" },
      { key: "app_id", label: "App ID", help: "It starts with cli_.", secret: false, example: "cli_a" },
      { key: "app_secret", label: "App Secret", help: "From Credentials & Basic Info.", secret: true, example: "" },
    ],
    connectable: true,
    unavailable: "",
    chosen: true,
    held: "",
    ...over,
  };
}

const GUIDES = { guides: [lark()], may_connect: true, schedule: "Read again every night." };

const PAGE = {
  options: [
    {
      name: "lark",
      meaning: "Lark's contact directory.",
      reads_a_list: true,
      needs: ["INSTALL_STAFF_SOURCE_LOCATION"],
      unsupplied: [],
      chosen: true,
    },
  ],
  selection: { name: "lark", meaning: "Lark's contact directory.", reads_a_list: true, unsupplied: [], refusal: "", ready: true },
  how_to_choose: "Choose your staff source on this screen.",
};

const RUNS = {
  runs: [
    {
      source: "lark",
      started_at: "2999-03-02T02:00:00Z",
      finished_at: "2999-03-02T02:00:05Z",
      outcome: "credential_refused",
      detail: "The staff source refused the kept credential. Nobody was changed.",
      added: [],
      marked_left: [],
      renamed: [],
      withheld: [],
      changed_nobody: true,
    },
  ],
};

const CREDENTIAL = {
  slot: "connector_keys/staff_source",
  held: false,
  set_at: null,
  vault: "ready",
  told: "The secrets vault answered.",
  form: "The custom app's App ID, a colon, then its App Secret.",
};

const TRANSFERS = { transfers: [{ agent_id: AGENT_ID, display_name: "Quotes helper", owner_id: OWNER_ID, running: false }] };

const READ_IT = { source: "lark", read: true, told: "Connected. Nothing was saved.", people: 2, complete: true, skipped: 0 };

const PLAN = {
  applied: false,
  outcome: "dry_run",
  told: "This is what the first sync would do.",
  added: ["Ada Lovelace"],
  marked_left: [],
  renamed: [],
  withheld: [],
  refusals: [],
  safe_to_apply: true,
};

interface Answer {
  readonly status?: number;
  readonly body: unknown;
}

/** Keyed `METHOD path`. A read with no answer is a 404, which is what a refused reader is told. */
type Answers = Readonly<Record<string, Answer>>;

const ANSWERS: Answers = {
  [`GET ${BASE}`]: { body: PAGE },
  [`GET ${BASE}/guides`]: { body: GUIDES },
  [`GET ${BASE}/runs`]: { body: RUNS },
  [`GET ${BASE}/credential`]: { body: CREDENTIAL },
  [`GET ${BASE}/transfers`]: { body: TRANSFERS },
  [`GET ${BASE}/trial`]: {
    body: {
      trial: {
        source: "lark",
        plan: {
          source: "lark",
          would_add: [
            { work_address: "ada@example.test", display_name: "Ada", department: "maintenance", groups: [], active: true },
          ],
          absent: ["hopper@example.test"],
          would_remove: [],
          would_deactivate: [],
          withheld: [],
          role_grants_to_add: [{ principal_id: "u_ada_sentinel", role: "engineer", source_group: "engineers" }],
          role_grants_to_remove: [],
          refusals: [],
          gaps: [],
          safe_to_apply: true,
          changes_nothing: false,
        },
        refusals: [],
        safe_to_apply: true,
      },
      unread: "",
    },
  },
  [`POST ${BASE}/test`]: { body: READ_IT },
  [`POST ${BASE}/connect`]: { body: { source: "lark", told: "Connected to Lark (or Feishu).", people: 2 } },
  [`POST ${BASE}/first-sync`]: { body: PLAN },
  [`POST ${BASE}/first-sync/apply`]: {
    body: { ...PLAN, applied: true, outcome: "applied", told: "Read the staff list and applied it.", added: [] },
  },
  [`PUT ${BASE}/credential`]: { body: { ...CREDENTIAL, held: true, told: "The credential is held in the vault." } },
  [`POST ${BASE}/transfers/${AGENT_ID}`]: { body: { agent_id: AGENT_ID, owner_id: "u_me" } },
};

interface Mounted {
  readonly container: HTMLElement;
  readonly idp: FakeIdp;
}

async function settled(container: HTMLElement): Promise<void> {
  await waitFor(() => {
    if (!container.querySelector("h1") || container.querySelector('[data-slot="loading-state"]')) {
      throw new Error("the page is still asking");
    }
  });
}

async function consoleAt(over: Answers = {}): Promise<Mounted> {
  const answers: Answers = { ...ANSWERS, ...over };
  const idp = fakeIdentityProvider({
    api(url, init) {
      const key = `${init?.method ?? "GET"} ${new URL(url, CONSOLE_ORIGIN).pathname}`;
      if (!key.includes(BASE)) {
        return null;
      }
      const answer = answers[key] ?? { status: 404, body: { message: "not here", trace_id: "t" } };
      return new Response(JSON.stringify(answer.body), {
        status: answer.status ?? 200,
        headers: { "content-type": "application/json" },
      });
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: ["/staff_sources"] });
  const { container } = render(<RouterProvider router={router} />);
  await settled(container);
  return { container, idp };
}

/** Every call this page made to its routes, as `METHOD path`, with the body a write sent. */
function calls(idp: FakeIdp): { key: string; body: string }[] {
  return idp.calls
    .filter((call) => new URL(call.url, CONSOLE_ORIGIN).pathname.startsWith(BASE))
    .map((call) => ({
      key: `${call.init?.method ?? "GET"} ${new URL(call.url, CONSOLE_ORIGIN).pathname}`,
      body: typeof call.init?.body === "string" ? call.init.body : "",
    }));
}

function writes(idp: FakeIdp): { key: string; body: string }[] {
  return calls(idp).filter((one) => !one.key.startsWith("GET "));
}

async function press(inside: HTMLElement, name: string | RegExp): Promise<void> {
  await act(async () => {
    fireEvent.click(within(inside).getByRole("button", { name }));
  });
}

async function openDrawer(label = SWITCH_SOURCE): Promise<HTMLElement> {
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: label }));
  });
  const drawer = await screen.findByRole("dialog");
  await waitFor(() => {
    if (drawer.querySelector('[data-slot="loading-state"]')) {
      throw new Error("the steps have not arrived");
    }
  });
  return drawer;
}

function fill(drawer: HTMLElement): void {
  for (const [name, value] of [
    ["location", "larksuite.com"],
    ["app_id", "cli_a"],
    ["app_secret", SECRET],
  ] as const) {
    fireEvent.change(drawer.querySelector(`input[name=${name}]`) as HTMLInputElement, { target: { value } });
  }
}

/** The page's text outside the Advanced section. */
function outsideAdvanced(container: HTMLElement): string {
  const copy = container.cloneNode(true) as HTMLElement;
  copy.querySelectorAll('[data-slot="advanced"]').forEach((one) => {
    one.remove();
  });
  return copy.textContent ?? "";
}

// ------------------------------------------------------------------------------ the tests

describe("what the page shows", () => {
  test("it reads its five answers on arrival and never the trial, which waits for a press", async () => {
    // What breaks if this is deleted: a trial fetched with the page, contacting a company's
    // directory whenever anybody opens the screen.
    const { idp } = await consoleAt();
    const asked = new Set(calls(idp).map((one) => one.key));
    expect([...asked].sort()).toEqual(
      [`GET ${BASE}`, `GET ${BASE}/credential`, `GET ${BASE}/guides`, `GET ${BASE}/runs`, `GET ${BASE}/transfers`].sort(),
    );
    expect(`/api/v1${STAFF_SOURCES_API_PATH}`).toBe(BASE);
    expect(`/api/v1${TRIAL_API_PATH}`).toBe(`${BASE}/trial`);
    expect(operation(BASE, "get").parameters ?? []).toEqual([]);
  });

  test("the status names the source, the last run and whether the credential is held, and counts nothing", async () => {
    // What breaks if this is deleted: the one-glance answer the owner asked for, or a figure beside a
    // list narrowed per reader, which would say how much a reader was not shown.
    const { container } = await consoleAt();
    const strip = container.querySelector('[data-slot="kpi-strip"]') as HTMLElement;
    expect(strip.textContent).toContain(SOURCE_IN_USE);
    expect(strip.textContent).toContain("Lark (or Feishu)");
    expect(strip.textContent).toContain("Credential refused");
    expect(strip.textContent).toContain(NOT_HELD);
    expect(container.textContent).not.toMatch(/\b\d+\s+(people|persons?|sources?|agents?|runs?|rows?)\b/i);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(STAFF_SOURCES_HEADING);
  });

  test("identifiers appear only inside Advanced", async () => {
    // What breaks if this is deleted: the clutter the owner removed, an agent id, a principal id, a
    // setting name or a vault slot, drawn back into the page's text.
    const { container } = await consoleAt();
    await press(container, TRY_A_READ);
    await waitFor(() => {
      expect(container.textContent).toContain(WOULD_ADD_LABEL);
    });
    const text = outsideAdvanced(container);
    for (const id of [AGENT_ID, OWNER_ID, "u_ada_sentinel", "INSTALL_STAFF_SOURCE_LOCATION", "connector_keys"]) {
      expect(text).not.toContain(id);
      expect(container.querySelector('[data-slot="advanced"]')?.textContent).toContain(id);
    }
  });

  test("a reader who reaches no source and an install with none are drawn alike, with nothing about why", async () => {
    // What breaks if this is deleted: DENIED told apart from ABSENT by a lock, a dash or a sentence.
    const { container } = await consoleAt({
      [`GET ${BASE}`]: { body: { options: [], selection: null, how_to_choose: "" } },
      [`GET ${BASE}/runs`]: { body: { runs: [] } },
      [`GET ${BASE}/transfers`]: { body: { transfers: [] } },
    });
    expect(container.textContent).toContain(NO_SOURCE);
    expect(container.textContent).toContain(NO_RUNS);
    expect(container.textContent).toContain(NO_TRANSFERS);
    expect(container.textContent).not.toMatch(/permission|not allowed|denied|hidden|restricted/i);
    expect(screen.getByRole("button", { name: CONNECT_A_SOURCE })).toBeTruthy();
  });

  test("a trial press asks once and names the people rather than counting them", async () => {
    const { container, idp } = await consoleAt();
    await press(container, TRY_A_READ);
    await waitFor(() => {
      expect(container.textContent).toContain("ada@example.test");
    });
    expect(calls(idp).filter((one) => one.key === `GET ${BASE}/trial`)).toHaveLength(1);
    expect(container.textContent).toContain("hopper@example.test");
  });
});

describe("the sync credential", () => {
  test("it says what to paste before anything is sent, and a blank one is told beside the field", async () => {
    const { container, idp } = await consoleAt();
    expect(container.textContent).toContain(CREDENTIAL.form);
    await press(container, REPLACE_CREDENTIAL);
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(container.textContent).toContain(CREDENTIAL_BLANK);
    expect(writes(idp)).toEqual([]);
  });

  test("a credential is sent once after the confirmation, never drawn back, and the page reads again", async () => {
    const { container, idp } = await consoleAt();
    fireEvent.input(screen.getByLabelText(NEW_CREDENTIAL), { target: { value: SECRET } });
    await press(container, REPLACE_CREDENTIAL);
    const dialog = await screen.findByRole("alertdialog");
    expect(writes(idp)).toEqual([]);
    await press(dialog, REPLACE_CREDENTIAL);
    await waitFor(() => {
      expect(container.textContent).toContain("The credential is held in the vault.");
    });
    await settled(container);

    expect(writes(idp)).toEqual([{ key: `PUT ${BASE}/credential`, body: JSON.stringify({ value: SECRET }) }]);
    expect(calls(idp).filter((one) => one.key === `GET ${BASE}/credential`)).toHaveLength(2);
    expect(document.body.innerHTML).not.toContain(SECRET);
  });

  test("the API's problem with the value is drawn beside the field", async () => {
    const { container } = await consoleAt({
      [`PUT ${BASE}/credential`]: {
        status: 422,
        body: { problems: [{ field: "value", code: "form", message: "Put a colon between the App ID and the App Secret." }] },
      },
    });
    fireEvent.input(screen.getByLabelText(NEW_CREDENTIAL), { target: { value: "no-colon" } });
    await press(container, REPLACE_CREDENTIAL);
    await press(await screen.findByRole("alertdialog"), REPLACE_CREDENTIAL);
    const beside = await screen.findByRole("list", { name: "Problems with value" });
    expect(beside.textContent).toContain("Put a colon between the App ID and the App Secret.");
  });

  test("the card is left out for a reader the API does not answer", async () => {
    const { container } = await consoleAt({
      [`GET ${BASE}/credential`]: { status: 404, body: { message: "not here", trace_id: "t" } },
    });
    expect(screen.queryByLabelText(NEW_CREDENTIAL)).toBeNull();
    expect(container.querySelector('[data-slot="kpi-strip"]')?.textContent).not.toContain(HELD);
  });
});

describe("agents waiting for an owner", () => {
  test("taking one on is confirmed, posts to its address, and the page reads again", async () => {
    const { container, idp } = await consoleAt();
    await press(container, `${TAKE_ON} Quotes helper`);
    const dialog = await screen.findByRole("alertdialog");
    expect(writes(idp)).toEqual([]);
    await press(dialog, TAKE_ON);
    await waitFor(() => {
      expect(container.textContent).toContain("Quotes helper now answers to you");
    });
    await settled(container);
    expect(writes(idp).map((one) => one.key)).toEqual([`POST ${BASE}/transfers/${AGENT_ID}`]);
    expect(calls(idp).filter((one) => one.key === `GET ${BASE}/transfers`)).toHaveLength(2);
  });
});

describe("connecting or switching the source", () => {
  test("each box says what it accepts before anything is sent, and a blank form sends nothing", async () => {
    // What breaks if this is deleted: the reason tests/validated-before-write.test.tsx excuses the
    // drawer's form, and a blank test sent to a directory with nobody's credential.
    const { idp } = await consoleAt();
    const drawer = await openDrawer();
    expect(drawer.textContent).toContain(`${FOR_EXAMPLE}: cli_a`);
    expect(drawer.textContent).toContain("larksuite.com or feishu.cn.");
    await press(drawer, TEST_CONNECTION);
    for (const label of ["Platform", "App ID", "App Secret"]) {
      expect(drawer.textContent).toContain(fillInBox(label));
    }
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(writes(idp)).toEqual([]);
  });

  test("save waits for a test, save and apply are each confirmed, and the secret is never drawn", async () => {
    // What breaks if this is deleted: "choose the source and connect it" in one unconfirmed press, or
    // a first sync applied on the press meant to show it.
    const { container, idp } = await consoleAt();
    const drawer = await openDrawer();
    const save = () => within(drawer).getByRole("button", { name: SAVE_AND_CONNECT }) as HTMLButtonElement;
    expect(save().disabled).toBe(true);
    fill(drawer);
    await press(drawer, TEST_CONNECTION);
    await waitFor(() => {
      expect(save().disabled).toBe(false);
    });

    await press(drawer, SAVE_AND_CONNECT);
    expect(writes(idp).map((one) => one.key)).toEqual([`POST ${BASE}/test`]);
    await press(await screen.findByRole("alertdialog"), SAVE_AND_CONNECT);
    await waitFor(() => {
      expect(drawer.textContent).toContain("Connected to Lark (or Feishu).");
    });

    await press(drawer, SHOW_FIRST_SYNC);
    await waitFor(() => {
      expect(drawer.textContent).toContain("Ada Lovelace");
    });
    await press(drawer, APPLY_FIRST_SYNC);
    expect(writes(idp).at(-1)?.key).toBe(`POST ${BASE}/first-sync`);
    await press(await screen.findByRole("alertdialog"), APPLY_FIRST_SYNC);
    await waitFor(() => {
      expect(drawer.textContent).toContain("applied it");
    });

    expect(writes(idp).map((one) => one.key)).toEqual([
      `POST ${BASE}/test`,
      `POST ${BASE}/connect`,
      `POST ${BASE}/first-sync`,
      `POST ${BASE}/first-sync/apply`,
    ]);
    expect(writes(idp).every((one) => one.body.includes(SECRET))).toBe(true);
    expect(document.body.textContent).not.toContain(SECRET);
    // The page read itself again after the save and after the apply.
    await settled(container);
    expect(calls(idp).filter((one) => one.key === `GET ${BASE}`).length).toBeGreaterThanOrEqual(3);
  });

  test("the vault's credential is offered first, asks only where the list is, and sends no secret", async () => {
    const { idp } = await consoleAt({
      [`GET ${BASE}/guides`]: {
        body: { ...GUIDES, guides: [lark({ held: "Use the Lark app connected on the Connectors screen." })] },
      },
    });
    const drawer = await openDrawer();
    expect(drawer.querySelector("input[name=app_secret]")).toBeNull();
    fireEvent.change(drawer.querySelector("input[name=location]") as HTMLInputElement, { target: { value: "larksuite.com" } });
    await press(drawer, SAVE_AND_CONNECT);
    await press(await screen.findByRole("alertdialog"), SAVE_AND_CONNECT);
    await waitFor(() => {
      expect(writes(idp)).toHaveLength(1);
    });
    expect(JSON.parse(writes(idp)[0]?.body ?? "{}")).toEqual({
      source: "lark",
      values: { location: "larksuite.com" },
      use_held: true,
    });
  });

  test("a reader who may not connect is shown the steps and no form", async () => {
    await consoleAt({ [`GET ${BASE}/guides`]: { body: { ...GUIDES, may_connect: false } } });
    const drawer = await openDrawer(HOW_TO_CONNECT);
    expect(drawer.querySelectorAll("ol li").length).toBeGreaterThan(0);
    expect(drawer.querySelector("input")).toBeNull();
    expect(drawer.textContent).toContain(STEPS_ONLY);
  });
});
