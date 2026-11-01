"use client";

import { submissionRequirements } from "@/lib/submission-readiness";
import { FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useConfirm } from "@/components/ui";
import { api, type ApiError } from "@/lib/api";

type Checklist = {id: string; title: string; declarations: string[]};
export type SubmittedManuscript = {id: string; reference: string; title: string; status: string; display_status?:string; status_detail?:string|null; editor_assigned?:boolean; updated_at?: string | null};
type Receipt = {reference: string; checklist_id: string; declarations: string[]; submitted_at: string};
type Detail = SubmittedManuscript & {decisions: {decision: string; round_number: number; letter: string; decided_at: string}[]; history: {status: string; created_at: string}[]};
type SavedDraft = {
  title: string;
  abstract: string;
  keywords: string[];
  manuscript_type: string | null;
  discipline: string | null;
  discipline_other: string | null;
  authors: {full_name: string; affiliation: string}[];
  files: {scan_status: string}[];
};
export type SubmissionPreparation = {declarationsReady: boolean; declarationsComplete: boolean};
type Props = {
  draftId: string | null;
  draftTitle?: string;
  draftReference?: string;
  savedDraft: SavedDraft | null;
  dirty: boolean;
  showDraft: boolean;
  selectedManuscript: SubmittedManuscript | null;
  detailVersion: number;
  onSubmitted: (item: SubmittedManuscript, notice: string) => void;
  onManuscriptUpdated: (item: SubmittedManuscript) => void;
  onBusyChange: (busy: boolean) => void;
  onRevisionDirtyChange: (dirty: boolean) => void;
  onPreparationChange: (state: SubmissionPreparation) => void;
};

