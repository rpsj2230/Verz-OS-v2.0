/**
 * The Staff sources screen: what it draws, what it never draws, and when it asks for a trial.
 *
 * This is a configuration screen with one read on it that is not configuration, and the
 * failures worth testing are the ones that look like the screen working.
 *
 * **The trial is asked for and never loaded.** It reads a client's own directory and it names
 * the company's staff, so a console that fetched it on mount would contact somebody else's
 * server every time anybody opened the page. The assertion is over the requests the console
 * made rather than over a flag it set, because a flag is satisfied by a console that set it and
 * fetched anyway.
 *
 * **An install that never looked must not read as an install where nothing would change.** The
 * unread sentence and a plan are different shapes on the payload and are drawn as different
 * things here: the sentence is a notice, and a plan is a list of people. A page that rendered
 * the plan's fields with `?? []` would draw an empty plan for both, which is the alarming word
 * for a fact nobody established.
 *
 * **Nothing around any of these lists may count anything.** Every listing on this screen is
 * narrowed per caller, so a number is the subtraction `CLAUDE.md` forbids rather than a footer,
 * and the assertion is over the rendered text rather than over a field nobody rendered. That
 * costs this screen the figure `docs/screens.html` puts in every filter bar it draws, which is
 * the one convention of the design it cannot keep.
 *
 * **A refused reader and an install with nothing to show are the same payload**, decided by
 * `brain.staff_source_routes` and not by this console, so what is tested here is that the
 * console adds nothing that would tell them apart: no lock, no dash and no sentence about
 * permission.
 *
 * Task ids: none
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import {
  CREDENTIAL_BLANK,
  readStaffSources,
  readTrial,
  wasRead,
  STAFF_SOURCES_API_PATH,
  TRIAL_API_PATH,
} from "../src/pages/staffSourcesQuery";
import {
  CHANGED_NOBODY,
  CREDENTIAL_NOT_HELD,
  NO_TRANSFERS,
  REPLACE_CREDENTIAL,
  SYNC_CREDENTIAL,
  TAKE_ON,
  CHANGES_NOTHING,
  CHOSEN,
  NO_SOURCES,
  READS_NO_LIST,
  RUN_THE_TRIAL,
  STAFF_SOURCES_HEADING,
  STILL_TO_SET,
  WOULD_ADD_LABEL,
} from "../src/pages/StaffSources";
import {
  APPLY_FIRST_SYNC,
  CONNECT_HEADING,
  NOT_CONNECTABLE_HERE,
  SAVE_AND_CONNECT,
  SHOW_FIRST_SYNC,
  STEPS_ONLY,
  TEST_CONNECTION,
} from "../src/components/ConnectStaffSource";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { operation } from "./support/openapi";

const PAGE_OPERATION = "/api/v1/govern/staff_sources";
const TRIAL_OPERATION = "/api/v1/govern/staff_sources/trial";
/** What the page reads when it opens: itself, and the nightly sync's three reads (2026-09-21). */
const MOUNT_OPERATIONS = [
  PAGE_OPERATION,
  "/api/v1/govern/staff_sources/credential",
  "/api/v1/govern/staff_sources/guides",
  "/api/v1/govern/staff_sources/runs",
  "/api/v1/govern/staff_sources/transfers",
];
const CONSOLE_ORIGIN = "https://console.test";
const ADDRESS = "/staff_sources";

interface Answers {
  readonly page?: unknown;
  readonly trial?: unknown;
  /** The nightly sync's three reads, and what the two writes answer (2026-09-21). */
  readonly runs?: unknown;
  readonly credential?: unknown;
  readonly transfers?: unknown;
  readonly written?: { method: string; path: string }[];
  /** The connect flow (2026-09-21): the guides read, and what each of its four writes answers. */
  readonly guides?: unknown;
  readonly tested?: unknown;
  readonly connected?: unknown;
  readonly plan?: unknown;
  readonly applied?: unknown;
  /** Every body a write sent, as text, so a test can look for a secret in it. */
  readonly bodies?: string[];
}

