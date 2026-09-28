/**
 * One credential's page, at `/credentials/{family}/{name}` and `/credentials/{family}/{name}/{view}`.
 * The page itself is `credentials/CredentialDetailPage.tsx`, on the shared page kit; this reads the
 * address and keys the page on the slot, so one slot's saved sentence never shows on another's.
 *
 * Task ids: M27.11.10, M27.16.1
 */

import { useParams } from "react-router-dom";
import { CredentialDetailPage } from "./credentials/CredentialDetailPage";

export function Credential() {
  const { family, name, view } = useParams();
  if (family === undefined || name === undefined) {
    return null;
  }
  const slot = `${family}/${name}`;
  return <CredentialDetailPage key={slot} slot={slot} view={view} />;
}
