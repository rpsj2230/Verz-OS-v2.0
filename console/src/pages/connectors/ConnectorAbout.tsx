/**
 * The About view of one source: how it is read, its verified rate ceiling, what this release
 * tested it against, where it is connected from, and every connection it has had.
 *
 * **Each line is the API's sentence, whole.** How it is read is written from the source's own
 * declaration, the ceiling from `brain.ops.limits` (or that nobody has verified one), and what it
 * was tested against from the release's recordings, which is never a claim that it works here.
 *
 * **The history is every connection, newest first**, with who connected and disconnected it, by
 * name, and the settings each was made with, so an edit reads as one connection ending and the next
 * beginning. No key is in any of it, because none is recorded here.
 *
 * Task ids: M27.11.9, M27.15.39
 */

import { Chip, Fact, FactList, Note, SectionCard } from "../../components/kit";
import { dateWords, personWords, type SourceDetail } from "./connectorSources";

export const HOW_HEADING = "How it is read";
export const HISTORY_HEADING = "History";
export const NO_HISTORY = "It has not been connected here.";
export const STILL_CONNECTED = "Still connected";

export function ConnectorAbout({ detail }: { readonly detail: SourceDetail }) {
  return (
    <div data-slot="connector-about" className="flex min-w-0 flex-col gap-4">
      <SectionCard title={HOW_HEADING}>
        <FactList>
          {detail.reading === undefined ? null : <Fact label="Reading">{detail.reading}</Fact>}
          {detail.ceiling === undefined ? null : <Fact label="Verified ceiling">{detail.ceiling}</Fact>}
          {detail.recorded === undefined ? null : <Fact label="Tested against">{detail.recorded}</Fact>}
          {detail.elsewhere === undefined ? null : <Fact label="Connected from">{detail.elsewhere}</Fact>}
        </FactList>
      </SectionCard>

      <SectionCard title={HISTORY_HEADING}>
        {detail.history.length === 0 ? (
          <Note>{NO_HISTORY}</Note>
        ) : (
          <ol className="m-0 flex list-none flex-col gap-3 p-0">
            {detail.history.map((one) => (
              <li key={`${one.connectedAt} ${one.connectedBy}`} className="flex flex-col gap-1 border-b border-line pb-3 text-[13px] last:border-b-0 last:pb-0">
                <span className="text-ink">
                  Connected {dateWords(one.connectedAt)} by {personWords(detail.people, one.connectedBy)}
                </span>
                <span className="text-dim">
                  {one.disconnectedAt === undefined
                    ? STILL_CONNECTED
                    : `Disconnected ${dateWords(one.disconnectedAt) ?? ""} by ${personWords(detail.people, one.disconnectedBy)}`}
                </span>
                {one.settings.length === 0 ? null : (
                  <span className="flex flex-wrap gap-1">
                    {one.settings.map((setting) => (
                      <Chip key={setting.name} mono>
                        {setting.label}: {setting.value}
                      </Chip>
                    ))}
                  </span>
                )}
              </li>
            ))}
          </ol>
        )}
      </SectionCard>

    </div>
  );
}