function json(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/** One option in the shape `SourceOptionView` serialises. */
function option(
  name: string,
  extra: {
    meaning?: string;
    reads_a_list?: boolean;
    needs?: string[];
    unsupplied?: string[];
    chosen?: boolean;
  } = {},
): unknown {
  return {
    name,
    meaning: extra.meaning ?? `what choosing ${name} means`,
    reads_a_list: extra.reads_a_list ?? true,
    needs: extra.needs ?? [],
    unsupplied: extra.unsupplied ?? [],
    chosen: extra.chosen ?? false,
  };
}

/** The whole page in the shape `StaffSourcesView` serialises. */
function page(
  options: unknown[],
  selection: unknown = null,
  howToChoose = "choose a source under Connect a staff source",
): unknown {
  return { options, selection, how_to_choose: howToChoose };
}

/** One selection in the shape `SelectionView` serialises. */
function selection(
  name: string,
  extra: { refusal?: string; unsupplied?: string[] } = {},
): unknown {
  const refusal = extra.refusal ?? "";
  return {
    name,
    meaning: `what choosing ${name} means`,
    reads_a_list: true,
    unsupplied: extra.unsupplied ?? [],
    refusal,
    ready: refusal === "",
  };
}

/** A trial that produced a plan, in the shape `TrialView` serialises. */
function trialWithPlan(): unknown {
  return {
    trial: {
      source: "spreadsheet",
      plan: {
        source: "spreadsheet",
        would_add: [
          {
            work_address: "ada@example.test",
            display_name: "Ada",
            department: "maintenance",
            groups: ["engineers"],
            active: true,
          },
        ],
        absent: ["hopper@example.test"],
        would_remove: [],
        would_deactivate: [],
        withheld: ["it did not promise a complete list"],
        role_grants_to_add: [],
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
  };
}

/** A trial nothing could run, in the shape `TrialView` serialises. */
function trialUnread(sentence: string): unknown {
  return { trial: null, unread: sentence };
}

/**
 * Mount the application's own route table at this screen's address, against a stand-in API.
 *
 * The real table rather than a copy of it, for the reason `routing.test.tsx` gives: a test that
 * declared its own route would be testing the copy, and this screen's address is half of what is
 * being checked, because it has to be the screen's key for the registry and the browser to be
 * the same list.
 */
async function consoleAt(answers: Answers): Promise<{ container: HTMLElement; idp: FakeIdp }> {
  const idp = fakeIdentityProvider({
    api(url, init) {
      const method = init?.method ?? "GET";
      if (method !== "GET") {
        const path = new URL(url, CONSOLE_ORIGIN).pathname;
        answers.written?.push({ method, path });
        answers.bodies?.push(typeof init?.body === "string" ? init.body : "");
        for (const [suffix, payload] of [
          ["/test", answers.tested],
          ["/connect", answers.connected],
          ["/first-sync/apply", answers.applied],
          ["/first-sync", answers.plan],
        ] as const) {
          if (path.endsWith(`${PAGE_OPERATION}${suffix}`)) {
            return json(payload);
          }
        }
        return json(url.includes("/credential") ? answers.credential : { agent_id: "a_x", owner_id: "u_1" });
      }
      for (const [suffix, payload] of [
        ["/guides", answers.guides],
        ["/runs", answers.runs],
        ["/credential", answers.credential],
        ["/transfers", answers.transfers],
      ] as const) {
        if (url.includes(`${PAGE_OPERATION}${suffix}`)) {
          return payload === undefined ? json({ message: "not here", trace_id: "t" }, 404) : json(payload);
        }
      }
      if (url.includes(TRIAL_OPERATION)) {
        return answers.trial === undefined
          ? null
          : new Response(JSON.stringify(answers.trial), {
              status: 200,
              headers: { "content-type": "application/json" },
            });
      }
      if (url.includes(PAGE_OPERATION) && answers.page !== undefined) {
        return new Response(JSON.stringify(answers.page), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      }
      return null;
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [ADDRESS] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (container.querySelector("h1") === null || container.textContent?.includes("Loading.")) {
      throw new Error("the page has no answer yet");
    }
  });
  return { container, idp };
}

/** Every request this console made to this screen's routes, as URLs. */
function asked(idp: FakeIdp): URL[] {
  return idp.urls
    .filter((url) => url.includes("/api/v1/govern/staff_sources"))
    .map((url) => new URL(url, CONSOLE_ORIGIN));
}

/** Every digit the page rendered, so a count anywhere is a failure rather than a field. */
function digitsOn(container: HTMLElement): string[] {
  return (container.querySelector(".page")?.textContent ?? "").match(/\d+/g) ?? [];
}

describe("what the staff sources screen draws", () => {
  test("it lists every source the API sent, in the order it sent them", async () => {
    // What breaks if this is deleted: a screen that sorts its own rows. `SELECTABLE` is
    // declared in the order a refusal lists its members in, so a console that re-sorted would
    // disagree with the message somebody gets when they mistype a source's name, and the two
    // are read side by side by exactly the person who mistyped.
    const { container } = await consoleAt({
      page: page(
        [option("none", { reads_a_list: false }), option("spreadsheet"), option("lark")],
        selection("none"),
      ),
    });

    const names = [...container.querySelectorAll(".roster code")].map((one) => one.textContent);
    expect(names).toEqual(["none", "spreadsheet", "lark"]);
    expect(container.textContent).toContain(READS_NO_LIST);
  });

  test("it marks the chosen source and marks no other", async () => {
    // What breaks if this is deleted: a screen where every source looks chosen, or none does.
    // Which list this install reads is the one fact somebody opens this screen for.
    const { container } = await consoleAt({
      page: page(
        [option("spreadsheet", { chosen: true }), option("lark")],
        selection("spreadsheet"),
      ),
    });

    expect([...container.querySelectorAll(".badge")].map((one) => one.textContent)).toEqual([
      CHOSEN,
    ]);
  });

  test("it names the settings a source still needs and never what they are set to", async () => {
    // What breaks if this is deleted: a value rendered beside a setting's name. The API has no
    // field for one, which is the real defence; this is the half that stops a console inventing
    // a field and filling it from somewhere else.
    const { container } = await consoleAt({
      page: page(
        [
          option("google_sheet", {
            needs: ["INSTALL_STAFF_SOURCE_LOCATION"],
            unsupplied: ["INSTALL_STAFF_SOURCE_LOCATION"],
            chosen: true,
          }),
        ],
        selection("google_sheet", {
          refusal: "google_sheet is the chosen staff list and it is unset",
          unsupplied: ["INSTALL_STAFF_SOURCE_LOCATION"],
        }),
      ),
    });

    expect(container.textContent).toContain(STILL_TO_SET);
    expect(container.textContent).toContain("INSTALL_STAFF_SOURCE_LOCATION");
    expect(container.textContent).toContain("google_sheet is the chosen staff list and it is unset");
  });

  test("an empty page says there is nothing and says nothing about why", async () => {
    // What breaks if this is deleted: a sentence explaining that the reader was refused. The API
    // answers a caller who holds nothing exactly what it answers a caller whose grant reaches no
    // source, and a console that drew a lock, a dash or an explanation would undo that in one
    // line, on the screen where the two readers are most likely to compare notes.
    const { container } = await consoleAt({ page: page([], null, "") });

    expect(container.textContent).toContain(NO_SOURCES);
    expect(container.querySelectorAll(".lock")).toHaveLength(0);
    expect(container.textContent).not.toContain("permission");
    expect(container.textContent).not.toContain("not allowed");
  });

  test("nothing on this screen renders a number", async () => {
    // What breaks if this is deleted: a count of sources, of settings or of people. Every
    // listing here is narrowed per caller, so a figure is the subtraction the disclosure rule
    // forbids. Asserted over the rendered text rather than over a field, because the field
    // somebody adds is the one nobody thought to look for.
    const { container } = await consoleAt({
      page: page([option("spreadsheet", { chosen: true }), option("lark")], selection("spreadsheet")),
      trial: trialWithPlan(),
    });
    fireEvent.click(await findTrialButton(container));
    await waitFor(() => {
      if (!container.textContent?.includes("ada@example.test")) {
        throw new Error("the trial has not been drawn yet");
      }
    });

    expect(digitsOn(container)).toEqual([]);
  });
});

/** The one control on this page. Found by its own text, which is the verb it performs. */
async function findTrialButton(container: HTMLElement): Promise<HTMLElement> {
  const found = [...container.querySelectorAll("button")].find(
    (one) => one.textContent === RUN_THE_TRIAL,
  );
  if (found === undefined) {
    throw new Error("the trial button is not on the page");
  }
  return found;
}

describe("when the trial is asked for", () => {
  test("nothing is asked of the trial address until somebody presses the button", async () => {
    // What breaks if this is deleted: every load of this screen reads a client's directory. The
    // trial is an outbound call to somebody else's server and a wider disclosure than the rest
    // of the page, and a console that fetched it on mount would make both happen to a reader who
    // only came to see which source was chosen.
    const { idp } = await consoleAt({
      page: page([option("spreadsheet", { chosen: true })], selection("spreadsheet")),
      trial: trialWithPlan(),
    });

    expect(asked(idp).map((url) => url.pathname).sort()).toEqual(MOUNT_OPERATIONS);
  });

  test("pressing it asks the trial address once, and asks for nothing else", async () => {
    // What breaks if this is deleted: a button that reads the source twice per press, or one
    // that asks a second question. A trial is a read of somebody's directory and the count is
    // the only evidence of how many.
    const { container, idp } = await consoleAt({
      page: page([option("spreadsheet", { chosen: true })], selection("spreadsheet")),
      trial: trialWithPlan(),
    });
    fireEvent.click(await findTrialButton(container));
    await waitFor(() => {
      if (!asked(idp).some((url) => url.pathname === TRIAL_OPERATION)) {
        throw new Error("the trial has not been asked for yet");
      }
    });

    expect(asked(idp).map((url) => url.pathname).sort()).toEqual(
      [...MOUNT_OPERATIONS, TRIAL_OPERATION].sort(),
    );
    expect(asked(idp).flatMap((url) => [...url.searchParams.keys()])).toEqual([]);
  });

  test("a trial nothing could run draws the sentence and never an empty plan", async () => {
    // What breaks if this is deleted: an install that never looked reports that nobody would be
    // added. The two shapes are different on the payload and must stay different on the screen:
    // `panel?.would_add ?? []` is one keystroke and it draws the reassuring answer for the
    // state nobody established.
    const sentence = "This install cannot try your staff source yet.";
    const { container } = await consoleAt({
      page: page([option("spreadsheet", { chosen: true })], selection("spreadsheet")),
      trial: trialUnread(sentence),
    });
    fireEvent.click(await findTrialButton(container));
    await waitFor(() => {
      if (!container.textContent?.includes(sentence)) {
        throw new Error("the sentence has not been drawn yet");
      }
    });

    expect(container.textContent).not.toContain(WOULD_ADD_LABEL);
    expect(container.textContent).not.toContain(CHANGES_NOTHING);
  });

  test("a trial that produced a plan names the people rather than counting them", async () => {
    // What breaks if this is deleted: a plan rendered as "1 person would be added". An operator
    // reading a figure cannot tell whether the one is the one they expect, which is the only
    // question a trial exists to answer, and `brain.identity.staff_sync.DryRun` is built as
    // lists rather than counts for exactly that reason.
    const { container } = await consoleAt({
      page: page([option("spreadsheet", { chosen: true })], selection("spreadsheet")),
      trial: trialWithPlan(),
    });
    fireEvent.click(await findTrialButton(container));
    await waitFor(() => {
      if (!container.textContent?.includes("ada@example.test")) {
        throw new Error("the plan has not been drawn yet");
      }
    });

    expect(container.textContent).toContain("Ada");
    expect(container.textContent).toContain("hopper@example.test");
    expect(container.textContent).toContain("it did not promise a complete list");
  });

  test("there is no control anywhere on this page that applies what a trial proposes", async () => {
    // What breaks if this is deleted: somebody adds an Apply button. Applying provisions people
    // and writes role assertions, which is a different authority from reading a configuration
    // screen, and there is no route in the API that could accept it. The assertion is over every
    // button on the page rather than over the absence of one word.
    const { container } = await consoleAt({
      page: page([option("spreadsheet", { chosen: true })], selection("spreadsheet")),
      trial: trialWithPlan(),
    });
    fireEvent.click(await findTrialButton(container));
    await waitFor(() => {
      if (!container.textContent?.includes("ada@example.test")) {
        throw new Error("the plan has not been drawn yet");
      }
    });

    expect(
      [...container.querySelectorAll(".page button")].map((one) => one.textContent),
    ).toEqual([RUN_THE_TRIAL]);
  });
});

describe("what this screen asks the API for", () => {
  test("neither route takes a parameter, so there is no page size to get wrong", () => {
    // What breaks if this is deleted: a `limit` appears on a screen that is answered whole or
    // not at all, and the console starts naming a number the route bounds. The other govern
    // screens read their bounds out of the API's own document and compare the number they ask
    // for against it; this one asserts there is nothing to ask, read from the same document, so
    // the claim is about the route rather than about the console's spelling of it.
    //
    // `declaredQueryParameters` refuses an operation with none, deliberately, because a subset
    // check against an empty set passes for a client that sends nothing. So the operation is
    // read directly here, which is that helper's own underlying call.
    expect(operation(PAGE_OPERATION, "get").parameters ?? []).toEqual([]);
    expect(operation(TRIAL_OPERATION, "get").parameters ?? []).toEqual([]);
  });

  test("an unreadable body is an empty page rather than a thrown error", () => {
    // What breaks if this is deleted: a console built against a different API renders a blank
    // screen with an exception behind it instead of saying there is nothing to show. The shape
    // is fixed by a response model in this repository, so a body that is not this page is not a
    // state worth composing a sentence about.
    expect(readStaffSources(null).options).toEqual([]);
    expect(readStaffSources({ options: "not a list" }).selection).toBeNull();
    expect(readStaffSources(page([option("lark")], selection("lark"))).options).toHaveLength(1);
  });

  test("a trial body carrying neither half is read as unread and never as a plan", () => {
    // What breaks if this is deleted: the absence becomes a plan with nothing in it. The
    // direction to fail in is the one that says less: a page drawing nothing is
    // indistinguishable from a page that had not loaded, and a plan drawing nothing is a claim.
    expect(wasRead(readTrial(null))).toBe(false);
    expect(wasRead(readTrial({ trial: null, unread: "" }))).toBe(false);
    expect(wasRead(readTrial(trialWithPlan() as never))).toBe(true);
  });

  test("the addresses this console uses are the ones the API serves", () => {
    // What breaks if this is deleted: a path typed twice and changed once. The console's own
    // address is the screen's key, which is what `brain.ops.console_screens.routed_screen_keys`
    // matches against the registry, and the API's addresses are what it serves under the prefix.
    expect(`/api/v1${STAFF_SOURCES_API_PATH}`).toBe(PAGE_OPERATION);
    expect(`/api/v1${TRIAL_API_PATH}`).toBe(TRIAL_OPERATION);
    expect(STAFF_SOURCES_HEADING).toBe("Staff sources");
  });
});

// ============================================================ the nightly sync (2026-09-21)
const CREDENTIAL = {
  slot: "connector_keys/staff_source",
  held: false,
  set_at: null,
  vault: "ready",
  told: "The secrets vault answered.",
  form: "The custom app's App ID, a colon, then its App Secret.",
};

const REFUSED_RUN = {
  source: "lark",
  started_at: "2999-03-02T02:00:00Z",
  finished_at: "2999-03-02T02:00:05Z",
  outcome: "credential_refused",
  detail: "The staff source refused the kept credential: app secret invalid. Nobody was changed.",
  added: [],
  marked_left: [],
  renamed: [],
  withheld: [],
  changed_nobody: true,
};

function pressButton(container: HTMLElement, text: string): void {
  const found = [...container.querySelectorAll("button")].find((one) => one.textContent === text);
  if (found === undefined) {
    throw new Error(`no button reading ${text}`);
  }
  fireEvent.click(found);
}

describe("what the nightly sync did, its credential and the agents of people who left", () => {
  test("a run the source refused is drawn as one that changed nobody, in the API's words", async () => {
    // What breaks if this is deleted: M1.8.6's last clause, a refused credential said on this
    // screen, could be recorded by the worker and drawn by nothing.
    const { container } = await consoleAt({ page: page([], null, ""), runs: { runs: [REFUSED_RUN] } });
    await waitFor(() => {
      if (!container.textContent?.includes("app secret invalid")) {
        throw new Error("the runs have not been drawn yet");
      }
    });

    expect(container.textContent).toContain(CHANGED_NOBODY);
    expect(container.textContent).toContain("credential_refused");
  });

  test("the credential card is left out for a reader the API does not answer", async () => {
    // What breaks if this is deleted: a failure notice telling a reader without the credential
    // authority that a credential screen exists and they may not see it.
    const { container } = await consoleAt({ page: page([], null, "") });

    expect(container.textContent).not.toContain(SYNC_CREDENTIAL);
  });

  test("a blank credential is told beside the field and nothing is confirmed or sent", async () => {
    // What breaks if this is deleted: a replace that confirms an empty paste and sends it.
    const written: { method: string; path: string }[] = [];
    const { container } = await consoleAt({ page: page([], null, ""), credential: CREDENTIAL, written });
    await waitFor(() => {
      if (!container.textContent?.includes(CREDENTIAL_NOT_HELD)) {
        throw new Error("the credential card has not been drawn yet");
      }
    });
    pressButton(container, REPLACE_CREDENTIAL);

    await waitFor(() => {
      expect(container.textContent).toContain(CREDENTIAL_BLANK);
    });
    expect(container.querySelector(".confirm")).toBeNull();
    expect(written).toEqual([]);
  });

  test("a credential is replaced only after the confirmation, with a PUT to its one address", async () => {
    // What breaks if this is deleted: M1.8.6's middle clause, the credential replaced from the
    // console, drawn and never sent, or sent on the first press.
    const written: { method: string; path: string }[] = [];
    const { container } = await consoleAt({ page: page([], null, ""), credential: CREDENTIAL, written });
    await waitFor(() => {
      if (!container.textContent?.includes(CREDENTIAL_NOT_HELD)) {
        throw new Error("the credential card has not been drawn yet");
      }
    });
    const field = container.querySelector<HTMLInputElement>("input[name=credential]");
    fireEvent.change(field as HTMLInputElement, { target: { value: "cli_a:secret" } });
    pressButton(container, REPLACE_CREDENTIAL);
    expect(written).toEqual([]);
    const confirm = container.querySelector(".confirm");
    expect(confirm).not.toBeNull();
    fireEvent.click([...(confirm as Element).querySelectorAll("button")].at(-1) as HTMLButtonElement);

    await waitFor(() => {
      expect(written).toEqual([{ method: "PUT", path: "/api/v1/govern/staff_sources/credential" }]);
    });
  });

  test("an agent whose owner left is taken on only after the confirmation, with a POST naming it", async () => {
    // What breaks if this is deleted: M1.8.9's listing drawn with no way to accept it, or an
    // agent handed over on one press.
    const written: { method: string; path: string }[] = [];
    const { container } = await consoleAt({
      page: page([], null, ""),
      transfers: {
        transfers: [{ agent_id: "a_quotes", display_name: "Quotes", owner_id: "u_gone", running: false }],
      },
      written,
    });
    await waitFor(() => {
      if (!container.textContent?.includes("Quotes")) {
        throw new Error("the transfers have not been drawn yet");
      }
    });
    pressButton(container, TAKE_ON);
    expect(written).toEqual([]);
    const confirm = container.querySelector(".confirm");
    fireEvent.click([...(confirm as Element).querySelectorAll("button")].at(-1) as HTMLButtonElement);

    await waitFor(() => {
      expect(written).toEqual([{ method: "POST", path: "/api/v1/govern/staff_sources/transfers/a_quotes" }]);
    });
  });

  test("with nothing waiting the screen says so and offers nothing to press", async () => {
    // What breaks if this is deleted: an empty list drawn as a heading over nothing.
    const { container } = await consoleAt({ page: page([], null, ""), transfers: { transfers: [] } });
    await waitFor(() => {
      expect(container.textContent).toContain(NO_TRANSFERS);
    });

    expect([...container.querySelectorAll("button")].some((one) => one.textContent === TAKE_ON)).toBe(false);
  });
});

// ======================================================== connecting a source (2026-09-21)
const SECRET = "SENTINEL-app-secret-typed-9d2e";

function lark(): unknown {
  return {
    source: "lark",
    title: "Lark (or Feishu)",
    where: "open.larksuite.com/app",
    steps: [
      "Sign in to open.larksuite.com/app.",
      'Open "Permissions & Scopes" and add contact:user.base:readonly and contact:department.base:readonly.',
      'Set the data range to "All members", then release a version.',
      'Copy the App ID and App Secret from "Credentials & Basic Info".',
    ],
    fields: [
      { key: "location", label: "Platform", help: "larksuite.com or feishu.cn", secret: false, example: "larksuite.com" },
      { key: "app_id", label: "App ID", help: "It starts with cli_.", secret: false, example: "cli_a" },
      { key: "app_secret", label: "App Secret", help: "Kept in the vault.", secret: true, example: "" },
    ],
    connectable: true,
    unavailable: "",
    chosen: false,
  };
}

function workspace(): unknown {
  return {
    source: "google_workspace",
    title: "Google Workspace",
    where: "admin.google.com",
    steps: ["Enable the Admin SDK API."],
    fields: [],
    connectable: false,
    unavailable: "Google Workspace cannot be connected for the nightly sync on this version.",
    chosen: false,
  };
}

const GUIDES = { guides: [lark(), workspace()], may_connect: true, schedule: "Read again every night." };

const READ_IT = {
  source: "lark",
  read: true,
  told: "Connected. Nothing was saved.",
  people: 2,
  complete: true,
  skipped: 0,
};

function fill(container: HTMLElement): void {
  for (const [name, value] of [
    ["location", "larksuite.com"],
    ["app_id", "cli_a"],
    ["app_secret", SECRET],
  ]) {
    const field = container.querySelector<HTMLInputElement>(`input[name=${name}]`);
    fireEvent.change(field as HTMLInputElement, { target: { value } });
  }
}

async function drawn(container: HTMLElement, text: string): Promise<void> {
  await waitFor(() => {
    if (!container.textContent?.includes(text)) {
      throw new Error(`nothing reads ${text} yet`);
    }
  });
}

function confirmIt(container: HTMLElement): void {
  const confirm = container.querySelector(".confirm");
  expect(confirm).not.toBeNull();
  fireEvent.click([...(confirm as Element).querySelectorAll("button")].at(-1) as HTMLButtonElement);
}

describe("connecting a staff source from the console", () => {
  test("the chosen kind's steps are drawn in order, and another kind's steps replace them", async () => {
    // What breaks if this is deleted: the owner's "full steps from backend to see how to add",
    // drawn for no source, or for the wrong one after somebody picks another.
    const { container } = await consoleAt({ page: page([], null, ""), guides: GUIDES });
    await drawn(container, CONNECT_HEADING);

    const steps = () => [...container.querySelectorAll("ol li")].map((one) => one.textContent);
    expect(steps()[0]).toBe("Sign in to open.larksuite.com/app.");
    expect(steps().join(" ")).toContain("Credentials & Basic Info");
    pressButton(container, "Google Workspace");

    expect(steps()).toEqual(["Enable the Admin SDK API."]);
    expect(container.textContent).toContain(NOT_CONNECTABLE_HERE);
    expect(container.querySelector("input[name=app_secret]")).toBeNull();
  });

  test("a test is sent once, to its own address, and save is offered only after it read", async () => {
    // What breaks if this is deleted: a save offered before anything proved the credential, or
    // a test that also saved.
    const written: { method: string; path: string }[] = [];
    const { container } = await consoleAt({ page: page([], null, ""), guides: GUIDES, tested: READ_IT, written });
    await drawn(container, CONNECT_HEADING);
    const save = () =>
      [...container.querySelectorAll<HTMLButtonElement>("button")].find((one) => one.textContent === SAVE_AND_CONNECT);
    expect(save()?.disabled).toBe(true);
    fill(container);
    pressButton(container, TEST_CONNECTION);

    await drawn(container, "Nothing was saved.");
    expect(written).toEqual([{ method: "POST", path: "/api/v1/govern/staff_sources/test" }]);
    expect(save()?.disabled).toBe(false);
    expect(container.textContent).not.toContain(SECRET);
  });

  test("an empty form says what to fill in and sends nothing", async () => {
    // What breaks if this is deleted: a blank test sent to a directory with nobody's credential.
    const written: { method: string; path: string }[] = [];
    const { container } = await consoleAt({ page: page([], null, ""), guides: GUIDES, written });
    await drawn(container, CONNECT_HEADING);
    pressButton(container, TEST_CONNECTION);

    await drawn(container, "Fill in every box");
    expect(written).toEqual([]);
  });

  test("saving and applying are each confirmed, the plan is shown first, and the secret is never drawn", async () => {
    // What breaks if this is deleted: the owner's "choose the source (Lark) and connect it" in one
    // unconfirmed press, or a first sync applied on the press meant to show it.
    const written: { method: string; path: string }[] = [];
    const bodies: string[] = [];
    const { container } = await consoleAt({
      page: page([], null, ""),
      guides: GUIDES,
      tested: READ_IT,
      connected: { source: "lark", told: "Connected to Lark (or Feishu).", people: 2 },
      plan: {
        applied: false,
        outcome: "dry_run",
        told: "This is what the first sync would do.",
        added: ["Ada Lovelace"],
        marked_left: [],
        renamed: [],
        withheld: [],
        refusals: [],
        safe_to_apply: true,
      },
      applied: {
        applied: true,
        outcome: "applied",
        told: "Read the staff list from lark and applied it.",
        added: [],
        marked_left: [],
        renamed: [],
        withheld: [],
        refusals: [],
        safe_to_apply: true,
      },
      written,
      bodies,
    });
    await drawn(container, CONNECT_HEADING);
    fill(container);
    pressButton(container, TEST_CONNECTION);
    await drawn(container, "Nothing was saved.");

    pressButton(container, SAVE_AND_CONNECT);
    expect(written.map((one) => one.path)).toEqual(["/api/v1/govern/staff_sources/test"]);
    confirmIt(container);
    await drawn(container, "Connected to Lark (or Feishu).");

    pressButton(container, SHOW_FIRST_SYNC);
    await drawn(container, "Ada Lovelace");
    pressButton(container, APPLY_FIRST_SYNC);
    expect(written.map((one) => one.path).at(-1)).toBe("/api/v1/govern/staff_sources/first-sync");
    confirmIt(container);
    await drawn(container, "applied it");

    expect(written.map((one) => one.path)).toEqual([
      "/api/v1/govern/staff_sources/test",
      "/api/v1/govern/staff_sources/connect",
      "/api/v1/govern/staff_sources/first-sync",
      "/api/v1/govern/staff_sources/first-sync/apply",
    ]);
    expect(bodies.every((one) => one.includes(SECRET))).toBe(true);
    expect(container.textContent).not.toContain(SECRET);
    expect(container.querySelector<HTMLInputElement>("input[name=app_secret]")?.value ?? "").toBe("");
  });

  test("a reader who may not connect is shown the steps and no form", async () => {
    // What breaks if this is deleted: a form drawn for a reader every write would refuse.
    const { container } = await consoleAt({ page: page([], null, ""), guides: { ...GUIDES, may_connect: false } });
    await drawn(container, CONNECT_HEADING);

    expect(container.querySelectorAll("ol li").length).toBeGreaterThan(0);
    expect(container.querySelector("input[name=app_secret]")).toBeNull();
    expect(container.textContent).toContain(STEPS_ONLY);
  });
});

describe("connecting with the Lark app the Connectors screen keeps", () => {
  test("the held app is offered first, asks only where the list is, and sends no credential", async () => {
    // What breaks if this is deleted: the owner pasting the same Lark App Secret a second time, or
    // "use the Lark app" sending an empty credential the API would refuse.
    const written: { method: string; path: string }[] = [];
    const bodies: string[] = [];
    const held = { ...(lark() as Record<string, unknown>), held: "Use the Lark app connected on the Connectors screen." };
    const { container } = await consoleAt({
      page: page([], null, ""),
      guides: { ...GUIDES, guides: [held] },
      connected: { source: "lark", told: "Connected to Lark (or Feishu) with the credential the vault already holds.", people: 0 },
      written,
      bodies,
    });
    await drawn(container, "Use the Lark app connected on the Connectors screen.");

    expect(container.querySelector("input[name=app_secret]")).toBeNull();
    const where = container.querySelector<HTMLInputElement>("input[name=location]");
    fireEvent.change(where as HTMLInputElement, { target: { value: "larksuite.com" } });
    pressButton(container, SAVE_AND_CONNECT);
    expect(written).toEqual([]);
    confirmIt(container);
    await drawn(container, "already holds");

    expect(written).toEqual([{ method: "POST", path: "/api/v1/govern/staff_sources/connect" }]);
    expect(JSON.parse(bodies[0] ?? "{}")).toEqual({ source: "lark", values: { location: "larksuite.com" }, use_held: true });
  });
});
