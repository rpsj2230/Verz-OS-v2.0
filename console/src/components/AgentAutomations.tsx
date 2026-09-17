/**
 * The Automations tab's list of what this agent has been given to do: each automation, when it
 * next runs or why it does not, its last run, and the confirmed Start and Stop (M39.6.1.4,
 * M39.6.1.5).
 *
 * **The list is handed in, not fetched here**, for `AutomationGallery`'s reason: the workspace
 * rebuilds a panel on every tab change, so `pages/Agent.tsx` asks for the list once the tab has been
 * shown and again after a change, and this component draws what it is given.
 *
 * **Starting and stopping are each two presses, and the second is the confirmation.** The first
 * opens `ConfirmAction` with what will change, in the API's words and figures: who it runs as,
 * when it would next run, and for a start that it acts with nobody watching. The second sends back
 * the digest the API computed, which the route recomputes. A 409 is its own sentence: a
 * confirmation that went stale, or a change a run or another person made first.
 *
 * **A control is drawn only where the API sent its confirmation.** An automation this install
 * cannot perform says why instead of offering a Start the first run would undo, and the list
 * never says how many automations it did not show.
 *
 * **Keyboard and phone**, as the gallery: buttons in document order, the confirmation focuses the
 * choice that changes nothing, leaving it returns focus to the button that opened it, and the facts
 * are `.fields` rows.
 *
 * Task ids: M39.6.1.4, M39.6.1.5, M38.2.2.5
 */

import { useEffect, useRef, useState } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import type { Resource } from "../api/useResource";
import { FailureNotice } from "../ui/FailureNotice";
import { Notice } from "../ui/Notice";
import { ConfirmAction } from "./ConfirmAction";
import {
  automationStartApiPath,
  automationStopApiPath,
  changeBody,
  readAgentAutomations,
  readNotChanged,
  type InstalledAutomationShown,
} from "../pages/agentAutomationsQuery";

export const AUTOMATIONS_HEADING = "What this agent does on a schedule";
export const AUTOMATIONS_LABEL = "Installed automations";
export const READING_AUTOMATIONS = "Reading what this agent does on a schedule.";
export const NO_AUTOMATIONS = "Nothing is installed on this agent that you may see.";
export const START_LABEL = "Start";
export const STOP_LABEL = "Stop";
export const KEEP_LABEL = "Not now";
export const NOT_CHANGED = "Nothing was changed";
export const STARTED_TITLE = "Started";
export const STOPPED_TITLE = "Stopped";
export const SOMETHING_DID_NOT_WORK = "Something did not work";
export const THE_BRAIN_COULD_NOT_BE_REACHED = "The Brain could not be reached";

export const RUNS_AS_LABEL = "Runs as";
export const SCHEDULE_LABEL = "Cadence";
export const NEXT_RUN_LABEL = "Next run";
export const LAST_RUN_LABEL = "Last run";
export const FOUND_LABEL = "What it found";

/** What a start is told, beside the next run it would leave. */
export const A_START_ACTS_UNWATCHED =
  "Once started it runs at this cadence with nobody watching, as the person it runs as, reaching " +
  "no more than they may reach through this agent.";

/** What a stop is told. */
export const A_STOP_TAKES_EFFECT_AT_ONCE =
  "Once stopped nothing it does happens until somebody starts it again.";

export function startQuestion(name: string): string {
  return `Start "${name}"?`;
}

export function stopQuestion(name: string): string {
  return `Stop "${name}"?`;
}

export function nextRunSentence(at: string): string {
  return `It would next run at ${at}.`;
}

export function lastRunSentence(outcome: string, at: string): string {
  return `${outcome} at ${at}`;
}

interface AgentAutomationsProps {
  readonly agentId: string;
  readonly automations: Resource<unknown>;
  /** Called after a start or a stop was written, so the page asks for the list again. */
  readonly onChanged: () => void;
}

interface Confirming {
  readonly automation: InstalledAutomationShown;
  readonly starting: boolean;
}

/**
 * A failure to show, and the refusal's own sentence when the API wrote one in its document.
 *
 * The 409 that says nothing was changed is a refusal with a sentence of its own and a reference like
 * any other, so it is drawn by `ui/FailureNotice.tsx` under its own heading rather than as a notice
 * with no reference, as `AutomationGallery` draws the 409 that says an automation was not installed.
 */
interface Refused {
  readonly failure: ApiFailure;
  readonly title?: string;
  readonly sentence?: string;
}

function Facts({ one, becomes }: { readonly one: InstalledAutomationShown; readonly becomes?: string }) {
  return (
    <dl className="fields">
      <div className="fields__row">
        <dt>{RUNS_AS_LABEL}</dt>
        <dd>
          {one.runsAsName} <code>{one.runsAs}</code>
        </dd>
      </div>
      <div className="fields__row">
        <dt>{SCHEDULE_LABEL}</dt>
        <dd>{one.schedule}</dd>
      </div>
      {becomes === undefined ? null : (
        <div className="fields__row">
          <dt>{NEXT_RUN_LABEL}</dt>
          <dd>{nextRunSentence(becomes)}</dd>
        </div>
      )}
    </dl>
  );
}

