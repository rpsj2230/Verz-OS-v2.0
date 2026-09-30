/**
 * The Knowledge module on the shared page kit: the list, one document's three views, the forms
 * each act is written in, and Solutions.
 *
 * **Reachable means through the application's own route table.** The pages are mounted from
 * `src/App.tsx`'s routes on a memory router, signed in through the real session modules and answered
 * by a stand-in API, so a test passes only if the address resolves. The forms, which open in drawers
 * outside the page's main landmark, are also rendered on their own and submitted blank here, which is
 * why `tests/validated-before-write.test.tsx` names this file for them.
 *
 * **Names, not identifiers.** A steward and a verifier are drawn by the names the API sent; the
 * principal ids and the document's reference appear only inside Advanced.
 *
 * Task ids: M7.7.3, M7.6.1, M27.15.40, M27.16.1, M7.4.4, M7.4.5, M7.4.6, M7.6.2, M7.6.3, M7.1.2, M7.1.5
 */

import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { createMemoryRouter, MemoryRouter, RouterProvider } from "react-router-dom";
import { beforeAll, describe, expect, test } from "vitest";
import { ADVANCED_LABEL, UNAVAILABLE_MARK } from "../src/components/kit/parts";
import { AddFileForm, AddLinkForm, AddManyForm } from "../src/pages/knowledge/addForms";
import { HandOverForm, NewVersionForm, ProposeForm, VerifyForm } from "../src/pages/knowledge/actForms";
import {
  ADD_IT_ON_CLASSIFICATION,
  ADD_VERSION,
  HAND_OVER,
  HAND_OVER_CONSEQUENCE,
  NEW_VERSION_CONSEQUENCE,
  NOT_SENT_TABLE,
  OFFERED_AS_A_TABLE,
  PROBLEMS,
  acceptsWords,
} from "../src/pages/knowledge/formParts";
import { UNAVAILABLE } from "../src/pages/knowledge/knowledgeActions";
import {
  DOCUMENTS_API_PATH,
  EVENT_WORDS,
  REVIEW_VALUES,
  VERIFICATIONS_API_PATH,
  historyPath,
  readDocRow,
  verifiedWords,
} from "../src/pages/knowledge/knowledgeDocuments";
import { ADD_LABEL, KNOWLEDGE_HEADING, NO_DOCUMENTS } from "../src/pages/knowledge/KnowledgePage";
import { CAPTURE, CAPTURE_PROBLEMS } from "../src/pages/knowledge/SolutionsPage";
import { QUEUED_FIELDS, QUEUED_STATES, queuedPath, readQueued } from "../src/pages/knowledgeIntakeQuery";
import {
  instantOf,
  isAfterToday,
  itemPath,
  newVersionPath,
  passagesPath,
  promotionPath,
  SOLUTIONS_API_PATH,
  solutionDecisionPath,
  stewardPath,
  TASKS_API_PATH,
  taskDonePath,
  verificationPath,
} from "../src/pages/knowledgeLifecycleQuery";
import { CLASSIFICATION_PATH } from "../src/pages/classificationQuery";
import {
  isOfferedAsTable,
  KIND_WORDS,
  readUploadOptions,
  UPLOAD_OPTIONS_API_PATH,
  uploadPath,
} from "../src/pages/knowledgeQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { apiDocument } from "./support/openapi";
import { backendEnumMembers, backendModelFields } from "./support/python";
import { installRadixStubs } from "./support/radix";
import { readRepoFile } from "./support/repo";

const API = "/api/v1";
const ORIGIN = "https://console.test";
const ITEM = "upload.tealsentinel";
const OLDER = "upload.tealolder";
const STEWARD_ID = "u_steward_sentinel";
const VERIFIER_ID = "u_verifier_sentinel";

beforeAll(() => {
  installRadixStubs();
});

const DOCUMENT = {
  item_id: ITEM,
  title: "Site handover",
  kind: "sop",
  kind_label: "SOP",
  level: "department",
  department: "web",
  steward_id: STEWARD_ID,
  state: "published",
  verification: "verified",
  verified_by: VERIFIER_ID,
  verified_at: "2019-03-02T09:00:00+00:00",
  review_by: "2999-01-01T12:00:00+00:00",
  due: false,
  supersedes: OLDER,
  added_at: "2019-03-04T09:00:00+00:00",
  you_steward: false,
  solves: null,
  promotion: null,
  steward_name: "Aisha Web",
  verified_by_name: "Ben Check",
};

const OLDER_DOCUMENT = {
  ...DOCUMENT,
  item_id: OLDER,
  state: "superseded",
  verification: "superseded",
  verified_by: null,
  verified_at: null,
  verified_by_name: null,
  supersedes: null,
};

