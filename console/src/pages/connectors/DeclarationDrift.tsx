/**
 * What changed in a source's declaration since its connection was agreed, and accepting it.
 *
 * **The change is shown before the accept is offered, and it is the API's.** The "Declaration
 * changed" pill said a source had stopped being read and nothing about why. This card lists each
 * operation added, removed or changed and each field kept or no longer kept, in the declaration's
 * own words, as `GET /console/connectors/{name}/drift` computes them from the declaration agreed
 * and the one this release ships (`brain.console.declaration_drift`). Nothing here compares two
 * declarations: the browser draws the lines it was sent.
 *
 * **When what was agreed was not kept**, for a connection made before the system kept it, the card
 * says so and lists everything the source does now, so what is accepted is still read first.
 *
 * **Accepting is confirmed, and names the declaration shown.** It is the registry's deliberate
 * upgrade: the source is agreed again with the same settings and key, the ledger records the
 * digest before and after, and the accept carries the digest this card showed, so a release that
 * lands between the reading and the press is refused rather than accepted unseen. A reader who may
 * not accept sees the change and no button; the API refuses them whatever this drew.
 *
 * Task ids: M27.11.9, M33.5.1.1
 */

import { useState } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import type { components } from "../../api/schema";
import { useResource } from "../../api/useResource";
import { Advanced, Chip, ConfirmDialog, Fact, FactList, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { FailureNotice } from "../../ui/FailureNotice";
import { sourceApiPath } from "./connectorSources";

export type DeclarationDrift = components["schemas"]["DeclarationDriftView"];

export const DRIFT_HEADING = "What changed in this source's declaration";
export const ACCEPT = "Accept these changes";
export const KEEP_UNACCEPTED = "Not now";
export const NOT_ACCEPTED = "The change was not accepted";
export const NOW_DOES = "What it does under this release";
export const BEFORE = "Before";

export const KIND_WORDS: Readonly<Record<string, string>> = Object.freeze({
  added: "Added",
  removed: "Removed",
  changed: "Changed",
});

/** Where a source's drift is read, and where its accept is sent. */
export function driftApiPath(name: string): string {
  return `${sourceApiPath(name)}/drift`;
}

export function acceptApiPath(name: string): string {
  return `/connectors/${encodeURIComponent(name)}/accept`;
}

function versions(drift: DeclarationDrift): string {
  if (drift.was_version === "" || drift.was_version === drift.now_version) {
    return drift.now_version === "" ? "" : `Version ${drift.now_version}`;
  }
  return `Version ${drift.was_version} to ${drift.now_version}`;
}

export function DeclarationDriftCard({
  name,
  label,
  version,
  onDone,
}: {
  readonly name: string;
  readonly label: string;
  /** Moves when the page reads again, so the card does too. */
  readonly version: number;
  /** Told the API's sentence once the change is accepted. */
  readonly onDone: (told: string) => void;
}) {
  const answer = useResource<DeclarationDrift>(driftApiPath(name), version);
  const [pending, setPending] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const drift = answer.data;
  if (drift === null || !drift.changed) {
    return null;
  }

  function accept(shown: string): void {
    setBusy(true);
    void (async () => {
      const result = await request<{ told: string }>(acceptApiPath(name), { method: "POST", body: { digest: shown } });
      setBusy(false);
      setPending(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      onDone(result.data.told);
    })();
  }

  const lines = drift.lines.map((one, index) => (
    <li key={`${one.kind} ${String(index)}`} className="flex min-w-0 flex-col gap-1 border-b border-line py-2 last:border-b-0">
      <span className="flex min-w-0 flex-wrap items-start gap-2">
        <Chip>{KIND_WORDS[one.kind] ?? one.kind}</Chip>
        <span className="min-w-0 text-[13px] text-ink [overflow-wrap:anywhere]">{one.what}</span>
      </span>
      {one.was === "" ? null : (
        <span className="text-[12.5px] text-dim [overflow-wrap:anywhere]">
          {BEFORE}: {one.was}
        </span>
      )}
    </li>
  ));

  return (
    <SectionCard
      title={DRIFT_HEADING}
      lede={drift.told}
      action={
        drift.may_accept ? (
          <Button
            size="sm"
            className="min-h-11 sm:min-h-8"
            disabled={busy}
            onClick={() => {
              setFailure(null);
              setPending(true);
            }}
          >
            {ACCEPT}
          </Button>
        ) : undefined
      }
    >
      <div className="flex min-w-0 flex-col gap-3">
        {versions(drift) === "" ? null : <p className="m-0 text-[12.5px] text-dim">{versions(drift)}</p>}
        {failure === null ? null : <FailureNotice failure={failure} title={NOT_ACCEPTED} fields={["digest", "connector"]} />}
        {drift.known ? (
          <ul aria-label={DRIFT_HEADING} className="m-0 flex list-none flex-col p-0">
            {lines}
          </ul>
        ) : (
          <section aria-label={NOW_DOES} className="flex min-w-0 flex-col gap-1.5">
            <h3 className="m-0 text-[13px] font-semibold text-ink">{NOW_DOES}</h3>
            <ul className="m-0 flex list-none flex-col gap-1.5 p-0 text-[13px] text-ink">
              {drift.now_does.map((one) => (
                <li key={one} className="[overflow-wrap:anywhere]">
                  {one}
                </li>
              ))}
            </ul>
          </section>
        )}
        <Advanced>
          <FactList>
            <Fact label="Agreed digest">
              <Chip mono>{drift.agreed_digest}</Chip>
            </Fact>
            <Fact label="This release's digest">
              <Chip mono>{drift.current_digest}</Chip>
            </Fact>
          </FactList>
        </Advanced>
      </div>
      <ConfirmDialog
        open={pending}
        question={`Accept the new declaration for ${label}?`}
        consequence={drift.confirm}
        details={drift.known ? <ul className="m-0 flex list-none flex-col p-0">{lines}</ul> : undefined}
        confirmLabel={ACCEPT}
        cancelLabel={KEEP_UNACCEPTED}
        busy={busy}
        onConfirm={() => {
          accept(drift.current_digest);
        }}
        onCancel={() => {
          setPending(false);
        }}
      />
    </SectionCard>
  );
}
