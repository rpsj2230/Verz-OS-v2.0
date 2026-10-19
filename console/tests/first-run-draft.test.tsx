/**
 * First run is a stepped wizard whose draft survives leaving the page: each finished screen is kept
 * on the server behind the setup code, and coming back with the code puts the person at the first
 * screen they had not finished, with what they typed still in the boxes.
 *
 * **The draft is the server's and the secret never goes with it.** `brain.setup_routes` keeps a draft
 * (M42.5.12) and drops a credential on the way in; this holds the other half, that the console does not
 * send a provider key to the draft route in the first place, so a key typed on the provider screen goes
 * only where the appointment sends it, at the end. The stand-in API here keeps what it is sent exactly
 * as the real one would, behind the same code, so the resume is read back from what left the browser.
 *
 * **Per person is per setup code.** A first-run install has one administrator being appointed and one
 * code; a draft is read only for the code that was presented, and a different code is told nothing.
 *
 * Task ids: M27.15.68, M42.5.12
 */

import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, test } from "vitest";
import { DRAFT_PATH, DRAFT_READ_PATH, FIRST_RUN_PATH, SCREENS } from "../src/setup/wizard";
import { CONSOLE_ORIGIN, fakeIdentityProvider, loadConsole, signIn } from "./support/auth";

const CODE = `CODE-SENTINEL-${"c".repeat(50)}`;
const OTHER_CODE = `OTHER-SENTINEL-${"o".repeat(50)}`;
const KEY = "sk-KEY-SENTINEL-9a1c";
const COMPANY = "COMPANY-DRAFT-SENTINEL";
const WEB = "https://brain.example.invalid";

interface Posted {
  readonly path: string;
  readonly body: Record<string, unknown>;
}

function json(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), { status, headers: { "content-type": "application/json" } });
}

/** A stand-in for the two draft routes: keeps what was posted for a code, and answers a read for that code. */
function standIn() {
  const posted: Posted[] = [];
  let kept: { code: string; answers: Record<string, Record<string, string>>; skipped: string[] } | null = null;
  const idp = fakeIdentityProvider({
    api(url, init) {
      const path = new URL(url, CONSOLE_ORIGIN).pathname;
      const body = init?.body === undefined ? {} : (JSON.parse(String(init.body)) as Record<string, unknown>);
      if (path === DRAFT_PATH) {
        posted.push({ path, body });
        kept = {
          code: String(body["setup_code"]),
          answers: body["answers"] as Record<string, Record<string, string>>,
          skipped: body["skipped"] as string[],
        };
        return json({ kept: Object.keys(kept.answers) });
      }
      if (path === DRAFT_READ_PATH) {
        posted.push({ path, body });
        if (kept === null || kept.code !== body["setup_code"]) {
          return json({ answers: {}, skipped: [], next_step: null });
        }
        // The screen after the last one kept: the wizard's own order.
        const last = Math.max(...Object.keys(kept.answers).map((key) => SCREENS.findIndex((one) => one.key === key)));
        return json({ answers: kept.answers, skipped: kept.skipped, next_step: SCREENS[last + 1]?.key ?? null });
      }
      if (path === "/api/v1/me") {
        return json({ principal_id: "u_first", display_name: "First", assurance: "strong", channel: "web", ent_hash: "f".repeat(64), withheld_verbs: [], second_factor_needed: false });
      }
      return null;
    },
  });
  return { idp, posted };
}

function headingOf(container: HTMLElement): string {
  return container.querySelector("h1")?.textContent ?? "";
}

async function arriveAt(container: HTMLElement, title: string): Promise<void> {
  await waitFor(() => expect(headingOf(container)).toBe(title));
}

function give(container: HTMLElement, step: string, name: string, value: string): void {
  const found = container.querySelector(`#first-run-${step}-${name}`);
  if (found === null) {
    throw new Error(`No control for ${step}.${name} on "${headingOf(container)}".`);
  }
  fireEvent.change(found, { target: { value } });
}

function press(container: HTMLElement, text: string): void {
  const button = [...container.querySelectorAll("button")].find((one) => one.textContent === text);
  if (button === undefined) {
    throw new Error(`No button "${text}" on "${headingOf(container)}".`);
  }
  if (button.type === "submit" && button.form !== null) {
    fireEvent.submit(button.form);
    return;
  }
  fireEvent.click(button);
}

async function mountFirstRun(idp: ReturnType<typeof fakeIdentityProvider>, again = false) {
  if (!again) {
    const loaded = await loadConsole({ idp, path: FIRST_RUN_PATH });
    await signIn(loaded, { returnTo: FIRST_RUN_PATH });
  }
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [FIRST_RUN_PATH] });
  const { container } = render(<RouterProvider router={router} />);
  await arriveAt(container, "Enter the setup code");
  return container;
}

