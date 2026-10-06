/**
 * Add an API: the submit form sends the body the route declares and draws the API's problems by
 * field, the operations offered are the pasted document's own, and a definition is approved only
 * through its confirmation by a reader the API says may decide it.
 *
 * Task ids: M11.7.8
 */

import { fireEvent, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { CUSTOM_CONNECTORS_PATH } from "../src/pages/CustomConnectors.route";
import {
  APPROVE_LABEL,
  BLANK_CEILING,
  BLANK_DEPARTMENT,
  BLANK_DOCUMENT,
  BLANK_LABEL,
  BLANK_NAME,
  DEFINITIONS_API_PATH,
  SUBMIT_LABEL,
  readOperations,
  type Definition,
  type DefinitionsPage,
} from "../src/pages/connectors/CustomConnectorsPage";
import { button, json, mountPage, settled, type Answer } from "./support/pageHarness";
import { backendModelFields } from "./support/python";
import { installRadixStubs } from "./support/radix";
import { confirmWith } from "./support/rowMenu";

const LIST = `GET /api/v1${DEFINITIONS_API_PATH}`;
const SUBMIT = `POST /api/v1${DEFINITIONS_API_PATH}`;
const REVIEW = `POST /api/v1${DEFINITIONS_API_PATH}/widgets_api/review`;

const DOCUMENT = JSON.stringify({
  paths: {
    "/widgets": { get: { operationId: "listWidgets" } },
    "/widgets/{id}": { get: { operationId: "getWidget" }, delete: { operationId: "dropWidget" } },
  },
});

beforeAll(() => {
  installRadixStubs();
});

function definition(overrides: Partial<Definition> = {}): Definition {
  return {
    name: "widgets_api",
    label: "Widgets",
    state: "unreviewed",
    revision: 3,
    department: "finance",
    key_scheme: "bearer",
    ceiling_per_minute: 60,
    ceiling_per_day: null,
    ceiling_cited: "https://vendor.example/limits",
    entities: [
      {
        entity: "widget",
        list_operation: "listWidgets",
        one_operation: "getWidget",
        id_path: "id",
        named_by: "code",
        description: "Widgets by code",
        fields: [{ target: "code", source_path: "code", classification: "internal", kept: "label" }],
      },
    ],
    document: { openapi: "3.0.3" },
    submitted_by: "u_definer",
    submitted_at: "2019-03-06T08:30:00Z",
    reviewed_by: null,
    reviewable: true,
    offered: false,
    ...overrides,
  };
}

function page(definitions: Definition[]): DefinitionsPage {
  return {
    definitions,
    classifications: ["public", "internal", "confidential", "restricted"],
    shapes: ["identifier", "join_key", "status", "timestamp", "label"],
    schemes: ["bearer", "basic_key_as_user", "none"],
    review: "REVIEW-SENTINEL",
  };
}

/** Every field the form judges blank, filled, so a submit reaches the API. */
function fill(container: HTMLElement): void {
  const set = (id: string, value: string) => {
    fireEvent.change(container.querySelector(`#custom-connector-${id}`) as HTMLInputElement, { target: { value } });
  };
  set("name", "widgets_api");
  set("label", "Widgets");
  set("department", "finance");
  set("document", DOCUMENT);
  set("minute", "60");
  set("cited", "https://vendor.example/limits");
}

async function mounted(answers: Record<string, Answer>) {
  return mountPage(
    CUSTOM_CONNECTORS_PATH,
    async () => {
      const { CustomConnectorsPage } = await import("../src/pages/connectors/CustomConnectorsPage");
      return <CustomConnectorsPage />;
    },
    answers,
  );
}

describe("the Add an API page", () => {
  test("the operations offered are the pasted document's GETs and nothing else", () => {
    // What breaks if this is deleted: a person is offered a write as a list operation, or offered
    // nothing to choose from a document the page could not read.
    expect(readOperations(DOCUMENT)).toEqual(["getWidget", "listWidgets"]);
    expect(readOperations("not json")).toEqual([]);
  });

  test("the form sends every field the route declares and draws a refused ceiling by its field", async () => {
    // What breaks if this is deleted: the form sends a body the route refuses whole, or a problem
    // the API named for the ceiling is shown nowhere near it.
    const { container, sent } = await mounted({
      [LIST]: () => json(page([])),
      [SUBMIT]: () =>
        json({ problems: [{ field: "ceiling", code: "missing", message: "CEILING-SENTINEL" }] }, 422),
    });
    fill(container);
    fireEvent.click(button(container, SUBMIT_LABEL));
    await waitFor(() => {
      expect(container.textContent).toContain("CEILING-SENTINEL");
    });
    const body = sent.find((one) => one.method === "POST")?.body as Record<string, unknown>;
    expect(Object.keys(body).sort()).toEqual(
      backendModelFields("src/brain/custom_connector_routes.py", "DefinitionAsked").sort(),
    );
    const entity = (body["entities"] as Record<string, unknown>[])[0] ?? {};
    expect(Object.keys(entity).sort()).toEqual(
      backendModelFields("src/brain/custom_connector_routes.py", "EntityAsked").sort(),
    );
    expect(container.querySelector('[aria-invalid="true"]')).toBeNull();
  });

  test("a form sent blank says what to fill in beside its fields and sends nothing", async () => {
    // What breaks if this is deleted: an empty definition sent for the API to refuse, which is a
    // request a person made by pressing once on an empty page. The sibling above sends a filled one.
    const { container, sent } = await mounted({ [LIST]: () => json(page([])) });
    fireEvent.click(button(container, SUBMIT_LABEL));
    await waitFor(() => {
      expect(container.textContent).toContain(BLANK_NAME);
    });
    for (const said of [BLANK_LABEL, BLANK_DEPARTMENT, BLANK_DOCUMENT, BLANK_CEILING]) {
      expect(container.textContent).toContain(said);
    }
    expect(sent.filter((one) => one.method === "POST")).toEqual([]);
  });

  test("a definition is approved only through its confirmation, naming the revision read", async () => {
    // What breaks if this is deleted: an approval is sent with no confirmation, or on a revision
    // other than the one on the screen, which the API would approve unread.
    const { container, sent } = await mounted({
      [LIST]: () => json(page([definition()])),
      [REVIEW]: () => json({ definition: definition({ state: "approved", reviewable: false }), told: "TOLD" }),
    });
    await settled(container);
    fireEvent.click(button(container, APPROVE_LABEL));
    expect(sent.filter((one) => one.method === "POST")).toEqual([]);
    await confirmWith(APPROVE_LABEL);
    await waitFor(() => {
      expect(sent.find((one) => one.method === "POST")?.body).toEqual({ approve: true, revision: 3 });
    });
  });

  test("a reader the API says may not decide a definition is offered no decision", async () => {
    // What breaks if this is deleted: a submitter is drawn an Approve button on their own.
    const { container } = await mounted({ [LIST]: () => json(page([definition({ reviewable: false })])) });
    await settled(container);
    expect(() => button(container, APPROVE_LABEL)).toThrow();
    expect(container.textContent).toContain("Waiting for review");
  });
});
