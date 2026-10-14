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

import { AskWelcome, readWelcome, TRY_ASKING, WELCOME_API_PATH } from "../src/pages/AskWelcome";

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
    asked.mockResolvedValue({ ok: true, data: { questions: ["First?", "Second?"] } });
    const chosen: string[] = [];
    const page = render(<AskWelcome onChoose={(one) => chosen.push(one)} />);
    await waitFor(() => expect(page.getByText(TRY_ASKING)).toBeTruthy());
    expect(asked).toHaveBeenCalledWith(WELCOME_API_PATH);
    fireEvent.click(page.getByText("Second?"));
    expect(chosen).toEqual(["Second?"]);
    expect(asked).toHaveBeenCalledTimes(1);
  });

  test("a route that sends none, or does not answer, leaves nothing on the page", async () => {
    asked.mockResolvedValue({ ok: false });
    const page = render(<AskWelcome onChoose={() => undefined} />);
    await waitFor(() => expect(asked).toHaveBeenCalled());
    expect(page.container.textContent).toBe("");
  });
});
