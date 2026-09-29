/**
 * Capacity, on the page kit: memory this profile wants against what the host has, and what each
 * database will admit against what its clients want.
 *
 * **Two memory figures, never one, and the second is "Not recorded yet" rather than filled in.**
 * `brain.console.installation.WHAT_A_PROFILE_DECLARES_AND_WHAT_THE_COMPOSE_FILES_RESERVE_ARE_TWO_FIGURES`
 * is the argument: this container mounts no compose file, so the reserved figure arrives null, and
 * drawing it as nought or as a copy of the declared figure would read as a measurement agreeing.
 *
 * **Every figure is the API's, and nothing here is a headroom indicator.** A bar or a colour would
 * be this console deciding what counts as close to a ceiling. The budget findings are the API's own
 * sentences, listed rather than counted, because the useful thing about one is which part it names.
 *
 * **The size this install was deployed at is its "install size", never its "profile".** The Settings
 * screen's model setting is also called a profile, and until 2026-09-29 the two Platform screens
 * used the one word for two things. A size that declares no memory says so rather than "0 MiB",
 * which read as a measurement of nothing.
 *
 * **Sizing is stated at the busiest minute, and the first limit at scale is named** (M22.3.1,
 * M22.3.2, M22.3.4). Each sizing's in-flight figure and slots are the API's, worked by Little's law in
 * `brain.ops.admission`, so this page draws them and computes nothing; the first limit reached at ten
 * and a hundred times today's volume is the product's documented sentence.
 *
 * Task ids: M27.7.27, M27.16.1, M22.3.1, M22.3.2, M22.3.4
 */

import { useResource } from "../../api/useResource";
import { KpiStrip, Note, SectionCard, StatCard, type EntityColumn } from "../../components/kit";
import { CAPACITY_API_PATH, type Capacity as CapacityBody, type Connection, type Sizing } from "../installQuery";
import { OpsPage, PLATFORM, WholeList } from "./parts";

export const CAPACITY_HEADING = "Capacity";
export const CAPACITY_LEDE = "What this install's size wants against what the host has, and what each database will admit.";
export const INSTALL_SIZE_LABEL = "Install size";
export const DECLARED_LABEL = "Declared by this install size";
/** Said where the install size declares no memory figure, instead of drawing nought. */
export const DECLARES_NO_FIGURE = "Declares no figure";
export const DECLARES_NO_FIGURE_MORE = "This install size sets no memory figure of its own to compare with.";
export const READING_CAPACITY = "Loading the capacity figures.";
export const MEMORY_LABEL = "Memory";
export const WHAT_DOES_NOT_ADD_UP = "What does not add up";
export const CONNECTIONS_HEADING = "Database connections";
export const NO_CONNECTIONS = "No databases declared";
export const NO_CONNECTIONS_MORE = "No database is declared, so there are no connections to weigh.";
/** Why the reserved figure is not recorded on this install. */
export const RESERVED_NOT_READ = "No compose file is mounted where the application runs, so what it reserves is not read here.";
export const SIZING_HEADING = "Sized for the busiest minute";
export const SIZING_LEDE =
  "Each sizing is the busiest minute's questions a second times how long each is in flight, which is how many are in flight at once. A day's total sizes a machine that is never busy.";
export const NO_SIZINGS = "No sizing is recorded";
export const FIRST_LIMIT_HEADING = "The first limit reached at ten and a hundred times";

function perSecond(value: number): string {
  return `${value.toLocaleString("en-GB")} a second`;
}

function seconds(value: number): string {
  return `${value.toLocaleString("en-GB")} s`;
}

