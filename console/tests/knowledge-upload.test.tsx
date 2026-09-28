/**
 * Adding a document on the Knowledge page: the form is drawn from what the API offers, a draft is
 * judged before it is sent, the file goes raw with its name in a header, and the answer is the
 * API's own sentence.
 *
 * The page is mounted against a stand-in API that answers the library, the upload options and
 * the upload itself, and every request the page sends is read back off the stand-in, so what the
 * test asserts is what went over the wire. What the route does with it is
 * `tests/unit/test_knowledge_routes.py`'s, and what the store does `test_knowledge_upload_db.py`'s.
 *
 * Task ids: M7.6.3, M7.6.1, M7.2.5
 */

import { fireEvent, render, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, test } from "vitest";
import {
  ADD_HEADING,
  ADD_LABEL,
  ADD_NOT_OFFERED,
  ADD_PROBLEMS,
  Knowledge,
} from "../src/pages/Knowledge";
import {
  KIND_NOT_RECORDED,
  KIND_WORDS,
  KNOWLEDGE_API_PATH,
  UPLOAD_OPTIONS_API_PATH,
  UPLOADS_API_PATH,
  addedSentence,
  kindWord,
  readUploadOptions,
  typeOf,
  uploadPath,
} from "../src/pages/knowledgeQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { backendEnumMembers } from "./support/python";

const API = "/api/v1";

const OPTIONS = {
  kinds: [
    { value: "sop", label: "SOP" },
    { value: "pricing_note", label: "Pricing note" },
  ],
  departments: ["web"],
  personal: false,
  types: [
    { media_type: "text/markdown", extensions: [".md", ".markdown"], max_bytes: 64 },
    { media_type: "application/pdf", extensions: [".pdf"], max_bytes: 1024 },
  ],
  found_by: "text search",
  checked_by: "structural check (not an antivirus)",
};

const LIBRARY = {
  items: [
    { item_id: "upload.tealsentinel", level: "department", kind: "sop" },
    { item_id: "doc-old-sentinel", level: "company", kind: null },
  ],
  next_cursor: null,
  total: null,
  truncated: false,
  departments: ["web"],
  staleness: null,
  only_existence_and_reach_are_shown: true,
  freshness_and_use_are_not_measured: true,
};

