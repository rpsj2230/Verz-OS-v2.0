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
  readStaffSources,
  readTrial,
  wasRead,
  STAFF_SOURCES_API_PATH,
  TRIAL_API_PATH,
} from "../src/pages/staffSourcesQuery";
import {
  CHANGES_NOTHING,
  CHOSEN,
  NO_SOURCES,
  READS_NO_LIST,
  RUN_THE_TRIAL,
  STAFF_SOURCES_HEADING,
  STILL_TO_SET,
  WOULD_ADD_LABEL,
} from "../src/pages/StaffSources";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { operation } from "./support/openapi";

const PAGE_OPERATION = "/api/v1/govern/staff_sources";
const TRIAL_OPERATION = "/api/v1/govern/staff_sources/trial";
const CONSOLE_ORIGIN = "https://console.test";
const ADDRESS = "/staff_sources";

interface Answers {
  readonly page?: unknown;
  readonly trial?: unknown;
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
  notWrittenHere = "the choice is an installation setting",
): unknown {
  return { options, selection, not_written_here: notWrittenHere };
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
    api(url) {
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

    expect(asked(idp).map((url) => url.pathname)).toEqual([PAGE_OPERATION]);
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
      if (asked(idp).length < 2) {
        throw new Error("the trial has not been asked for yet");
      }
    });

    expect(asked(idp).map((url) => url.pathname)).toEqual([PAGE_OPERATION, TRIAL_OPERATION]);
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
