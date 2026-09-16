/**
 * First run's staff list check: a spreadsheet read from a chosen file, a directory signed in to in
 * a second window, and nothing either of them holds reaching the appointment.
 *
 * **Driven through the real first run.** Sign-in runs through `support/auth.ts`'s provider, the
 * wizard is answered screen by screen, and the three staff list routes answer from the same
 * stand-in as the appointment, so what is asserted is what left the browser and what was drawn.
 * The pop-up is a stand-in window whose address the page sets, and the vendor's answer arrives
 * as a message the test posts, the way `pages/StaffListSignedIn.tsx` posts it.
 *
 * **The copies are checked against the originals.** The three addresses and the return path are
 * read out of the Python modules that serve them, and both request bodies against the API
 * document, so a route that moves fails here rather than on a company's server.
 *
 * Task ids: M42.5.7
 */

import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, test, vi } from "vitest";
import { APPOINTMENT_PATH, FIRST_RUN_PATH, REVIEW_TITLE } from "../src/setup/wizard";
import {
  REGISTRATION_PATH,
  RETURN_PATH,
  SIGNED_IN_KIND,
  SIGN_IN_PATH,
  TRIAL_PATH,
  codeFrom,
  directoryTrialBody,
  signInBody,
  type Attempt,
} from "../src/setup/staffList";
import {
  CLIENT_ID_LABEL,
  NOT_READ_TITLE,
  READ_THE_SHEET,
  SIGN_IN_AND_READ,
  WOULD_ADD_TITLE,
} from "../src/components/StaffListCheck";
import { SIGNED_IN_TITLE } from "../src/pages/StaffListSignedIn";
import { CONSOLE_ORIGIN, fakeIdentityProvider, loadConsole, signIn } from "./support/auth";
import { declaredPropertyNames, declaredRequestBodySchema } from "./support/openapi";
import { extractOne, readRepoFile } from "./support/repo";

const CODE = `CODE-SENTINEL-${"c".repeat(50)}`;
const PRINCIPAL = "u_PRINCIPAL-SENTINEL";
const CLIENT_SECRET = "CLIENT-SECRET-SENTINEL-8b1f";
const SHEET_TEXT = "Work Email,Full Name\nSHEET-SENTINEL@example.invalid,Sheet Person\n";
const TENANT = "8f1a0e5c-0000-4000-8000-00000000000a";
const VENDOR_PAGE = "https://login.example.invalid/authorize?state=from-the-server";

function json(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json", "x-trace-id": "TRACE-SENTINEL" },
  });
}

interface Seen {
  readonly path: string;
  readonly body: unknown;
}

/** A plan adding the people named, as `TrialView` serialises one. */
function plan(source: string, people: readonly string[]): unknown {
  return {
    trial: {
      source,
      plan: {
        source,
        would_add: people.map((address) => ({
          work_address: address,
          display_name: `Name of ${address}`,
          department: "",
          groups: [],
          active: true,
        })),
        absent: [],
        would_remove: [],
        would_deactivate: [],
        withheld: ["WITHHELD-SENTINEL"],
        role_grants_to_add: [],
        role_grants_to_remove: [],
        refusals: [],
        gaps: [],
        safe_to_apply: false,
        changes_nothing: false,
      },
      refusals: [],
      safe_to_apply: false,
    },
    unread: "",
  };
}

function standIn(trial: () => Response) {
  const seen: Seen[] = [];
  const idp = fakeIdentityProvider({
    api(url, init) {
      const path = new URL(url, CONSOLE_ORIGIN).pathname;
      const record = () =>
        seen.push({ path, body: init?.body === undefined ? null : JSON.parse(String(init.body)) });
      if (path === REGISTRATION_PATH) {
        record();
        return json({
          sources: [
            { source: "microsoft_entra", where: "WHERE-SENTINEL", grant: "GRANT-SENTINEL", location: "LOCATION-SENTINEL" },
          ],
          return_path: RETURN_PATH,
        });
      }
      if (path === SIGN_IN_PATH) {
        record();
        return json({ address: VENDOR_PAGE, problem: "" });
      }
      if (path === TRIAL_PATH) {
        record();
        return trial();
      }
      if (path === APPOINTMENT_PATH) {
        record();
        return json({ message: "stop here" }, 500);
      }
      return null;
    },
  });
  return { idp, seen };
}

function headingOf(container: HTMLElement): string {
  return container.querySelector("h1")?.textContent ?? "";
}

