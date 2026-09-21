/**
 * The Requirement checks screen, and the Audit screen's verification card.
 *
 * Mounted directly on a memory router at each address, for the reason `tests/sessions-page.test.tsx`
 * gives. The failures worth testing look like the screen working: a requirement nobody checked drawn
 * as passed, a check sent with no note, a recorded check that never reaches the table, and a walk of
 * the ledger drawn as a tick when only the chain was checked.
 *
 * Task ids: M1.8.8, M2.3.2, M5.6.5, M24.3.6, M24.1.2, M24.3.3
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { READING_CHECKS, NOT_CHECKED } from "../src/pages/RequirementChecks";
import { DRAFT_PROBLEMS } from "../src/pages/requirementChecksQuery";
import { CHECK_HEAD_LABEL, WALK_LABEL } from "../src/pages/Audit";
import { COMPLETENESS_WORDS, HEAD_PROBLEMS } from "../src/pages/auditQuery";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";

const CHECKS = "/api/v1/requirements/checks";
const VERIFY = "/api/v1/audit/verification";
const CONSOLE_ORIGIN = "https://console.test";
const TOLD = "A check is what a person saw this install do.";
const CAVEAT = "no anchor was checked, so this run proves continuity and not completeness";

beforeAll(async () => {
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
      { id: "ARC-A-001", requirement: "Each person sees only what they are entitled to see.", source: "s", latest },
      { id: "DEC-30", requirement: "Every personnel read is written down.", source: "s", latest: null },
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
      return null;
    },
    sent,
    READING_CHECKS,
  );
}

describe("the requirement checks screen", () => {
  test("every area with where it stands, and one area's requirements in the owner's words, unchecked", async () => {
    // What breaks if this is deleted: an area's standing drops off, or a requirement nobody checked
    // is drawn with somebody else's check.
    const container = await checksPage([]);
    const areas = container.querySelector('[aria-label="Areas of the register"]')?.textContent ?? "";
    expect(areas).toContain("Permissions");
    expect(areas).toContain("0 passed, 0 failed, 2 not yet checked, of 2, for M1.8.8");
    expect(areas).toContain("Models");
    const table = container.querySelector('[aria-label="Requirements in this area"]')?.textContent ?? "";
    expect(table).toContain("Each person sees only what they are entitled to see.");
    expect(table).toContain(NOT_CHECKED);
    expect(container.textContent).toContain(TOLD);
  });

  test("a check sent blank is told what to fill in and nothing is sent", async () => {
    // What breaks if this is deleted: a check with no requirement, no outcome or no note reaches the
    // API, and the one record of what a person saw says nothing.
    const sent: Sent[] = [];
    const container = await checksPage(sent);
    fireEvent.submit(container.querySelector('form[aria-label="Record a check"]') as HTMLFormElement);
    await waitFor(() => expect(container.textContent).toContain(DRAFT_PROBLEMS.note));
    expect(container.textContent).toContain(DRAFT_PROBLEMS.requirementId);
    expect(container.textContent).toContain(DRAFT_PROBLEMS.outcome);
    expect(sent.filter((one) => one.method !== "GET")).toEqual([]);
  });

  test("a check filled in is sent as the API takes it and the table shows it afterwards", async () => {
    // What breaks if this is deleted: the form sends a different body from the one the route
    // takes, or a recorded check never reaches the table the person is looking at.
    const sent: Sent[] = [];
    const container = await checksPage(sent, RECORDED);
    const form = container.querySelector('form[aria-label="Record a check"]') as HTMLFormElement;
    const [requirement, outcome] = [...form.querySelectorAll("select")];
    fireEvent.change(requirement as HTMLSelectElement, { target: { value: "ARC-A-001" } });
    fireEvent.change(outcome as HTMLSelectElement, { target: { value: "passed" } });
    fireEvent.change(form.querySelector("textarea") as HTMLTextAreaElement, {
      target: { value: "  Asked as Priya and was refused the salary.  " },
    });
    fireEvent.submit(form);
    await waitFor(() => expect(container.textContent).toContain("Passed by u_admin"));
    const posted = sent.filter((one) => one.method === "POST");
    expect(posted).toEqual([
      {
        method: "POST",
        path: CHECKS,
        body: { requirement_id: "ARC-A-001", outcome: "passed", note: "Asked as Priya and was refused the salary." },
      },
    ]);
    expect(container.textContent).toContain("release aaaaaaa");
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
