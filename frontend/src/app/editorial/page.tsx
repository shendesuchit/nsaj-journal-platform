"use client";
import {compareWork,compareCases} from "@/lib/work-priority";

import {DateTimeField} from "@/components/date-time-field";
import {JournalIcon} from "@/components/journal-art";
import Link from "next/link";
import { FormEvent, MouseEvent, useEffect, useRef, useState } from "react";
import { researchAreaLabel } from "@/lib/research-areas";
import { useRouter } from "next/navigation";
import { useConfirm } from "@/components/ui";
import { useUnsavedChanges } from "@/components/use-unsaved-changes";
import { ManuscriptProgress } from "@/components/manuscript-progress";
import { api, type ApiError } from "@/lib/api";
import { editorActionLabel, type WorkflowProgress } from "@/lib/manuscript-progress";

type WorklistItem = {
  id: string; reference: string; title: string; status: string; display_status?:string;
  assigned_editors: { id: string; display_name: string }[];
  is_assigned_to_me: boolean;
  progress: WorkflowProgress;
};
type EligibleEditor = { id: string; display_name: string; email: string; roles: string[] };
type ReviewerOption = { id: string; full_name: string; email: string; affiliation: string; expertise: string[]; languages: string[] };
type AuditItem = { id: string; event_type: string; actor: string; target_type: string | null; target_id: string | null; created_at: string };
type ChecklistSummary = { approved_at: string | null };
type EditorialCase = {
  id: string;
  reference: string;
  title: string;
  abstract: string;
  discipline?: string | null;
  discipline_other?: string | null;
  status: string; display_status?:string;
  progress: WorkflowProgress;
  can_record_decision: boolean;
  decision_options:string[];
  manual_transitions:string[];
  authors: { full_name: string; affiliation: string; email: string | null }[];
  files: { id: string; name: string; scan_status: string; download_url?:string|null }[];
  reviewer_options?: ReviewerOption[];
  reviews: {
    id: string;
    reviewer: string;
    status: string;
    round_number: number;
    due_at: string | null;
    conflict_status: string;
    conflict_details: string | null;
    recommendation: string | null;
    comments_to_editor: string | null;
    comments_to_author: string | null;
  }[];
};



