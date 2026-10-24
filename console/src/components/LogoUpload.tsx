/**
 * The company screen's logo upload: choose an image, and it is kept for the appointment to point at.
 *
 * Drawn under the company questions by `pages/FirstRun.tsx`, beside the optional web address of a
 * logo, because a company with somewhere to host one has a faster way and a company without has
 * this. **It is not an answer to the wizard.** The file is sent the moment it is chosen, behind the
 * setup code, and nothing about it is in the review or in the appointment's body: the appointment
 * finds the file the server kept and points the logo setting at it, unless an address was typed,
 * which wins. See `brain.branding` for where the file lives and why an SVG is not offered.
 *
 * **A refusal is the server's sentence.** A 422 carries `problem`, which is drawn as it came, and a
 * 404 is the wizard's one constant refusal for `setup/wizard.ts`'s `A_SETUP_REFUSAL_NAMES_NO_REASON`.
 *
 * Task ids: M42.5.5
 */

import { useState } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { LOGO_ACCEPT, LOGO_UPLOAD_PATH, MAX_LOGO_BYTES, TOO_LARGE, logoBody, type LogoKept } from "../setup/logo";
import { SETUP_REFUSED_MESSAGE } from "../setup/wizard";
import { FailureNotice } from "../ui/FailureNotice";
import { Notice } from "../ui/Notice";

export const LOGO_TITLE = "Upload your logo";
export const LOGO_LEDE =
  "Optional. A PNG, JPEG, GIF or WebP file of up to 256 KiB. If you also give a web address above, the address is used.";
export const LOGO_LABEL = "Your logo, as an image file";
export const LOGO_KEPT = "Your logo is kept. It is used when setup finishes.";
export const LOGO_NOT_KEPT_TITLE = "That logo could not be used";

type Shown =
  | { readonly kind: "kept"; readonly media: string }
  | { readonly kind: "sentence"; readonly sentence: string }
  | { readonly kind: "refused"; readonly failure: ApiFailure; readonly sentence?: string }
  | null;

interface Props {
  readonly setupCode: string;
}

export function LogoUpload({ setupCode }: Props) {
  const [busy, setBusy] = useState(false);
  const [shown, setShown] = useState<Shown>(null);

  async function chosen(file: File | null): Promise<void> {
    if (file === null) {
      return;
    }
    if (file.size > MAX_LOGO_BYTES) {
      setShown({ kind: "sentence", sentence: TOO_LARGE });
      return;
    }
    setBusy(true);
    setShown(null);
    const result = await request<LogoKept>(LOGO_UPLOAD_PATH, {
      method: "POST",
      body: await logoBody(setupCode, file),
      atRoot: true,
    });
    setBusy(false);
    if (result.ok) {
      setShown({ kind: "kept", media: result.data.media_type });
      return;
    }
    if (result.failure.status === 404) {
      setShown({
        kind: "refused",
        failure: { ...result.failure, problems: [] },
        sentence: SETUP_REFUSED_MESSAGE,
      });
      return;
    }
    const problem = (result.body as { problem?: unknown } | null)?.problem;
    setShown(
      typeof problem === "string" && problem !== ""
        ? { kind: "refused", failure: result.failure, sentence: problem }
        : { kind: "refused", failure: result.failure },
    );
  }

  return (
    <section className="first-run__section">
      <h2>{LOGO_TITLE}</h2>
      <p>{LOGO_LEDE}</p>
      <div className="rjsf-field">
        <label className="control-label" htmlFor="first-run-company-logo-file">
          {LOGO_LABEL}
        </label>
        <input
          id="first-run-company-logo-file"
          type="file"
          className="form-control"
          accept={LOGO_ACCEPT}
          disabled={busy}
          onChange={(event) => void chosen(event.target.files?.[0] ?? null)}
        />
      </div>
      {shown?.kind === "kept" ? <p className="note">{LOGO_KEPT}</p> : null}
      {shown?.kind === "sentence" ? (
        <Notice title={LOGO_NOT_KEPT_TITLE}>
          <p>{shown.sentence}</p>
        </Notice>
      ) : null}
      {shown?.kind === "refused" ? (
        <FailureNotice
          failure={shown.failure}
          title={LOGO_NOT_KEPT_TITLE}
          {...(shown.sentence === undefined ? {} : { sentence: shown.sentence })}
        />
      ) : null}
    </section>
  );
}
