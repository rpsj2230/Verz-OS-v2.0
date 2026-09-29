/**
 * Features on the shared page kit: every genuinely new feature this install can switch on, what it
 * does, and its switch, confirmed with the product's own sentence for that direction.
 *
 * **Nothing here decides who may switch.** The route asks for `admin:feature` over everything and
 * refuses everybody else before it reads anything, so a reader who may not switch sees the API's
 * refusal and no list. Each feature the API sends is drawn; none is named here, so a feature added
 * on the server (the release check, since M27.15.51) appears with no console change.
 *
 * **A write is followed by a fresh read**, so the page shows what the database holds.
 *
 * **What was removed**: the functions that read each switch (module paths, now in Advanced), who
 * last switched it (a principal id, in Advanced; the page says when), and the three-card "what this
 * screen cannot switch" panel, which is one sentence under the list.
 *
 * Task ids: M27.15.51, M27.16.1
 */

import { useState } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import {
  Advanced,
  Chip,
  ConfirmDialog,
  EmptyState,
  Fact,
  FactList,
  FailureState,
  LoadingState,
  Note,
  PageHeader,
  SectionCard,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import {
  FEATURES_API_PATH,
  FEATURES_LABEL,
  FEATURES_LEDE,
  KEEP_IT,
  NEVER_CHANGED,
  NO_FEATURES,
  NO_FEATURES_TITLE,
  NOT_SWITCHED_HERE,
  OFF,
  ON,
  READING_FEATURES,
  readFeature,
  readFeatures,
  SWITCH_OFF,
  SWITCH_ON,
  switchConsequence,
  switchedSentence,
  switchPath,
  switchQuestion,
  UNREADABLE_ANSWER,
  type FeatureRow,
  type FeaturesBody,
} from "../featuresQuery";
import { when } from "../sessionsQuery";

export const NOT_SWITCHED = "The feature was not switched";

function FeatureCard({ row, onAsk, busy }: { readonly row: FeatureRow; readonly onAsk: (row: FeatureRow) => void; readonly busy: boolean }) {
  const changed = row.changed_at === null || row.changed_at === undefined ? NEVER_CHANGED : `Last switched ${row.on ? "on" : "off"} ${when(row.changed_at)}.`;
  return (
    <SectionCard
      title={row.title}
      headingLevel="h2"
      action={
        <>
          <Chip>{row.on ? ON : OFF}</Chip>
          <Button
            size="sm"
            variant={row.on ? "outline" : "default"}
            className="min-h-11 sm:min-h-8"
            disabled={busy}
            aria-label={`${row.on ? SWITCH_OFF : SWITCH_ON}: ${row.title}`}
            onClick={() => {
              onAsk(row);
            }}
          >
            {row.on ? SWITCH_OFF : SWITCH_ON}
          </Button>
        </>
      }
      footer={<p className="m-0 text-[12px] text-dim">{changed}</p>}
    >
      <p className="m-0 text-[13px] text-body">{row.what}</p>
      <p className="m-0 mt-2 text-[12.5px] text-dim">While off: {row.while_off}</p>
    </SectionCard>
  );
}

function FeatureList({ body, onSwitched }: { readonly body: FeaturesBody; readonly onSwitched: (told: string) => void }) {
  const [confirming, setConfirming] = useState<FeatureRow | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  function flip(row: FeatureRow): void {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(switchPath(row.name), { method: "POST", body: { on: !row.on } });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      setConfirming(null);
      const switched = readFeature(result.data);
      onSwitched(switched === null ? switchedSentence({ ...row, on: !row.on }) : switchedSentence(switched));
    })();
  }

  const saysBoth = body.components_are_chosen_by_the_profile !== false && body.plugins_have_no_loader !== false;
  return (
    <>
      {body.features.length === 0 ? <EmptyState title={NO_FEATURES_TITLE} description={NO_FEATURES} /> : null}
      {body.features.map((row) => (
        <FeatureCard
          key={row.name}
          row={row}
          busy={busy}
          onAsk={(chosen) => {
            setFailure(null);
            setConfirming(chosen);
          }}
        />
      ))}
      {saysBoth ? <Note>{NOT_SWITCHED_HERE}</Note> : null}
      {body.features.length === 0 ? null : (
        <Advanced>
          <FactList>
            {body.features.map((row) => (
              <Fact key={row.name} label={row.title}>
                <span className="font-mono text-[11.5px]">{row.name}</span>
                <span className="block font-mono text-[11px] text-dim">Read by {row.read_by.join(", ")}</span>
                {row.changed_by === null || row.changed_by === undefined ? null : (
                  <span className="block font-mono text-[11px] text-dim">Last switched by {row.changed_by}</span>
                )}
              </Fact>
            ))}
          </FactList>
        </Advanced>
      )}
      <ConfirmDialog
        open={confirming !== null}
        question={confirming === null ? "" : switchQuestion(confirming)}
        consequence={confirming === null ? "" : switchConsequence(confirming)}
        details={failure === null ? undefined : <FailureState failure={failure} title={NOT_SWITCHED} />}
        confirmLabel={confirming?.on === true ? SWITCH_OFF : SWITCH_ON}
        cancelLabel={KEEP_IT}
        tone={confirming?.on === true ? "danger" : "plain"}
        busy={busy}
        onConfirm={() => {
          if (confirming !== null) {
            flip(confirming);
          }
        }}
        onCancel={() => {
          setConfirming(null);
        }}
      />
    </>
  );
}

export function FeaturesPage() {
  const [version, setVersion] = useState(0);
  const [told, setTold] = useState<string | null>(null);
  const answer = useResource<unknown>(FEATURES_API_PATH, version);

  let content;
  if (answer.busy) {
    content = <LoadingState label={READING_FEATURES} />;
  } else if (answer.failure !== null) {
    content = <FailureState failure={answer.failure} />;
  } else {
    const body = readFeatures(answer.data);
    content =
      body === null ? (
        <Note>{UNREADABLE_ANSWER}</Note>
      ) : (
        <FeatureList
          body={body}
          onSwitched={(sentence) => {
            setTold(sentence);
            setVersion((count) => count + 1);
          }}
        />
      );
  }
  return (
    <div data-slot="features-page" className="flex min-w-0 flex-col gap-4">
      <PageHeader crumbs={[{ label: FEATURES_LABEL }]} title={FEATURES_LABEL} lede={FEATURES_LEDE} />
      {told === null ? null : (
        <div role="status">
          <Note kind="done">{told}</Note>
        </div>
      )}
      {content}
    </div>
  );
}
