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
 * Task ids: M27.7.27, M27.16.1
 */

import { useResource } from "../../api/useResource";
import { KpiStrip, Note, SectionCard, StatCard, type EntityColumn } from "../../components/kit";
import { CAPACITY_API_PATH, type Capacity as CapacityBody, type Connection } from "../installQuery";
import { OpsPage, PLATFORM, WholeList } from "./parts";

export const CAPACITY_HEADING = "Capacity";
export const CAPACITY_LEDE = "What this profile wants against what the host has, and what each database will admit.";
export const READING_CAPACITY = "Loading the capacity figures.";
export const MEMORY_LABEL = "Memory";
export const WHAT_DOES_NOT_ADD_UP = "What does not add up";
export const CONNECTIONS_HEADING = "Database connections";
export const NO_CONNECTIONS = "No databases declared";
export const NO_CONNECTIONS_MORE = "No database is declared, so there are no connections to weigh.";
/** Why the reserved figure is not recorded on this install. */
export const RESERVED_NOT_READ = "No compose file is mounted where the application runs, so what it reserves is not read here.";

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
              <StatCard label="Profile" value={page.memory.profile} />
              <StatCard label="Host memory" value={mib(page.memory.host_total_mib)} />
              <StatCard label="Declared by this profile" value={mib(page.memory.declared_mib)} />
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
          </>
        );
      }}
    </OpsPage>
  );
}
