/**
 * The Automations tab: what this agent could take on, and the one confirmed step that installs it
 * (M39.6.1.3).
 *
 * **The gallery is handed in, not fetched here, and that is `AgentWorkspace`'s own warning
 * heeded.** That component selects a tab as the arrow keys move, and says the day a tab's panel
 * issues its own request is the day holding an arrow key becomes a stream of requests. The panel
 * is rebuilt on every tab change, so a fetch in it would be one per visit. This component says
 * once that it has been shown, `pages/Agent.tsx` asks for the gallery then and keeps the answer
 * across tab changes, and this component draws what it is given. The preview and the install are requested here, because
 * each is a person pressing a button and not a person moving through tabs.
 *
 * **Installing is two presses and the second one is the confirmation.** Install asks the API what
 * installing would do and shows it in `ConfirmAction`: who it runs as, when it runs once started,
 * that it starts paused and why, what it can reach, and what breaks without it, in the API's own
 * words. Only the second press writes, and it sends back the digest the API computed over those
 * facts, which the route recomputes and compares. The browser's confirmation is therefore a
 * courtesy and the server's is the rule.
 *
 * **Loading, empty, failure and success are each a sentence.** A refusal of the gallery is the
 * API's sentence and trace id, as every page renders one, and it is the same sentence for an agent
 * that is not there and one this reader may not see. A 409 from the install is its own sentence:
 * a confirmation that went stale, or the automation this reader already has.
 *
 * **Keyboard and phone.** Every control is a button in document order. The confirmation takes
 * focus on the choice that changes nothing and Escape leaves it, which `ConfirmAction` does, and
 * leaving it puts focus back on the Install button that opened it, so a keyboard user is not
 * dropped at the top of the document. The facts are `.fields` rows, which `tests/phone-width.
 * test.tsx` already holds to a phone's width, and both lists are `.agent-assembly__list`, whose
 * items may break inside a word, from the stylesheet the workspace already loads.
 *
 * **Nothing here decides anything.** `installable` only chooses whether a button is drawn, and a
 * card without one says the reader cannot install here rather than showing a control that would
 * be refused.
 *
 * Task ids: M39.6.1.3
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import type { Resource } from "../api/useResource";
import { FailureNotice } from "../ui/FailureNotice";
import { Notice } from "../ui/Notice";
import { ConfirmAction } from "./ConfirmAction";
import {
  automationInstallApiPath,
  automationPreviewApiPath,
  installBody,
  readGallery,
  readInstalled,
  readNotInstalled,
  readPreview,
  type AutomationCard,
  type InstallPreview,
} from "../pages/automationGalleryQuery";

export const GALLERY_HEADING = "Automations this agent can take on";
export const GALLERY_LABEL = "Automation templates";
export const READING_GALLERY = "Reading the automations this agent can take on.";
export const NO_TEMPLATES = "This install offers no automation templates.";
export const READING_PREVIEW = "Reading what installing it would do.";
export const SOMETHING_DID_NOT_WORK = "Something did not work";
export const THE_BRAIN_COULD_NOT_BE_REACHED = "The Brain could not be reached";
export const NOT_INSTALLED = "Nothing was installed";
export const INSTALLED_TITLE = "Installed";

export const INSTALL_LABEL = "Install";
export const KEEP_LABEL = "Not now";
export const CANNOT_INSTALL_HERE = "You cannot install automations on this agent.";

/** The labels of the facts a person confirms. */
export const RUNS_AS_LABEL = "Runs as";
export const SCHEDULE_LABEL = "When it runs, once started";
export const START_LABEL = "How it starts";
export const REACH_LABEL = "What it can reach";
export const GUARDS_LABEL = "What breaks without it";
export const FACTS_LABEL = "What installing it would do";

/** What an empty reach says, rather than an empty list. */
export const REACHES_NOTHING =
  "Nothing. Your access and this agent's ceiling have no read in common, so it would reach nothing.";

/** A preview whose body the console cannot read, which is not the same as a refusal. */
export const PREVIEW_UNREADABLE =
  "The API's answer about this automation could not be read, so nothing can be confirmed. Nothing was installed.";

export function installQuestion(name: string): string {
  return `Install "${name}" on this agent?`;
}

export function installedSentence(name: string, automationId: string): string {
  return `"${name}" is installed as ${automationId}. It is paused until somebody starts it.`;
}

export function scheduleSentence(schedule: string): string {
  return `Once started, it runs ${schedule}.`;
}

export function installedAsSentence(automationId: string): string {
  return `You have installed this as ${automationId}.`;
}

interface AutomationGalleryProps {
  readonly agentId: string;
  /** The gallery answer, fetched by the page once per workspace answer. */
  readonly gallery: Resource<unknown>;
  /** Called when the panel is first shown, so the page asks for the gallery. */
  readonly onShown: () => void;
  /** Called after a successful install, so the page asks for the gallery again. */
  readonly onInstalled: () => void;
}

/**
 * A failure to show, and the refusal's own sentence when the API wrote one in its document.
 *
 * The 409 that says an automation was not installed is a refusal with a sentence of its own and a
 * reference like any other, so it is drawn by `ui/FailureNotice.tsx` under this panel's heading
 * rather than as a notice with no reference.
 */
interface Refused {
  readonly failure: ApiFailure;
  readonly title?: string;
  readonly sentence?: string;
}

