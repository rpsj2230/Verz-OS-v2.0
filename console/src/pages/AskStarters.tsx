/**
 * Up to three things to ask the agent just chosen (M40.7.8).
 *
 * The API's own list for this person and this agent (`GET /me/agents/{agent_id}/starters`), each
 * the example task of one of the agent's skills that a run at this person's reach could carry out.
 * Pressing one puts it in the question box and asks nothing: the person reads it, changes it and
 * sends it. **An empty list draws nothing**, not a sentence, because the same empty list is what an
 * agent with no examples, a switch that is off and a person whose reach covers none of them all
 * answer, and this page must not say which.
 *
 * Task ids: M40.7.8
 */

import { useResource } from "../api/useResource";
import { msg } from "../locale";

export const STARTERS_HEADING = msg("console.ask.starters_heading", "You could ask");

export const STARTERS_API_PATH = "/me/agents";

/** Where one agent's starters are read, under the API base. */
export function startersApiPath(agentId: string): string {
  return `${STARTERS_API_PATH}/${encodeURIComponent(agentId)}/starters`;
}

interface StartersBody {
  readonly prompts: readonly string[];
}

export function AskStarters({
  agent,
  disabled,
  onPick,
}: {
  readonly agent: string;
  readonly disabled: boolean;
  readonly onPick: (prompt: string) => void;
}): React.JSX.Element | null {
  const answer = useResource<StartersBody>(agent === "" ? null : startersApiPath(agent));
  const prompts = agent === "" ? [] : (answer.data?.prompts ?? []);
  if (prompts.length === 0) {
    return null;
  }
  return (
    <div className="ask__starters">
      <p className="note">{STARTERS_HEADING}</p>
      <ul aria-label={STARTERS_HEADING}>
        {prompts.map((one) => (
          <li key={one}>
            <button
              type="button"
              className="button"
              disabled={disabled}
              onClick={() => {
                onPick(one);
              }}
            >
              {one}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
