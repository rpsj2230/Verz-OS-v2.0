/**
 * Backup and recovery, on the page kit: where the install stands, each coverage's newest copy
 * against the recovery point, and how a restore is rehearsed.
 *
 * `docs/needs-rupash.md` item 44: this is the screen somebody checks before deciding not to worry,
 * and `brain.console.recovery_view` is built around the state that reads best and is worst, a fresh
 * copy that nobody has ever read back. So the page adds nothing to the API's answer.
 *
 * **No tick and no colour on the verdict.** The standing is a word from a closed set, drawn in the
 * plain tone with the API's two sentences beside it; seven of its eight words mean "this cannot be
 * established", and the eighth is refused by the server under conditions this browser cannot check.
 * `tests/install-pages.test.tsx` holds that no standing can choose a colour.
 *
 * **Last verified restore is a fact and not a date.** A fact the API could not establish reads
 * "Not recorded yet" with the API's reason on hover and focus, never a dash beside a backup time.
 * A restore time nobody measured is the same.
 *
 * **Every coverage gets a row, including one nothing copies.** A coverage left out is an absence a
 * reader would have to notice by counting.
 *
 * **What was removed.** The raw `true` and `false` values beside "a rehearsal is owed" and "inside
 * the recovery point" (words now), recovery times in bare seconds (in words), and the two record
 * file suffixes (in Advanced). Starting a rehearsal has no route, so it is `kit/UnavailableAction`.
 *
 * Task ids: M27.16.1
 */

import { Play } from "lucide-react";
import { useResource } from "../../api/useResource";
import {
  Advanced,
  Fact,
  FactList,
  KpiStrip,
  Note,
  SectionCard,
  StatCard,
  UnavailableAction,
  type EntityColumn,
} from "../../components/kit";
import {
  isKnown,
  RECOVERY_API_PATH,
  readRecovery,
  wasRead,
  type Copies,
  type Recovery as RecoveryBody,
  type Rehearsal,
} from "../installQuery";
import { UNAVAILABLE } from "./operationsActions";
import { durationWords, Line, OpsPage, PLATFORM, WholeList } from "./parts";
import { Pill } from "./pills";

export const RECOVERY_HEADING = "Backup and recovery";
export const RECOVERY_LEDE = "What has been copied, when a restore was last verified, and whether a rehearsal is owed.";
export const READING_RECOVERY = "Loading what has been copied.";

/** The heading over the state where this install could not look at its own copies. */
export const NOTHING_LOOKED = "Nothing here has looked at your copies";

/** The heading over the records in the bucket that could not be read. */
export const RECORDS_THAT_COULD_NOT_BE_READ = "Records that could not be read";

export const REHEARSING_A_RESTORE = "Rehearsing a restore";
export const STANDING_LABEL = "Where this install stands";
export const LAST_VERIFIED_LABEL = "Last verified restore";
export const REHEARSAL_LABEL = "Rehearsal";
export const RESTORE_TOOK_LABEL = "Last restore took";
export const REHEARSAL_OWED = "Owed";
export const REHEARSAL_NOT_OWED = "Not owed";

export const COPIES_HEADING = "Copies";
export const COPIES_CAPTION = "Each coverage's copies against the recovery point";
/** A profile that takes no copies, said rather than left as no rows at all. */
export const NO_COPIES = "No copies are taken";
export const NO_COPIES_MORE = "This profile takes no copies, so there is nothing to recover from.";

function RehearsalCard({ rehearsal }: { readonly rehearsal: Rehearsal }) {
  return (
    <SectionCard
      title={REHEARSING_A_RESTORE}
      action={
        <UnavailableAction
          label={UNAVAILABLE.startRehearsal.label}
          text={UNAVAILABLE.startRehearsal.label}
          icon={<Play aria-hidden />}
          reason={UNAVAILABLE.startRehearsal.reason}
        />
      }
      footer={<Line>{rehearsal.no_control_here}</Line>}
    >
      <FactList>
        <Fact label="Owed every">{`${String(rehearsal.every_days)} days`}</Fact>
        <Fact label="Recovery time promised">{durationWords(rehearsal.promised_recovery_seconds)}</Fact>
        <Fact label="A copy is kept for">{`${String(rehearsal.copies_kept_days)} days`}</Fact>
      </FactList>
    </SectionCard>
  );
}

