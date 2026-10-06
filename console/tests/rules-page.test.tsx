/**
 * Quick answers: each rule drawn by its words, where it answers and the column it answers with; a
 * candidate tried and its answer said, saving nothing; a rule added and the list read again; a
 * refused addition said with what was typed kept; a retirement confirmed and posted; an empty list
 * and an unreadable answer each said in a sentence; and every body the page sends holding exactly
 * the fields `brain.rule_routes` reads.
 *
 * Mounted on its own at its address. The shapes are read from `brain.rule_routes`, so a renamed
 * field fails here rather than on an install.
 *
 * Task ids: M6.5.1
 */

import { act, fireEvent, screen, within } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  ADD,
  NO_RULES,
  RETIRE,
  retireApiPath,
  RULES_API_PATH,
  RULES_PATH,
  TEMPLATE_LABEL,
  TRY,
  TRY_API_PATH,
  UNREADABLE_ANSWER,
  WHOLE_COMPANY,
  FILL_EVERY_BOX,
  NAME_LABEL,
  SLOT_LABEL,
  ENTITY_LABEL,
  MATCH_LABEL,
  ANSWER_LABEL,
  QUESTION_LABEL,
  NEEDS_A_QUESTION,
} from "../src/pages/rulesQuery";
import { button, json, mountPage, type Answer } from "./support/pageHarness";
import { backendModelFields } from "./support/python";
import { installRadixStubs } from "./support/radix";

beforeAll(() => {
  installRadixStubs();
});

const ROUTES = "src/brain/rule_routes.py";
const LIST = `GET /api/v1${RULES_API_PATH}`;
const ADDING = `POST /api/v1${RULES_API_PATH}`;
const TRYING = `POST /api/v1${TRY_API_PATH}`;
const RULE_ID = "acceptance_a__rate";
const RETIRING = `POST /api/v1${retireApiPath(RULE_ID)}`;

function rule(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    rule_id: RULE_ID,
    department: "acceptance_a",
    template: "what is the rate for {name}",
    slot: "name",
    source: "tables",
    entity: "price_list",
    match_field: "name",
    answer_field: "sell_price",
    created_by: "u_admin",
    created_at: "2019-03-04T09:00:00Z",
    ...overrides,
  };
}

function listed(rules: Record<string, unknown>[] = [rule()]): Record<string, unknown> {
  return { rules, own_department: "acceptance_a", may_write_install: false, told: "The quick answers you may change." };
}

async function rulesPage(answers: Record<string, Answer>) {
  return mountPage(
    RULES_PATH,
    async () => {
      const { Rules } = await import("../src/pages/Rules");
      return <Rules />;
    },
    answers,
  );
}

function type(container: HTMLElement, label: string, value: string): void {
  fireEvent.change(within(container).getByLabelText(label), { target: { value } });
}

function fill(container: HTMLElement): void {
  type(container, NAME_LABEL, "rate");
  type(container, TEMPLATE_LABEL, "what is the rate for {name}");
  type(container, SLOT_LABEL, "name");
  type(container, ENTITY_LABEL, "price_list");
  type(container, MATCH_LABEL, "name");
  type(container, ANSWER_LABEL, "sell_price");
}

/** The page's text with the Advanced section taken out, which is what a person reads. */
function readable(container: HTMLElement): string {
  const copy = container.cloneNode(true) as HTMLElement;
  copy.querySelectorAll('[data-slot="advanced"]').forEach((one) => {
    one.remove();
  });
  return copy.textContent ?? "";
}

describe("what the Quick answers screen draws", () => {
  test("a rule by its words, where it answers and what it answers with, and its id in Advanced alone", async () => {
    // What breaks if this is deleted: a rule drawn without its words or its department, which asks an
    // administrator to retire something they cannot recognise.
    const { container } = await rulesPage({ [LIST]: () => json(listed([rule(), rule({ rule_id: "global", department: null, template: "who owns {name}" })])) });

    const text = readable(container);
    expect(text).toContain("what is the rate for {name}");
    expect(text).toContain("acceptance_a");
    expect(text).toContain("sell_price");
    expect(text).toContain("price_list");
    expect(text).toContain(WHOLE_COMPANY);
    expect(text).not.toContain(RULE_ID);
    expect(container.querySelector('[data-slot="advanced"]')?.textContent ?? "").toContain(RULE_ID);
  });

  test("an empty list is a sentence and an unreadable answer says so", async () => {
    // What breaks if this is deleted: an empty list drawn as a blank page, which reads as a screen
    // that failed, or a shape this console does not know drawn as no rules.
    const empty = await rulesPage({ [LIST]: () => json(listed([])) });
    expect(empty.container.textContent).toContain(NO_RULES);

    const unreadable = await rulesPage({ [LIST]: () => json({ rules: "no" }) });
    expect(unreadable.container.textContent).toContain(UNREADABLE_ANSWER);
  });
});

