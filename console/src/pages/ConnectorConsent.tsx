/**
 * Where the vendor sends a person back after a consent: the answer handed over once, and what it
 * came to, with the source's own page one press away.
 *
 * The vendor's code and state arrive in this page's address. The page hands them to the callback
 * once (`consentAtVendor.handOver`, the request kept in a ref so an effect run twice sends one), then
 * takes them out of the address, so a reload or a copied link
 * carries neither, and says what the API said: kept, or the consent withdrawn, in the API's words.
 * A refusal the API made is drawn whole by `FailureNotice`, as every refusal on this console is.
 *
 * Task ids: M11.8.6
 */

import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import type { ApiFailure } from "../api/errors";
import { Button } from "../components/ui/button";
import { FailureNotice } from "../ui/FailureNotice";
import { Notice } from "../ui/Notice";
import { handOver, vendorAnswer, type ConsentAnswered } from "./connectors/consentAtVendor";

export const CONSENT_HEADING = "Connecting with the vendor";
export const CONSENT_WAITING = "Handing the vendor's answer to this install.";
export const CONSENT_NOT_KEPT = "The consent was not kept";
export const CONSENT_NOTHING_TO_HAND = "There is no answer from a vendor in this address.";
export const GO_TO_SOURCE = "Go to the source";

export function ConnectorConsent() {
  const location = useLocation();
  const navigate = useNavigate();
  const [answer] = useState(() => vendorAnswer(location.search));
  const [done, setDone] = useState<ConsentAnswered | null>(null);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const sent = useRef<ReturnType<typeof handOver> | null>(null);

  useEffect(() => {
    if (!answer.state) {
      return;
    }
    let live = true;
    sent.current ??= handOver(answer);
    void sent.current.then((result) => {
      if (!live) {
        return;
      }
      if (result.ok) {
        setDone(result.data);
      } else {
        setFailure(result.failure);
      }
    });
    // Neither the code nor the state stays in the address once it has been read.
    if (location.search) {
      navigate(location.pathname, { replace: true });
    }
    return () => {
      live = false;
    };
    // The answer is read once, from the address the vendor sent; see `handOver`.
  }, [answer, location.pathname, location.search, navigate]);

  return (
    <section aria-label={CONSENT_HEADING}>
      <h1>{CONSENT_HEADING}</h1>
      {!answer.state ? <p>{CONSENT_NOTHING_TO_HAND}</p> : null}
      {answer.state && done === null && failure === null ? <p role="status">{CONSENT_WAITING}</p> : null}
      {failure === null ? null : <FailureNotice failure={failure} title={CONSENT_NOT_KEPT} />}
      {done === null ? null : (
        <Notice title={done.kept ? "Consent kept" : CONSENT_NOT_KEPT} withoutTrace="">
          <p>{done.told}</p>
          <Button asChild variant="outline">
            <Link to={done.back_to}>{GO_TO_SOURCE}</Link>
          </Button>
        </Notice>
      )}
    </section>
  );
}
