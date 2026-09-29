/**
 * The Models page, on the shared page kit: the AI providers this install can use as a row of
 * compact cards, then the failover matrix that decides which of them answers, then what their
 * calls cost. The owner's screenshot of 2026-09-03, restated on 2026-09-29, is the design of
 * record: providers at the top and his matrix under them.
 *
 * **A card says what an administrator acts on every day and nothing more** (2026-09-22: the screen
 * was "very complicated"): the provider by the name a person knows, its status, whether a key is
 * held and its last test, and the three acts, add a key, test it and turn it off or on. Its terms,
 * figures and history are its own page's, which the name opens. The models it is used for are the
 * matrix's to say, under the cards, rather than a second copy on each card.
 *
 * **The matrix is the same card the Routing page draws** (`FailoverMatrixCard`), read from the same
 * two answers: `GET /routing/rungs` for the whole chain and the providers' plan for each step's role
 * and marker. Here a step opens on the Routing page, where its editor and the matrix gate are.
 *
 * **Both lists are drawn whole, with no search, filter or order**: a handful of providers and a
 * dozen steps are read at a glance, and "Show more" is drawn only when the API says there is more.
 * The providers keep the product's own order, built in first.
 *
 * **Where answers are made sits above the cards, because it decides whether any of them is used.**
 * It is the install's profile, shown to every reader and changed from a confirmation by a reader the
 * API says may.
 *
 * **The prices sit at the end, because they are what a provider's calls are costed at**
 * (M27.12.5): `components/ModelPrices.tsx`, each model a step names with its price per million
 * tokens and whether its calls are costed, set from its row by a reader who may switch a provider.
 *
 * **Every act is confirmed, and drawn only for a reader the API says may use it.** A switch moves
 * every department's questions, a test spends tokens under the presser's name
 * (`modelsQuery.A_CHECK_SPENDS_TOKENS_SO_IT_IS_CONFIRMED`), and a new provider is somewhere questions
 * may be sent. `editable` decides whether a control is drawn and decides nothing else.
 *
 * **What was removed on 2026-09-29**: the providers table with its search, its two filters, its
 * order, its column chooser, its row selection and export, and the Models in use column.
 *
 * Task ids: M27.16.1, M27.8.8, M5.7.1, M5.7.2, M5.6.4, M27.12.5
 */

import { Download, Plus, Route } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useListing } from "../../components/useListing";
import { ConfirmDialog, EmptyState, FailureState, LoadingState, Note, PageHeader } from "../../components/kit";
import { SHOW_MORE } from "../../components/ListControls";
import { ModelPrices } from "../../components/ModelPrices";
import { Button } from "../../components/ui/button";
import { CHAIN_PAGE_SIZE, MATRIX_API_PATH, readMatrixPage, rungAddress, type RungRow } from "../matrixQuery";
import {
  checkConsequence,
  checkQuestion,
  chooseProfileLabel,
  keyAction,
  keyHeldWords,
  KEEP_IT_AS_IT_IS,
  DO_NOT_TEST,
  MODELS_LABEL,
  otherProfile,
  PROFILE_API_PATH,
  PROFILE_WORDS,
  profileBody,
  profileChosenSentence,
  profileConsequence,
  profileNowSentence,
  profileQuestion,
  providerCheckApiPath,
  providerName,
  providerStatus,
  providerSwitchApiPath,
  PROVIDERS_API_PATH,
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
  WHERE_ANSWERS_ARE_MADE,
  type ProviderStateRow,
  type ProvidersBody,
  type RungStateRow,
} from "../modelsQuery";
import { readRegisterDocument, REGISTER_API_PATH, REGISTER_HEADING } from "../providerRegisterQuery";
import { AddProvider } from "./AddProvider";
import { FailoverMatrixCard } from "./FailoverMatrixCard";
import { MODULE_LABEL, providerAddress, saveText, WORKS_AT } from "./modelsActions";
import { StatusPill } from "./pills";
import { lastTestWords } from "./providerWords";
import { matrixLines } from "./routingWords";

