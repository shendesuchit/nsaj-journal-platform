"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useConfirm } from "@/components/ui";
import { useUnsavedChanges } from "@/components/use-unsaved-changes";
import { api, type ApiError } from "@/lib/api";

type Version = { id: string; title: string; declarations: string[]; approved_at: string | null };
export default function ChecklistPage() {
  const router = useRouter();
  const confirm = useConfirm();
  const [items, setItems] = useState<Version[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [access, setAccess] = useState<"loading" | "ready" | "denied" | "error">("loading");
  const [busy, setBusy] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [title, setTitle] = useState("");
  const [declarations, setDeclarations] = useState("");
  const errorSummary = useRef<HTMLParagraphElement>(null);
  const dirty = title !== "" || declarations !== "";
  useUnsavedChanges(dirty);
  useEffect(() => { if (error) errorSummary.current?.focus(); }, [error]);
  const current = [...items].filter(version => version.approved_at).sort((a,b) => Date.parse(b.approved_at!) - Date.parse(a.approved_at!))[0];

  function report(reason: unknown, fallback: string) {
    if ((reason as ApiError)?.status === 401) { router.replace("/sign-in"); return; }
    if ((reason as ApiError)?.status === 403) setAccess("denied");
    setError(reason instanceof Error ? reason.message : fallback);
  }
  async function load() {
    setRefreshing(true);
    try { const response = await api<{items: Version[]}>("/editorial/submission-checklists"); setItems(response.items); setAccess("ready"); }
    catch (reason) { report(reason, "Checklist versions could not be loaded."); if ((reason as ApiError)?.status !== 403) setAccess(previous => previous === "ready" ? "ready" : "error"); }
    finally { setRefreshing(false); }
  }
  useEffect(() => { void load(); }, []);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy) return;
    setBusy("create"); setError(""); setNotice("");
    try {
      await api("/editorial/submission-checklists", {method: "POST", body: JSON.stringify({title, declarations: declarations.split("\n").map(text => text.trim()).filter(Boolean)})});
      setTitle(""); setDeclarations(""); setNotice("Draft checklist version saved. Authors will only use it after you approve its exact wording.");
      await load();
    } catch (reason) { report(reason, "Could not save checklist. Your wording has been retained."); }
    finally { setBusy(""); }
  }
  async function approve(version: Version) {
    if (busy) return;
    if (!await confirm({title: "Approve this exact declaration wording?", description: `${version.title}, version ${version.id}, containing ${version.declarations.length} declarations. It will replace the checklist for future submissions immediately. Approval makes this version immutable. Existing submission receipts keep their original wording.`, confirmLabel: "Approve checklist"})) return;
    setBusy(version.id); setError(""); setNotice("");
    try { await api(`/editorial/submission-checklists/${version.id}/approve`, {method: "POST"}); setNotice(`Checklist ${version.title} approved for future submissions.`); await load(); }
    catch (reason) { report(reason, "Approval failed. Refresh the list and review the current version."); }
    finally { setBusy(""); }
  }
  return <main id="main-content" tabIndex={-1} className="workspace-page">
    <header className="workspace-header"><div><p className="eyebrow">Editorial operations / Editor-in-Chief</p><h1>Submission declarations</h1><p className="muted-copy">Manage the exact wording authors acknowledge when submitting a manuscript.</p></div><Link href="/editorial">Return to editorial workspace</Link></header>
    <p className="draft-warning" role="note">Approved versions are immutable. A new approval replaces the checklist for future submissions; existing receipts retain their original declarations. No journal wording is supplied automatically.</p>
    {error && <p ref={errorSummary} tabIndex={-1} className="error-message" role="alert">{error}</p>}{notice && <p className="notice-message" role="status">{notice}</p>}
    {access === "loading" && <p role="status">Loading declaration versions...</p>}
    {access === "denied" && <section className="workspace-surface"><h2>Editor-in-Chief access required</h2><p>Only the Editor-in-Chief can create or approve submission declarations. Site Admin accounts cannot manage confidential editorial settings.</p></section>}
    {access === "error" && <section className="workspace-surface"><h2>Declarations unavailable</h2><button type="button" className="secondary-button" onClick={() => {setError(""); void load();}}>Try again</button></section>}
    {access === "ready" && <>
      <section className="workspace-surface" aria-labelledby="current-checklist-title"><h2 id="current-checklist-title">Current checklist</h2>{current ? <><h3>{current.title}</h3><p className="work-meta">Version {current.id}</p><p>Approved {new Date(current.approved_at!).toLocaleString()}</p><ol className="declaration-list">{current.declarations.map((text,index) => <li key={index}>{text}</li>)}</ol></> : <p>No approved checklist. Authors can save drafts, but final submission is unavailable until declaration wording is approved.</p>}</section>
      <section className="draft-editor" aria-busy={busy === "create"} aria-labelledby="create-checklist-title"><h2 id="create-checklist-title">Create a checklist version</h2><p>Enter approved journal wording for review. Saving this version does not activate it.</p><form onSubmit={create}><fieldset className="form-fields" disabled={!!busy}><label><span className="field-label">Checklist title <span className="required-mark" aria-hidden="true">*</span><span className="visually-hidden"> (required)</span></span><input name="title" maxLength={200} required value={title} onChange={event => setTitle(event.target.value)} /></label><label><span className="field-label">Declarations, one per line <span className="required-mark" aria-hidden="true">*</span><span className="visually-hidden"> (required)</span></span><textarea name="declarations" rows={10} required value={declarations} onChange={event => setDeclarations(event.target.value)} aria-describedby="declaration-help" /></label><p id="declaration-help" className="muted-copy">Enter 1 to 30 distinct declarations, up to 4,000 characters each. Each nonempty line becomes one declaration. Review the exact wording below before approval.</p><div className="work-actions"><button className="button-link" disabled={!!busy}>{busy === "create" ? "Saving checklist..." : "Save draft checklist"}</button>{dirty && <span className="muted-copy">Unsaved wording</span>}</div></fieldset></form></section>
      <section className="workspace-surface" aria-labelledby="checklist-versions-title" aria-busy={refreshing}><div className="draft-list__heading"><h2 id="checklist-versions-title">Checklist versions</h2><button className="secondary-button" type="button" disabled={!!busy || refreshing} onClick={() => {setError(""); void load();}}>{refreshing ? "Refreshing..." : "Refresh versions"}</button></div>
        {items.length === 0 ? <p className="muted-copy">No versions saved yet. Create a draft checklist above.</p> : items.map(item => <article className="work-section" key={item.id}><header className="record-heading"><h3>{item.title}</h3><p className="work-meta">Version {item.id}</p><p>{item.id === current?.id ? "Current approved checklist" : item.approved_at ? "Previously approved version" : "Draft - awaiting approval"}</p></header><ol className="declaration-list">{item.declarations.map((text,index) => <li key={index}>{text}</li>)}</ol>{item.approved_at ? <p className="work-meta">Approval recorded {new Date(item.approved_at).toLocaleString()}</p> : <div className="work-actions"><button className="button-link" disabled={!!busy} onClick={() => void approve(item)}>{busy === item.id ? "Approving checklist..." : "Approve this exact wording"}</button></div>}</article>)}
      </section>
    </>}
  </main>;
}