export default function EditorialWorkspacePage() {
  const router = useRouter();
  const confirm = useConfirm();
  const [queue, setQueue] = useState<WorklistItem[]>([]);
  const [eligibleEditors, setEligibleEditors] = useState<EligibleEditor[]>([]);
  const [auditItems, setAuditItems] = useState<AuditItem[]>([]);
  const [isEditorInChief, setIsEditorInChief] = useState(false);
  const [declarationStatus, setDeclarationStatus] = useState<"loading" | "needs-approval" | "approved" | "error">("loading");
  const [selected, setSelected] = useState<EditorialCase | null>(null);
  const [selectedSummary, setSelectedSummary] = useState<WorklistItem | null>(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("active");
  const [myCases, setMyCases] = useState(false);
  const [editorFilter, setEditorFilter] = useState("");
  const [auditStatus, setAuditStatus] = useState<"idle" | "loading" | "loaded" | "error">("idle");
  const [auditError, setAuditError] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [queueError, setQueueError] = useState("");
  const [supportError, setSupportError] = useState("");
  const [busy, setBusy] = useState("");
  const [access, setAccess] = useState<"loading" | "ready" | "denied" | "error">("loading");
  const [detailLoading, setDetailLoading] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [task, setTask] = useState("workflow");
  const [productionCreated, setProductionCreated] = useState(false);
  const [downloading,setDownloading]=useState<string|null>(null);
  const [reviewerChoice, setReviewerChoice] = useState("");
  const detailSequence = useRef(0);
  const queueSequence = useRef(0);
  const selectionRef = useRef<WorklistItem | null>(null);
  const errorSummary = useRef<HTMLParagraphElement>(null);
  useUnsavedChanges(dirty);
  useEffect(() => { if (error) errorSummary.current?.focus(); }, [error]);

  function message(reason: unknown, fallback: string) {
    if ((reason as ApiError)?.status === 401) router.replace("/sign-in");
    return reason instanceof Error ? reason.message : fallback;
  }

  async function loadQueue(initial = false): Promise<WorklistItem[] | null> {
    const sequence = ++queueSequence.current;
    if (initial) setAccess("loading");
    setQueueError("");
    try {
      const me = await api<{ authenticated?: boolean; roles: string[] }>("/auth/me");
      if (sequence !== queueSequence.current) return null;
      if (me.authenticated === false) { router.replace("/sign-in"); return null; }
      if (me.roles.includes("site_admin") || !me.roles.some(role => ["editor_in_chief", "managing_editor", "associate_editor"].includes(role))) {
        setAccess("denied"); setQueueError("An authorized editorial role is required. Site Admin accounts cannot access confidential editorial cases."); return null;
      }
      const data = await api<{items: WorklistItem[]}>("/editorial/worklist");
      if (sequence !== queueSequence.current) return null;
      data.items.sort(compareCases); setQueue(data.items); setAccess("ready");
      setSelectedSummary(current => current ? data.items.find(item => item.id === current.id) ?? current : null);
      const refreshedSelection = data.items.find(item => item.id === selectionRef.current?.id);
      if (refreshedSelection) {
        selectionRef.current = refreshedSelection;
        if (!refreshedSelection.is_assigned_to_me) { detailSequence.current += 1; setSelected(null); setDetailLoading(false); }
      }
      const chief = me.roles.includes("editor_in_chief"); setIsEditorInChief(chief);
      if (chief) {
        setDeclarationStatus("loading");
        const results = await Promise.allSettled([api<{items: EligibleEditor[]}>("/editorial/editors"), api<{items: ChecklistSummary[]}>("/editorial/submission-checklists")]);
        if (sequence !== queueSequence.current) return null;
        const [editors, declarations] = results;
        if (editors.status === "fulfilled") setEligibleEditors(editors.value.items);
        if (declarations.status === "fulfilled") {
          setDeclarationStatus(declarations.value.items.some(version => version.approved_at) ? "approved" : "needs-approval");
        } else {
          setDeclarationStatus("error");
        }
        setSupportError(editors.status === "rejected" ? "Available editors could not be refreshed. Retry before assigning a case." : "");
      }
      return data.items;
    } catch (reason) {
      if (sequence !== queueSequence.current) return null;
      setQueueError(message(reason, "The editorial queue could not be loaded."));
      if (initial) setAccess((reason as ApiError)?.status === 403 ? "denied" : "error");
      return null;
    }
  }

  async function openCase(item: WorklistItem) {
    const sequence = ++detailSequence.current;
    selectionRef.current = item;
    setSelectedSummary(item); setSelected(null); setDetailLoading(item.is_assigned_to_me); setError(""); setNotice(""); setProductionCreated(false); setReviewerChoice(""); setDirty(false);
    if (!item.is_assigned_to_me) return;
    try {
      const data = await api<EditorialCase>(`/editorial/submissions/${item.id}`);
      if (sequence !== detailSequence.current) return;
      setSelected(data); setTask(data.status === "accepted" ? "production" : data.progress.bucket === "reports_available" && data.can_record_decision ? "decision" : "workflow");
    } catch (reason) { if (sequence === detailSequence.current) setError(message(reason, "The case could not be loaded.")); }
    finally { if (sequence === detailSequence.current) setDetailLoading(false); }
  }

  async function selectCase(item: WorklistItem) {
    if (busy || selectedSummary?.id === item.id) return;
    if (dirty && !await confirm({title: "Discard unsaved case changes?", description: "The current form has not been recorded. Switching cases will discard its entries.", confirmLabel: "Discard changes", danger: true})) return;
    await openCase(item);
  }

  async function refreshWorklist() {
    if (busy) return;
    if (dirty && !await confirm({title: "Discard unsaved case changes?", description: "Refreshing the selected case will discard its unsaved form entries.", confirmLabel: "Discard changes", danger: true})) return;
    const target = selectionRef.current;
    const refreshed = await loadQueue();
    if (target && selectionRef.current?.id === target.id && refreshed) {
      const item = refreshed.find(value => value.id === target.id);
      if (item) await openCase(item);
    }
  }

  async function loadAudit() {
    if (auditStatus === "loading") return;
    setAuditStatus("loading"); setAuditError("");
    try { const data = await api<{items: AuditItem[]}>("/editorial/audit"); setAuditItems(data.items); setAuditStatus("loaded"); }
    catch (reason) { setAuditError(message(reason, "Journal activity could not be loaded.")); setAuditStatus("error"); }
  }

  async function changeTask(next: string) {
    if (busy || next === task) return;
    if (dirty && !await confirm({title: "Discard unsaved form changes?", description: "Changing tasks will discard the current unsaved form entries.", confirmLabel: "Discard changes", danger: true})) return;
    setDirty(false); setTask(next); setError(""); setReviewerChoice("");
  }

  useEffect(() => { void loadQueue(true); return () => { detailSequence.current += 1; queueSequence.current += 1; }; }, []);

  async function downloadManuscript(event:MouseEvent<HTMLAnchorElement>,file:EditorialCase["files"][number]) {
    if(event.ctrlKey||event.metaKey||event.shiftKey||event.altKey)return;
    event.preventDefault();if(!file.download_url||downloading)return;
    setDownloading(file.id);setError("");
    try {const response=await fetch(file.download_url,{credentials:"same-origin"});
      if(!response.ok){const payload=await response.json().catch(()=>null);const error=new Error(typeof payload?.detail==="string"?payload.detail:"The manuscript could not be downloaded.") as ApiError;error.status=response.status;throw error;}
      const url=URL.createObjectURL(await response.blob()),anchor=document.createElement("a");anchor.href=url;anchor.download=file.name;document.body.appendChild(anchor);anchor.click();anchor.remove();window.setTimeout(()=>URL.revokeObjectURL(url),1000);
    } catch(reason){setError(message(reason,"The manuscript could not be downloaded. Try again."));}finally{setDownloading(null);}
  }

  async function submitAction(event: FormEvent<HTMLFormElement>, path: string, body: object, success: string, pending: string, review?: {title: string; description: string; confirmLabel: string; danger?: boolean}): Promise<boolean> {
    event.preventDefault(); if (busy) return false;
    const form = event.currentTarget;
    if (review && !await confirm(review)) return false;
    const target = selectedSummary;
    setBusy(pending); setError(""); setNotice("");
    try {
      await api(path, {method: "POST", body: JSON.stringify(body)});
      form.reset(); setDirty(false);
      const refreshed = await loadQueue();
      if (target) await openCase(refreshed?.find(item => item.id === target.id) ?? target);
      setNotice(success);
      return true;
    } catch (reason) { setError(message(reason, "The action could not be completed.")); return false; }
    finally { setBusy(""); }
  }

  async function resolveConflict(reviewId: string, clear: boolean) {
    if (!selected || busy) return;
    if (!await confirm({title: clear ? "Clear this reviewer conflict?" : "Disqualify this reviewer?", description: `${selected.reference}: ${selected.title}. ${clear ? "The reviewer will be able to access the manuscript and submit a report." : "The review assignment will be cancelled."}${dirty ? " Unsaved form entries will be discarded when the case refreshes." : ""}`, confirmLabel: clear ? "Resolve and continue" : "Disqualify reviewer", danger: !clear})) return;
    const target = selectedSummary;
    setBusy("Recording conflict resolution..."); setError("");
    try { await api(`/editorial/reviews/${reviewId}/resolve-conflict?clear=${clear}`, {method: "POST"}); const refreshed = await loadQueue(); if (target) await openCase(refreshed?.find(item => item.id === target.id) ?? target); setNotice("Conflict resolution recorded."); }
    catch (reason) { setError(message(reason, "The conflict resolution could not be recorded.")); }
    finally { setBusy(""); }
  }

  async function saveArticle(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!selected || busy || productionCreated) return;
    const data = new FormData(event.currentTarget);
    setBusy("Creating production record..."); setError(""); setNotice("");
    try {
      await api<{id: string}>(`/editorial/submissions/${selected.id}/article`, {method: "POST", body: JSON.stringify({slug: data.get("slug"), title: data.get("title"), abstract: data.get("abstract"), final_file_id: String(data.get("file_id") ?? ""), license: data.get("license"), doi: data.get("doi") || null})});
      setDirty(false);
      const target = selectedSummary;
      const refreshed = await loadQueue();
      if (target) await openCase(refreshed?.find(item => item.id === target.id) ?? target);
      setProductionCreated(true);
      setNotice("Production article created. It remains private until issue publication.");
    } catch (reason) { setError(message(reason, "The production record could not be created.")); }
    finally { setBusy(""); }
  }

  const editorsInWorklist = Array.from(new Map(queue.flatMap(item => item.assigned_editors).map(editor => [editor.id, editor])).values()).sort((a, b) => a.display_name.localeCompare(b.display_name));
  const matchesFilter = (item: typeof queue[number], filter: string) => {
    const bucket = item.progress.bucket;
    const inFilter = filter === "active" ? bucket !== "closed"
      : filter === "needs_assignment" ? bucket === "needs_assignment"
      : filter === "needs_editor" ? ["needs_editor", "needs_reviewer", "reports_available", "revisions_received"].includes(bucket)
      : filter === "waiting" ? ["waiting_review", "awaiting_author"].includes(bucket)
      : filter === "production" ? bucket === "production" : bucket === "closed";
    return inFilter && (!myCases || item.is_assigned_to_me) && (!editorFilter || item.assigned_editors.some(editor => editor.id === editorFilter)) && `${item.reference} ${item.title}`.toLowerCase().includes(search.toLowerCase().trim());
  };
  const filteredQueue = queue.filter(item => matchesFilter(item, filter));
  const progress = selected?.progress ?? selectedSummary?.progress;

  return <main id="main-content" tabIndex={-1} className="workspace-page">
    <header className="workspace-header"><div><p className="eyebrow">Editorial operations</p><h1>Editorial worklist</h1><p className="muted-copy">See where each manuscript stands, who is handling it and what needs attention next.</p></div>{isEditorInChief && <Link className="secondary-button" href="/editorial/checklist">Manage submission declarations</Link>}</header>
    <p className="draft-warning" role="note">{isEditorInChief ? "Team summaries show the journal's work. Open private manuscript details only for cases assigned to you." : "Your worklist shows cases assigned to your account."} Reviewer recommendations are advisory; decisions require case permission.</p>
    {access === "loading" && <p className="notice-message" role="status">Loading editorial workspace...</p>}
    {access === "denied" && <section className="workspace-surface"><h2>Editorial access required</h2><p className="error-message" role="alert">{queueError}</p></section>}
    {access === "error" && <section className="workspace-surface"><h2>Workspace unavailable</h2><p className="error-message" role="alert">{queueError}</p><button className="secondary-button" type="button" onClick={() => void loadQueue(true)}>Try again</button></section>}
    {access === "ready" && <>
      {queueError && <p className="error-message" role="alert">{queueError}</p>}
      {isEditorInChief && declarationStatus === "needs-approval" && <section className="next-step-callout" aria-labelledby="declaration-action-title">
        <p className="eyebrow">Action required before authors can submit</p>
        <h2 id="declaration-action-title">Approve the declaration wording</h2>
        <p>No approved checklist is active. Authors can save drafts and upload files, but final submission stays unavailable until you approve the exact wording.</p>
        <Link className="secondary-button" href="/editorial/checklist">Review and approve declarations</Link>
      </section>}
      {isEditorInChief && declarationStatus === "error" && <section className="next-step-callout" aria-labelledby="declaration-status-title">
        <p className="eyebrow">Declaration status unavailable</p>
        <h2 id="declaration-status-title">Check the approved wording</h2>
        <p>The dashboard could not confirm whether a checklist is active. Open declaration management to verify its status.</p>
        <Link className="secondary-button" href="/editorial/checklist">Open declaration management</Link>
      </section>}
      <section className="workspace-surface" aria-labelledby="worklist-title">
        <div className="draft-list__heading"><h2 id="worklist-title">Manuscript worklist</h2><button className="secondary-button" type="button" disabled={!!busy} onClick={() => void refreshWorklist()}>Refresh worklist</button></div>
        <div className="worklist-controls">
          <label>Find a manuscript<input type="search" value={search} onChange={event => setSearch(event.currentTarget.value)} placeholder="Paper reference or title" /></label>
          <label>Assigned editor<select value={editorFilter} onChange={event => setEditorFilter(event.currentTarget.value)}><option value="">All editors</option>{editorsInWorklist.map(editor => <option value={editor.id} key={editor.id}>{editor.display_name}</option>)}</select></label>
          <label className="checkbox-label"><input type="checkbox" checked={myCases} onChange={event => setMyCases(event.currentTarget.checked)} /><span>My cases</span></label>
        </div>
        <nav className="work-actions worklist-filters" aria-label="Filter editorial worklist">{[["active", "All active"], ["needs_assignment", "Needs assignment"], ["needs_editor", "Needs editor"], ["waiting", "Waiting on others"], ["production", "Production"], ["closed", "Closed"]].map(([value, label]) => <button className="secondary-button" key={value} type="button" aria-pressed={filter === value} onClick={() => setFilter(value)}>{label} <span className="filter-count">{queue.filter(item => matchesFilter(item,value)).length}</span></button>)}</nav>
        <p className="muted-copy" role="status">{filteredQueue.length} manuscript{filteredQueue.length === 1 ? "" : "s"} in this view</p>
      </section>
      <div className="workspace-grid">
        <aside className="draft-list" aria-label="Editorial manuscript worklist"><div className="draft-list__heading"><h2>{isEditorInChief ? "Team cases" : "My cases"}</h2></div>
          {filteredQueue.length === 0 && <p className="muted-copy">No manuscripts match this view.</p>}
          {filteredQueue.map(item => <button key={item.id} data-status={item.status} className={`draft-item${selectedSummary?.id === item.id ? " draft-item--selected" : ""}`} type="button" disabled={!!busy} aria-current={selectedSummary?.id === item.id ? "true" : undefined} onClick={() => void selectCase(item)}><strong>{item.reference}</strong><span>{item.title || "Untitled submission"}</span><small>{item.display_status ?? item.status.replaceAll("_", " ")}</small><small>{item.assigned_editors.length ? item.assigned_editors.map(editor => editor.display_name).join(", ") : "Unassigned"}</small><small>{editorActionLabel(item.progress.next_action)}</small></button>)}
        </aside>
        <section className="draft-editor" aria-busy={!!busy || detailLoading} aria-label="Selected editorial case">
          {!selectedSummary && <><h2>Select a manuscript</h2><p className="muted-copy">Choose a paper to see its progress and next action. Private manuscript details are available within your assigned cases.</p></>}
          {selectedSummary && <header className="record-heading"><p className="eyebrow">Paper ID: {selectedSummary.reference} / {selected?.display_status ?? selectedSummary.display_status ?? (selected?.status || selectedSummary.status).replaceAll("_", " ")}</p><h2>{selected?.title || selectedSummary.title || "Untitled submission"}</h2></header>}
          {selectedSummary && <ManuscriptProgress displayStatus={selected?.display_status ?? selectedSummary.display_status} reference={selectedSummary.reference} title={selected?.title || selectedSummary.title} status={productionCreated ? "production" : selected?.status || selectedSummary.status} nextAction={progress ? editorActionLabel(progress.next_action) : undefined} roundNumber={progress?.current_round} />}
          {selectedSummary && <section className="work-section worklist-summary"><h3>Case responsibility</h3><p><strong>Assigned editors:</strong> {selectedSummary.assigned_editors.length ? selectedSummary.assigned_editors.map(editor => editor.display_name).join(", ") : "Unassigned"}</p>{progress && <><p><strong>Waiting on:</strong> {(progress.waiting_on ?? "No pending action").replaceAll("_", " ")}</p>{progress.due_at && <p><strong>Next review deadline:</strong> <time dateTime={progress.due_at}>{new Date(progress.due_at).toLocaleString()}</time></p>}</>}{!selectedSummary.is_assigned_to_me && <p className="muted-copy">This is a team summary. Full manuscript details and confidential reports are available to assigned editors.</p>}</section>}
          {detailLoading && <p className="notice-message" role="status">Loading selected manuscript...</p>}
          {error && <p ref={errorSummary} tabIndex={-1} className="error-message" role="alert">{error}</p>}{notice && <p className="notice-message" role="status">{notice}</p>}
          {selectedSummary?.is_assigned_to_me && !selected && !detailLoading && <button type="button" className="secondary-button" onClick={() => void openCase(selectedSummary)}>Retry selected case</button>}
          {isEditorInChief && selectedSummary && <section className="work-section"><h3>Assign editor / update decision permission</h3><p className="muted-copy">Choose the editor who will handle this case. Decision authority is granted explicitly for this manuscript.</p>{supportError ? <div><p className="error-message" role="alert">{supportError}</p><button className="secondary-button" type="button" disabled={!!busy} onClick={() => void loadQueue()}>Retry available editors</button></div> : <form key={selectedSummary.id} onChange={() => setDirty(true)} onSubmit={event => { const data = new FormData(event.currentTarget); void submitAction(event, `/editorial/submissions/${selectedSummary.id}/editors`, {editor_id: data.get("editor_id"), can_make_decisions: data.get("can_make_decisions") === "on"}, `Case ${selectedSummary.reference} assigned.`, "Assigning case..."); }}><fieldset className="form-fields" disabled={!!busy}><label><span className="field-label">Assign {selectedSummary.reference} to <span className="required-mark" aria-hidden="true">*</span><span className="visually-hidden"> (required)</span></span><select name="editor_id" required defaultValue=""><option value="" disabled>Select an editor</option>{eligibleEditors.map(editor => <option key={editor.id} value={editor.id}>{editor.display_name} / {editor.roles.join(", ")}</option>)}</select></label><label className="checkbox-label"><input type="checkbox" name="can_make_decisions" /><span>May record decisions for this case</span></label><div className="work-actions"><button className="button-link" disabled={!!busy}>{busy || "Assign case"}</button></div></fieldset></form>}</section>}
          {selected && <div key={selected.id}>
            {selected.progress.bucket === "reports_available" && <div className="decision-ready"><h3>Reviews received · Editorial decision required</h3><p>{selected.can_record_decision ? "Review the reports and use Editor decision to send the author an acceptance, revision request or decline letter." : "The editor-in-chief must assign a decision editor or grant you decision permission for this case."}</p></div>}<p className="notice-message">Decision authority for this case: {selected.can_record_decision ? "You may record editorial decisions." : "You may coordinate the case; decision authority has not been granted."}</p>
            <section className="work-section review-progress" aria-label="Current review round"><h3>Review round {selected.progress.current_round}</h3><p>{selected.progress.review_counts.completed} submitted reports / {selected.progress.review_counts.accepted} active reviews / {selected.progress.review_counts.invited} pending invitations</p>{selected.progress.review_counts.conflict_reported > 0 && <p className="draft-warning">{selected.progress.review_counts.conflict_reported} conflict{selected.progress.review_counts.conflict_reported === 1 ? " needs" : "s need"} editor attention.</p>}{selected.progress.review_counts.overdue > 0 && <p className="draft-warning">{selected.progress.review_counts.overdue} review deadline{selected.progress.review_counts.overdue === 1 ? " is" : "s are"} overdue.</p>}<p className="muted-copy">These counts describe the current round. Reports are advisory and do not establish a minimum reviewer requirement.</p></section>
            <details className="work-section"><summary>Manuscript details and files</summary>{selected.discipline && <p><strong>Area of research:</strong> {researchAreaLabel(selected.discipline, selected.discipline_other)}</p>}<h3>Abstract</h3><p className="preserve-lines">{selected.abstract}</p><h3>Authors</h3><ol>{selected.authors.map((author,index) => <li key={index}>{author.full_name}{author.affiliation ? ` / ${author.affiliation}` : ""}</li>)}</ol><h3>Private manuscript files</h3>{selected.files.length ? <ul className="editorial-file-list">{selected.files.map(file=><li key={file.id}><span className="editorial-file-icon"><JournalIcon name="file" size={21}/></span><div>{file.scan_status==="clean"&&file.download_url?<a className="manuscript-download" href={file.download_url} download={file.name} aria-label={`Download ${file.name}`} aria-disabled={!!downloading} onClick={event=>void downloadManuscript(event,file)}>{file.name}<JournalIcon name="download" size={16}/></a>:<strong>{file.name}</strong>}<p className="small-copy" role={downloading===file.id?"status":undefined}>{downloading===file.id?"Downloading…":file.scan_status==="clean"&&file.download_url?"Private manuscript · Ready to download":`Download unavailable · Scan: ${file.scan_status.replaceAll("_"," ")}`}</p></div></li>)}</ul> : <p>No manuscript files are available.</p>}</details>
            <section className="work-section"><h3>Case actions</h3><nav className="work-actions" aria-label="Editorial case tasks">
              <button className="secondary-button" type="button" aria-pressed={task === "workflow"} disabled={!!busy} onClick={() => void changeTask("workflow")}>Workflow</button>
              {["editorial_screening", "reviewer_invitation", "under_review"].includes(selected.status) && <button className="secondary-button" type="button" aria-pressed={task === "reviewer"} disabled={!!busy} onClick={() => void changeTask("reviewer")}>Assign reviewer</button>}
              {selected.decision_options.length > 0 && selected.can_record_decision && <button className="secondary-button" type="button" aria-pressed={task === "decision"} disabled={!!busy} onClick={() => void changeTask("decision")}>Editor decision</button>}
              {selected.status === "accepted" && <button className="secondary-button" type="button" aria-pressed={task === "production"} disabled={!!busy} onClick={() => void changeTask("production")}>Production record</button>}
            </nav>
            <div key={`${selected.id}-${task}`}>
              {task === "workflow" && <><h4>Workflow</h4>{(selected.manual_transitions ?? []).length ? <form onChange={() => setDirty(true)} onSubmit={event => { const data = new FormData(event.currentTarget); const state = String(data.get("to_status")); void submitAction(event, `/editorial/submissions/${selected.id}/transition`, {to_status: state, reason: data.get("reason")}, "Workflow status updated.", "Recording transition...", ["withdrawn", "revision_requested"].includes(state) ? {title: "Record manuscript transition?", description: `${selected.reference}: ${selected.title}. The case will move to ${state.replaceAll("_", " ")}. Reason: ${data.get("reason")}`, confirmLabel: "Record transition", danger: state === "withdrawn"} : undefined); }}><fieldset className="form-fields" disabled={!!busy}><label><span className="field-label">Next state <span className="required-mark" aria-hidden="true">*</span><span className="visually-hidden"> (required)</span></span><select name="to_status" required>{(selected.manual_transitions ?? []).map(state => <option key={state} value={state}>{state.replaceAll("_", " ")}</option>)}</select></label><label><span className="field-label">Reason <span className="required-mark" aria-hidden="true">*</span><span className="visually-hidden"> (required)</span></span><textarea name="reason" required minLength={3} rows={3} /></label><div className="work-actions"><button className="button-link" disabled={!!busy}>{busy || "Record transition"}</button></div></fieldset></form> : <p className="muted-copy">No manual workflow transition is available from this state.</p>}</>}
              {task === "reviewer" && <><h4>Assign a reviewer</h4><p className="muted-copy">Choose an existing reviewer account, or invite a new reviewer. The deadline uses your device's local time and is sent as an absolute instant.</p><form onChange={() => setDirty(true)} onSubmit={event => { const data = new FormData(event.currentTarget); const choice = String(data.get("reviewer_choice") ?? ""); const existing = selected.reviewer_options?.find(reviewer => reviewer.id === choice); const body = {email: existing?.email ?? data.get("email"), full_name: existing?.full_name ?? data.get("full_name"), affiliation: existing?.affiliation ?? data.get("affiliation") ?? "", expertise: existing?.expertise ?? [], languages: existing?.languages ?? [], due_at: new Date(String(data.get("due_at"))).toISOString(), round_number: selected.progress.current_round}; void submitAction(event, `/editorial/submissions/${selected.id}/reviewers`, body, existing ? "Existing reviewer assigned to this case." : "Reviewer invitation queued for delivery.", existing ? "Assigning reviewer..." : "Inviting reviewer...").then(saved => { if (saved) setReviewerChoice(""); }); }}><fieldset className="form-fields" disabled={!!busy}><label><span className="field-label">Reviewer <span className="required-mark" aria-hidden="true">*</span><span className="visually-hidden"> (required)</span></span><select name="reviewer_choice" value={reviewerChoice} required onChange={event => setReviewerChoice(event.currentTarget.value)}><option value="">Select a reviewer</option>{(selected.reviewer_options ?? []).map(reviewer => <option key={reviewer.id} value={reviewer.id}>{reviewer.full_name}{reviewer.affiliation ? ` / ${reviewer.affiliation}` : ""} / {reviewer.email}</option>)}<option value="new">Invite a new reviewer...</option></select></label>{(selected.reviewer_options ?? []).length === 0 && <p className="form-help">No active reviewer accounts are available for this case yet.</p>}{reviewerChoice === "new" && <><label><span className="field-label">Reviewer email <span className="required-mark" aria-hidden="true">*</span><span className="visually-hidden"> (required)</span></span><input type="email" name="email" required /></label><label><span className="field-label">Reviewer name <span className="required-mark" aria-hidden="true">*</span><span className="visually-hidden"> (required)</span></span><input name="full_name" required /></label><label>Affiliation (optional)<input name="affiliation" /></label></>}<DateTimeField label="Review deadline" name="due_at" required /><div className="work-actions"><button className="button-link" disabled={!!busy || !reviewerChoice}>{busy || (reviewerChoice === "new" ? "Invite and assign reviewer" : "Assign selected reviewer")}</button></div></fieldset></form></>}
              {task === "decision" && selected.decision_options.length > 0 && selected.can_record_decision && <><h4>Editor decision</h4><p>Record your accountable decision separately from reviewer recommendations. The letter is author-visible; the internal reason remains private.</p><form onChange={() => setDirty(true)} onSubmit={event => { const data = new FormData(event.currentTarget); void submitAction(event, `/editorial/submissions/${selected.id}/decision`, {decision: data.get("decision"), author_letter: data.get("author_letter"), internal_reason: data.get("internal_reason"), round_number: selected.progress.current_round, close_open_reviews: data.get("close_open_reviews")==="on", review_closure_reason: data.get("review_closure_reason")}, "Editorial decision recorded and attributed to your account.", "Recording decision...", {title: "Record editorial decision?", description: `${selected.reference}: ${selected.title}. Decision: ${String(data.get("decision")).replaceAll("_", " ")}. The letter will become visible to the author. Review your wording before recording it.`, confirmLabel: "Confirm decision", danger: data.get("decision") === "declined"}); }}><fieldset className="form-fields" disabled={!!busy}><label>Decision<select name="decision">{selected.decision_options.map(option=><option key={option} value={option}>{option.replaceAll("_"," ")}</option>)}</select></label><label><span className="field-label">Letter to author <span className="required-mark" aria-hidden="true">*</span><span className="visually-hidden"> (required)</span></span><textarea name="author_letter" required rows={7} /></label><label className="checkbox-label"><input type="checkbox" name="close_open_reviews"/><span>Close outstanding review assignments with this decision</span></label><label>Reason for closing outstanding reviews<textarea name="review_closure_reason" rows={2}/></label><label>Internal reason (optional)<textarea name="internal_reason" rows={4} /></label><div className="work-actions"><button className="button-link" disabled={!!busy}>{busy || "Record decision"}</button></div></fieldset></form></>}
              {task === "production" && <><h4>Production record</h4><p>This creates a private article record. Issue preparation and explicit publication remain separate steps.</p><form onChange={() => setDirty(true)} onSubmit={saveArticle}><fieldset className="form-fields" disabled={!!busy || productionCreated}><label><span className="field-label">Stable article URL slug <span className="required-mark" aria-hidden="true">*</span><span className="visually-hidden"> (required)</span></span><input name="slug" required defaultValue={selected.reference.toLowerCase().replaceAll(/[^a-z0-9]+/g, "-")} /></label><label><span className="field-label">Published title <span className="required-mark" aria-hidden="true">*</span><span className="visually-hidden"> (required)</span></span><input name="title" required defaultValue={selected.title} /></label><label><span className="field-label">Abstract <span className="required-mark" aria-hidden="true">*</span><span className="visually-hidden"> (required)</span></span><textarea name="abstract" rows={7} required defaultValue={selected.abstract} /></label><label><span className="field-label">Final clean file <span className="required-mark" aria-hidden="true">*</span><span className="visually-hidden"> (required)</span></span><select name="file_id" required defaultValue=""><option value="" disabled>Select a clean file</option>{selected.files.filter(file => file.scan_status === "clean").map(file => <option key={file.id} value={file.id}>{file.name}</option>)}</select></label><label><span className="field-label">Approved license text <span className="required-mark" aria-hidden="true">*</span><span className="visually-hidden"> (required)</span></span><input name="license" required /></label><label>DOI, only if registered (optional)<input name="doi" /></label><div className="work-actions"><button className="button-link" disabled={!!busy || productionCreated}>{busy || (productionCreated ? "Production record created" : "Create production record")}</button></div></fieldset></form></>}
              {dirty && <p className="muted-copy">Unsaved form changes</p>}
            </div>
            {(productionCreated || ["production", "scheduled"].includes(selected.status)) && <p className="notice-message">Production record for {selected.reference} is ready for issue preparation. <Link href={`/admin/publication?submissionReference=${encodeURIComponent(selected.reference)}`}>Continue issue preparation</Link></p>}
            </section>
            <section className="work-section"><h3>Review reports</h3><p className="muted-copy">Recommendations are advisory. Review comments and conflict information are confidential.</p>{selected.reviews.length === 0 ? <p className="muted-copy">No reviewer responses have been recorded.</p> : [...selected.reviews].sort(compareWork).map(review => <article data-status={review.status} className="review-card" key={review.id}><h4>{review.reviewer}</h4><p className="work-meta">Round {review.round_number} / {review.status.replaceAll("_", " ")} / {review.due_at ? `Due ${new Date(review.due_at).toLocaleString()}` : "No deadline"}</p>
              {review.conflict_status === "reported" && <div className="draft-warning"><p>Potential conflict: {review.conflict_details}</p><div className="work-actions"><button className="secondary-button" type="button" disabled={!!busy} onClick={() => void resolveConflict(review.id, true)}>Resolve and continue</button><button className="danger-button" type="button" disabled={!!busy} onClick={() => void resolveConflict(review.id, false)}>Disqualify reviewer</button></div></div>}
              {review.recommendation && <><p>Recommendation: <strong>{review.recommendation.replaceAll("_", " ")}</strong></p><h5>Confidential comments to editor</h5><p className="preserve-lines">{review.comments_to_editor}</p><h5>Comments to author</h5><p className="preserve-lines">{review.comments_to_author}</p></>}
            </article>)}</section>
          </div>}
        </section>
      </div>
      {isEditorInChief && <details className="workspace-surface audit-panel" onToggle={event => { if (event.currentTarget.open && auditStatus === "idle") void loadAudit(); }}><summary>Recent journal activity</summary><p className="muted-copy">Latest 100 editorial, review, publication, and public-content events. Sensitive event details are not shown here.</p>{auditStatus === "loading" ? <p role="status">Loading journal activity...</p> : auditStatus === "error" ? <div><p className="error-message" role="alert">{auditError}</p><button className="secondary-button" type="button" onClick={() => void loadAudit()}>Retry journal activity</button></div> : auditStatus === "loaded" && (auditItems.length === 0 ? <p className="muted-copy">No journal activity has been recorded.</p> : <ol className="audit-list">{auditItems.map(event => <li key={event.id}><strong>{event.event_type.replaceAll(".", " ")}</strong><span>{event.actor} / {event.target_type ?? "record"}{event.target_id ? ` ${event.target_id}` : ""}</span><time dateTime={event.created_at}>{new Date(event.created_at).toLocaleString()}</time></li>)}</ol>)}</details>}
    </>}
  </main>;
}
