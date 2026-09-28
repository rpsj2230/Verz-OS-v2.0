/**
 * A provider's About view: what it is, where it runs, and its history.
 *
 * **The history is the audit ledger's**, read from `GET /audit` narrowed to setting subjects and the
 * provider's name, and kept to its two subjects exactly: `provider.<slug>`, where its switch and,
 * since `0140`, its registry row are recorded, and `provider_check.<slug>`, its last test. So each
 * turn on or off, each terms change naming the fields that moved, a retirement and every test are
 * listed, newest first, and never a value. A reader who may not read the ledger is shown the API's
 * own refusal where the list would be.
 *
 * **Who acted is under Advanced.** The ledger names a person by principal id, and page text names
 * nobody by id.
 *
 * Task ids: M5.6.4, M27.16.1
 */

import { useMemo } from "react";
import { useResource } from "../../api/useResource";
import { Advanced, Chip, Fact, FactList, FailureState, LoadingState, Note, NotOffered, SectionCard } from "../../components/kit";
import { SWITCHED_OFF, SWITCHED_ON, type ProviderStateRow, type ProvidersBody } from "../modelsQuery";
import { NOT_OFFERED, providerHistoryApiPath } from "./modelsActions";
import { dayWords, historyWords, isAdded, readHistory, stepsOf } from "./providerWords";

export const ABOUT_HEADING = "About this provider";
export const HISTORY_HEADING = "History";
export const HISTORY_LEDE = "Turned on or off, terms changed, tested and retired, newest first.";
export const LOADING_HISTORY = "Loading the history.";
export const NO_HISTORY = "Nothing has been changed or tested yet.";
export const WHERE_IT_RUNS = "Where it runs";
export const ONLINE = "Online, outside this server";
export const THIS_SERVER = "On this server";

export function ProviderAbout({ row, body }: { readonly row: ProviderStateRow; readonly body: ProvidersBody }) {
  const history = useResource<unknown>(providerHistoryApiPath(row.provider));
  const rows = useMemo(() => readHistory(history.data, row.provider), [history.data, row.provider]);
  const steps = stepsOf(row.provider, body.rungs);
  return (
    <div data-slot="provider-about" className="flex min-w-0 flex-col gap-4">
      <SectionCard title={ABOUT_HEADING}>
        <FactList>
          <Fact label="What it is">{row.description}</Fact>
          <Fact label={WHERE_IT_RUNS}>{row.hosted ? ONLINE : THIS_SERVER}</Fact>
          <Fact label="On or off">
            {row.switched_on ? SWITCHED_ON : SWITCHED_OFF}
            {row.switched_at === null ? null : <span className="text-dim"> since {dayWords(row.switched_at)}</span>}
          </Fact>
          {row.registered?.base_url === null || row.registered?.base_url === undefined ? null : (
            <Fact label="Address">
              <span className="font-mono text-[12px]">{row.registered.base_url}</span>
            </Fact>
          )}
        </FactList>
        {isAdded(row) ? null : (
          <div className="mt-3">
            <NotOffered>{NOT_OFFERED.builtInRetire}</NotOffered>
          </div>
        )}
      </SectionCard>

      <SectionCard title={HISTORY_HEADING} lede={HISTORY_LEDE}>
        {history.failure !== null ? (
          <FailureState failure={history.failure} />
        ) : history.busy ? (
          <LoadingState label={LOADING_HISTORY} rows={2} />
        ) : rows.length === 0 ? (
          <Note>{NO_HISTORY}</Note>
        ) : (
          <ol className="m-0 flex list-none flex-col gap-2 p-0">
            {rows.map((one, index) => (
              <li key={`${one.at} ${String(index)}`} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-[13px]">
                <span className="w-28 shrink-0 font-mono text-[11.5px] text-dim">{dayWords(one.at)}</span>
                <span className="min-w-0 text-ink [overflow-wrap:anywhere]">{historyWords(one)}</span>
              </li>
            ))}
          </ol>
        )}
      </SectionCard>

      <Advanced>
        <FactList>
          <Fact label="Provider id">
            <Chip mono>{row.provider}</Chip>
          </Fact>
          {row.credential === null ? null : (
            <Fact label="Vault slot">
              <Chip mono>{row.credential.slot}</Chip>
            </Fact>
          )}
          {steps.length === 0 ? null : (
            <Fact label="Deployments">
              <span className="flex flex-wrap gap-1">
                {steps.map((one) => (
                  <Chip key={one.rung_id} mono>
                    {one.deployment_id}
                  </Chip>
                ))}
              </span>
            </Fact>
          )}
          {row.switched_by === null ? null : (
            <Fact label="Last switched by">
              <Chip mono>{row.switched_by}</Chip>
            </Fact>
          )}
          {rows.length === 0 ? null : (
            <Fact label="Who acted">
              <span className="flex flex-wrap gap-1">
                {[...new Set(rows.map((one) => one.actor).filter((one) => one !== ""))].map((one) => (
                  <Chip key={one} mono>
                    {one}
                  </Chip>
                ))}
              </span>
            </Fact>
          )}
        </FactList>
      </Advanced>
    </div>
  );
}
