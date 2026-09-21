/**
 * The Compliance screen: who each sensitive topic is routed to and the naming of a person, the
 * processing register, and breach cases opened, moved step by step and closed.
 *
 * Mounted directly on a memory router at its own address, for the reason
 * `tests/sessions-page.test.tsx` gives. The failures worth testing are the ones that look like the
 * screen working: a write sent without its confirmation, a reference that fails the route's own
 * pattern only after it was sent, an estimate opened without its earliest moment, a close offered
 * on a case the API says is not closable, and a suppressed tally drawn as a number.
 *
 * **What each form sends is read against the route's own request body**, so a key or a pattern this
 * console invented is a failure here rather than a 422 in front of the person recording a breach.
 *
 * Task ids: M24.2.2, M24.2.3, M24.2.4
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  ASSESS_FORM_LABEL,
  ASSESS_LABEL,
  CLOSE_LABEL,
  COMMISSION_FORM_LABEL,
  COMMISSION_LABEL,
  EXCEPTION_FORM_LABEL,
  INDIVIDUALS_FORM_LABEL,
  NAME_FORM_LABEL,
  NAME_LABEL,
  NOBODY_NAMED,
  NOTHING_CONNECTED,
  NO_CASES,
  OPENING,
  OPEN_FORM_LABEL,
  OPEN_LABEL,
  READING_COMPLIANCE,
} from "../src/pages/Compliance";
import {
  IDENTIFIER_PATTERN,
  assessBody,
  exceptionBody,
  nameBody,
  obligationSentence,
  openBody,
  openProblems,
  tallySentence,
  type Breach,
  type BreachesAnswer,
  type RegisterAnswer,
  type TopicsAnswer,
} from "../src/pages/complianceQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { declaredPropertySchema, declaredRequestBodySchema } from "./support/openapi";

const CONSOLE_ORIGIN = "https://console.test";
const TOPICS_OPERATION = "/api/v1/govern/compliance/topics";
const REGISTER_OPERATION = "/api/v1/govern/compliance/register";
const BREACHES_OPERATION = "/api/v1/govern/compliance/breaches";
const CASE = "11111111-1111-4111-8111-111111111111";

beforeAll(async () => {
  await import("../src/pages/Compliance");
}, 60_000);

function topics(overrides: Partial<TopicsAnswer> = {}): TopicsAnswer {
  return {
    topics: [
      {
        topic: "grievance",
        label: "Grievances",
        named: { principal_id: "u_hr", named_by: "u_admin", named_at: "2019-03-04T09:00:00Z" },
      },
      { topic: "salary", label: "Salary", named: null },
    ],
    tally: { period: "2019-03", total: null, by_topic: null, suppressed: true },
    referral: "REFERRAL-SENTENCE",
    routing: "ROUTING-SENTENCE",
    ...overrides,
  };
}

function register(overrides: Partial<RegisterAnswer> = {}): RegisterAnswer {
  return {
    connectors: [
      {
        connector: "xero",
        label: "Xero",
        connected_by: "u_admin",
        connected_at: "2019-03-04T09:00:00Z",
        transport: "https",
        version: "2",
        entities: [{ entity: "invoice", tier: "projected", fields: ["amount", "contact"], classes: ["financial"] }],
        categories: ["financial"],
        write_capable: false,
        records_read: 42,
        documents_read: null,
        last_read_at: "2019-03-04T10:00:00Z",
        problem: "PROBLEM-SENTENCE",
      },
    ],
    counts: "COUNTS-SENTENCE",
    ...overrides,
  };
}

function breach(overrides: Partial<Breach> = {}): Breach {
  return {
    case_id: CASE,
    became_aware_at: "2019-03-04T09:00:00Z",
    clock_starts_at: "2019-03-04T08:00:00Z",
    awareness_basis: "estimated",
    awareness_source: "staff_report",
    recorded_by: "u_dpo",
    evidence_reference: "INC-7",
    assessed_at: null,
    significant_harm: null,
    affected_count: null,
    outcome: null,
    commission_notified_at: null,
    individuals_notified_at: null,
    exception_ground: null,
    closed_at: null,
    closed_by: null,
    obligations: [
      {
        kind: "assess",
        basis: "guideline",
        due_before: "2019-04-03T08:00:00Z",
        satisfied: false,
        overdue: true,
        satisfied_late: false,
        out_of_order: false,
      },
    ],
    findings: ["FINDING-SENTENCE"],
    closable: false,
    ...overrides,
  };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

interface Stand {
  topics?: TopicsAnswer;
  register?: RegisterAnswer;
  breaches?: BreachesAnswer;
}

async function mount(stand: Stand = {}): Promise<{ container: HTMLElement; idp: FakeIdp }> {
  const cases = stand.breaches ?? { cases: [breach()], closing: "CLOSING-SENTENCE" };
  const idp = fakeIdentityProvider({
    api(url, init) {
      const path = new URL(url, CONSOLE_ORIGIN).pathname;
      if (init?.method === "PUT") {
        return json({ principal_id: "u_new", named_by: "u_admin", named_at: "2019-03-05T10:00:00Z" });
      }
      if (init?.method === "POST") {
        return json(breach({ case_id: "22222222-2222-4222-8222-222222222222" }));
      }
      if (path === TOPICS_OPERATION) {
        return json(stand.topics ?? topics());
      }
      if (path === REGISTER_OPERATION) {
        return json(stand.register ?? register());
      }
      if (path === BREACHES_OPERATION) {
        return json(cases);
      }
      return null;
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { Compliance } = await import("../src/pages/Compliance");
  const router = createMemoryRouter([{ path: "/compliance", element: <Compliance /> }], {
    initialEntries: ["/compliance"],
  });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (container.textContent?.includes(READING_COMPLIANCE) || !container.querySelector("h2")) {
      throw new Error("still reading");
    }
  });
  return { container, idp };
}

function writes(idp: FakeIdp): { method: string; path: string; body: unknown }[] {
  return idp.calls
    .filter(
      (call) =>
        call.init?.method !== undefined &&
        call.init.method !== "GET" &&
        new URL(call.url, CONSOLE_ORIGIN).pathname.startsWith("/api/"),
    )
    .map((call) => ({
      method: call.init?.method ?? "",
      path: new URL(call.url, CONSOLE_ORIGIN).pathname,
      body: call.init?.body === undefined ? undefined : (JSON.parse(String(call.init.body)) as unknown),
    }));
}

function formNamed(container: HTMLElement, label: string): HTMLFormElement {
  const found = container.querySelector(`form[aria-label="${label}"]`);
  if (found === null) {
    throw new Error(`no form labelled ${label}`);
  }
  return found as HTMLFormElement;
}

function field(form: Element, label: string): HTMLInputElement | HTMLSelectElement {
  const found = [...form.querySelectorAll("label")].find((one) => one.textContent?.startsWith(label));
  const control = found?.querySelector("input, select, textarea");
  if (control === null || control === undefined) {
    throw new Error(`no field labelled ${label}`);
  }
  return control as HTMLInputElement;
}

function confirm(container: HTMLElement, label: string): void {
  fireEvent.click(
    [...container.querySelectorAll(".confirm button")].find((one) => one.textContent === label) as HTMLButtonElement,
  );
}

function button(container: HTMLElement, name: string): HTMLButtonElement | null {
  return (
    ([...container.querySelectorAll("button")].find((one) => one.textContent === name) as HTMLButtonElement | undefined) ??
    null
  );
}

describe("what the compliance screen agrees with the API about", () => {
  test("every body is the route's own, and every reference is checked against the route's pattern", () => {
    // What breaks if this is deleted: a pattern here drifts from `brain.audit.ledger.IDENTIFIER`, or
    // a key is renamed on one side, and a write the page accepted is refused with a 422 after the
    // person confirmed it.
    const keys = (path: string, method: string) =>
      Object.keys(declaredRequestBodySchema(path, method)["properties"] as object).sort();
    expect(keys(`${TOPICS_OPERATION}/{topic}`, "put")).toEqual(Object.keys(nameBody({ topic: "a", principalId: "b" })).sort());
    expect(declaredPropertySchema(`${TOPICS_OPERATION}/{topic}`, "put", "principal_id")["pattern"]).toBe(IDENTIFIER_PATTERN);

    const estimated = openBody({
      becameAwareAt: "2019-03-04T09:00",
      basis: "estimated",
      source: "staff_report",
      evidenceReference: "INC-7",
      earliestPossibleAt: "2019-03-04T08:00",
    });
    expect(keys(BREACHES_OPERATION, "post")).toEqual(Object.keys(estimated).sort());
    expect(declaredPropertySchema(BREACHES_OPERATION, "post", "evidence_reference")["pattern"]).toBe(IDENTIFIER_PATTERN);

    const assessment = `${BREACHES_OPERATION}/{case_id}/assessment`;
    expect(keys(assessment, "post")).toEqual(
      Object.keys(assessBody({ harm: "yes", rationaleReference: "r", affectedCount: "" })).sort(),
    );
    expect(declaredPropertySchema(assessment, "post", "rationale_reference")["pattern"]).toBe(IDENTIFIER_PATTERN);
    const exception = `${BREACHES_OPERATION}/{case_id}/exception`;
    expect(keys(exception, "post")).toEqual(Object.keys(exceptionBody({ ground: "remedial_action", rationaleReference: "r" })).sort());
  });

  test("an estimate needs its earliest moment, and an observed time is sent without one", () => {
    // What breaks if this is deleted: `brain.audit.compliance.Awareness` refuses the case only after
    // the confirmation, or an observed case carries a second start time the clock could read.
    const now = new Date("2019-03-05T00:00:00Z");
    const estimate = {
      becameAwareAt: "2019-03-04T09:00",
      basis: "estimated",
      source: "staff_report",
      evidenceReference: "INC-7",
      earliestPossibleAt: "",
    };
    expect(openProblems(estimate, now).join(" ")).toContain("earliest moment");
    expect(openProblems({ ...estimate, earliestPossibleAt: "2019-03-04T10:00" }, now).join(" ")).toContain("later than the estimate");
    expect(openProblems({ ...estimate, earliestPossibleAt: "2019-03-04T08:00" }, now)).toEqual([]);
    const observed = { ...estimate, basis: "observed", earliestPossibleAt: "2019-03-04T08:00" };
    expect(openProblems(observed, now)).toEqual([]);
    expect("earliest_possible_at" in openBody(observed)).toBe(false);
    expect(openProblems({ ...observed, becameAwareAt: "2019-03-06T09:00" }, now).join(" ")).toContain("future");
  });

  test("a suppressed tally draws no number, and a released one names its topics", () => {
    // What breaks if this is deleted: a small count of intercepted questions drawn beside a topic,
    // which points at the people who asked.
    const label = (topic: string) => (topic === "salary" ? "Salary" : topic);
    const suppressed = tallySentence({ period: "2019-03", total: null, by_topic: null, suppressed: true }, label);
    expect(suppressed).toContain("suppressed");
    expect(suppressed).not.toMatch(/\d+ questions/);
    expect(tallySentence({ period: "2019-03", total: 40, by_topic: { salary: 40 }, suppressed: false }, label)).toBe(
      "For 2019-03, 40 questions were intercepted: Salary 40.",
    );
  });

  test("an obligation says its deadline, whether it is statutory, and whether it is overdue", () => {
    // What breaks if this is deleted: a guideline drawn like a statutory deadline, or an overdue one
    // drawn as merely open, which is the difference the case exists to show.
    const [duty] = breach().obligations;
    expect(obligationSentence(duty as Breach["obligations"][number], () => "THEN")).toBe(
      "Assess whether it is notifiable, expected by the regulator's guidance: due before THEN; overdue.",
    );
  });
});

describe("sensitive topics", () => {
  test("each topic, its named person or nobody, the tally, and both served sentences are drawn", async () => {
    // What breaks if this is deleted: a topic with nobody named drawn as blank, or the page dropping
    // the sentence that tells the administrator what the asker is told.
    const { container } = await mount();
    const rows = [...container.querySelectorAll("table[aria-label='Who each sensitive topic is routed to'] tbody tr")];
    expect(rows).toHaveLength(2);
    expect(rows[0]?.textContent).toContain("u_hr");
    expect(rows[1]?.textContent).toContain(NOBODY_NAMED);
    expect(container.textContent).toContain("REFERRAL-SENTENCE");
    expect(container.textContent).toContain("ROUTING-SENTENCE");
    expect(container.textContent).toContain("the count is suppressed");
  });

  test("a person without a reference is refused before anything is asked", async () => {
    const { container, idp } = await mount();
    const form = formNamed(container, NAME_FORM_LABEL);
    fireEvent.change(field(form, "Topic"), { target: { value: "salary" } });
    fireEvent.change(field(form, "Person, by reference"), { target: { value: "Jane Smith" } });
    fireEvent.submit(form);
    expect(container.querySelector("[role='alert']")?.textContent).toContain("reference");
    expect(container.querySelector(".confirm")).toBeNull();
    expect(writes(idp)).toEqual([]);
  });

  test("naming a person is confirmed with whom it replaces, then sent as a PUT to the topic", async () => {
    // What breaks if this is deleted: a person named on the first click, or a confirmation that does
    // not say whose notes stop, which is the grievance handler replaced unread.
    const { container, idp } = await mount();
    const form = formNamed(container, NAME_FORM_LABEL);
    fireEvent.change(field(form, "Topic"), { target: { value: "grievance" } });
    fireEvent.change(field(form, "Person, by reference"), { target: { value: " u_new " } });
    fireEvent.submit(form);
    const confirmation = container.querySelector(".confirm")?.textContent ?? "";
    expect(confirmation).toContain("Route Grievances questions to u_new?");
    expect(confirmation).toContain("in place of u_hr");
    expect(writes(idp)).toEqual([]);

    confirm(container, NAME_LABEL);
    await waitFor(() => {
      expect(writes(idp)).toEqual([
        { method: "PUT", path: `${TOPICS_OPERATION}/grievance`, body: { principal_id: "u_new" } },
      ]);
    });
    await waitFor(() => {
      expect(container.textContent).toContain("u_new was named for Grievances at");
    });
  });
});

describe("the processing register", () => {
  test("a connector is drawn with what it reads per entity, its categories, its counts and its problem", async () => {
    // What breaks if this is deleted: the register drops the fields a source reads, or a count not
    // yet taken is drawn as zero, which reads as a source that read nothing.
    const { container } = await mount();
    const text = container.textContent ?? "";
    expect(text).toContain("COUNTS-SENTENCE");
    expect(text).toContain("Xero");
    expect(text).toContain("amount, contact");
    expect(text).toContain("projected");
    expect(text).toContain("financial");
    expect(text).toContain("42");
    expect(text).toContain("Not read yet.");
    expect(text).toContain("No, it only reads.");
    expect(text).toContain("PROBLEM-SENTENCE");
  });

  test("an install with nothing connected says so rather than drawing an empty register", async () => {
    const { container } = await mount({ register: register({ connectors: [] }) });
    expect(container.textContent).toContain(NOTHING_CONNECTED);
    expect(container.textContent).toContain("COUNTS-SENTENCE");
  });
});

describe("breach cases", () => {
  test("a case draws its clock, its obligations with their flags, and its findings as served", async () => {
    // What breaks if this is deleted: the clock drawn from the estimate rather than the earliest
    // moment, or an overdue obligation and the case's findings missing from the page.
    const { container } = await mount();
    const card = container.querySelector(`section[aria-label="Breach case ${CASE}"]`);
    expect(card).not.toBeNull();
    expect(card?.textContent).toContain("The clock starts");
    expect(card?.querySelector(`ul[aria-label="What breach case ${CASE} owes"]`)?.textContent).toContain("overdue");
    expect(card?.textContent).toContain("FINDING-SENTENCE");
  });

  test("close is disabled with the route's sentence until the case is closable, then confirmed and sent", async () => {
    // What breaks if this is deleted: a close offered on a case whose assessment is not made, which
    // the route refuses after the confirmation, or a close sent on the first click.
    const first = await mount();
    expect(button(first.container, CLOSE_LABEL)?.disabled).toBe(true);
    expect(first.container.textContent).toContain("CLOSING-SENTENCE");

    const { container, idp } = await mount({
      breaches: { cases: [breach({ assessed_at: "2019-03-04T12:00:00Z", closable: true })], closing: "CLOSING-SENTENCE" },
    });
    const close = [...container.querySelectorAll(`section[aria-label="Breach case ${CASE}"] button`)].find(
      (one) => one.textContent === CLOSE_LABEL,
    ) as HTMLButtonElement;
    expect(close.disabled).toBe(false);
    fireEvent.click(close);
    expect(container.querySelector(".confirm")?.textContent).toContain(`Close breach case ${CASE}?`);
    expect(writes(idp)).toEqual([]);
    confirm(container, CLOSE_LABEL);
    await waitFor(() => {
      expect(writes(idp)).toEqual([{ method: "POST", path: `${BREACHES_OPERATION}/${CASE}/close`, body: undefined }]);
    });
  });

  test("an assessment is judged, confirmed with the judgement, then sent to the case", async () => {
    const { container, idp } = await mount();
    const form = formNamed(container, ASSESS_FORM_LABEL);
    fireEvent.submit(form);
    expect(form.querySelector("[role='alert']")?.textContent).toContain("significant harm");
    expect(container.querySelector(".confirm")).toBeNull();

    fireEvent.change(field(form, "Likely to result in significant harm"), { target: { value: "yes" } });
    fireEvent.change(field(form, "Where the reasoning is written"), { target: { value: "DPO-MEMO-3" } });
    fireEvent.change(field(form, "How many people are affected"), { target: { value: "12" } });
    fireEvent.submit(form);
    const confirmation = container.querySelector(".confirm")?.textContent ?? "";
    expect(confirmation).toContain("is likely to result in significant harm?");
    expect(confirmation).toContain("12 people affected");
    expect(writes(idp)).toEqual([]);

    confirm(container, ASSESS_LABEL);
    await waitFor(() => {
      expect(writes(idp)).toEqual([
        {
          method: "POST",
          path: `${BREACHES_OPERATION}/${CASE}/assessment`,
          body: { significant_harm: true, rationale_reference: "DPO-MEMO-3", affected_count: 12 },
        },
      ]);
    });
  });

  test("a notification needs its moment, and is sent as that instant with a zone", async () => {
    const { container, idp } = await mount();
    const form = formNamed(container, COMMISSION_FORM_LABEL);
    fireEvent.submit(form);
    expect(form.querySelector("[role='alert']")?.textContent).toContain("date and time");

    fireEvent.change(field(form, "When the Commission was notified"), { target: { value: "2019-03-04T15:30" } });
    fireEvent.submit(form);
    confirm(container, COMMISSION_LABEL);
    await waitFor(() => {
      expect(writes(idp)).toEqual([
        {
          method: "POST",
          path: `${BREACHES_OPERATION}/${CASE}/commission`,
          body: { at: new Date("2019-03-04T15:30").toISOString() },
        },
      ]);
    });
  });

  test("an excused case offers neither the individuals' notification nor a second exception, and a closed one offers nothing", async () => {
    // What breaks if this is deleted: a case with a recorded decision not to notify offered the
    // notification anyway, or a closed case drawn with controls the route refuses.
    const excused = await mount({
      breaches: { cases: [breach({ exception_ground: "remedial_action" })], closing: "CLOSING-SENTENCE" },
    });
    expect(excused.container.querySelector(`form[aria-label="${INDIVIDUALS_FORM_LABEL}"]`)).toBeNull();
    expect(excused.container.querySelector(`form[aria-label="${EXCEPTION_FORM_LABEL}"]`)).toBeNull();
    expect(excused.container.textContent).toContain("Remedial action made significant harm unlikely");

    const closed = await mount({
      breaches: { cases: [breach({ closed_at: "2019-03-05T09:00:00Z", closed_by: "u_dpo" })], closing: "CLOSING-SENTENCE" },
    });
    const card = closed.container.querySelector(`section[aria-label="Breach case ${CASE}"]`);
    expect(card?.querySelector("form")).toBeNull();
    expect(card?.querySelector("button")).toBeNull();
  });

  test("opening a case is judged, confirmed with what the clock runs from, then sent", async () => {
    // What breaks if this is deleted: a case opened on the first click, or opened as an estimate with
    // no earliest moment, which the route refuses after the confirmation.
    const { container, idp } = await mount({ breaches: { cases: [], closing: "CLOSING-SENTENCE" } });
    expect(container.textContent).toContain(NO_CASES);
    const form = formNamed(container, OPEN_FORM_LABEL);
    fireEvent.change(field(form, "When there was first reason to believe it"), { target: { value: "2019-03-04T09:00" } });
    fireEvent.change(field(form, "How that moment is known"), { target: { value: "estimated" } });
    fireEvent.change(field(form, "Where the reason to believe came from"), { target: { value: "staff_report" } });
    fireEvent.change(field(form, "Where the evidence is"), { target: { value: "INC-7" } });
    fireEvent.submit(form);
    expect(form.querySelector("[role='alert']")?.textContent).toContain("earliest moment");
    expect(container.querySelector(".confirm")).toBeNull();

    fireEvent.change(field(form, "The earliest it could have been"), { target: { value: "2019-03-04T08:00" } });
    fireEvent.submit(form);
    expect(container.querySelector(".confirm")?.textContent).toContain(OPENING);
    expect(writes(idp)).toEqual([]);

    confirm(container, OPEN_LABEL);
    await waitFor(() => {
      expect(writes(idp)).toEqual([
        {
          method: "POST",
          path: BREACHES_OPERATION,
          body: {
            became_aware_at: new Date("2019-03-04T09:00").toISOString(),
            basis: "estimated",
            source: "staff_report",
            evidence_reference: "INC-7",
            earliest_possible_at: new Date("2019-03-04T08:00").toISOString(),
          },
        },
      ]);
    });
    await waitFor(() => {
      expect(container.textContent).toContain("Breach case 22222222-2222-4222-8222-222222222222 was opened.");
    });
  });
});
