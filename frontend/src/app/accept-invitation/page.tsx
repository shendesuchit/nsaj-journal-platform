"use client";

import Link from "next/link";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { api, prepareCsrf, type ApiError } from "@/lib/api";
import { Button, FormField, Notice } from "@/components/ui";
import { AccountLayout } from "@/components/account-layout";
import { PasswordInput } from "@/components/password-input";
import { workspaceForRoles } from "@/lib/account-navigation";

type Acceptance = {
  ok: boolean;
  role: string;
  mfa_setup: null | { secret: string; otpauth_uri: string; recovery_codes: string[] };
};

export default function AcceptInvitationPage() {
  const router = useRouter();
  const [intakeToken, setIntakeToken] = useState("");
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [accepted, setAccepted] = useState<Acceptance | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const stageRef = useRef<HTMLHeadingElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  useEffect(() => { if (accepted) stageRef.current?.focus(); }, [accepted]);
  useEffect(() => { if (error) errorRef.current?.focus(); }, [error]);

  useEffect(() => {
    const readToken = () => {
      const intake = new URLSearchParams(window.location.hash.slice(1)).get("intake") ?? "";
      setIntakeToken(intake);
      if (intake) sessionStorage.setItem("nsaj-email-intake", intake);
      setToken(new URLSearchParams(window.location.hash.slice(1)).get("token") ?? "");
    };
    readToken();
    window.addEventListener("hashchange", readToken);
    return () => window.removeEventListener("hashchange", readToken);
  }, []);

  async function accept(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending.current) return;
    pending.current = true; setBusy(true); setError(""); setFieldErrors({});
    try {
      await prepareCsrf();
      const response = await api<Acceptance>("/invitations/accept", {
        method: "POST",
        body: JSON.stringify({ token, password }),
      });
      setAccepted(response);
      setPassword("");
      window.history.replaceState(null, "", window.location.pathname);
      if (!response.mfa_setup) router.push(intakeToken ? "/email-submission" : workspaceForRoles([response.role]));
    } catch (reason) {
      setFieldErrors((reason as ApiError).fieldErrors ?? {});
      setError(reason instanceof Error ? reason.message : "Invitation could not be accepted.");
    } finally { pending.current = false; setBusy(false); }
  }

  async function confirmMfa(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending.current) return;
    pending.current = true; setBusy(true); setError(""); setFieldErrors({});
    try {
      await api("/auth/mfa/setup/confirm", {
        method: "POST",
        body: JSON.stringify({ code }),
      });
      const user = await api<{ roles: string[] }>("/auth/me");
      router.push(intakeToken ? "/email-submission" : workspaceForRoles(user.roles));
    } catch (reason) {
      setFieldErrors((reason as ApiError).fieldErrors ?? {});
      setError(reason instanceof Error ? reason.message : "MFA setup failed.");
    } finally { pending.current = false; setBusy(false); }
  }

  return (
    <AccountLayout><main id="main-content" tabIndex={-1} className="account-page">
      <p className="eyebrow">NSAJ account</p>
      <h1>Create your account</h1>
      <p className="muted-copy">{accepted?.mfa_setup ? "Secure your account before continuing." : "Choose a password to finish setting up your verified account."}</p>
      {!accepted && (
        <form className="form-card" onSubmit={accept} aria-busy={busy}>
          {!token && <Notice tone="info">Open the setup link sent to your email. Authors can request a fresh link from the registration page.</Notice>}
          <FormField label="Create password" required hint="Use 12–128 characters." error={fieldErrors.password}><PasswordInput minLength={12} maxLength={128} autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} /></FormField>
          <Button disabled={!token || busy}>{busy ? "Creating account…" : "Create account"}</Button>
        </form>
      )}
      {accepted?.mfa_setup && (
        <form className="form-card" onSubmit={confirmMfa} aria-busy={busy}>
          <h2 ref={stageRef} tabIndex={-1}>Set up multi-factor authentication</h2>
          <p>Use your authenticator app with this setup key:</p>
          <code className="setup-key">{accepted.mfa_setup.secret}</code>
          <p className="small-copy">Manual setup URI: <code>{accepted.mfa_setup.otpauth_uri}</code></p>
          <div className="recovery-codes"><strong>Store these one-use recovery codes securely. They will not be shown again.</strong><ul>{accepted.mfa_setup.recovery_codes.map((item) => <li key={item}><code>{item}</code></li>)}</ul></div>
          <FormField label="Authenticator code" required error={fieldErrors.code}><input autoComplete="one-time-code" value={code} onChange={(event) => setCode(event.target.value)} /></FormField>
          <Button disabled={busy}>{busy ? "Confirming…" : "Confirm and continue"}</Button>
        </form>
      )}
      {error && <div ref={errorRef} tabIndex={-1}><Notice tone="error">{error}</Notice></div>}
      {intakeToken && !accepted && <p><Link href="/email-submission">Already have an account? Continue to your emailed draft</Link></p>}
      <p className="account-links"><Link href="/register">Author registration</Link> <Link href="/sign-in">Back to sign in</Link></p>
    </main></AccountLayout>
  );
}