const DETAIL = {
  document: DOCUMENT,
  versions: [
    { item_id: OLDER, title: "Site handover", state: "superseded", level: "department", department: "web", added_at: "2019-03-01T09:00:00+00:00", readable: true },
    { item_id: ITEM, title: "Site handover", state: "published", level: "department", department: "web", added_at: "2019-03-04T09:00:00+00:00", readable: true },
  ],
  offered: { verify: true, new_version: true, propose: false, hand_over: true },
  promotion_waits: "Asking puts a card on the Approvals screen.",
};

const TASKS = {
  items: [
    { task_id: "steward.b", kind: "steward_named", item_id: ITEM, says: "You are now the steward of Site handover.", opened_at: "2019-03-02T09:00:00+00:00", due_at: null, closable: true },
  ],
};

const OPTIONS = {
  kinds: [{ value: "sop", label: "SOP" }],
  departments: ["web"],
  personal: false,
  types: [
    { media_type: "text/markdown", extensions: [".md", ".markdown"], max_bytes: 5 * 1024 * 1024 },
    { media_type: "application/pdf", extensions: [".pdf"], max_bytes: 20 * 1024 * 1024 },
  ],
  found_by: "text search",
  checked_by: "structural check",
  offered_as_tables: [".csv", ".xlsx"],
};

const HISTORY = {
  item_id: ITEM,
  events: [
    { item_id: OLDER, at: "2019-03-01T09:00:00+00:00", event: "added" },
    { item_id: OLDER, at: "2019-03-04T09:00:00+00:00", event: "replaced" },
    { item_id: ITEM, at: "2019-03-04T09:00:00+00:00", event: "handed_over" },
  ],
  truncated: false,
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

type Answers = Readonly<Record<string, unknown>>;

/** A stand-in API: each GET path answers its body, and every write answers `written`. */
function api(answers: Answers, written: unknown = {}): FakeIdp {
  return fakeIdentityProvider({
    api(url, init) {
      const path = new URL(url, ORIGIN).pathname;
      if ((init?.method ?? "GET") !== "GET") {
        return json(written);
      }
      const found = Object.entries(answers).find(([key]) => path === `${API}${key}`);
      return found === undefined ? null : found[1] === 404 ? json({ message: "I could not find that." }, 404) : json(found[1]);
    },
  });
}

function writes(idp: FakeIdp): { url: URL; init: RequestInit }[] {
  return idp.calls
    .filter((call) => (call.init?.method ?? "GET") !== "GET" && new URL(call.url, ORIGIN).pathname.startsWith("/api/"))
    .map((call) => ({ url: new URL(call.url, ORIGIN), init: call.init as RequestInit }));
}

function bodyOf(init: RequestInit): unknown {
  return JSON.parse(String(init.body));
}

async function page(address: string, idp: FakeIdp): Promise<HTMLElement> {
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [address] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (!container.querySelector("h1")) {
      throw new Error("the page has not arrived");
    }
  });
  await waitFor(() => {
    if (container.querySelector('[data-slot="loading-state"]')) {
      throw new Error("the page is still asking");
    }
  });
  return container;
}

/** A form rendered on its own, in a signed-in console, so its writes reach the stand-in API. */
async function alone(idp: FakeIdp, element: ReactElement): Promise<HTMLElement> {
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { container } = render(<MemoryRouter>{element}</MemoryRouter>);
  return container;
}

function setField(scope: ParentNode, name: string, value: string): void {
  const field = scope.querySelector(`[name="${name}"]`);
  if (field === null) {
    throw new Error(`no ${name} field`);
  }
  fireEvent.change(field, { target: { value } });
}

function textOutsideAdvanced(container: HTMLElement): string {
  const copy = container.cloneNode(true) as HTMLElement;
  copy.querySelectorAll('[data-slot="advanced"]').forEach((one) => one.remove());
  return copy.textContent ?? "";
}

const LIST = { [DOCUMENTS_API_PATH]: { items: [DOCUMENT, OLDER_DOCUMENT], next_cursor: null, total: null, truncated: false } };

