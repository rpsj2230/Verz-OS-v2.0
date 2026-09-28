/**
 * One provider's page on the shared kit, in SCREEN 14's shape: one header with its figures, and
 * three views at their own addresses. The Dashboard is what it has done (its steps, its last test,
 * what it has been sent), the Profile is how it is set up (its key, its terms and residency, its
 * models), and About is what it is and its history.
 *
 * **One request for the provider, and each view asks only for its own.** The provider is the
 * providers list narrowed to its slug (`modelsActions.providerApiPath`), which also carries the
 * steps and the profile, so the status drawn is the plan the next call makes. The figures are
 * `GET /models/providers/{provider}/stats`, drawn by `StatsStrip`: what it answered, from the
 * metadata ledger; failures and cost are named as not recorded and read "Not recorded yet" with the
 * reason, never nought.
 *
 * **A provider that is not there and one the reader may not see are one answer.** The list route
 * refuses an unreadable reader with its own sentence, drawn as the failure; a slug that matches no
 * provider draws the same empty state whatever the reason.
 *
 * **Every act is confirmed and drawn only for a reader the API says may use it.** Test, turn on or
 * off, and retire, which is offered for a provider added here and is a sentence for a built-in one.
 *
 * **What was removed from the old screen**: the provider details table with the slug beside every
 * name (the slug is under Advanced), the vault column (the key card says it for a reader who may
 * manage keys), each step's health table (a step's marker is on its row), and the three figures
 * that were the whole install's rather than a provider's.
 *
 * Task ids: M27.16.1, M5.6.4, M5.7.1, M5.7.2, M27.8.8
 */