const SIZING_COLUMNS: readonly EntityColumn<Sizing>[] = [
  { id: "name", header: "Sizing", hideable: false, cell: (row) => row.name, text: (row) => row.name },
  { id: "peak", header: "Busiest minute", align: "end", cell: (row) => perSecond(row.peak_per_second), text: (row) => perSecond(row.peak_per_second) },
  { id: "service", header: "Each takes", align: "end", cell: (row) => seconds(row.service_seconds), text: (row) => seconds(row.service_seconds) },
  {
    id: "in_flight",
    header: "In flight at once",
    align: "end",
    cell: (row) => row.in_flight_at_peak.toLocaleString("en-GB"),
    text: (row) => String(row.in_flight_at_peak),
  },
  { id: "slots", header: "Slots needed", align: "end", cell: (row) => row.slots_needed.toLocaleString("en-GB"), text: (row) => String(row.slots_needed) },
  { id: "reason", header: "Where the figure came from", hidden: true, cell: (row) => row.reason, text: (row) => row.reason },
];

function mib(value: number): string {
  return `${value.toLocaleString("en-GB")} MiB`;
}

const COLUMNS: readonly EntityColumn<Connection>[] = [
  { id: "database", header: "Database", hideable: false, cell: (row) => row.database, text: (row) => row.database },
  { id: "admissible", header: "Admits", align: "end", cell: (row) => row.admissible.toLocaleString("en-GB"), text: (row) => String(row.admissible) },
  { id: "demand", header: "Clients want", align: "end", cell: (row) => row.demand.toLocaleString("en-GB"), text: (row) => String(row.demand) },
  { id: "headroom", header: "Left", align: "end", cell: (row) => row.headroom.toLocaleString("en-GB"), text: (row) => String(row.headroom) },
];

export function CapacityPage() {
  const answer = useResource<CapacityBody>(CAPACITY_API_PATH);
  return (
    <OpsPage
      crumbs={[{ label: PLATFORM }, { label: CAPACITY_HEADING }]}
      title={CAPACITY_HEADING}
      lede={CAPACITY_LEDE}
      loading={READING_CAPACITY}
      busy={answer.busy}
      failure={answer.failure}
      body={answer.data}
    >
      {(page) => {
        const findings = [...page.memory.breaches, ...page.memory.unbudgeted];
        const reserved = page.memory.deployed_mib;
        return (
          <>
            <KpiStrip label={MEMORY_LABEL} count={4}>
              <StatCard label={INSTALL_SIZE_LABEL} value={page.memory.profile} />
              <StatCard label="Host memory" value={mib(page.memory.host_total_mib)} />
              {page.memory.declared_mib > 0 ? (
                <StatCard label={DECLARED_LABEL} value={mib(page.memory.declared_mib)} />
              ) : (
                <StatCard label={DECLARED_LABEL} value={DECLARES_NO_FIGURE} sub={DECLARES_NO_FIGURE_MORE} />
              )}
              <StatCard
                label="Reserved by the compose files"
                value={reserved === null || reserved === undefined ? undefined : mib(reserved)}
                unrecordedWhy={RESERVED_NOT_READ}
              />
            </KpiStrip>
            {findings.length === 0 ? null : (
              <SectionCard title={WHAT_DOES_NOT_ADD_UP}>
                <div className="flex flex-col gap-1">
                  {findings.map((one) => (
                    <Note key={one}>{one}</Note>
                  ))}
                </div>
              </SectionCard>
            )}
            <WholeList
              title={CONNECTIONS_HEADING}
              caption={CONNECTIONS_HEADING}
              columns={COLUMNS}
              rows={page.connections}
              rowId={(row) => row.database}
              rowLabel={(row) => row.database}
              empty={NO_CONNECTIONS}
              emptyDescription={NO_CONNECTIONS_MORE}
            />
            <WholeList
              title={SIZING_HEADING}
              lede={SIZING_LEDE}
              caption={SIZING_HEADING}
              columns={SIZING_COLUMNS}
              rows={page.sizings ?? []}
              rowId={(row) => row.name}
              rowLabel={(row) => row.name}
              empty={NO_SIZINGS}
            />
            {page.first_limit ? (
              <SectionCard title={FIRST_LIMIT_HEADING}>
                <Note>{page.first_limit}</Note>
              </SectionCard>
            ) : null}
          </>
        );
      }}
    </OpsPage>
  );
}
