/**
 * The People screen's Data steward card: drawn for an administrator the API answers, naming
 * another person or the administrator, each confirmed, and saying nothing for anybody else.
 *
 * Mounted through the route table at `/people`, with a stand-in API answering the listing and the
 * card, because the card is part of that page and a component mounted alone would not show whether
 * the page draws it.
 *
 * Task ids: M27.9.9
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  CONFIRM_NAMING,
  DATA_STEWARD_HEADING,
  KEEP_AS_IT_IS,
  NAME_ANOTHER,
  NAME_YOURSELF,
  STEWARD_ADDRESS_LABEL,
  STEWARD_NAME_LABEL,
  YOURSELF_QUESTION,
  anotherQuestion,
} from "../src/pages/dataStewardQuery";
import { messageFor } from "../src/setup/wizard";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { declaredPropertyNames, declaredRequestBodySchema, declaredResponseSchema } from "./support/openapi";

const STEWARD_OPERATION = "/api/v1/govern/data-steward";
const CONSOLE_ORIGIN = "https://console.test";
const NOBODY = "No data steward is appointed, so nobody can be granted a read.";
const ANOTHER = "They are granted every read, recorded against you.";
const YOURSELF = "Your account then holds both, recorded against you.";

const PEOPLE = {
  items: [],
  next_cursor: null,
  total: null,
  truncated: false,
  editable: true,
  staleness: null,
};

function view(appointed: boolean): unknown {
  return {
    appointed,
    principal_id: appointed ? "u_steward" : null,
    display_name: appointed ? "A Steward" : null,
    told: appointed ? "A Steward is the data steward." : NOBODY,
    appointing_another: ANOTHER,
    appointing_yourself: YOURSELF,
  };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

type Written = (body: unknown) => Response;

beforeAll(async () => {
  await import("../src/pages/People");
}, 60_000);

/**
 * The People page with the card answered by `read`, and every write answered by `write`. After a
 * write the card is read again, and `read` is asked for its second answer.
 */