export function SubmissionIntake({draftId, draftTitle, draftReference, savedDraft, dirty, showDraft, selectedManuscript, detailVersion, onSubmitted, onManuscriptUpdated, onBusyChange, onRevisionDirtyChange, onPreparationChange}: Props) {
  const confirm = useConfirm();
  const router = useRouter();
  const [checklist, setChecklist] = useState<Checklist | null>(null);
  const [checks, setChecks] = useState<number[]>([]);
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [receiptState, setReceiptState] = useState<"loading" | "available" | "missing" | "error">("loading");
  const [detail, setDetail] = useState<Detail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [policyLoading, setPolicyLoading] = useState(true);
  const [policyError, setPolicyError] = useState("");
  const [detailError, setDetailError] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [revisionDirty, setRevisionDirty] = useState(false);
  const sequence = useRef(0);
  const actionError = useRef<HTMLParagraphElement>(null);
  const selectedId = selectedManuscript?.id ?? null;
  const declarationsReady = !policyLoading && !!checklist;
  const declarationsComplete = declarationsReady && checks.length === checklist!.declarations.length;

  useEffect(() => { if (error) actionError.current?.focus(); }, [error]);
  useEffect(() => { onBusyChange(busy); }, [busy, onBusyChange]);
  useEffect(() => { onRevisionDirtyChange(revisionDirty); }, [revisionDirty, onRevisionDirtyChange]);
  useEffect(() => { onPreparationChange({declarationsReady, declarationsComplete}); }, [declarationsReady, declarationsComplete, onPreparationChange]);
  useEffect(() => { setChecks([]); setError(""); }, [draftId, dirty]);

  const requirementsComplete = submissionRequirements(savedDraft,declarationsComplete).every(item=>item.complete);

  function errorText(reason: unknown, fallback: string) {
    if ((reason as ApiError)?.status === 401) router.replace("/sign-in");
    return reason instanceof Error ? reason.message : fallback;
  }

  async function loadChecklist() {
    setPolicyLoading(true); setPolicyError("");
    try { const policy = await api<{checklist: Checklist | null}>("/author/submission-checklist"); setChecklist(policy.checklist); setChecks([]); }
    catch (reason) { setChecklist(null); setPolicyError(errorText(reason, "Declaration wording could not be loaded.")); }
    finally { setPolicyLoading(false); }
  }

  useEffect(() => { void loadChecklist(); }, []);

  async function loadSelected(id: string, current: number) {
    setDetail(null); setReceipt(null); setDetailLoading(true); setReceiptState("loading"); setDetailError(""); setRevisionDirty(false);
    const [caseResult, receiptResult] = await Promise.allSettled([
      api<Detail>(`/author/submissions/${id}/editorial`),
      api<Receipt>(`/author/submissions/${id}/receipt`),
    ]);
    if (current !== sequence.current) return;
    if (caseResult.status === "fulfilled") {
      setDetail(caseResult.value);
      onManuscriptUpdated({id: caseResult.value.id, reference: caseResult.value.reference, title: caseResult.value.title, status: caseResult.value.status, display_status:caseResult.value.display_status, status_detail:caseResult.value.status_detail, editor_assigned:caseResult.value.editor_assigned});
    } else setDetailError(errorText(caseResult.reason, "The submission could not be loaded. Try again."));
    if (receiptResult.status === "fulfilled") { setReceipt(receiptResult.value); setReceiptState("available"); }
    else if ((receiptResult.reason as ApiError)?.status === 404) setReceiptState("missing");
    else { setReceiptState("error"); errorText(receiptResult.reason, "Receipt unavailable."); }
    setDetailLoading(false);
  }

  useEffect(() => {
    const current = ++sequence.current;
    setError(""); setNotice(""); setRevisionDirty(false); setDetail(null); setReceipt(null); setDetailError("");
    if (selectedId) void loadSelected(selectedId, current);
    else setDetailLoading(false);
    return () => { sequence.current += 1; };
    // The parent controls selection; metadata updates must not refetch or reset a revision form.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, detailVersion]);

  async function retrySelected() {
    if (!selectedId || busy) return;
    if (revisionDirty && !await confirm({title: "Discard unsent revision?", description: "Reloading this manuscript will discard your selected file and response text.", confirmLabel: "Discard changes", danger: true})) return;
    await loadSelected(selectedId, ++sequence.current);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!draftId || !checklist || !savedDraft || dirty || busy || !requirementsComplete) return;
    if (!await confirm({title: "Submit manuscript for editorial review?", description: `${draftReference || draftId}: ${draftTitle || "Selected manuscript"}. You have acknowledged every declaration in checklist ${checklist.title}, version ${checklist.id}. Submission locks this draft for editorial processing.`, confirmLabel: "Confirm submission"})) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await api<{reference: string; submitted_at: string}>(`/author/submissions/${draftId}/submit`, {method: "POST", body: JSON.stringify({checklist_id: checklist.id, acknowledged_indices: checks})});
      onSubmitted({id: draftId, reference: result.reference, title: savedDraft.title, status: "submitted", updated_at: result.submitted_at}, `Submitted ${result.reference} on ${new Date(result.submitted_at).toLocaleString()}. It is now available to the editorial team.`);
      setChecks([]);
    } catch (reason) { setError(errorText(reason, "Submission failed. Your manuscript remains available to review.")); await loadChecklist(); }
    finally { setBusy(false); }
  }

  async function revise(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!detail || !selectedManuscript || busy) return;
    const manuscript = selectedManuscript;
    const data = new FormData(event.currentTarget);
    const upload = data.get("upload");
    if (upload instanceof File && upload.size > 50 * 1024 * 1024) { setError("File exceeds the 50 MB limit."); return; }
    if (!await confirm({title: "Submit revised manuscript?", description: `${detail.reference}: ${detail.title}. The manuscript file and response will be sent to the editorial team after the required scan.`, confirmLabel: "Submit revision"})) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await api<{status: string}>(`/author/submissions/${manuscript.id}/revisions`, {method: "POST", body: data});
      setRevisionDirty(false);
      onManuscriptUpdated({...manuscript, status: result.status});
      setNotice("Revision submitted to the editorial team.");
      await loadSelected(manuscript.id, ++sequence.current);
    } catch (reason) { setError(errorText(reason, "Revision failed. Review your file and try again.")); }
    finally { setBusy(false); }
  }

  return <div className="submission-workflow">
    {showDraft && <section id="submission-declarations" className="draft-editor" aria-labelledby="submission-title" aria-busy={busy || policyLoading}>
      <h2 id="submission-title">Submit for editorial review</h2>
      {error && <p ref={actionError} tabIndex={-1} className="error-message" role="alert">{error}</p>}
      {policyLoading ? <p role="status">Loading approved declarations...</p> : policyError ? <><p className="error-message" role="alert">{policyError}</p><button type="button" className="secondary-button" onClick={() => void loadChecklist()}>Retry declarations</button></> : !checklist ? <p className="draft-warning">No checklist has been approved. The Editor-in-Chief must approve declaration wording before final submission.</p> : <>
        <header className="record-heading"><h3>{checklist.title}</h3><p className="work-meta">Checklist version {checklist.id}</p></header>
        <p>Final submission locks the draft for editorial processing. Saving a draft does not submit it. Readiness checks in the sidebar use your saved draft.</p>
        {!draftId ? <p className="muted-copy">Save and select a draft, then upload your manuscript to submit.</p> : <form onSubmit={submit}>
          <p className="submission-context"><strong>{draftTitle || "Selected manuscript"}</strong>{draftReference && <><br />Paper ID: {draftReference}</>}</p>
          <fieldset className="form-fields declaration-list" disabled={busy || dirty}><legend>Confirm each declaration for this manuscript <span className="required-mark" aria-hidden="true">*</span></legend>{checklist.declarations.map((text,index) => <label className="checkbox-label" key={index}><input type="checkbox" checked={checks.includes(index)} onChange={event => setChecks(previous => event.target.checked ? [...previous,index] : previous.filter(value => value !== index))} /> <span>{text}</span></label>)}</fieldset>
          {dirty ? <p className="draft-warning">Save your changes before confirming declarations.</p> : <p className="muted-copy">{checks.length} of {checklist.declarations.length} declarations confirmed.</p>}
          <div className="work-actions"><button className="button-link" disabled={busy || dirty || !requirementsComplete}>{busy ? "Submitting manuscript..." : "Submit manuscript for editorial review"}</button></div>
        </form>}
      </>}
    </section>}
    {!showDraft && <section className="workspace-surface" aria-label="Selected submitted manuscript" aria-busy={busy || detailLoading}>
      {selectedManuscript && <header className="record-heading"><p className="eyebrow">Paper ID: {selectedManuscript.reference} / {selectedManuscript.display_status ?? selectedManuscript.status.replaceAll("_", " ")}</p><h2>{selectedManuscript.title}</h2></header>}
      {error && <p ref={actionError} tabIndex={-1} className="error-message" role="alert">{error}</p>}{notice && <p className="notice-message" role="status">{notice}</p>}
      {detailLoading && <p role="status" className="notice-message">Loading selected submission and receipt...</p>}
      {detailError && <div><p className="error-message" role="alert">{detailError}</p><button className="secondary-button" type="button" onClick={() => void retrySelected()}>Retry selected submission</button></div>}
      {detail && <div className="submission-detail">
        <section className="work-section"><h3>Editorial correspondence</h3>{detail.decisions.length ? detail.decisions.map(decision => <article key={`${decision.round_number}-${decision.decided_at}`} className="decision-letter"><h4>Round {decision.round_number}: {decision.decision.replaceAll("_", " ")}</h4><p className="work-meta">{new Date(decision.decided_at).toLocaleString()}</p><p className="preserve-lines">{decision.letter}</p></article>) : <p className="muted-copy">No editorial decision letters yet.</p>}</section>
        {detail.status === "revision_requested" && <section className="work-section"><h3>Submit requested revision</h3><p>Upload a PDF or DOCX (up to 50 MB) and respond to the editorial request. Files remain private.</p><form key={detail.id} onChange={() => setRevisionDirty(true)} onSubmit={revise}><fieldset className="form-fields" disabled={busy}><label><span className="field-label">Revision manuscript (PDF or DOCX) <span className="required-mark" aria-hidden="true">*</span><span className="visually-hidden"> (required)</span></span><input type="file" name="upload" accept=".pdf,.docx" required /></label><label><span className="field-label">Response to editor <span className="required-mark" aria-hidden="true">*</span><span className="visually-hidden"> (required)</span></span><textarea name="response_note" maxLength={4000} rows={6} required /></label><div className="work-actions"><button className="button-link" disabled={busy}>{busy ? "Submitting revision..." : "Submit revision"}</button>{revisionDirty && <span className="muted-copy">Unsent revision</span>}</div></fieldset></form></section>}
        <details className="work-section"><summary>Submission receipt and declarations</summary>{receiptState === "available" && receipt ? <><p><strong>Paper ID:</strong> {receipt.reference || detail.reference}</p><p>Submitted {new Date(receipt.submitted_at).toLocaleString()}</p><p className="work-meta">Checklist version {receipt.checklist_id}</p><ol>{receipt.declarations.map((text,index) => <li key={index}>{text}</li>)}</ol></> : receiptState === "missing" ? <p>No stored submission receipt is available for this manuscript. Older records may predate declaration receipts.</p> : <div><p className="error-message" role="alert">The receipt could not be loaded. This does not mean the manuscript has no receipt.</p><button type="button" className="secondary-button" onClick={() => void retrySelected()}>Retry receipt</button></div>}</details>
        <details className="work-section"><summary>Workflow history</summary>{detail.history.length ? <ol className="timeline">{detail.history.map((event,index) => <li key={index}><strong>{event.status.replaceAll("_", " ")}</strong><time dateTime={event.created_at}>{new Date(event.created_at).toLocaleString()}</time></li>)}</ol> : <p>No workflow history is available.</p>}</details>
      </div>}
    </section>}
  </div>;
}
