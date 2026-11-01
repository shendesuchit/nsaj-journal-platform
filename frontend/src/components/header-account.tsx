"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { api, type ApiError } from "@/lib/api";
import { workspaceForRoles } from "@/lib/account-navigation";
import { confirmDiscardUnsavedChanges } from "@/components/use-unsaved-changes";

type AccountIdentity = { display_name: string; roles: string[] };

const roleLabels: Record<string, string> = {
  site_admin: "Site Admin",
  author: "Author",
  reviewer: "Reviewer",
  editor_in_chief: "Editor-in-Chief",
  managing_editor: "Managing Editor",
  associate_editor: "Associate Editor",
  board_member: "Board Member",
};

export function HeaderAccount() {
  const pathname = usePathname();
  const router = useRouter();
  const [identity, setIdentity] = useState<AccountIdentity | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const pending = useRef(false);

  useEffect(() => {
    let active = true;
    void api<{ id?: string; display_name?: string; roles?: string[] }>("/auth/me", { cache: "no-store" })
      .then(user => {
        if (active) {
          setIdentity(typeof user.id === "string" && user.display_name
            ? {display_name: user.display_name, roles: user.roles ?? []}
            : null);
        }
      })
      .catch(() => { if (active) setIdentity(null); });
    return () => { active = false; };
  }, [pathname]);

  async function logout() {
    if (pending.current || !confirmDiscardUnsavedChanges()) return;
    pending.current = true;
    setBusy(true);
    setError("");
    try {
      await api("/auth/logout", { method: "POST" });
      setIdentity(null);
      router.replace("/sign-in");
      router.refresh();
    } catch (reason) {
      if ((reason as ApiError).status === 401) {
        setIdentity(null);
        router.replace("/sign-in");
        router.refresh();
      } else {
        setError("Could not log out. Please try again.");
      }
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }

  return <div className="header-account">
    {identity && <div className="header-account__identity" aria-label={`Signed in as ${identity.display_name}`}>
      <strong className="header-account__name">{identity.display_name}</strong>
      <div className="header-account__roles">{identity.roles.map(role => <span className="header-account__role" key={role}>{roleLabels[role] ?? role.replaceAll("_", " ")}</span>)}</div>
    </div>}
    {identity && workspaceForRoles(identity.roles) !== "/" && <Link className="header-account__workspace" href={workspaceForRoles(identity.roles)}>Workspace</Link>}
    <div className="header-account__controls">
      {identity ? <button className="secondary-button" type="button" disabled={busy} aria-busy={busy || undefined} onClick={() => void logout()}>{busy ? "Logging out..." : "Log out"}</button> : <Link className="secondary-button" href="/sign-in">Sign in</Link>}
      {error && <p className="header-account__error" role="alert">{error}</p>}
    </div>
  </div>;
}