export const PROVIDERS_LEDE = "The AI providers this install can use, and which of them answers each level of question.";
export const LOADING_PROVIDERS = "Loading the providers.";
export const LOADING_MATRIX = "Loading the failover matrix.";
export const NO_PROVIDERS = "No providers to show";
export const NO_PROVIDERS_DESCRIPTION = "A provider appears here once it is built in or added by an administrator.";
export const PROVIDERS_CAPTION = "AI providers";
export const ADD_A_PROVIDER = "Add a provider";
export const ROUTING_LINK = "Routing";
export const KEY_LABEL = "Key";
export const LAST_TEST_LABEL = "Last test";

/** A write this page is about to send, held while its confirmation is open. */
type Ask =
  | { readonly kind: "switch"; readonly provider: string; readonly name: string; readonly on: boolean }
  | { readonly kind: "check"; readonly provider: string; readonly name: string }
  | { readonly kind: "profile"; readonly profile: string };

/**
 * The rows out of the list's body, its `items`: a provider only with its slug, once each, in the
 * order sent. `providers` beside them is every provider, for names; the page is `items`.
 */
export function readProviderRows(payload: unknown): readonly ProviderStateRow[] {
  const body = readProviders(payload);
  if (body === null) {
    return [];
  }
  const seen = new Set<string>();
  const items = (payload as { items?: unknown }).items;
  if (!Array.isArray(items)) {
    return [];
  }
  return (items as ProviderStateRow[]).filter((one) => {
    if (typeof one.provider !== "string" || one.provider === "" || seen.has(one.provider)) {
      return false;
    }
    seen.add(one.provider);
    return true;
  });
}

function askQuestion(ask: Ask): string {
  if (ask.kind === "switch") {
    return switchQuestion(ask.name, ask.on);
  }
  return ask.kind === "check" ? checkQuestion(ask.name) : profileQuestion(ask.profile);
}

function askConsequence(ask: Ask): string {
  if (ask.kind === "switch") {
    return switchConsequence(ask.name, ask.on);
  }
  return ask.kind === "check" ? checkConsequence(ask.name) : profileConsequence(ask.profile);
}

function askLabel(ask: Ask): string {
  if (ask.kind === "switch") {
    return ask.on ? TURN_ON : TURN_OFF;
  }
  return ask.kind === "check" ? SEND_THE_TEST : chooseProfileLabel(ask.profile);
}

