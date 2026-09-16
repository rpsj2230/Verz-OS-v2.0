/**
 * First run: signed in first, the setup code held in memory only, the wizard's answers posted
 * once, every refusal drawn the way the server meant it, and the console home at the end.
 *
 * **The copies are checked against the originals.** The screens are read out of
 * `brain.setup_wizard.WIZARD` and the sentences out of `brain.locale.MESSAGES`, and the two
 * request bodies against the API document `npm run api:generate` wrote, so a renamed question
 * or a route that moved fails here rather than posting answers the server drops.
 *
 * **The API and the identity provider are stand-ins, as everywhere in this suite.** Sign-in
 * runs through the real `beginSignIn` and `completeSignIn` against `support/auth.ts`'s provider,
 * and the two setup routes and `/api/v1/me` answer from the same stand-in, so what is asserted
 * is what left the browser and what was drawn.
 *
 * **The provider key is searched for as well as the setup code.** A hosted install's key travels
 * in the same body, and the finishing screen that follows a kept key is drawn from a reason and
 * an outcome, never from what was typed.
 *
 * Task ids: M42.5.14, M27.8.7
 */

import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test, vi } from "vitest";
import {
  APPOINTMENT_PATH,
  FINISH_PATH,
  FINISH_TITLE,
  FIRST_RUN_PATH,
  MAX_ANSWER_CHARS,
  MAX_KEY_CHARS,
  MESSAGES,
  REVIEW_TITLE,
  SCREENS,
  SETUP_REFUSED_MESSAGE,
  appointmentBody,
  finishBody,
} from "../src/setup/wizard";
import {
  KEY_KEPT_SENTENCES,
  NOT_CONTINUED_TITLE,
  OPEN_CONSOLE,
  SENDING_SETUP,
  UNKEPT_SENTENCES,
  UNKEPT_TITLE,
} from "../src/pages/FirstRun";
import { THE_BRAIN_COULD_NOT_BE_REACHED } from "../src/ui/FailureNotice";
import { CONSOLE_ORIGIN, everythingInStorage, fakeIdentityProvider, loadConsole, signIn } from "./support/auth";
import {
  declaredPropertyNames,
  declaredRequestBodySchema,
  declaredResponseSchema,
} from "./support/openapi";
import { backendEnumMembers } from "./support/python";
import { backendWizard, catalogueEnglish, catalogueKeys } from "./support/wizard";

/** A code nothing else on the page could contain, so finding it anywhere is a leak. */
const CODE = `CODE-SENTINEL-${"c".repeat(50)}`;
const PRINCIPAL = "u_PRINCIPAL-SENTINEL";
/** A provider key nothing else could contain, searched for wherever the setup code is. */
const KEY = "sk-KEY-SENTINEL-4d7e1b";
const COMPANY = "COMPANY-SENTINEL";
const WEB = "https://brain.example.invalid";

const A_CALLER = {
  principal_id: PRINCIPAL,
  display_name: "DISPLAY-SENTINEL",
  primary_department: "DEPARTMENT-SENTINEL",
  employment: "EMPLOYMENT-SENTINEL",
  assurance: "ASSURANCE-SENTINEL",
  channel: "CHANNEL-SENTINEL",
  ent_hash: "ENTHASH-SENTINEL",
};

function json(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json", "x-trace-id": "TRACE-SENTINEL" },
  });
}

interface Seen {
  readonly path: string;
  readonly body: unknown;
  readonly authorization: string;
}

interface Stand {
  readonly appointment: () => Response;
  readonly signIn?: () => Response;
}

/** A stand-in API answering the two setup routes and `/me`, recording what reached it. */
function standIn(answers: Stand) {
  const seen: Seen[] = [];
  const idp = fakeIdentityProvider({
    api(url, init) {
      const path = new URL(url, CONSOLE_ORIGIN).pathname;
      const headers = (init?.headers ?? {}) as Record<string, string>;
      const record = () =>
        seen.push({
          path,
          body: init?.body === undefined ? null : JSON.parse(String(init.body)),
          authorization: headers["authorization"] ?? "",
        });
      if (path === APPOINTMENT_PATH) {
        record();
        return answers.appointment();
      }
      if (path === FINISH_PATH) {
        record();
        return (answers.signIn ?? (() => json({ principal_id: PRINCIPAL, outcome: "bound" })))();
      }
      if (path === "/api/v1/me") {
        record();
        return json(A_CALLER);
      }
      return null;
    },
  });
  return { idp, seen };
}