const ADDED = {
  item_id: "upload.tealsentinel",
  title: "Site handover",
  kind: "sop",
  level: "department",
  department: "web",
  passages: 2,
  found_by: "text search",
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

/** A stand-in API: the library, the options (or a refusal of them), and the upload's answer. */
function api(options: { offered?: unknown; offeredStatus?: number; upload?: unknown; uploadStatus?: number } = {}): FakeIdp {
  return fakeIdentityProvider({
    api(url, init) {
      const path = new URL(url, "https://console.test").pathname;
      if (path.endsWith(`${API}${KNOWLEDGE_API_PATH}`)) {
        return json(LIBRARY);
      }
      if (path.endsWith(`${API}${UPLOAD_OPTIONS_API_PATH}`)) {
        return json(options.offered ?? OPTIONS, options.offeredStatus ?? 200);
      }
      if (path.endsWith(`${API}${UPLOADS_API_PATH}`) && init?.method === "POST") {
        return json(options.upload ?? ADDED, options.uploadStatus ?? 201);
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

function form(container: HTMLElement): HTMLFormElement {
  const found = container.querySelector(`form[aria-label="${ADD_HEADING}"]`);
  if (!found) {
    throw new Error("the Add a document form is not drawn");
  }
  return found as HTMLFormElement;
}

function choose(scope: HTMLElement, name: string, value: string): void {
  const select = scope.querySelector(`select[name="${name}"]`) as HTMLSelectElement | null;
  if (!select) {
    throw new Error(`no ${name} select`);
  }
  fireEvent.change(select, { target: { value } });
}

function attach(scope: HTMLElement, file: File): void {
  const input = scope.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [file] } });
}

function posts(idp: FakeIdp): { url: URL; init: RequestInit }[] {
  return idp.calls
    .filter((call) => call.init?.method === "POST" && new URL(call.url, "https://console.test").pathname.startsWith("/api/"))
    .map((call) => ({ url: new URL(call.url, "https://console.test"), init: call.init as RequestInit }));
}

function header(init: RequestInit, name: string): string | undefined {
  return (init.headers as Record<string, string>)[name];
}

const MARKDOWN = new File(["# Site handover\n\nSign the TEALCHECK list."], "Site handover.md", { type: "" });

describe("adding a document on the Knowledge page", () => {
  test("the form offers the kinds and departments the API sent, and the file goes raw with its name in a header", async () => {
    // What breaks if this is deleted: the page can send the file as JSON, put its name in the URL
    // where every access log keeps it, or send a kind or a department the API never offered.
    const idp = api();
    const container = await mount(idp);
    const added = form(container);

    expect([...added.querySelectorAll('select[name="kind"] option')].map((one) => one.textContent)).toEqual([
      "Choose one",
      "SOP",
      "Pricing note",
    ]);
    attach(added, MARKDOWN);
    choose(added, "kind", "sop");
    fireEvent.submit(added);

    await waitFor(() => expect(posts(idp)).toHaveLength(1));
    const [sent] = posts(idp);
    expect(sent?.url.pathname).toBe(`${API}${UPLOADS_API_PATH}`);
    expect(Object.fromEntries(sent?.url.searchParams ?? [])).toEqual({ kind: "sop", level: "department", department: "web" });
    expect(sent?.url.search).not.toContain("handover");
    expect(sent === undefined ? "" : header(sent.init, "content-type")).toBe("text/markdown");
    expect(sent === undefined ? "" : header(sent.init, "x-upload-name")).toBe(encodeURIComponent("Site handover.md"));
    expect(sent?.init.body).toBe(MARKDOWN);
    await waitFor(() =>
      expect(container.textContent).toContain(
        addedSentence({ itemId: ADDED.item_id, title: ADDED.title, kind: "sop", level: "department", department: "web", passages: 2, foundBy: "text search" }),
      ),
    );
  });

  test("a draft with nothing chosen says what to fill in and sends nothing", async () => {
    // What breaks if this is deleted: an empty form is sent, and the uploader reads the API's
    // refusal of a file they never chose.
    const idp = api();
    const container = await mount(idp);
    const added = form(container);
    fireEvent.submit(added);

    expect(container.textContent).toContain(ADD_PROBLEMS.file);
    expect(container.textContent).toContain(ADD_PROBLEMS.kind);
    expect(posts(idp)).toEqual([]);
  });

  test("a file of a type or size the API would refuse is said before anything is sent", async () => {
    // What breaks if this is deleted: a spreadsheet or a file over the ceiling is uploaded whole to
    // be refused, on a connection that may be slow.
    const idp = api();
    const container = await mount(idp);
    const added = form(container);
    choose(added, "kind", "sop");

    attach(added, new File(["a,b"], "rows.csv"));
    fireEvent.submit(added);
    expect(container.textContent).toContain(ADD_PROBLEMS.type);

    attach(added, new File(["x".repeat(65)], "large.md"));
    fireEvent.submit(added);
    expect(container.textContent).toContain(ADD_PROBLEMS.size);
    expect(posts(idp)).toEqual([]);
  });

  test("a refusal is the API's own sentence, a parse failure's cause included", async () => {
    // What breaks if this is deleted: the page draws a generic failure over the reason the API gave,
    // and the uploader sends the same locked file again (M7.2.5).
    const reason = "handover.pdf could not be read: the file is password-protected, so nothing could be read from it.";
    const idp = api({
      upload: { message: reason, trace_id: "trace-upload-1", problems: [{ field: "file", code: "encrypted", message: reason }] },
      uploadStatus: 422,
    });
    const container = await mount(idp);
    const added = form(container);
    attach(added, new File(["%PDF-1.4"], "handover.pdf"));
    choose(added, "kind", "sop");
    fireEvent.submit(added);

    await waitFor(() => expect(container.textContent).toContain(reason));
    expect(container.textContent).toContain("trace-upload-1");
  });

  test("somebody the API offers nothing to is told so in one sentence and shown no form", async () => {
    // What breaks if this is deleted: a reader is shown a form every press of which is refused, or
    // a failure notice for what is the ordinary answer to somebody who may add nothing.
    const container = await mount(api({ offered: { message: "I could not find that." }, offeredStatus: 404 }));

    expect(container.textContent).toContain(ADD_NOT_OFFERED);
    expect(container.querySelector(`form[aria-label="${ADD_HEADING}"]`)).toBeNull();
    expect(container.textContent).not.toContain(ADD_LABEL);
  });

  test("each library row says its kind, and a row with none says it was not recorded", async () => {
    // What breaks if this is deleted: the Type column can be drawn blank for an old item, which
    // reads as a document nobody classified rather than one added before kinds existed (M7.6.1).
    const container = await mount(api());
    const rows = [...container.querySelectorAll("tbody tr")].map((row) =>
      [...row.querySelectorAll("td")].map((cell) => cell.textContent),
    );

    expect(rows).toContainEqual(["upload.tealsentinel", "SOP", "department"]);
    expect(rows).toContainEqual(["doc-old-sentinel", KIND_NOT_RECORDED, "company"]);
  });
});

describe("the knowledge query helpers", () => {
  test("the console's kind words are keyed by exactly the kinds the Python enum stores", () => {
    // What breaks if this is deleted: a kind added in brain.knowledge.kinds is drawn in the library
    // as its stored word, or one renamed there keeps a label nothing sends.
    const members = backendEnumMembers("src/brain/knowledge/kinds.py", "KnowledgeKind");

    expect(Object.keys(KIND_WORDS).sort()).toEqual(Object.values(members).sort());
    expect(kindWord("pricing_note")).toBe("Pricing note");
    expect(kindWord(null)).toBe(KIND_NOT_RECORDED);
  });

  test("a type is chosen by extension, an unreadable options body draws no form, and the address carries no name", () => {
    // What breaks if this is deleted: a Markdown file, which most browsers send with no type, is
    // refused as untyped; or a body with no kinds draws a form nobody can submit.
    const options = readUploadOptions(OPTIONS);

    expect(options === null ? null : typeOf("Notes.MD", options.types)?.mediaType).toBe("text/markdown");
    expect(options === null ? "x" : typeOf("rows.csv", options.types)).toBeNull();
    expect(readUploadOptions({ ...OPTIONS, kinds: [] })).toBeNull();
    expect(readUploadOptions("not options")).toBeNull();
    expect(uploadPath("sop", "personal", "web")).toBe(`${UPLOADS_API_PATH}?kind=sop&level=personal&department=`);
  });
});
