// The whole of what an automation step sends to the application: one tool name and one
// argument bag, with the automation's credential as a bearer. Nothing else.
//
// Written without a dependency, so the one thing this package decides can be tested by the
// Node that is already on a development machine, without the Activepieces toolchain. The
// shape is read from `contract.json`, and `tests/unit/test_automation_piece_package.py` holds
// that file equal to the route `brain.automation_routes` mounts and to the fields of
// `brain.ops.automation_piece.PieceStep`. So the three cannot drift apart silently: the route,
// the model a step is validated into, and the request this builds.
//
// **There is no address field, no principal and no capability in what a step sends.** The
// address is the application's, configured once in the piece's authentication, and a flow
// author choosing a tool cannot choose where the request goes. Who the step runs as is the
// automation's registered owner, decided by the application and never by the request.

export interface Contract {
  method: string;
  path: string;
  credential_header: string;
  credential_scheme: string;
  credential_prefix: string;
  body_fields: string[];
}

export interface ToolCallRequest {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: string;
}

export function buildToolCall(
  contract: Contract,
  baseUrl: string,
  credential: string,
  tool: string,
  args: Record<string, unknown>,
): ToolCallRequest {
  // Refused here as well as by the application, so a person's session token pasted into the
  // automation's credential field is never sent anywhere at all.
  if (!credential.startsWith(`${contract.credential_prefix}.`)) {
    throw new Error("this is not an automation credential");
  }
  const root = baseUrl.replace(/\/+$/, "");
  const body: Record<string, unknown> = { tool: tool, arguments: args };
  return {
    url: `${root}${contract.path}`,
    method: contract.method,
    headers: {
      [contract.credential_header]: `${contract.credential_scheme} ${credential}`,
      "content-type": "application/json",
    },
    body: JSON.stringify(body),
  };
}