function headingOf(container: HTMLElement): string {
  return container.querySelector("h1")?.textContent ?? "";
}

function control(container: HTMLElement, step: string, name: string): HTMLInputElement {
  const found = container.querySelector(`#first-run-${step}-${name}`);
  if (!found) {
    throw new Error(`No control for ${step}.${name} on "${headingOf(container)}".`);
  }
  return found as HTMLInputElement;
}

function give(container: HTMLElement, step: string, name: string, value: string): void {
  fireEvent.change(control(container, step, name), { target: { value } });
}

function press(container: HTMLElement, text: string): void {
  const button = [...container.querySelectorAll("button")].find((one) => one.textContent === text);
  if (!button) {
    throw new Error(`No button "${text}" on "${headingOf(container)}".`);
  }
  if (button.type === "submit" && button.form) {
    fireEvent.submit(button.form);
    return;
  }
  fireEvent.click(button);
}

async function arriveAt(container: HTMLElement, title: string): Promise<void> {
  await waitFor(() => expect(headingOf(container)).toBe(title));
}

/** Sign in through the real flow, returning to first run, and mount the route table there. */
async function openFirstRun(idp: ReturnType<typeof fakeIdentityProvider>) {
  const loaded = await loadConsole({ idp, path: FIRST_RUN_PATH });
  const landed = await signIn(loaded, { returnTo: FIRST_RUN_PATH });
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [landed] });
  const { container } = render(<RouterProvider router={router} />);
  await arriveAt(container, "Enter the setup code");
  return { loaded, router, container, landed };
}

/** Every screen answered, the data sources skipped, ending on the review. */
async function answerEverything(container: HTMLElement, hosted = false): Promise<void> {
  give(container, "setup_code", "setup_code", CODE);
  press(container, "Continue");
  await arriveAt(container, "Your company");
  give(container, "company", "company_name", COMPANY);
  give(container, "company", "web_address", WEB);
  press(container, "Continue");
  await arriveAt(container, "The first administrator");
  give(container, "administrator", "full_name", "NAME-SENTINEL");
  give(container, "administrator", "work_address", "first@example.invalid");
  press(container, "Continue");
  await arriveAt(container, "Your staff list");
  give(container, "staff_source", "staff_source", "spreadsheet");
  press(container, "Continue");
  await arriveAt(container, "How questions are answered");
  if (hosted) {
    give(container, "model_provider", "model_profile", "hosted");
    give(container, "model_provider", "model_provider", "anthropic");
    give(container, "model_provider", "provider_key", KEY);
  } else {
    give(container, "model_provider", "model_profile", "local");
  }
  press(container, "Continue");
  await arriveAt(container, "Data sources");
  press(container, "Skip this screen");
  await arriveAt(container, REVIEW_TITLE);
}

function callsTo(seen: readonly Seen[], path: string): Seen[] {
  return seen.filter((one) => one.path === path);
}

beforeAll(async () => {
  await import("../src/App");
}, 60_000);

