"use client";

import {SubmissionReadiness} from "@/components/submission-readiness";
import {JournalIcon} from "@/components/journal-art";
import { researchAreas } from "@/lib/research-areas";
import Link from "next/link";
import { ChangeEvent, FormEvent, useCallback, useEffect, useRef, useState } from "react";

import {compareWork} from "@/lib/work-priority";
import { useRouter } from "next/navigation";

import { useConfirm } from "@/components/ui";
import { useUnsavedChanges } from "@/components/use-unsaved-changes";
import { SubmissionIntake, type SubmittedManuscript, type SubmissionPreparation } from "@/components/submission-intake";
import { ManuscriptProgress } from "@/components/manuscript-progress";
import { api, type ApiError } from "@/lib/api";

type Author = { full_name: string; affiliation: string; email: string | null };
type DraftFile = {
  id: string;
  original_name: string;
  size_bytes: number;
  scan_status: string;
};
type Draft = {
  id: string;
  reference: string;
  status: "draft";
  title: string;
  abstract: string;
  keywords: string[];
  manuscript_type: string | null;
  discipline: string | null;
  discipline_other: string | null;
  authors: Author[];
  files: DraftFile[];
  updated_at: string | null;
};
type DraftForm = Omit<Draft, "id" | "reference" | "status" | "files" | "updated_at">;
type Selection = {kind: "draft"; id: string | null} | {kind: "submitted"; id: string};

const emptyForm: DraftForm = {
  title: "",
  abstract: "",
  keywords: [],
  manuscript_type: null,
  discipline: null,
  discipline_other: null,
  authors: [{ full_name: "", affiliation: "", email: "" }],
};

const authorRoleError = "An Author role is required.";
const authorAccessMessage =
  "Your account does not have the Author role. Ask a Site Admin to assign it before using the author workspace.";

const manuscriptTypes = [
  "original research",
  "review article",
  "case study",
  "technical paper",
];

const authorNextActions: Record<string, string> = {
  submitted: "Your paper is with the editorial team. No author action is required yet.",
  technical_check: "The editorial team is checking your submission. Watch for correspondence here.",
  editorial_screening: "Your paper is being assessed by the editorial team. Watch for correspondence here.",
  reviewer_invitation: "The editorial team is arranging peer review. No author action is required yet.",
  under_review: "Your paper is in peer review. Wait for an editorial decision or a request for information.",
  revision_requested: "Read the editorial letter, then upload your revised manuscript and response below.",
  resubmitted: "Your revision has been sent to the editorial team for further assessment.",
  accepted: "Your paper has been accepted. The editorial team will prepare it for publication.",
  production: "Your accepted paper is being prepared for publication.",
  scheduled: "Your paper is scheduled in an issue and remains private until publication.",
  published: "Your paper has been published. Its editorial correspondence remains available below.",
  declined: "Read the editorial decision letter below.",
  withdrawn: "This submission has been withdrawn. Its correspondence remains available below.",
};

function RequiredMark() {
  return <span className="required-mark" aria-hidden="true">*</span>;
}

