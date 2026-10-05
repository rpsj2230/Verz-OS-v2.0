/**
 * One source's page on the shared kit, in SCREEN 14's shape: one header shared by three views,
 * Dashboard, Profile and About, each at its own address.
 *
 * **The addresses.** `/connectors/{name}` is the Dashboard; `/connectors/{name}/profile` and
 * `/connectors/{name}/about` are the other two. An address naming anything else opens the
 * Dashboard, so an address typed to probe for a view learns nothing.
 *
 * **Two requests for the page, and the Dashboard's figures on their own.** The source itself is
 * `GET /api/v1/console/connectors/{name}`; the connection as the Connectors screen describes it
 * (its key, what it may read, how reading went, the forms and the confirmations) is
 * `GET /api/v1/connectors`, the same read the old screen made, so the two pages cannot disagree
 * about a connection. The Dashboard asks the shared stats route for its figures.
 *
 * **Nothing here decides what a person may see.** A source this reader may not be told is connected
 * is answered by the API exactly as one nobody connected, and is drawn the same. A 404 is not
 * explained: a name nothing ships and a name the reader may not open are one answer.
 *
 * **A changed declaration is shown before it is accepted.** When the pill says the declaration
 * changed, every view opens on what changed, read from the API, with "Accept these changes" for a
 * reader who may make it (`DeclarationDrift.tsx`).
 *
 * **Every act works.** Connect, Connect Lark, edit settings, replace the key, export the record and
 * disconnect, each confirmed in the API's words where it changes something (`SourceActs.tsx`), and
 * test connection (`TestConnection.tsx`), which the worker makes and the header reports: waiting,
 * then what it found. A reader who may not manage the source sees the newest test and no button.
 *
 * **A write the source can be allowed to make is its own item, apart from the read key.** Each grant
 * the form declares (Cloudflare's "Allow approved DNS changes") is an item under a separator in the
 * Manage menu, labelled in the API's words, and opens the key drawer for that grant alone.
 *
 * Task ids: M27.11.9, M27.15.39, M27.15.58, M11.7.7, M27.16.1, M27.10.2, M27.15.8, M11.7.3
 */

