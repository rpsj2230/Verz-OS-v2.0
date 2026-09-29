/**
 * An agent's tools and connectors on its Profile, with attach and detach for whoever holds the
 * department's tool or connector role.
 *
 * **Everything offered is the route's answer.** The tools listed to attach are the ones the agent's
 * ceiling and the reader's reach both admit (`brain.agent_attachment_routes`), the controls appear
 * only where the API said the reader may press, and a refusal is the API's own sentence.
 *
 * **Every press is confirmed**, and the dialog says what changes: a run is handed the tools the
 * agent carries from the next question on, and the press is on the audit log.
 *
 * Task ids: M39.8.6, M39.2.1.2, M39.1.1.3
 */

import { useId, useState } from "react";
import { request } from "../../api/client";
import { useResource } from "../../api/useResource";
import { ConfirmDialog, FailureState, LoadingState, Note } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Label } from "../../components/ui/label";

export const LOADING_TOOLS = "Loading what this agent may call.";
export const NOTHING_CARRIED = "It carries no tool this system has.";

export function agentAttachmentsApiPath(agentId: string): string {
  return `/agents/${encodeURIComponent(agentId)}/attachments`;
}

interface Named {
  readonly name: string;
  readonly source: string;
  readonly description: string;
}

interface Attachments {
  readonly carried: readonly Named[];
  readonly carriedConnectors: readonly string[];
  readonly tools: readonly Named[];
  readonly connectors: readonly string[];
  readonly mayChangeTools: boolean;
  readonly mayChangeConnectors: boolean;
}

type Fields = Readonly<Record<string, unknown>>;

function fieldsOf(value: unknown): Fields | null {
  // A cast at the boundary, where proving a structural match buys nothing: every field is read
  // back through a type test below.
  return typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Fields) : null;
}

function names(value: unknown): Named[] {
  return (Array.isArray(value) ? (value as readonly unknown[]) : [])
    .map(fieldsOf)
    .filter((one): one is Fields => one !== null && typeof one["name"] === "string")
    .map((one) => ({
      name: String(one["name"]),
      source: typeof one["source"] === "string" ? one["source"] : "",
      description: typeof one["description"] === "string" ? one["description"] : "",
    }));
}

function words(value: unknown): string[] {
  return (Array.isArray(value) ? (value as readonly unknown[]) : []).filter((one): one is string => typeof one === "string");
}

/** The attachments read out of a body, or null when the body is not an object at all. */
export function readAttachments(payload: unknown): Attachments | null {
  const fields = fieldsOf(payload);
  if (fields === null) {
    return null;
  }
  return {
    carried: names(fields["carried"]),
    carriedConnectors: words(fields["carried_connectors"]),
    tools: names(fields["tools"]),
    connectors: words(fields["connectors"]),
    mayChangeTools: fields["may_change_tools"] === true,
    mayChangeConnectors: fields["may_change_connectors"] === true,
  };
}

interface Press {
  readonly part: "tool" | "connector";
  readonly reference: string;
  readonly attached: boolean;
}

function Chooser({
  label,
  options,
  verb,
  onPick,
}: {
  readonly label: string;
  readonly options: readonly { readonly value: string; readonly words: string }[];
  readonly verb: string;
  readonly onPick: (value: string) => void;
}) {
  const id = useId();
  const [picked, setPicked] = useState(options[0]?.value ?? "");
  if (options.length === 0) {
    return null;
  }
  const chosen = options.some((one) => one.value === picked) ? picked : (options[0]?.value ?? "");
  return (
    <form
      className="flex flex-wrap items-end gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        if (chosen !== "") {
          onPick(chosen);
        }
      }}
    >
      <div className="flex min-w-0 flex-col gap-1">
        <Label htmlFor={id}>{label}</Label>
        <select id={id} className="h-8 min-w-0 rounded-md border border-input bg-transparent px-2 text-[12.5px] text-ink" value={chosen} onChange={(event) => setPicked(event.target.value)}>
          {options.map((one) => (
            <option key={one.value} value={one.value}>
              {one.words}
            </option>
          ))}
        </select>
      </div>
      <Button type="submit" size="xs" variant="outline">
        {verb}
      </Button>
    </form>
  );
}

