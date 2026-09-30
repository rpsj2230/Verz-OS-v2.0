/**
 * Compliance on the page kit: breach cases and each case's own page, sensitive topics, and the
 * processing register.
 *
 * Mounted through the page's own route file. The failures worth testing: a record that cannot be
 * taken back sent without its confirmation, a form judged only after the confirmation, a step offered
 * on a case that no longer takes it, a principal id where a person's name belongs, and a count of
 * intercepted questions small enough to point at somebody.
 *
 * And the escalation queues (M8.3.2): who answers for each queue a skill hands its unanswered
 * questions to, and the confirmed form that names them.
 *
 * Task ids: M24.2.2, M24.2.3, M24.2.4, M27.16.1, M8.3.2
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  ASSESS_LABEL,
  CLOSE_LABEL,
  COMMISSION_LABEL,
  EXCEPTION_FORM_LABEL,
  INDIVIDUALS_LABEL,
  NAME_FORM_LABEL,
  NAME_LABEL,
  OPENING,
  OPEN_FORM_LABEL,
  OPEN_LABEL,
  REVIEW_CASE,
} from "../src/pages/compliance/ComplianceActs";
import { NO_CASE } from "../src/pages/compliance/BreachPage";
import {
  caseAddress,
  NAME_A_PERSON,
  NOBODY_NAMED,
  NOTHING_CONNECTED,
  NO_CASES,
  READING_COMPLIANCE,
  viewAddress,
} from "../src/pages/compliance/CompliancePage";
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
import {
  NAME_QUEUE_LABEL,
  NAME_QUEUE_SUBMIT,
  NO_QUEUES,
  QUEUE_PROBLEMS,
  queueBody,
  type RoutesAnswer,
} from "../src/pages/compliance/EscalationQueues";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { backendModelFields } from "./support/python";
import { declaredPropertySchema, declaredRequestBodySchema } from "./support/openapi";
import { installRadixStubs } from "./support/radix";
import { chooseInMenu, confirmWith } from "./support/rowMenu";

const CONSOLE_ORIGIN = "https://console.test";
const TOPICS_OPERATION = "/api/v1/govern/compliance/topics";
const REGISTER_OPERATION = "/api/v1/govern/compliance/register";
const BREACHES_OPERATION = "/api/v1/govern/compliance/breaches";
const ROUTES_OPERATION = "/api/v1/govern/escalation-routes";
const CASE = "11111111-1111-4111-8111-111111111111";

beforeAll(async () => {
  installRadixStubs();
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
    people: { u_hr: "Hana HR", u_admin: "Adam Admin" },
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
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

interface Stand {
  topics?: TopicsAnswer;
  register?: RegisterAnswer;
  breaches?: BreachesAnswer;
  routes?: RoutesAnswer;
}

function queues(overrides: Partial<RoutesAnswer> = {}): RoutesAnswer {
  return {
    routes: [
      {
        queue: "pricing",
        person: "u_quotes",
        person_name: "Quinn Quotes",
        channel: "lark",
        address: "ou_quotes",
        named_by: "u_admin",
        named_at: "2019-03-04T09:00:00Z",
      },
    ],
    channels: ["lark", "webhook"],
    told: "ROUTING-TOLD-SENTENCE",
    ...overrides,
  };
}

async function mount(path: string, stand: Stand = {}): Promise<{ container: HTMLElement; idp: FakeIdp }> {
  const cases = stand.breaches ?? { cases: [breach()], closing: "CLOSING-SENTENCE", people: { u_dpo: "Dana DPO" } };
  const idp = fakeIdentityProvider({
    api(url, init) {
      const at = new URL(url, CONSOLE_ORIGIN).pathname;
      if (init?.method === "PUT") {
        return json({ principal_id: "u_new", named_by: "u_admin", named_at: "2019-03-05T10:00:00Z" });
      }
      if (init?.method === "POST") {
        return json(breach({ case_id: "22222222-2222-4222-8222-222222222222" }));
      }
      const reads: Record<string, unknown> = {
        [TOPICS_OPERATION]: stand.topics ?? topics(),
        [REGISTER_OPERATION]: stand.register ?? register(),
        [BREACHES_OPERATION]: cases,
        [ROUTES_OPERATION]: stand.routes ?? queues(),
      };
      return at in reads ? json(reads[at]) : null;
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/pages/Compliance.route");
  const router = createMemoryRouter(routes.map((one) => ({ path: `/${one.path}`, element: one.element })), { initialEntries: [path] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if ((container.textContent ?? "").includes(READING_COMPLIANCE) || container.querySelector("h1") === null) {
      throw new Error("still reading");
    }
  });
  return { container, idp };
}

function writes(idp: FakeIdp): { method: string; path: string; body: unknown }[] {
  return idp.calls
    .filter((call) => call.init?.method !== undefined && call.init.method !== "GET" && new URL(call.url, CONSOLE_ORIGIN).pathname.startsWith("/api/"))
    .map((call) => ({
      method: call.init?.method ?? "",
      path: new URL(call.url, CONSOLE_ORIGIN).pathname,
      body: call.init?.body === undefined ? undefined : (JSON.parse(String(call.init.body)) as unknown),
    }));
}

function type(form: HTMLElement, name: string, value: string): void {
  fireEvent.change(form.querySelector(`[name="${name}"]`) as HTMLInputElement, { target: { value } });
}

function choose(form: HTMLElement, label: string, value: string): void {
  const found = [...form.querySelectorAll("label")].find((one) => one.textContent === label);
  const select = form.ownerDocument.getElementById(found?.htmlFor ?? "") as HTMLSelectElement;
  fireEvent.change(select, { target: { value } });
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
  test("each topic names its person by name or says nobody, with the tally and both served sentences", async () => {
    // What breaks if this is deleted: a principal id drawn where the reader needs a name, or the
    // sentence the asker is told dropped.
    const { container } = await mount(viewAddress("topics"));
    expect(container.textContent).toContain("Hana HR");
    expect(container.textContent).toContain("Adam Admin");
    expect(container.textContent).not.toContain("u_hr");
    expect(container.textContent).toContain(NOBODY_NAMED);
    expect(container.textContent).toContain("REFERRAL-SENTENCE");
    expect(container.textContent).toContain("ROUTING-SENTENCE");
    expect(container.textContent).toContain("suppressed");
  });

  test("naming a person says what it takes, refuses a blank one, and is confirmed with whom it replaces before the PUT", async () => {
    const { idp } = await mount(viewAddress("topics"));
    await chooseInMenu(screen.getByRole("button", { name: "Actions for Grievances" }), NAME_A_PERSON);
    const form = (await screen.findByRole("form", { name: NAME_FORM_LABEL })) as HTMLFormElement;
    expect(form.textContent).toContain("with no spaces");
    fireEvent.submit(form);
    await waitFor(() => {
      expect(form.textContent).toContain("Give the person's reference");
    });
    expect(screen.queryByRole("alertdialog")).toBeNull();

    type(form, "principal_id", " u_new ");
    fireEvent.submit(form);
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain("in place of Hana HR");
    expect(writes(idp)).toEqual([]);
    await confirmWith(NAME_LABEL);
    await waitFor(() => {
      expect(writes(idp)).toEqual([{ method: "PUT", path: `${TOPICS_OPERATION}/grievance`, body: { principal_id: "u_new" } }]);
    });
  });
});

describe("escalation queues", () => {
  test("each queue says who answers for it, by name, and where they are reached, under the served sentence", async () => {
    // What breaks if this is deleted: a queue drawn with a reference where a name belongs, or with
    // no channel, so nobody can tell where the questions it is handed go.
    const { container } = await mount(viewAddress("escalations"));
    expect(container.textContent).toContain("pricing");
    expect(container.textContent).toContain("Quinn Quotes");
    expect(container.textContent).toContain("lark, ou_quotes");
    expect(container.textContent).toContain("ROUTING-TOLD-SENTENCE");
  });

  test("an install with no queue named says so and still offers the form", async () => {
    // What breaks if this is deleted: an empty table that reads as a broken page, with no way to name
    // the first person.
    const { container } = await mount(viewAddress("escalations"), { routes: queues({ routes: [] }) });
    expect(container.textContent).toContain(NO_QUEUES);
    expect(screen.getByRole("button", { name: new RegExp(NAME_QUEUE_LABEL) })).toBeTruthy();
  });

  test("naming says what each field takes, refuses blanks before anything is sent, and is confirmed before the PUT", async () => {
    // What breaks if this is deleted: a naming sent without its confirmation, which replaces whoever
    // answered for the queue, or a form judged only after the route refuses it.
    const { idp } = await mount(viewAddress("escalations"));
    fireEvent.click(screen.getByRole("button", { name: new RegExp(NAME_QUEUE_LABEL) }));
    const form = (await screen.findByRole("form", { name: NAME_QUEUE_LABEL })) as HTMLFormElement;
    fireEvent.submit(form);
    await waitFor(() => {
      expect(form.textContent).toContain(QUEUE_PROBLEMS.queue);
    });
    expect(form.textContent).toContain(QUEUE_PROBLEMS.person);
    expect(form.textContent).toContain(QUEUE_PROBLEMS.channel);
    expect(screen.queryByRole("alertdialog")).toBeNull();

    type(form, "queue", "pricing");
    type(form, "person", " u_new ");
    choose(form, "Channel", "webhook");
    type(form, "address", " desk ");
    fireEvent.submit(form);
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain("in place of whoever was named before");
    expect(writes(idp)).toEqual([]);
    await confirmWith(NAME_QUEUE_SUBMIT);
    await waitFor(() => {
      expect(writes(idp)).toEqual([
        { method: "PUT", path: `${ROUTES_OPERATION}/pricing`, body: { person: "u_new", channel: "webhook", address: "desk" } },
      ]);
    });
  });

  test("the body and the fields read are the route's own", () => {
    // What breaks if this is deleted: a renamed field in the route that this page goes on sending or
    // reading, so every naming is refused or every queue is drawn empty.
    const body = declaredRequestBodySchema(`${ROUTES_OPERATION}/{queue}`, "put");
    expect(Object.keys(body["properties"] as object).sort()).toEqual(Object.keys(queueBody({ queue: "q", person: "p", channel: "c", address: "a" })).sort());
    expect(Object.keys(queues().routes[0] ?? {}).sort()).toEqual(backendModelFields("src/brain/escalation_routes.py", "RouteView").sort());
    expect(Object.keys(queues()).sort()).toEqual(backendModelFields("src/brain/escalation_routes.py", "RoutesView").sort());
  });
});

describe("the processing register", () => {
  test("a connector is drawn with what it reads per entity, its categories, its counts and its problem", async () => {
    const { container } = await mount(viewAddress("register"), { register: { ...register(), people: { u_admin: "Adam Admin" } } as RegisterAnswer });
    expect(container.textContent).toContain("Xero");
    expect(container.textContent).toContain("invoice");
    expect(container.textContent).toContain("financial");
    expect(container.textContent).toContain("42");
    expect(container.textContent).toContain("PROBLEM-SENTENCE");
    expect(container.textContent).toContain("Adam Admin");
  });

  test("an install with nothing connected says so rather than drawing an empty register", async () => {
    const { container } = await mount(viewAddress("register"), { register: register({ connectors: [] }) });
    expect(container.textContent).toContain(NOTHING_CONNECTED);
  });
});

describe("breach cases", () => {
  test("the list draws each case by its evidence reference and whether it is overdue", async () => {
    const { container } = await mount(viewAddress("breaches"));
    const table = within(container.querySelector("table") as HTMLElement);
    expect(table.getByText("INC-7")).toBeTruthy();
    expect(table.getByText("Overdue")).toBeTruthy();

    const none = await mount(viewAddress("breaches"), { breaches: { cases: [], closing: "", people: {} } as BreachesAnswer });
    expect(none.container.textContent).toContain(NO_CASES);
  });

  test("a case's page draws its clock, its obligations with their flags, and its findings as served", async () => {
    const { container } = await mount(caseAddress(CASE));
    expect(container.querySelector("h1")?.textContent).toBe("Breach case INC-7");
    expect(container.textContent).toContain("overdue");
    expect(container.textContent).toContain("FINDING-SENTENCE");
    expect(container.textContent).toContain("Dana DPO");
    expect(container.querySelector('[data-slot="advanced"]')?.textContent).toContain("u_dpo");

    const absent = await mount(caseAddress("33333333-3333-4333-8333-333333333333"));
    expect(absent.container.querySelector("h1")?.textContent).toBe(NO_CASE);
  });

  test("close is inert with the route's sentence until the case is closable, then confirmed and sent", async () => {
    // What breaks if this is deleted: a case closed before its assessment, or closed on one press.
    const inert = await mount(caseAddress(CASE));
    const unavailable = within(inert.container).getByRole("button", { name: CLOSE_LABEL });
    expect(unavailable.getAttribute("aria-disabled")).toBe("true");
    expect(inert.container.textContent).toContain("CLOSING-SENTENCE");

    const closable = await mount(caseAddress(CASE), { breaches: { cases: [breach({ closable: true })], closing: "CLOSING-SENTENCE", people: {} } as BreachesAnswer });
    fireEvent.click(within(closable.container).getByRole("button", { name: CLOSE_LABEL }));
    expect(writes(closable.idp)).toEqual([]);
    await confirmWith(CLOSE_LABEL);
    await waitFor(() => {
      expect(writes(closable.idp)).toEqual([{ method: "POST", path: `${BREACHES_OPERATION}/${CASE}/close`, body: undefined }]);
    });
  });

  test("an assessment is judged, confirmed with the judgement, then sent to the case", async () => {
    const { idp } = await mount(caseAddress(CASE));
    fireEvent.click(screen.getByRole("button", { name: ASSESS_LABEL }));
    const form = (await screen.findByRole("form", { name: ASSESS_LABEL })) as HTMLFormElement;
    fireEvent.submit(form);
    await waitFor(() => {
      expect(form.textContent).toContain("Say whether the breach is likely to result in significant harm.");
    });
    expect(screen.queryByRole("alertdialog")).toBeNull();

    choose(form, "Likely to result in significant harm", "yes");
    type(form, "rationale_reference", "DPIA-3");
    fireEvent.submit(form);
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain("is likely to result in significant harm?");
    await confirmWith(ASSESS_LABEL);
    await waitFor(() => {
      expect(writes(idp)).toEqual([
        { method: "POST", path: `${BREACHES_OPERATION}/${CASE}/assessment`, body: { significant_harm: true, rationale_reference: "DPIA-3", affected_count: null } },
      ]);
    });
  });

  test("a notification needs its moment, and is sent as that instant with a zone", async () => {
    const { idp } = await mount(caseAddress(CASE));
    fireEvent.click(screen.getByRole("button", { name: COMMISSION_LABEL }));
    const form = (await screen.findByRole("form", { name: COMMISSION_LABEL })) as HTMLFormElement;
    fireEvent.submit(form);
    await waitFor(() => {
      expect(form.textContent).toContain("Give the date and time the notification was made.");
    });
    type(form, "at", "2019-03-04T10:00");
    fireEvent.submit(form);
    await confirmWith(COMMISSION_LABEL);
    await waitFor(() => {
      expect(writes(idp)).toHaveLength(1);
    });
    const sent = writes(idp)[0]?.body as { at: string };
    expect(sent.at).toBe(new Date("2019-03-04T10:00").toISOString());
  });

  test("an excused case offers neither the individuals' notification nor a second exception, and a closed one offers no step", async () => {
    const excused = await mount(caseAddress(CASE), { breaches: { cases: [breach({ exception_ground: "remedial_action" })], closing: "", people: {} } as BreachesAnswer });
    expect(within(excused.container).queryByRole("button", { name: INDIVIDUALS_LABEL })).toBeNull();
    expect(within(excused.container).queryByRole("button", { name: EXCEPTION_FORM_LABEL })).toBeNull();
    expect(within(excused.container).getByRole("button", { name: COMMISSION_LABEL })).toBeTruthy();

    const closed = await mount(caseAddress(CASE), { breaches: { cases: [breach({ closed_at: "2019-03-06T10:00:00Z" })], closing: "", people: {} } as BreachesAnswer });
    expect(within(closed.container).queryByRole("button", { name: ASSESS_LABEL })).toBeNull();
    expect(within(closed.container).queryByRole("button", { name: CLOSE_LABEL })).toBeNull();
  });

  test("opening a case is judged, confirmed with what the clock runs from, then sent", async () => {
    const { idp } = await mount(viewAddress("breaches"));
    fireEvent.click(screen.getByRole("button", { name: OPEN_FORM_LABEL }));
    const form = (await screen.findByRole("form", { name: OPEN_FORM_LABEL })) as HTMLFormElement;
    expect(form.textContent).toContain("such as the alert or ticket number");
    fireEvent.click(screen.getByRole("button", { name: REVIEW_CASE }));
    await waitFor(() => {
      expect(form.textContent).toContain("Give the date and time there was first reason to believe");
    });
    expect(screen.queryByRole("alertdialog")).toBeNull();

    type(form, "became_aware_at", "2019-03-04T09:00");
    choose(form, "How that moment is known", "observed");
    choose(form, "Where it came from", "staff_report");
    type(form, "evidence_reference", "INC-9");
    fireEvent.submit(form);
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain(OPENING);
    await confirmWith(OPEN_LABEL);
    await waitFor(() => {
      expect(writes(idp)).toHaveLength(1);
    });
    expect(writes(idp)[0]?.body).toEqual({ became_aware_at: new Date("2019-03-04T09:00").toISOString(), basis: "observed", source: "staff_report", evidence_reference: "INC-9" });
  });
});