const COPY_COLUMNS: readonly EntityColumn<Copies>[] = [
  { id: "coverage", header: "Coverage", hideable: false, cell: (row) => row.coverage, text: (row) => row.coverage },
  {
    id: "facts",
    header: "Newest copy",
    cell: (row) => (
      <ul className="m-0 flex list-none flex-col gap-0.5 p-0">
        {row.facts.map((fact) => (
          <li key={fact.name} className="text-[12.5px]">
            {isKnown(fact) ? fact.value : <span className="text-dim">{fact.because}</span>}
          </li>
        ))}
      </ul>
    ),
    text: (row) => row.facts.map((fact) => (isKnown(fact) ? fact.value : fact.because)).join("; "),
  },
  {
    id: "within",
    header: "Inside the recovery point",
    cell: (row) => <Pill>{row.within_objective ? "Yes" : "No"}</Pill>,
    text: (row) => (row.within_objective ? "Yes" : "No"),
  },
  {
    id: "objective",
    header: "Recovery point promised",
    cell: (row) => durationWords(row.objective_seconds),
    text: (row) => durationWords(row.objective_seconds),
  },
];

export function RecoveryPage() {
  const answer = useResource<RecoveryBody>(RECOVERY_API_PATH);
  const body = answer.data === null ? null : { read: readRecovery(answer.data), rehearsal: answer.data.rehearsal ?? null };

  return (
    <OpsPage
      crumbs={[{ label: PLATFORM }, { label: RECOVERY_HEADING }]}
      title={RECOVERY_HEADING}
      lede={RECOVERY_LEDE}
      loading={READING_RECOVERY}
      busy={answer.busy}
      failure={answer.failure}
      body={body}
    >
      {({ read, rehearsal }) => (
        <>
          {wasRead(read) ? (
            <>
              <KpiStrip label={STANDING_LABEL} count={4}>
                <StatCard label={STANDING_LABEL} value={read.panel.assurance} />
                <StatCard
                  label={LAST_VERIFIED_LABEL}
                  value={isKnown(read.panel.last_verified) ? read.panel.last_verified.value : undefined}
                  unrecordedWhy={read.panel.last_verified.because}
                />
                <StatCard label={REHEARSAL_LABEL} value={read.panel.drill_is_due ? REHEARSAL_OWED : REHEARSAL_NOT_OWED} />
                <StatCard
                  label={RESTORE_TOOK_LABEL}
                  value={
                    read.panel.measured_rto_seconds === null || read.panel.measured_rto_seconds === undefined
                      ? undefined
                      : durationWords(read.panel.measured_rto_seconds)
                  }
                />
              </KpiStrip>
              <div className="flex flex-col gap-1">
                <p className="m-0 text-sm text-ink">{read.panel.says}</p>
                <Line>{read.panel.what_to_do}</Line>
              </div>
              {read.panel.unreadable.length === 0 ? null : (
                <SectionCard title={RECORDS_THAT_COULD_NOT_BE_READ}>
                  <ul className="m-0 flex list-none flex-col gap-1 p-0">
                    {read.panel.unreadable.map((one) => (
                      <li key={one.where} className="text-[13px]">
                        <code className="font-mono text-[12px]">{one.where}</code> {one.why}
                      </li>
                    ))}
                  </ul>
                </SectionCard>
              )}
              <WholeList
                title={COPIES_HEADING}
                caption={COPIES_CAPTION}
                columns={COPY_COLUMNS}
                rows={read.panel.copies}
                rowId={(row) => row.coverage}
                rowLabel={(row) => row.coverage}
                empty={NO_COPIES}
                emptyDescription={NO_COPIES_MORE}
              />
            </>
          ) : (
            <SectionCard title={NOTHING_LOOKED}>
              <Note>{read.unread}</Note>
            </SectionCard>
          )}
          {rehearsal === null ? null : <RehearsalCard rehearsal={rehearsal} />}
          {rehearsal === null ? null : (
            <Advanced>
              <FactList>
                <Fact label="A copy's record ends">
                  <code className="font-mono text-[12px]">{rehearsal.manifest_ends}</code>
                </Fact>
                <Fact label="A rehearsal's record ends">
                  <code className="font-mono text-[12px]">{rehearsal.record_ends}</code>
                </Fact>
              </FactList>
            </Advanced>
          )}
        </>
      )}
    </OpsPage>
  );
}
