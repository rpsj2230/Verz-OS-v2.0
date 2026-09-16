/**
 * Where a directory sends the person back after the staff list screen's sign-in, in its own window.
 *
 * `setup/staffList.ts` argues why the sign-in happens in a second window. This is that window's
 * last page: it posts the vendor's answer to the tab that opened it, addressed to this console's
 * own origin and to nothing wider, and closes. It holds nothing, keeps nothing and asks the API
 * nothing, because the code is useless without the verifier the wizard tab kept and that tab is
 * the one that uses it.
 *
 * Opened any other way, with no tab behind it, it says what it is and does nothing else.
 *
 * Task ids: M42.5.7
 */

import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { SIGNED_IN_KIND, type SignedIn } from "../setup/staffList";

export const SIGNED_IN_TITLE = "Signed in to your staff list";
export const SIGNED_IN_BODY =
  "You can close this window. The setup page you came from reads your staff list next.";

export function StaffListSignedIn() {
  const { search } = useLocation();

  useEffect(() => {
    const opener = window.opener as Window | null;
    if (opener === null) {
      return;
    }
    const given = new URLSearchParams(search);
    const answer: SignedIn = {
      kind: SIGNED_IN_KIND,
      state: given.get("state") ?? "",
      code: given.get("code") ?? "",
      error: given.get("error_description") ?? given.get("error") ?? "",
    };
    opener.postMessage(answer, window.location.origin);
    window.close();
  }, [search]);

  return (
    <main className="first-run">
      <h1>{SIGNED_IN_TITLE}</h1>
      <p>{SIGNED_IN_BODY}</p>
    </main>
  );
}
