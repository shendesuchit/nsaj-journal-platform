"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState, type DragEvent } from "react";
import { useRouter } from "next/navigation";

import { api, type ApiError } from "@/lib/api";
import { Button, LoadingState, Notice, StatusBadge, useConfirm } from "@/components/ui";
import { JournalIcon } from "@/components/journal-art";
import { useUnsavedChanges } from "@/components/use-unsaved-changes";
import { ManuscriptProgress } from "@/components/manuscript-progress";
import {
  demoPublicationVolumes,
  isDemoContentEnabled,
  type AdminIssueRecord,
  type AdminVolumeRecord,
} from "@/lib/demo-content";

type Readiness = {
  ready: boolean;
  blockers: { issue?: string; article_id?: string; slug?: string; blocker?: string; blockers?: string[] }[];
};
type ProductionArticleOption = {
  id: string;
  reference: string;
  title: string;
  status: string;
  issue_id: string | null;
};

export default function PublicationAdminPage() {
  const router = useRouter();
  const [volumes, setVolumes] = useState<AdminVolumeRecord[]>([]);
  const [productionArticles, setProductionArticles] = useState<ProductionArticleOption[]>([]);
  const [articlesLoading, setArticlesLoading] = useState(false);
  const [articleLoadError, setArticleLoadError] = useState("");
  const [volumeId, setVolumeId] = useState("");
  const [issueId, setIssueId] = useState("");
  const [articleId, setArticleId] = useState("");
  const [publishedArticle, setPublishedArticle] = useState<ProductionArticleOption | null>(null);
  const [requestedArticleReference, setRequestedArticleReference] = useState("");
  const [moveTargets, setMoveTargets] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [roles, setRoles] = useState<string[]>([]);
  const [draggedIssueId, setDraggedIssueId] = useState("");
  const [draggedVolumeId, setDraggedVolumeId] = useState("");
  const [dragTargetIssueId, setDragTargetIssueId] = useState("");
  const [arrangeArchive, setArrangeArchive] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [toolsOpen, setToolsOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [accessError, setAccessError] = useState("");
  const [loadFailed, setLoadFailed] = useState(false);
  const [working, setWorking] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [articleEvidenceDirty, setArticleEvidenceDirty] = useState(false);
  const [feedbackScope, setFeedbackScope] = useState("archive");
  const pending = useRef(false);
  const detailSequence = useRef(0);
  const dirtyForms = useRef(new Set<HTMLFormElement>());
  const confirm = useConfirm();
  useUnsavedChanges(dirty);
  const realIssues = volumes.filter((volume) => !volume.demo).flatMap((volume) => volume.issues.map((issue) => ({ ...issue, volume })));
  const assignableIssues = realIssues.filter((issue) => ["draft", "scheduled"].includes(issue.status));
  const selectedIssue = realIssues.find((issue) => issue.id === issueId);
  const selectedArticle = productionArticles.find((article) => article.id === articleId);
  const trackerArticle = selectedArticle ?? publishedArticle;
  const issueLabel = selectedIssue ? `Volume ${selectedIssue.volume.number} (${selectedIssue.volume.year}), Issue ${selectedIssue.number}${selectedIssue.title ? `: ${selectedIssue.title}` : ""}` : "";


  const demoPreview = volumes.length > 0 && volumes.every((volume) => volume.demo);
  const openVolumes = volumes.filter((volume) => volume.status === "open");
  const hasReorderableDrafts = volumes.some(
    (volume) => volume.issues.filter((issue) => issue.status === "draft").length > 1,
  );

  function openPublicationTask(id: string, targetVolume?: string) {
    if (targetVolume) setVolumeId(targetVolume);
    if (id === "new-volume" || id === "new-issue") setToolsOpen(true);
    const panel = document.getElementById(id);
    if (panel instanceof HTMLDetailsElement) panel.open = true;
    requestAnimationFrame(() => {
      panel?.scrollIntoView({ behavior: "smooth", block: "start" });
      panel?.querySelector<HTMLElement>("input:not([type=hidden]), select, button")?.focus({ preventScroll: true });
    });
  }

  const suggestedVolumeNumber = Math.max(0, ...volumes.filter(volume => !volume.demo).map(volume => volume.number)) + 1;
  const suggestedIssueNumber = Math.max(0, ...(volumes.find(volume => volume.id === volumeId)?.issues ?? []).map(issue => /^\d+$/.test(issue.number) ? Number(issue.number) : 0)) + 1;

  async function refreshVolumes() {
    const data = await api<{ items: AdminVolumeRecord[] }>("/admin/volumes");
    const nextVolumes = data.items.length === 0 && isDemoContentEnabled
      ? demoPublicationVolumes
      : data.items;
    setVolumes(nextVolumes);
    setMoveTargets({});
    return nextVolumes;
  }

  async function changeVolumeStatus(volume: AdminVolumeRecord, status: AdminVolumeRecord["status"]) {
    const label = status === "open" ? "Reopen" : status === "archived" ? "Archive" : volume.status === "archived" ? "Restore" : "Close";
    if (!await confirm({ title: `${label} Volume ${volume.number}?`, description: status === "open" ? "This volume will accept new issues again." : status === "archived" ? "This volume will move out of the active management list. Its published issues and articles remain publicly accessible." : "This volume will stop accepting new issues. Existing issues and published articles are retained.", confirmLabel: `${label} volume` })) return;
    await mutate(async () => {
      await api(`/admin/volumes/${volume.id}/status`, { method: "PUT", body: JSON.stringify({ status, expected_status: volume.status }) });
      if (volumeId === volume.id && status !== "open") setVolumeId("");
      await refreshVolumes();
      setNotice(`Volume ${volume.number} is now ${status}.`);
    }, "archive");
  }

  async function refreshProductionArticles() {
    setArticlesLoading(true);
    setArticleLoadError("");
    try {
      const data = await api<{ items: ProductionArticleOption[] }>("/admin/production-articles");
      setProductionArticles(data.items);
      setArticleId((current) => data.items.some((article) => article.id === current) ? current : "");
      return data.items;
    } catch (reason) {
      if ((reason as ApiError).status === 401) router.replace("/sign-in");
      setArticleLoadError("Production articles could not be loaded. Please try again.");
      return [];
    } finally {
      setArticlesLoading(false);
    }
  }

  async function chooseArticle(nextArticleId: string, target: HTMLSelectElement) {
    if (articleEvidenceDirty && !await confirm({
      title: "Discard unsaved article evidence?",
      description: "The entered evidence belongs to the current article. It will be cleared before changing the article.",
      confirmLabel: "Discard evidence",
      danger: true,
    })) {
      target.value = articleId;
      return;
    }
    for (const form of dirtyForms.current) {
      if (form.closest('[aria-label="Article verification"]')) dirtyForms.current.delete(form);
    }
    setArticleId(nextArticleId);
    setPublishedArticle(null);
    setRequestedArticleReference("");
    setReadiness(null);
    setNotice("");
    setError("");
    setArticleEvidenceDirty(false);
    setDirty([...dirtyForms.current].some((form) => form.isConnected && !form.contains(target)));
  }

  async function load() {
    setLoading(true); setLoadFailed(false); setAccessError("");
    try {
      const me = await api<{ roles: string[] }>("/auth/me");
      setRoles(me.roles);
      if (!me.roles.some((role) => ["site_admin", "editor_in_chief", "managing_editor", "associate_editor"].includes(role))) {
        setAccessError("Publication workspace access is required. Ask a Site Admin if your responsibilities have changed."); return;
      }
      await refreshVolumes();
      if (me.roles.includes("site_admin")) setProductionArticles([]);
      else await refreshProductionArticles();
    } catch (reason) {
      if ((reason as ApiError).status === 401) { router.replace("/sign-in"); return; }
      setAccessError((reason as ApiError).status === 403 ? "Your account does not have access to publication records." : "Publication records could not be loaded. Please try again.");
      setLoadFailed((reason as ApiError).status !== 403);
    } finally { setLoading(false); }
  }

  useEffect(() => { void load(); }, []);
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setRequestedArticleReference(params.get("submissionReference") ?? "");
  }, []);
  useEffect(() => {
    if (!requestedArticleReference) return;
    const requestedArticle = productionArticles.find((article) => article.reference === requestedArticleReference);
    if (requestedArticle) { setArticleId(requestedArticle.id); setRequestedArticleReference(""); }
  }, [productionArticles, requestedArticleReference]);
  useEffect(() => { setReadiness(null); detailSequence.current += 1; }, [issueId]);

  function feedback(scope: string) {
    if (scope !== feedbackScope) return null;
    return <div className="task-feedback">{notice && <Notice tone="success">{notice}</Notice>}{error && <Notice tone="error">{error}</Notice>}</div>;
  }

  async function mutate(callback: () => Promise<void>, scope: string, clearDirty = false) {
    if (pending.current) return;
    pending.current = true; setWorking(true); setFeedbackScope(scope); setError(""); setNotice("");
    try { await callback(); if (clearDirty) { setDirty(false); setArticleEvidenceDirty(false); } }
    catch (reason) { setError(reason instanceof Error ? reason.message : "The action could not be completed."); }
    finally { pending.current = false; setWorking(false); }
  }

  async function run(
    event: FormEvent<HTMLFormElement>,
    callback: (data: FormData) => Promise<void>,
  ) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    await mutate(async () => {
      await callback(data); form.reset(); dirtyForms.current.delete(form);
      const remaining = [...dirtyForms.current].filter(item => item.isConnected);
      setDirty(remaining.length > 0);
      setArticleEvidenceDirty(remaining.some(item => !!item.closest('[aria-label="Article verification"]')));
    }, form.closest("[data-feedback-scope]")?.getAttribute("data-feedback-scope") ?? "assembly");
  }

  async function moveIssue(issue: AdminIssueRecord, source: AdminVolumeRecord, destinationId: string) {
    if (pending.current) return;
    setFeedbackScope("archive");
    const destination = volumes.find((volume) => volume.id === destinationId);
    if (!destination || destination.status !== "open") {
      setError("Choose an open destination volume.");
      return;
    }
    if (issue.status !== "draft") {
      setError("Only draft issues can be moved.");
      return;
    }
    setError("");
    setNotice("");

    if (issue.demo && destination.demo) {
      const duplicate = destination.issues.some(
        (item) => item.id !== issue.id && item.number === issue.number,
      );
      if (duplicate) {
        setError(`Issue ${issue.number} already exists in Volume ${destination.number} (${destination.year}).`);
        return;
      }
      setVolumes((current) => current.map((volume) => {
        if (volume.id === source.id) {
          return { ...volume, issues: volume.issues.filter((item) => item.id !== issue.id) };
        }
        if (volume.id === destination.id) {
          return { ...volume, issues: [...volume.issues, issue] };
        }
        return volume;
      }));
      setMoveTargets((current) => ({ ...current, [issue.id]: "" }));
      setNotice(`Demo only: Issue ${issue.number} moved to Volume ${destination.number} for this preview. The change is not saved.`);
      return;
    }
    if (issue.demo || destination.demo) {
      setError("Preview issues can only be moved between preview volumes.");
      return;
    }

    pending.current = true; setWorking(true);
    try {
      await api(`/admin/issues/${issue.id}/volume`, {
        method: "PUT",
        body: JSON.stringify({ volume_id: destination.id }),
      });
      setNotice(`Issue ${issue.number} moved to Volume ${destination.number} (${destination.year}).`);
      await refreshVolumes();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The issue could not be moved.");
    } finally { pending.current = false; setWorking(false); }
  }

  function startIssueDrag(event: DragEvent<HTMLElement>, issue: AdminIssueRecord) {
    if (working || issue.status !== "draft") return;
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("application/x-nsaj-issue-id", issue.id);
    event.dataTransfer.setData("text/plain", issue.id);
    setDraggedVolumeId("");
    setDraggedIssueId(issue.id);
  }

  function startVolumeDrag(event: DragEvent<HTMLElement>, volume: AdminVolumeRecord) {
    if (working) return;
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("application/x-nsaj-volume-id", volume.id);
    event.dataTransfer.setData("text/plain", volume.id);
    setDraggedIssueId("");
    setDraggedVolumeId(volume.id);
  }

  async function reorderVolumes(sourceId: string, destinationId: string) {
    if (pending.current || sourceId === destinationId) return;
    const source = volumes.find((volume) => volume.id === sourceId);
    const destination = volumes.find((volume) => volume.id === destinationId);
    if (!source || !destination) return;
    const reordered = [...volumes];
    const from = reordered.findIndex((volume) => volume.id === sourceId);
    const to = reordered.findIndex((volume) => volume.id === destinationId);
    reordered.splice(from, 1);
    reordered.splice(to, 0, source);

    if (source.demo && destination.demo) {
      setVolumes(reordered);
      setFeedbackScope("archive");
      setNotice(`Demo only: Volume ${source.number} moved in this preview. The change is not saved.`);
      setError("");
      return;
    }
    if (source.demo || destination.demo) {
      setFeedbackScope("archive");
      setError("Preview volumes can only be reordered with other preview volumes.");
      return;
    }

    pending.current = true;
    setWorking(true);
    setFeedbackScope("archive");
    setNotice("");
    setError("");
    try {
      await api("/admin/volumes/order", {
        method: "PUT",
        body: JSON.stringify({ volume_ids: reordered.map((volume) => volume.id) }),
      });
      await refreshVolumes();
      setNotice("Volume order saved.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The volume order could not be saved.");
    } finally {
      pending.current = false;
      setWorking(false);
    }
  }

  function draftIssuesInSlotOrder(
    issues: AdminIssueRecord[],
    draftIds: string[],
  ): AdminIssueRecord[] {
    const byId = new Map(issues.filter((issue) => issue.status === "draft").map((issue) => [issue.id, issue]));
    let nextDraft = 0;
    return issues.map((issue) => issue.status === "draft" ? byId.get(draftIds[nextDraft++]) ?? issue : issue);
  }

  async function reorderDraftIssues(
    volume: AdminVolumeRecord,
    sourceId: string,
    destinationId: string,
  ) {
    if (pending.current || sourceId === destinationId) return;
    const drafts = volume.issues.filter((issue) => issue.status === "draft");
    const from = drafts.findIndex((issue) => issue.id === sourceId);
    const to = drafts.findIndex((issue) => issue.id === destinationId);
    if (from < 0 || to < 0) return;
    const reorderedDrafts = [...drafts];
    const moving = reorderedDrafts[from];
    if (!moving) return;
    reorderedDrafts.splice(from, 1);
    reorderedDrafts.splice(to, 0, moving);
    const issueIds = reorderedDrafts.map((issue) => issue.id);
    const reorderedIssues = draftIssuesInSlotOrder(volume.issues, issueIds);

    if (volume.demo) {
      setVolumes((current) => current.map((item) => item.id === volume.id
        ? { ...item, issues: reorderedIssues }
        : item));
      setFeedbackScope("archive");
      setError("");
      setNotice(`Demo only: Issue order changed for Volume ${volume.number}. The change is not saved.`);
      return;
    }

    pending.current = true;
    setWorking(true);
    setFeedbackScope("archive");
    setNotice("");
    setError("");
    try {
      await api(`/admin/volumes/${volume.id}/issues/order`, {
        method: "PUT",
        body: JSON.stringify({ issue_ids: issueIds }),
      });
      await refreshVolumes();
      setNotice(`Draft issue order saved for Volume ${volume.number}.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The draft issue order could not be saved.");
    } finally {
      pending.current = false;
      setWorking(false);
    }
  }

  function moveVolumeBy(volumeId: string, offset: number) {
    const index = volumes.findIndex((volume) => volume.id === volumeId);
    const destination = volumes[index + offset];
    if (index >= 0 && destination) void reorderVolumes(volumeId, destination.id);
  }

  function moveDraftIssueBy(volume: AdminVolumeRecord, issueId: string, offset: number) {
    const drafts = volume.issues.filter((issue) => issue.status === "draft");
    const index = drafts.findIndex((issue) => issue.id === issueId);
    const destination = drafts[index + offset];
    if (index >= 0 && destination) void reorderDraftIssues(volume, issueId, destination.id);
  }

  function dropIssue(event: DragEvent<HTMLElement>, destination: AdminVolumeRecord) {
    event.preventDefault();
    const volumeId = event.dataTransfer.getData("application/x-nsaj-volume-id") || draggedVolumeId;
    if (volumeId) {
      setDraggedVolumeId("");
      void reorderVolumes(volumeId, destination.id);
      return;
    }
    const issueId = event.dataTransfer.getData("application/x-nsaj-issue-id") || draggedIssueId;
    const source = volumes.find((volume) => volume.issues.some((issue) => issue.id === issueId));
    const issue = source?.issues.find((item) => item.id === issueId);
    setDraggedIssueId("");
    setDragTargetIssueId("");
    if (issue && source && source.id !== destination.id) void moveIssue(issue, source, destination.id);
  }

  function dropOnIssue(
    event: DragEvent<HTMLLIElement>,
    destinationVolume: AdminVolumeRecord,
    destinationIssue: AdminIssueRecord,
  ) {
    event.preventDefault();
    event.stopPropagation();
    const issueId = event.dataTransfer.getData("application/x-nsaj-issue-id") || draggedIssueId;
    const source = volumes.find((volume) => volume.issues.some((issue) => issue.id === issueId));
    const issue = source?.issues.find((item) => item.id === issueId);
    setDraggedIssueId("");
    setDragTargetIssueId("");
    if (!issue || !source) return;
    if (source.id === destinationVolume.id && destinationIssue.status === "draft") {
      void reorderDraftIssues(destinationVolume, issue.id, destinationIssue.id);
    } else if (source.id !== destinationVolume.id) {
      void moveIssue(issue, source, destinationVolume.id);
    }
  }

  return (
    <main id="main-content" tabIndex={-1} className="workspace-page publication-workspace" onChangeCapture={(event) => { const target = event.target; if (target instanceof Element) { const form = target.closest("form"); if (form) dirtyForms.current.add(form); } }}>
      <header className="workspace-header">
        <div><p className="eyebrow">JOURNAL PUBLISHING</p><h1>Volumes &amp; issues</h1><p className="publication-intro">Organize the journal one collection at a time. Create a volume, add its issues, then prepare approved articles for publication.</p></div>
        {!roles.includes("site_admin") && roles.length > 0 && <Link href="/editorial">Editorial cases</Link>}
      </header>
      <p className="draft-warning" role="note">Accepted articles stay private until an authorized editor publishes the issue. DOI and license details appear only after an editor records verification.</p>

      {loading && <LoadingState>Loading publication records...</LoadingState>}
      {accessError && <section className="workspace-access"><Notice tone={loadFailed ? "error" : "warning"}>{accessError}</Notice>{loadFailed && <Button variant="secondary" onClick={() => void load()}>Try again</Button>}</section>}
      {!loading && !accessError && <>
      {!roles.includes("site_admin") && <ManuscriptProgress reference={trackerArticle?.reference} title={trackerArticle?.title} status={trackerArticle?.status} nextAction={trackerArticle?.status === "published" ? "This article was published with its issue." : trackerArticle ? "Assign this article to an issue, verify publication details and check the issue's readiness." : undefined}>
        {trackerArticle?.status !== "published" && <Button type="button" variant="secondary" disabled={working} onClick={() => openPublicationTask("issue-publication")}>{trackerArticle ? "Continue issue preparation" : "Choose a production article"}</Button>}
      </ManuscriptProgress>}
      <div className="publication-actions" aria-label="Publication tasks">
        <Button type="button" disabled={working} onClick={() => openPublicationTask("new-volume")}><JournalIcon name="book" size={15} /> New volume</Button>
        <Button type="button" variant="secondary" disabled={working || openVolumes.length === 0} onClick={() => openPublicationTask("new-issue")}><JournalIcon name="file" size={15} /> Add an issue</Button>
        {!roles.includes("site_admin") && <Button type="button" variant="secondary" disabled={working} onClick={() => openPublicationTask("issue-publication")}>Review &amp; publish <JournalIcon name="arrow" size={15} /></Button>}
        <Button id="publication-tools-toggle" type="button" variant="text" aria-expanded={toolsOpen} aria-controls="publication-tools" onClick={() => setToolsOpen(value => !value)}>{toolsOpen ? "Expand archive" : "Show creation tools"}</Button>
        <Button type="button" variant="text" className="publication-actions__arrange" aria-pressed={arrangeArchive} onClick={() => setArrangeArchive(value => !value)}>{arrangeArchive ? "Done arranging" : "Arrange archive"}</Button>
      </div>
      <details className="publication-help"><summary>How volumes and issues work</summary><div className="publication-guide" aria-label="How volumes and issues work">
        <div><span className="publication-guide__number">01</span><div><strong>Create a volume</strong><p>A collection, usually for one year.</p></div></div>
        <div><span className="publication-guide__number">02</span><div><strong>Add its issues</strong><p>Each issue is a release within that volume.</p></div></div>
        <div><span className="publication-guide__number">03</span><div><strong>Review before publishing</strong><p>Editors confirm readiness before public release.</p></div></div>
      </div>
      </details>
      <p className="publication-legend"><strong>Draft</strong> — private preparation. &nbsp; <strong>Scheduled</strong> — planned release. &nbsp; <strong>Published</strong> — available in the journal archive.</p>
      {demoPreview && <p className="demo-preview-notice" role="note"><strong>Demo only.</strong> These fictional volumes and issues are preview records. Drag and move actions update this screen only and are discarded when you reload.</p>}
      <div className={`publication-layout${toolsOpen ? " publication-layout--tools" : ""}`}>
      <section className="volume-board" aria-labelledby="volume-board-title" aria-busy={working}>
        {feedback("archive")}
        <header className="volume-board__header">
          <div><p className="eyebrow">Publication archive</p><h2 id="volume-board-title">Volumes and issues</h2></div>
          <span>{volumes.length} {volumes.length === 1 ? "volume" : "volumes"}</span>
        </header>
        <label className="checkbox-label"><input type="checkbox" checked={showArchived} disabled={arrangeArchive} onChange={event => setShowArchived(event.target.checked)} /><span>Show archived volumes ({volumes.filter(volume => volume.status === "archived").length})</span></label>
        {arrangeArchive && (volumes.length > 1 || hasReorderableDrafts) && <p className="volume-board__hint">Reorder volumes and draft issues with the handles or arrow buttons. Use the volume selector to move a draft issue.</p>}
        {volumes.length === 0 ? <p className="muted-copy">Your archive is ready to begin. Create the first volume using “New volume” above.</p> : (
          <div className="volume-board__grid">
            {volumes.map((volume, volumeIndex) => {
              if (volume.status === "archived" && !showArchived && !arrangeArchive) return null;
              const counts = volume.issues.reduce<Record<string, number>>((result, issue) => {
                result[issue.status] = (result[issue.status] ?? 0) + 1;
                return result;
              }, {});
              const isIssueDropTarget = Boolean(draggedIssueId && volume.status === "open");
              const isVolumeDropTarget = Boolean(draggedVolumeId && draggedVolumeId !== volume.id);
              return (
                <section
                  className={`volume-card${isIssueDropTarget ? " volume-card--drop-target" : ""}${isVolumeDropTarget ? " volume-card--volume-drop-target" : ""}`}
                  key={volume.id}
                  aria-label={`Volume ${volume.number}, ${volume.year}`}
                  onDragOver={(event) => {
                    if ((draggedVolumeId && draggedVolumeId !== volume.id) || (draggedIssueId && volume.status === "open")) {
                      event.preventDefault();
                      event.dataTransfer.dropEffect = "move";
                    }
                  }}
                  onDrop={(event) => dropIssue(event, volume)}
                >
                  <header className="volume-card__header">
                    <div className="volume-card__heading-row">
                      <h3>Volume {volume.number} <span>· {volume.year}</span></h3>
                      {arrangeArchive && <div className="volume-order-controls" aria-label={`Reorder Volume ${volume.number}`}>
                        <button
                          type="button"
                          className="volume-order-handle"
                          draggable={!working}
                          disabled={working}
                          aria-label={`Drag to reorder Volume ${volume.number}`}
                          title="Drag to reorder volume"
                          onDragStart={(event) => startVolumeDrag(event, volume)}
                          onDragEnd={() => setDraggedVolumeId("")}
                        >⠿</button>
                        <button type="button" aria-label={`Move Volume ${volume.number} up`} disabled={working || volumeIndex === 0} onClick={() => moveVolumeBy(volume.id, -1)}>↑</button>
                        <button type="button" aria-label={`Move Volume ${volume.number} down`} disabled={working || volumeIndex === volumes.length - 1} onClick={() => moveVolumeBy(volume.id, 1)}>↓</button>
                      </div>}
                    </div>
                    <p className="volume-card__title" title={volume.title || "Journal volume"}>{volume.title || "Journal volume"}</p>
                    <StatusBadge status={volume.status} />
                  </header>
                  <p className="volume-card__summary">
                    {volume.issues.length} {volume.issues.length === 1 ? "issue" : "issues"}
                    {Object.entries(counts).map(([status, count]) => <span key={status}>{count} {status}</span>)}
                  </p>
                  {volume.demo && <span className="demo-badge">Demo only</span>}
                  {volume.issues.length === 0 ? <p className="muted-copy volume-card__empty">No issues yet. Add the first issue to this volume.</p> : (
                    <ul className="volume-issue-list">
                      {volume.issues.map((issue) => {
                        const movable = issue.status === "draft";
                        const draftIssues = volume.issues.filter((item) => item.status === "draft");
                        const draftPosition = draftIssues.findIndex((item) => item.id === issue.id);
                        const availableDestinations = openVolumes.filter((item) =>
                          item.id !== volume.id && (issue.demo ? item.demo : !item.demo),
                        );
                        return (
                          <li
                            className={`volume-issue${movable ? " volume-issue--movable" : ""}${dragTargetIssueId === issue.id ? " volume-issue--drag-over" : ""}`}
                            key={issue.id}
                            aria-label={`Issue ${issue.number}, ${issue.status}`}
                            onDragOver={(event) => {
                              if (draggedIssueId && issue.status === "draft") {
                                event.preventDefault();
                                event.dataTransfer.dropEffect = "move";
                              }
                            }}
                            onDragEnter={() => { if (draggedIssueId && issue.status === "draft") setDragTargetIssueId(issue.id); }}
                            onDragLeave={() => { if (dragTargetIssueId === issue.id) setDragTargetIssueId(""); }}
                            onDrop={(event) => dropOnIssue(event, volume, issue)}
                          >
                            <div className="volume-issue__main">
                              {arrangeArchive && movable && <div className="volume-order-controls" aria-label={`Reorder Issue ${issue.number}`}>
                                <button
                                  type="button"
                                  className="volume-order-handle"
                                  draggable={!working}
                                  disabled={working}
                                  aria-label={`Drag to reorder Issue ${issue.number}`}
                                  title="Drag to reorder draft issue"
                                  onDragStart={(event) => startIssueDrag(event, issue)}
                                  onDragEnd={() => { setDraggedIssueId(""); setDragTargetIssueId(""); }}
                                >⠿</button>
                                <button type="button" aria-label={`Move Issue ${issue.number} up`} disabled={working || draftPosition <= 0} onClick={() => moveDraftIssueBy(volume, issue.id, -1)}>↑</button>
                                <button type="button" aria-label={`Move Issue ${issue.number} down`} disabled={working || draftPosition === draftIssues.length - 1} onClick={() => moveDraftIssueBy(volume, issue.id, 1)}>↓</button>
                              </div>}
                              <span className="volume-issue__number">Issue {issue.number}</span>
                              <strong>{issue.title || `Issue ${issue.number}`}</strong>
                              <StatusBadge status={issue.status} />
                              {issue.demo && <span className="demo-badge">Demo only</span>}
                            </div>
                            {arrangeArchive && movable && availableDestinations.length > 0 && (
                              <div className="volume-issue__move">
                                <label>
                                  <span className="visually-hidden">Destination for Volume {volume.number}, Issue {issue.number}</span>
                                  <select
                                    disabled={working}
                                    value={moveTargets[issue.id] ?? ""}
                                    onChange={(event) => setMoveTargets((current) => ({ ...current, [issue.id]: event.target.value }))}
                                  >
                                    <option value="">Choose volume</option>
                                    {availableDestinations.map((item) => <option value={item.id} key={item.id}>Vol. {item.number} · {item.year}{item.id === volume.id ? " (current)" : ""}</option>)}
                                  </select>
                                </label>
                                <button
                                  type="button"
                                  className="secondary-button"
                                  disabled={working || !moveTargets[issue.id]}
                                  onClick={() => void moveIssue(issue, volume, moveTargets[issue.id])}
                                >Move to volume</button>
                              </div>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  )}
                  {volume.status === "open" && <div className="volume-card__add-issue"><Button type="button" variant="secondary" disabled={working} onClick={() => openPublicationTask("new-issue", volume.id)}><JournalIcon name="file" size={13} /> Add an issue to this volume</Button></div>}
                  {!volume.demo && <div className="volume-status-actions">
                    {volume.status === "open" && <Button type="button" variant="text" disabled={working} onClick={() => void changeVolumeStatus(volume, "closed")}>Close volume</Button>}
                    {volume.status === "closed" && <><Button type="button" variant="text" disabled={working} onClick={() => void changeVolumeStatus(volume, "open")}>Reopen</Button><Button type="button" variant="text" disabled={working || volume.issues.some(issue => issue.status !== "published")} onClick={() => void changeVolumeStatus(volume, "archived")}>Archive volume</Button>{volume.issues.some(issue => issue.status !== "published") && <small>Complete or move unpublished issues before archiving.</small>}</>}
                    {volume.status === "archived" && <Button type="button" variant="text" disabled={working} onClick={() => void changeVolumeStatus(volume, "closed")}>Restore volume</Button>}
                  </div>}
                </section>
              );
            })}
          </div>
        )}
      </section>

      <aside id="publication-tools" className="publication-tools" hidden={!toolsOpen} aria-label="Create volumes and issues">
        <div className="publication-tools__heading"><h2>Volume &amp; issue tools</h2><Button type="button" variant="text" onClick={() => { setToolsOpen(false); document.getElementById("publication-tools-toggle")?.focus(); }}>Hide panel</Button></div>
      <details className="publication-details" id="new-volume" data-feedback-scope="volume">
        <summary><span>01</span> Create a volume</summary>
        {feedback("volume")}
        <div className="content-panel"><div>
          <p className="form-help">Choose the next volume number and its publication year. The suggested number can be changed.</p>
          <p className="form-required-note"><span className="required-mark" aria-hidden="true">*</span> Required fields</p>
          <form className="inline-form" aria-busy={working} onChange={() => setDirty(true)} onSubmit={(event) => void run(event, async (data) => {
            const result = await api<AdminVolumeRecord>("/admin/volumes", { method: "POST", body: JSON.stringify({ number: Number(data.get("number")), year: Number(data.get("year")), title: data.get("title") }) });
            setVolumeId(result.id);
            setNotice(`Volume ${result.number} created.`);
            await refreshVolumes();
          })}>
            <label><span className="field-label">Volume number <span className="required-mark" aria-hidden="true">*</span><span className="visually-hidden"> (required)</span></span><input name="number" type="number" min="1" required defaultValue={suggestedVolumeNumber} /></label>
            <label><span className="field-label">Publication year <span className="required-mark" aria-hidden="true">*</span><span className="visually-hidden"> (required)</span></span><input name="year" type="number" min="1900" max="2200" required defaultValue={new Date().getFullYear()} /></label>
            <label className="form-field--wide">Volume title (optional)<input name="title" placeholder="For example, Annual research collection" /></label>
            <Button disabled={working}>{working ? "Saving..." : "Create volume"}</Button>
          </form>
        </div></div>
      </details>
      <details className="publication-details" id="new-issue" data-feedback-scope="issue">
        <summary><span>02</span> Add an issue</summary>
        {feedback("issue")}
        <div className="content-panel"><div>
          <p className="form-help">Select the volume first. A new issue is saved as a private draft until an editor publishes it.</p>
          <p className="form-required-note"><span className="required-mark" aria-hidden="true">*</span> Required fields</p>
          <form className="inline-form" aria-busy={working} onChange={() => setDirty(true)} onSubmit={(event) => void run(event, async (data) => {
            const targetVolume = volumes.find((item) => item.id === data.get("volume_id"));
            if (targetVolume?.demo) throw new Error("Demo preview volumes are read-only. Create a real volume before adding an issue.");
            const result = await api<{ id: string; number: string }>("/admin/issues", { method: "POST", body: JSON.stringify({ volume_id: data.get("volume_id"), number: data.get("number"), title: data.get("title"), description: data.get("description") }) });
            setIssueId(result.id);
            setNotice(`Draft issue ${result.number} created.`);
            await refreshVolumes();
          })}>
            <label><span className="field-label">Volume <span className="required-mark" aria-hidden="true">*</span><span className="visually-hidden"> (required)</span></span><select name="volume_id" required value={volumeId} onChange={(event) => setVolumeId(event.target.value)}><option value="">Select a volume</option>{openVolumes.map((item) => <option key={item.id} value={item.id}>Volume {item.number} · {item.year}{item.demo ? " · Demo only" : ""}</option>)}</select></label>
            <label><span className="field-label">Issue number <span className="required-mark" aria-hidden="true">*</span><span className="visually-hidden"> (required)</span></span><input name="number" required key={volumeId} defaultValue={String(suggestedIssueNumber)} /></label>
            <details className="publication-optional"><summary>Add an issue title or description (optional)</summary><div><label>Issue title<input name="title" placeholder="For example, Emerging perspectives" /></label><label className="form-field--wide">Description<textarea name="description" rows={3} placeholder="A brief introduction to this issue" /></label></div></details>
            <Button disabled={working}>{working ? "Saving..." : "Create draft issue"}</Button>
          </form>
        </div></div>
      </details>

      </aside>
      </div>
      {roles.includes("site_admin") ? <Notice tone="info">Site Admin can manage volume and issue records. Assigned editors handle confidential article assembly and publication.</Notice> : <details className="publication-details" id="issue-publication" data-feedback-scope="assembly"><summary><span>03</span> Review &amp; publish an issue</summary><section className="content-panel"><div>
        <h2>Assemble and publish an issue</h2>
        <p>Choose a production article by Paper ID and title, then select its target issue.</p>
        {feedback("assembly")}
        {working && <p role="status">Saving publication changes...</p>}
        {articlesLoading && <LoadingState>Loading production articles...</LoadingState>}
        {articleLoadError && <div className="task-feedback"><Notice tone="error">{articleLoadError}</Notice><Button type="button" variant="secondary" disabled={working || articlesLoading} onClick={() => void refreshProductionArticles()}>Retry articles</Button></div>}
        <div className="record-context"><p><strong>Article:</strong> {selectedArticle ? `${selectedArticle.reference} · ${selectedArticle.title}` : "Choose an available production article."}</p><p><strong>Target issue:</strong> {issueLabel || "Select an issue below."}</p></div>
        <form className="inline-form" aria-busy={working} onSubmit={(event) => void run(event, async (data) => {
          const aid = String(data.get("article_id")); const iid = String(data.get("issue_id"));
          await api(`/editorial/articles/${aid}/issue`, { method: "PUT", body: JSON.stringify({ issue_id: iid }) });
          setArticleId(aid); setIssueId(iid); setReadiness(null); setNotice(`${selectedArticle?.reference ?? "Article"} assigned to ${issueLabel}.`);
          await refreshProductionArticles();
        })}>
          <label><span className="field-label">Production article <span className="required-mark" aria-hidden="true">*</span><span className="visually-hidden"> (required)</span></span><select name="article_id" required value={articleId} disabled={working || articlesLoading || !!articleLoadError} onChange={(event) => void chooseArticle(event.currentTarget.value, event.currentTarget)} aria-describedby="article-choice-help"><option value="">Select by Paper ID and title</option>{productionArticles.map((article) => <option key={article.id} value={article.id}>{article.reference} · {article.title} · {article.status}</option>)}</select><span id="article-choice-help" className="form-help">Only production articles from your assigned editorial cases appear here.</span></label>
          <label><span className="field-label">Issue <span className="required-mark" aria-hidden="true">*</span><span className="visually-hidden"> (required)</span></span><select name="issue_id" required value={issueId} disabled={working} onChange={(event) => { setIssueId(event.target.value); setNotice(""); setError(""); }}><option value="">Select a draft or scheduled issue</option>{assignableIssues.map((issue) => <option key={issue.id} value={issue.id}>Volume {issue.volume.number} ({issue.volume.year}) · Issue {issue.number}{issue.title ? ` — ${issue.title}` : ""} · {issue.status}</option>)}</select></label>
          {!articlesLoading && !articleLoadError && productionArticles.length === 0 && <p className="form-help">No production articles are available for your assigned editorial cases yet. Create a production record from an accepted case to make it available here.</p>}
          {assignableIssues.length === 0 && <p className="form-help">Create a draft issue above to begin assembly.</p>}
          <Button disabled={working || articlesLoading || !!articleLoadError || !selectedArticle || !issueId}>{working ? "Saving..." : "Assign article"}</Button>
        </form>
        <section className="form-section" key={articleId} aria-label="Article verification">
          <h3>Verify publication details</h3><p>Evidence below applies to {selectedArticle ? `${selectedArticle.reference} · ${selectedArticle.title}` : "the selected production article"}.</p>
          <form className="inline-form" aria-busy={working} onChange={() => { setDirty(true); setArticleEvidenceDirty(true); }} onSubmit={(event) => void run(event, async (data) => { await api(`/editorial/articles/${articleId}/license/verify`, { method: "POST", body: JSON.stringify({ evidence_reference: data.get("license_evidence") }) }); setReadiness(null); setNotice(`License verification recorded for ${selectedArticle?.reference ?? "the selected article"}.`); })}>
            <label><span className="field-label">License approval reference <span className="required-mark" aria-hidden="true">*</span><span className="visually-hidden"> (required)</span></span><input name="license_evidence" required maxLength={500} /></label><Button variant="secondary" disabled={working || !articleId}>Record license verification</Button>
          </form>
          <form className="inline-form" aria-busy={working} onChange={() => { setDirty(true); setArticleEvidenceDirty(true); }} onSubmit={(event) => void run(event, async (data) => { const result = await api<{ skipped?: boolean }>(`/editorial/articles/${articleId}/doi/verify`, { method: "POST", body: JSON.stringify({ evidence_reference: data.get("doi_evidence") }) }); setReadiness(null); setNotice(result.skipped ? "No DOI is registered; DOI verification was skipped." : `DOI registration verification recorded for ${selectedArticle?.reference ?? "the selected article"}.`); })}>
            <label>DOI registration reference<input name="doi_evidence" maxLength={500} placeholder="Optional; only if a DOI is registered" /></label><Button variant="secondary" disabled={working || !articleId}>Record DOI verification</Button>
          </form>
        </section>
        <section className="form-section" aria-label="Issue publication">
          <h3>Review and publish</h3><p>{issueLabel || "Select an issue before checking its readiness."}</p>
          <div className="form-actions">
            <Button type="button" variant="secondary" disabled={working || !issueId} onClick={() => void mutate(async () => { const sequence = ++detailSequence.current; const result = await api<Readiness>(`/editorial/issues/${issueId}/readiness`); if (sequence === detailSequence.current) setReadiness(result); }, "assembly")}>Check readiness</Button>
            <Button type="button" disabled={working || !issueId || !readiness?.ready} onClick={async () => {
              if (!await confirm({ title: "Publish this issue?", description: `${issueLabel} and its assigned articles will become publicly available. Review the current issue and all publication details before proceeding.`, confirmLabel: "Publish issue" })) return;
              void mutate(async () => {
                const result = await api<{ published_article_ids: string[] }>(`/editorial/issues/${issueId}/publish`, { method: "POST", body: JSON.stringify({}) });
                setPublishedArticle(selectedArticle && result.published_article_ids?.includes(selectedArticle.id) ? { ...selectedArticle, status: "published", issue_id: issueId } : null);
                setArticleId(""); setRequestedArticleReference("");
                setNotice(`${issueLabel} published.`); setReadiness(null); setIssueId("");
                try { await refreshVolumes(); await refreshProductionArticles(); } catch { setError("The issue was published, but the refreshed archive could not be loaded. Refresh this page to check its status."); }
              }, "assembly");
            }}>Publish issue</Button>
          </div>
          {!readiness && <p className="form-help">Check readiness to see publication blockers and enable publishing. The server checks requirements again when publishing.</p>}
          {readiness && <section aria-label="Publication readiness"><h4>{readiness.ready ? "Ready to publish" : "Publication blockers"}</h4>{readiness.ready ? <Notice tone="success">The selected issue passed the current readiness check.</Notice> : <ul>{readiness.blockers.map((item, index) => <li key={`${item.slug ?? item.issue ?? "blocker"}-${index}`}>{item.blocker ?? `${item.slug ?? selectedArticle?.reference ?? "Article"}: ${(item.blockers ?? []).join("; ")}`}</li>)}</ul>}</section>}
        </section>
      </div></section></details>}
      </>}

    </main>
  );
}
