/**
 * File and object storage, on the page kit: where the store is, and each bucket with what it holds,
 * how much it holds now and how long it keeps it.
 *
 * **How much a bucket holds is a count the API took, or "Not recorded yet".** The API counts on the
 * server and sends a sentence exactly when it did not, which is the tooltip here; a figure the count
 * stopped short of is said as "at least". Nothing here draws nought for a bucket nobody counted.
 *
 * **No object is ever named.** No field on the answer could hold one, and the page says so once.
 *
 * **What was removed.** The breadcrumb as text, the "What is not shown or changed here" card (two
 * lines under the buckets now), and the "why kept" column as a default (a column a reader turns on).
 *
 * Task ids: M27.8.15, M27.16.1
 */

import { useResource } from "../../api/useResource";
import { Fact, FactList, Note, NOT_RECORDED, SectionCard, type EntityColumn } from "../../components/kit";
import { heldNow, keptFor, readStorage, STORAGE_API_PATH, type BucketRow } from "../storageQuery";
import { Line, OpsPage, PLATFORM, WholeList } from "./parts";
import { Pill, PublicPill } from "./pills";

export const STORAGE_HEADING = "Storage";
export const STORAGE_LEDE = "The buckets this install keeps files in, how much each holds, and how long it keeps them.";
export const READING_STORAGE = "Loading how files are kept.";
export const NOT_A_READABLE_ADDRESS = "The address set for the store is not one this page can show.";
export const FROM_DEFAULT = "This is the address a new install starts with; nobody has set another.";
export const NO_BUCKETS = "No buckets declared";
export const NO_BUCKETS_MORE = "This install declares no bucket to keep files in.";
export const BUCKETS_HEADING = "Buckets";

const COLUMNS: readonly EntityColumn<BucketRow>[] = [
  { id: "bucket", header: "Bucket", hideable: false, cell: (row) => row.name, text: (row) => row.name },
  {
    id: "holds",
    header: "Holds",
    cell: (row) => (row.kinds.length === 0 ? row.holds : `${row.holds} (${row.kinds.join(", ")})`),
    text: (row) => row.holds,
  },
  {
    id: "now",
    header: "Holds now",
    cell: (row) =>
      row.usage === null || row.usage === undefined ? (
        <span className="text-dim" title={row.usage_unread ?? undefined}>
          {NOT_RECORDED}
        </span>
      ) : (
        heldNow(row)
      ),
    text: (row) => (row.usage === null || row.usage === undefined ? "" : heldNow(row)),
  },
  { id: "kept", header: "Kept for", cell: (row) => keptFor(row), text: (row) => keptFor(row) },
  { id: "why", header: "Why kept that long", hidden: true, cell: (row) => row.retention_reason, text: (row) => row.retention_reason },
  {
    id: "versioned",
    header: "Versioned",
    cell: (row) => <Pill>{row.versioned ? "Yes" : "No"}</Pill>,
    text: (row) => (row.versioned ? "Yes" : "No"),
  },
  {
    id: "public",
    header: "Readable without signing in",
    cell: (row) => <PublicPill open={row.public_read} />,
    text: (row) => (row.public_read ? "Yes" : "No"),
  },
];

export function StoragePage() {
  const answer = useResource<unknown>(STORAGE_API_PATH);
  const body = answer.data === null ? null : readStorage(answer.data);
  return (
    <OpsPage
      crumbs={[{ label: PLATFORM }, { label: STORAGE_HEADING }]}
      title={STORAGE_HEADING}
      lede={STORAGE_LEDE}
      loading={READING_STORAGE}
      busy={answer.busy}
      failure={answer.failure}
      body={body}
    >
      {(page) => (
        <>
          <SectionCard
            title="Where the store is"
            footer={
              <>
                <Line>{page.endpoint.told}</Line>
                <Line>{page.connection}</Line>
              </>
            }
          >
            <FactList>
              <Fact label="Kind of store">{page.endpoint.backend}</Fact>
              <Fact label="Address">{page.endpoint.address ?? NOT_A_READABLE_ADDRESS}</Fact>
              <Fact label="Prefix">{page.endpoint.prefix}</Fact>
            </FactList>
            {page.endpoint.from_default ? (
              <div className="mt-2">
                <Note>{FROM_DEFAULT}</Note>
              </div>
            ) : null}
          </SectionCard>
          {page.findings.length === 0 ? null : (
            <div className="flex flex-col gap-1">
              {page.findings.map((one) => (
                <Note key={one}>{one}</Note>
              ))}
            </div>
          )}
          <WholeList
            title={BUCKETS_HEADING}
            caption={BUCKETS_HEADING}
            columns={COLUMNS}
            rows={page.buckets}
            rowId={(row) => row.name}
            rowLabel={(row) => row.name}
            exportName="buckets"
            empty={NO_BUCKETS}
            emptyDescription={NO_BUCKETS_MORE}
            footer={
              <>
                <Line>{page.usage}</Line>
                <Line>{page.retention}</Line>
                <Line>{page.names}</Line>
                <Line>{page.manages}</Line>
              </>
            }
          />
        </>
      )}
    </OpsPage>
  );
}
