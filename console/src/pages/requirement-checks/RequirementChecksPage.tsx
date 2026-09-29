/**
 * Requirement checks on the shared page kit: every requirement the owner asked for, one area at a
 * time, each beside its proof leaves, what the install's acceptance checks said about them and the
 * newest check a person recorded, with the record act in a drawer.
 *
 * **What it records, and how, is unchanged**: the owner's sign-off is these rows, so the drawer sends
 * the old form's one request (`RecordDrawer.tsx`). What changed is how quickly a row can be judged.
 * The evidence the install already has is on the row, the figures say where the whole register and
 * each area stand, and an area can be narrowed to what is left to check.
 *
 * **Counts are drawn, and they hide nothing.** The register is the product's, the same on every
 * install and for every reader of this screen, which `brain.requirement_check_routes` argues; a
 * count here is not a count of rows somebody was not shown.
 *
 * **Narrowed here, over the area's whole answer.** The route answers an area whole, so the search
 * and the standing narrow what was sent and nothing else (`Narrowing.tsx`). The area is in the
 * address, so a colleague can be sent the area being worked through.
 *
 * Removed from the old screen: the register id as the first column (it is under each requirement
 * now, and the drawer's reference), the requirement picker that listed every id in an area, the
 * form drawn open under the table, the served paragraph above the form (it is in the drawer), and
 * the crumb written as text.
 *
 * Task ids: M1.8.8, M2.3.2, M5.6.5, M24.3.6, M27.16.1
 */

import { ClipboardCheck } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useResource } from "../../api/useResource";
import {
  Chip,
  EmptyState,
  EntityTable,
  FailureState,
  KpiStrip,
  LoadingState,
  PageHeader,
  RESET_LABEL,
  SectionCard,
  StatCard,
  type EntityColumn,
} from "../../components/kit";
import { NOTHING_MATCHES } from "../../components/ListControls";
import { Button } from "../../components/ui/button";
import { dayWords } from "../access/formParts";
import { PersonName, useNames } from "../access/PersonName";
import {
  AREA_PARAMETER,
  CHECKS_LABEL,
  CHECKS_PATH,
  STANDINGS,
  STANDING_WORDS,
  checksApiPath,
  evidenceOf,
  evidenceWords,
  proofOf,
  readChecks,
  recordedIn,
  rowSays,
  standingOf,
  type AreaRow,
  type ChecksBody,
  type RequirementRow,
} from "../requirementChecksQuery";
import { Narrowing } from "./Narrowing";
import { EvidencePill, StandingPill } from "./pills";
import { RecordDrawer } from "./RecordDrawer";

export const CHECKS_HEADING = CHECKS_LABEL;
export const CHECKS_LEDE =
  "Every requirement the owner asked for, in the owner's words. Check each one on this install and record what you saw.";
export const READING_CHECKS = "Reading the register and the checks.";
export const NOT_A_BODY = "The answer about requirement checks was not in a shape this screen can read.";
export const NOT_CHECKED = STANDING_WORDS.unchecked;
export const RECORD_LABEL = "Record";
export const RECORDED = "The check was recorded.";
export const REQUIREMENTS_LABEL = "Requirements in this area";
export const AREAS_HEADING = "By area";
export const AREAS_LABEL = "Areas of the register";
export const NARROW_LABEL = "Narrow the requirements";
export const EVERY_STANDING = "Every standing";
export const SEARCH_HINT = "Words, a reference or a leaf";

/** The console's own parameters beside the area. */
const SEARCH_PARAMETER = "q";
const STANDING_PARAMETER = "standing";

function areaAddress(area: string): string {
  return `${CHECKS_PATH}?${new URLSearchParams({ [AREA_PARAMETER]: area }).toString()}`;
}

function Register({ body }: { readonly body: ChecksBody }) {
  const total = body.areas.reduce((sum, one) => sum + one.requirements, 0);
  const passed = body.areas.reduce((sum, one) => sum + one.passed, 0);
  const failed = body.areas.reduce((sum, one) => sum + one.failed, 0);
  const unchecked = body.areas.reduce((sum, one) => sum + one.unchecked, 0);
  return (
    <KpiStrip label="The whole register" count={4}>
      <StatCard label="Requirements" value={String(total)} sub={`${String(body.areas.length)} areas`} />
      <StatCard label="Passed" value={String(passed)} />
      <StatCard label="Failed" value={String(failed)} />
      <StatCard label="To check" value={String(unchecked)} />
    </KpiStrip>
  );
}

