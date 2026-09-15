// The Activepieces piece: one action, "Call a tool", which sends what `call.ts` builds.
//
// **Compiled under strict settings against `@activepieces/pieces-framework` 0.7.42**, the
// version the Activepieces 0.39.5 source tree declares for itself, and loaded by
// `test/load.test.ts` the way that release's engine loads a piece: a CommonJS `require` of the
// package, then the one export whose constructor is `Piece`. `package.json` and the README say
// why that version and not a newer one.
//
// `fetch` rather than the framework's HTTP client, deliberately. The sandbox sets HTTP_PROXY
// for every outbound request so the egress allowlist applies, and the application is reached
// over the `tool-api` network rather than through the proxy, which would refuse it.
//
// No import attribute on the JSON import, unlike the tests. This file compiles to CommonJS,
// where TypeScript refuses one, and it is never run by Node's type stripping directly.

import { createAction, createPiece, PieceAuth, Property } from "@activepieces/pieces-framework";
import contract from "../contract.json";
import { buildToolCall } from "./call.ts";

export const brainAuth = PieceAuth.CustomAuth({
  required: true,
  props: {
    baseUrl: Property.ShortText({
      displayName: "Application address on the tool network",
      required: true,
    }),
    credential: PieceAuth.SecretText({
      displayName: "Automation credential",
      required: true,
    }),
  },
});

export const callTool = createAction({
  auth: brainAuth,
  name: "call_tool",
  displayName: "Call a tool",
  description: "Run one tool as this automation's owner, at their reach narrowed by the automation's own",
  props: {
    tool: Property.ShortText({ displayName: "Tool", required: true }),
    arguments: Property.Json({ displayName: "Arguments", required: false }),
  },
  async run(context) {
    const request = buildToolCall(
      contract,
      context.auth.baseUrl,
      context.auth.credential,
      context.propsValue.tool,
      context.propsValue.arguments ?? {},
    );
    const response = await fetch(request.url, {
      method: request.method,
      headers: request.headers,
      body: request.body,
    });
    if (!response.ok) {
      // The status only. The application's refusal says nothing about why, on purpose, and a
      // step that tried to say more would be guessing.
      throw new Error(`the tool call was refused (${response.status})`);
    }
    return await response.json();
  },
});

export const brain = createPiece({
  displayName: "Company Brain",
  auth: brainAuth,
  minimumSupportedRelease: "0.39.0",
  logoUrl: "",
  authors: [],
  actions: [callTool],
  triggers: [],
});
