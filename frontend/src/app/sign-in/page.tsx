"use client";

import Link from "next/link";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { api, prepareCsrf, type ApiError } from "@/lib/api";
import { Button, FormField, Notice } from "@/components/ui";
import { AccountLayout } from "@/components/account-layout";
import { PasswordInput } from "@/components/password-input";
import { workspaceForRoles } from "@/lib/account-navigation";

type LoginResult = {
  authenticated: boolean;
  mfa_required?: boolean;
  mfa_setup_required?: boolean;
  mfa_secret?: string;
  otpauth_uri?: string;
  recovery_codes?: string[];
};

export default function SignInPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [result, setResult] = useState<LoginResult | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const stageRef = useRef<HTMLHeadingElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  useEffect(() => { if (result) stageRef.current?.focus(); }, [result]);
  useEffect(() => { if (error) errorRef.current?.focus(); }, [error]);

  async function continueAfterSignIn() {
    const user = await api<{ roles: string[] }>("/auth/me");
    router.push(new URLSearchParams(window.location.search).get("return") === "email-submission" ? "/email-submission" : workspaceForRoles(user.roles));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending.current) return;
    pending.current = true; setError(""); setFieldErrors({}); setBusy(true);
    try {
      await prepareCsrf();
      const response = await api<LoginResult>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      setResult(response);
      setPassword(""); setCode("");
      if (response.authenticated) await continueAfterSignIn();
    } catch (reason) {
      setFieldErrors((reason as ApiError).fieldErrors ?? {});
      setError(reason instanceof Error ? reason.message : "Sign in failed.");
    } finally {
      pending.current = false; setBusy(false);
    }
  }

  async function verifyCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending.current) return;
    pending.current = true; setError(""); setFieldErrors({}); setBusy(true);
    try {
      await api("/auth/mfa/verify", {
        method: "POST",
        body: JSON.stringify({ code }),
      });
      await continueAfterSignIn();
    } catch (reason) {
      setFieldErrors((reason as ApiError).fieldErrors ?? {});
      setError(reason instanceof Error ? reason.message : "Code verification failed.");
    } finally {
      pending.current = false; setBusy(false);
    }
  }

  async function confirmSetup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending.current) return;
    pending.current = true; setError(""); setFieldErrors({}); setBusy(true);
    try {
      await api("/auth/mfa/setup/confirm", {
        method: "POST",
        body: JSON.stringify({ code }),
      });
      await continueAfterSignIn();
    } catch (reason) {
      setFieldErrors((reason as ApiError).fieldErrors ?? {});
      setError(reason instanceof Error ? reason.message : "MFA setup failed.");
    } finally {
      pending.current = false; setBusy(false);
    }
  }

  return (
    <AccountLayout><main id="main-content" tabIndex={-1} className="account-page">
      <p className="eyebrow">NSAJ account</p>
      <h1>Sign in</h1>
      {result && <p className="account-progress">{result.mfa_setup_required ? "Account security · Set up authenticator" : "Account security · Verify identity"}</p>}
      <p className="muted-copy">Use the email address associated with your invitation.</p>
      {!result && <p className="form-required-note"><span className="required-mark" aria-hidden="true">*</span> Required fields</p>}
      {!result && (
        <form className="form-card" onSubmit={submit} aria-busy={busy}>
          <FormField label="Email" required error={fieldErrors.email}><input type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} /></FormField>
          <FormField label="Password" required error={fieldErrors.password}><PasswordInput autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} /></FormField>
          <Button disabled={busy}>{busy ? "Signing in…" : "Sign in"}</Button>
        </form>
      )}
      {result?.authenticated && <section className="form-card"><Notice tone="success">You are signed in.</Notice><Button disabled={busy} onClick={async () => { if (pending.current) return; pending.current = true; setBusy(true); setError(""); setFieldErrors({}); try { await continueAfterSignIn(); } catch { setError("Your workspace could not be opened. Please try again."); } finally { pending.current = false; setBusy(false); } }}>Continue to workspace</Button></section>}
      {result?.mfa_required && (
        <form className="form-card" onSubmit={verifyCode} aria-busy={busy}>
          <h2 ref={stageRef} tabIndex={-1}>Verify your identity</h2>
          <p>Enter a six-digit authenticator code or a one-use recovery code.</p>
          <FormField label="Authenticator or recovery code" required error={fieldErrors.code}><input autoComplete="one-time-code" value={code} onChange={(event) => setCode(event.target.value)} /></FormField>
          <Button disabled={busy}>{busy ? "Verifying…" : "Verify"}</Button>
        </form>
      )}
      {result?.mfa_setup_required && (
        <form className="form-card" onSubmit={confirmSetup} aria-busy={busy}>
          <h2 ref={stageRef} tabIndex={-1}>Set up multi-factor authentication</h2>
          <p>Add this account to an authenticator app, then enter its current code.</p>
          <p>Setup key</p><code className="setup-key">{result.mfa_secret}</code>
          <p className="small-copy">Manual setup URI: <code>{result.otpauth_uri}</code></p>
          {result.recovery_codes?.length ? <RecoveryCodes codes={result.recovery_codes} /> : null}
          <FormField label="Authenticator code" required error={fieldErrors.code}><input autoComplete="one-time-code" value={code} onChange={(event) => setCode(event.target.value)} /></FormField>
          <Button disabled={busy}>{busy ? "Confirming…" : "Confirm setup"}</Button>
        </form>
      )}
      {error && <div ref={errorRef} tabIndex={-1}><Notice tone="error">{error}</Notice></div>}
      <p>New author? <Link href="/register">Create your account</Link> — no invitation needed.</p><p className="account-links"><Link href="/recover">Forgot your password?</Link> <Link href="/accept-invitation">Accept an invitation</Link></p>
    </main></AccountLayout>
  );
}

function RecoveryCodes({ codes }: { codes: string[] }) {
  return (
    <div className="recovery-codes">
      <strong>Save these one-use recovery codes now.</strong>
      <ul>{codes.map((code) => <li key={code}><code>{code}</code></li>)}</ul>
    </div>
  );
}
