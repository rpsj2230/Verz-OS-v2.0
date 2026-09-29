/**
 * Access reviews and elevation on the page kit: the review list and one holding's page, the
 * certification report, the elevation requests and one request's page.
 *
 * Mounted through each page's own route file on a memory router, signed in through the real session
 * modules and answered by a stand-in API. The failures worth testing look like a screen working: a
 * decision sent without a confirmation or with a body key the route forbids, a confirmation that
 * paraphrases what happens, a principal id drawn where a name belongs, a form that says what it takes
 * only after a refusal, and a row's own page that says whether a hidden row exists.
 *
 * Task ids: M27.7.8, M27.7.9, M27.15.21, M27.16.1
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { ASK_BLANKS, type ElevationRequestRow, type ReviewRow } from "../src/pages/governPeopleQuery";
import {
  CERTIFICATION_EXPORT_API_PATH,
  EXPORT_REASONS,
  REASON_BLANK,
  REFERENCE_BLANK,
  REFERENCE_PATTERN,
} from "../src/pages/review/CertificationExport";
import { NO_HOLDING, READING_HOLDING } from "../src/pages/review/HoldingPage";
import { NO_REQUESTS, READING_ELEVATION } from "../src/pages/review/ElevationPage";
import { READING_REQUEST } from "../src/pages/review/RequestPage";
import { NOTHING_TO_REVIEW, READING_REVIEW } from "../src/pages/review/ReviewPage";
import { ACT_LABELS, UNAVAILABLE } from "../src/pages/review/reviewActions";
import { holdingAddress, requestAddress } from "../src/pages/review/reviewQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { apiDocument, declaredQueryParameters, declaredRequestBodySchema } from "./support/openapi";
import { backendEnumMembers } from "./support/python";
import { installRadixStubs } from "./support/radix";
import { readRepoFile } from "./support/repo";
import { chooseInMenu, confirmWith } from "./support/rowMenu";

const CONSOLE_ORIGIN = "https://console.test";
const REVIEW = "/api/v1/govern/access-review";
const DECISION = "/api/v1/govern/access-review/decision";
const DECISIONS = "/api/v1/govern/access-review/decisions";
const EXPORT = `/api/v1${CERTIFICATION_EXPORT_API_PATH}`;
const ELEVATION = "/api/v1/govern/elevation";
const NOTICES = "/api/v1/govern/elevation/notices";
const ASK = "/api/v1/govern/elevation/requests";

/** Principal ids nothing outside Advanced may print. */
const HOLDER = "u_holder_7c1d";
const GRANTOR = "u_grantor_2b9e";
const PEOPLE = { [GRANTOR]: "Gita Grantor" };

const KEEPING = "KEEPING-SENTENCE";
const REMOVING = "REMOVING-SENTENCE";
const WHAT = "WHAT-AN-ELEVATION-IS";

beforeAll(async () => {
  installRadixStubs();
  await import("../src/pages/AccessReview");
  await import("../src/pages/Elevation");
}, 60_000);

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

type Answer = (url: URL, init: RequestInit | undefined) => Response | null;

