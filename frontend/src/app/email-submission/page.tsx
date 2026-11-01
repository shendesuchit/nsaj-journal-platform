"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { AccountLayout } from "@/components/account-layout";
import { Notice } from "@/components/ui";
import { api } from "@/lib/api";
export default function EmailSubmissionPage() {
  const [token, setToken] = useState("");
  const [signedIn, setSignedIn] = useState<boolean | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<{id: string; reference: string; warnings: string[]} | null>(null);
  useEffect(() => {
    const value = new URLSearchParams(window.location.hash.slice(1)).get("token") || sessionStorage.getItem("nsaj-email-intake") || "";
    if (value) sessionStorage.setItem("nsaj-email-intake", value);
    setToken(value); window.history.replaceState(null, "", window.location.pathname);
    api<{authenticated: boolean}>("/auth/me").then(user => setSignedIn(user.authenticated)).catch(() => setSignedIn(false));
  }, []);
  async function claim() {
    setBusy(true); setError("");
    try { const result = await api<{id: string; reference: string; warnings: string[]}>("/author/email-intake/claim", {method: "POST", body: JSON.stringify({token})}); setDraft(result); sessionStorage.removeItem("nsaj-email-intake"); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Your draft could not be prepared."); }
    finally { setBusy(false); }
  }
  return <AccountLayout><main id="main-content" tabIndex={-1} className="account-page"><p className="eyebrow">Email submission</p><h1>Review your emailed manuscript</h1><p>We will prepare a private draft from your email. Verify its details, add any missing information and complete the normal submission checklist in your workspace.</p>
    {error && <Notice tone="error">{error}</Notice>}
    {!token && <Notice tone="info">Open the private link sent in response to your submission email.</Notice>}
    {signedIn === null ? <p role="status">Checking your account…</p> : !signedIn ? <Link className="button-link" href="/sign-in?return=email-submission">Sign in to continue</Link> : !draft && <button className="button-link" disabled={!token || busy} onClick={() => void claim()}>{busy ? "Preparing draft…" : "Prepare my draft"}</button>}
    {draft && <><Notice tone="success">Draft {draft.reference} is ready. It has not been formally submitted.</Notice>{draft.warnings.length > 0 && <ul>{draft.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>}<Link className="button-link" href={`/author?draft=${encodeURIComponent(draft.id)}`}>Review draft and declarations</Link></>}
  </main></AccountLayout>;
}