async function mount(
  reads: readonly Response[],
  write: Written = () => json(view(true)),
): Promise<{ container: HTMLElement; idp: FakeIdp }> {
  let asked = 0;
  const idp = fakeIdentityProvider({
    api(url, init) {
      const path = new URL(url, CONSOLE_ORIGIN).pathname;
      if (path === "/api/v1/govern/people") {
        return json(PEOPLE);
      }
      if (path !== STEWARD_OPERATION) {
        return null;
      }
      if ((init?.method ?? "GET") === "POST") {
        return write(JSON.parse(String(init?.body ?? "null")));
      }
      const answer = reads[Math.min(asked, reads.length - 1)] as Response;
      asked += 1;
      return answer.clone();
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: ["/people"] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (container.querySelector("h1") === null || container.textContent?.includes("Loading.")) {
      throw new Error("the page has no answer yet");
    }
  });
  return { container, idp };
}

function posts(idp: FakeIdp): unknown[] {
  return idp.calls
    .filter(
      (call) =>
        call.init?.method === "POST" && new URL(call.url, CONSOLE_ORIGIN).pathname === STEWARD_OPERATION,
    )
    .map((call) => JSON.parse(String(call.init?.body ?? "null")) as unknown);
}

function button(container: HTMLElement, name: string): HTMLButtonElement {
  const found = [...container.querySelectorAll("button")].find((one) => one.textContent === name);
  if (found === undefined) {
    throw new Error(`no button named ${name}`);
  }
  return found as HTMLButtonElement;
}

function typeInto(container: HTMLElement, label: string, value: string): void {
  const found = [...container.querySelectorAll("label")].find((one) => one.textContent === label);
  const input = container.querySelector(`#${found?.getAttribute("for") ?? "missing"}`) as HTMLInputElement;
  fireEvent.change(input, { target: { value } });
}

function headings(container: HTMLElement): string[] {
  return [...container.querySelectorAll("h2")].map((one) => one.textContent ?? "");
}

describe("the data steward card", () => {
  test("what the card sends and reads is what the route declares", () => {
    // What breaks if this is deleted: a body key the route forbids, which is a 422 in front of an
    // administrator who filled the card in, or a field the card reads that the API never sends.
    expect(declaredPropertyNames(declaredRequestBodySchema(STEWARD_OPERATION, "post"))).toEqual([
      "full_name",
      "same_as_administrator",
      "work_address",
    ]);
    expect(declaredPropertyNames(declaredResponseSchema(STEWARD_OPERATION, "get"))).toEqual([
      "appointed",
      "appointing_another",
      "appointing_yourself",
      "display_name",
      "principal_id",
      "told",
    ]);
  });

  test("a reader the API refuses is shown no card, and an appointed steward is named with no control", async () => {
    // What breaks if this is deleted: the card drawn for everybody on the People screen, telling
    // each reader a control exists that they may not use, or a steward who can be replaced from it.
    const refused = await mount([json({ message: "I could not find that.", trace_id: "t" }, 404)]);
    // Asked and answered before the absence is believed, so an unanswered card is not the pass.
    await waitFor(() => expect(refused.idp.urls.some((url) => url.includes(STEWARD_OPERATION))).toBe(true));
    await new Promise((settled) => setTimeout(settled, 50));
    expect(headings(refused.container)).not.toContain(DATA_STEWARD_HEADING);
    expect(refused.container.textContent).not.toContain("I could not find that.");

    const appointed = await mount([json(view(true))]);
    await waitFor(() => expect(headings(appointed.container)).toContain(DATA_STEWARD_HEADING));
    expect(appointed.container.textContent).toContain("A Steward is the data steward.");
    expect(() => button(appointed.container, NAME_ANOTHER)).toThrow();
    expect(() => button(appointed.container, NAME_YOURSELF)).toThrow();
  });

  test("naming another person is judged blank first, confirmed in the API's words, and sent trimmed", async () => {
    // What breaks if this is deleted: a confirmation about naming nobody, a name sent with the
    // space a paste carries, or a write sent before anybody agreed to what it does.
    const { container, idp } = await mount([json(view(false)), json(view(true))]);
    await waitFor(() => expect(container.textContent).toContain(NOBODY));

    fireEvent.submit(button(container, NAME_ANOTHER).form as HTMLFormElement);
    await waitFor(() => expect(container.textContent).toContain(messageFor("setup.error.steward_needed")));
    expect(container.textContent).not.toContain(ANOTHER);
    expect(posts(idp)).toEqual([]);

    typeInto(container, STEWARD_NAME_LABEL, "  A Steward ");
    typeInto(container, STEWARD_ADDRESS_LABEL, " a.steward@company.invalid ");
    fireEvent.submit(button(container, NAME_ANOTHER).form as HTMLFormElement);
    await waitFor(() => expect(container.textContent).toContain(anotherQuestion("A Steward")));
    expect(container.textContent).toContain(ANOTHER);
    expect(posts(idp)).toEqual([]);

    fireEvent.click(button(container, CONFIRM_NAMING));
    await waitFor(() => expect(container.textContent).toContain("A Steward is the data steward."));
    expect(posts(idp)).toEqual([
      { same_as_administrator: false, full_name: "A Steward", work_address: "a.steward@company.invalid" },
    ]);
  });

  test("naming yourself is its own press and confirmation, and sends that choice and nothing typed", async () => {
    // What breaks if this is deleted: the administrator made the steward by a box left ticked, or a
    // name typed beside the choice sent with it, which the API refuses as two answers to one question.
    const { container, idp } = await mount([json(view(false)), json(view(true))]);
    await waitFor(() => expect(container.textContent).toContain(NOBODY));
    typeInto(container, STEWARD_NAME_LABEL, "Somebody Typed");

    fireEvent.click(button(container, NAME_YOURSELF));
    await waitFor(() => expect(container.textContent).toContain(YOURSELF_QUESTION));
    expect(container.textContent).toContain(YOURSELF);
    fireEvent.click(button(container, KEEP_AS_IT_IS));
    await waitFor(() => expect(container.textContent).not.toContain(YOURSELF_QUESTION));
    expect(posts(idp)).toEqual([]);

    fireEvent.click(button(container, NAME_YOURSELF));
    await waitFor(() => expect(container.textContent).toContain(YOURSELF_QUESTION));
    fireEvent.click(button(container, CONFIRM_NAMING));
    await waitFor(() => expect(posts(idp)).toEqual([{ same_as_administrator: true }]));
  });

  test("a refusal is drawn in the API's own sentence, and nothing is appointed", async () => {
    // What breaks if this is deleted: a steward already named reaches the administrator as a
    // generic failure rather than as the sentence saying the console does not replace one.
    const told = "This install already has a data steward. Nothing was changed.";
    const { container } = await mount([json(view(false))], () =>
      json({ message: told, trace_id: "TRACE-SENTINEL" }, 409),
    );
    await waitFor(() => expect(container.textContent).toContain(NOBODY));
    fireEvent.click(button(container, NAME_YOURSELF));
    await waitFor(() => expect(container.textContent).toContain(YOURSELF_QUESTION));
    fireEvent.click(button(container, CONFIRM_NAMING));
    await waitFor(() => expect(container.textContent).toContain(told));
    expect(container.textContent).toContain(NOBODY);
  });

  test("a problem with what was typed is drawn beside its own box in the API's sentence", async () => {
    // What breaks if this is deleted: a problem with the address drawn nowhere near the address,
    // so the administrator is told the form failed and not which box to change.
    const unaddressed = "Enter the work email address this person signs in with";
    const { container } = await mount([json(view(false))], () =>
      json(
        { problems: [{ field: "steward_work_address", key: "setup.error.not_an_address", message: unaddressed }] },
        422,
      ),
    );
    await waitFor(() => expect(container.textContent).toContain(NOBODY));
    typeInto(container, STEWARD_NAME_LABEL, "A Steward");
    typeInto(container, STEWARD_ADDRESS_LABEL, "nobody");
    fireEvent.submit(button(container, NAME_ANOTHER).form as HTMLFormElement);
    await waitFor(() => expect(container.textContent).toContain(anotherQuestion("A Steward")));
    fireEvent.click(button(container, CONFIRM_NAMING));
    await waitFor(() => {
      const described = container.querySelector("#data-steward-work-address-problem");
      expect(described?.textContent).toBe(unaddressed);
    });
  });
});