// ------------------------------------------------------------------------------ the list
describe("the Knowledge list", () => {
  test("it draws each document by title with its department, reach, steward's name, review and state", async () => {
    // What breaks if this is deleted: the list goes back to three facts a row, or names a steward by
    // the principal id the owner found cluttering every page.
    const idp = api({ ...LIST, [UPLOAD_OPTIONS_API_PATH]: OPTIONS, [TASKS_API_PATH]: { items: [] } });
    const container = await page("/library", idp);
    const table = container.querySelector('[data-slot="entity-table"]') as HTMLElement;
    const heads = [...table.querySelectorAll("th")].map((one) => one.textContent ?? "").filter((one) => one !== "");

    expect(container.querySelector("h1")?.textContent).toBe(KNOWLEDGE_HEADING);
    expect(heads).toEqual(["Document", "Department", "Visible to", "Steward", "Verified", "Review due", "State", "Actions"]);
    const rows = [...table.querySelectorAll("tbody tr")];
    expect(rows).toHaveLength(2);
    expect(rows[0]?.textContent).toContain("Aisha Web");
    expect(rows[0]?.textContent).toContain("Verified by Ben Check");
    expect(rows[0]?.textContent).toContain("Current");
    expect(rows[1]?.textContent).toContain("Superseded");
    expect(table.querySelector("tbody a")?.getAttribute("href")).toBe(`/library/${ITEM}`);
    expect(container.textContent).not.toContain(STEWARD_ID);
    expect(container.textContent).not.toContain(VERIFIER_ID);
    expect(container.textContent).not.toContain(ITEM);
  });

  test("Export inventory is drawn inert with its reason, and Add is offered to somebody the API lets add", async () => {
    // What breaks if this is deleted: an unrecorded export of titles, or the upload control vanishing
    // for the people who may add documents.
    const idp = api({ ...LIST, [UPLOAD_OPTIONS_API_PATH]: OPTIONS, [TASKS_API_PATH]: { items: [] } });
    const container = await page("/library", idp);
    const inert = [...container.querySelectorAll(`[${UNAVAILABLE_MARK}]`)].map((one) => one.textContent ?? "");

    expect(inert).toContain("Export inventory");
    expect(container.textContent).toContain(UNAVAILABLE.exportInventory.reason);
    expect([...container.querySelectorAll("button")].some((one) => (one.textContent ?? "").includes(ADD_LABEL))).toBe(true);
  });

  test("somebody the API lets add nothing sees no Add, and an empty list says what would fill it", async () => {
    // What breaks if this is deleted: an Add control that is refused on every press, or an empty list
    // that says why it is empty, which tells a reader something exists they may not see.
    const idp = api({
      [DOCUMENTS_API_PATH]: { items: [], next_cursor: null, total: null, truncated: false },
      [UPLOAD_OPTIONS_API_PATH]: 404,
      [TASKS_API_PATH]: { items: [] },
    });
    const container = await page("/library", idp);

    expect(container.textContent).toContain(NO_DOCUMENTS);
    expect([...container.querySelectorAll("button")].some((one) => (one.textContent ?? "").includes(ADD_LABEL))).toBe(false);
  });

  test("the Review filter offers both words and asks the route for the due documents", async () => {
    // What breaks if this is deleted: the Review due chip SCREEN 7 draws, filtering on a date the
    // row does not carry, or offered only once a due row has been drawn.
    const idp = api({ ...LIST, [UPLOAD_OPTIONS_API_PATH]: 404, [TASKS_API_PATH]: { items: [] } });
    const container = await page("/library", idp);
    const review = [...container.querySelectorAll("select")].find((one) => one.labels?.[0]?.textContent === "Review") as HTMLSelectElement;

    expect([...review.options].map((one) => one.value)).toEqual(["", ...REVIEW_VALUES]);
    fireEvent.change(review, { target: { value: "due" } });
    await waitFor(() => {
      const asked = idp.calls.map((call) => new URL(call.url, ORIGIN)).filter((url) => url.pathname === `${API}${DOCUMENTS_API_PATH}`);
      expect(asked.some((url) => url.searchParams.getAll("filter").includes("review:due"))).toBe(true);
    });
  });

  test("the Kind filter offers each kind the rows carry, in the library's words, and asks the route for one (M7.6.1)", async () => {
    // What breaks if this is deleted: a library whose documents carry a kind nobody can narrow by,
    // or a filter sending the label rather than the stored word, which the route matches nothing on.
    const idp = api({ ...LIST, [UPLOAD_OPTIONS_API_PATH]: 404, [TASKS_API_PATH]: { items: [] } });
    const container = await page("/library", idp);
    const kind = await waitFor(() => {
      const found = [...container.querySelectorAll("select")].find((one) => one.labels?.[0]?.textContent === "Kind");
      if (found === undefined) {
        throw new Error("the Kind filter is not drawn");
      }
      return found;
    });

    expect([...kind.options].map((one) => [one.value, one.textContent])).toContainEqual(["sop", KIND_WORDS["sop"]]);
    fireEvent.change(kind, { target: { value: "sop" } });
    await waitFor(() => {
      const asked = idp.calls.map((call) => new URL(call.url, ORIGIN)).filter((url) => url.pathname === `${API}${DOCUMENTS_API_PATH}`);
      expect(asked.some((url) => url.searchParams.getAll("filter").includes("kind:sop"))).toBe(true);
    });
  });

  test("ticked documents are verified with one review date, after a confirmation, as one request of each id", async () => {
    // What breaks if this is deleted: M27.15.40's bulk re-verify, or several vouches sent on one press
    // with no confirmation saying what they are.
    const idp = api(
      { ...LIST, [UPLOAD_OPTIONS_API_PATH]: 404, [TASKS_API_PATH]: { items: [] } },
      { outcomes: [{ item_id: ITEM, verified: true, says: "verified" }] },
    );
    const container = await page("/library", idp);
    fireEvent.click(within(container).getAllByRole("checkbox", { name: `Select ${DOCUMENT.title}` })[0] as HTMLElement);
    const bar = within(container).getByRole("region", { name: "Bulk actions" });
    fireEvent.click(within(bar).getByText("Verify"));
    expect(writes(idp)).toEqual([]);
    const dialog = await screen.findByRole("alertdialog");
    fireEvent.change(within(dialog).getByLabelText("Next review by"), { target: { value: "2999-02-03" } });
    fireEvent.click(within(dialog).getByText("Verify them"));

    await waitFor(() => expect(writes(idp)).toHaveLength(1));
    const [sent] = writes(idp);
    expect(sent?.url.pathname).toBe(`${API}${VERIFICATIONS_API_PATH}`);
    expect(bodyOf(sent?.init as RequestInit)).toEqual({ item_ids: [ITEM], review_by: "2999-02-03T12:00:00+00:00" });
    await waitFor(() => expect(container.textContent).toContain("Verified 1 of the 1 you chose."));
  });

  test("the reader's own tasks sit above the list, and one that reports is marked read", async () => {
    // What breaks if this is deleted: a task the database opened that nobody sees, or a review task
    // dismissed while its document stays overdue.
    const idp = api({ ...LIST, [UPLOAD_OPTIONS_API_PATH]: 404, [TASKS_API_PATH]: TASKS });
    const container = await page("/library", idp);

    expect(container.textContent).toContain("You are now the steward of Site handover.");
    fireEvent.click(within(container).getByText("Mark as read"));
    await waitFor(() => expect(writes(idp)).toHaveLength(1));
    expect(writes(idp)[0]?.url.pathname).toBe(`${API}${taskDonePath("steward.b")}`);
  });
});

