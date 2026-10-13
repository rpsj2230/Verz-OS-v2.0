/**
 * An agent's Workflows card: a part of the agent in its own right, drawn with its empty state until a
 * workflow can be stored, so the part is on the page and says so rather than being absent.
 *
 * Task ids: M39.1.1.1
 */

import { render } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { NO_WORKFLOWS, WORKFLOWS_HEADING, WorkflowsCard } from "../src/pages/agents/AgentProfile";
import { installRadixStubs } from "./support/radix";

beforeAll(() => {
  installRadixStubs();
});

describe("the workflows card", () => {
  test("a workflows part with nothing stored says what a workflow is and that none is stored", () => {
    // What breaks if this is deleted: the part decided on needs item 180 goes missing from the page, so
    // an agent reads as having no such thing rather than the product not having built it yet.
    const { container } = render(<WorkflowsCard />);
    expect(container.textContent).toContain(WORKFLOWS_HEADING);
    expect(container.textContent).toContain(NO_WORKFLOWS);
    expect(NO_WORKFLOWS).toContain("No workflows are stored");
  });
});
