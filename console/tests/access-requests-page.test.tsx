/**
 * The Access requests page on the kit: a request is sent as the route declares it, the asker is
 * shown the API's own sentence and nothing else, the list is the requests addressed to the reader
 * named by who asked, and a request is marked handled only through its confirmation. Below them,
 * the questions nothing answered that were handed to a person, as the API lists them (M8.3.2).
 *
 * Task ids: M4.3.4, M2.2.4, M27.16.1, M8.3.2, M8.3.4
 */

import { fireEvent, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { ACCESS_REQUESTS_API_PATH, ACCESS_REQUESTS_PATH, ASK_HEADING, NOTHING_SENT } from "../src/pages/accessRequestsQuery";
import { MARK_HANDLED } from "../src/pages/access-requests/AccessRequestsPage";
import {
  ESCALATIONS_API_PATH,
  NOTHING_HANDED,
  NOTHING_OF_YOURS,
  type EscalationsAnswer,
} from "../src/pages/access-requests/HandedToAPerson";
import { json, mountPage, settled, type Answer } from "./support/pageHarness";
import { backendModelFields } from "./support/python";
import { installRadixStubs } from "./support/radix";
import { chooseInMenu, confirmWith } from "./support/rowMenu";

const LIST = `GET /api/v1${ACCESS_REQUESTS_API_PATH}`;
const SEND = `POST /api/v1${ACCESS_REQUESTS_API_PATH}`;
const REQUEST_ID = "11111111-2222-3333-4444-555555555555";
const HANDLED = `POST /api/v1${ACCESS_REQUESTS_API_PATH}/${REQUEST_ID}/handled`;
const REPLY = "REPLY-SENTINEL";
const HANDED = `GET /api/v1${ESCALATIONS_API_PATH}`;
const ASKER = "u_asker_41f2";

beforeAll(() => {
  installRadixStubs();
});

function row(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    request_id: REQUEST_ID,
    asker_id: ASKER,
    subject: "department:finance",
    question: "QUESTION-SENTINEL",
    requested_capability: "read:knowledge",
    requested_at: "2019-03-06T08:30:00Z",
    handled_at: null,
    ...overrides,
  };
}

function escalations(): EscalationsAnswer {
  return {
    asked: [
      {
        escalation_id: "e-asked",
        queue: "pricing",
        question: "My own question about pricing",
        raised_at: "2019-03-06T08:30:00Z",
        expires_at: "2019-03-06T09:30:00Z",
        expired: true,
        said: "NOBODY-PICKED-IT-UP-SENTINEL",
      },
    ],
    handed: [
      {
        escalation_id: "e-handed",
        queue: "pricing",
        asker_id: "u_asker_41f2",
        asker_name: "Asha Asker",
        question: "What does the premium plan cost for a charity?",
        tried: ["answer.searched_at_the_askers_reach", "skill.quote_desk"],
        needed: "Somebody who can quote outside the price list",
        raised_at: "2019-03-06T08:30:00Z",
        expires_at: "2019-03-06T12:30:00Z",
        expired: false,
      },
    ],
    told: "HANDED-TOLD",
  };
}

function listed(items: Record<string, unknown>[]): Record<string, unknown> {
  return { items, next_cursor: null, total: null, truncated: false, people: { [ASKER]: "Asha Asker" } };
}

async function accessPage(answers: Record<string, Answer>) {
  return mountPage(
    ACCESS_REQUESTS_PATH,
    async () => {
      const { AccessRequests } = await import("../src/pages/AccessRequests");
      return <AccessRequests />;
    },
    answers,
  );
}

function type(name: string, value: string): void {
  const field = document.querySelector(`[name="${name}"]`) as HTMLInputElement;
  fireEvent.change(field, { target: { value } });
}

function press(root: ParentNode, words: string): void {
  const found = [...root.querySelectorAll("button")].find((one) => (one.textContent ?? "").trim().endsWith(words));
  if (found === undefined) {
    throw new Error(`no ${words} button`);
  }
  fireEvent.click(found);
}

async function askForm(container: HTMLElement): Promise<HTMLFormElement> {
  press(container, ASK_HEADING);
  return waitFor(() => document.querySelector('form[aria-label="Ask for access"]') as HTMLFormElement);
}

