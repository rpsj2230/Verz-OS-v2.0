/**
 * The Profile view of one source: the connection's settings without its key, the department its
 * records answer to, what it keeps and what it reads live, what it may do, and who uses it.
 *
 * **Connectors keep a minimal index and read every value live, and this view is where that is
 * visible.** "What it keeps" is each entity and its field names, read off the manifest; "What it
 * reads live" is the manifest's tools. Neither is a value from the source, and nothing on the page
 * is one. See `brain.connectors.declaration.CONNECTORS_NEVER_BULK_SYNC`.
 *
 * **No key, ever.** The key line is the API's word for whether the vault holds one and since when;
 * there is no field anywhere on this page that could show a key or where it is kept.
 *
 * **Names on the page, identifiers in Advanced.** The source's own short name is how the system
 * names it; it is in Advanced with nothing else, for quoting in a support request.
 *
 * **The agents and skills that use the source are the API's list for this reader** (M27.15.58):
 * agents whose manifest names it, among those the reader may see, and skills whose tools come from
 * it, for a reader of the skill library. An empty list says so in one sentence.
 *
 * Task ids: M27.11.9, M27.15.58, M11.2.1, M11.2.4
 */

import { Link } from "react-router-dom";
import { Advanced, Chip, Fact, FactList, Note, SectionCard } from "../../components/kit";
import { AGENT_ADDRESS_PREFIX } from "../../components/agentWorkspaceState";
import { keyWords, type Connected } from "../connectorsQuery";
import { dateWords, personWords, type SourceDetail } from "./connectorSources";

export const CONNECTION_HEADING = "Connection";
export const KEEPS_HEADING = "What it keeps";
export const KEEPS_LEDE = "A small index of each record. Every value is read live when a question needs it.";
export const READS_HEADING = "What it reads live";
export const MAY_DO_HEADING = "What it may do";
export const USED_BY_HEADING = "Used by";
export const NOT_CONNECTED_NOTE = "It is not connected, so it keeps nothing and reads nothing here.";
export const NO_AGENT = "No agent you can see names this source.";
export const NO_SKILL = "No skill you can see uses its tools.";
export const SOURCE_NAME = "Source name";

export function ConnectorProfile({
  detail,
  connected,
}: {
  readonly detail: SourceDetail;
  readonly connected: Connected | undefined;
}) {
  const { source } = detail;
  const latest = detail.history.find((one) => one.disconnectedAt === undefined);
  const trust = connected?.trust ?? null;
  return (
    <div data-slot="connector-profile" className="[display:grid] min-w-0 gap-4 xl:grid-cols-2">
      <SectionCard title={CONNECTION_HEADING}>
        {source.status === "not_connected" ? (
          <Note>{NOT_CONNECTED_NOTE}</Note>
        ) : (
          <FactList>
            {detail.settings.map((one) => (
              <Fact key={one.name} label={one.label}>
                <span className="font-mono text-[12.5px]">{one.value}</span>
              </Fact>
            ))}
            <Fact label="Department">{source.department ?? detail.departmentSays ?? ""}</Fact>
            {connected === undefined ? null : <Fact label="Key">{keyWords(connected)}</Fact>}
            {latest === undefined ? null : (
              <Fact label="Connected">
                {dateWords(latest.connectedAt)} by {personWords(detail.people, latest.connectedBy)}
              </Fact>
            )}
          </FactList>
        )}
      </SectionCard>

      {trust === null ? null : (
        <SectionCard title={MAY_DO_HEADING}>
          <FactList>
            <Fact label="Reaches">{trust.reaches}</Fact>
            <Fact label="May do">{trust.access}</Fact>
            <Fact label="Who may see a row">{trust.permission_sync}</Fact>
          </FactList>
        </SectionCard>
      )}

      {detail.keeps.length === 0 ? null : (
        <SectionCard title={KEEPS_HEADING} lede={KEEPS_LEDE}>
          <FactList>
            {detail.keeps.map((one) => (
              <Fact key={one.entity} label={one.entity}>
                <span className="flex flex-wrap gap-1">
                  {one.fields.map((field) => (
                    <Chip key={field} mono>
                      {field}
                    </Chip>
                  ))}
                </span>
              </Fact>
            ))}
          </FactList>
        </SectionCard>
      )}

      {detail.readsLive.length === 0 ? null : (
        <SectionCard title={READS_HEADING}>
          <FactList>
            {detail.readsLive.map((one) => (
              <Fact key={one.tool} label={one.entity}>
                {one.description}
              </Fact>
            ))}
          </FactList>
        </SectionCard>
      )}

      <SectionCard title={USED_BY_HEADING}>
        <FactList>
          <Fact label="Agents">
            {detail.agents.length === 0 ? (
              <span className="text-dim">{NO_AGENT}</span>
            ) : (
              <span className="flex flex-wrap gap-2">
                {detail.agents.map((one) => (
                  <Link key={one.agentId} to={`${AGENT_ADDRESS_PREFIX}${encodeURIComponent(one.agentId)}`} className="text-acc-text underline-offset-4 hover:underline">
                    {one.displayName}
                  </Link>
                ))}
              </span>
            )}
          </Fact>
          <Fact label="Skills">
            {detail.skills.length === 0 ? (
              <span className="text-dim">{NO_SKILL}</span>
            ) : (
              <span className="flex flex-wrap gap-1">
                {detail.skills.map((one) => (
                  <Chip key={one.name}>
                    {one.name} {one.version} · {one.state}
                  </Chip>
                ))}
              </span>
            )}
          </Fact>
        </FactList>
      </SectionCard>

      <div className="xl:col-span-2">
        <Advanced>
          <FactList>
            <Fact label={SOURCE_NAME}>
              <code>{source.name}</code>
            </Fact>
            {latest === undefined ? null : (
              <Fact label="Connected by">
                <code>{latest.connectedBy}</code>
              </Fact>
            )}
          </FactList>
        </Advanced>
      </div>
    </div>
  );
}
