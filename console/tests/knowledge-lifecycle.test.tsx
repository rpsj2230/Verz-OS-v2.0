/**
 * A stored document's life on the Knowledge page: the tasks, the documents looked after with their
 * four acts, and captured solutions, each drawn from what the API answers and each sending one
 * request.
 *
 * The page is mounted against a stand-in API that answers the library, the upload options and the
 * lifecycle routes, and every request the page sends is read back off the stand-in, so what is
 * asserted is what went over the wire. What the routes do with it is
 * `tests/unit/test_knowledge_lifecycle_db.py`'s, against a real database.
 *
 * Task ids: M7.4.4, M7.4.5, M7.4.6, M7.6.2, M7.7.2
 */

import { fireEvent, render, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, test } from "vitest";
import { Knowledge } from "../src/pages/Knowledge";
import {
  CAPTURE_HEADING,
  CAPTURE_NOT_OFFERED,
  DECIDE_HEADING,
  HAND_OVER_CONSEQUENCE,
  HAND_OVER_HEADING,
  LIFECYCLE_PROBLEMS,
  MARK_READ,
  NEW_VERSION_CONSEQUENCE,
  NEW_VERSION_HEADING,
  NEW_VERSION_LABEL,
  PROPOSE_HEADING,
  REFUSE_LABEL,
  VERIFY_HEADING,
  HAND_OVER_LABEL,
} from "../src/components/KnowledgeLifecycle";
import {
  instantOf,
  isAfterToday,
  ITEMS_API_PATH,
  itemPath,
  promotionPath,
  SOLUTIONS_API_PATH,
  solutionDecisionPath,
  stewardPath,
  taskDonePath,
  TASKS_API_PATH,
  verificationPath,
  verificationWords,
  newVersionPath,
} from "../src/pages/knowledgeLifecycleQuery";
import { KNOWLEDGE_API_PATH, UPLOAD_OPTIONS_API_PATH } from "../src/pages/knowledgeQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";

const API = "/api/v1";
const ITEM = "upload.tealsentinel";
const OLDER = "upload.tealolder";
const SOLUTION = "solution.tealfix";

const LIBRARY = {
  items: [],
  next_cursor: null,
  total: null,
  truncated: false,
  departments: ["web"],
  staleness: null,
  only_existence_and_reach_are_shown: true,
  freshness_and_use_are_not_measured: true,
};

const DOCUMENT = {
  item_id: ITEM,
  title: "Site handover",
  kind: "sop",
  kind_label: "SOP",
  level: "department",
  department: "web",
  steward_id: "u_admin",
  state: "published",
  verification: "verified",
  verified_by: null,
  verified_at: null,
  review_by: "2999-01-01T12:00:00+00:00",
  due: false,
  supersedes: OLDER,
  added_at: "2019-03-04T09:00:00+00:00",
  you_steward: true,
  solves: null,
  promotion: { suspension_id: "promotion.x", status: "waiting", expires_at: "2019-03-05T09:00:00+00:00" },
};

const DETAIL = {
  document: DOCUMENT,
  versions: [
    { item_id: OLDER, title: "Site handover", state: "superseded", level: "department", department: "web", added_at: "2019-03-01T09:00:00+00:00", readable: true },
    { item_id: ITEM, title: "Site handover", state: "published", level: "department", department: "web", added_at: "2019-03-04T09:00:00+00:00", readable: true },
  ],
  offered: { verify: true, new_version: true, propose: true, hand_over: true },
  promotion_waits: "Asking puts a card on the Approvals screen.",
};

const TASKS = {
  items: [
    { task_id: "reverification.a", kind: "reverify", item_id: ITEM, says: "Site handover was due for review on 2019-03-01.", opened_at: "2019-03-02T09:00:00+00:00", due_at: "2019-03-01T09:00:00+00:00", closable: false },
    { task_id: "steward.b", kind: "steward_named", item_id: ITEM, says: "You are now the steward of Site handover.", opened_at: "2019-03-02T09:00:00+00:00", due_at: null, closable: true },
  ],
};

const WAITING = {
  solution_id: SOLUTION,
  department: "web",
  problem: "Checkout fails after the plugin update",
  answer: "Clear the object cache.",
  conversation_ref: null,
  captured_by: "u_narrow",
  captured_at: "2019-03-02T09:00:00+00:00",
  state: "pending",
  decided_by: null,
  decided_at: null,
  item_id: null,
};

