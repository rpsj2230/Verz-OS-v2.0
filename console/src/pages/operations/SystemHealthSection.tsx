/**
 * System health, beneath the incidents it sits with: what each part this install depends on is
 * doing, and which of its guarantees are held.
 *
 * **Shown only to a reader the API answers.** The route is the whole installation's, so it refuses a
 * department's reader as it refuses a person with no screen, and this section then draws nothing
 * rather than an error under a page that is otherwise fine.
 *
 * **A guarantee is held or not held, and never "probably".** A control nothing runs, nothing records,
 * that has never run or that is behind, leaves the protection it keeps not held, and the section
 * says which, in words.
 *
 * Task ids: M27.13.2, M27.15.54
 */

import { useResource } from "../../api/useResource";
import { Note, type EntityColumn } from "../../components/kit";
import {
  becauseWords,
  isHeld,
  readSystemHealth,
  standingWords,
  SYSTEM_HEALTH_API_PATH,
  type GuaranteeRow,
  type PartRow,
} from "../systemHealthQuery";
import { at, jobName, Line, WholeList } from "./parts";
import { Pill } from "./pills";

export const SYSTEM_HEALTH_HEADING = "System health";
export const PARTS_HEADING = "What this install depends on";
export const GUARANTEES_HEADING = "Guarantees";
export const NO_PARTS = "No part was named";
export const NO_GUARANTEES = "No guarantee was listed";
export const HELD = "Held";
export const NOT_HELD = "Not held";

const PART_COLUMNS: readonly EntityColumn<PartRow>[] = [
  {
    id: "part",
    header: "Part",
    hideable: false,
    cell: (row) => jobName(row.name),
    text: (row) => jobName(row.name),
  },
  {
    id: "standing",
    header: "Standing",
    cell: (row) => <Pill>{standingWords(row.state)}</Pill>,
    text: (row) => standingWords(row.state),
  },
  {
    id: "said",
    header: "What was measured",
    cell: (row) => row.said ?? "",
    text: (row) => row.said ?? "",
  },
];

const GUARANTEE_COLUMNS: readonly EntityColumn<GuaranteeRow>[] = [
  {
    id: "guarantee",
    header: "Kept by",
    hideable: false,
    cell: (row) => jobName(row.control),
    text: (row) => jobName(row.control),
  },
  {
    id: "state",
    header: "State",
    cell: (row) => <Pill>{isHeld(row) ? HELD : NOT_HELD}</Pill>,
    text: (row) => (isHeld(row) ? HELD : NOT_HELD),
  },
  {
    id: "because",
    header: "Why not",
    cell: (row) => becauseWords(row),
    text: (row) => becauseWords(row),
  },
  {
    id: "guards",
    header: "What it protects",
    cell: (row) => row.guards,
    text: (row) => row.guards,
  },
];

export function SystemHealthSection() {
  const answer = useResource<unknown>(SYSTEM_HEALTH_API_PATH);
  const page = answer.data === null ? null : readSystemHealth(answer.data);
  if (answer.busy || answer.failure !== null || page === null) {
    return null;
  }
  const parts: readonly PartRow[] = [
    ...page.parts,
    page.vault,
    page.object_store,
  ];
  return (
    <section
      aria-label={SYSTEM_HEALTH_HEADING}
      className="flex min-w-0 flex-col gap-4"
    >
      <WholeList
        title={PARTS_HEADING}
        caption={PARTS_HEADING}
        columns={PART_COLUMNS}
        rows={parts}
        rowId={(row) => row.name}
        rowLabel={(row) => jobName(row.name)}
        exportName="system-health-parts"
        empty={NO_PARTS}
        footer={
          <Line>
            {page.worker.last_seen
              ? `The worker was last seen ${at(page.worker.last_seen)}. ${page.worker.said}`
              : page.worker.said}
          </Line>
        }
      />
      {page.breakers_said !== undefined && page.breakers_said !== "" ? (
        <Note>{page.breakers_said}</Note>
      ) : null}
      {(page.guarantees_said ?? "") !== "" ? (
        <Note>{page.guarantees_said}</Note>
      ) : null}
      <WholeList
        title={GUARANTEES_HEADING}
        caption={GUARANTEES_HEADING}
        columns={GUARANTEE_COLUMNS}
        rows={page.guarantees}
        rowId={(row) => row.control}
        rowLabel={(row) => jobName(row.control)}
        exportName="system-health-guarantees"
        empty={NO_GUARANTEES}
      />
    </section>
  );
}
