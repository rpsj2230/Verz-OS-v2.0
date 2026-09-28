/**
 * A person's Grants: every direct grant and pack they hold that this reader may be told, each with
 * its scope, who gave it, why and when it lapses, and the acts that add and take away.
 *
 * **Additive only, and drawn that way.** There is no deny row and none is drawn: a person holds what
 * these rows say and nothing else. A list the reader may not be told is empty, and an empty list
 * says one sentence that is true for both reasons it can be empty (`governQuery.
 * AN_EMPTY_CAPABILITY_LIST_MEANS_TWO_THINGS_AND_SAYS_NEITHER`).
 *
 * **Taking one away is confirmed and is a retirement.** A direct grant is removed by
 * `/govern/grants/removal`, which retires the row; a pack is taken away whole by the access review's
 * decision, which retires the assignment. A capability that came with a pack has no removal of its
 * own: the row says which pack, and the API refuses a removal of it with a sentence naming the pack
 * (M27.15.20), because the pack's capabilities were granted together.
 *
 * **Adding is a drawer and is not confirmed**, because it ends nothing. Both routes judge the grant
 * against the grantor's own reach, so nobody grants what they do not hold.
 *
 * Task ids: M27.11.2, M27.11.3, M27.15.20, M27.16.1
 */

import { KeyRound, Package, Plus } from "lucide-react";
import { useCallback, useState } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { Chip, ConfirmDialog, EmptyState, EntityTable, FailureState, Note, SectionCard, type EntityColumn } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { scopeLines } from "../scopeText";
import { dayWords } from "../access/formParts";
import { GrantDrawer, PackDrawer } from "./GrantDrawers";
import { KindPill } from "./pills";
import { REMOVAL_API_PATH, REVIEW_DECISION_API_PATH, fromElevation, type Held, type PersonDetail } from "./peopleQuery";

export const GRANTS_HEADING = "Grants";
export const NOTHING_HELD = "Nothing to show";
export const NOTHING_HELD_DESCRIPTION =
  "A grant appears here once somebody who may grant it gives it. Grants only add: a person holds what is listed and nothing else.";
export const GRANT_LABEL = "Grant a capability";
export const PACK_LABEL = "Assign a pack";

export function removeQuestion(held: Held, person: string): string {
  return held.kind === "pack"
    ? `Take the ${held.packLabel ?? held.pack ?? "pack"} pack away from ${person}?`
    : `Remove ${held.capabilities[0] ?? "this capability"} from ${person}?`;
}

export const REMOVAL_CONSEQUENCE =
  "It is retired, so their next request is answered without it. The record is kept, and granting it again is how it is given back.";

export const PACK_REMOVAL_CONSEQUENCE =
  "Every capability the pack brought is retired together, so their next request is answered without any of them. The record is kept.";

/** Where a holding came from, in words. */
export function originWords(held: Held): string {
  if (held.kind === "pack") {
    const version = held.packVersion === undefined ? "" : `, version ${String(held.packVersion)}`;
    return `Pack: ${held.packLabel ?? held.pack ?? ""}${version}`;
  }
  return fromElevation(held) ? "Elevation" : "Granted directly";
}

/** A holding's scope, in words: the named scope's label, or the predicate spelled out. */
export function scopeWords(held: Held): string {
  if (held.scopeLabel !== undefined) {
    return held.scopeLabel;
  }
  const lines = scopeLines(held.scope);
  return lines.length === 0 ? "Everything" : lines.join("; ");
}