// ------------------------------------------------------------------------ one document
describe("one document's page", () => {
  const answers = {
    [itemPath(ITEM)]: DETAIL,
    [TASKS_API_PATH]: TASKS,
    [historyPath(ITEM)]: HISTORY,
    [passagesPath(ITEM)]: { item_id: ITEM, title: "Site handover", state: "published", passages: [{ ordinal: 0, section: "", page: null, text: "Sign the TEAL list." }], truncated: false },
  };

  test("the Dashboard names it, shows what is recorded, and offers only the acts the API offered", async () => {
    // What breaks if this is deleted: a figure drawn as nought where nothing counted it, or a control
    // for an act this reader's reach withholds, such as asking for the whole company here.
    const idp = api(answers);
    const container = await page(`/library/${ITEM}`, idp);
    const header = container.querySelector('[data-slot="detail-header"]') as HTMLElement;

    expect(header.querySelector("h1")?.textContent).toBe("Site handover");
    expect(header.textContent).toContain("Versions");
    expect(header.textContent).toContain("2");
    expect(header.textContent).toContain("Your open tasks");
    expect(within(header).getByText("Verify")).toBeDefined();
    const views = [...container.querySelectorAll('[data-slot="view-switch"] a')].map((one) => [one.textContent, one.getAttribute("href")]);
    expect(views).toEqual([
      ["Dashboard", `/library/${ITEM}`],
      ["Profile", `/library/${ITEM}/profile`],
      ["About", `/library/${ITEM}/about`],
    ]);
    expect(container.textContent).not.toContain("Ask for approval");
    expect(textOutsideAdvanced(container)).not.toContain(STEWARD_ID);
  });

  test("the Profile names the steward and keeps every identifier in Advanced, and the text is read on a press", async () => {
    // What breaks if this is deleted: ids back in the page text, or a document's text fetched for
    // every reader who opens its record.
    const idp = api(answers);
    const container = await page(`/library/${ITEM}/profile`, idp);

    expect(container.textContent).toContain("Aisha Web");
    expect(textOutsideAdvanced(container)).not.toContain(STEWARD_ID);
    expect(textOutsideAdvanced(container)).not.toContain(ITEM);
    const advanced = container.querySelector('[data-slot="advanced"]') as HTMLElement;
    expect(advanced.querySelector("summary")?.textContent).toBe(ADVANCED_LABEL);
    expect(advanced.textContent).toContain(STEWARD_ID);
    expect(advanced.textContent).toContain(ITEM);
    const asked = () => idp.calls.filter((call) => new URL(call.url, ORIGIN).pathname === `${API}${passagesPath(ITEM)}`);
    expect(asked()).toEqual([]);
    fireEvent.click(within(container).getByText("Show the text"));
    await waitFor(() => expect(container.textContent).toContain("Sign the TEAL list."));
  });

  test("About lists its versions and what happened, in words, naming nobody", async () => {
    // What breaks if this is deleted: the history M27.15.40 asks for, or a ledger actor drawn beside
    // an event, which is how a verifier's name would leak past the badge.
    const idp = api(answers);
    const container = await page(`/library/${ITEM}/about`, idp);
    await waitFor(() => expect(container.textContent).toContain(EVENT_WORDS["handed_over"] ?? "x"));

    expect(container.textContent).toContain(EVENT_WORDS["replaced"] ?? "x");
    expect(container.textContent).toContain(EVENT_WORDS["added"] ?? "x");
    expect(container.querySelector(`a[href="/library/${OLDER}"]`)).not.toBeNull();
    expect(container.textContent).not.toContain(VERIFIER_ID);
  });

  test("a document that is refused and one that is not there are one failure, said in the API's words", async () => {
    // What breaks if this is deleted: a page explaining a 404, which tells a reader the document is
    // somebody else's.
    const idp = api({ [itemPath(ITEM)]: 404, [TASKS_API_PATH]: TASKS });
    const loaded = await loadConsole({ idp });
    await signIn(loaded);
    const { routes } = await import("../src/App");
    const { container } = render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [`/library/${ITEM}`] })} />);
    await waitFor(() => expect(container.textContent).toContain("I could not find that."));
    expect(container.querySelector('[data-slot="detail-header"]')).toBeNull();
  });
});