function Areas({ body }: { readonly body: ChecksBody }) {
  const columns: readonly EntityColumn<AreaRow>[] = [
    {
      id: "area",
      header: "Area",
      hideable: false,
      cell: (row) =>
        row.area === body.area ? (
          <span className="font-medium text-ink">{row.area}</span>
        ) : (
          <Link to={areaAddress(row.area)} className="text-ink underline-offset-4 hover:underline">
            {row.area}
          </Link>
        ),
      text: (row) => row.area,
    },
    { id: "recorded", header: "Recorded", align: "end", cell: (row) => `${String(recordedIn(row))} of ${String(row.requirements)}`, text: (row) => String(recordedIn(row)) },
    { id: "passed", header: "Passed", align: "end", cell: (row) => String(row.passed), text: (row) => String(row.passed) },
    { id: "failed", header: "Failed", align: "end", cell: (row) => String(row.failed), text: (row) => String(row.failed) },
    { id: "unchecked", header: "To check", align: "end", cell: (row) => String(row.unchecked), text: (row) => String(row.unchecked) },
  ];
  return (
    <SectionCard title={AREAS_HEADING} lede="Where each area of the register stands on this install.">
      <EntityTable caption={AREAS_LABEL} columns={columns} rows={body.areas} rowId={(row) => row.area} rowLabel={(row) => row.area} exportName="requirement-areas" />
    </SectionCard>
  );
}

function Requirements({
  body,
  names,
  onRecord,
}: {
  readonly body: ChecksBody;
  readonly names: ReadonlyMap<string, string>;
  readonly onRecord: (row: RequirementRow) => void;
}) {
  const [search, setSearch] = useSearchParams();
  const typed = search.get(SEARCH_PARAMETER) ?? "";
  const chosen = search.get(STANDING_PARAMETER) ?? "";
  const standing = (STANDINGS as readonly string[]).includes(chosen) ? chosen : "";
  const area = body.areas.find((one) => one.area === body.area) ?? null;
  const rows = useMemo(
    () => body.requirements.filter((row) => (standing === "" || standingOf(row) === standing) && rowSays(row, typed)),
    [body.requirements, standing, typed],
  );

  const set = (name: string, value: string) => {
    const next = new URLSearchParams(search);
    if (value === "") {
      next.delete(name);
    } else {
      next.set(name, value);
    }
    setSearch(next, { replace: true });
  };
  const reset = () => {
    const next = new URLSearchParams();
    if (body.area !== null) {
      next.set(AREA_PARAMETER, body.area);
    }
    setSearch(next, { replace: true });
  };

  const columns: readonly EntityColumn<RequirementRow>[] = [
    {
      id: "requirement",
      header: "Requirement",
      hideable: false,
      cell: (row) => (
        <span className="flex min-w-0 flex-col gap-0.5">
          <span className="text-ink [overflow-wrap:anywhere]">{row.requirement}</span>
          <span className="font-mono text-[11px] text-dim">{row.id}</span>
        </span>
      ),
      text: (row) => `${row.id} ${row.requirement}`,
    },
    {
      id: "proof",
      header: "Proved by",
      cell: (row) => (
        <span className="flex flex-wrap gap-1">
          {proofOf(row).map((leaf) => (
            <Chip key={leaf} mono>
              {leaf}
            </Chip>
          ))}
        </span>
      ),
      text: (row) => proofOf(row).join(" "),
    },
    {
      id: "evidence",
      header: "Automatic checks",
      cell: (row) =>
        evidenceOf(row).length === 0 ? (
          <span className="text-dim">{evidenceWords(row)}</span>
        ) : (
          <span className="flex flex-wrap gap-1">
            {evidenceOf(row).map((one) => (
              <span key={one.name} title={one.sentence}>
                <EvidencePill outcome={one.outcome} />
              </span>
            ))}
          </span>
        ),
      text: (row) => evidenceWords(row),
    },
    {
      id: "standing",
      header: "Newest check",
      cell: (row) => {
        const latest = row.latest ?? null;
        return (
          <span className="flex min-w-0 flex-col gap-0.5">
            <StandingPill standing={standingOf(row)} />
            {latest === null ? null : (
              <span className="text-[12px] text-dim">
                <PersonName principalId={latest.checked_by} names={names} link={false} />, {dayWords(latest.checked_at)}
              </span>
            )}
          </span>
        );
      },
      text: (row) => STANDING_WORDS[standingOf(row)],
    },
  ];

  let list;
  if (body.requirements.length === 0) {
    list = <EmptyState title="Nothing to check" description={body.told} icon={<ClipboardCheck aria-hidden />} />;
  } else if (rows.length === 0) {
    list = (
      <EmptyState
        title={NOTHING_MATCHES}
        description="Change the search or choose every standing."
        action={
          <Button variant="outline" onClick={reset}>
            {RESET_LABEL}
          </Button>
        }
      />
    );
  } else {
    list = (
      <EntityTable
        caption={REQUIREMENTS_LABEL}
        columns={columns}
        rows={rows}
        rowId={(row) => row.id}
        rowLabel={(row) => row.id}
        exportName="requirement-checks"
        rowActions={(row) => (
          <Button
            size="sm"
            variant="outline"
            aria-label={`${RECORD_LABEL} a check of ${row.id}`}
            onClick={() => {
              onRecord(row);
            }}
          >
            {RECORD_LABEL}
          </Button>
        )}
      />
    );
  }

  return (
    <SectionCard
      title={body.area ?? CHECKS_LABEL}
      lede={area === null ? undefined : `${String(recordedIn(area))} of ${String(area.requirements)} recorded, ${String(area.unchecked)} to check.`}
    >
      <div className="flex min-w-0 flex-col gap-3">
        <Narrowing
          label={NARROW_LABEL}
          search={typed}
          onSearch={(value) => {
            set(SEARCH_PARAMETER, value);
          }}
          searchLabel="Search the requirements"
          searchHint={SEARCH_HINT}
          narrows={[
            {
              label: "Area",
              everything: "",
              value: body.area ?? "",
              options: body.areas.map((one) => ({ value: one.area, label: `${one.area} (${String(one.unchecked)} to check)` })),
              onChange: (value) => {
                setSearch(new URLSearchParams({ [AREA_PARAMETER]: value }), { replace: false });
              },
            },
            {
              label: "Standing",
              everything: EVERY_STANDING,
              value: standing,
              options: STANDINGS.map((one) => ({ value: one, label: STANDING_WORDS[one] })),
              onChange: (value) => {
                set(STANDING_PARAMETER, value);
              },
            },
          ]}
          onReset={reset}
        />
        {list}
      </div>
    </SectionCard>
  );
}