import { FlaskConical, IdCard, Info, LayoutDashboard, Power, Trash2 } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import {
  ConfirmDialog,
  DetailHeader,
  DetailPage,
  EmptyState,
  FailureState,
  LoadingState,
  Note,
  PageHeader,
  StatCard,
  StatsStrip,
  ViewSwitch,
  type DetailView,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import {
  checkConsequence,
  checkQuestion,
  DO_NOT_TEST,
  KEEP_IT_AS_IT_IS,
  MODELS_LABEL,
  providerCheckApiPath,
  providerName,
  providerStatus,
  providerSwitchApiPath,
  readCheck,
  readProviders,
  SEND_THE_TEST,
  switchBody,
  switchConsequence,
  switchedSentence,
  switchQuestion,
  TEST,
  TURN_OFF,
  TURN_ON,
  type CheckBody,
  type ProviderStateRow,
} from "../modelsQuery";
import {
  KEEP_PROVIDER,
  RETIRE_CONSEQUENCE,
  RETIRE_PROVIDER,
  retireProviderApiPath,
  retireQuestion,
} from "../providerRegisterQuery";
import {
  MODULE_LABEL,
  providerAddress,
  providerApiPath,
  providerStatsApiPath,
  PROVIDER_VIEW_LABELS,
  PROVIDER_VIEWS,
  WORKS_AT,
  type ProviderView,
} from "./modelsActions";
import { OnOffPill, StatusPill } from "./pills";
import { ProviderAbout } from "./ProviderAbout";
import { ProviderDashboard } from "./ProviderDashboard";
import { ProviderProfile } from "./ProviderProfile";
import { figure, isAdded, readStats, unrecordedWhy } from "./providerWords";

export const VIEWS_LABEL = "Provider views";
export const LOADING_PROVIDER = "Loading this provider.";
export const FIGURES_LABEL = "This provider at a glance";
export const NO_SUCH_PROVIDER = "No provider at this address";
export const NO_SUCH_PROVIDER_DESCRIPTION = "Open the providers list to choose one.";
export const ANSWERED_LABEL = "Answered, 30 days";
export const FAILURES_LABEL = "Failures, 30 days";
export const COST_LABEL = "Cost, 30 days";
export const ANSWERED_SUB = "requests whose model calls all went to it";

const VIEW_ICONS: Readonly<Record<ProviderView, typeof LayoutDashboard>> = {
  dashboard: LayoutDashboard,
  profile: IdCard,
  about: Info,
};

/** A write this page is about to send, held while its confirmation is open. */
type Ask =
  | { readonly kind: "switch"; readonly provider: string; readonly on: boolean }
  | { readonly kind: "check"; readonly provider: string }
  | { readonly kind: "retire"; readonly provider: string };

function ProviderAnswer({ provider, view }: { readonly provider: string; readonly view: ProviderView }) {
  const [version, setVersion] = useState(0);
  const answer = useResource<unknown>(providerApiPath(provider), version);
  const stats = useResource<unknown>(providerStatsApiPath(provider), version);
  const body = useMemo(() => readProviders(answer.data), [answer.data]);
  // The list narrowed to this provider answers it as its one item; `providers` is every provider.
  const items = (answer.data as { items?: unknown } | null)?.items;
  const row = (Array.isArray(items) ? (items as ProviderStateRow[]) : []).find((one) => one.provider === provider) ?? null;
  const navigate = useNavigate();
  const [asked, setAsked] = useState<Ask | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [told, setTold] = useState<string | null>(null);
  const [checked, setChecked] = useState<CheckBody | null>(null);
  const onChanged = useCallback(() => {
    setVersion((count) => count + 1);
  }, []);
  const name = providerName(provider, body?.providers ?? []);

  const send = useCallback(
    (pending: Ask) => {
      setBusy(true);
      void (async () => {
        const result =
          pending.kind === "switch"
            ? await request<unknown>(providerSwitchApiPath(pending.provider), { method: "PUT", body: switchBody(pending.on) })
            : pending.kind === "check"
              ? await request<unknown>(providerCheckApiPath(pending.provider), { method: "POST" })
              : await request<unknown>(retireProviderApiPath(pending.provider), { method: "POST" });
        setBusy(false);
        setAsked(null);
        if (!result.ok) {
          setFailure(result.failure);
          return;
        }
        setFailure(null);
        if (pending.kind === "retire") {
          navigate(WORKS_AT.providers);
          return;
        }
        if (pending.kind === "check") {
          setChecked(readCheck(result.data));
          setTold(null);
        } else {
          setTold(switchedSentence(name, pending.on));
        }
        setVersion((count) => count + 1);
      })();
    },
    [name, navigate],
  );

  if (answer.failure !== null) {
    return <FailureState failure={answer.failure} />;
  }
  if (answer.busy && body === null) {
    return <LoadingState label={LOADING_PROVIDER} />;
  }
  if (body === null || row === null) {
    return (
      <div className="flex min-w-0 flex-col gap-4">
        <PageHeader crumbs={[{ label: MODULE_LABEL }, { label: MODELS_LABEL, to: WORKS_AT.providers }, { label: NO_SUCH_PROVIDER }]} title={MODELS_LABEL} />
        <EmptyState
          title={NO_SUCH_PROVIDER}
          description={NO_SUCH_PROVIDER_DESCRIPTION}
          action={
            <Button asChild variant="outline" className="text-ink no-underline">
              <Link to={WORKS_AT.providers}>{MODELS_LABEL}</Link>
            </Button>
          }
        />
      </div>
    );
  }

  const figures = readStats(stats.data);
  const editable = body.editable;
  const views: DetailView[] = PROVIDER_VIEWS.map((one) => {
    const Icon = VIEW_ICONS[one];
    return { key: one, label: PROVIDER_VIEW_LABELS[one], to: providerAddress(provider, one), icon: <Icon aria-hidden /> };
  });
  const confirm = (ask: Ask) => {
    setFailure(null);
    setTold(null);
    setAsked(ask);
  };

  const header = (
    <DetailHeader
      name={name}
      headingId={`provider-${provider}`}
      pills={
        <>
          <OnOffPill on={row.switched_on} />
          <StatusPill status={providerStatus(row, body.rungs, body.profile)} />
        </>
      }
      subline={row.description}
      actions={
        editable ? (
          <>
            <Button
              variant="outline"
              size="sm"
              className="min-h-11 sm:min-h-8"
              onClick={() => {
                confirm({ kind: "check", provider });
              }}
            >
              <FlaskConical aria-hidden /> {TEST}
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="min-h-11 sm:min-h-8"
              onClick={() => {
                confirm({ kind: "switch", provider, on: !row.switched_on });
              }}
            >
              <Power aria-hidden /> {row.switched_on ? TURN_OFF : TURN_ON}
            </Button>
            {isAdded(row) ? (
              <Button
                variant="outline"
                size="sm"
                className="min-h-11 sm:min-h-8"
                onClick={() => {
                  confirm({ kind: "retire", provider });
                }}
              >
                <Trash2 aria-hidden /> {RETIRE_PROVIDER}
              </Button>
            ) : null}
          </>
        ) : undefined
      }
      figures={
        <StatsStrip label={FIGURES_LABEL} busy={stats.busy} failure={stats.failure} count={3}>
          <StatCard
            label={ANSWERED_LABEL}
            value={figure(figures?.answered)}
            sub={figure(figures?.answered) === undefined ? undefined : ANSWERED_SUB}
            unrecordedWhy={unrecordedWhy(figures, "answered")}
          />
          <StatCard
            label={FAILURES_LABEL}
            value={figure(figures?.failures)}
            unrecordedWhy={unrecordedWhy(figures, "failures")}
          />
          <StatCard
            label={COST_LABEL}
            value={figures?.cost_minor === null || figures?.cost_minor === undefined ? undefined : figure(figures.cost_minor)}
            unrecordedWhy={unrecordedWhy(figures, "model_cost")}
            link={
              <Link to={WORKS_AT.spend} className="text-[12px] font-normal text-acc-text underline-offset-4 hover:underline">
                Spend
              </Link>
            }
          />
        </StatsStrip>
      }
      footnote={
        told === null && failure === null ? undefined : (
          <div className="flex flex-col gap-2">
            {told === null ? null : (
              <div role="status">
                <Note kind="works">{told}</Note>
              </div>
            )}
            {failure === null ? null : <FailureState failure={failure} />}
          </div>
        )
      }
    />
  );

  return (
    <>
      <DetailPage
        crumbs={[{ label: MODULE_LABEL }, { label: MODELS_LABEL, to: WORKS_AT.providers }, { label: name }]}
        header={header}
        switcher={<ViewSwitch label={VIEWS_LABEL} views={views} current={view} />}
      >
        {view === "dashboard" ? <ProviderDashboard row={row} body={body} checked={checked} /> : null}
        {view === "profile" ? <ProviderProfile row={row} body={body} name={name} onChanged={onChanged} /> : null}
        {view === "about" ? <ProviderAbout row={row} body={body} /> : null}
      </DetailPage>
      <ConfirmDialog
        open={asked !== null}
        question={
          asked === null
            ? ""
            : asked.kind === "switch"
              ? switchQuestion(name, asked.on)
              : asked.kind === "check"
                ? checkQuestion(name)
                : retireQuestion(name)
        }
        consequence={
          asked === null
            ? ""
            : asked.kind === "switch"
              ? switchConsequence(name, asked.on)
              : asked.kind === "check"
                ? checkConsequence(name)
                : RETIRE_CONSEQUENCE
        }
        confirmLabel={
          asked === null ? "" : asked.kind === "switch" ? (asked.on ? TURN_ON : TURN_OFF) : asked.kind === "check" ? SEND_THE_TEST : RETIRE_PROVIDER
        }
        cancelLabel={asked?.kind === "check" ? DO_NOT_TEST : asked?.kind === "retire" ? KEEP_PROVIDER : KEEP_IT_AS_IT_IS}
        busy={busy}
        onConfirm={() => {
          if (asked !== null) {
            send(asked);
          }
        }}
        onCancel={() => {
          setAsked(null);
        }}
      />
    </>
  );
}

export function ProviderDetailPage({ provider, view }: { readonly provider: string; readonly view: string | undefined }) {
  const chosen: ProviderView = view === "profile" || view === "about" ? view : "dashboard";
  return (
    <div data-slot="provider-page" className="min-w-0">
      <ProviderAnswer key={provider} provider={provider} view={chosen} />
    </div>
  );
}
