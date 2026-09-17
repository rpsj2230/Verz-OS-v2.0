/**
 * The install's names and logo, from the served configuration document to the header.
 *
 * `brain.console_static.served_brand` sends `INSTALL_COMPANY_NAME`, `INSTALL_PRODUCT_NAME` and
 * `INSTALL_LOGO_URL`. The console's half is held here: it reads the three names the server writes,
 * draws a logo only from an address an image may safely load, and falls back to the product's own
 * title rather than a blank header when the document carries none.
 *
 * Task ids: M41.1.4
 */

import { describe, expect, test, vi } from "vitest";
import { CONFIG_GLOBAL } from "../src/config";
import { ISSUER } from "./support/auth";
import { extractOne, readRepoFile } from "./support/repo";

async function freshConfig(brand: unknown): Promise<typeof import("../src/config")> {
  vi.resetModules();
  vi.stubGlobal(CONFIG_GLOBAL, Object.freeze({ issuer: ISSUER, brand }));
  return await import("../src/config");
}

describe("reading the served brand", () => {
  test("the console reads the three names the server writes", async () => {
    // What breaks if this is deleted: the two sides spelling a name differently, so every install's
    // header says the product's own title and nobody reports it, because it reads fine.
    const source = readRepoFile("src/brain/console_static.py");
    const body = extractOne(source, /def served_brand[\s\S]*?return \{([\s\S]*?)\n {4}\}/, "served_brand's document");
    const served = [...body.matchAll(/"(\w+)":/g)].map((match) => match[1]);

    expect(served).toEqual(["companyName", "productName", "logoUrl"]);
  });

  test("a served brand is drawn as the company and the product together", async () => {
    // What breaks if this is deleted: the sibling of the refusals below. A reader that dropped every
    // brand would pass them and the header would never carry a company's name.
    const { config, brandTitle } = await freshConfig({
      companyName: "Northwind Trading",
      productName: "Knowledge Desk",
      logoUrl: "https://assets.northwind.example/logo.svg",
    });

    expect(brandTitle(config.brand)).toBe("Northwind Trading Knowledge Desk");
    expect(config.brand.logoUrl).toBe("https://assets.northwind.example/logo.svg");
  });

  test("a logo from a scheme an image should not load is dropped, and no brand is the product's title", async () => {
    // What breaks if this is deleted: a `javascript:` or protocol-relative address put in an image
    // source from a setting, or a header left blank on an install that set nothing.
    const { drawableLogo, brandTitle, config, UNBRANDED_TITLE } = await freshConfig(undefined);

    expect(drawableLogo("javascript:alert(1)")).toBe("");
    expect(drawableLogo("//elsewhere.example/logo.svg")).toBe("");
    expect(drawableLogo("http://plain.example/logo.svg")).toBe("");
    expect(drawableLogo("/icon.svg")).toBe("/icon.svg");
    expect(brandTitle(config.brand)).toBe(UNBRANDED_TITLE);
  });
});
