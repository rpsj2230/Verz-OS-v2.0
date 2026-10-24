/**
 * Trying an approved skill from Ask (M40.7.2).
 *
 * A skill's card opens Ask at `/ask?skill=<digest>`. The digest is not a secret and the question is
 * never put in the address; this is the only part of Ask that reads the address. The page asks
 * `GET /me/skills/{digest}/try` whether the skill can be tried and what it is called, and says so in
 * words: it names the skill when it can be tried, and otherwise says one sentence and sends the
 * question as an ordinary one. The one sentence is the same for every reason it cannot be tried.
 *
 * Trying needs an agent to run through, so the page asks for one before it will send, and the body
 * carries the digest for that question alone. What the skill may reach is still the run's reach.
 *
 * Task ids: M40.7.2
 */

import { useSearchParams } from "react-router-dom";
import { useResource } from "../api/useResource";
import { msg } from "../locale";

export const TRIAL_PARAM = "skill";

interface TryBody {
  readonly available: boolean;
  readonly name: string;
  readonly told: string;
}

/** Where a skill's availability to try is read, under the API base. */
export function tryApiPath(digest: string): string {
  return `/me/skills/${encodeURIComponent(digest)}/try`;
}

export const TRIAL_NEEDS_AN_AGENT = msg("console.ask.trial_needs_an_agent", "Choose the agent that will use it, then ask.");

export interface Trial {
  /** The digest to send with the question, or empty when no skill is being tried. */
  readonly digest: string;
  readonly banner: React.JSX.Element | null;
}

/** What the address asks to try, and what to say about it. */
export function useTrial(): Trial {
  const [params] = useSearchParams();
  const wanted = params.get(TRIAL_PARAM) ?? "";
  const answer = useResource<TryBody>(wanted === "" ? null : tryApiPath(wanted));
  if (wanted === "" || answer.data === null) {
    return { digest: "", banner: null };
  }
  if (!answer.data.available) {
    return {
      digest: "",
      banner: (
        <p className="note" role="status">
          {answer.data.told}
        </p>
      ),
    };
  }
  return {
    digest: wanted,
    banner: (
      <p className="note" role="status">
        {`Trying the skill ${answer.data.name} for the questions you ask here. ${TRIAL_NEEDS_AN_AGENT}`}
      </p>
    ),
  };
}