function give(container: HTMLElement, id: string, value: string): void {
  const found = container.querySelector(`#${id}`);
  if (!found) {
    throw new Error(`No control #${id} on "${headingOf(container)}".`);
  }
  fireEvent.change(found, { target: { value } });
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

/** Signed in, the code given, and the first two screens answered, ending on the staff list. */
async function openAtTheStaffList(idp: ReturnType<typeof fakeIdentityProvider>) {
  const loaded = await loadConsole({ idp, path: FIRST_RUN_PATH });
  const landed = await signIn(loaded, { returnTo: FIRST_RUN_PATH });
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [landed] });
  const { container } = render(<RouterProvider router={router} />);
  await arriveAt(container, "Enter the setup code");
  give(container, "first-run-setup_code-setup_code", CODE);
  press(container, "Continue");
  await arriveAt(container, "Your company");
  give(container, "first-run-company-company_name", "COMPANY-SENTINEL");
  give(container, "first-run-company-web_address", "https://brain.example.invalid");
  press(container, "Continue");
  await arriveAt(container, "The first administrator");
  give(container, "first-run-administrator-full_name", "NAME-SENTINEL");
  give(container, "first-run-administrator-work_address", "first@example.invalid");
  press(container, "Continue");
  await arriveAt(container, "Your staff list");
  return { container, router };
}

/** From the staff list to the review, and the review sent, so the appointment body is recorded. */
async function sendTheReview(container: HTMLElement): Promise<void> {
  press(container, "Continue");
  await arriveAt(container, "How questions are answered");
  give(container, "first-run-model_provider-model_profile", "local");
  press(container, "Continue");
  await arriveAt(container, "Data sources");
  press(container, "Skip this screen");
  await arriveAt(container, REVIEW_TITLE);
  press(container, "Set up this system");
}

beforeAll(async () => {
  await import("../src/App");
}, 60_000);

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the staff list check's copies of the server", () => {
  test("the three addresses and the return path are the ones the server serves", () => {
    // What breaks if this is deleted: a route renamed on the server and not here, so the check
    // posts to nothing and every company's sign-in stops at a 404 drawn as the setup refusal.
    const routes = readRepoFile("src/brain/setup_staff_routes.py");
    const directories = readRepoFile("src/brain/connectors/staff_directories.py");
    const constant = (source: string, name: string) =>
      extractOne(source, new RegExp(`^${name}: Final = "([^"]+)"$`, "m"), name);
    expect(REGISTRATION_PATH).toBe(constant(routes, "REGISTRATION_PATH"));
    expect(SIGN_IN_PATH).toBe(constant(routes, "SIGN_IN_PATH"));
    expect(TRIAL_PATH).toBe(constant(routes, "TRIAL_PATH"));
    expect(RETURN_PATH).toBe(constant(directories, "RETURN_PATH"));
  });

  test("both request bodies are the ones the API document says the routes take", () => {
    // What breaks if this is deleted: a body key the route forbids. Both models forbid extras,
    // so a renamed key is a 422 on every sign-in, with nothing the page can say about it.
    const attempt: Attempt = { state: "s", verifier: "v", challenge: "c" };
    expect(declaredPropertyNames(declaredRequestBodySchema(SIGN_IN_PATH, "post"))).toEqual(
      Object.keys(signInBody("x", "y", "z", "w", CONSOLE_ORIGIN, attempt)).sort(),
    );
    expect(declaredPropertyNames(declaredRequestBodySchema(TRIAL_PATH, "post"))).toEqual(
      Object.keys(directoryTrialBody("x", "y", "z", "w", "v", "u", CONSOLE_ORIGIN, attempt)).sort(),
    );
  });
});