export default function AuthorWorkspacePage() {
  const router = useRouter();
  const confirm = useConfirm();
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [submitted, setSubmitted] = useState<SubmittedManuscript[]>([]);
  const [selection, setSelection] = useState<Selection>({kind: "draft", id: null});
  const selected = selection.kind === "draft" ? drafts.find(draft => draft.id === selection.id) ?? null : null;
  const selectedManuscript = selection.kind === "submitted" ? submitted.find(item => item.id === selection.id) ?? null : null;
  const [form, setForm] = useState<DraftForm>(emptyForm);
  const [keywordsText, setKeywordsText] = useState("");
  const [userName, setUserName] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [submissionBusy, setSubmissionBusy] = useState(false);
  const [revisionDirty, setRevisionDirty] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState("");
  const [detailVersion, setDetailVersion] = useState(0);
  const [preparation, setPreparation] = useState<SubmissionPreparation>({declarationsReady: false, declarationsComplete: false});
  const [busyAction, setBusyAction] = useState("");
  const [savedForm, setSavedForm] = useState(JSON.stringify(emptyForm));
  const errorSummary = useRef<HTMLParagraphElement>(null);
  const currentForm = {...form, keywords: keywordsText.split(",").map(word => word.trim()).filter(Boolean)};
  const dirty = JSON.stringify(currentForm) !== savedForm;
  const working = busy || submissionBusy || refreshing;
  const detailsComplete = !!selected && !dirty && !!selected.title.trim() && !!selected.abstract.trim()
    && !!selected.discipline && (selected.discipline !== "other" || !!selected.discipline_other?.trim()) && !!selected.manuscript_type && selected.keywords.length > 0 && selected.authors.length > 0
    && selected.authors.every(author => author.full_name.trim() && author.affiliation.trim());
  const filesComplete = !!selected && selected.files.length > 0 && selected.files.every(file => file.scan_status === "clean");
  const preparationSteps = [
    {title: "Details", complete: detailsComplete},
    {title: "File", complete: filesComplete},
    {title: "Declarations", complete: preparation.declarationsComplete && !dirty},
    {title: "Submit", complete: false},
  ];
  const currentPreparation = preparationSteps.findIndex(step => !step.complete);
  const nextStep: {title: string; detail: string; href?: string; linkLabel?: string} = !selected
    ? {
        title: "Step 1: Complete the details and save your draft.",
        detail: "After it is saved, upload the manuscript file, then confirm the declarations before submitting.",
        href: "#manuscript-details",
        linkLabel: "Go to manuscript details",
      }
    : busy && busyAction === "save"
      ? {
          title: "Saving your draft…",
          detail: "The next step will appear here when the save is complete.",
        }
      : dirty
        ? {
            title: "Next: Save your draft changes.",
            detail: "Submission checks use the last saved version of your details.",
          }
        : busy && busyAction === "upload"
          ? {
              title: "Your file is uploading and being scanned.",
              detail: "Wait for the scan result before moving on to declarations.",
            }
          : selected.files.length === 0
            ? {
                title: "Next: Upload the manuscript file.",
                detail: "Choose a PDF or DOCX, then wait for it to show a clean scan.",
                href: "#files-title",
                linkLabel: "Go to manuscript files",
              }
            : selected.files.some(file => file.scan_status !== "clean")
              ? {
                  title: "Next: Resolve the manuscript file scan.",
                  detail: "Every uploaded file must show a clean scan before submission.",
                  href: "#files-title",
                  linkLabel: "Review manuscript files",
                }
              : {
                  title: "Next: Confirm the declarations and submit.",
                  detail: "Review the approved declaration wording below and confirm each statement. If no approved checklist appears, the Editor-in-Chief must approve it first.",
                  href: "#submission-declarations",
                  linkLabel: "Go to declarations and submit",
                };
  useUnsavedChanges(selection.kind === "draft" ? dirty : revisionDirty);
  useEffect(() => { if (error) errorSummary.current?.focus(); }, [error]);
  const [accessState, setAccessState] = useState<"loading" | "ready" | "denied" | "error">("loading");

  function isAuthorRoleError(reason: unknown): reason is ApiError {
    return reason instanceof Error
      && (reason as ApiError).status === 403
      && reason.message === authorRoleError;
  }

  function reportActionError(reason: unknown, fallback: string) {
    if (reason instanceof Error && (reason as ApiError).status === 401) {
      router.replace("/sign-in");
      return;
    }
    if (isAuthorRoleError(reason)) {
      setAccessState("denied");
      setError(authorAccessMessage);
      return;
    }
    setError(reason instanceof Error ? reason.message : fallback);
  }

  function displayDraft(draft: Draft | null, name = userName) {
    const displayed: DraftForm = draft ? {
      title: draft.title,
      abstract: draft.abstract,
      keywords: draft.keywords,
      manuscript_type: draft.manuscript_type,
      discipline: draft.discipline,
      discipline_other: draft.discipline_other,
      authors: draft.authors.length ? draft.authors : [{full_name: "", affiliation: "", email: ""}],
    } : {...emptyForm, authors: [{full_name: name, affiliation: "", email: ""}]};
    setForm(displayed); setSavedForm(JSON.stringify(displayed)); setKeywordsText(displayed.keywords.join(", "));
  }

  function applySelection(next: Selection, availableDrafts = drafts) {
    setSelection(next); setRevisionDirty(false); setNotice(""); setError("");
    displayDraft(next.kind === "draft" ? availableDrafts.find(draft => draft.id === next.id) ?? null : null);
  }

  async function confirmSelectionChange() {
    if (working) return false;
    if (selection.kind === "draft" && dirty) return confirm({title: "Discard unsaved draft changes?", description: "Your latest edits have not been saved. Changing manuscripts or refreshing will discard them.", confirmLabel: "Discard changes", danger: true});
    if (selection.kind === "submitted" && revisionDirty) return confirm({title: "Discard unsent revision?", description: "Changing manuscripts or refreshing will discard your selected file and response text.", confirmLabel: "Discard changes", danger: true});
    return true;
  }

  async function loadWorkspace(initial = true) {
    if (!initial && !await confirmSelectionChange()) return;
    if (initial) setAccessState("loading");
    else setRefreshing(true);
    setError(""); setRefreshError("");
    try {
      const user = await api<{ display_name: string; roles: string[]; authenticated: boolean }>("/auth/me");
      if (!user.authenticated) {
        router.replace("/sign-in");
        return;
      }
      if (!user.roles.includes("author")) {
        setAccessState("denied");
        setError(authorAccessMessage);
        return;
      }
      setUserName(user.display_name);
      const [draftResponse, submittedResponse] = await Promise.all([
        api<{ items: Draft[] }>("/author/submissions"),
        api<{ items: SubmittedManuscript[] }>("/author/workspace"),
      ]);
      setDrafts(draftResponse.items); setSubmitted(submittedResponse.items);
      const retainSelection = !initial && (selection.kind === "submitted"
        ? submittedResponse.items.some(item => item.id === selection.id)
        : selection.id === null || draftResponse.items.some(item => item.id === selection.id));
      const requestedDraft = initial ? draftResponse.items.find(item => item.id === new URLSearchParams(window.location.search).get("draft")) : null;
      const next: Selection = requestedDraft ? {kind: "draft", id: requestedDraft.id} : retainSelection ? selection : submittedResponse.items.length
        ? {kind: "submitted", id: submittedResponse.items[0].id}
        : {kind: "draft", id: draftResponse.items[0]?.id ?? null};
      setSelection(next); setRevisionDirty(false); setNotice("");
      displayDraft(next.kind === "draft" ? draftResponse.items.find(draft => draft.id === next.id) ?? null : null, user.display_name);
      setDetailVersion(version => version + 1);
      setAccessState("ready");
    } catch (reason) {
      if (isAuthorRoleError(reason)) {
        setAccessState("denied");
        setError(authorAccessMessage);
      } else if (reason instanceof Error && (reason as ApiError).status === 401) {
        router.replace("/sign-in");
      } else {
        const message = reason instanceof Error ? reason.message : "The author workspace could not be loaded.";
        if (initial) { setAccessState("error"); setError(message); }
        else setRefreshError(message);
      }
    } finally { setRefreshing(false); }
  }

  useEffect(() => {
    void loadWorkspace();
    // loadWorkspace is stable for the page lifetime.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function selectDraft(draft: Draft) {
    if (selection.kind === "draft" && selection.id === draft.id) return;
    if (!await confirmSelectionChange()) return;
    applySelection({kind: "draft", id: draft.id});
  }

  async function newDraft() {
    if (!await confirmSelectionChange()) return;
    applySelection({kind: "draft", id: null});
  }

  async function selectSubmitted(item: SubmittedManuscript) {
    if (selection.kind === "submitted" && selection.id === item.id) return;
    if (!await confirmSelectionChange()) return;
    applySelection({kind: "submitted", id: item.id});
  }

  const updateManuscript = useCallback((item: SubmittedManuscript) => {
    setSubmitted(previous => previous.map(current => current.id === item.id ? {...current, ...item} : current));
  }, []);

  function manuscriptSubmitted(item: SubmittedManuscript, message: string) {
    setDrafts(previous => previous.filter(draft => draft.id !== item.id));
    setSubmitted(previous => [item, ...previous.filter(current => current.id !== item.id)]);
    applySelection({kind: "submitted", id: item.id});
    setNotice(message);
  }

  function updateAuthor(index: number, key: keyof Author, value: string) {
    setForm((previous) => ({
      ...previous,
      authors: previous.authors.map((author, row) =>
        row === index ? { ...author, [key]: value } : author,
      ),
    }));
  }

  async function saveDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusyAction("save");
    setBusy(true);
    setError("");
    setNotice("");
    const payload = {
      ...form,
      keywords: keywordsText.split(",").map((word) => word.trim()).filter(Boolean),
    };
    try {
      const saved = selected
        ? await api<Draft>(`/author/submissions/${selected.id}`, { method: "PATCH", body: JSON.stringify(payload) })
        : await api<Draft>("/author/submissions", { method: "POST", body: JSON.stringify(payload) });
      setSelection({kind: "draft", id: saved.id});
      const savedValues = {title: saved.title, abstract: saved.abstract, keywords: saved.keywords, manuscript_type: saved.manuscript_type, discipline: saved.discipline, discipline_other: saved.discipline_other, authors: saved.authors};
      setForm(savedValues); setKeywordsText(saved.keywords.join(", ")); setSavedForm(JSON.stringify(savedValues));
      setDrafts((previous) => [saved, ...previous.filter((draft) => draft.id !== saved.id)]);
      setNotice("Draft saved. It has not been submitted for editorial review.");
    } catch (reason) {
      reportActionError(reason, "Draft could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  async function uploadFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file || !selected) return;
    if (file.size > 50 * 1024 * 1024) {
      setError("File exceeds the 50 MB limit.");
      event.target.value = "";
      return;
    }
    setBusyAction("upload");
    setBusy(true);
    setError("");
    setNotice("");
    const data = new FormData();
    data.append("upload", file);
    try {
      const result = await api<DraftFile & { download_available: boolean }>(
        `/author/submissions/${selected.id}/files`,
        { method: "POST", body: data },
      );
      const updated = { ...selected, files: [...selected.files, result] };
      setDrafts((previous) => previous.map((draft) => draft.id === updated.id ? updated : draft));
      setNotice(result.download_available
        ? "File uploaded and passed malware scanning."
        : "File is stored privately but unavailable because scanning did not complete successfully.");
    } catch (reason) {
      reportActionError(reason, "File could not be uploaded.");
    } finally {
      event.target.value = "";
      setBusy(false);
    }
  }

  async function downloadFile(file: DraftFile) {
    if (!selected || file.scan_status !== "clean") return;
    try {
      const response = await fetch(`/api/v1/author/submissions/${selected.id}/files/${file.id}`, {
        credentials: "same-origin",
      });
      if (!response.ok) {
        if (response.status === 401) {
          router.replace("/sign-in");
          return;
        }
        const payload = await response.json().catch(() => null) as { detail?: string } | null;
        if (response.status === 403 && payload?.detail === authorRoleError) {
          setAccessState("denied");
          setError(authorAccessMessage);
          return;
        }
        throw new Error(payload?.detail ?? "This file is unavailable.");
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = file.original_name;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (reason) {
      reportActionError(reason, "Download failed.");
    }
  }

  return (
    <main id="main-content" tabIndex={-1} className="workspace-page">
      <header className="workspace-header">
        <div><p className="eyebrow">Author workspace</p><h1>My manuscripts</h1></div>
        {accessState === "ready" && <button className="secondary-button" type="button" disabled={working} onClick={() => void loadWorkspace(false)}>{refreshing ? "Refreshing manuscripts..." : "Refresh manuscripts"}</button>}
      </header>
      {accessState === "loading" && <p className="notice-message" role="status">Loading your author workspace...</p>}
      {accessState === "denied" && <section className="content-panel" aria-labelledby="author-access-title">
        <h2 id="author-access-title">Author access required</h2>
        <p className="error-message" role="alert">{error || authorAccessMessage}</p>
        <p>If you believe this is incorrect, contact a Site Admin to check your assigned roles.</p>
        <Link href="/">Return to the journal home</Link>
      </section>}
      {accessState === "error" && <section className="content-panel" aria-labelledby="author-load-error-title">
        <h2 id="author-load-error-title">Workspace unavailable</h2>
        <p className="error-message" role="alert">{error}</p>
        <button className="secondary-button" type="button" onClick={() => void loadWorkspace()}>Try again</button>
      </section>}
      {accessState === "ready" && <>
      {notice && <p className="notice-message" role="status">{notice}</p>}
      {refreshError && <p className="error-message" role="alert">{refreshError}</p>}
      <p className="draft-warning" role="note">
        Drafts stay private and are not sent for editorial review until you submit them.
      </p>
      <div className="workspace-grid author-workspace-grid">
        <aside className="draft-list manuscript-sidebar author-library" aria-label="My manuscripts">
          <section className="manuscript-group manuscript-group--drafts" aria-labelledby="draft-list-title"><div className="draft-list__heading"><h2 id="draft-list-title"><JournalIcon name="file" size={15}/> Your drafts <span className="manuscript-count">{drafts.length}</span></h2></div><button className="new-draft-button" type="button" disabled={working} onClick={() => void newDraft()}><JournalIcon name="plus" size={15}/> New draft</button>
          {drafts.length === 0 && <p className="muted-copy">No drafts yet.</p>}
          <div className="manuscript-card-list">{drafts.map((draft) => (
            <button className={`manuscript-card manuscript-card--draft draft-item${selected?.id === draft.id ? " draft-item--selected" : ""}`} type="button" key={draft.id} aria-current={selected?.id === draft.id ? "true" : undefined} disabled={working} onClick={() => void selectDraft(draft)}>
              <span className="manuscript-card__meta"><span className="manuscript-card__reference">{draft.reference}</span><span className="manuscript-card__tag">Draft</span></span><strong>{draft.title || "Untitled draft"}</strong>
            </button>
          ))}</div>
          </section>
          <section className="manuscript-group manuscript-group--submitted" id="submitted-manuscripts" aria-labelledby="submitted-title"><div className="draft-list__heading"><h2 id="submitted-title"><JournalIcon name="book" size={15}/> Submitted manuscripts <span className="manuscript-count">{submitted.length}</span></h2></div>
            <div className="manuscript-card-list">{submitted.length === 0 ? <p className="muted-copy">No manuscripts submitted yet. Submitted work and editorial correspondence will appear here.</p> : [...submitted].sort(compareWork).map(item => <button key={item.id} type="button" data-status={item.status} className={`manuscript-card draft-item${selectedManuscript?.id === item.id ? " draft-item--selected" : ""}`} disabled={working} aria-current={selectedManuscript?.id === item.id ? "true" : undefined} onClick={() => void selectSubmitted(item)}><span className="manuscript-card__reference">{item.reference}</span><strong>{item.title}</strong><span className="manuscript-status">{item.display_status ?? item.status.replaceAll("_", " ")}</span></button>)}</div>
          </section>
          {selection.kind === "draft" && <SubmissionReadiness draft={selected} dirty={dirty || busy} declarationsComplete={preparation.declarationsComplete}/>}

        </aside>
        <div className="author-submission-column">
      <ManuscriptProgress
        displayStatus={selectedManuscript?.display_status}
        reference={selectedManuscript?.reference ?? selected?.reference}
        title={selection.kind === "draft" ? form.title || "New manuscript draft" : selectedManuscript?.title}
        status={selection.kind === "draft" ? "draft" : selectedManuscript?.status}
        nextAction={selection.kind === "draft" ? `${nextStep.title} ${nextStep.detail}` : selectedManuscript?.status_detail ?? authorNextActions[selectedManuscript?.status ?? ""] ?? "Review the current manuscript status and editorial correspondence below."}
      >
        {selection.kind === "draft" && <>
          <ol className="manuscript-preparation" aria-label="Draft preparation">
            {preparationSteps.map((step, index) => <li key={step.title} data-state={step.complete ? "complete" : index === currentPreparation ? "current" : "upcoming"} aria-current={index === currentPreparation ? "step" : undefined}>
              <strong>{step.title}</strong><span>{step.complete ? "Complete" : index === currentPreparation ? "Current step" : "Upcoming"}</span>
            </li>)}
          </ol>
          {nextStep.href && <a href={nextStep.href}>{nextStep.linkLabel}</a>}
        </>}
      </ManuscriptProgress>

        {selection.kind === "draft" && <section className="draft-editor" aria-labelledby="editor-title" aria-busy={busy}>
          <h2 id="editor-title">{selected ? "Edit draft details" : "Start a draft"}</h2>
          {selected && <p className="work-meta">Paper ID: {selected.reference} / Draft</p>}
          <p className="muted-copy">You may save an incomplete draft. Fields marked <RequiredMark /> are required for final submission.</p>
          {error && <p ref={errorSummary} tabIndex={-1} className="error-message" role="alert">{error}</p>}
          <nav className="draft-section-nav" aria-label="Jump to a draft section">
            <span className="draft-section-nav__label">Jump to:</span>
            <a href="#manuscript-details">Manuscript details</a>
            <a href="#author-details">Authors and affiliations</a>
            {selected && <a href="#files-title">Manuscript files</a>}
            <a href="#submission-declarations">Declarations and submit</a>
          </nav>
          <form onSubmit={saveDraft}><fieldset disabled={busy} className="form-fields">
            <section id="manuscript-details" className="work-section manuscript-details-fields"><h3>Manuscript details</h3>
            <label><span>Manuscript title <RequiredMark /></span><input maxLength={500} value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></label>
            <label><span>Manuscript type <RequiredMark /></span><select value={form.manuscript_type ?? ""} onChange={(event) => setForm({ ...form, manuscript_type: event.target.value || null })}><option value="">Select a type</option>{manuscriptTypes.map((type) => <option key={type} value={type}>{type.replace(/^./, (letter) => letter.toUpperCase())}</option>)}</select></label>
            <label><span>Area of research <RequiredMark /></span><select id="research-area" aria-required="true" value={form.discipline ?? ""} onChange={event => setForm({...form, discipline: event.target.value || null, discipline_other: event.target.value === "other" ? form.discipline_other : null})}><option value="">Select an area</option>{researchAreas.map(area => <option key={area.value} value={area.value}>{area.label}</option>)}</select></label>
            {form.discipline === "other" && <label><span>Specify your research area <RequiredMark /></span><input maxLength={200} aria-required="true" value={form.discipline_other ?? ""} onChange={event => setForm({...form, discipline_other: event.target.value})} /></label>}
            <label className="manuscript-field--full"><span>Abstract <RequiredMark /></span><textarea rows={5} maxLength={50_000} value={form.abstract} onChange={(event) => setForm({ ...form, abstract: event.target.value })} /></label>
            <label className="manuscript-field--full keywords-field"><span>Keywords <RequiredMark /></span><input aria-describedby="keywords-help" placeholder="e.g. machine learning, clinical research" value={keywordsText} onChange={(event) => setKeywordsText(event.target.value)} /><span id="keywords-help" className="form-help">Enter at least one keyword. Separate keywords with commas.</span></label>
            </section>
            <fieldset id="author-details" className="author-fields"><legend>Authors and affiliations, in display order <RequiredMark /></legend><p className="form-help">Enter a name and affiliation for every author. Email is optional.</p>
              {form.authors.map((author, index) => (
                <div className="author-row" key={index}>
                  <label><span>Author {index + 1} name <RequiredMark /></span><input maxLength={200} value={author.full_name} onChange={(event) => updateAuthor(index, "full_name", event.target.value)} /></label>
                  <label><span>Affiliation <RequiredMark /></span><input maxLength={500} value={author.affiliation} onChange={(event) => updateAuthor(index, "affiliation", event.target.value)} /></label>
                  <label>Email (optional)<input type="email" maxLength={320} value={author.email ?? ""} onChange={(event) => updateAuthor(index, "email", event.target.value)} /></label>
                  <div className="author-row__actions">{index === form.authors.length - 1 && <button type="button" className="secondary-button" onClick={() => setForm({ ...form, authors: [...form.authors, { full_name: "", affiliation: "", email: "" }] })}><JournalIcon name="plus" size={15}/> Add author</button>}{form.authors.length > 1 && <button type="button" className="text-button" aria-label={`Remove author ${index + 1}`} onClick={() => setForm({ ...form, authors: form.authors.filter((_, row) => row !== index) })}>Remove author</button>}</div>
                </div>
              ))}

            </fieldset>
            <div className="work-actions"><button className="button-link" disabled={busy}>{busy && busyAction === "save" ? "Saving..." : "Save draft"}</button>{dirty && <span className="muted-copy">Unsaved changes</span>}</div>
          </fieldset></form>
          {selected && <section className="file-section" aria-labelledby="files-title">
            <h3 id="files-title">Manuscript files</h3>
            <p id="files-help">At least one PDF or DOCX file is required for final submission. Each file can be up to 50 MB, and every uploaded file must show a clean scan. Files remain private.</p>
            {busy && busyAction === "upload" && <p role="status">Uploading and scanning manuscript...</p>}
            <label className="file-picker"><span>Choose at least one manuscript file <RequiredMark /></span><input type="file" aria-describedby="files-help" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={uploadFile} disabled={busy} /></label>
            {selected.files.length === 0 && <p className="muted-copy">No manuscript file uploaded yet.</p>}
            {selected.files.length > 0 && <ul className="file-list">{selected.files.map((file) => <li key={file.id}><span>{file.original_name} / {Math.ceil(file.size_bytes / 1024)} KB / {file.scan_status}</span>{file.scan_status === "clean" ? <button className="text-button" type="button" disabled={busy} onClick={() => void downloadFile(file)}>Download</button> : <span className="muted-copy">Unavailable until scan is clean</span>}</li>)}</ul>}
          </section>}
        </section>}
          <SubmissionIntake
            draftId={selected?.id ?? null}
            draftTitle={selected?.title || "Untitled draft"}
            draftReference={selected?.reference}
            savedDraft={selected}
            dirty={dirty || busy}
            showDraft={selection.kind === "draft"}
            selectedManuscript={selectedManuscript}
            detailVersion={detailVersion}
            onSubmitted={manuscriptSubmitted}
            onManuscriptUpdated={updateManuscript}
            onBusyChange={setSubmissionBusy}
            onRevisionDirtyChange={setRevisionDirty}
            onPreparationChange={setPreparation}
          />
        </div>
      </div>
      </>}
    </main>
  );
}
