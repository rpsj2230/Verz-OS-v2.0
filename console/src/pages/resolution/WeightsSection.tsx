/**
 * How pairs are weighed, under the queue on Possible duplicates: which weights score pairs now,
 * what the weekly fit would change, and the one action that puts the fit in use.
 *
 * **It sits on this page because the people who decide pairs are the ones who approve the
 * weights.** The route asks for `admin:entity_merge`, the same capability as the queue, and the
 * owner's rule for this install is that a reviewer approves new weights rather than a fit going
 * into use on its own (`brain.resolution.calibration_store`). Rejected: a card on the Settings
 * page, which a reviewer does not open and which would show a weight change away from the pairs
 * it changes the evidence on.
 *
 * **No figures, and the version strings go to Advanced.** A fit is measured on every candidate pair
 * the install holds, including pairs whose records the reader does not see, so the API sends no
 * count and this card draws none; a weight is a number nobody can act on without a threshold
 * beside it, so the drift is said in bands. See
 * `resolutionReviewQuery.THE_WEIGHTS_ARE_SAID_IN_BANDS_AND_NEVER_IN_FIGURES`.
 *
 * **The moves that change a sentence are drawn first and apart from the rest.** A crossing changes
 * what a reviewer reads about a pair ("strong" where it said "some support"), which is the thing
 * the approval is for, so it leads under its own heading; the moves within a band follow as other
 * changes. Every line the API sends is drawn once, because a report listing only what changed
 * reads as though the rest were not measured.
 *
 * **The promote names the version it was shown, and the card is read again after it.** The route
 * puts a fit in use only if it is still the one waiting, so a newer fit or somebody else's approval
 * answers 409 with a sentence, which is shown as the API sent it, and either way the card is read
 * again so it shows what the database holds.
 *
 * Task ids: M14.4.4, M14.8.3
 */

