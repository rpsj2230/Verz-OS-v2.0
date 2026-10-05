/**
 * The Website widget card's reading of the marking route, and the route's own description.
 *
 * The card draws what `readPublicMarking` reads, so a field the API renamed would draw "Not public"
 * over a document visitors are being answered from. Held here against the API's own description of
 * the route, and the sentence the card says is held against what it was given.
 *
 * Task ids: M10.7.2
 */

import { describe, expect, test } from "vitest";
import { publicWords, readPublicMarking } from "../src/pages/knowledge/PublicMarkingCard";
import { publicPath } from "../src/pages/knowledgeLifecycleQuery";
import { declaredPropertyNames, declaredRequestBodySchema, declaredResponseSchema } from "./support/openapi";

const OPERATION = "/api/v1/knowledge/items/{item_id}/public";

describe("the Website widget card", () => {
  test("reads every field the route declares, and asks with the one field it takes", () => {
    expect(declaredPropertyNames(declaredResponseSchema(OPERATION, "get")).sort()).toEqual(
      ["item_id", "marked_at", "marked_by", "marked_by_name", "may_change", "public", "says"].sort(),
    );
    expect(declaredPropertyNames(declaredRequestBodySchema(OPERATION, "put"))).toEqual(["public"]);
    expect(`/api/v1${publicPath("upload.x")}`).toBe("/api/v1/knowledge/items/upload.x/public");
  });

  test("a marked document says since when and who made it public", () => {
    const marking = readPublicMarking({
      item_id: "upload.x",
      public: true,
      marked_by: "u_admin",
      marked_by_name: "An Admin",
      marked_at: "2019-03-04T09:00:00Z",
      may_change: true,
      says: null,
    });
    expect(marking).not.toBeNull();
    expect(publicWords(marking!)).toBe("Public, since 4 Mar 2019, made so by An Admin");
  });

  test("an unmarked document says so, and a refusal's sentence is kept for the card to show", () => {
    const marking = readPublicMarking({
      item_id: "upload.x",
      public: false,
      marked_by: null,
      marked_by_name: null,
      marked_at: null,
      may_change: false,
      says: "You decide what is public for your own department's documents only.",
    });
    expect(marking?.mayChange).toBe(false);
    expect(marking?.says).toBe("You decide what is public for your own department's documents only.");
    expect(publicWords(marking!)).toBe("Not public");
  });

  test("an answer that is not a marking is read as nothing, so no button is drawn over it", () => {
    expect(readPublicMarking(null)).toBeNull();
    expect(readPublicMarking({ public: "yes", may_change: true })).toBeNull();
    expect(readPublicMarking({ public: true })).toBeNull();
  });
});