export function AgentAutomations({ agentId, automations, onChanged }: AgentAutomationsProps) {
  const [confirming, setConfirming] = useState<Confirming | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Refused | null>(null);
  const [told, setTold] = useState<{ readonly title: string; readonly sentence: string } | null>(
    null,
  );
  const buttons = useRef(new Map<string, HTMLButtonElement>());
  const returnTo = useRef<string | null>(null);

  useEffect(() => {
    if (confirming === null && returnTo.current !== null) {
      buttons.current.get(returnTo.current)?.focus();
      returnTo.current = null;
    }
  }, [confirming]);

  const confirm = (shown: Confirming, digest: string) => {
    setBusy(true);
    void (async () => {
      const { automation, starting } = shown;
      const path = starting
        ? automationStartApiPath(agentId, automation.automationId)
        : automationStopApiPath(agentId, automation.automationId);
      const result = await request<unknown>(path, { method: "POST", body: changeBody(digest) });
      setBusy(false);
      returnTo.current = `${starting ? START_LABEL : STOP_LABEL}:${automation.automationId}`;
      setConfirming(null);
      if (result.ok) {
        setFailure(null);
        setTold({ title: starting ? STARTED_TITLE : STOPPED_TITLE, sentence: automation.name });
        onChanged();
        return;
      }
      const refused = result.failure.status === 409 ? readNotChanged(result.body) : null;
      setFailure(
        refused === null
          ? { failure: result.failure }
          : { failure: result.failure, title: NOT_CHANGED, sentence: refused.sentence },
      );
    })();
  };

  if (automations.failure) {
    return <FailureNotice failure={automations.failure} title={SOMETHING_DID_NOT_WORK} />;
  }
  if (automations.busy) {
    return (
      <p className="note" role="status">
        {READING_AUTOMATIONS}
      </p>
    );
  }
  const answer = readAgentAutomations(automations.data);
  if (answer === null) {
    return null;
  }

  const control = (one: InstalledAutomationShown, starting: boolean) => {
    const label = starting ? START_LABEL : STOP_LABEL;
    const key = `${label}:${one.automationId}`;
    return (
      <button
        type="button"
        className="button"
        aria-label={`${label}: ${one.name}`}
        disabled={busy || confirming !== null}
        ref={(element) => {
          if (element) {
            buttons.current.set(key, element);
          } else {
            buttons.current.delete(key);
          }
        }}
        onClick={() => {
          setFailure(null);
          setTold(null);
          setConfirming({ automation: one, starting });
        }}
      >
        {label}
      </button>
    );
  };

  const shown = confirming;
  const digest =
    shown === null
      ? undefined
      : shown.starting
        ? shown.automation.start?.confirmation
        : shown.automation.stopConfirmation;

  return (
    <section aria-label={AUTOMATIONS_LABEL}>
      <h3>{AUTOMATIONS_HEADING}</h3>
      <p className="note">{answer.resultRule}</p>

      {failure === null ? null : (
        <FailureNotice
          failure={failure.failure}
          title={failure.title ?? SOMETHING_DID_NOT_WORK}
          {...(failure.sentence === undefined ? {} : { sentence: failure.sentence })}
        />
      )}
      {told === null ? null : (
        <Notice title={told.title}>
          <p>{told.sentence}</p>
        </Notice>
      )}

      {shown === null || digest === undefined ? null : (
        <ConfirmAction
          question={
            shown.starting ? startQuestion(shown.automation.name) : stopQuestion(shown.automation.name)
          }
          consequence={shown.starting ? A_START_ACTS_UNWATCHED : A_STOP_TAKES_EFFECT_AT_ONCE}
          details={
            <Facts
              one={shown.automation}
              {...(shown.starting && shown.automation.start !== undefined
                ? { becomes: shown.automation.start.becomes }
                : {})}
            />
          }
          confirmLabel={shown.starting ? START_LABEL : STOP_LABEL}
          cancelLabel={KEEP_LABEL}
          busy={busy}
          onConfirm={() => {
            confirm(shown, digest);
          }}
          onCancel={() => {
            returnTo.current = `${shown.starting ? START_LABEL : STOP_LABEL}:${shown.automation.automationId}`;
            setConfirming(null);
          }}
        />
      )}

      {answer.items.length === 0 ? (
        <p className="note">{NO_AUTOMATIONS}</p>
      ) : (
        <ul className="agent-assembly__list">
          {answer.items.map((one) => (
            <li key={one.automationId} className="card">
              <h4>{one.name}</h4>
              <Facts one={one} />
              <p className="note">{one.nextRunAt ?? one.pausedBecause}</p>
              {one.lastRun === undefined ? null : (
                <div>
                  <p className="note">
                    {LAST_RUN_LABEL}: {lastRunSentence(one.lastRun.outcome, one.lastRun.finishedAt)}
                  </p>
                  {one.lastRun.result.length === 0 ? null : (
                    <ul className="agent-assembly__list" aria-label={FOUND_LABEL}>
                      {one.lastRun.result.map((line) => (
                        <li key={line}>{line}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
              {one.cannotStart === undefined ? null : <p className="note">{one.cannotStart}</p>}
              {one.start === undefined ? null : control(one, true)}
              {one.stopConfirmation === undefined ? null : control(one, false)}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
