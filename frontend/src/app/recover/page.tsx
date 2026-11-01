"use client";

import Link from "next/link";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { api, prepareCsrf, type ApiError } from "@/lib/api";
import { Button, FormField, Notice } from "@/components/ui";
import { AccountLayout } from "@/components/account-layout";
import { PasswordInput } from "@/components/password-input";

export default function RecoveryPage() {
  const [token, setToken] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [complete, setComplete] = useState(false);
  const pending = useRef(false);
  const errorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const readToken = () => setToken(new URLSearchParams(window.location.hash.slice(1)).get("token") ?? "");
    readToken();
    window.addEventListener("hashchange", readToken);
    return () => window.removeEventListener("hashchange", readToken);
  }, []);
  useEffect(() => { if (error) errorRef.current?.focus(); }, [error]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending.current) return;
    pending.current = true;
    setBusy(true); setError(""); setFieldErrors({}); setMessage("");
    try {
      await prepareCsrf();
      if (token) {
        await api("/auth/recovery/complete", { method: "POST", body: JSON.stringify({ token, password }) });
        setComplete(true); setPassword(""); setToken("");
        window.history.replaceState(null, "", window.location.pathname);
        setMessage("Password updated. You can now sign in with your new password.");
      } else {
        const result = await api<{ message: string }>("/auth/recovery/request", { method: "POST", body: JSON.stringify({ email }) });
        setMessage(result.message);
      }
    } catch (reason) {
      setFieldErrors((reason as ApiError).fieldErrors ?? {});
      setError(reason instanceof Error ? reason.message : "Password recovery could not be completed. Please try again.");
    } finally { pending.current = false; setBusy(false); }
  }

  return <AccountLayout><main id="main-content" tabIndex={-1} className="account-page">
    <header><p className="eyebrow">NSAJ account</p><h1>{complete ? "Password updated" : "Reset your password"}</h1>
      {!complete && <p className="muted-copy">{token ? "Choose a new password to restore access to your account." : "Request a secure link to choose a new password."}</p>}
    </header>
    {complete ? <section className="form-card account-stage" aria-label="Recovery complete">
      <Notice tone="success">{message}</Notice><Link className="button-link" href="/sign-in">Sign in with your new password</Link>
    </section> : <form className="form-card" onSubmit={submit} aria-busy={busy}>
      {token ? <FormField label="New password" required hint="Use 12–128 characters." error={fieldErrors.password}><PasswordInput minLength={12} maxLength={128} autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} /></FormField>
        : <><p>If an account matches, recovery instructions will be sent to that email address.</p><FormField label="Email" required error={fieldErrors.email}><input type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} /></FormField></>}
      {error && <div ref={errorRef} tabIndex={-1}><Notice tone="error">{error}</Notice></div>}
      {message && <Notice tone="success">{message}</Notice>}
      <Button disabled={busy}>{busy ? (token ? "Updating password…" : "Sending instructions…") : (token ? "Update password" : "Send recovery instructions")}</Button>
      {token && <Link href="/recover" onClick={() => { setToken(""); setError(""); setFieldErrors({}); window.history.replaceState(null, "", "/recover"); }}>Request a new recovery link</Link>}
    </form>}
    {!complete && <p className="account-links"><Link href="/sign-in">Back to sign in</Link></p>}
  </main></AccountLayout>;
}