function PreviewFacts({ shown }: { readonly shown: InstallPreview }) {
  return (
    <dl className="fields" aria-label={FACTS_LABEL}>
      <div className="fields__row">
        <dt>{RUNS_AS_LABEL}</dt>
        <dd>
          {shown.runsAsName} <code>{shown.runsAs}</code>
        </dd>
      </div>
      <div className="fields__row">
        <dt>{SCHEDULE_LABEL}</dt>
        <dd>{shown.schedule}</dd>
      </div>
      <div className="fields__row">
        <dt>{START_LABEL}</dt>
        <dd>{shown.pausedBecause}</dd>
      </div>
      <div className="fields__row">
        <dt>{REACH_LABEL}</dt>
        <dd>
          {shown.reach.length === 0 ? (
            REACHES_NOTHING
          ) : (
            <ul className="agent-assembly__list">
              {shown.reach.map((one) => (
                <li key={one}>
                  <code>{one}</code>
                </li>
              ))}
            </ul>
          )}
        </dd>
      </div>
      <div className="fields__row">
        <dt>{GUARDS_LABEL}</dt>
        <dd>{shown.guards}</dd>
      </div>
    </dl>
  );
}

export function AutomationGallery({
  agentId,
  gallery,
  onShown,
  onInstalled,
}: AutomationGalleryProps) {
  const [confirming, setConfirming] = useState<InstallPreview | null>(null);
  const [asking, setAsking] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Refused | null>(null);
  const [told, setTold] = useState<{ readonly title: string; readonly sentence: string } | null>(
    null,
  );
  // One button per card, so leaving the confirmation can put focus back where it came from
  // without asking the document which button that was.
  const buttons = useRef(new Map<string, HTMLButtonElement>());
  // Where focus goes once the confirmation has gone. Moved in an effect rather than beside the
  // state change, because every Install button is disabled while a confirmation is open and a
  // disabled button refuses focus until the render that enables it.
  const returnTo = useRef<string | null>(null);

  useEffect(() => {
    onShown();
  }, [onShown]);

  useEffect(() => {
    if (confirming === null && returnTo.current !== null) {
      buttons.current.get(returnTo.current)?.focus();
      returnTo.current = null;
    }
  }, [confirming]);

  const ask = useCallback(
    (card: AutomationCard) => {
      setAsking(card.templateId);
      setFailure(null);
      setTold(null);
      void (async () => {
        const result = await request<unknown>(automationPreviewApiPath(agentId, card.templateId));
        setAsking(null);
        if (!result.ok) {
          setFailure({ failure: result.failure });
          return;
        }
        const shown = readPreview(result.data);
        if (shown === null) {
          setTold({ title: NOT_INSTALLED, sentence: PREVIEW_UNREADABLE });
          return;
        }
        setConfirming(shown);
      })();
    },
    [agentId],
  );

  const leave = useCallback((templateId: string) => {
    returnTo.current = templateId;
    setConfirming(null);
  }, []);

  const confirm = useCallback(
    (shown: InstallPreview) => {
      setBusy(true);
      void (async () => {
        const result = await request<unknown>(automationInstallApiPath(agentId), {
          method: "POST",
          body: installBody(shown),
        });
        setBusy(false);
        setConfirming(null);
        if (result.ok) {
          const made = readInstalled(result.data);
          setFailure(null);
          setTold({
            title: INSTALLED_TITLE,
            sentence: installedSentence(made?.name ?? shown.name, made?.automationId ?? ""),
          });
          onInstalled();
          return;
        }
        const refused = result.failure.status === 409 ? readNotInstalled(result.body) : null;
        setFailure(
          refused === null
            ? { failure: result.failure }
            : { failure: result.failure, title: NOT_INSTALLED, sentence: refused.sentence },
        );
      })();
    },
    [agentId, onInstalled],
  );

  if (gallery.failure) {
    return <FailureNotice failure={gallery.failure} title={SOMETHING_DID_NOT_WORK} />;
  }
  if (gallery.busy) {
    return (
      <p className="note" role="status">
        {READING_GALLERY}
      </p>
    );
  }
  const answer = readGallery(gallery.data);
  if (answer === null) {
    return null;
  }

  return (
    <section aria-label={GALLERY_LABEL}>
      <h3>{GALLERY_HEADING}</h3>
      <p className="note">{answer.installing}</p>

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
      {asking === null ? null : (
        <p className="note" role="status">
          {READING_PREVIEW}
        </p>
      )}

      {confirming === null ? null : (
        <ConfirmAction
          question={installQuestion(confirming.name)}
          consequence={confirming.reachRule}
          details={<PreviewFacts shown={confirming} />}
          warning={confirming.installing}
          confirmLabel={INSTALL_LABEL}
          cancelLabel={KEEP_LABEL}
          busy={busy}
          onConfirm={() => {
            confirm(confirming);
          }}
          onCancel={() => {
            leave(confirming.templateId);
          }}
        />
      )}

      {answer.cards.length === 0 ? (
        <p className="note">{NO_TEMPLATES}</p>
      ) : (
        <ul className="agent-assembly__list">
          {answer.cards.map((card) => (
            <li key={card.templateId} className="card">
              <h4>{card.name}</h4>
              <p>{card.summary}</p>
              <p className="note">{scheduleSentence(card.schedule)}</p>
              {card.installedAs !== undefined ? (
                <p className="note">
                  {installedAsSentence(card.installedAs)}
                </p>
              ) : card.installable ? (
                <button
                  type="button"
                  className="button"
                  aria-label={`${INSTALL_LABEL}: ${card.name}`}
                  disabled={busy || asking !== null || confirming !== null}
                  ref={(element) => {
                    if (element) {
                      buttons.current.set(card.templateId, element);
                    } else {
                      buttons.current.delete(card.templateId);
                    }
                  }}
                  onClick={() => {
                    ask(card);
                  }}
                >
                  {INSTALL_LABEL}
                </button>
              ) : (
                <p className="note">{CANNOT_INSTALL_HERE}</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
