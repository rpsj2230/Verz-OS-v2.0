/**
 * The small parts the Credentials pages share: a slot's state as a pill, the environment variable
 * that outranks it, and the vault's state above the list and on every slot's page.
 *
 * **The vault card says four things and no more.** Whether the vault is sealed, which policies the
 * application's token carries, whether the server holds the install's template signing key, in the
 * API's sentence and never the key (needs-rupash 82), and, only when it is true, that answers are
 * waiting for the owner to load the vault's policies again before they can read a connected source
 * live (needs-rupash 99).
 * The run-token leases and the shipping of the vault's own log are on the Vault activity tab, so
 * they are not drawn twice.
 *
 * A word this console has not heard of is drawn as itself in the plain tone, `agents/pills.tsx`'
 * rule: inventing a meaning for an unknown state is the guess that fails in the wrong direction.
 *
 * Task ids: M27.11.10, M27.15.50, M13.8.10
 */

import { Link } from "react-router-dom";
import { Fact, FactList, Note, SectionCard } from "../../components/kit";
import { cn } from "../../lib/utils";
import { WORKS_AT } from "./credentialActions";
import { sealWords, stateWords, type VaultOverview } from "./credentialRows";

const STATE_TONE: Readonly<Record<string, string>> = {
  held: "bg-ok-wash text-ok",
  defined: "bg-sunk text-dim",
  empty: "bg-sunk text-dim",
  unknown: "bg-sunk text-dim",
};

const SEAL_TONE: Readonly<Record<string, string>> = {
  open: "bg-ok-wash text-ok",
  sealed: "bg-warn-wash text-warn",
};

const PILL = "inline-block rounded-[2px] px-1.5 py-0.5 font-mono text-[10.5px] font-medium tracking-[0.03em]";

export function StatePill({ state }: { readonly state: string }) {
  return (
    <span data-slot="credential-state" className={cn(PILL, STATE_TONE[state] ?? "bg-sunk text-ink")}>
      {stateWords(state)}
    </span>
  );
}

/** The variable that wins over the slot on every start. Named, because removing it is the fix. */
export function OutrankedPill({ variable }: { readonly variable: string }) {
  return (
    <span data-slot="outranked" className={cn(PILL, "bg-warn-wash text-warn")}>
      Outranked by {variable}
    </span>
  );
}

export const VAULT_HEADING = "The vault";
export const VAULT_CARD_LABEL = "The vault's state";
export const POLICIES_LABEL = "Policies loaded";
export const STATE_LABEL = "State";
export const NO_POLICIES_SAID = "Not known";
export const TEMPLATE_KEY_LABEL = "Template signing key";

const TEMPLATE_KEY_TONE: Readonly<Record<string, string>> = {
  held: "text-ok",
  waiting: "text-warn",
  unusable: "text-warn",
};
export const VAULT_ACTIVITY_LINK = "Vault activity";

/** The vault's seal, its token's policies, and the live-read sentence when there is one. */
export function VaultCard({ vault }: { readonly vault: VaultOverview }) {
  return (
    <div aria-label={VAULT_CARD_LABEL} role="group">
      <SectionCard
        title={VAULT_HEADING}
        lede={vault.told}
        action={
          <Link to={WORKS_AT.vault} className="text-[12.5px] text-acc-text underline-offset-4 hover:underline">
            {VAULT_ACTIVITY_LINK}
          </Link>
        }
        footer={
          vault.liveReads === "waiting" || vault.slotsUnread !== "" ? (
            <>
              {vault.slotsUnread === "" ? null : <Note kind="not-yet">{vault.slotsUnread}</Note>}
              {vault.liveReads === "waiting" ? <Note kind="not-yet">{vault.liveReadsTold}</Note> : null}
            </>
          ) : undefined
        }
      >
        <FactList>
          <Fact label={STATE_LABEL}>
            <span className={cn(PILL, SEAL_TONE[vault.seal] ?? "bg-sunk text-ink")}>{sealWords(vault.seal)}</span>
          </Fact>
          <Fact label={POLICIES_LABEL}>
            {vault.tokenPolicies.length > 0 ? vault.tokenPolicies.join(", ") : NO_POLICIES_SAID}
            {vault.tokenPolicy === "other" && vault.tokenTold !== "" ? (
              <span className="mt-1 block text-[12px] text-warn">{vault.tokenTold}</span>
            ) : null}
          </Fact>
          {vault.templateKeyTold === "" ? null : (
            <Fact label={TEMPLATE_KEY_LABEL}>
              <span data-slot="template-key" className={cn("block text-[12.5px]", TEMPLATE_KEY_TONE[vault.templateKey] ?? "text-dim")}>
                {vault.templateKeyTold}
              </span>
            </Fact>
          )}
        </FactList>
      </SectionCard>
    </div>
  );
}