describe("the console's copy of the wizard", () => {
  test("the screens are the wizard's screens, in its order, asking its questions", () => {
    // What breaks if this is deleted: a question renamed, added, made optional or given a new
    // choice in `brain.setup_wizard` and not here. The console would post a field the route
    // drops, or never ask for one it requires, and every install would stop on a 422 naming a
    // field no screen draws.
    const backend = backendWizard();
    expect(backend.map((step) => step.key)).toEqual([
      ...SCREENS.map((screen) => screen.key),
      "review",
      "finish",
    ]);
    for (const screen of SCREENS) {
      const original = backend.find((step) => step.key === screen.key);
      expect(original?.skippable, screen.key).toBe(screen.skippable);
      expect(
        screen.questions.map(({ name, required, secret, maxChars, choices }) => ({
          name,
          required,
          secret,
          maxChars,
          choices,
        })),
        screen.key,
      ).toEqual(original?.questions);
    }
    expect(new Set(backend.flatMap((step) => step.questions.map((one) => one.maxChars)))).toEqual(
      new Set([MAX_ANSWER_CHARS, MAX_KEY_CHARS]),
    );
  });

  test("every title, label and problem sentence is the catalogue's English", () => {
    // What breaks if this is deleted: a sentence here that says something the catalogue does
    // not, and a 422 drawn in words nobody reviewed. Both directions for the problems, so a key
    // the wizard gains is a failure rather than "Check this answer" beside a box.
    const backend = backendWizard();
    for (const screen of SCREENS) {
      const original = backend.find((step) => step.key === screen.key);
      expect(screen.title).toBe(catalogueEnglish(original?.titleKey ?? ""));
      for (const question of screen.questions) {
        expect(question.label).toBe(catalogueEnglish(`field.${question.name}.label`));
      }
    }
    expect(REVIEW_TITLE).toBe(catalogueEnglish("setup.step.review.title"));
    expect(FINISH_TITLE).toBe(catalogueEnglish("setup.step.finish.title"));
    const keys = [...catalogueKeys("setup.error."), ...catalogueKeys("setup.review.")].sort();
    expect(Object.keys(MESSAGES).sort()).toEqual(keys);
    for (const key of keys) {
      expect(MESSAGES[key], key).toBe(catalogueEnglish(key));
    }
  });

  test("both request bodies are the ones the API document says the routes take", () => {
    // What breaks if this is deleted: a body key the route forbids. Both models set
    // `extra="forbid"`, so a renamed key is a 422 carrying no problems on every install, drawn
    // as the least useful sentence this console has.
    expect(declaredPropertyNames(declaredRequestBodySchema(APPOINTMENT_PATH, "post"))).toEqual(
      Object.keys(appointmentBody("x", {}, new Set())).sort(),
    );
    expect(declaredPropertyNames(declaredRequestBodySchema(FINISH_PATH, "post"))).toEqual(
      Object.keys(finishBody("x", "y")).sort(),
    );
    expect(declaredPropertyNames(declaredResponseSchema(APPOINTMENT_PATH, "post"))).toContain(
      "principal_id",
    );
    expect(declaredPropertyNames(declaredResponseSchema(APPOINTMENT_PATH, "post", "422"))).toEqual([
      "problems",
    ]);
    expect(declaredPropertyNames(declaredResponseSchema(APPOINTMENT_PATH, "post", "409"))).toEqual([
      "reason",
      "unkept",
      "variables",
    ]);
    expect(declaredPropertyNames(declaredResponseSchema(APPOINTMENT_PATH, "post"))).toContain(
      "provider_key",
    );
  });

  test("every reason a key is not kept, and every outcome of keeping one, has its sentence here", () => {
    // What breaks if this is deleted: a reason or an outcome added to `brain.setup_routes` and not
    // here. A 409 with a reason this page has no sentence for is drawn as the generic failure, and a
    // kept key with an outcome it does not know lands on the console with nothing said, which is
    // the one moment the person needed to be told a restart is due.
    const reasons = Object.values(backendEnumMembers("src/brain/setup_routes.py", "NotKeptReason"));
    const outcomes = Object.values(backendEnumMembers("src/brain/setup_routes.py", "ProviderKeyKept"));
    expect(Object.keys(UNKEPT_SENTENCES).sort()).toEqual([...reasons].sort());
    expect([...Object.keys(KEY_KEPT_SENTENCES), "not_asked"].sort()).toEqual([...outcomes].sort());
    expect(new Set(Object.values(UNKEPT_SENTENCES)).size).toBe(reasons.length);
    expect(new Set(Object.values(KEY_KEPT_SENTENCES)).size).toBe(outcomes.length - 1);
  });
});

describe("before anything is asked", () => {
  test("a person with no session is sent to sign in and brought back to first run", async () => {
    // What breaks if this is deleted: the order the setup code's safety depends on. A page that
    // asked for the code first would lose it to the sign-in redirect, and one that carried it
    // across would put it in a store or an address. The callback must also return here and not
    // to the overview, whose `/me` refuses a sign-in bound to nobody.
    const loaded = await loadConsole({ path: FIRST_RUN_PATH });
    const { routes } = await import("../src/App");
    const router = createMemoryRouter(routes, { initialEntries: [FIRST_RUN_PATH] });
    const { container } = render(<RouterProvider router={router} />);

    expect(headingOf(container)).toBe("Set up this system");
    expect(container.querySelector("#first-run-setup_code-setup_code")).toBeNull();
    press(container, "Sign in to begin");

    await waitFor(() => expect(loaded.location.assign).toHaveBeenCalled());
    const pending = JSON.parse(
      sessionStorage.getItem(loaded.constants.PENDING_SIGN_IN_KEY) ?? "null",
    ) as { returnTo: string };
    expect(pending.returnTo).toBe(FIRST_RUN_PATH);
    expect(loaded.location.lastAssigned().searchParams.get("response_type")).toBe("code");
  });
});

