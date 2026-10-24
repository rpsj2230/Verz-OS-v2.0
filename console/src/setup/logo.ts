/**
 * The company step's logo upload: where it goes, what is chosen, and the file as base64.
 *
 * **The checks here are courtesy and the server's are the rule.** The size and the kinds are
 * restated so a person is told before a file crosses the network, and `brain.branding` decides
 * again from the bytes, which is why the file's name and the browser's idea of its type are not
 * trusted for anything but the file chooser's filter. An SVG is not offered: see
 * `brain.branding.AN_SVG_IS_A_DOCUMENT_THAT_CAN_CARRY_SCRIPT`.
 *
 * Task ids: M42.5.5
 */

/** `POST` the setup code and the image as base64 here. Answered at the root, like every setup route. */
export const LOGO_UPLOAD_PATH = "/setup/logo";

/** The largest file the server keeps, as it states it (`brain.branding.MAX_LOGO_BYTES`). */
export const MAX_LOGO_BYTES = 256 * 1024;

/** What the file chooser offers. A filter and not a check. */
export const LOGO_ACCEPT = "image/png,image/jpeg,image/gif,image/webp";

export interface LogoKept {
  readonly media_type: string;
  readonly bytes_kept: number;
  readonly path: string;
}

/** The body the upload route takes. */
export interface LogoAsked {
  readonly setup_code: string;
  readonly image: string;
}

/** Said when a file is over the limit, before it is sent. */
export const TOO_LARGE =
  "That file is larger than 256 KiB. Export your logo at about twice the height it is drawn and try again.";

/** The bytes of a file as base64, without a data-URL prefix. */
export async function base64Of(file: Blob): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  const chunk = 0x8000;
  for (let at = 0; at < bytes.length; at += chunk) {
    binary += String.fromCharCode(...bytes.subarray(at, at + chunk));
  }
  return btoa(binary);
}

/** The upload route's body for this file. */
export async function logoBody(setupCode: string, file: Blob): Promise<LogoAsked> {
  return { setup_code: setupCode, image: await base64Of(file) };
}
