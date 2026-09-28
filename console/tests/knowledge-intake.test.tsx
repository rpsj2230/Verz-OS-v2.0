/**
 * Adding a web page by its link and many documents at once, on the Knowledge page.
 *
 * The page is mounted against a stand-in API answering the library, the upload options, the link,
 * the queued route and each ticket, and every request the page sends is read back off the stand-in,
 * so what is asserted is what went over the wire. What the routes do with it is
 * `tests/unit/test_knowledge_intake_routes.py`'s, and what the worker does `test_ingest_queue.py`'s.
 *
 * Task ids: M7.1.2, M7.1.5, M22.2.4
 */

import { fireEvent, render, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, test } from "vitest";
import { Knowledge } from "../src/pages/Knowledge";
import {
  BULK_HEADING,
  CHECK_AGAIN,
  LINK_HEADING,
  NO_FILES,
  NOT_SENT_QUEUE_FULL,
  NOT_SENT_TYPE,
} from "../src/pages/KnowledgeIntake";
import {
  LINK_PROBLEMS,
  LINKS_API_PATH,
  QUEUED_API_PATH,
  QUEUED_STATES,
  linkProblems,
  queuedTicketPath,
  readQueued,
} from "../src/pages/knowledgeIntakeQuery";
import { KNOWLEDGE_API_PATH, UPLOAD_OPTIONS_API_PATH, addedSentence } from "../src/pages/knowledgeQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { backendEnumMembers } from "./support/python";

const API = "/api/v1";
const TICKET = "a".repeat(40);
const PAGE_URL = "https://www.example.org/services/pricing?token=abc123";

const OPTIONS = {
  kinds: [
    { value: "sop", label: "SOP" },
    { value: "service_package", label: "Service package" },
  ],
  departments: ["web"],
  personal: false,
  types: [
    { media_type: "text/markdown", extensions: [".md"], max_bytes: 64 },
    { media_type: "application/pdf", extensions: [".pdf"], max_bytes: 1024 },
  ],
  found_by: "text search",
  checked_by: "structural check (not an antivirus)",
};

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

const ADDED = {
  item_id: "upload.tealpage",
  title: "Care plans & pricing",
  kind: "service_package",
  level: "department",
  department: "web",
  passages: 5,
  found_by: "text search",
};

function queuedView(name: string, state: string, said: string) {
  return { ticket: TICKET, name, state, said, item_id: state === "added" ? "upload.x" : null, passages: 0 };
}

function json(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", ...headers } });
}

interface Answers {
  readonly offered?: unknown;
  readonly offeredStatus?: number;
  readonly link?: unknown;
  readonly linkStatus?: number;
  readonly queued?: (count: number) => Response;
  readonly ticket?: unknown;
}