describe("what a sign-in window's message may say", () => {
  const attempt: Attempt = { state: "STATE-OF-THIS-ATTEMPT", verifier: "v", challenge: "c" };
  const answer = { kind: SIGNED_IN_KIND, state: attempt.state, code: "THE-CODE", error: "" };

  test("only a message from this origin, of this kind, with this attempt's state is believed", () => {
    // What breaks if this is deleted: `A_MESSAGE_IS_BELIEVED_FROM_THIS_ORIGIN_WITH_THIS_STATE`. Any
    // window that can message this tab could hand it a code of its own choosing, and the read
    // would sign in to whatever account that code belongs to.
    expect(codeFrom({ origin: CONSOLE_ORIGIN, data: answer }, CONSOLE_ORIGIN, attempt)).toBe("THE-CODE");
    expect(codeFrom({ origin: "https://elsewhere.invalid", data: answer }, CONSOLE_ORIGIN, attempt)).toBeNull();
    expect(
      codeFrom({ origin: CONSOLE_ORIGIN, data: { ...answer, state: "ANOTHER" } }, CONSOLE_ORIGIN, attempt),
    ).toBeNull();
    expect(
      codeFrom({ origin: CONSOLE_ORIGIN, data: { ...answer, kind: "something.else" } }, CONSOLE_ORIGIN, attempt),
    ).toBeNull();
    expect(() =>
      codeFrom({ origin: CONSOLE_ORIGIN, data: { ...answer, code: "", error: "access_denied" } }, CONSOLE_ORIGIN, attempt),
    ).toThrow("access_denied");
  });
});

describe("reading the list before setup is sent", () => {
  test("a spreadsheet is chosen, read, drawn as the people it adds, and kept out of the appointment", async () => {
    // What breaks if this is deleted: the spreadsheet half of M42.5.7. The file's text must reach
    // the read with the setup code, the plan must be drawn as people rather than a count, and the
    // file must never become an answer the appointment carries.
    const { idp, seen } = standIn(() => json(plan("spreadsheet", ["SHEET-SENTINEL@example.invalid"])));
    const { container } = await openAtTheStaffList(idp);
    give(container, "first-run-staff_source-staff_source", "spreadsheet");

    const input = container.querySelector("#first-run-staff-list-sheet") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File([SHEET_TEXT], "staff.csv", { type: "text/csv" })] } });
    await waitFor(() =>
      expect(
        [...container.querySelectorAll("button")].find((one) => one.textContent === READ_THE_SHEET)?.disabled,
      ).toBe(false),
    );
    press(container, READ_THE_SHEET);

    await waitFor(() => expect(container.textContent).toContain(WOULD_ADD_TITLE));
    const read = seen.find((one) => one.path === TRIAL_PATH)?.body as Record<string, string>;
    expect(read["setup_code"]).toBe(CODE);
    expect(read["staff_source"]).toBe("spreadsheet");
    expect(read["sheet"]).toBe(SHEET_TEXT);
    expect(container.querySelector(`[aria-label="${WOULD_ADD_TITLE}"]`)?.textContent).toContain(
      "SHEET-SENTINEL@example.invalid",
    );
    expect(container.textContent).not.toMatch(/\b1 (person|people)\b/);

    await sendTheReview(container);
    await waitFor(() => expect(seen.some((one) => one.path === APPOINTMENT_PATH)).toBe(true));
    const appointment = JSON.stringify(seen.find((one) => one.path === APPOINTMENT_PATH)?.body);
    expect(appointment).not.toContain("SHEET-SENTINEL");
    expect(JSON.parse(appointment).answers.staff_source).toEqual({
      staff_source: "spreadsheet",
      staff_source_location: "",
    });
  });

  test("a directory is signed in to in a second window, read with the verifier, and its secret goes nowhere else", async () => {
    // What breaks if this is deleted: the directory half of M42.5.7, and the three properties the
    // pop-up rests on. The vendor's page opens in the window rather than this tab, a message with
    // the wrong state reads nothing, the read carries the verifier whose challenge was sent, and
    // the client secret is in the read and in no other request, the appointment included.
    const { idp, seen } = standIn(() => json(plan("microsoft_entra", ["DIRECTORY-SENTINEL@example.invalid"])));
    const popup = { location: { href: "" }, close: vi.fn() };
    const opened = vi.fn(() => popup);
    vi.stubGlobal("open", opened);
    const { container } = await openAtTheStaffList(idp);

    give(container, "first-run-staff_source-staff_source", "microsoft_entra");
    give(container, "first-run-staff_source-staff_source_location", TENANT);
    await waitFor(() => expect(container.textContent).toContain("WHERE-SENTINEL"));
    expect(container.textContent).toContain(`${CONSOLE_ORIGIN}${RETURN_PATH}`);
    expect(container.textContent).toContain(CLIENT_ID_LABEL);
    give(container, "first-run-staff-list-client-id", "CLIENT-ID-SENTINEL");
    give(container, "first-run-staff-list-client-secret", CLIENT_SECRET);
    press(container, SIGN_IN_AND_READ);

    await waitFor(() => expect(popup.location.href).toBe(VENDOR_PAGE));
    expect(opened).toHaveBeenCalledTimes(1);
    const started = seen.find((one) => one.path === SIGN_IN_PATH)?.body as Record<string, string>;
    expect(started["setup_code"]).toBe(CODE);
    expect(started["location"]).toBe(TENANT);
    expect(started["redirect_uri"]).toBe(`${CONSOLE_ORIGIN}${RETURN_PATH}`);
    expect(JSON.stringify(started)).not.toContain(CLIENT_SECRET);

    window.dispatchEvent(
      new MessageEvent("message", {
        origin: CONSOLE_ORIGIN,
        data: { kind: SIGNED_IN_KIND, state: "NOT-THIS-ATTEMPT", code: "WRONG-CODE", error: "" },
      }),
    );
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(seen.some((one) => one.path === TRIAL_PATH)).toBe(false);

    window.dispatchEvent(
      new MessageEvent("message", {
        origin: CONSOLE_ORIGIN,
        data: { kind: SIGNED_IN_KIND, state: started["state"], code: "RETURNED-CODE", error: "" },
      }),
    );
    await waitFor(() => expect(container.textContent).toContain("DIRECTORY-SENTINEL@example.invalid"));

    const read = seen.find((one) => one.path === TRIAL_PATH)?.body as Record<string, string>;
    expect(read["code"]).toBe("RETURNED-CODE");
    expect(read["client_secret"]).toBe(CLIENT_SECRET);
    const { challengeFor } = await import("../src/auth/pkce");
    expect(await challengeFor(read["verifier"] ?? "")).toBe(started["challenge"]);

    await sendTheReview(container);
    await waitFor(() => expect(seen.some((one) => one.path === APPOINTMENT_PATH)).toBe(true));
    const elsewhere = seen.filter((one) => one.path !== TRIAL_PATH).map((one) => JSON.stringify(one.body));
    expect(elsewhere.join("\n")).not.toContain(CLIENT_SECRET);
    expect(elsewhere.join("\n")).not.toContain(read["verifier"]);
  });

  test("a read the server refuses is drawn in its words, with no people", async () => {
    // What breaks if this is deleted: a refused read drawn as an empty list, which says the
    // directory names nobody when nobody has read it.
    const refused = {
      trial: { source: "spreadsheet", plan: null, refusals: ["REFUSAL-SENTINEL"], safe_to_apply: false },
      unread: "",
    };
    const { idp } = standIn(() => json(refused));
    const { container } = await openAtTheStaffList(idp);
    give(container, "first-run-staff_source-staff_source", "spreadsheet");
    const input = container.querySelector("#first-run-staff-list-sheet") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File([SHEET_TEXT], "staff.csv")] } });
    await waitFor(() =>
      expect(
        [...container.querySelectorAll("button")].find((one) => one.textContent === READ_THE_SHEET)?.disabled,
      ).toBe(false),
    );
    press(container, READ_THE_SHEET);

    await waitFor(() => expect(container.textContent).toContain("REFUSAL-SENTINEL"));
    expect(container.textContent).toContain(NOT_READ_TITLE);
    expect(container.textContent).not.toContain(WOULD_ADD_TITLE);
  });
});