describe("the whole of first run", () => {
  test("the finished wizard appoints, signs in with the token, and lands on the console home", async () => {
    // What breaks if this is deleted: M42.5.14 itself. The appointment's principal must reach
    // the finishing screen with the same code and the held token as the bearer, in that order,
    // and the person must end on the overview signed in rather than on a page asking them to
    // do something else.
    const { idp, seen } = standIn({
      appointment: () => json({ principal_id: PRINCIPAL, finish_path: FINISH_PATH, provider_key: "not_asked" }),
    });
    const { container, router, landed } = await openFirstRun(idp);
    expect(landed).toBe(FIRST_RUN_PATH);

    await answerEverything(container);
    press(container, "Set up this system");
    await arriveAt(container, "Overview");

    // Waited for rather than asserted outright: the overview's own read of `/me` is fired by
    // the page, so the heading can be on screen a tick before the request is recorded. This
    // read as a stable assertion until the twelve console screens changed what the shell loads
    // on the way in, and then failed in CI on a flow that was working.
    await waitFor(() =>
      expect(seen.map((one) => one.path)).toEqual([APPOINTMENT_PATH, FINISH_PATH, "/api/v1/me"]),
    );
    expect(callsTo(seen, APPOINTMENT_PATH)[0]?.body).toEqual({
      setup_code: CODE,
      answers: {
        company: { company_name: COMPANY, product_name: "", web_address: WEB, logo_url: "" },
        administrator: { full_name: "NAME-SENTINEL", work_address: "first@example.invalid" },
        staff_source: { staff_source: "spreadsheet" },
        model_provider: { model_profile: "local", model_provider: "", provider_key: "" },
      },
      skipped: ["connections"],
    });
    const finishing = callsTo(seen, FINISH_PATH)[0];
    expect(finishing?.body).toEqual({ setup_code: CODE, principal_id: PRINCIPAL });
    expect(finishing?.authorization).toBe("Bearer ACCESS-TOKEN-1");
    expect(router.state.location.pathname).toBe("/");
  });

  test("the setup code reaches no browser store and no address at any point", async () => {
    // What breaks if this is deleted: the code in a store any script on the origin can read, or
    // in an address that lands in history, a proxy's log and a referrer. It is the one value
    // that makes whoever holds it the widest role on a fresh install, so it is looked for in
    // every write to either store, in both stores at the end, and in every address the page
    // held or was sent to.
    const writes = vi.spyOn(Storage.prototype, "setItem");
    const { idp } = standIn({
      appointment: () => json({ principal_id: PRINCIPAL, finish_path: FINISH_PATH, provider_key: "not_asked" }),
    });
    const { container, router, loaded } = await openFirstRun(idp);
    const addresses: string[] = [];
    const stop = router.subscribe((state) => {
      addresses.push(`${state.location.pathname}${state.location.search}${state.location.hash}`);
    });

    await answerEverything(container);
    press(container, "Set up this system");
    await arriveAt(container, "Overview");
    stop();

    for (const call of writes.mock.calls) {
      expect(String(call[1])).not.toContain(CODE);
    }
    const stored = everythingInStorage();
    expect([...stored.keys, ...stored.values].join("\n")).not.toContain(CODE);
    expect(addresses.length).toBeGreaterThan(0);
    expect(addresses.join("\n")).not.toContain(CODE);
    expect(loaded.location.assign.mock.calls.map((call) => String(call[0])).join("\n")).not.toContain(
      CODE,
    );
    expect(container.querySelector("form")).toBeNull();
  });
  test.each(["in_use", "outranked", "from_environment"] as const)(
    "a key kept as %s stops the finish on what the person must know, then opens the console",
    async (outcome) => {
      // What breaks if this is deleted: the honesty of the finishing screen. A key kept in the vault
      // is in use by one server process at once, or by none while the environment file outranks it,
      // and a person landed straight on the console asks a question that fails with no idea why.
      // The local install's test above is the sibling that still lands at once.
      const writes = vi.spyOn(Storage.prototype, "setItem");
      const { idp, seen } = standIn({
        appointment: () =>
          json({ principal_id: PRINCIPAL, finish_path: FINISH_PATH, provider_key: outcome }),
      });
      const { container, router } = await openFirstRun(idp);
      await answerEverything(container, true);
      press(container, "Set up this system");

      await waitFor(() => expect(container.textContent).toContain(KEY_KEPT_SENTENCES[outcome]));
      expect(headingOf(container)).toBe(FINISH_TITLE);
      expect(router.state.location.pathname).toBe(FIRST_RUN_PATH);
      expect(callsTo(seen, APPOINTMENT_PATH)[0]?.body).toMatchObject({
        answers: {
          model_provider: { model_profile: "hosted", model_provider: "anthropic", provider_key: KEY },
        },
      });
      expect(callsTo(seen, FINISH_PATH)).toHaveLength(1);
      expect(container.textContent).not.toContain(KEY);
      for (const call of writes.mock.calls) {
        expect(String(call[1])).not.toContain(KEY);
      }
      const stored = everythingInStorage();
      expect([...stored.keys, ...stored.values].join("\n")).not.toContain(KEY);

      press(container, OPEN_CONSOLE);
      await arriveAt(container, "Overview");
      expect(router.state.location.pathname).toBe("/");
      writes.mockRestore();
    },
  );
});