import { ChevronDown, IdCard, Info, LayoutDashboard, Plus, Settings } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { useResource } from "../../api/useResource";
import type { ApiFailure } from "../../api/errors";
import {
  DetailHeader,
  DetailPage,
  FailureState,
  KpiStrip,
  LoadingState,
  Note,
  StatCard,
  ViewSwitch,
  type DetailView,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../../components/ui/dropdown-menu";
import { FailureNotice } from "../../ui/FailureNotice";
import {
  CONNECTORS_API_PATH,
  when,
  type Connectable,
  type Connected,
  type Connectors as ConnectorsBody,
} from "../connectorsQuery";
import { LARK_API_PATH, type LarkGuide } from "../larkConnectQuery";
import { ACT_LABELS } from "./connectorActions";
import { worthShowing } from "./connectorProbe";
import { ConnectorAbout } from "./ConnectorAbout";
import { ConnectorDashboard } from "./ConnectorDashboard";
import { ConnectorProfile } from "./ConnectorProfile";
import { DeclarationDriftCard } from "./DeclarationDrift";
import {
  CONNECTORS_ADDRESS,
  CONNECT_FROM_WORDS,
  connectorAddress,
  dateWords,
  personWords,
  readSourceDetail,
  sourceApiPath,
  type SourceDetail,
} from "./connectorSources";
import { CONNECTORS_HEADING } from "./ConnectorsPage";
import { DriftPill, HealthPill, StatusPill } from "./pills";
import {
  DisconnectDialog,
  EditDrawer,
  KeyDrawer,
  LarkDialog,
  NOT_EXPORTED,
  exportRecord,
  type OpenAct,
} from "./SourceActs";
import { SourceFlow } from "./SourceFlow";
import { ConnectionTestNote, NOT_TESTED, TestConnectionButton, useConnectionTest } from "./TestConnection";

/** The three views, in the owner's order. The first is where the bare address lands. */
export const VIEWS = ["dashboard", "profile", "about"] as const;
export type SourceView = (typeof VIEWS)[number];

export const VIEW_LABELS: Readonly<Record<SourceView, string>> = Object.freeze({
  dashboard: "Dashboard",
  profile: "Profile",
  about: "About",
});

export const VIEWS_LABEL = "Source views";
export const MANAGE_LABEL = "Manage this source";
export const LOADING_SOURCE = "Loading this source.";
export const FIGURES_LABEL = "This source at a glance";
export const LAST_READ_LABEL = "Last read";
export const KEY_LABEL = "Key";
export const DEPARTMENT_LABEL = "Department";
export const NEVER_READ = "Never read yet";
export const NO_DEPARTMENT_WORDS = "None";

const VIEW_ICONS: Readonly<Record<SourceView, typeof LayoutDashboard>> = {
  dashboard: LayoutDashboard,
  profile: IdCard,
  about: Info,
};

/** Where a view of a source is. The Dashboard is the bare address. */
export function viewAddress(name: string, view: SourceView): string {
  return view === VIEWS[0] ? connectorAddress(name) : `${connectorAddress(name)}/${view}`;
}

/** Which view an address opens. Anything unknown opens the Dashboard, silently. */
export function viewFor(tab: string | undefined): SourceView {
  return tab === "profile" || tab === "about" ? tab : "dashboard";
}

function ManageMenu({
  detail,
  connected,
  form,
  onAct,
  onExport,
}: {
  readonly detail: SourceDetail;
  readonly connected: Connected | undefined;
  readonly form: Connectable | undefined;
  readonly onAct: (act: OpenAct) => void;
  readonly onExport: () => void;
}) {
  const { source } = detail;
  const manages = source.mayManage && source.connectFrom === "console" && connected !== undefined;
  const grants = manages ? (form?.writes ?? []) : [];
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="min-h-11 sm:min-h-8" aria-label={MANAGE_LABEL}>
          <Settings aria-hidden />
          <span className="hidden sm:inline">Manage</span>
          <ChevronDown aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72">
        {manages ? (
          <>
            <DropdownMenuItem
              onSelect={() => {
                onAct({ act: "edit", source: source.name });
              }}
            >
              {ACT_LABELS.edit}
            </DropdownMenuItem>
            <DropdownMenuItem
              onSelect={() => {
                onAct({ act: "key", source: source.name });
              }}
            >
              {ACT_LABELS.key}
            </DropdownMenuItem>
          </>
        ) : null}
        {grants.length === 0 ? null : (
          <>
            <DropdownMenuSeparator />
            {grants.map((grant) => (
              <DropdownMenuItem
                key={grant.name}
                onSelect={() => {
                  onAct({ act: "grant", source: source.name, grant: grant.name });
                }}
              >
                {grant.label}
              </DropdownMenuItem>
            ))}
          </>
        )}
        <DropdownMenuItem onSelect={onExport}>{ACT_LABELS.export}</DropdownMenuItem>
        {manages && connected?.may_disconnect === true ? (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              className="text-crit"
              onSelect={() => {
                onAct({ act: "disconnect", source: source.name, label: source.label });
              }}
            >
              {ACT_LABELS.disconnect}
            </DropdownMenuItem>
          </>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function SourceAnswer({ name, tab }: { readonly name: string; readonly tab: string | undefined }) {
  const [version, setVersion] = useState(0);
  const [open, setOpen] = useState<OpenAct | null>(null);
  const [told, setTold] = useState<string | null>(null);
  const [exportFailure, setExportFailure] = useState<ApiFailure | null>(null);
  const [testFailure, setTestFailure] = useState<ApiFailure | null>(null);
  const answer = useResource<unknown>(sourceApiPath(name), version);
  const context = useResource<ConnectorsBody>(CONNECTORS_API_PATH, version);
  const detail = useMemo(() => readSourceDetail(answer.data), [answer.data]);
  // Asked only on a source Connect Lark connects, to offer Manage Lark once anything is on.
  const lark = useResource<LarkGuide>(detail?.source.connectFrom === "lark" ? LARK_API_PATH : null, version).data;
  const page = context.data;
  const connected = page?.connectors?.find((one) => one.name === name);
  const form = page?.connectable.find((one) => one.name === name);
  const tested = useCallback(() => {
    setVersion((count) => count + 1);
  }, []);
  const test = useConnectionTest(name, connected !== undefined, tested);

  const done = useCallback((sentence: string) => {
    setOpen(null);
    setTold(sentence);
    setVersion((count) => count + 1);
  }, []);
  const close = useCallback(() => {
    setOpen(null);
  }, []);
  const closeLark = useCallback(() => {
    setOpen(null);
    setVersion((count) => count + 1);
  }, []);
  const act = useCallback((next: OpenAct) => {
    setTold(null);
    setExportFailure(null);
    setTestFailure(null);
    setOpen(next);
  }, []);
  const saveExport = useCallback(() => {
    setTold(null);
    void (async () => {
      setExportFailure(await exportRecord(name));
    })();
  }, [name]);

  if (answer.failure !== null) {
    return <FailureState failure={answer.failure} />;
  }
  if (answer.busy || detail === null) {
    return answer.busy ? <LoadingState label={LOADING_SOURCE} /> : null;
  }
  const { source } = detail;
  const view = viewFor(tab);
  const headingId = `connector-${source.name}`;
  const views: DetailView[] = VIEWS.map((one) => {
    const Icon = VIEW_ICONS[one];
    return { key: one, label: VIEW_LABELS[one], to: viewAddress(name, one), icon: <Icon aria-hidden /> };
  });
  const latest = detail.history.find((one) => one.disconnectedAt === undefined);
  const subline = [
    CONNECT_FROM_WORDS[source.connectFrom] ?? source.connectFrom,
    source.connectedAt === undefined
      ? null
      : `since ${dateWords(source.connectedAt) ?? ""}${latest === undefined ? "" : ` by ${personWords(detail.people, latest.connectedBy)}`}`,
  ]
    .filter((one): one is string => one !== null && one !== "")
    .join(" · ");
  const mayConnect = source.status === "not_connected" && source.connectFrom === "console" && source.mayManage && form !== undefined;
  const showsTest = connected !== undefined && worthShowing(test.probe);

  const header = (
    <DetailHeader
      name={source.label}
      headingId={headingId}
      pills={
        <>
          <StatusPill status={source.status} />
          {source.health === undefined ? null : <HealthPill health={source.health} />}
          {source.declarationChanged ? <DriftPill /> : null}
        </>
      }
      subline={subline}
      actions={
        <>
          {mayConnect ? (
            <Button
              size="sm"
              className="min-h-11 sm:min-h-8"
              onClick={() => {
                act({ act: "connect", source: source.name });
              }}
            >
              <Plus aria-hidden />
              {ACT_LABELS.connect}
            </Button>
          ) : null}
          {source.connectFrom === "server" ? (
            <Button
              size="sm"
              variant="outline"
              className="min-h-11 sm:min-h-8"
              onClick={() => {
                act({ act: "connect", source: source.name });
              }}
            >
              {ACT_LABELS.howToConnect}
            </Button>
          ) : null}
          {source.connectFrom === "lark" ? (
            <Button
              size="sm"
              variant="outline"
              className="min-h-11 sm:min-h-8"
              onClick={() => {
                act({ act: "lark", start: { at: "choose" } });
              }}
            >
              {lark?.connected === true ? ACT_LABELS.manageLark : ACT_LABELS.connectLark}
            </Button>
          ) : null}
          {connected === undefined || !source.mayManage ? null : (
            <TestConnectionButton
              name={source.name}
              label={source.label}
              probe={test.probe}
              onAsked={(fresh) => {
                setTold(null);
                test.took(fresh);
              }}
              onFailed={setTestFailure}
            />
          )}
          <ManageMenu detail={detail} connected={connected} form={form} onAct={act} onExport={saveExport} />
        </>
      }
      figures={
        connected === undefined ? undefined : (
          <KpiStrip label={FIGURES_LABEL} count={3}>
            <StatCard
              label={LAST_READ_LABEL}
              value={source.lastReadAt === undefined ? NEVER_READ : dateWords(source.lastReadAt)}
            />
            <StatCard
              label={KEY_LABEL}
              value={connected.key_held === null ? "Not known" : connected.key_held ? "Held" : "Not held"}
              sub={connected.key_written_at === null ? undefined : `written ${when(connected.key_written_at)}`}
            />
            <StatCard label={DEPARTMENT_LABEL} value={source.department ?? NO_DEPARTMENT_WORDS} />
          </KpiStrip>
        )
      }
      footnote={
        told === null && exportFailure === null && testFailure === null && !showsTest ? undefined : (
          <div role="status" className="flex flex-col gap-2">
            {told === null || told === "" ? null : <Note kind="done">{told}</Note>}
            {showsTest ? <ConnectionTestNote probe={test.probe} onCheckAgain={test.checkAgain} /> : null}
            {exportFailure === null ? null : <FailureNotice failure={exportFailure} title={NOT_EXPORTED} />}
            {testFailure === null ? null : <FailureNotice failure={testFailure} title={NOT_TESTED} />}
          </div>
        )
      }
    />
  );

  return (
    <>
      <DetailPage
        crumbs={[{ label: CONNECTORS_HEADING, to: CONNECTORS_ADDRESS }, { label: source.label }]}
        header={header}
        switcher={<ViewSwitch label={VIEWS_LABEL} views={views} current={view} />}
      >
        {source.declarationChanged ? (
          <DeclarationDriftCard name={source.name} label={source.label} version={version} onDone={done} />
        ) : null}
        {view === "dashboard" ? (
          <ConnectorDashboard
            detail={detail}
            connected={connected}
            onEdit={form === undefined || !source.mayManage ? undefined : () => {
              act({ act: "edit", source: source.name });
            }}
            onConnectSource={mayConnect ? () => {
              act({ act: "connect", source: source.name });
            } : undefined}
          />
        ) : null}
        {view === "profile" ? <ConnectorProfile detail={detail} connected={connected} /> : null}
        {view === "about" ? <ConnectorAbout detail={detail} /> : null}
      </DetailPage>
      {open?.act === "connect" && page !== null ? (
        <SourceFlow page={page} source={open.source} onClose={close} onDone={done} />
      ) : null}
      {open?.act === "lark" ? <LarkDialog start={open.start} onClose={closeLark} onDone={done} /> : null}
      {open?.act === "edit" && form !== undefined ? (
        <EditDrawer
          name={source.name}
          form={form}
          current={detail.settings}
          confirmation={detail.confirmEdit}
          onClose={close}
          onDone={done}
        />
      ) : null}
      {open?.act === "key" && form !== undefined && page !== null ? (
        <KeyDrawer
          name={source.name}
          form={form}
          keyBlank={page.key_blank}
          confirmation={detail.confirmKey}
          keyHeld={connected?.key_held === true}
          onClose={close}
          onDone={done}
        />
      ) : null}
      {open?.act === "grant" && form !== undefined && page !== null
        ? (() => {
            const grant = form.writes.find((one) => one.name === open.grant);
            return grant === undefined ? null : (
              <KeyDrawer
                name={source.name}
                form={form}
                grant={grant}
                keyBlank={page.key_blank}
                confirmation={grant.confirmation}
                keyHeld={(connected?.writes_allowed ?? []).includes(grant.name)}
                onClose={close}
                onDone={done}
              />
            );
          })()
        : null}
      {open?.act === "disconnect" && page !== null ? (
        <DisconnectDialog
          name={source.name}
          label={source.label}
          consequence={page.confirm_disconnect}
          onClose={close}
          onDone={done}
        />
      ) : null}
    </>
  );
}

export function ConnectorDetailPage({ name, tab }: { readonly name: string; readonly tab: string | undefined }) {
  return (
    <div data-slot="connector-page" className="min-w-0">
      <SourceAnswer key={name} name={name} tab={tab} />
    </div>
  );
}