function RemoveControl({
  held,
  person,
  principalId,
  onWritten,
}: {
  readonly held: Held;
  readonly person: string;
  readonly principalId: string;
  readonly onWritten: () => void;
}) {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  const remove = useCallback(() => {
    setBusy(true);
    void (async () => {
      const result =
        held.kind === "pack"
          ? await request<unknown>(REVIEW_DECISION_API_PATH, {
              method: "POST",
              body: { kind: "pack", row_id: held.rowId, decision: "remove" },
            })
          : await request<unknown>(REMOVAL_API_PATH, {
              method: "POST",
              body: { principal_id: principalId, capability: held.capabilities[0] },
            });
      setBusy(false);
      setAsking(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      onWritten();
    })();
  }, [held, principalId, onWritten]);

  const label = held.kind === "pack" ? "Remove pack" : "Remove";
  return (
    <span className="flex flex-col items-end gap-1">
      <Button
        size="sm"
        variant="outline"
        aria-label={held.kind === "pack" ? `Remove the ${held.packLabel ?? held.pack ?? ""} pack` : `Remove ${held.capabilities[0] ?? ""}`}
        onClick={() => {
          setFailure(null);
          setAsking(true);
        }}
      >
        {label}
      </Button>
      {failure === null ? null : <FailureState failure={failure} />}
      <ConfirmDialog
        open={asking}
        question={removeQuestion(held, person)}
        consequence={held.kind === "pack" ? PACK_REMOVAL_CONSEQUENCE : REMOVAL_CONSEQUENCE}
        details={
          held.kind === "pack" ? (
            <p className="m-0 font-mono text-[12px] [overflow-wrap:anywhere]">{held.capabilities.join(", ")}</p>
          ) : undefined
        }
        confirmLabel={held.kind === "pack" ? "Remove the pack" : "Remove the grant"}
        cancelLabel="Keep it"
        busy={busy}
        onConfirm={remove}
        onCancel={() => {
          setAsking(false);
        }}
      />
    </span>
  );
}

export function PersonGrants({ detail, onWritten }: { readonly detail: PersonDetail; readonly onWritten: () => void }) {
  const { person, held, editable } = detail;
  const [granting, setGranting] = useState(false);
  const [packing, setPacking] = useState(false);

  const columns: readonly EntityColumn<Held>[] = [
    {
      id: "capability",
      header: "Capability",
      hideable: false,
      cell: (row) => (
        <span className="flex max-w-[22rem] flex-wrap gap-1">
          {row.capabilities.map((one) => (
            <Chip key={one} mono>
              {one}
            </Chip>
          ))}
        </span>
      ),
      text: (row) => row.capabilities.join("; "),
    },
    {
      id: "scope",
      header: "Scope",
      cell: (row) => <span className="[overflow-wrap:anywhere]">{scopeWords(row)}</span>,
      text: (row) => scopeWords(row),
    },
    {
      id: "origin",
      header: "From",
      cell: (row) => <KindPill>{originWords(row)}</KindPill>,
      text: (row) => originWords(row),
    },
    {
      id: "granted_by",
      header: "Given by",
      cell: (row) => row.grantedByName ?? null,
      text: (row) => row.grantedByName ?? "",
    },
    {
      id: "reason",
      header: "Reason",
      hidden: true,
      cell: (row) => <span className="[overflow-wrap:anywhere]">{row.reason ?? ""}</span>,
      text: (row) => row.reason ?? "",
    },
    {
      id: "granted_at",
      header: "Given",
      hidden: true,
      cell: (row) => dayWords(row.grantedAt),
      text: (row) => row.grantedAt ?? "",
    },
    {
      id: "lapses",
      header: "Lapses",
      cell: (row) => (row.notAfter === undefined ? "Does not lapse" : dayWords(row.notAfter)),
      text: (row) => row.notAfter ?? "",
    },
  ];

  const packs = held.filter((one) => one.kind === "pack");

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <SectionCard
        title={GRANTS_HEADING}
        lede="What they hold that you may be told, each with its scope and when it lapses."
        action={
          editable ? (
            <>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  setPacking(true);
                }}
              >
                <Package aria-hidden /> {PACK_LABEL}
              </Button>
              <Button
                size="sm"
                onClick={() => {
                  setGranting(true);
                }}
              >
                <Plus aria-hidden /> {GRANT_LABEL}
              </Button>
            </>
          ) : undefined
        }
        footer={
          packs.length > 0 ? (
            <Note>
              {detail.fromAPack ??
                "A capability that came with a pack is removed with the whole pack, because a pack's capabilities are granted together."}
            </Note>
          ) : undefined
        }
      >
        {held.length === 0 ? (
          <EmptyState title={NOTHING_HELD} description={NOTHING_HELD_DESCRIPTION} icon={<KeyRound aria-hidden />} />
        ) : (
          <EntityTable
            caption={`What ${person.displayName} holds`}
            columns={columns}
            rows={held}
            rowId={(row) => `${row.kind}:${row.rowId}`}
            rowLabel={(row) => row.capabilities[0] ?? row.rowId}
            exportName="grants"
            rowActions={
              editable
                ? (row) => <RemoveControl held={row} person={person.displayName} principalId={person.principalId} onWritten={onWritten} />
                : undefined
            }
          />
        )}
      </SectionCard>
      {editable ? (
        <>
          <GrantDrawer
            open={granting}
            onOpenChange={setGranting}
            principalId={person.principalId}
            personName={person.displayName}
            onWritten={onWritten}
          />
          <PackDrawer
            open={packing}
            onOpenChange={setPacking}
            principalId={person.principalId}
            personName={person.displayName}
            onWritten={onWritten}
          />
        </>
      ) : null}
    </div>
  );
}