// ------------------------------------------------------------------------------ the forms
describe("the forms", () => {
  const options = readUploadOptions(OPTIONS);
  if (options === null) {
    throw new Error("the options did not read");
  }

  test("adding a file says which types and sizes it takes before anything is sent, and a blank one sends nothing", async () => {
    // What breaks if this is deleted: a form that tells a person what it accepts only after refusing
    // them, or one that sends an empty upload.
    const idp = api({});
    const container = await alone(idp, <AddFileForm options={options} onAdded={() => undefined} />);

    expect(container.textContent).toContain(acceptsWords(options.types));
    expect(acceptsWords(options.types)).toContain(".md, .markdown up to 5 MB");
    fireEvent.submit(container.querySelector("form") as HTMLFormElement);
    expect(container.textContent).toContain(PROBLEMS.file);
    expect(container.textContent).toContain(PROBLEMS.kind);
    expect(writes(idp)).toEqual([]);

    const file = new File(["# Notes"], "Notes.md", { type: "" });
    fireEvent.change(container.querySelector('input[type="file"]') as HTMLInputElement, { target: { files: [file] } });
    setField(container, "kind", "sop");
    setField(container, "department", "web");
    fireEvent.submit(container.querySelector("form") as HTMLFormElement);
    await waitFor(() => expect(writes(idp)).toHaveLength(1));
    const [sent] = writes(idp);
    expect(`${sent?.url.pathname}${sent?.url.search}`).toBe(`${API}${uploadPath("sop", "department", "web")}`);
    expect(sent?.init.body).toBe(file);
  });

  test("a spreadsheet chosen as a document is offered to Classification with a link, and is not sent", async () => {
    // What breaks if this is deleted: a price list sent to be indexed as text, cost and margin in
    // passages a department's readers are shown, or refused as an unknown type with no word of where
    // it belongs (M7.7.3). The batch form says the same of each spreadsheet in it.
    const idp = api({});
    const container = await alone(idp, <AddFileForm options={options} onAdded={() => undefined} />);
    const sheet = new File(["name,sell,cost"], "Price list.csv", { type: "text/csv" });
    fireEvent.change(container.querySelector('input[type="file"]') as HTMLInputElement, { target: { files: [sheet] } });
    setField(container, "kind", "sop");
    setField(container, "department", "web");
    fireEvent.submit(container.querySelector("form") as HTMLFormElement);
    expect(container.textContent).toContain(OFFERED_AS_A_TABLE);
    expect(container.textContent).not.toContain(PROBLEMS.type);
    expect(container.querySelector(`a[href="${CLASSIFICATION_PATH}"]`)?.textContent).toBe(ADD_IT_ON_CLASSIFICATION);
    expect(writes(idp)).toEqual([]);

    const many = api({});
    const manyForm = await alone(many, <AddManyForm options={options} onAdded={() => undefined} />);
    const notes = new File(["# Notes"], "Notes.md", { type: "" });
    const workbook = new File(["x"], "Prices.XLSX", { type: "" });
    fireEvent.change(manyForm.querySelector('input[type="file"]') as HTMLInputElement, { target: { files: [workbook] } });
    setField(manyForm, "kind", "sop");
    setField(manyForm, "department", "web");
    fireEvent.submit(manyForm.querySelector("form") as HTMLFormElement);
    await waitFor(() => expect(manyForm.textContent).toContain(`Prices.XLSX: ${NOT_SENT_TABLE}`));
    expect(writes(many)).toEqual([]);
    expect(isOfferedAsTable(notes.name, options)).toBe(false);
  });

  test("a blank web page or a blank batch sends nothing and says what to fill in", async () => {
    // What breaks if this is deleted: a fetch of nothing, or a queue asked to read no files.
    const link = api({});
    const linkForm = await alone(link, <AddLinkForm options={options} onAdded={() => undefined} />);
    fireEvent.submit(linkForm.querySelector("form") as HTMLFormElement);
    expect(linkForm.textContent).toContain("beginning with https");
    expect(writes(link)).toEqual([]);

    const many = api({});
    const manyForm = await alone(many, <AddManyForm options={options} onAdded={() => undefined} />);
    fireEvent.submit(manyForm.querySelector("form") as HTMLFormElement);
    expect(manyForm.textContent).toContain(PROBLEMS.files);
    expect(writes(many)).toEqual([]);
  });

  test("a file queued behind others is shown its place in line and expected wait, as the API said them", async () => {
    // M22.1.4. What breaks if this is deleted: the queued upload's place and wait sent by the API
    // and dropped by the form, which is every queued file told only that it is queued, or a field
    // added to `QueuedView` that the form never reads.
    expect([...QUEUED_FIELDS].sort()).toEqual(backendModelFields("src/brain/knowledge_intake_routes.py", "QueuedView").sort());
    const said = "Notes.md is queued to be read, number 3 in line, and should start in about 90 seconds.";
    const view = {
      ticket: "a".repeat(40),
      name: "Notes.md",
      state: "queued",
      said,
      item_id: null,
      passages: 0,
      position: 3,
      expected_wait_seconds: 90,
    };
    expect(Object.keys(view).sort()).toEqual([...QUEUED_FIELDS].sort());
    const read = readQueued(view);
    expect([read?.position, read?.expectedWaitSeconds]).toEqual([3, 90]);
    expect(readQueued({ ...view, position: null, expected_wait_seconds: null })?.position).toBeNull();

    const idp = api({}, view);
    const container = await alone(idp, <AddManyForm options={options} onAdded={() => undefined} />);
    const file = new File(["# Notes"], "Notes.md", { type: "" });
    fireEvent.change(container.querySelector('input[type="file"]') as HTMLInputElement, { target: { files: [file] } });
    setField(container, "kind", "sop");
    setField(container, "department", "web");
    fireEvent.submit(container.querySelector("form") as HTMLFormElement);
    await waitFor(() => expect(container.textContent).toContain(said));
    const [sent] = writes(idp);
    expect(`${sent?.url.pathname}${sent?.url.search}`).toBe(`${API}${queuedPath("sop", "department", "web")}`);
  });

  test("verifying refuses a day that is not after today before sending, and sends a later one as noon UTC", async () => {
    // What breaks if this is deleted: a verification that leaves the sweep for good, or a review day
    // that moves with the browser's timezone.
    const idp = api({});
    const container = await alone(idp, <VerifyForm itemId={ITEM} onDone={() => undefined} />);
    setField(container, "review_by", "2019-01-01");
    fireEvent.submit(container.querySelector("form") as HTMLFormElement);
    expect(container.textContent).toContain(PROBLEMS.reviewAhead);
    expect(writes(idp)).toEqual([]);

    setField(container, "review_by", "2999-02-03");
    fireEvent.submit(container.querySelector("form") as HTMLFormElement);
    await waitFor(() => expect(writes(idp)).toHaveLength(1));
    expect(writes(idp)[0]?.url.pathname).toBe(`${API}${verificationPath(ITEM)}`);
    expect(bodyOf(writes(idp)[0]?.init as RequestInit)).toEqual({ review_by: "2999-02-03T12:00:00+00:00" });
  });

  test("a newer version and a hand-over are each confirmed in a sentence before they are sent", async () => {
    // What breaks if this is deleted: the text answers are drawn from, or the steward, replaced by one
    // press (M7.4.5, M7.7.2).
    const version = api({});
    const versionForm = await alone(version, <NewVersionForm itemId={ITEM} title="Site handover" onDone={() => undefined} />);
    const file = new File(["# Site handover\n\nNew text."], "Site handover v2.md", { type: "" });
    fireEvent.change(versionForm.querySelector('input[type="file"]') as HTMLInputElement, { target: { files: [file] } });
    setField(versionForm, "review_by", "2999-02-03");
    fireEvent.submit(versionForm.querySelector("form") as HTMLFormElement);
    expect(writes(version)).toEqual([]);
    let dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain(NEW_VERSION_CONSEQUENCE);
    fireEvent.click(within(dialog).getByText(ADD_VERSION));
    await waitFor(() => expect(writes(version)).toHaveLength(1));
    const [sent] = writes(version);
    expect(`${sent?.url.pathname}${sent?.url.search}`).toBe(`${API}${newVersionPath(ITEM, "2999-02-03T12:00:00+00:00")}`);
    expect(sent?.url.search).not.toContain("handover");

    const hand = api({});
    const handForm = await alone(hand, <HandOverForm itemId={ITEM} title="Site handover" onDone={() => undefined} />);
    fireEvent.submit(handForm.querySelector("form") as HTMLFormElement);
    expect(handForm.textContent).toContain(PROBLEMS.steward);
    setField(handForm, "steward_id", "u_narrow");
    fireEvent.submit(handForm.querySelector("form") as HTMLFormElement);
    dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain(HAND_OVER_CONSEQUENCE);
    expect(writes(hand)).toEqual([]);
    fireEvent.click(within(dialog).getByText(HAND_OVER));
    await waitFor(() => expect(writes(hand)).toHaveLength(1));
    expect(writes(hand)[0]?.url.pathname).toBe(`${API}${stewardPath(ITEM)}`);
    expect(bodyOf(writes(hand)[0]?.init as RequestInit)).toEqual({ steward_id: "u_narrow" });
  });

  test("asking for the whole company needs a reason, and sends it with the review date", async () => {
    // What breaks if this is deleted: a promotion card on the Approvals screen with no reason on it.
    const idp = api({});
    const container = await alone(idp, <ProposeForm itemId={ITEM} waits="It waits on the Approvals screen." onDone={() => undefined} />);
    fireEvent.submit(container.querySelector("form") as HTMLFormElement);
    expect(container.textContent).toContain(PROBLEMS.reason);
    expect(writes(idp)).toEqual([]);
    setField(container, "reason", "Every team quotes from it.");
    setField(container, "review_by", "2999-02-03");
    fireEvent.submit(container.querySelector("form") as HTMLFormElement);
    await waitFor(() => expect(writes(idp)).toHaveLength(1));
    expect(writes(idp)[0]?.url.pathname).toBe(`${API}${promotionPath(ITEM)}`);
    expect(bodyOf(writes(idp)[0]?.init as RequestInit)).toEqual({ review_by: "2999-02-03T12:00:00+00:00", reason: "Every team quotes from it." });
  });
});

