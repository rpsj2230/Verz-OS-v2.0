/**
 * The matrix gate on the Routing screen: a held save shows its failing cases, the golden questions
 * are listed, and a rung is added only through a confirmation.
 *
 * Driven through the real route table with a stand-in API, as the matrix page's own tests are.
 *
 * Task ids: M5.6.2, M5.7.2
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  ADD_GOLDEN,
  ADD_RUNG,
  ADD_RUNG_HEADING,
  CHOOSE_A_PERSON,
  GOLDEN_COUNTS_WHEN,
  GOLDEN_HEADING,
  HELD,
  NO_GOLDEN,
  STEPS_TO_PASS,
  caseReasonWords,
  heldWhy,
} from "../src/pages/matrixGateQuery";
import { SAVE_RUNG } from "../src/pages/Matrix";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";

const RUNG_ID = "11111111-1111-4111-8111-111111111111";

beforeAll(async () => {
  await import("../src/pages/Matrix");
}, 60_000);

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

const MATRIX = {
  items: [
    {
      id: RUNG_ID,
      tier: "main",
      position: 0,
      role: "primary",
      scope: {},
      deployment_id: "anthropic-sonnet-global",
      provider: "anthropic",
      model: "claude-sonnet-5",
      attempts: 1,
      timeout_seconds: 12,
      max_concurrency: 40,
      enabled: true,
    },
  ],
  next_cursor: null,
  total: null,
  truncated: false,
  editable: true,
};

const HELD_CHANGE = {
  id: "22222222-2222-4222-8222-222222222222",
  kind: "edit",
  status: "held",
  rung_id: RUNG_ID,
  proposed: {},
  failing: [{ case: "q-leave", reason: "did not answer: absent" }],
  reasons: ["quality is 0.000 against a floor of 0.900"],
  quality_share: 0,
  proposed_by: "u_admin",
  decided_at: "2019-03-04T09:00:00Z",
  rung: null,
};

const PEOPLE = {
  items: [
    { id: "u_nadia", name: "Nadia Tan" },
    { id: "u_omar", name: "Omar Lee" },
  ],
  truncated: false,
};

async function routingAt(path: string, golden: unknown[] = []): Promise<{ container: HTMLElement; idp: FakeIdp }> {
  const idp = fakeIdentityProvider({
    api(url, init) {
      const method = init?.method ?? "GET";
      if (url.includes("/api/v1/routing/changes")) {
        return json({ items: [] });
      }
      if (url.includes("/api/v1/routing/golden-questions/askers")) {
        return json(PEOPLE);
      }
      if (url.includes("/api/v1/routing/golden-questions") && method === "POST") {
        return json({ items: golden });
      }
      if (url.includes("/api/v1/routing/golden-questions")) {
        return json({ items: golden });
      }
      if (url.includes(`/api/v1/routing/rungs/${RUNG_ID}`) && method === "PATCH") {
        return json(HELD_CHANGE);
      }
      if (url.includes("/api/v1/routing/rungs") && method === "POST") {
        return json({ ...HELD_CHANGE, kind: "add", rung_id: null });
      }
      if (url.includes("/api/v1/routing/rungs")) {
        return json(MATRIX);
      }
      return null;
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (!container.textContent?.includes(GOLDEN_HEADING) || container.querySelector(".grid__busy")) {
      throw new Error("the gate has no answer yet");
    }
  });
  return { container, idp };
}

function writes(idp: FakeIdp): { url: string; method: string; body: unknown }[] {
  return idp.calls
    .filter((call) => String(call.url).includes("/api/v1/") && (call.init?.method ?? "GET") !== "GET")
    .map((call) => ({
      url: String(call.url),
      method: call.init?.method ?? "GET",
      body: typeof call.init?.body === "string" ? (JSON.parse(call.init.body) as unknown) : null,
    }));
}

function button(container: HTMLElement, text: string): HTMLElement {
  const found = [...container.querySelectorAll("button")].find((one) => one.textContent === text);
  if (found === undefined) {
    throw new Error(`no button reads ${text}`);
  }
  return found;
}

describe("the matrix gate on the Routing screen", () => {
  test("a save the gate held is shown held with its failing case and reason, and never as saved", async () => {
    // What breaks if this is deleted: a held change reads to a person as a saved one, because the
    // screen refreshes either way, and the rung that kept its old numbers looks as if it moved.
    const { container, idp } = await routingAt(`/routing/${RUNG_ID}`);
    fireEvent.click(container.querySelector(".form button[type=submit]") as HTMLElement);
    await waitFor(() => {
      button(container, SAVE_RUNG);
    });
    fireEvent.click(button(container, SAVE_RUNG));
    await waitFor(() => {
      if (!container.querySelector('[aria-label="The change was held"]')) {
        throw new Error("the held change is not drawn");
      }
    });

    const held = container.querySelector('[aria-label="The change was held"]');
    expect(held?.textContent).toContain(HELD);
    expect(held?.textContent).toContain("q-leave");
    expect(held?.textContent).toContain("did not answer: absent");
    expect(writes(idp).map((one) => one.method)).toEqual(["PATCH"]);
  });

  test("with no golden question the screen says every change is held until some are", async () => {
    // What breaks if this is deleted: an install with no golden questions has every save held and
    // nothing on the screen saying why or what to do.
    const { container } = await routingAt("/routing");

    expect(container.textContent).toContain(NO_GOLDEN);
  });

  test("a rung is added only from its confirmation, as one POST naming the tier, provider and model", async () => {
    // What breaks if this is deleted: the add form's submit posts directly, and a rung reaches the
    // gate, and possibly the chain, from one press nobody confirmed.
    const { container, idp } = await routingAt("/routing");
    const form = container.querySelector(`form[aria-label="${ADD_RUNG_HEADING}"]`) as HTMLFormElement;
    fireEvent.change(form.querySelector('input[name="provider"]') as HTMLElement, { target: { value: "deepseek" } });
    fireEvent.change(form.querySelector('input[name="model"]') as HTMLElement, { target: { value: "deepseek-chat" } });
    fireEvent.submit(form);
    expect(writes(idp)).toEqual([]);

    // The confirmation is drawn in the gate's card above the forms, so its button is the first of
    // the two that read the same; the second is the form's own submit, which asked it.
    const confirm = [...container.querySelectorAll("button")].filter((one) => one.textContent === ADD_RUNG);
    expect(confirm).toHaveLength(2);
    fireEvent.click(confirm[0] as HTMLElement);
    await waitFor(() => {
      if (writes(idp).length === 0) {
        throw new Error("nothing sent");
      }
    });

    const [sent] = writes(idp);
    expect(sent?.method).toBe("POST");
    expect(sent?.body).toEqual({
      tier: "main",
      provider: "deepseek",
      model: "deepseek-chat",
      attempts: 1,
      timeout_seconds: 20,
      max_concurrency: 4,
    });
  });

  test("a change held with no golden questions says why and the steps to get one through, where it was saved", async () => {
    // What breaks if this is deleted: a new install saves a change, sees Held and a sentence about
    // a floor, and has nothing on the screen saying that a document and a golden question asked as
    // a person who can read it are what every change waits on, which is where the owner was.
    const { container } = await routingAt(`/routing/${RUNG_ID}`);
    fireEvent.click(container.querySelector(".form button[type=submit]") as HTMLElement);
    await waitFor(() => {
      button(container, SAVE_RUNG);
    });
    fireEvent.click(button(container, SAVE_RUNG));
    await waitFor(() => {
      if (!container.querySelector('[aria-label="The change was held"]')) {
        throw new Error("the held change is not drawn");
      }
    });

    const held = container.querySelector('[aria-label="The change was held"]');
    const words = held?.textContent ?? "";
    expect(words).toContain(GOLDEN_COUNTS_WHEN);
    for (const step of STEPS_TO_PASS) {
      expect(words).toContain(step);
    }
    expect(held?.querySelector('a[href="/library"]')).not.toBeNull();
    // The API's case ids and reasons are kept, under Details, and said in plain words above it.
    expect(words).toContain(caseReasonWords("did not answer: absent"));
  });

  test("why a change was held is the permission check, the golden question, or there being none, in that order", () => {
    // What breaks if this is deleted: a held change blames the golden questions when a permission
    // check found a leak, or says there are none when one exists and was not answered.
    const base = { id: "c", kind: "edit", status: "held", rung_id: null, reasons: [], quality_share: null, proposed_by: "u", decided_at: "" } as const;
    expect(heldWhy({ ...base, failing: [{ case: "canary-1", reason: "x" }, { case: "q", reason: "did not answer: x" }] }, 1)).toContain("permission check");
    expect(heldWhy({ ...base, failing: [{ case: "q", reason: "answered a question it must refuse" }] }, 1)).toContain("must be refused");
    expect(heldWhy({ ...base, failing: [{ case: "q", reason: "did not answer: nothing retrieved" }] }, 1)).toContain("was not answered");
    expect(heldWhy({ ...base, failing: [] }, 0)).toContain("no golden questions yet");
    // A withheld record and an absent one are one sentence, never two.
    expect(caseReasonWords("did not answer: not entitled")).toBe(caseReasonWords("did not answer: nothing retrieved"));
  });

  test("a golden question is asked as a person chosen by name, and the id the API stores is what is sent", async () => {
    // What breaks if this is deleted: the form goes back to asking for a principal id, which no
    // owner knows, so the golden question every change waits on is never recorded.
    const { container, idp } = await routingAt("/routing");
    const form = container.querySelector('form[aria-label="Add a golden question"]') as HTMLFormElement;
    await waitFor(() => {
      if (form.querySelectorAll('select[name="asked_as"] option').length < 3) {
        throw new Error("the people have not arrived");
      }
    });
    const options = [...form.querySelectorAll('select[name="asked_as"] option')].map((one) => one.textContent);
    expect(options).toEqual([CHOOSE_A_PERSON, "Nadia Tan", "Omar Lee"]);
    expect(form.querySelector('input[name="asked_as"]')).toBeNull();

    fireEvent.change(form.querySelector('input[name="question"]') as HTMLElement, { target: { value: "How many days of leave do I have?" } });
    fireEvent.change(form.querySelector('select[name="asked_as"]') as HTMLElement, { target: { value: "u_nadia" } });
    fireEvent.submit(form);
    expect(container.querySelector(".confirm")?.textContent).toContain("Nadia Tan");
    const confirm = [...container.querySelectorAll(".confirm button")].find((one) => one.textContent === ADD_GOLDEN);
    fireEvent.click(confirm as HTMLElement);
    await waitFor(() => {
      if (writes(idp).length === 0) {
        throw new Error("nothing sent");
      }
    });
    expect(writes(idp)[0]?.body).toEqual({ question: "How many days of leave do I have?", asked_as: "u_nadia", expect: "answer" });
  });

  test("every control on the Routing screen is named by its label and carries a name", async () => {
    // What breaks if this is deleted: the owner's audit on 2026-09-28 again finds the Add form's
    // inputs with no accessible name. Each control is found by its label element, both the label's
    // for attribute and the control's labels list, which is what an assistive tool reads.
    const { container } = await routingAt("/routing");
    // The screen itself, not the shell around it, whose theme switch is another screen's concern.
    const screen = container.querySelector("article.page") as HTMLElement;
    const controls = [...screen.querySelectorAll<HTMLInputElement | HTMLSelectElement>("input, select, textarea")];

    expect(controls.length).toBeGreaterThan(8);
    for (const control of controls) {
      const labels = [...(control.labels ?? [])];
      expect(labels.length, control.outerHTML).toBeGreaterThan(0);
      expect(labels.some((one) => (one.textContent ?? "").trim() !== ""), control.outerHTML).toBe(true);
      expect(control.getAttribute("name"), control.outerHTML).not.toBeNull();
      expect(container.querySelector(`label[for="${control.id}"]`), control.outerHTML).not.toBeNull();
    }
  });

  test("no rung, ladder, tier, lane or slot is drawn on the Routing screen", async () => {
    // What breaks if this is deleted: the owner's plain Routing screen grows internal words again.
    const { container } = await routingAt("/routing", [
      { id: "g-1", question: "How many days of leave do I have?", asked_as: "u_nadia", asked_as_name: "Nadia Tan", expect: "answer", created_by: "u_admin" },
    ]);

    expect(container.textContent).toContain("Nadia Tan");
    expect(container.textContent).not.toMatch(/\b(rungs?|ladders?|tiers?|lanes?|slots?)\b/i);
    expect(container.textContent).not.toMatch(/\b(small|heavy)\b/);
  });
});
