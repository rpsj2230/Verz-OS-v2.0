/**
 * Preview a run through an agent for the person on this page: choose an agent the reader may open,
 * and see what that person's run of it would be handed, worked out by the gate.
 *
 * **The same route the agent's own Profile asks**, `POST /agents/{agent_id}/preview`, which computes
 * the run at the person's reach narrowed by the agent's ceiling and answers a reader who may not
 * read grants as an agent that does not exist. The agents offered are the roster's, which is the
 * reader's own audience, so the choice lists nothing they may not open. Nothing is sent until an
 * agent is chosen, and the form says so first.
 *
 * Task ids: M39.3.1.4
 */

import { useId, useState, type FormEvent } from "react";
import { request } from "../../api/client";
import { useResource } from "../../api/useResource";
import { Button } from "../../components/ui/button";
import { Label } from "../../components/ui/label";
import { ROSTER_API_PATH, readRoster } from "../agentsQuery";
import { agentPreviewApiPath, readPreview, type Preview } from "../agents/agentCapabilitiesQuery";
import { rungWords } from "../agents/agentActions";

export const CHOOSE_AN_AGENT = "Choose which agent's run to preview.";
export const AGENT_FORMAT = "One of the agents you may open.";

export function PersonPreview({ principalId }: { readonly principalId: string }) {
  const selectId = useId();
  const roster = useResource<unknown>(`${ROSTER_API_PATH}?limit=100`);
  const entries = roster.data === null ? [] : (readRoster(roster.data)?.entries ?? []);
  const [agent, setAgent] = useState("");
  const [said, setSaid] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [shown, setShown] = useState<Preview | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (agent === "") {
      setSaid(CHOOSE_AN_AGENT);
      return;
    }
    setBusy(true);
    const result = await request<unknown>(agentPreviewApiPath(agent), { method: "POST", body: { person_id: principalId } });
    setBusy(false);
    if (!result.ok) {
      setShown(null);
      setSaid(result.failure.message);
      return;
    }
    setSaid(null);
    setShown(readPreview(result.data));
  };

  return (
    <div data-slot="person-preview" className="flex flex-col gap-2">
      <form onSubmit={(event) => void submit(event)} className="flex flex-col gap-1.5">
        <Label htmlFor={selectId}>Preview a run through an agent</Label>
        <div className="flex flex-wrap gap-2">
          <select
            id={selectId}
            value={agent}
            onChange={(event) => setAgent(event.target.value)}
            aria-describedby={`${selectId}-format`}
            className="h-9 max-w-72 min-w-0 rounded-md border border-input bg-transparent px-2.5 text-sm text-ink"
          >
            <option value="">Choose an agent</option>
            {entries.map((one) => (
              <option key={one.agentId} value={one.agentId}>
                {one.displayName}
              </option>
            ))}
          </select>
          <Button type="submit" size="sm" variant="outline" disabled={busy} className="min-h-11 sm:min-h-8">
            Preview
          </Button>
        </div>
        <span id={`${selectId}-format`} className="text-[11.5px] text-dim">
          {AGENT_FORMAT}
        </span>
      </form>
      {said === null ? null : (
        <p role="alert" className="m-0 text-[12px] text-crit">
          {said}
        </p>
      )}
      {shown === null ? null : (
        <div data-slot="preview-result" className="rounded-md border border-line p-3 text-[13px]">
          {shown.tools.length === 0 ? (
            <p className="m-0 text-body">{shown.notice ?? "This person's run of this agent would return nothing."}</p>
          ) : (
            <>
              <p className="m-0 text-body">
                {`Their run would be handed ${String(shown.tools.length)} ${shown.tools.length === 1 ? "action" : "actions"}`}
                {shown.rung === undefined ? "." : `, held at ${rungWords(shown.rung)}.`}
              </p>
              <ul className="m-0 mt-2 flex list-disc flex-col gap-0.5 pl-4">
                {shown.tools.map((one) => (
                  <li key={one.name}>{one.description ?? one.name}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </div>
  );
}