describe("the page a directory sends the person back to", () => {
  test("it hands the vendor's answer to the tab that opened it, at this origin only, and closes", async () => {
    // What breaks if this is deleted: the return half of the sign-in. A page that posted to "*"
    // would hand the code to whatever document the opener had navigated to, and one that did not
    // close would leave the person looking at a window with nothing to do in it.
    const posted = vi.fn();
    const closed = vi.fn();
    const loaded = await loadConsole({ path: `${RETURN_PATH}?code=THE-CODE&state=THE-STATE` });
    expect(loaded).toBeDefined();
    vi.stubGlobal("opener", { postMessage: posted });
    vi.stubGlobal("close", closed);
    const { routes } = await import("../src/App");
    const router = createMemoryRouter(routes, {
      initialEntries: [`${RETURN_PATH}?code=THE-CODE&state=THE-STATE`],
    });
    const { container } = render(<RouterProvider router={router} />);

    await waitFor(() => expect(posted).toHaveBeenCalledTimes(1));
    expect(headingOf(container)).toBe(SIGNED_IN_TITLE);
    expect(posted).toHaveBeenCalledWith(
      { kind: SIGNED_IN_KIND, state: "THE-STATE", code: "THE-CODE", error: "" },
      CONSOLE_ORIGIN,
    );
    expect(closed).toHaveBeenCalledTimes(1);
  });
});