async function mount(path: string, answer: Answer, reading: string): Promise<{ container: HTMLElement; idp: FakeIdp }> {
  const idp = fakeIdentityProvider({
    api(url, init) {
      return answer(new URL(url, CONSOLE_ORIGIN), init);
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const review = await import("../src/pages/AccessReview.route");
  const elevation = await import("../src/pages/Elevation.route");
  const router = createMemoryRouter(
    [...review.routes, ...elevation.routes].map((one) => ({ path: `/${one.path}`, element: one.element })),
    { initialEntries: [path] },
  );
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (container.querySelector("h1") === null || (container.textContent ?? "").includes(reading)) {
      throw new Error("still reading");
    }
  });
  return { container, idp };
}

function posts(idp: FakeIdp): { path: string; body: unknown }[] {
  return idp.calls
    .filter((call) => call.init?.method === "POST" && new URL(call.url, CONSOLE_ORIGIN).pathname.startsWith("/api/"))
    .map((call) => ({ path: new URL(call.url, CONSOLE_ORIGIN).pathname, body: JSON.parse(String(call.init?.body ?? "null")) as unknown }));
}

function asked(idp: FakeIdp, operation: string): URL[] {
  return idp.urls.map((url) => new URL(url, CONSOLE_ORIGIN)).filter((url) => url.pathname === operation);
}

/** Text outside the Advanced section, which is the only place an id may be. */
function outsideAdvanced(container: HTMLElement): string {
  const copy = container.cloneNode(true) as HTMLElement;
  copy.querySelectorAll('[data-slot="advanced"]').forEach((one) => one.remove());
  return copy.textContent ?? "";
}

// ------------------------------------------------------------------ access review

function holding(over: Partial<ReviewRow> = {}): ReviewRow {
  return {
    kind: "grant",
    row_id: "r-1",
    principal_id: HOLDER,
    display_name: "Wei Ling Tan",
    department: "web",
    capabilities: ["read:client.name"],
    pack: null,
    scope: { clauses: [{ field: "department", op: "eq", value: "web" }] },
    granted_by: GRANTOR,
    reason: "the job needs it",
    granted_at: "2019-03-04T09:00:00Z",
    lapses_at: null,
    last_decision: null,
    last_decided_by: null,
    last_decided_at: null,
    ...over,
  };
}

function review(items: ReviewRow[], over: Record<string, unknown> = {}): unknown {
  return { items, next_cursor: null, truncated: false, shows: "", keeping: KEEPING, removing: REMOVING, people: PEOPLE, ...over };
}

describe("access review", () => {
  test("a row reads as the holder's name, what they hold and who granted it, and no principal id is printed", async () => {
    // What breaks if this is deleted: the ids the owner found cluttering the review come back, or
    // the page asks the route for a parameter it does not declare.
    const declared = new Set(declaredQueryParameters(REVIEW, "get"));
    const { container, idp } = await mount("/access_review", (url) => (url.pathname === REVIEW ? json(review([holding()])) : null), READING_REVIEW);

    const table = within(container.querySelector("table") as HTMLElement);
    expect(table.getByText("Wei Ling Tan")).toBeTruthy();
    expect(table.getByText("read:client.name")).toBeTruthy();
    expect(table.getByText("Gita Grantor")).toBeTruthy();
    expect(table.getByText("Never reviewed")).toBeTruthy();
    expect(container.textContent).not.toContain(HOLDER);
    expect(container.textContent).not.toContain(GRANTOR);
    expect(asked(idp, REVIEW).flatMap((url) => [...url.searchParams.keys()]).filter((name) => !declared.has(name))).toEqual([]);
  });

  test("removing is confirmed in the API's words, sends the three declared keys, and the list is asked again", async () => {
    // What breaks if this is deleted: a decision sent from the menu with no confirmation, a
    // confirmation paraphrasing what happens, a body key the route forbids, or a row patched locally.
    let decided = false;
    const { container, idp } = await mount(
      "/access_review",
      (url) => {
        if (url.pathname === DECISION) {
          decided = true;
          return json({ kind: "grant", row_id: "r-1", principal_id: HOLDER, decision: "remove", decided_at: "2019-05-01T10:00:00Z" });
        }
        return url.pathname === REVIEW ? json(review(decided ? [] : [holding()])) : null;
      },
      READING_REVIEW,
    );
    await chooseInMenu(screen.getByRole("button", { name: /^Actions for read:client.name/ }), ACT_LABELS.remove);
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain("Remove read:client.name from Wei Ling Tan?");
    expect(dialog.textContent).toContain(REMOVING);
    expect(posts(idp)).toEqual([]);
    await confirmWith(ACT_LABELS.remove);

    await waitFor(() => {
      expect(container.textContent).toContain("read:client.name for Wei Ling Tan was removed at");
    });
    await waitFor(() => {
      expect(container.textContent).toContain(NOTHING_TO_REVIEW);
    });
    const [sent] = posts(idp);
    expect(sent?.body).toEqual({ kind: "grant", row_id: "r-1", decision: "remove" });
    expect(Object.keys(sent?.body as object).sort()).toEqual(Object.keys(declaredRequestBodySchema(DECISION, "post")["properties"] as object).sort());
  });

  test("keeping several lists each first, sends their holdings, and says what came of each", async () => {
    // What breaks if this is deleted: a bulk decision whose confirmation names no grant, or a partial
    // refusal read as a success.
    const rows = [holding(), holding({ row_id: "r-2", display_name: "Ahmed Khan" })];
    const { container, idp } = await mount(
      "/access_review",
      (url) => {
        if (url.pathname === DECISIONS) {
          return json({
            decision: "keep",
            outcomes: [
              { kind: "grant", row_id: "r-1", decided: true, principal_id: HOLDER, decided_at: "2019-05-01T10:00:00Z" },
              { kind: "grant", row_id: "r-2", decided: false },
            ],
          });
        }
        return url.pathname === REVIEW ? json(review(rows)) : null;
      },
      READING_REVIEW,
    );
    fireEvent.click(screen.getByRole("checkbox", { name: /Select every row shown/ }));
    fireEvent.click(await screen.findByRole("button", { name: ACT_LABELS.keepSelected }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain("read:client.name for Ahmed Khan is recorded as kept.");
    await confirmWith(ACT_LABELS.keepSelected);

    await waitFor(() => {
      expect(container.textContent).toContain("read:client.name for Ahmed Khan was not decided.");
    });
    expect(posts(idp)[0]?.body).toEqual({
      decision: "keep",
      holdings: [
        { kind: "grant", row_id: "r-1" },
        { kind: "grant", row_id: "r-2" },
      ],
    });
  });

  test("a holding's page asks the list for it by id, names the people, and keeps the ids in Advanced", async () => {
    // What breaks if this is deleted: the page fetches something the review does not decide, or
    // prints the holder's principal id in its heading.
    const { container, idp } = await mount(
      holdingAddress(holding()),
      (url) => (url.pathname === REVIEW ? json(review([holding()])) : null),
      READING_HOLDING,
    );

    const [one] = asked(idp, REVIEW);
    expect(one?.searchParams.getAll("filter").sort()).toEqual(["kind:grant", "row_id:r-1"]);
    expect(container.querySelector("h1")?.textContent).toBe("Wei Ling Tan");
    expect(outsideAdvanced(container)).not.toContain(HOLDER);
    expect(outsideAdvanced(container)).toContain("Gita Grantor");
    expect(container.querySelector('[data-slot="advanced"]')?.textContent).toContain(HOLDER);
  });

  test("a holding the reviewer is not shown is one sentence, the same as one that never existed", async () => {
    // What breaks if this is deleted: a guessed id opens a page that says whether the holding exists.
    const { container } = await mount(holdingAddress(holding()), (url) => (url.pathname === REVIEW ? json(review([])) : null), READING_HOLDING);

    expect(container.textContent).toContain(NO_HOLDING);
    expect(container.textContent).not.toMatch(/permission|not allowed|denied|hidden/i);
  });

  test("the certification report says what each field takes, refuses a blank form, and is sent from its confirmation", async () => {
    // What breaks if this is deleted: M27.15.21's report goes without a reason or a reference, or is
    // sent before anybody agreed to it, or asks the route for a key it does not declare.
    const { idp } = await mount(
      "/access_review",
      (url) => {
        if (url.pathname === EXPORT) {
          return json({
            export: { export_id: "e-1", data_set: "access_certification", reason: "regulatory_request", reason_reference: "AUDIT-1", produced_at: "2019-05-01T10:00:00Z", form: "readable", first_seq: null, last_seq: null, entries: 1, verified: null, document_digest: "a".repeat(64) },
            filename: "access_certification-e-1.csv",
            document: "Person\r\nWei Ling Tan\r\n",
            told: "TOLD-SENTENCE",
          });
        }
        return url.pathname === REVIEW ? json(review([holding()])) : null;
      },
      READING_REVIEW,
    );
    fireEvent.click(screen.getByRole("button", { name: ACT_LABELS.exportReport }));
    const form = (await screen.findByRole("form", { name: ACT_LABELS.exportReport })) as HTMLFormElement;
    expect(form.textContent).toContain("for example AUDIT-2026-Q3");
    fireEvent.submit(form);
    await waitFor(() => {
      expect(form.textContent).toContain(REASON_BLANK);
    });
    expect(form.textContent).toContain(REFERENCE_BLANK);
    expect(screen.queryByRole("alertdialog")).toBeNull();

    fireEvent.change(form.querySelector("select") as HTMLSelectElement, { target: { value: "regulatory_request" } });
    fireEvent.change(form.querySelector('input[name="reason_reference"]') as HTMLInputElement, { target: { value: " AUDIT-1 " } });
    fireEvent.submit(form);
    expect(posts(idp)).toEqual([]);
    await confirmWith(ACT_LABELS.exportReport);

    await waitFor(() => {
      expect(posts(idp)).toHaveLength(1);
    });
    expect(posts(idp)[0]).toEqual({ path: EXPORT, body: { reason: "regulatory_request", reason_reference: "AUDIT-1" } });
    expect(Object.keys(posts(idp)[0]?.body as object).sort()).toEqual(Object.keys(declaredRequestBodySchema(EXPORT, "post")["properties"] as object).sort());
  });

  test("the report's reasons and reference rule are the API's own", () => {
    // What breaks if this is deleted: the form offers a reason the route refuses, or accepts a
    // reference the table's constraint refuses, so the refusal arrives only after the confirmation.
    const pattern = /REFERENCE_PATTERN: Final = r"(.+)"/.exec(readRepoFile("src/brain/tables/data_export.py"))?.[1];
    expect(pattern).toBe(REFERENCE_PATTERN.source);
    expect([...EXPORT_REASONS].sort()).toEqual(Object.values(backendEnumMembers("src/brain/ops/export.py", "ExportReason")).sort());
    const paths = Object.keys((apiDocument()["paths"] as Record<string, unknown>) ?? {});
    for (const one of Object.values(UNAVAILABLE) as { retiredBy: RegExp }[]) {
      expect(paths.filter((path) => one.retiredBy.test(path))).toEqual([]);
    }
  });
});

// ------------------------------------------------------------------ elevation

function aRequest(over: Partial<ElevationRequestRow> = {}): ElevationRequestRow {
  return {
    request_id: "req-1",
    principal_id: HOLDER,
    display_name: "Wei Ling Tan",
    department: "web",
    capability: "read:client.name",
    scope_slug: "web_all",
    reason: "incident_response",
    explanation: "the portal is down",
    hours: 2,
    requested_at: "2019-03-04T09:00:00Z",
    state: "pending",
    decided_by: null,
    decided_at: null,
    lapses_at: null,
    decidable: true,
    ...over,
  };
}

function landing(items: ElevationRequestRow[]): unknown {
  return {
    prompt: "PROMPT-SENTENCE",
    holds_nothing_standing: false,
    may_authorise: true,
    reasons: ["install", "incident_response"],
    longest_hours: 4,
    items,
    next_cursor: null,
    truncated: false,
    what: WHAT,
    recorded: "RECORDED-SENTENCE",
    notified: "",
    authorising: "",
    people: PEOPLE,
  };
}

function elevationAnswers(items: ElevationRequestRow[], extra: Answer = () => null): Answer {
  return (url, init) =>
    extra(url, init) ??
    (url.pathname === ELEVATION ? json(landing(items)) : url.pathname === NOTICES ? json({ items: [], people: {} }) : null);
}

describe("elevation requests", () => {
  test("the list names the person and the decider, and says the reader's standing in one line", async () => {
    // What breaks if this is deleted: the page draws principal ids, or loses the standing a
    // requester needs to read before asking.
    const { container } = await mount(
      "/elevation",
      elevationAnswers([aRequest({ state: "live", decided_by: GRANTOR, decided_at: "2019-03-04T10:00:00Z", lapses_at: "2019-03-04T12:00:00Z", decidable: false })]),
      READING_ELEVATION,
    );

    expect(container.textContent).toContain("PROMPT-SENTENCE");
    const table = within(container.querySelector("table") as HTMLElement);
    expect(table.getByText("Wei Ling Tan")).toBeTruthy();
    expect(table.getByText("Gita Grantor")).toBeTruthy();
    expect(container.textContent).not.toContain(HOLDER);
  });

  test("asking says what each field takes, refuses a blank one before anything is sent, and is sent from its confirmation", async () => {
    // What breaks if this is deleted: an empty request reaches the API, or one is sent without a
    // confirmation naming the capability, the scope and the hours, or with a key the route forbids.
    const { idp } = await mount(
      "/elevation",
      elevationAnswers([], (url, init) =>
        url.pathname === ASK && init?.method === "POST" ? json({ request_id: "r_1", requested_at: "2019-03-04T09:00:00Z" }, 201) : null,
      ),
      READING_ELEVATION,
    );
    fireEvent.click(screen.getByRole("button", { name: ACT_LABELS.ask }));
    const form = (await screen.findByRole("form", { name: "Ask for an elevation" })) as HTMLFormElement;
    expect(form.textContent).toContain("for example read:client.name");
    fireEvent.submit(form);
    await waitFor(() => {
      expect(form.textContent).toContain(ASK_BLANKS.capability);
    });
    expect(form.textContent).toContain(ASK_BLANKS.explanation);
    expect(posts(idp)).toEqual([]);

    const inputs = form.querySelectorAll("input");
    fireEvent.change(inputs[0] as HTMLInputElement, { target: { value: " read:client.name " } });
    fireEvent.change(inputs[1] as HTMLInputElement, { target: { value: "web_all" } });
    const [reason, hours] = [...form.querySelectorAll("select")];
    fireEvent.change(reason as HTMLSelectElement, { target: { value: "incident_response" } });
    fireEvent.change(hours as HTMLSelectElement, { target: { value: "2" } });
    fireEvent.change(form.querySelector("textarea") as HTMLTextAreaElement, { target: { value: "the portal is down" } });
    fireEvent.submit(form);
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain("Ask for read:client.name over web_all for 2 hours?");
    expect(dialog.textContent).toContain(WHAT);
    expect(posts(idp)).toEqual([]);
    await confirmWith(ACT_LABELS.askSend);

    await waitFor(() => {
      expect(posts(idp)).toHaveLength(1);
    });
    const body = posts(idp)[0]?.body;
    expect(body).toEqual({ capability: "read:client.name", scope_slug: "web_all", reason: "incident_response", explanation: "the portal is down", hours: 2 });
    expect(Object.keys(body as object).sort()).toEqual(Object.keys(declaredRequestBodySchema(ASK, "post")["properties"] as object).sort());
  });

  test("a decidable request is approved through its confirmation, and one that is not offers no decision", async () => {
    // What breaks if this is deleted: a decision sent without a confirmation, or offered on a
    // request the API said this reader may not decide.
    const decided: unknown[] = [];
    await mount(
      "/elevation",
      elevationAnswers([aRequest(), aRequest({ request_id: "req-2", display_name: "Ahmed Khan", decidable: false })], (url, init) => {
        if (url.pathname.endsWith("/decision") && init?.method === "POST") {
          decided.push(JSON.parse(String(init.body)));
          return json({ request_id: "req-1", decision: "approved", decided_at: "2019-03-04T10:00:00Z" });
        }
        return null;
      }),
      READING_ELEVATION,
    );
    await chooseInMenu(screen.getByRole("button", { name: "Actions for read:client.name, Wei Ling Tan" }), ACT_LABELS.approve);
    expect(decided).toEqual([]);
    await confirmWith(ACT_LABELS.approve);
    await waitFor(() => {
      expect(decided).toEqual([{ decision: "approved" }]);
    });

    const other = screen.getByRole("button", { name: "Actions for read:client.name, Ahmed Khan" });
    other.focus();
    fireEvent.keyDown(other, { key: "Enter" });
    const menu = await screen.findByRole("menu");
    expect(within(menu).queryByRole("menuitem", { name: ACT_LABELS.approve })).toBeNull();
  });

  test("a request's page asks the list for it by id and a hidden one is the empty sentence", async () => {
    // What breaks if this is deleted: the page reaches past the requests the reader is shown.
    const shown = await mount(requestAddress("req-1"), elevationAnswers([aRequest()]), READING_REQUEST);
    expect(asked(shown.idp, ELEVATION)[0]?.searchParams.getAll("filter")).toEqual(["request_id:req-1"]);
    expect(shown.container.querySelector("h1")?.textContent).toBe("Wei Ling Tan");
    expect(outsideAdvanced(shown.container)).not.toContain(HOLDER);

    const hidden = await mount(requestAddress("req-9"), elevationAnswers([]), READING_REQUEST);
    expect(hidden.container.textContent).toContain("No request here");
    expect(hidden.container.textContent).not.toContain(NO_REQUESTS);
  });
});