describe("the Access requests page", () => {
  test("a department request is sent as the route declares it and the reply is drawn as sent", async () => {
    // What breaks if this is deleted: a request that never reaches the route, or a console that
    // writes its own reply ("sent to the finance owner") and so tells the asker who owns what.
    const { container, sent } = await accessPage({
      [LIST]: () => json(listed([])),
      [SEND]: () => json({ message: REPLY }, 202),
    });
    const form = await askForm(container);
    type("department", "  Finance ");
    type("question", "what is their leave policy");
    fireEvent.submit(form);

    await waitFor(() => {
      expect(container.textContent).toContain(REPLY);
    });
    expect(sent.find((one) => one.method === "POST")?.body).toEqual({ department: "finance", question: "what is their leave policy" });
  });

  test("a locked field is sent as an entity and a field, and a blank one is said before anything is sent", async () => {
    // What breaks if this is deleted: an empty ask reaches the API, or a field's shape is said only
    // after a refusal.
    const { container, sent } = await accessPage({
      [LIST]: () => json(listed([])),
      [SEND]: () => json({ message: REPLY }, 202),
    });
    const form = await askForm(container);
    fireEvent.change(form.querySelector("select") as HTMLSelectElement, { target: { value: "field" } });
    expect(form.textContent).toContain("for example contract_value");
    fireEvent.submit(form);
    await waitFor(() => {
      expect(form.textContent).toContain("Name the field that was shown locked.");
    });
    expect(sent.filter((one) => one.method === "POST")).toEqual([]);

    type("entity", "client");
    type("field", "contract_value");
    type("question", "for the renewal");
    fireEvent.submit(form);
    await waitFor(() => {
      expect(sent.some((one) => one.method === "POST")).toBe(true);
    });
    expect(sent.find((one) => one.method === "POST")?.body).toEqual({ entity: "client", field: "contract_value", question: "for the renewal" });
  });

  test("the requests sent to the reader name who asked, with their question, and never the id", async () => {
    // What breaks if this is deleted: a request stored where its owner never reads it, or read as
    // a principal id nobody knows.
    const { container } = await accessPage({ [LIST]: () => json(listed([row()])) });
    await settled(container);
    const text = container.textContent ?? "";
    expect(text).toContain("Asha Asker");
    expect(text).toContain("QUESTION-SENTINEL");
    expect(text).toContain("The finance department");
    expect(text).not.toContain(ASKER);
  });

  test("a request is marked handled only through its confirmation, and a handled one offers no mark", async () => {
    // What breaks if this is deleted: the mark is sent from the menu with no confirmation, or
    // offered again on a request already handled.
    let handled = false;
    const { container, sent } = await accessPage({
      [LIST]: () => json(listed([row(handled ? { handled_at: "2019-03-07T08:30:00Z" } : {})])),
      [HANDLED]: () => {
        handled = true;
        return json({ request_id: REQUEST_ID, handled_at: "2019-03-07T08:30:00Z" });
      },
    });
    await settled(container);
    await chooseInMenu(container.querySelector('button[aria-label^="Actions for the request"]') as HTMLElement, MARK_HANDLED);
    expect(sent.filter((one) => one.method === "POST")).toEqual([]);
    await confirmWith(MARK_HANDLED);

    await waitFor(() => {
      expect(container.textContent).toContain("is marked handled");
    });
    expect(sent.filter((one) => one.method === "POST").map((one) => one.path)).toEqual([`/api/v1${ACCESS_REQUESTS_API_PATH}/${REQUEST_ID}/handled`]);
    await waitFor(() => {
      expect(container.querySelector('button[aria-label^="Actions for the request"]')).toBeNull();
    });
  });

  test("an empty list says nobody has sent a request", async () => {
    const { container } = await accessPage({ [LIST]: () => json(listed([])) });
    expect(container.textContent).toContain(NOTHING_SENT);
  });

  test("a question handed to the reader shows who asked, the question, what was tried and what is needed", async () => {
    // What breaks if this is deleted: a handoff fetched and never drawn, or drawn without what is
    // needed, which is the one line that tells the reader whether to pick it up (M8.3.2).
    const { container } = await accessPage({
      [LIST]: () => json(listed([])),
      [HANDED]: () => json(escalations()),
    });
    await waitFor(() => {
      expect(container.textContent).toContain("Asha Asker");
    });
    const text = container.textContent;
    expect(text).toContain("What does the premium plan cost for a charity?");
    expect(text).toContain("Needed: Somebody who can quote outside the price list");
    expect(text).toContain("skill.quote_desk");
    expect(text).toContain("NOBODY-PICKED-IT-UP-SENTINEL");
    expect(text).toContain("My own question about pricing");
  });

  test("with nothing handed either way, each list says so in one sentence and counts nothing", async () => {
    // What breaks if this is deleted: two empty lists drawn as blank cards, or as numbers.
    const { container } = await accessPage({
      [LIST]: () => json(listed([])),
      [HANDED]: () => json({ asked: [], handed: [], told: "TOLD" }),
    });
    await waitFor(() => {
      expect(container.textContent).toContain(NOTHING_HANDED);
    });
    expect(container.textContent).toContain(NOTHING_OF_YOURS);
  });

  test("every field the handed-on lists read is a field the route declares", () => {
    // What breaks if this is deleted: a renamed field in the route that the page goes on reading as
    // empty, so a handoff loses its question or its asker is never told it expired.
    const found = escalations();
    expect(Object.keys(found).sort()).toEqual(backendModelFields("src/brain/escalation_routes.py", "EscalationsView").sort());
    expect(Object.keys(found.asked[0] ?? {}).sort()).toEqual(backendModelFields("src/brain/escalation_routes.py", "AskedView").sort());
    expect(Object.keys(found.handed[0] ?? {}).sort()).toEqual(backendModelFields("src/brain/escalation_routes.py", "HandedView").sort());
  });

  test("every field the page reads is a field the route declares", () => {
    // What breaks if this is deleted: a renamed field that the page goes on reading as empty.
    expect(Object.keys(row()).sort()).toEqual(backendModelFields("src/brain/access_request_routes.py", "AccessRequestView").sort());
  });
});