import { useState } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { Advanced, ConfirmDialog, Fact, FactList, FailureState, LoadingState, Note, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import {
  CROSSINGS_LABEL,
  driftSentence,
  IN_FORCE_VERSION_LABEL,
  inForceSentence,
  KEEP_CURRENT_WEIGHTS,
  NEW_WEIGHTS_IN_FORCE,
  NEW_WEIGHTS_WAITING,
  NO_CROSSINGS,
  NOTHING_NEW,
  OTHER_CHANGES_LABEL,
  otherChanges,
  PROMOTE_WEIGHTS_API_PATH,
  promoteBody,
  readNotChanged,
  READING_WEIGHTS,
  readWeights,
  USE_NEW_WEIGHTS,
  USE_NEW_WEIGHTS_CONSEQUENCE,
  USE_NEW_WEIGHTS_QUESTION,
  WAITING_VERSION_LABEL,
  WEIGHTS_API_PATH,
  WEIGHTS_LEDE,
  WEIGHTS_NOT_CHANGED,
  WEIGHTS_TITLE,
  WEIGHTS_UNREADABLE,
  type WeightsBody,
} from "../resolutionReviewQuery";

/** What the card was told after a promote: done, or the API's sentence for why nothing changed. */
interface Told {
  readonly sentence: string;
  readonly done: boolean;
}

function DriftList({ lines, slot }: { readonly lines: readonly string[]; readonly slot: string }) {
  return (
    <ul data-slot={slot} className="m-0 mt-1 flex list-disc flex-col gap-0.5 pl-5 text-[13px] text-body">
      {lines.map((line) => (
        <li key={line}>{driftSentence(line)}</li>
      ))}
    </ul>
  );
}

function Waiting({ body, version, onTold }: { readonly body: WeightsBody; readonly version: string; readonly onTold: (told: Told) => void }) {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const others = otherChanges(body);

  function promote(): void {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(PROMOTE_WEIGHTS_API_PATH, { method: "POST", body: promoteBody(version) });
      setBusy(false);
      if (!result.ok) {
        const notChanged = result.failure.status === 409 ? readNotChanged(result.body) : null;
        if (notChanged === null) {
          setFailure(result.failure);
          return;
        }
        setAsking(false);
        onTold({ sentence: notChanged.sentence, done: false });
        return;
      }
      setAsking(false);
      onTold({ sentence: NEW_WEIGHTS_IN_FORCE, done: true });
    })();
  }

  return (
    <>
      <p className="m-0 mt-3 text-[13px] font-medium text-ink">{NEW_WEIGHTS_WAITING}</p>
      {body.crossings.length === 0 ? (
        <p className="m-0 mt-1 text-[13px] text-body">{NO_CROSSINGS}</p>
      ) : (
        <div data-slot="weights-crossings" className="mt-2 rounded-md border border-warn bg-warn-wash px-3 py-2">
          <h3 className="m-0 text-[12.5px] font-semibold text-ink">{CROSSINGS_LABEL}</h3>
          <DriftList lines={body.crossings} slot="weights-crossing-lines" />
        </div>
      )}
      {others.length === 0 ? null : (
        <>
          <h3 className="m-0 mt-3 text-[12.5px] font-semibold text-ink">{OTHER_CHANGES_LABEL}</h3>
          <DriftList lines={others} slot="weights-other-lines" />
        </>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          size="sm"
          className="min-h-11 sm:min-h-8"
          disabled={busy}
          onClick={() => {
            setFailure(null);
            setAsking(true);
          }}
        >
          {USE_NEW_WEIGHTS}
        </Button>
      </div>
      <ConfirmDialog
        open={asking}
        question={USE_NEW_WEIGHTS_QUESTION}
        consequence={USE_NEW_WEIGHTS_CONSEQUENCE}
        details={failure === null ? undefined : <FailureState failure={failure} title={WEIGHTS_NOT_CHANGED} />}
        confirmLabel={USE_NEW_WEIGHTS}
        cancelLabel={KEEP_CURRENT_WEIGHTS}
        danger={false}
        busy={busy}
        onConfirm={promote}
        onCancel={() => {
          setAsking(false);
        }}
      />
    </>
  );
}

function Weighed({ body, onTold }: { readonly body: WeightsBody; readonly onTold: (told: Told) => void }) {
  return (
    <>
      <p data-slot="weights-in-force" className="m-0 text-[13px] text-body">
        {inForceSentence(body)}
      </p>
      {body.candidate === null ? (
        <p data-slot="weights-nothing-new" className="m-0 mt-3 text-[13px] text-body">
          {NOTHING_NEW}
        </p>
      ) : (
        <Waiting key={body.candidate} body={body} version={body.candidate} onTold={onTold} />
      )}
      <div className="mt-3">
        <Advanced>
          <FactList>
            <Fact label={IN_FORCE_VERSION_LABEL}>
              <span className="font-mono text-[11.5px]">{body.in_force}</span>
            </Fact>
            {body.candidate === null ? null : (
              <Fact label={WAITING_VERSION_LABEL}>
                <span className="font-mono text-[11.5px]">{body.candidate}</span>
              </Fact>
            )}
          </FactList>
        </Advanced>
      </div>
    </>
  );
}

export function WeightsSection() {
  const [version, setVersion] = useState(0);
  const [told, setTold] = useState<Told | null>(null);
  const answer = useResource<unknown>(WEIGHTS_API_PATH, version);

  let content;
  if (answer.busy) {
    content = <LoadingState label={READING_WEIGHTS} />;
  } else if (answer.failure !== null) {
    content = <FailureState failure={answer.failure} />;
  } else {
    const body = readWeights(answer.data);
    content =
      body === null ? (
        <Note>{WEIGHTS_UNREADABLE}</Note>
      ) : (
        <Weighed
          body={body}
          onTold={(next) => {
            setTold(next);
            setVersion((count) => count + 1);
          }}
        />
      );
  }
  return (
    <div data-slot="weights-section">
      <SectionCard title={WEIGHTS_TITLE} headingLevel="h2" lede={WEIGHTS_LEDE}>
        {told === null ? null : (
          <div role="status" className="mb-3">
            <Note kind={told.done ? "done" : "info"}>{told.sentence}</Note>
          </div>
        )}
        {content}
      </SectionCard>
    </div>
  );
}