function api(answers: Answers = {}): FakeIdp {
  let queued = 0;
  return fakeIdentityProvider({
    api(url, init) {
      const path = new URL(url, "https://console.test").pathname;
      if (path.endsWith(`${API}${KNOWLEDGE_API_PATH}`)) {
        return json(LIBRARY);
      }
      if (path.endsWith(`${API}${UPLOAD_OPTIONS_API_PATH}`)) {
        return json(answers.offered ?? OPTIONS, answers.offeredStatus ?? 200);
      }
      if (path.endsWith(`${API}${LINKS_API_PATH}`) && init?.method === "POST") {
        return json(answers.link ?? ADDED, answers.linkStatus ?? 201);
      }
      if (path.endsWith(`${API}${QUEUED_API_PATH}`) && init?.method === "POST") {
        queued += 1;
        return answers.queued?.(queued) ?? json(queuedView("one.md", "queued", "one.md is queued to be read."), 202);
      }
      if (path.endsWith(`${API}${queuedTicketPath(TICKET)}`)) {
        return json(answers.ticket ?? queuedView("one.md", "added", "one.md was added."));
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
    if (text.includes("Loading.") || text.includes("Asking what you may add.")) {
      throw new Error("the page has no answer yet");
    }
  });
  return container;
}

function form(container: HTMLElement, label: string): HTMLFormElement {
  const found = container.querySelector(`form[aria-label="${label}"]`);
  if (!found) {
    throw new Error(`the ${label} form is not drawn`);
  }
  return found as HTMLFormElement;
}

function choose(scope: HTMLElement, name: string, value: string): void {
  const select = scope.querySelector(`select[name="${name}"]`) as HTMLSelectElement;
  fireEvent.change(select, { target: { value } });
}

function posts(idp: FakeIdp, path: string): { url: URL; init: RequestInit }[] {
  return idp.calls
    .filter((call) => call.init?.method === "POST" && new URL(call.url, "https://console.test").pathname === `${API}${path}`)
    .map((call) => ({ url: new URL(call.url, "https://console.test"), init: call.init as RequestInit }));
}

function header(init: RequestInit, name: string): string | undefined {
  return (init.headers as Record<string, string>)[name];
}

describe("adding a web page by its link", () => {
  test("the address travels in the body, never the address bar, and the answer is the API's sentence", async () => {
    // What breaks if this is deleted: the page can put the link, and the token a share link carries,
    // into the query string every access log keeps, or send a kind the API never offered.
    const idp = api();
    const container = await mount(idp);
    const link = form(container, LINK_HEADING);

    fireEvent.change(link.querySelector('input[name="url"]') as HTMLInputElement, { target: { value: PAGE_URL } });
    choose(link, "kind", "service_package");
    fireEvent.submit(link);

    await waitFor(() => expect(posts(idp, LINKS_API_PATH)).toHaveLength(1));
    const [sent] = posts(idp, LINKS_API_PATH);
    expect(sent?.url.search).toBe("");
    expect(JSON.parse(String(sent?.init.body))).toEqual({
      url: PAGE_URL,
      kind: "service_package",
      level: "department",
      department: "web",
    });
    await waitFor(() =>
      expect(container.textContent).toContain(
        addedSentence({
          itemId: ADDED.item_id,
          title: ADDED.title,
          kind: "service_package",
          level: "department",
          department: "web",
          passages: 5,
          foundBy: "text search",
        }),
      ),
    );
  });

  test("a blank or non-https address says what to fill in and sends nothing", async () => {
    // What breaks if this is deleted: an empty link is sent and refused by the API, or a plain http
    // address is sent to be refused after the administrator has waited for it.
    const idp = api();
    const container = await mount(idp);
    const link = form(container, LINK_HEADING);

    fireEvent.submit(link);
    expect(container.textContent).toContain(LINK_PROBLEMS.url);
    expect(container.textContent).toContain(LINK_PROBLEMS.kind);

    fireEvent.change(link.querySelector('input[name="url"]') as HTMLInputElement, {
      target: { value: "http://www.example.org/" },
    });
    choose(link, "kind", "sop");
    fireEvent.submit(link);
    expect(container.textContent).toContain(LINK_PROBLEMS.url);
    expect(posts(idp, LINKS_API_PATH)).toEqual([]);
  });

  test("a refusal is the API's own sentence, a page that needs a browser included", async () => {
    // What breaks if this is deleted: a generic failure is drawn over the reason, and the administrator
    // pastes the same single-page application's link again.
    const reason =
      "pricing could not be read: the page holds no words until a browser runs its scripts, and a link is read as it arrives.";
    const container = await mount(
      api({
        link: { message: reason, trace_id: "trace-link-1", problems: [{ field: "url", code: "scripted_page", message: reason }] },
        linkStatus: 422,
      }),
    );
    const link = form(container, LINK_HEADING);
    fireEvent.change(link.querySelector('input[name="url"]') as HTMLInputElement, { target: { value: PAGE_URL } });
    choose(link, "kind", "sop");
    fireEvent.submit(link);

    await waitFor(() => expect(container.textContent).toContain(reason));
    expect(container.textContent).toContain("trace-link-1");
  });

  test("somebody the API offers nothing to is shown neither card", async () => {
    // What breaks if this is deleted: a reader is shown two forms every press of which is refused.
    const container = await mount(api({ offered: { message: "I could not find that." }, offeredStatus: 404 }));

    expect(container.querySelector(`form[aria-label="${LINK_HEADING}"]`)).toBeNull();
    expect(container.querySelector(`form[aria-label="${BULK_HEADING}"]`)).toBeNull();
  });
});

describe("adding many documents at once", () => {
  test("each file is sent raw to the queue with its name in a header, and the outcome is asked of its ticket", async () => {
    // What breaks if this is deleted: the files can be sent as one JSON body the door cannot measure
    // as it arrives, a file of a type the API refuses is uploaded to be refused, or what the worker
    // decided is never shown to the person who sent it.
    const idp = api();
    const container = await mount(idp);
    const bulk = form(container, BULK_HEADING);
    const files = [new File(["# One"], "one.md"), new File(["a,b"], "rows.csv")];
    fireEvent.change(bulk.querySelector('input[name="files"]') as HTMLInputElement, { target: { files } });
    choose(bulk, "kind", "sop");
    fireEvent.submit(bulk);

    await waitFor(() => expect(container.textContent).toContain(`rows.csv: ${NOT_SENT_TYPE}`));
    const sent = posts(idp, QUEUED_API_PATH);
    expect(sent).toHaveLength(1);
    expect(Object.fromEntries(sent[0]?.url.searchParams ?? [])).toEqual({ kind: "sop", level: "department", department: "web" });
    expect(sent[0] === undefined ? "" : header(sent[0].init, "x-upload-name")).toBe("one.md");
    expect(sent[0]?.init.body).toBe(files[0]);
    expect(container.textContent).toContain("one.md is queued to be read.");

    fireEvent.click([...container.querySelectorAll("button")].find((one) => one.textContent === CHECK_AGAIN) as HTMLButtonElement);
    await waitFor(() => expect(container.textContent).toContain("one.md was added."));
  });

  test("a full queue stops the rest being sent and says so for each of them", async () => {
    // What breaks if this is deleted: every remaining file is sent into a queue that has said it is
    // full, each refused in turn, and the person cannot tell which were never tried.
    const busy = {
      message: "ingestion is busy; this upload was not accepted and needs sending again",
      problems: [{ field: "file", code: "queue_full", message: "ingestion is busy" }],
    };
    const idp = api({ queued: () => json(busy, 429, { "retry-after": "60" }) });
    const container = await mount(idp);
    const bulk = form(container, BULK_HEADING);
    const files = [new File(["# One"], "one.md"), new File(["# Two"], "two.md")];
    fireEvent.change(bulk.querySelector('input[name="files"]') as HTMLInputElement, { target: { files } });
    choose(bulk, "kind", "sop");
    fireEvent.submit(bulk);

    await waitFor(() => expect(container.textContent).toContain(`two.md: ${NOT_SENT_QUEUE_FULL}`));
    expect(posts(idp, QUEUED_API_PATH)).toHaveLength(1);
    expect(container.textContent).toContain("one.md: ingestion is busy");
  });

  test("a bulk form sent with nothing chosen says what to fill in and sends nothing", async () => {
    // What breaks if this is deleted: an empty selection is submitted and the page says nothing.
    const idp = api();
    const container = await mount(idp);
    fireEvent.submit(form(container, BULK_HEADING));

    expect(container.textContent).toContain(NO_FILES);
    expect(posts(idp, QUEUED_API_PATH)).toEqual([]);
  });
});

describe("the intake helpers", () => {
  test("the three queued states are exactly the ones the Python ticket names", () => {
    // What breaks if this is deleted: a state added to brain.knowledge.ingest_queue.TicketState is
    // read as no answer at all, and the file's line never moves on from queued.
    const members = backendEnumMembers("src/brain/knowledge/ingest_queue.py", "TicketState");

    expect([...QUEUED_STATES].sort()).toEqual(Object.values(members).sort());
    expect(readQueued({ ...queuedView("x", "added", "x was added."), state: "lost" })).toBeNull();
    expect(readQueued(queuedView("x", "not_added", "x was not added: it is a scan."))?.state).toBe("not_added");
  });

  test("a link is judged only for being blank or not https, and a ticket is encoded into its address", () => {
    // What breaks if this is deleted: the page starts judging which addresses are safe, which is a
    // second copy of the API's address rule, or a ticket with a slash addresses another route.
    expect(linkProblems({ url: "https://intranet/", kind: "sop", level: "department", department: "web" })).toEqual([]);
    expect(linkProblems({ url: " ", kind: "", level: "department", department: "" })).toEqual(["url", "kind", "department"]);
    expect(queuedTicketPath("../x")).toBe(`${QUEUED_API_PATH}/..%2Fx`);
  });
});
