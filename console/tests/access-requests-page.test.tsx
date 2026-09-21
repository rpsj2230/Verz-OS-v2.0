/**
 * The Access requests screen: a request is sent as the route declares it, the asker is shown the
 * API's own sentence and nothing else, and the list is the requests addressed to the reader.
 *
 * Task ids: M4.3.4, M2.2.4
 */

import { fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import {
  ACCESS_REQUESTS_API_PATH,
  ACCESS_REQUESTS_PATH,
  NOTHING_SENT,
} from "../src/pages/accessRequestsQuery";
import { json, mountPage, settled, type Answer } from "./support/pageHarness";
import { backendModelFields } from "./support/python";

const LIST = `GET /api/v1${ACCESS_REQUESTS_API_PATH}`;
const SEND = `POST /api/v1${ACCESS_REQUESTS_API_PATH}`;
const REPLY = "REPLY-SENTINEL";

function row(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    request_id: "11111111-2222-3333-4444-555555555555",
    asker_id: "ASKER-SENTINEL",
    subject: "department:finance",
    question: "QUESTION-SENTINEL",
    requested_capability: "read:knowledge",
    requested_at: "2019-03-06T08:30:00Z",
    ...overrides,
  };
}

function listed(items: Record<string, unknown>[]): Record<string, unknown> {
  return { items, next_cursor: null, total: null, truncated: false };
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

function type(container: HTMLElement, name: string, value: string): void {
  const field = container.querySelector(`[name="${name}"]`) as HTMLInputElement;
  fireEvent.change(field, { target: { value } });
}

describe("the Access requests screen", () => {
  test("a department request is sent as the route declares it and the reply is drawn as sent", async () => {
    // What breaks if this is deleted: a request that never reaches the route, or a console that
    // writes its own reply ("sent to the finance owner") and so tells the asker who owns what.
    const { container, sent } = await accessPage({
      [LIST]: () => json(listed([])),
      [SEND]: () => json({ message: REPLY }, 202),
    });
    type(container, "department", "  Finance ");
    type(container, "question", "what is their leave policy");
    fireEvent.submit(container.querySelector('form[aria-label="Ask for access"]') as HTMLFormElement);

    await waitFor(() => {
      expect(container.textContent).toContain(REPLY);
    });
    const posted = sent.find((one) => one.method === "POST");
    expect(posted?.body).toEqual({ department: "finance", question: "what is their leave policy" });
  });

  test("a locked field is sent as an entity and a field, and nothing else", async () => {
    const { container, sent } = await accessPage({
      [LIST]: () => json(listed([])),
      [SEND]: () => json({ message: REPLY }, 202),
    });
    fireEvent.change(container.querySelector('[name="kind"]') as HTMLSelectElement, { target: { value: "field" } });
    type(container, "entity", "client");
    type(container, "field", "contract_value");
    type(container, "question", "for the renewal");
    fireEvent.submit(container.querySelector('form[aria-label="Ask for access"]') as HTMLFormElement);

    await waitFor(() => {
      expect(sent.some((one) => one.method === "POST")).toBe(true);
    });
    expect(sent.find((one) => one.method === "POST")?.body).toEqual({
      entity: "client",
      field: "contract_value",
      question: "for the renewal",
    });
  });

  test("the requests sent to the reader are listed with the asker's question", async () => {
    // What breaks if this is deleted: a request stored where its owner never reads it.
    const { container } = await accessPage({ [LIST]: () => json(listed([row()])) });
    await settled(container);
    const text = container.textContent ?? "";
    expect(text).toContain("ASKER-SENTINEL");
    expect(text).toContain("QUESTION-SENTINEL");
    expect(text).toContain("The finance department");
  });

  test("an empty list says nobody has sent a request", async () => {
    const { container } = await accessPage({ [LIST]: () => json(listed([])) });
    expect(container.textContent).toContain(NOTHING_SENT);
  });

  test("every field the page reads is a field the route declares", () => {
    // What breaks if this is deleted: a renamed field that the page goes on reading as empty.
    expect(Object.keys(row()).sort()).toEqual(
      backendModelFields("src/brain/access_request_routes.py", "AccessRequestView").sort(),
    );
  });
});
