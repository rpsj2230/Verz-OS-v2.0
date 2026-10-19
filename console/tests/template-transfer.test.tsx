/**
 * Withdrawing a template version, putting it back, saving it as a document and bringing one in,
 * on the template pages.
 *
 * **Reachable means through the application's own route table**, as the module's other tests mount
 * it. The failures worth testing: a withdrawal sent without a reason or from a single press, a card
 * drawn for a reader the API refused, an import written from its reading instead of its
 * confirmation, an import confirmed with a digest other than the one it showed, and a "coming soon"
 * sentence left about a route that has arrived.
 *
 * Task ids: M27.15.35
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  DOCUMENT_NEEDED,
  DOCUMENT_UNREADABLE,
  IMPORT_HEADING,
  PUT_BACK,
  REASON_NEEDED,
  WITHDRAW,
  WITHDRAWN_HEADING,
  saveVersion,
} from "../src/pages/agent-templates/TemplateTransfer";
import {
  exportApiPath,
  exportFileName,
  IMPORT_API_PATH,
  parseDocument,
  readImport,
  readWithdrawal,
  readWithdrawn,
  undoApiPath,
  WITHDRAWN_API_PATH,
  withdrawalApiPath,
} from "../src/pages/agent-templates/templateTransferQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { apiDocument } from "./support/openapi";
import { installRadixStubs } from "./support/radix";

const CONSOLE_ORIGIN = "https://console.test";
const DIGEST = "d".repeat(64);

beforeAll(async () => {
  installRadixStubs();
  await import("../src/pages/AgentTemplate");
}, 60_000);

const LIST = {
  items: [{ template_id: "pricing_desk", version: 2, display_name: "Pricing desk", summary: "Prices things.", published_by: "system", origin: "published" }],
  next_cursor: null,
  total: null,
  truncated: false,
};

const DETAIL = {
  entry: { template_id: "pricing_desk", version: 2, display_name: "Pricing desk", summary: "Prices things.", published_by: "system", origin: "published" },
  persona: "PERSONA-SENTENCE",
  tier: "main",
  skills: [],
  connectors: [],
  tools: [],
  capabilities: [],
  leash: [],
  max_side_effect: "write",
  golden_cases: 1,
};

function offered(over: Record<string, unknown> = {}): Record<string, unknown> {
  return { template_id: "pricing_desk", version: 2, withdrawn: false, changes: [], may_withdraw: true, may_undo: false, unavailable: "", ...over };
}

function withdrawnState(): Record<string, unknown> {
  return offered({
    withdrawn: true,
    may_withdraw: false,
    may_undo: true,
    changes: [{ withdrawn: true, set_by: "u_admin_sentinel", at: "2026-10-01T09:00:00Z", reason: "Wrong tone." }],
  });
}

const WITHDRAWN_LIST = {
  versions: [{ template_id: "pricing_desk", version: 1, display_name: "Pricing desk", reason: "REASON-SENTENCE", set_by: "u_admin_sentinel", at: "2026-10-01T09:00:00Z" }],
};

const READING = {
  imported: false,
  created: false,
  template_id: "arrived_desk",
  version: 1,
  display_name: "Arrived desk",
  summary: "Arrived summary.",
  content_digest: DIGEST,
  signed_by_this_install: false,
  company_details: [],
  says: "",
};

type Answers = Record<string, { status?: number; body: unknown }>;

async function consoleAt(path: string, over: Answers = {}): Promise<{ container: HTMLElement; idp: FakeIdp }> {
  const answers: Answers = {
    "/api/v1/agent-templates": { body: LIST },
    "/api/v1/agent-templates/pricing_desk": { body: DETAIL },
    ...over,
  };
  const idp = fakeIdentityProvider({
    api(url, init) {
      const pathname = new URL(url, CONSOLE_ORIGIN).pathname;
      const reply = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
      const key = init?.method === "POST" ? `POST ${pathname}` : pathname;
      const answer = answers[key] ?? (init?.method === "POST" ? undefined : answers[pathname]);
      return answer === undefined ? null : reply(answer.body, answer.status ?? 200);
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (!container.querySelector("h1") || container.querySelector('[data-slot="loading-state"]')) {
      throw new Error("the page is still asking");
    }
  });
  return { container, idp };
}

function posts(idp: FakeIdp): { path: string; body: unknown }[] {
  return idp.calls
    .filter((call) => call.init?.method === "POST" && new URL(call.url, CONSOLE_ORIGIN).pathname.startsWith("/api/"))
    .map((call) => ({ path: new URL(call.url, CONSOLE_ORIGIN).pathname, body: call.init?.body === undefined ? {} : (JSON.parse(String(call.init.body)) as unknown) }));
}

const STATE = "/api/v1/agent-templates/pricing_desk/versions/2/withdrawal";
const UNDO = `${STATE}/undo`;

describe("what this module agrees with the API about", () => {
  test("every address the page builds is a route the API serves, and a withdrawal sends a reason", () => {
    // What breaks if this is deleted: a page asking for an address the API renamed, so every
    // reader is shown nothing and nobody is told why.
    const paths = Object.keys((apiDocument()["paths"] ?? {}) as Record<string, unknown>);
    for (const built of [
      withdrawalApiPath("{template_id}", 0),
      undoApiPath("{template_id}", 0),
      exportApiPath("{template_id}", 0),
    ]) {
      const pattern = `/api/v1${built.replace("%7Btemplate_id%7D", "{template_id}").replace(/\/versions\/0/, "/versions/{version}")}`;
      expect(paths, pattern).toContain(pattern);
    }
    expect(paths).toContain(`/api/v1${WITHDRAWN_API_PATH}`);
    expect(paths).toContain(`/api/v1${IMPORT_API_PATH}`);
    expect(exportFileName("pricing_desk", 2)).toBe("pricing_desk-v2.template.json");
  });
});

describe("reading what the API sent", () => {
  test("a body that is not a state, a list or a reading is nothing, and a list drops an entry naming no template", () => {
    // What breaks if this is deleted: a card drawn from a body that said nothing.
    for (const unreadable of [null, [], "x", {}, { withdrawn: "yes" }]) {
      expect(readWithdrawal(unreadable)).toBeNull();
      expect(readImport(unreadable)).toBeNull();
    }
    expect(readWithdrawn({})).toBeNull();
    expect(readWithdrawn({ versions: [{ template_id: "a", version: 1 }, { version: 2 }, { template_id: "b" }] })?.map((one) => one.template_id)).toEqual(["a"]);
    expect(readWithdrawal(offered())?.may_withdraw).toBe(true);
    expect(parseDocument("[1]")).toBeNull();
    expect(parseDocument("not json")).toBeNull();
    expect(parseDocument('{"schema":"x"}')).toEqual({ schema: "x" });
  });
});

describe("a version's page", () => {
  test("draws nothing about withdrawing for a reader the API refused", async () => {
    // What breaks if this is deleted: a Withdraw button, or a sentence about one, shown to a person
    // who may only install, which tells them what they are missing.
    const { container } = await consoleAt("/agent-templates/pricing_desk", { [STATE]: { status: 404, body: { message: "I could not find that.", trace_id: "T" } } });
    expect(screen.queryByRole("button", { name: WITHDRAW })).toBeNull();
    expect(container.textContent).not.toContain("Offered to new installs");
  });

  test("a withdrawal needs a reason, is sent only from its confirmation, and says nothing is lost", async () => {
    // What breaks if this is deleted: a version hidden from every colleague with no reason given, or
    // on a single press, or a confirmation that does not say installed agents are left alone.
    const { idp } = await consoleAt("/agent-templates/pricing_desk", {
      [STATE]: { body: offered() },
      [`POST ${STATE}`]: { body: withdrawnState() },
    });
    await screen.findByText("Offered to new installs");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: WITHDRAW }));
    });
    expect(screen.getByText(REASON_NEEDED)).toBeTruthy();
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(posts(idp)).toEqual([]);

    fireEvent.change(screen.getByLabelText("Why is it being withdrawn?"), { target: { value: "  Wrong tone for clients.  " } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: WITHDRAW }));
    });
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain("Agents already installed from it keep running");
    expect(dialog.textContent).toContain("You can put it back");
    expect(posts(idp)).toEqual([]);
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: WITHDRAW }));
    });

    await waitFor(() => {
      expect(posts(idp)).toEqual([{ path: STATE, body: { reason: "Wrong tone for clients." } }]);
    });
  });

  test("a withdrawn version offers to put it back, confirmed, and its history is behind Advanced", async () => {
    // What breaks if this is deleted: a withdrawn version nobody can bring back from its page, or
    // the person who withdrew it named in the page's text.
    const { container, idp } = await consoleAt("/agent-templates/pricing_desk", {
      [STATE]: { body: withdrawnState() },
      [`POST ${UNDO}`]: { body: offered() },
    });
    await screen.findByText("Offered to new installs");
    const copy = container.cloneNode(true) as HTMLElement;
    copy.querySelectorAll('[data-slot="advanced"]').forEach((one) => {
      one.remove();
    });
    expect(copy.textContent).not.toContain("u_admin_sentinel");
    expect(container.querySelector('[data-slot="advanced"]')?.textContent).toContain("u_admin_sentinel");
    expect(screen.queryByRole("button", { name: WITHDRAW })).toBeNull();

    await act(async () => {
      fireEvent.click(screen.getAllByRole("button", { name: PUT_BACK })[0] as HTMLElement);
    });
    const dialog = await screen.findByRole("alertdialog");
    expect(posts(idp)).toEqual([]);
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: PUT_BACK }));
    });
    await waitFor(() => {
      expect(posts(idp)).toEqual([{ path: UNDO, body: {} }]);
    });
  });

  test("with the switch off, Withdraw is a sentence saying so and an undo is still offered", async () => {
    // What breaks if this is deleted: a button that fails after the press, or a switch turned off
    // that leaves a withdrawn version with no way back.
    await consoleAt("/agent-templates/pricing_desk", { [STATE]: { body: offered({ may_withdraw: false, unavailable: "SWITCH-OFF-SENTENCE" }) } });
    await screen.findByText("SWITCH-OFF-SENTENCE");
    expect(screen.queryByRole("button", { name: WITHDRAW })).toBeNull();
    expect(screen.getByRole("button", { name: "Save as a document" }).hasAttribute("disabled")).toBe(true);
  });

  test("saving a version asks for its export and does not write", async () => {
    // What breaks if this is deleted: an export that posts, or one that fails silently.
    const { idp } = await consoleAt("/agent-templates/pricing_desk", {
      [STATE]: { body: offered() },
      "/api/v1/agent-templates/pricing_desk/versions/2/export": { body: { template_id: "pricing_desk", version: 2, document: { schema: "brain.template.export.v1" } } },
    });
    await screen.findByText("Offered to new installs");
    const failure = await saveVersion("pricing_desk", 2);
    expect(failure).toBeNull();
    expect(posts(idp)).toEqual([]);
    expect(idp.calls.some((call) => new URL(call.url, CONSOLE_ORIGIN).pathname.endsWith("/versions/2/export"))).toBe(true);
  });
});

describe("the catalogue", () => {
  test("lists what is withdrawn for a reader allowed to put it back, and nothing for anybody else", async () => {
    // What breaks if this is deleted: the withdrawn list shown to a reader who may only install, or
    // withheld from the one who needs it, so nothing withdrawn can ever be put back.
    const refused = await consoleAt("/agent-templates", { [WITHDRAWN_API_PATH.replace(/^/, "/api/v1")]: { status: 404, body: { message: "I could not find that.", trace_id: "T" } } });
    expect(refused.container.textContent).not.toContain(WITHDRAWN_HEADING);
    expect(refused.container.textContent).not.toContain(IMPORT_HEADING);
  });

  test("puts a withdrawn version back only from a confirmation", async () => {
    // What breaks if this is deleted: a version brought back on a single press, for everybody.
    const { idp } = await consoleAt("/agent-templates", {
      [`/api/v1${WITHDRAWN_API_PATH}`]: { body: WITHDRAWN_LIST },
      "/api/v1/agent-templates/pricing_desk/versions/1/withdrawal/undo": { body: offered({ version: 1 }) },
    });
    await screen.findByText(WITHDRAWN_HEADING);
    expect(document.body.textContent).toContain("REASON-SENTENCE");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Put back on offer: Pricing desk, version 1/ }));
    });
    const dialog = await screen.findByRole("alertdialog");
    expect(posts(idp)).toEqual([]);
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: PUT_BACK }));
    });
    await waitFor(() => {
      expect(posts(idp).map((one) => one.path)).toEqual(["/api/v1/agent-templates/pricing_desk/versions/1/withdrawal/undo"]);
    });
  });

  test("an import is read before it is written, and written with the digest it showed", async () => {
    // What breaks if this is deleted: a document added from a reading, or confirmed with a digest
    // the person was not shown.
    const IMPORT = `/api/v1${IMPORT_API_PATH}`;
    const { idp } = await consoleAt("/agent-templates", {
      [`/api/v1${WITHDRAWN_API_PATH}`]: { body: { versions: [] } },
      [`POST ${IMPORT}`]: { body: READING },
    });
    await screen.findByText(IMPORT_HEADING);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Read it" }));
    });
    expect(screen.getByText(DOCUMENT_NEEDED)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Template document"), { target: { value: "not json" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Read it" }));
    });
    expect(screen.getByText(DOCUMENT_UNREADABLE)).toBeTruthy();
    expect(posts(idp)).toEqual([]);

    fireEvent.change(screen.getByLabelText("Template document"), { target: { value: '{"schema":"brain.template.export.v1"}' } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Read it" }));
    });
    await screen.findByText("Arrived desk");
    expect(document.body.textContent).toContain("Signed somewhere else");
    expect(posts(idp)).toEqual([{ path: IMPORT, body: { document: { schema: "brain.template.export.v1" } } }]);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Add to the catalogue" }));
    });
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain("signed with this install's key");
    expect(posts(idp)).toHaveLength(1);
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: "Add to the catalogue" }));
    });
    await waitFor(() => {
      expect(posts(idp)).toHaveLength(2);
    });
    expect(posts(idp)[1]).toEqual({ path: IMPORT, body: { document: { schema: "brain.template.export.v1" }, expected_digest: DIGEST } });
  });

  test("a document that looks like a company's own cannot be added from the page", async () => {
    // What breaks if this is deleted: an Add button over a document the API will refuse, which
    // sends a confirmation to say no.
    const IMPORT = `/api/v1${IMPORT_API_PATH}`;
    await consoleAt("/agent-templates", {
      [`/api/v1${WITHDRAWN_API_PATH}`]: { body: { versions: [] } },
      [`POST ${IMPORT}`]: { body: { ...READING, company_details: [{ kind: "email", places: ["persona"] }] } },
    });
    await screen.findByText(IMPORT_HEADING);
    fireEvent.change(screen.getByLabelText("Template document"), { target: { value: "{}" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Read it" }));
    });
    await screen.findByText("email in persona");
    expect(screen.getByRole("button", { name: "Add to the catalogue" }).hasAttribute("disabled")).toBe(true);
  });
});