// ---------------------------------------------------------------------------- solutions
describe("Solutions", () => {
  const WAITING = {
    solution_id: "solution.tealfix",
    department: "web",
    problem: "Checkout fails after the plugin update",
    answer: "Clear the object cache.",
    conversation_ref: null,
    captured_by: "u_capturer_sentinel",
    captured_at: "2019-03-02T09:00:00+00:00",
    state: "pending",
    decided_by: null,
    decided_at: null,
    item_id: null,
    captured_by_name: "Cara Capture",
    decided_by_name: null,
  };
  const SOLUTIONS = { waiting: [WAITING], yours: [], departments: ["web"] };

  test("a waiting solution names its capturer, and is approved only with a review date", async () => {
    // What breaks if this is deleted: a capturer drawn as a principal id, or an approval sent with no
    // review date for the document it becomes (M7.6.2).
    const idp = api({ [SOLUTIONS_API_PATH]: SOLUTIONS });
    const container = await page("/solutions", idp);

    expect(container.textContent).toContain("Cara Capture");
    expect(container.textContent).not.toContain("u_capturer_sentinel");
    const form = container.querySelector('form[aria-label^="Decide"]') as HTMLFormElement;
    setField(form, "review_by", "");
    fireEvent.submit(form);
    expect(form.textContent).toContain(PROBLEMS.review);
    expect(writes(idp)).toEqual([]);
    setField(form, "review_by", "2999-02-03");
    fireEvent.submit(form);
    await waitFor(() => expect(writes(idp)).toHaveLength(1));
    expect(writes(idp)[0]?.url.pathname).toBe(`${API}${solutionDecisionPath("solution.tealfix")}`);
    expect(bodyOf(writes(idp)[0]?.init as RequestInit)).toEqual({ verdict: "approved", review_by: "2999-02-03T12:00:00+00:00" });
  });

  test("capturing sent blank says what to fill in and sends nothing", async () => {
    // What breaks if this is deleted: an empty solution waiting for somebody's decision.
    const idp = api({ [SOLUTIONS_API_PATH]: SOLUTIONS });
    const container = await page("/solutions", idp);
    fireEvent.click(within(container).getByText(CAPTURE));
    const drawer = await screen.findByRole("dialog");
    const form = drawer.querySelector("form") as HTMLFormElement;
    setField(form, "department", "");
    fireEvent.submit(form);
    expect(form.textContent).toContain(CAPTURE_PROBLEMS.problem);
    expect(form.textContent).toContain(CAPTURE_PROBLEMS.answer);
    expect(form.textContent).toContain(CAPTURE_PROBLEMS.department);
    expect(writes(idp)).toEqual([]);
    await act(async () => {
      fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    });
  });
});

