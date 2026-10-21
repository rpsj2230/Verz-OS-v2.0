/**
 * The questions offered on the empty Ask page: read defensively, drawn as controls that fill the
 * field and ask nothing, and absent when the route sends none or does not answer.
 *
 * Task ids: M26.1.4
 */

import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

const asked = vi.fn();
vi.mock("../src/api/client", () => ({ request: (path: string) => asked(path) }));

import { FROM_DATA_API_PATH, readFromData } from "../src/pages/adoptionCoverageQuery";
import { AskWelcome, CHECK_IN, FROM_YOUR_DATA, readWelcome, TRY_ASKING, WELCOME_API_PATH } from "../src/pages/AskWelcome";

beforeEach(() => {
  asked.mockReset();
});

describe("reading the route's answer", () => {
  test("keeps the strings and drops anything else", () => {
    expect(readWelcome({ questions: ["What does the sales team do here?", "", 3, null] })).toEqual([
      "What does the sales team do here?",
    ]);
  });

  test("a body that is not the route's shape offers nothing", () => {
    expect(readWelcome(null)).toEqual([]);
    expect(readWelcome([])).toEqual([]);
    expect(readWelcome({ questions: "x" })).toEqual([]);
  });
});

describe("the offered questions", () => {
  test("each is a control that hands its words over and asks nothing", async () => {
    asked.mockImplementation((path: string) =>
      Promise.resolve(path === WELCOME_API_PATH ? { ok: true, data: { questions: ["First?", "Second?"] } } : { ok: false }),
    );
    const chosen: string[] = [];
    const page = render(<AskWelcome onChoose={(one) => chosen.push(one)} />);
    await waitFor(() => expect(page.getByText(TRY_ASKING)).toBeTruthy());
    expect(asked).toHaveBeenCalledWith(WELCOME_API_PATH);
    fireEvent.click(page.getByText("Second?"));
    expect(chosen).toEqual(["Second?"]);
    expect(asked).toHaveBeenCalledTimes(2);
  });

  test("a question built from the department's data says where to check its answer", async () => {
    asked.mockImplementation((path: string) =>
      Promise.resolve(
        path === FROM_DATA_API_PATH
          ? { ok: true, data: { questions: [{ question: "How many ticket are there?", check_in: "Freshdesk" }] } }
          : { ok: false },
      ),
    );
    const chosen: string[] = [];
    const page = render(<AskWelcome onChoose={(one) => chosen.push(one)} />);
    await waitFor(() => expect(page.getByText(FROM_YOUR_DATA)).toBeTruthy());
    expect(page.queryByText(TRY_ASKING)).toBeNull();
    expect(page.container.textContent).toContain(`${CHECK_IN} Freshdesk.`);
    fireEvent.click(page.getByText("How many ticket are there?"));
    expect(chosen).toEqual(["How many ticket are there?"]);
  });

  test("a question from data with no system to check it in is not drawn", () => {
    expect(readFromData({ questions: [{ question: "Q?", check_in: "" }, { question: "R?" }, 3] })).toEqual([]);
    expect(readFromData(null)).toEqual([]);
  });

  test("a route that sends none, or does not answer, leaves nothing on the page", async () => {
    asked.mockResolvedValue({ ok: false });
    const page = render(<AskWelcome onChoose={() => undefined} />);
    await waitFor(() => expect(asked).toHaveBeenCalled());
    expect(page.container.textContent).toBe("");
  });
});