beforeAll(async () => {
  await import("../src/App");
}, 60_000);

afterEach(() => {
  cleanup();
});

describe("first run keeps its place", () => {
  test("every finished screen is kept, and coming back with the code resumes at the next one with the answers in place", async () => {
    // What breaks if this is deleted: the owner's ask, that the first run of a new install is a
    // wizard whose draft survives leaving the page. Closing the tab half way would send the person
    // back to the first question.
    const { idp, posted } = standIn();
    const first = await mountFirstRun(idp);
    give(first, "setup_code", "setup_code", CODE);
    press(first, "Continue");
    await arriveAt(first, "Your company");
    give(first, "company", "company_name", COMPANY);
    give(first, "company", "web_address", WEB);
    press(first, "Continue");
    await arriveAt(first, "The first administrator");
    await waitFor(() => expect(posted.filter((one) => one.path === DRAFT_PATH)).toHaveLength(1));
    const kept = posted.find((one) => one.path === DRAFT_PATH)?.body;
    expect(kept?.["setup_code"]).toBe(CODE);
    expect(kept?.["answers"]).toMatchObject({ company: { company_name: COMPANY, web_address: WEB } });
    // Only the screens finished so far are kept: the administrator screen was seen, not answered.
    expect(Object.keys(kept?.["answers"] as Record<string, unknown>)).toEqual(["company"]);

    // Leave the page entirely, and come back to the same address.
    cleanup();
    const second = await mountFirstRun(idp, true);
    give(second, "setup_code", "setup_code", CODE);
    press(second, "Continue");
    await arriveAt(second, "The first administrator");
    press(second, "Back");
    await arriveAt(second, "Your company");
    expect((second.querySelector("#first-run-company-company_name") as HTMLInputElement).value).toBe(COMPANY);
    expect((second.querySelector("#first-run-company-web_address") as HTMLInputElement).value).toBe(WEB);
  });

  test("a provider key typed on its screen is never sent to the draft route, only a blank where it goes", async () => {
    // What breaks if this is deleted: a credential travelling in a request whose only purpose is to
    // remember the person's place. The server drops it, but the console must not send it: it goes
    // where the appointment sends it, once, at the end.
    const { idp, posted } = standIn();
    const container = await mountFirstRun(idp);
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
    await arriveAt(container, "The data steward");
    give(container, "data_steward", "steward_is_administrator", "yes");
    press(container, "Continue");
    await arriveAt(container, "Your staff list");
    give(container, "staff_source", "staff_source", "spreadsheet");
    press(container, "Continue");
    await arriveAt(container, "How questions are answered");
    give(container, "model_provider", "model_profile", "hosted");
    give(container, "model_provider", "model_provider", "anthropic");
    give(container, "model_provider", "provider_key", KEY);
    press(container, "Continue");
    await arriveAt(container, "Data sources");
    await waitFor(() => expect(posted.filter((one) => one.path === DRAFT_PATH).length).toBeGreaterThanOrEqual(5));

    const everything = JSON.stringify(posted.filter((one) => one.path === DRAFT_PATH).map((one) => one.body));
    expect(everything).not.toContain(KEY);
    const last = posted.filter((one) => one.path === DRAFT_PATH).at(-1)?.body;
    expect((last?.["answers"] as Record<string, Record<string, string>>)["model_provider"]).toMatchObject({
      model_profile: "hosted",
      model_provider: "anthropic",
      provider_key: "",
    });
  });

  test("a different setup code is told nothing is kept, so the draft is the code holder's alone", async () => {
    // What breaks if this is deleted: a draft handed to anybody who opens the page, which would put
    // one person's company name and administrator in front of another.
    const { idp } = standIn();
    const first = await mountFirstRun(idp);
    give(first, "setup_code", "setup_code", CODE);
    press(first, "Continue");
    await arriveAt(first, "Your company");
    give(first, "company", "company_name", COMPANY);
    give(first, "company", "web_address", WEB);
    press(first, "Continue");
    await arriveAt(first, "The first administrator");

    cleanup();
    const second = await mountFirstRun(idp, true);
    give(second, "setup_code", "setup_code", OTHER_CODE);
    press(second, "Continue");
    await arriveAt(second, "Your company");
    expect((second.querySelector("#first-run-company-company_name") as HTMLInputElement).value).toBe("");
  });

  test("the wizard says which step of how many it is on, so a person who left knows how far they are", async () => {
    // What breaks if this is deleted: a wizard with no sense of place, which is what makes a draft
    // worth coming back to.
    const { idp } = standIn();
    const container = await mountFirstRun(idp);
    expect(container.textContent).toMatch(/Step 1 of \d+/);
    give(container, "setup_code", "setup_code", CODE);
    press(container, "Continue");
    await arriveAt(container, "Your company");
    expect(container.textContent).toMatch(/Step 2 of \d+/);
  });
});