const SOLUTIONS = { waiting: [WAITING], yours: [], departments: ["web"] };

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

function api(options: { solutions?: unknown } = {}): FakeIdp {
  return fakeIdentityProvider({
    api(url, init) {
      const path = new URL(url, "https://console.test").pathname;
      const method = init?.method ?? "GET";
      if (method === "POST") {
        return json({ ...DOCUMENT }, 200);
      }
      if (path.endsWith(`${API}${KNOWLEDGE_API_PATH}`)) {
        return json(LIBRARY);
      }
      if (path.endsWith(`${API}${UPLOAD_OPTIONS_API_PATH}`)) {
        return json({ message: "I could not find that." }, 404);
      }
      if (path.endsWith(`${API}${TASKS_API_PATH}`)) {
        return json(TASKS);
      }
      if (path.endsWith(`${API}${ITEMS_API_PATH}`)) {
        return json({ items: [DOCUMENT], truncated: false });
      }
      if (path.endsWith(`${API}${itemPath(ITEM)}`)) {
        return json(DETAIL);
      }
      if (path.endsWith(`${API}${SOLUTIONS_API_PATH}`)) {
        return json(options.solutions ?? SOLUTIONS);
      }
      return null;
    },
  });
}

async function mount(idp: FakeIdp): Promise<HTMLElement> {
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { container } = render(
    <MemoryRouter initialEntries={["/library"]}>
      <Routes>
        <Route path="/library" element={<Knowledge />} />
      </Routes>
    </MemoryRouter>,
  );
  await waitFor(() => {
    const text = container.textContent ?? "";
    if (text.includes("Loading.") || text.includes("Asking")) {
      throw new Error("the page has no answer yet");
    }
  });
  return container;
}

function posts(idp: FakeIdp): { url: URL; init: RequestInit }[] {
  return idp.calls
    .filter((call) => call.init?.method === "POST" && new URL(call.url, "https://console.test").pathname.startsWith("/api/"))
    .map((call) => ({ url: new URL(call.url, "https://console.test"), init: call.init as RequestInit }));
}

function bodyOf(init: RequestInit): unknown {
  return JSON.parse(String(init.body));
}

function formNamed(container: HTMLElement, name: string): HTMLFormElement {
  const found = container.querySelector(`form[aria-label="${name}"]`);
  if (!found) {
    throw new Error(`the ${name} form is not drawn`);
  }
  return found as HTMLFormElement;
}

function buttonNamed(scope: HTMLElement, name: string): HTMLButtonElement {
  const found = [...scope.querySelectorAll("button")].find(
    (one) => one.textContent === name || one.getAttribute("aria-label") === name,
  );
  if (!found) {
    throw new Error(`no ${name} button`);
  }
  return found;
}

function setField(scope: HTMLElement, name: string, value: string): void {
  const field = scope.querySelector(`[name="${name}"]`) as HTMLInputElement | HTMLTextAreaElement | null;
  if (!field) {
    throw new Error(`no ${name} field`);
  }
  fireEvent.change(field, { target: { value } });
}

async function opened(idp: FakeIdp): Promise<HTMLElement> {
  const container = await mount(idp);
  fireEvent.click(buttonNamed(container, "Open Site handover"));
  await waitFor(() => formNamed(container, VERIFY_HEADING));
  return container;
}