export function RequirementChecksPage() {
  const [search] = useSearchParams();
  const area = search.get(AREA_PARAMETER);
  const [version, setVersion] = useState(0);
  // A recorded check bumps the version, which asks again, so the row shows the newest check.
  const answer = useResource<unknown>(checksApiPath(area), version);
  const names = useNames(true);
  const [recording, setRecording] = useState<RequirementRow | null>(null);
  const [said, setSaid] = useState("");
  const recorded = useCallback(() => {
    setRecording(null);
    setSaid(RECORDED);
    setVersion((one) => one + 1);
  }, []);

  let content;
  if (answer.failure !== null) {
    content = <FailureState failure={answer.failure} />;
  } else if (answer.data === null) {
    content = <LoadingState label={READING_CHECKS} />;
  } else {
    const body = readChecks(answer.data);
    content =
      body === null ? (
        <p className="m-0 text-sm text-dim">{NOT_A_BODY}</p>
      ) : (
        <>
          <Register body={body} />
          <Requirements
            body={body}
            names={names}
            onRecord={(row) => {
              setSaid("");
              setRecording(row);
            }}
          />
          <Areas body={body} />
          {recording === null ? null : (
            <RecordDrawer
              key={recording.id}
              row={recording}
              told={body.told}
              names={names}
              onClose={() => {
                setRecording(null);
              }}
              onRecorded={recorded}
            />
          )}
        </>
      );
  }

  return (
    <div data-slot="requirement-checks-page" className="flex min-w-0 flex-col gap-4">
      <PageHeader crumbs={[{ label: "Install", to: "/install" }, { label: CHECKS_HEADING }]} title={CHECKS_HEADING} lede={CHECKS_LEDE} />
      {said === "" ? null : (
        <p role="status" className="m-0 text-[13px] text-ok">
          {said}
        </p>
      )}
      {content}
    </div>
  );
}