describe("what a refusal is drawn as", () => {
  test("problems with the answers are drawn beside the fields they name", async () => {
    // What breaks if this is deleted: a 422 drawn as a banner, or against the wrong box. The
    // route names a step and a field for each problem precisely so the sentence sits beside
    // its input, and a person told "this is needed" at the top of a review of twenty answers
    // has been told nothing they can act on.
    const { idp, seen } = standIn({
      appointment: () =>
        json(
          {
            problems: [
              { step: "company", field: "company_name", key: "setup.error.blank" },
              { step: "company", field: "web_address", key: "setup.error.not_absolute" },
              { step: "company", field: "", key: "setup.review.not_given" },
            ],
          },
          422,
        ),
    });
    const { container } = await openFirstRun(idp);
    await answerEverything(container);
    press(container, "Set up this system");
    await arriveAt(container, "Your company");

    const named = control(container, "company", "company_name");
    expect(named.getAttribute("aria-invalid")).toBe("true");
    const describedBy = named.getAttribute("aria-describedby") ?? "";
    expect(container.querySelector(`#${describedBy}`)?.textContent).toBe(
      catalogueEnglish("setup.error.blank"),
    );
    const web = control(container, "company", "web_address");
    expect(container.querySelector(`#${web.getAttribute("aria-describedby") ?? ""}`)?.textContent).toBe(
      catalogueEnglish("setup.error.not_absolute"),
    );
    // The sibling that proves the mapping is by field and not everything on the screen.
    expect(control(container, "company", "product_name").getAttribute("aria-invalid")).not.toBe("true");
    expect(container.querySelector(".first-run__step-problems")?.textContent).toBe(
      catalogueEnglish("setup.review.not_given"),
    );
    expect(callsTo(seen, FINISH_PATH)).toEqual([]);
  });

  test.each(["no_vault", "vault_unreachable", "vault_refused", "not_a_key"] as const)(
    "a key not kept for %s is told by its reason, and only a vaultless install is shown a variable",
    async (reason) => {
      // What breaks if this is deleted: the one thing a person can do about a 409, which differs by
      // reason. An install with no vault is told to set up a vault or set the named variable; a
      // silent vault to start it; a refusing one to load its policy; a bad paste to paste again. A
      // console that drew the variable for every reason would send somebody with a vault to edit
      // an environment file, and one that echoed the key would put a credential on the screen.
      const { idp, seen } = standIn({
        appointment: () =>
          json({ unkept: ["providers/anthropic"], variables: ["ANTHROPIC_API_KEY"], reason }, 409),
      });
      const { container } = await openFirstRun(idp);
      await answerEverything(container, true);
      press(container, "Set up this system");

      await waitFor(() => expect(container.querySelector(".notice")).not.toBeNull());
      const notice = container.querySelector(".notice");
      expect(notice?.querySelector(".notice__title")?.textContent).toBe(UNKEPT_TITLE);
      expect(notice?.querySelector(".notice__body p")?.textContent).toBe(UNKEPT_SENTENCES[reason]);
      const names = [...(notice?.querySelectorAll(".first-run__names li") ?? [])].map(
        (one) => one.textContent,
      );
      expect(names).toEqual(reason === "no_vault" ? ["ANTHROPIC_API_KEY"] : []);
      expect(container.textContent).not.toContain(KEY);
      expect(headingOf(container)).toBe(REVIEW_TITLE);
      expect(callsTo(seen, FINISH_PATH)).toEqual([]);
    },
  );

  test("a 409 whose reason this page does not know is drawn as a failure and not as an empty notice", async () => {
    // What breaks if this is deleted: the sibling of the test above. A reason the server gained and
    // this page did not would be drawn under the key heading with no sentence at all, which tells the
    // person something went wrong with their key and nothing about what.
    const { idp } = standIn({
      appointment: () => json({ unkept: ["providers/anthropic"], variables: [], reason: "new_reason" }, 409),
    });
    const { container } = await openFirstRun(idp);
    await answerEverything(container, true);
    press(container, "Set up this system");

    await waitFor(() => expect(container.querySelector(".notice")).not.toBeNull());
    expect(container.querySelector(".notice__title")?.textContent).toBe(NOT_CONTINUED_TITLE);
  });

  test("a setup still being sent, one that cannot reach the API and one the API failed are three different sentences", async () => {
    // What breaks if this is deleted: the wizard drawing "not continued" over a laptop that lost its
    // network, which reads as the server having refused the installer, or drawing nothing but two
    // greyed-out buttons while the answers are on their way. `tests/screen-states.test.tsx` excuses
    // this page from its loop because it asks nothing on arrival, and points here.
    const sending = standIn({ appointment: () => json({}, 500) });
    const hanging = {
      ...sending.idp,
      fetch: vi.fn(async (input: unknown, init?: RequestInit) =>
        new URL(String(input), CONSOLE_ORIGIN).pathname === APPOINTMENT_PATH
          ? await new Promise<Response>(() => undefined)
          : ((await sending.idp.fetch(input, init)) as Response),
      ),
    };
    const opened = await openFirstRun(hanging);
    await answerEverything(opened.container, true);
    press(opened.container, "Set up this system");
    await waitFor(() => expect(opened.container.querySelector('[role="status"]')?.textContent).toBe(SENDING_SETUP));
    expect(opened.container.querySelector(".notice")).toBeNull();
    cleanup();
    sessionStorage.clear();

    const headings: string[] = [];
    for (const appointment of [
      (): Response => {
        throw new TypeError("Failed to fetch");
      },
      (): Response => json({ message: "MESSAGE-SENTINEL" }, 500),
    ]) {
      const { idp } = standIn({ appointment });
      const { container } = await openFirstRun(idp);
      await answerEverything(container, true);
      press(container, "Set up this system");
      await waitFor(() => expect(container.querySelector(".notice")).not.toBeNull());
      headings.push(container.querySelector(".notice__title")?.textContent ?? "");
      cleanup();
      sessionStorage.clear();
    }
    expect(headings).toEqual([THE_BRAIN_COULD_NOT_BE_REACHED, NOT_CONTINUED_TITLE]);
    expect(THE_BRAIN_COULD_NOT_BE_REACHED).not.toBe(NOT_CONTINUED_TITLE);
  });

  test("every refusal before the answers is one sentence that gives no reason", async () => {
    // What breaks if this is deleted: the console turning one 404 back into several. The
    // server makes a finished install, a wrong code and a lost race one answer so that whoever
    // finds the address learns nothing, and a console that drew the body's words, or a
    // helpful "check your code", would tell them which it was.
    const drawn: string[] = [];
    for (const message of ["REASON-ONE the code has expired", "REASON-TWO already administered"]) {
      const { idp, seen } = standIn({
        appointment: () => json({ message, trace_id: "T" }, 404),
      });
      const { container } = await openFirstRun(idp);
      await answerEverything(container);
      press(container, "Set up this system");
      await waitFor(() => expect(container.querySelector(".notice")).not.toBeNull());

      const body = container.querySelector(".notice .notice__body")?.textContent ?? "";
      expect(body).toBe(SETUP_REFUSED_MESSAGE);
      expect(container.textContent).not.toContain(message);
      expect(container.querySelector(".notice__trace")).toBeNull();
      expect(callsTo(seen, FINISH_PATH)).toEqual([]);
      drawn.push(container.textContent ?? "");
      document.body.innerHTML = "";
    }
    expect(drawn[0]).toBe(drawn[1]);
    expect(SETUP_REFUSED_MESSAGE.toLowerCase()).not.toMatch(/code|expire|finish|administrator|already|wrong/);
  });
});