describe("a stored document's life on the Knowledge page", () => {
  test("the tasks say their sentence, and only a task that reports offers to be marked read", async () => {
    // What breaks if this is deleted: a review task could be dismissed while the document stays
    // overdue, or a task drawn as an id rather than the sentence the API composed (M7.4.6).
    const idp = api();
    const container = await mount(idp);
    const list = container.querySelector('ul[aria-label="Your knowledge tasks"]') as HTMLElement;

    expect(list.textContent).toContain("Site handover was due for review on 2019-03-01.");
    expect(within(list).getAllByText(MARK_READ)).toHaveLength(1);
    fireEvent.click(within(list).getByText(MARK_READ));
    await waitFor(() => expect(posts(idp)).toHaveLength(1));
    expect(posts(idp)[0]?.url.pathname).toBe(`${API}${taskDonePath("steward.b")}`);
  });

  test("an opened document shows its history, and verifying sends the review date as an instant", async () => {
    // What breaks if this is deleted: the older version could vanish from the page once replaced,
    // or a verification be sent with a day the API reads in the wrong timezone (M7.4.5, M7.4.6).
    const idp = api();
    const container = await opened(idp);
    const history = container.querySelector('ul[aria-label="History"]') as HTMLElement;

    expect(history.textContent).toContain("replaced");
    expect(history.textContent).toContain("current");
    const verify = formNamed(container, VERIFY_HEADING);
    setField(verify, "review_by", "2999-02-03");
    fireEvent.submit(verify);
    await waitFor(() => expect(posts(idp)).toHaveLength(1));
    const [sent] = posts(idp);
    expect(sent?.url.pathname).toBe(`${API}${verificationPath(ITEM)}`);
    expect(sent === undefined ? null : bodyOf(sent.init)).toEqual({ review_by: "2999-02-03T12:00:00+00:00" });
  });

  test("a newer version is confirmed first, then sent raw with its review date in the address", async () => {
    // What breaks if this is deleted: a document is replaced by one press, or the file's name is
    // put in the address every access log keeps (M7.4.5).
    const idp = api();
    const container = await opened(idp);
    const form = formNamed(container, NEW_VERSION_HEADING);
    const file = new File(["# Site handover\n\nNew text."], "Site handover v2.md", { type: "" });
    fireEvent.change(form.querySelector('input[type="file"]') as HTMLInputElement, { target: { files: [file] } });
    setField(form, "review_by", "2999-02-03");
    fireEvent.submit(form);

    expect(posts(idp)).toEqual([]);
    expect(container.textContent).toContain(NEW_VERSION_CONSEQUENCE);
    const confirm = container.querySelector('section[role="group"]') as HTMLElement;
    fireEvent.click(buttonNamed(confirm, NEW_VERSION_LABEL));
    await waitFor(() => expect(posts(idp)).toHaveLength(1));
    const [sent] = posts(idp);
    expect(`${sent?.url.pathname}${sent?.url.search}`).toBe(`${API}${newVersionPath(ITEM, "2999-02-03T12:00:00+00:00")}`);
    expect(sent?.url.search).not.toContain("handover");
    expect((sent?.init.headers as Record<string, string>)["x-upload-name"]).toBe(encodeURIComponent("Site handover v2.md"));
    expect(sent?.init.body).toBe(file);
  });

  test("a hand-over names nobody until a person is entered, and is confirmed before it is sent", async () => {
    // What breaks if this is deleted: an empty hand-over is sent, or a steward replaced by one
    // press (M7.7.2).
    const idp = api();
    const container = await opened(idp);
    const form = formNamed(container, HAND_OVER_HEADING);
    fireEvent.submit(form);
    expect(container.textContent).toContain(LIFECYCLE_PROBLEMS.steward);
    expect(container.textContent).not.toContain(HAND_OVER_CONSEQUENCE);

    setField(form, "steward_id", "u_narrow");
    fireEvent.submit(form);
    expect(container.textContent).toContain(HAND_OVER_CONSEQUENCE);
    expect(posts(idp)).toEqual([]);
    fireEvent.click(buttonNamed(container.querySelector('section[role="group"]') as HTMLElement, HAND_OVER_LABEL));
    await waitFor(() => expect(posts(idp)).toHaveLength(1));
    expect(posts(idp)[0]?.url.pathname).toBe(`${API}${stewardPath(ITEM)}`);
    expect(bodyOf(posts(idp)[0]?.init as RequestInit)).toEqual({ steward_id: "u_narrow" });
  });

  test("asking for the whole company says where it goes and sends the reason and the review date", async () => {
    // What breaks if this is deleted: a promotion is asked for with no reason, or the page stops
    // saying it waits on the Approvals screen for somebody else (M7.4.4).
    const idp = api();
    const container = await opened(idp);
    const form = formNamed(container, PROPOSE_HEADING);
    expect(form.textContent).toContain(DETAIL.promotion_waits);
    expect(container.textContent).toContain("waiting on the Approvals screen until 2019-03-05");

    fireEvent.submit(form);
    expect(form.textContent).toContain(LIFECYCLE_PROBLEMS.reason);
    expect(posts(idp)).toEqual([]);
    setField(form, "reason", "every team quotes it");
    setField(form, "review_by", "2999-02-03");
    fireEvent.submit(form);
    await waitFor(() => expect(posts(idp)).toHaveLength(1));
    expect(posts(idp)[0]?.url.pathname).toBe(`${API}${promotionPath(ITEM)}`);
    expect(bodyOf(posts(idp)[0]?.init as RequestInit)).toEqual({
      review_by: "2999-02-03T12:00:00+00:00",
      reason: "every team quotes it",
    });
  });

  test("a solution is captured only once it says what it solved and how, for a department", async () => {
    // What breaks if this is deleted: an empty solution is sent to wait for somebody's approval
    // (M7.6.2).
    const idp = api();
    const container = await mount(idp);
    const form = formNamed(container, CAPTURE_HEADING);
    fireEvent.submit(form);
    expect(form.textContent).toContain(LIFECYCLE_PROBLEMS.problem);
    expect(form.textContent).toContain(LIFECYCLE_PROBLEMS.answer);
    expect(posts(idp)).toEqual([]);

    setField(form, "problem", "Checkout fails");
    setField(form, "answer", "Clear the cache.");
    setField(form, "conversation_ref", "conv.42");
    fireEvent.submit(form);
    await waitFor(() => expect(posts(idp)).toHaveLength(1));
    expect(posts(idp)[0]?.url.pathname).toBe(`${API}${SOLUTIONS_API_PATH}`);
    expect(bodyOf(posts(idp)[0]?.init as RequestInit)).toEqual({
      problem: "Checkout fails",
      answer: "Clear the cache.",
      department: "web",
      conversation_ref: "conv.42",
    });
  });

  test("a waiting solution is approved with its review date or refused, each one request", async () => {
    // What breaks if this is deleted: approving could send no review date, which the API refuses,
    // or refusing send an approval (M7.6.2).
    const idp = api();
    const container = await mount(idp);
    const decide = formNamed(container, DECIDE_HEADING);
    setField(decide, "review_by", "2999-02-03");
    fireEvent.submit(decide);
    await waitFor(() => expect(posts(idp)).toHaveLength(1));
    fireEvent.click(buttonNamed(decide, REFUSE_LABEL));
    await waitFor(() => expect(posts(idp)).toHaveLength(2));

    expect(posts(idp).map((one) => one.url.pathname)).toEqual([
      `${API}${solutionDecisionPath(SOLUTION)}`,
      `${API}${solutionDecisionPath(SOLUTION)}`,
    ]);
    expect(posts(idp).map((one) => bodyOf(one.init))).toEqual([
      { verdict: "approved", review_by: "2999-02-03T12:00:00+00:00" },
      { verdict: "rejected", review_by: null },
    ]);
  });

  test("somebody who may capture nowhere is told so and shown no capture form", async () => {
    // What breaks if this is deleted: a form whose every press is refused as absent.
    const container = await mount(api({ solutions: { waiting: [], yours: [], departments: [] } }));

    expect(container.textContent).toContain(CAPTURE_NOT_OFFERED);
    expect(container.querySelector(`form[aria-label="${CAPTURE_HEADING}"]`)).toBeNull();
  });
});

describe("the lifecycle query helpers", () => {
  test("a picked day is noon UTC that day, and a review day must be after today", () => {
    // What breaks if this is deleted: a review date moves a day with the browser's timezone, or a
    // past date is sent for the API to refuse.
    const today = new Date("2019-03-04T23:30:00Z");

    expect(instantOf("2019-03-05")).toBe("2019-03-05T12:00:00+00:00");
    expect(instantOf("5 March")).toBeNull();
    expect(isAfterToday("2019-03-05", today)).toBe(true);
    expect(isAfterToday("2019-03-04", today)).toBe(false);
  });

  test("a verification names nobody unless the API sent the name", () => {
    // What breaks if this is deleted: the page could fill in a verifier the reader may not be told.
    expect(verificationWords({ verification: "verified" })).toBe("verified");
    expect(verificationWords({ verification: "verified", verified_by: "u_v", verified_at: "2019-03-01T00:00:00Z" })).toBe(
      "verified by u_v on 2019-03-01",
    );
    expect(verificationWords({ verification: "unverified" })).toBe("not verified by anyone");
  });
});