describe("what the Quick answers screen sends", () => {
  test("trying a rule posts the rule and the question, says the answer, and saves nothing", async () => {
    // What breaks if this is deleted: a Try button that adds the rule, or one whose answer is never
    // shown, so an administrator learns the rule is wrong from the people it answered.
    const { container, sent } = await rulesPage({
      [LIST]: () => json(listed([])),
      [TRYING]: () => json({ matches: true, answer: "ANSWER-SENTINEL", told: "The rule would answer this question with no model." }),
    });
    fill(container);
    fireEvent.click(button(container, TRY));
    expect(container.textContent).toContain(NEEDS_A_QUESTION);
    expect(sent.filter((one) => one.method === "POST")).toHaveLength(0);

    type(container, QUESTION_LABEL, "what is the rate for Acme");
    await act(async () => {
      fireEvent.click(button(container, TRY));
    });
    expect(await screen.findByText("ANSWER-SENTINEL")).toBeTruthy();
    const posts = sent.filter((one) => one.method === "POST");
    expect(posts.map((one) => one.path)).toEqual([`/api/v1${TRY_API_PATH}`]);
    expect(posts[0]?.body).toMatchObject({ name: "rate", department: "acceptance_a", question: "what is the rate for Acme", source: "tables" });
  });

  test("a blank box is said beside the form and nothing is sent", async () => {
    // What breaks if this is deleted: a half-written rule sent for the API to refuse, after which the
    // page has nothing in its own words to say.
    const { container, sent } = await rulesPage({ [LIST]: () => json(listed([])) });
    fireEvent.submit(container.querySelector("form") as HTMLFormElement);
    expect(container.textContent).toContain(FILL_EVERY_BOX);
    expect(sent.filter((one) => one.method === "POST")).toHaveLength(0);
  });

  test("adding a rule posts it and reads the list again; a refused one is said and keeps what was typed", async () => {
    // What breaks if this is deleted: an addition the page never re-reads, so it shows a list that is
    // not what the next question is answered from; or a refusal that clears the form.
    let added = false;
    const { container, sent } = await rulesPage({
      [LIST]: () => json(listed(added ? [rule()] : [])),
      [ADDING]: () => {
        added = true;
        return json({ done: true, rule_id: RULE_ID, told: "The rule is live and answers from the next question." });
      },
    });
    fill(container);
    await act(async () => {
      fireEvent.click(button(container, ADD));
    });
    expect(await screen.findByText("The rule is live and answers from the next question.")).toBeTruthy();
    expect(sent.filter((one) => one.method === "POST").map((one) => one.path)).toEqual([`/api/v1${RULES_API_PATH}`]);
    expect(sent.filter((one) => one.method === "GET").length).toBeGreaterThanOrEqual(2);

    const refused = await rulesPage({
      [LIST]: () => json(listed([])),
      [ADDING]: () => json({ done: false, rule_id: null, told: "TAKEN-SENTINEL" }),
    });
    fill(refused.container);
    await act(async () => {
      fireEvent.click(button(refused.container, ADD));
    });
    expect(await within(refused.container).findByText("TAKEN-SENTINEL")).toBeTruthy();
    expect((within(refused.container).getByLabelText(NAME_LABEL) as HTMLInputElement).value).toBe("rate");
  });

  test("retiring a rule is confirmed, posted to that rule, and the list read again", async () => {
    // What breaks if this is deleted: a Retire that posts to the wrong rule, or one with no
    // confirmation, which takes a rule out of every answer on one click.
    let retired = false;
    const { container, sent } = await rulesPage({
      [LIST]: () => json(listed(retired ? [] : [rule()])),
      [RETIRING]: () => {
        retired = true;
        return json({ done: true, rule_id: RULE_ID, told: "The rule is retired and answers nothing from the next question." });
      },
    });
    fireEvent.click(button(container, RETIRE));
    const dialog = await screen.findByRole("alertdialog");
    expect(sent.filter((one) => one.method === "POST")).toHaveLength(0);
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: RETIRE }));
    });
    expect(await screen.findByText(NO_RULES)).toBeTruthy();
    expect(sent.filter((one) => one.method === "POST").map((one) => one.path)).toEqual([`/api/v1${retireApiPath(RULE_ID)}`]);
  });

  test("every body the page sends holds exactly the fields the routes read", async () => {
    // What breaks if this is deleted: a field renamed in `brain.rule_routes` and not here, which the
    // routes refuse (they forbid unknown fields) on every addition from an install.
    const { container, sent } = await rulesPage({
      [LIST]: () => json(listed([])),
      [ADDING]: () => json({ done: true, rule_id: RULE_ID, told: "Added." }),
      [TRYING]: () => json({ matches: false, answer: null, told: "No." }),
    });
    fill(container);
    type(container, QUESTION_LABEL, "what is the rate for Acme");
    await act(async () => {
      fireEvent.click(button(container, TRY));
    });
    await act(async () => {
      fireEvent.click(button(container, ADD));
    });
    const [tried, adding] = sent.filter((one) => one.method === "POST");
    // `FastRuleTried` is `FastRuleAsked` and the question.
    const asked = backendModelFields(ROUTES, "FastRuleAsked");
    expect(Object.keys(adding?.body as object).sort()).toEqual([...asked].sort());
    expect(Object.keys(tried?.body as object).sort()).toEqual([...asked, ...backendModelFields(ROUTES, "FastRuleTried")].sort());
  });
});