export function AgentTools({ agentId }: { readonly agentId: string }) {
  const [version, setVersion] = useState(0);
  const answer = useResource<unknown>(agentAttachmentsApiPath(agentId), version);
  const [asking, setAsking] = useState<Press | null>(null);
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState<string | null>(null);

  if (answer.failure !== null) {
    return <FailureState failure={answer.failure} />;
  }
  const attachments = answer.data === null ? null : readAttachments(answer.data);
  if (answer.busy || attachments === null) {
    return <LoadingState label={LOADING_TOOLS} />;
  }

  const decide = async (one: Press): Promise<void> => {
    setBusy(true);
    const result = await request<unknown>(agentAttachmentsApiPath(agentId), { method: "POST", body: one });
    setBusy(false);
    setAsking(null);
    setSaid(result.ok ? null : result.failure.message);
    setVersion((count) => count + 1);
  };

  const toolWords = (one: Named) => (one.description === "" ? one.name : `${one.description} (${one.name})`);
  return (
    <div data-slot="agent-tools" className="flex min-w-0 flex-col gap-2 text-[12.5px]">
      {said === null ? null : (
        <p role="alert" className="m-0 text-crit">
          {said}
        </p>
      )}
      {attachments.carried.length === 0 ? (
        <Note>{NOTHING_CARRIED}</Note>
      ) : (
        <ul data-slot="tools-carried" className="m-0 flex list-none flex-col p-0">
          {attachments.carried.map((one) => (
            <li key={one.name} className="flex flex-wrap items-center gap-2 border-b border-line py-1.5 last:border-b-0">
              <span className="min-w-0 text-ink [overflow-wrap:anywhere]">{toolWords(one)}</span>
              {attachments.mayChangeTools ? (
                <Button className="ml-auto" variant="ghost" size="xs" onClick={() => setAsking({ part: "tool", reference: one.name, attached: false })}>
                  Detach
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {attachments.mayChangeTools ? (
        <Chooser
          label="Attach a tool"
          verb="Attach"
          options={attachments.tools.map((one) => ({ value: one.name, words: toolWords(one) }))}
          onPick={(value) => setAsking({ part: "tool", reference: value, attached: true })}
        />
      ) : null}
      {attachments.mayChangeConnectors ? (
        <>
          <Chooser
            label="Attach a connector's tools"
            verb="Attach"
            options={attachments.connectors.map((one) => ({ value: one, words: one }))}
            onPick={(value) => setAsking({ part: "connector", reference: value, attached: true })}
          />
          <Chooser
            label="Detach a connector's tools"
            verb="Detach"
            options={attachments.carriedConnectors.map((one) => ({ value: one, words: one }))}
            onPick={(value) => setAsking({ part: "connector", reference: value, attached: false })}
          />
        </>
      ) : null}
      <ConfirmDialog
        open={asking !== null}
        question={
          asking === null
            ? ""
            : `${asking.attached ? "Attach" : "Detach"} ${asking.part === "tool" ? asking.reference : `every tool of ${asking.reference}`}?`
        }
        consequence={
          asking?.attached === false
            ? "Its runs stop being handed it from the next question on. The change is on the audit log."
            : "Its runs are handed it from the next question on, within what each person asking may reach. The change is on the audit log."
        }
        confirmLabel={asking?.attached === false ? "Detach" : "Attach"}
        cancelLabel="Leave it"
        danger={asking?.attached === false}
        busy={busy}
        onConfirm={() => {
          if (asking !== null) {
            void decide(asking);
          }
        }}
        onCancel={() => setAsking(null)}
      />
    </div>
  );
}
