"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {ChoiceField} from "@/components/choice-field";
import {compareWork} from "@/lib/work-priority";
import { useConfirm } from "@/components/ui";
import { useUnsavedChanges } from "@/components/use-unsaved-changes";
import { api, type ApiError } from "@/lib/api";
import { ManuscriptProgress } from "@/components/manuscript-progress";

type Assignment = { id: string; reference: string; title: string; status: string; due_at: string | null; round_number: number };
type Manuscript = { id: string; reference: string; title: string; abstract: string; authors: { full_name: string; affiliation: string }[]; files: { id: string; name: string; url: string }[] };

export default function ReviewerWorkspacePage() {
  const router = useRouter();
  const confirm = useConfirm();
  const [items, setItems] = useState<Assignment[]>([]);
  const [selected, setSelected] = useState<Assignment | null>(null);
  const [manuscript, setManuscript] = useState<Manuscript | null>(null);
  const [access, setAccess] = useState<"loading" | "ready" | "denied" | "error">("loading");
  const [detailLoading, setDetailLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const detailSequence = useRef(0);
  useUnsavedChanges(dirty);

  function reportError(reason: unknown) {
    const status = (reason as ApiError)?.status;
    if (status === 401) { router.replace("/sign-in"); return; }
    setError(reason instanceof Error ? reason.message : "The reviewer workspace is unavailable. Try again.");
    if (status === 403 && !selected) setAccess("denied");
  }

  async function load(initial = false) {
    if (initial) setAccess("loading");
    try {
      const me = await api<{ authenticated?: boolean; roles: string[] }>("/auth/me");
      if (me.authenticated === false) { router.replace("/sign-in"); return []; }
      if (!me.roles.includes("reviewer")) { setAccess("denied"); setError("A Reviewer role is required to use this workspace."); return []; }
      const updated = (await api<{ items: Assignment[] }>("/reviewer/assignments")).items;
      updated.sort(compareWork); setItems(updated);
      setAccess("ready");
      return updated;
    } catch (reason) { reportError(reason); if (initial && (reason as ApiError)?.status !== 403) setAccess("error"); throw reason; }
  }

  useEffect(() => { void load(true).catch(() => {}); return () => { detailSequence.current += 1; }; }, []);

  async function changeSelection(assignment: Assignment) {
    if (busy || assignment.id === selected?.id) return;
    if (dirty && !await confirm({title: "Discard unsaved review changes?", description: "Your entries have not been sent. Switching assignments will discard them.", confirmLabel: "Discard changes", danger: true})) return;
    detailSequence.current += 1;
    setSelected(assignment); setManuscript(null); setDetailLoading(false); setDirty(false); setError(""); setNotice("");
    if (assignment.status === "accepted") await openAssignment(assignment);
  }

  async function openAssignment(assignment: Assignment) {
    const sequence = ++detailSequence.current;
    setError(""); setManuscript(null); setDetailLoading(true);
    try {
      const data = await api<Manuscript>(`/reviewer/assignments/${assignment.id}`);
      if (sequence === detailSequence.current) setManuscript(data);
    } catch (reason) { if (sequence === detailSequence.current) reportError(reason); }
    finally { if (sequence === detailSequence.current) setDetailLoading(false); }
  }

  async function refresh() {
    if (dirty && !await confirm({title: "Discard unsaved review changes?", description: "Refreshing this assignment discards your unsent entries.", confirmLabel: "Discard and refresh", danger: true})) return;
    setError("");
    try {
      const updated = await load();
      detailSequence.current += 1;
      setSelected(current => updated.find(item => item.id === current?.id) ?? null);
      setManuscript(null); setDetailLoading(false); setDirty(false);
    } catch { /* The loader retains the current assignment and displays the read failure. */ }
  }

  async function respond(event: FormEvent<HTMLFormElement>, assignment: Assignment) {
    event.preventDefault(); if (busy) return;
    const data = new FormData(event.currentTarget);
    const accept = data.get("response") === "accept";
    setBusy(true); setError(""); setNotice("");
    try {
      const response = await api<{status: string}>(`/reviewer/assignments/${assignment.id}/respond`, { method: "POST", body: JSON.stringify({accept, confidentiality_accepted: accept && data.get("confidentiality") === "yes", has_conflict: accept && data.get("conflict") === "yes", conflict_details: data.get("conflict_details")}) });
      setDirty(false);
      setSelected({...assignment, status: response.status});
      setNotice(accept ? "Your response was recorded." : "You declined this assignment.");
      // The list response is authoritative: never keep the old invited object after acceptance.
      const updated = await load();
      const current = updated.find(item => item.id === assignment.id) ?? null;
      setSelected(current); setManuscript(null);
      if (current?.status === "accepted") await openAssignment(current);
    } catch (reason) { reportError(reason); }
    finally { setBusy(false); }
  }

  async function submitReport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!selected || selected.status !== "accepted" || busy) return;
    const assignment = selected;
    const data = new FormData(event.currentTarget);
    if (!await confirm({title: "Submit confidential review?", description: `${assignment.reference}: ${assignment.title}. The assigned editor will receive this report. A recommendation is advisory and is separate from the editorial decision.`, confirmLabel: "Submit review"})) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await api(`/reviewer/assignments/${assignment.id}/report`, { method: "POST", body: JSON.stringify({recommendation: data.get("recommendation"), comments_to_editor: data.get("comments_to_editor"), comments_to_author: data.get("comments_to_author")}) });
      setDirty(false); setManuscript(null);
      // Close the editable report immediately, even when the following list refresh fails.
      setSelected({...assignment, status: "completed"});
      setNotice("Your confidential report was submitted to the assigned editor.");
      const updated = await load();
      setSelected(updated.find(item => item.id === assignment.id) ?? {...assignment, status: "completed"});
    } catch (reason) { reportError(reason); }
    finally { setBusy(false); }
  }

  return <main id="main-content" tabIndex={-1} className="workspace-page">
    <header className="workspace-header"><div><p className="eyebrow">Reviewer workspace</p><h1>Assigned review work</h1><p className="muted-copy">Respond to invitations and prepare reports for your assigned manuscripts.</p></div></header>
    <p className="draft-warning" role="note">Your review is confidential and is visible only to the assigned editorial team. A recommendation is not an editorial decision.</p>
    {access === "loading" && <p role="status" className="notice-message">Loading review assignments...</p>}
    {access === "denied" && <section className="workspace-surface"><h2>Reviewer access required</h2><p role="alert" className="error-message">{error}</p><p>Ask a Site Admin to check your assigned roles if you believe this is incorrect.</p></section>}
    {access === "error" && <section className="workspace-surface"><h2>Workspace unavailable</h2><p role="alert" className="error-message">{error}</p><button className="secondary-button" type="button" onClick={() => void load(true).catch(() => {})}>Try again</button></section>}
    {access === "ready" && <div className="workspace-grid">
      <aside className="draft-list" aria-label="Review assignments"><div className="draft-list__heading"><h2>My assignments</h2><button type="button" disabled={busy} onClick={() => void refresh()}>Refresh</button></div>
        {items.length === 0 && <p className="muted-copy">No review assignments. New invitations will appear here.</p>}
        {items.map(item => <button key={item.id} type="button" disabled={busy} aria-current={selected?.id === item.id ? "true" : undefined} data-status={item.status} className={`draft-item${selected?.id === item.id ? " draft-item--selected" : ""}`} onClick={() => void changeSelection(item)}><strong>{item.reference}</strong><span>{item.title}</span><small>{item.status.replaceAll("_", " ")} / Round {item.round_number} / {item.due_at ? `Due ${new Date(item.due_at).toLocaleDateString()}` : "No deadline"}</small></button>)}
      </aside>
      <section className="draft-editor" aria-busy={busy || detailLoading} aria-label="Selected review assignment">
        {!selected && <><h2>Select an assignment</h2><p className="muted-copy">Only work assigned to this reviewer account appears here.</p></>}
        {selected && <header className="record-heading"><p className="eyebrow">Paper ID: {selected.reference} / {selected.status.replaceAll("_", " ")}</p><h2>{selected.title}</h2><p className="muted-copy">Round {selected.round_number}{selected.due_at ? ` / Due ${new Date(selected.due_at).toLocaleString()}` : " / No deadline"}</p></header>}
        <ManuscriptProgress reference={selected?.reference} title={selected?.title} status={selected?.status} roundNumber={selected?.round_number} scope="review" />
        {error && <p className="error-message" role="alert">{error}</p>}{notice && <p className="notice-message" role="status">{notice}</p>}
        {selected?.status === "invited" && <section className="work-section"><h3>Respond to this invitation</h3><p>Review confidentiality and declare any potential conflict before accepting.</p><form key={selected.id} onChange={() => setDirty(true)} onSubmit={event => void respond(event, selected)}><fieldset className="form-fields" disabled={busy}>
          <ChoiceField name="response" label="Response" defaultValue="accept" options={[{"value": "accept", "label": "Accept"}, {"value": "decline", "label": "Decline"}]}/>
          <ChoiceField name="confidentiality" label="Confidentiality acknowledgement" defaultValue="no" options={[{"value": "no", "label": "Not acknowledged"}, {"value": "yes", "label": "I will keep the manuscript and review confidential"}]}/>
          <ChoiceField name="conflict" label="Potential conflict" defaultValue="no" options={[{"value": "no", "label": "No conflict to report"}, {"value": "yes", "label": "I need to report a potential conflict"}]}/>
          <label>Conflict details<textarea name="conflict_details" rows={3} maxLength={4000} /></label>
          <div className="work-actions"><button className="button-link" disabled={busy}>{busy ? "Recording response..." : "Record response"}</button></div>
        </fieldset></form></section>}
        {selected?.status === "conflict_reported" && <section className="review-state"><h3>Awaiting conflict resolution</h3><p>The editorial team must resolve your reported conflict before manuscript access and review are available.</p></section>}
        {selected?.status === "completed" && <section className="review-state"><h3>Review submitted</h3><p>Your report has been handed to the editorial team. An authorized editor now considers the reports and records a decision. No further action is required from you for this report.</p></section>}
        {selected && ["declined", "cancelled", "expired"].includes(selected.status) && <section className="review-state"><h3>Assignment {selected.status}</h3><p>This assignment is closed and manuscript access is unavailable.</p></section>}
        {selected && ["accepted", "completed"].includes(selected.status) && !manuscript && !detailLoading && <div className="work-actions"><button className="button-link" type="button" disabled={busy} onClick={() => void openAssignment(selected)}>{selected.status === "accepted" ? "Retry assigned manuscript" : "Open assigned manuscript"}</button></div>}
        {detailLoading && <p role="status" className="notice-message">Loading assigned manuscript...</p>}
        {manuscript && selected && ["accepted", "completed"].includes(selected.status) && <><section className="work-section"><h3>Manuscript summary</h3><p className="preserve-lines">{manuscript.abstract}</p><h3>Author metadata</h3>{manuscript.authors.length ? <ol>{manuscript.authors.map((author,index) => <li key={index}>{author.full_name}{author.affiliation ? ` / ${author.affiliation}` : ""}</li>)}</ol> : <p className="muted-copy">Author identity is hidden under the configured review model.</p>}<h3>Assigned manuscript file</h3>{manuscript.files.length ? <ul>{manuscript.files.map(file => <li key={file.id}><a href={file.url}>{file.name}</a></li>)}</ul> : <p className="muted-copy">No clean assigned file is available.</p>}</section>
          {selected.status === "accepted" && <section className="work-section"><h3>Confidential review report</h3><p>Comments to the editor stay confidential. The editor determines the decision and author correspondence.</p><form key={`report-${selected.id}`} onChange={() => setDirty(true)} onSubmit={event => void submitReport(event)}><fieldset className="form-fields" disabled={busy}><label>Recommendation<select name="recommendation"><option value="minor_revision">Minor revision</option><option value="major_revision">Major revision</option><option value="accept">Accept</option><option value="decline">Decline</option></select></label><label><span className="field-label">Confidential comments to editor <span className="required-mark" aria-hidden="true">*</span><span className="visually-hidden"> (required)</span></span><textarea name="comments_to_editor" required rows={6} /></label><label>Comments to author (optional)<textarea name="comments_to_author" rows={6} /></label><div className="work-actions"><button className="button-link" disabled={busy}>{busy ? "Submitting review..." : "Submit confidential review"}</button>{dirty && <span className="muted-copy">Unsent changes</span>}</div></fieldset></form></section>}
        </>}
      </section>
    </div>}
  </main>;
}
