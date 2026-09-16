/**
 * The Prompts screen: the system instructions drawn with no control, an agent's instructions with
 * who set them, an edit checked for length before it can be sent, confirmed, posted with the hash
 * the editor was shown, and re-read.
 *
 * Mounted on its own at its address, because the route table is a shared file this change does not
 * edit. The shapes are read from `brain.prompt_routes` itself.
 *
 * Task ids: M27.8.9
 */

import { fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import {
  EDIT,
  EDITING_SWITCHED_OFF,
  GIVE_BACK,
  NO_MODEL_IS_CALLED_YET,
  NOT_INSTALLED,
  PROMPTS_API_PATH,
  PROMPTS_PATH,
  SAVE,
  SYSTEM_INSTRUCTIONS_ARE_PRODUCT_TEXT,
} from "../src/pages/promptsQuery";
import { button, json, mountPage, settled, type Answer } from "./support/pageHarness";
import { backendModelFields } from "./support/python";

const LIST = `GET /api/v1${PROMPTS_API_PATH}`;
const EDIT_ROUTE = `POST /api/v1${PROMPTS_API_PATH}/pricing_desk`;
const ROUTES = "src/brain/prompt_routes.py";

function agent(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    agent_id: "pricing_desk",
    display_name: "Pricing desk",
    department: null,
    instructions: "IN-FORCE-LINE-ONE\nIN-FORCE-LINE-TWO",
    template_id: "pricing_desk",
    template_version: 3,
    template_instructions: "TEMPLATE-SENTENCE",
    overridden: true,
    set_by: "u_installer",
    set_at: "2019-03-05T09:00:00Z",
    effective_hash: "HASH-SHOWN",
    installed: true,
    editable: true,
    ...overrides,
  };
}

function page(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    house_rules: ["HOUSE-RULE-ONE"],
    output_lengths: [{ name: "brief", instruction: "LENGTH-SENTENCE" }],
    agents: [agent()],
    max_chars: 40,
    editing_switched_on: true,
    system_instructions_are_product_text: true,
    no_model_is_called_yet: true,
    only_the_last_change_is_kept: true,
    ...overrides,
  };
}

async function promptsPage(answers: Record<string, Answer>) {
  return mountPage(
    PROMPTS_PATH,
    async () => {
      const { Prompts } = await import("../src/pages/Prompts");
      return <Prompts />;
    },
    answers,
  );
}

describe("what the Prompts screen draws", () => {
  test("the system instructions with no control beside them, and an agent's with who set them", async () => {
    // What breaks if this is deleted: the house rules drawn as though an install could change
    // them, or an agent's instructions drawn with no word on whose they are.
    const { container } = await promptsPage({ [LIST]: () => json(page()) });

    const text = container.textContent ?? "";
    expect(text).toContain("HOUSE-RULE-ONE");
    expect(text).toContain("LENGTH-SENTENCE");
    expect(text).toContain(SYSTEM_INSTRUCTIONS_ARE_PRODUCT_TEXT);
    expect(text).toContain(NO_MODEL_IS_CALLED_YET);
    expect(text).toContain("set by u_installer");
    expect(container.querySelector("#prompts-system button")).toBeNull();
    const lines = [...container.querySelectorAll("p")].map((one) => one.textContent);
    expect(lines).toContain("IN-FORCE-LINE-ONE");
    expect(lines).toContain("IN-FORCE-LINE-TWO");
  });

  test("an agent with no install says why and offers nothing, and editing switched off says where", async () => {
    // What breaks if this is deleted: an Edit button beside an agent the API refuses every time.
    const { container } = await promptsPage({
      [LIST]: () =>
        json(page({ editing_switched_on: false, agents: [agent({ installed: false, editable: false, overridden: false })] })),
    });

    expect(container.textContent).toContain(NOT_INSTALLED);
    expect(container.textContent).toContain(EDITING_SWITCHED_OFF);
    expect(container.querySelectorAll("button")).toHaveLength(0);
  });
});

describe("an edit", () => {
  test("cannot be sent over the stated length, and is confirmed, posted with the shown hash, and re-read", async () => {
    // What breaks if this is deleted: instructions over the limit sent to be refused, an edit
    // sent without the hash that stops two administrators overwriting each other, or a page that
    // goes on drawing the old instructions.
    let instructions = "IN-FORCE-LINE-ONE";
    const { container, sent } = await promptsPage({
      [LIST]: () => json(page({ agents: [agent({ instructions })] })),
      [EDIT_ROUTE]: (body) => {
        instructions = (body as { instructions: string }).instructions;
        return json(agent({ instructions, set_by: "u_admin" }));
      },
    });

    fireEvent.click(button(container, `${EDIT}: Pricing desk`));
    const field = container.querySelector("textarea") as HTMLTextAreaElement;
    fireEvent.change(field, { target: { value: "x".repeat(41) } });
    expect(container.textContent).toContain("at most 40 characters");
    expect((button(container, SAVE) as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(field, { target: { value: "NEW-INSTRUCTIONS" } });
    fireEvent.click(button(container, SAVE));
    expect(container.querySelector(".confirm")?.textContent).toMatch(/from the next request/i);
    const confirm = [...container.querySelectorAll(".confirm button")].find((one) => one.textContent === SAVE);
    fireEvent.click(confirm as HTMLButtonElement);

    await waitFor(() => {
      expect(container.textContent).toContain("instructions were replaced");
    });
    await settled(container);
    expect(sent.filter((one) => one.method === "POST").map((one) => one.body)).toEqual([
      { instructions: "NEW-INSTRUCTIONS", expected_hash: "HASH-SHOWN" },
    ]);
    expect(container.textContent).toContain("NEW-INSTRUCTIONS");
  });

  test("giving back is offered only for instructions this install changed", async () => {
    // What breaks if this is deleted: a give-back offered on an agent already using its
    // template's instructions, which the API refuses every time.
    const changed = await promptsPage({ [LIST]: () => json(page()) });
    expect(button(changed.container, GIVE_BACK)).toBeDefined();

    const template = await promptsPage({ [LIST]: () => json(page({ agents: [agent({ overridden: false })] })) });
    expect([...template.container.querySelectorAll("button")].map((one) => one.textContent)).toEqual([EDIT]);
  });

  test("every field the page reads is a field the route declares", () => {
    // What breaks if this is deleted: a renamed field that the page goes on reading as empty.
    expect(Object.keys(page()).sort()).toEqual(backendModelFields(ROUTES, "PromptsPage").sort());
    expect(Object.keys(agent()).sort()).toEqual(backendModelFields(ROUTES, "AgentInstructionsView").sort());
  });
});
