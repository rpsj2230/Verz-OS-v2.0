/**
 * The Requirement checks page on the page kit, and the Audit screen's verification card.
 *
 * Mounted directly on a memory router at each address, for the reason `tests/sessions-page.test.tsx`
 * gives. The failures worth testing look like the screen working: a requirement nobody checked drawn
 * as passed, evidence from a check that proves another leaf, a check sent with no note, a recorded
 * check that never reaches the row, a person drawn as their reference, and a walk of the ledger drawn
 * as a tick when only the chain was checked.
 *
 * Task ids: M1.8.8, M2.3.2, M5.6.5, M24.3.6, M24.1.2, M24.3.3
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { NOTHING_MATCHES } from "../src/components/ListControls";
import { READING_CHECKS, NOT_CHECKED, RECORD_LABEL, RECORDED as RECORDED_SENTENCE } from "../src/pages/requirement-checks/RequirementChecksPage";
import { DRAFT_PROBLEMS } from "../src/pages/requirementChecksQuery";
import { CHECK_HEAD_LABEL, WALK_LABEL } from "../src/pages/Audit";
import { COMPLETENESS_WORDS, HEAD_PROBLEMS } from "../src/pages/auditQuery";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";
import { installRadixStubs } from "./support/radix";

const CHECKS = "/api/v1/requirements/checks";
const VERIFY = "/api/v1/audit/verification";
const CONSOLE_ORIGIN = "https://console.test";
const TOLD = "A check is what a person saw this install do.";
const CAVEAT = "no anchor was checked, so this run proves continuity and not completeness";

beforeAll(async () => {
  installRadixStubs();
  await import("../src/pages/RequirementChecks");
  await import("../src/pages/Audit");
}, 60_000);

interface Sent {
  readonly method: string;
  readonly path: string;
  readonly body: unknown;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

function checksBody(latest: unknown = null): unknown {
  return {
    areas: [
      { area: "Permissions", proves: "M1.8.8", requirements: 2, passed: latest === null ? 0 : 1, failed: 0, unchecked: latest === null ? 2 : 1 },
      { area: "Models", proves: "M5.6.5", requirements: 1, passed: 0, failed: 0, unchecked: 1 },
    ],
    area: "Permissions",
    requirements: [
      {
        id: "ARC-A-001",
        requirement: "Each person sees only what they are entitled to see.",
        source: "s",
        latest,
        proof: ["M1.8.8"],
        evidence: [
          {
            name: "grant_is_refused",
            sentence: "A refusal names nothing.",
            leaves: ["M1.8.8"],
            outcome: "passed",
            checked_at: "2019-03-04T09:00:05+00:00",
            reason: "",
          },
        ],
      },
      { id: "DEC-30", requirement: "Every personnel read is written down.", source: "s", latest: null, proof: ["M24.3.6"], evidence: [] },
    ],
    release_commit: "a".repeat(40),
    told: TOLD,
  };
}

const RECORDED = {
  requirement_id: "ARC-A-001",
  outcome: "passed",
  checked_by: "u_admin",
  checked_at: "2019-03-04T09:00:00Z",
  release_commit: "a".repeat(40),
  note: "Asked as Priya and was refused the salary.",
};

async function mount(
  address: string,
  element: JSX.Element,
  answer: (url: URL, init: RequestInit | undefined) => Response | null,
  sent: Sent[],
  reading: string,
): Promise<HTMLElement> {
  const idp = fakeIdentityProvider({
    api(url, init) {
      const parsed = new URL(url, CONSOLE_ORIGIN);
      sent.push({
        method: init?.method ?? "GET",
        path: parsed.pathname,
        body: init?.body === undefined ? null : JSON.parse(String(init.body)),
      });
      return answer(parsed, init);
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const router = createMemoryRouter([{ path: address, element }], { initialEntries: [address] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (reading !== "" && container.textContent?.includes(reading)) {
      throw new Error("still reading");
    }
  });
  return container;
}

async function checksPage(sent: Sent[], afterRecord: unknown = null): Promise<HTMLElement> {
  const { RequirementChecks } = await import("../src/pages/RequirementChecks");
  let recorded = false;
  return mount(
    "/requirement-checks",
    <RequirementChecks />,
    (url, init) => {
      if (url.pathname === CHECKS && (init?.method ?? "GET") === "POST") {
        recorded = true;
        return json(RECORDED, 201);
      }
      if (url.pathname === CHECKS) {
        return json(checksBody(recorded ? afterRecord : null));
      }
      if (url.pathname === "/api/v1/govern/directory/u_admin") {
        return json({ person: { principal_id: "u_admin", display_name: "Ada Admin", standing: "live", packs: [] }, placements: {}, held: [] });
      }
      return null;
    },
    sent,
    READING_CHECKS,
  );
}

function drawerFor(container: HTMLElement, id: string): HTMLElement {
  const opener = [...container.querySelectorAll("button")].find((one) => one.getAttribute("aria-label") === `${RECORD_LABEL} a check of ${id}`);
  if (opener === undefined) {
    throw new Error(`No record control for ${id}.`);
  }
  fireEvent.click(opener);
  const found = document.body.querySelector<HTMLElement>('[data-slot="drawer"]');
  if (found === null) {
    throw new Error("The drawer did not open.");
  }
  return found;
}

describe("the requirement checks page", () => {
  test("where the register and each area stand, and one area's requirements with their proof and evidence", async () => {
    // What breaks if this is deleted: an area's standing drops off, a requirement nobody checked is
    // drawn with somebody else's check, or the install's own evidence is missing from the row.
    const container = await checksPage([]);
    const register = container.querySelector('[aria-label="The whole register"]')?.textContent ?? "";
    expect(register).toContain("Requirements3");
    expect(register).toContain("To check3");
    const areas = container.querySelector("table")?.closest('[data-slot="section-card"]');
    expect(areas).not.toBeNull();
    const byArea = [...container.querySelectorAll('[data-slot="section-card"]')].find((one) => one.querySelector("h2")?.textContent === "By area");
    expect(byArea?.textContent).toContain("Permissions");
    expect(byArea?.textContent).toContain("0 of 2");
    expect(byArea?.textContent).toContain("Models");
    const rows = [...container.querySelectorAll('[data-slot="section-card"]')]
      .find((one) => one.querySelector("h2")?.textContent === "Permissions")
      ?.querySelectorAll("tbody tr");
    const first = rows?.[0]?.textContent ?? "";
    expect(first).toContain("Each person sees only what they are entitled to see.");
    expect(first).toContain("M1.8.8");
    expect(first).toContain("Passed");
    expect(first).toContain(NOT_CHECKED);
    expect(rows?.[1]?.textContent).toContain("No automatic check");
  });

  test("a check sent blank from the drawer is told what to fill in and nothing is sent", async () => {
    // What breaks if this is deleted: a check with no outcome or no note reaches the API, and the one
    // record of what a person saw says nothing.
    const sent: Sent[] = [];
    const container = await checksPage(sent);
    const drawer = drawerFor(container, "ARC-A-001");
    expect(drawer.textContent).toContain("A refusal names nothing.");
    expect(drawer.textContent).toContain(TOLD);
    fireEvent.submit(drawer.querySelector('form[aria-label="Record a check"]') as HTMLFormElement);
    await waitFor(() => expect(drawer.textContent).toContain(DRAFT_PROBLEMS.note));
    expect(drawer.textContent).toContain(DRAFT_PROBLEMS.outcome);
    expect(sent.filter((one) => one.method !== "GET")).toEqual([]);
  });

  test("a check filled in is sent as the API takes it and the row shows it afterwards, by name", async () => {
    // What breaks if this is deleted: the drawer sends a different body from the one the route
    // takes, a recorded check never reaches the row, or the recorder is drawn as a reference.
    const sent: Sent[] = [];
    const container = await checksPage(sent, RECORDED);
    const drawer = drawerFor(container, "ARC-A-001");
    const form = drawer.querySelector('form[aria-label="Record a check"]') as HTMLFormElement;
    fireEvent.click(form.querySelector('input[value="passed"]') as HTMLInputElement);
    fireEvent.change(form.querySelector("textarea") as HTMLTextAreaElement, {
      target: { value: "  Asked as Priya and was refused the salary.  " },
    });
    fireEvent.submit(form);
    await waitFor(() => expect(container.textContent).toContain(RECORDED_SENTENCE));
    expect(sent.filter((one) => one.method === "POST")).toEqual([
      {
        method: "POST",
        path: CHECKS,
        body: { requirement_id: "ARC-A-001", outcome: "passed", note: "Asked as Priya and was refused the salary." },
      },
    ]);
    await waitFor(() => expect(container.querySelector("tbody tr")?.textContent).toContain("Passed"));
    expect(container.textContent).not.toContain("u_admin");
    const reopened = drawerFor(container, "ARC-A-001");
    await waitFor(() => expect(reopened.textContent).toContain("by Ada Admin"));
    const advanced = reopened.querySelector('[data-slot="advanced"]')?.textContent ?? "";
    expect(advanced).toContain("u_admin");
    expect((reopened.textContent ?? "").replace(advanced, "")).not.toContain("u_admin");
  });

  test("the standing and the words narrow the area's rows, and clearing them brings every row back", async () => {
    // What breaks if this is deleted: a narrowing that hides a row it should show, or one that cannot
    // be undone, so a requirement looks missing from the register.
    const container = await checksPage([]);
    const narrowing = container.querySelector('form[aria-label="Narrow the requirements"]') as HTMLFormElement;
    const standing = [...narrowing.querySelectorAll("select")].find((one) => one.querySelector('option[value="failed"]') !== null) as HTMLSelectElement;
    fireEvent.change(standing, { target: { value: "failed" } });
    await waitFor(() => expect(container.textContent).toContain(NOTHING_MATCHES));
    fireEvent.change(standing, { target: { value: "unchecked" } });
    await waitFor(() => expect(container.querySelectorAll("tbody tr").length).toBeGreaterThan(2));
    fireEvent.change(narrowing.querySelector('input[type="search"]') as HTMLInputElement, { target: { value: "personnel" } });
    await waitFor(() => {
      const rows = [...container.querySelectorAll('[data-slot="section-card"]')]
        .find((one) => one.querySelector("h2")?.textContent === "Permissions")
        ?.querySelectorAll("tbody tr");
      expect([...(rows ?? [])].map((one) => one.textContent ?? "").join(" ")).toContain("DEC-30");
      expect(rows?.length).toBe(1);
    });
  });
});

describe("the audit screen's verification card", () => {
  async function auditPage(sent: Sent[], verification: unknown): Promise<HTMLElement> {
    const { Audit } = await import("../src/pages/Audit");
    return mount(
      "/audit",
      <Audit />,
      (url) => {
        if (url.pathname === VERIFY) {
          return json(verification);
        }
        if (url.pathname === "/api/v1/audit") {
          return json({ items: [], next_cursor: null, order: "newest", actions: [], subject_kinds: [], actors: [] });
        }
        return null;
      },
      sent,
      "Reading the ledger.",
    );
  }

  const WALKED = {
    checked_at: "2019-03-04T09:00:00Z",
    entries_walked: 80,
    first_seq: 0,
    last_seq: 79,
    head: "b".repeat(64),
    continuous: true,
    break_found: null,
    completeness: "unanchored",
    published: null,
    caveats: [CAVEAT],
  };

  test("walking the ledger says what held and what was not checked, in words and never as a tick", async () => {
    // What breaks if this is deleted: the card drops the caveat and a walk of the chain reads as a
    // ledger proved complete, which is the reading brain.audit.verify exists to prevent.
    const sent: Sent[] = [];
    const container = await auditPage(sent, WALKED);
    const walk = [...container.querySelectorAll("button")].find((one) => one.textContent === WALK_LABEL);
    fireEvent.click(walk as HTMLButtonElement);
    await waitFor(() => expect(container.textContent).toContain(CAVEAT));
    expect(container.textContent).toContain("No entry in the ledger was edited, removed or reordered.");
    expect(container.textContent).toContain(COMPLETENESS_WORDS.unanchored);
    expect(container.textContent).toContain("Entries 0 to 79");
    expect(container.textContent).not.toMatch(/verified/i);
    expect(sent.filter((one) => one.method === "POST")).toEqual([{ method: "POST", path: VERIFY, body: {} }]);
  });

  test("a published head half copied is told what is missing and nothing is sent", async () => {
    // What breaks if this is deleted: a head with no digest reaches the API as a check of nothing.
    const sent: Sent[] = [];
    const container = await auditPage(sent, WALKED);
    const form = container.querySelector('form[aria-label="The last published head"]') as HTMLFormElement;
    fireEvent.change(form.querySelectorAll("input")[0] as HTMLInputElement, { target: { value: "79" } });
    fireEvent.submit(form);
    await waitFor(() => expect(container.textContent).toContain(HEAD_PROBLEMS.head));
    expect(container.textContent).toContain(HEAD_PROBLEMS.takenAt);
    expect(container.textContent).not.toContain(HEAD_PROBLEMS.seq);
    expect(sent.filter((one) => one.method === "POST")).toEqual([]);
  });

  test("a published head the ledger no longer holds is said plainly", async () => {
    // What breaks if this is deleted: a truncated ledger is drawn with the same words as a whole
    // one, and the check M24.3.3 asks for tells nobody anything.
    const sent: Sent[] = [];
    const container = await auditPage(sent, { ...WALKED, completeness: "anchor_missing", caveats: ["removed"] });
    const form = container.querySelector('form[aria-label="The last published head"]') as HTMLFormElement;
    const [seq, head, takenAt] = [...form.querySelectorAll("input")];
    fireEvent.change(seq as HTMLInputElement, { target: { value: "90" } });
    fireEvent.change(head as HTMLInputElement, { target: { value: "c".repeat(64) } });
    fireEvent.change(takenAt as HTMLInputElement, { target: { value: "2019-03-04T09:00:00Z" } });
    const submit = [...form.querySelectorAll("button")].find((one) => one.textContent === CHECK_HEAD_LABEL);
    fireEvent.click(submit as HTMLButtonElement);
    await waitFor(() => expect(container.textContent).toContain(COMPLETENESS_WORDS.anchor_missing));
    expect(sent.filter((one) => one.method === "POST")).toEqual([
      {
        method: "POST",
        path: VERIFY,
        body: { published: { seq: 90, head: "c".repeat(64), taken_at: "2019-03-04T09:00:00.000Z" } },
      },
    ]);
  });
});