/** One provider as a compact card: its name and status, its key and last test, and its acts. */
function ProviderCard({
  row,
  name,
  steps,
  profile,
  editable,
  onAsk,
}: {
  readonly row: ProviderStateRow;
  readonly name: string;
  readonly steps: readonly RungStateRow[];
  readonly profile: string | undefined;
  readonly editable: boolean;
  readonly onAsk: (ask: Ask) => void;
}) {
  const mayKey = row.credential !== null;
  return (
    <li data-slot="provider-card" className="flex min-w-0 flex-col gap-2 rounded-md border border-line bg-panel px-4 py-3">
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
        <Link
          to={providerAddress(row.provider)}
          className="min-w-0 text-[14px] font-semibold text-ink underline-offset-4 [overflow-wrap:anywhere] hover:text-acc-text hover:underline"
        >
          {name}
        </Link>
        <StatusPill status={providerStatus(row, steps, profile)} />
      </div>
      <dl className="m-0 flex flex-wrap gap-x-4 gap-y-0.5 text-[12.5px]">
        <div className="flex gap-1">
          <dt className="text-dim">{KEY_LABEL}:</dt>
          <dd className="m-0 text-body">{keyHeldWords(row.key_held)}</dd>
        </div>
        <div className="flex min-w-0 gap-1">
          <dt className="shrink-0 text-dim">{LAST_TEST_LABEL}:</dt>
          <dd className="m-0 min-w-0 text-body [overflow-wrap:anywhere]">{lastTestWords(row.last_check)}</dd>
        </div>
      </dl>
      {mayKey || editable ? (
        <div className="mt-auto flex flex-wrap gap-1.5 pt-1">
          {mayKey ? (
            <Button asChild variant="outline" size="sm" className="min-h-11 text-ink no-underline sm:min-h-7">
              <Link to={providerAddress(row.provider, "profile")}>{keyAction(row)}</Link>
            </Button>
          ) : null}
          {editable ? (
            <>
              <Button
                variant="outline"
                size="sm"
                className="min-h-11 sm:min-h-7"
                aria-label={`${TEST} ${name}`}
                onClick={() => {
                  onAsk({ kind: "check", provider: row.provider, name });
                }}
              >
                {TEST}
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="min-h-11 sm:min-h-7"
                aria-label={`${row.switched_on ? TURN_OFF : TURN_ON} ${name}`}
                onClick={() => {
                  onAsk({ kind: "switch", provider: row.provider, name, on: !row.switched_on });
                }}
              >
                {row.switched_on ? TURN_OFF : TURN_ON}
              </Button>
            </>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

/** Where answers are made, and the one control that changes it. */
function WhereAnswersAreMade({ body, onAsk }: { readonly body: ProvidersBody; readonly onAsk: (ask: Ask) => void }) {
  const target = otherProfile(body.profile);
  return (
    <section
      aria-label={WHERE_ANSWERS_ARE_MADE}
      className="flex flex-col gap-2 rounded-md border border-line bg-panel px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
    >
      <p className="m-0 text-[13px] text-body">
        <span className="font-semibold text-ink">{WHERE_ANSWERS_ARE_MADE}: </span>
        {PROFILE_WORDS[body.profile] ?? body.profile}. {profileNowSentence(body.profile)}
      </p>
      {body.profile_editable === true ? (
        <Button
          variant="outline"
          size="sm"
          className="min-h-11 shrink-0 sm:min-h-8"
          onClick={() => {
            onAsk({ kind: "profile", profile: target });
          }}
        >
          {chooseProfileLabel(target)}
        </Button>
      ) : null}
    </section>
  );
}

export function ProvidersPage() {
  const navigate = useNavigate();
  const [version, setVersion] = useState(0);
  const listing = useListing<ProviderStateRow>(PROVIDERS_API_PATH, { version });
  const chain = useListing<RungRow>(MATRIX_API_PATH, { version, pageSize: CHAIN_PAGE_SIZE });
  const rows = useMemo(() => readProviderRows(listing.body), [listing.body]);
  const body = useMemo(() => readProviders(listing.body), [listing.body]);
  const matrix = useMemo(() => readMatrixPage(chain.body), [chain.body]);
  const [asked, setAsked] = useState<Ask | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [told, setTold] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  const send = useCallback((pending: Ask) => {
    setBusy(true);
    void (async () => {
      const result =
        pending.kind === "switch"
          ? await request<unknown>(providerSwitchApiPath(pending.provider), { method: "PUT", body: switchBody(pending.on) })
          : pending.kind === "check"
            ? await request<unknown>(providerCheckApiPath(pending.provider), { method: "POST" })
            : await request<unknown>(PROFILE_API_PATH, { method: "PUT", body: profileBody(pending.profile) });
      setBusy(false);
      setAsked(null);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      if (pending.kind === "switch") {
        setTold(switchedSentence(pending.name, pending.on));
      } else if (pending.kind === "check") {
        const check = readCheck(result.data);
        setTold(check === null ? null : `${pending.name}: ${check.told}`);
      } else {
        setTold(profileChosenSentence(pending.profile));
      }
      setVersion((count) => count + 1);
    })();
  }, []);

  const downloadRegister = useCallback(() => {
    void (async () => {
      const result = await request<unknown>(REGISTER_API_PATH);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      const register = readRegisterDocument(result.data);
      if (register !== null) {
        saveText(register.filename, register.document, "text/markdown;charset=utf-8");
      }
    })();
  }, []);

  const providers = body?.providers ?? [];
  const steps = body?.rungs ?? [];
  const editable = body?.editable === true;
  const lines = useMemo(() => matrixLines(matrix.rungs, steps, providers), [matrix.rungs, steps, providers]);
  // Adding writes a key as well as a provider, so it is offered to a reader the API sent the vault's
  // column to, who may manage credentials, and who may also switch.
  const mayAdd = editable && providers.some((one) => one.credential !== null);
  const onAsk = (ask: Ask) => {
    setFailure(null);
    setTold(null);
    setAsked(ask);
  };

  let cards;
  if (listing.failure !== null) {
    cards = <FailureState failure={listing.failure} />;
  } else if (listing.busy) {
    cards = <LoadingState label={LOADING_PROVIDERS} />;
  } else if (rows.length === 0) {
    cards = <EmptyState title={NO_PROVIDERS} description={NO_PROVIDERS_DESCRIPTION} />;
  } else {
    cards = (
      <ul aria-label={PROVIDERS_CAPTION} className="m-0 [display:grid] list-none grid-cols-1 gap-3 p-0 sm:grid-cols-2 xl:grid-cols-3">
        {rows.map((row) => (
          <ProviderCard
            key={row.provider}
            row={row}
            name={providerName(row.provider, providers)}
            steps={steps}
            profile={body?.profile}
            editable={editable}
            onAsk={onAsk}
          />
        ))}
      </ul>
    );
  }

  let matrixState;
  if (chain.failure !== null) {
    matrixState = <FailureState failure={chain.failure} />;
  } else if (chain.busy) {
    matrixState = <LoadingState label={LOADING_MATRIX} />;
  }

  return (
    <div data-slot="models-page" className="flex min-w-0 flex-col gap-4">
      <PageHeader
        crumbs={[{ label: MODULE_LABEL }, { label: MODELS_LABEL }]}
        title={MODELS_LABEL}
        lede={PROVIDERS_LEDE}
        primary={
          mayAdd ? (
            <Button
              className="min-h-11 sm:min-h-8"
              aria-expanded={adding}
              onClick={() => {
                setAdding((open) => !open);
              }}
            >
              <Plus aria-hidden />
              {ADD_A_PROVIDER}
            </Button>
          ) : undefined
        }
        actions={
          <>
            <Button asChild variant="outline" size="sm" className="min-h-11 text-ink no-underline sm:min-h-8">
              <Link to={WORKS_AT.routing}>
                <Route aria-hidden /> {ROUTING_LINK}
              </Link>
            </Button>
            {body === null ? null : (
              <Button variant="outline" size="sm" className="min-h-11 sm:min-h-8" onClick={downloadRegister}>
                <Download aria-hidden /> {REGISTER_HEADING}
              </Button>
            )}
          </>
        }
      />
      {body === null ? null : <WhereAnswersAreMade body={body} onAsk={onAsk} />}
      {adding && mayAdd ? (
        <AddProvider
          onAdded={(name) => {
            setAdding(false);
            setTold(`${name} was added. Add a step for one of its models on the Routing page to use it.`);
            setVersion((count) => count + 1);
          }}
          onClose={() => {
            setAdding(false);
          }}
        />
      ) : null}
      {told === null ? null : (
        <div role="status">
          <Note kind="works">{told}</Note>
        </div>
      )}
      {failure === null ? null : <FailureState failure={failure} />}

      <section aria-label={PROVIDERS_CAPTION} className="flex min-w-0 flex-col gap-2">
        {cards}
        {listing.moreFailure === null ? null : <FailureState failure={listing.moreFailure} />}
        {listing.more ? (
          <Button
            variant="outline"
            className="min-h-11 self-start sm:min-h-9"
            disabled={listing.fetchingMore}
            onClick={() => {
              listing.showMore();
            }}
          >
            {SHOW_MORE}
          </Button>
        ) : null}
      </section>

      <FailoverMatrixCard
        lines={lines}
        state={matrixState}
        acts={
          matrix.editable
            ? {
                open: (line) => {
                  if (line.rung !== null) {
                    void navigate(rungAddress(line.rung.id));
                  }
                },
              }
            : undefined
        }
        footer={
          chain.moreFailure === null && !chain.more ? undefined : (
            <>
              {chain.moreFailure === null ? null : <FailureState failure={chain.moreFailure} />}
              {chain.more ? (
                <Button
                  variant="outline"
                  className="min-h-11 self-start sm:min-h-9"
                  disabled={chain.fetchingMore}
                  onClick={() => {
                    chain.showMore();
                  }}
                >
                  {SHOW_MORE}
                </Button>
              ) : null}
            </>
          )
        }
      />

      {body === null ? null : <ModelPrices editable={editable} />}

      <ConfirmDialog
        open={asked !== null}
        question={asked === null ? "" : askQuestion(asked)}
        consequence={asked === null ? "" : askConsequence(asked)}
        confirmLabel={asked === null ? "" : askLabel(asked)}
        cancelLabel={asked?.kind === "check" ? DO_NOT_TEST : KEEP_IT_AS_IT_IS}
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
    </div>
  );
}