// ------------------------------------------------------------------------------ helpers
describe("what the module reads and says", () => {
  test("no act the pages call coming soon has a route in the API document", () => {
    // What breaks if this is deleted: "coming soon" said about Archive or Export after its route has
    // landed. The positive sibling holds that each pattern matches the path it is written for.
    const paths = Object.keys((apiDocument()["paths"] ?? {}) as Record<string, unknown>);
    for (const [act, { retiredBy }] of Object.entries(UNAVAILABLE)) {
      expect(paths.filter((path) => retiredBy.test(path)), act).toEqual([]);
    }
    expect(UNAVAILABLE.archive.retiredBy.test("/api/v1/knowledge/items/{item_id}/archive")).toBe(true);
    expect(UNAVAILABLE.exportInventory.retiredBy.test("/api/v1/knowledge/inventory")).toBe(true);
    expect(paths).toContain(`${API}${DOCUMENTS_API_PATH}`);
    expect(paths).toContain(`${API}${VERIFICATIONS_API_PATH}`);
  });

  test("the words the module draws are keyed by exactly what the Python sends", () => {
    // What breaks if this is deleted: a kind, a history event or a queued state added in the Python
    // and drawn as its stored word, or a review filter value the route does not match.
    const kinds = backendEnumMembers("src/brain/knowledge/kinds.py", "KnowledgeKind");
    expect(Object.keys(KIND_WORDS).sort()).toEqual(Object.values(kinds).sort());
    const events = backendEnumMembers("src/brain/knowledge/lifecycle.py", "HistoryEvent");
    expect(Object.keys(EVENT_WORDS).sort()).toEqual(Object.values(events).sort());
    const queued = backendEnumMembers("src/brain/knowledge/ingest_queue.py", "TicketState");
    expect([...QUEUED_STATES].sort()).toEqual(Object.values(queued).sort());
    expect(readQueued({ ticket: "x", name: "x", state: "lost", said: "x" })).toBeNull();
    const routes = readRepoFile("src/brain/knowledge_lifecycle_routes.py");
    const due = /^REVIEW_DUE: Final = "([^"]+)"/m.exec(routes)?.[1];
    const notDue = /^REVIEW_NOT_DUE: Final = "([^"]+)"/m.exec(routes)?.[1];
    expect([...REVIEW_VALUES]).toEqual([due, notDue]);
  });

  test("a row keeps only what was sent, and a verification names nobody the API did not name", () => {
    // What breaks if this is deleted: a steward or a verifier filled in from somewhere other than the
    // answer, which is how a name the badge withholds would be drawn.
    const bare = readDocRow({ item_id: ITEM, title: "Site handover", level: "department", state: "published", verification: "verified" });
    expect(bare).not.toBeNull();
    expect(bare !== null && "stewardName" in bare).toBe(false);
    expect(bare === null ? "" : verifiedWords(bare)).toBe("Verified");
    const named = readDocRow(DOCUMENT);
    expect(named === null ? "" : verifiedWords(named)).toBe("Verified by Ben Check on 2 Mar 2019");
    expect(readDocRow({ title: "no id" })).toBeNull();
  });

  test("a picked day is noon UTC that day, and a review day must be after today", () => {
    // What breaks if this is deleted: a review date moving a day with the browser's timezone, or a
    // past date sent for the API to refuse.
    const today = new Date("2019-03-04T23:30:00Z");
    expect(instantOf("2019-03-05")).toBe("2019-03-05T12:00:00+00:00");
    expect(instantOf("5 March")).toBeNull();
    expect(isAfterToday("2019-03-05", today)).toBe(true);
    expect(isAfterToday("2019-03-04", today)).toBe(false);
  });
});
