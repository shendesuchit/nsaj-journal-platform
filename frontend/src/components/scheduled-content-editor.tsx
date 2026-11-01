"use client";

import {DateTimeField} from "@/components/date-time-field";
import { FormEvent, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useConfirm } from "@/components/ui";

export type ScheduledRecord = {id: string; title: string; status: string; version: number; body?: string; description?: string; scope?: string; manuscript_types?: string[]; instructions?: string; related_issue_id?: string | null; opens_at?: string | null; deadline_at?: string | null; time_zone?: string; contact?: string; display_order?: number; publish_at?: string | null; published_at?: string | null};
type Props = {kind: "calls" | "announcements"; items: ScheduledRecord[]; busy: boolean; dirty: boolean; clearDirty: () => void; perform: (action: () => Promise<unknown>, message: string, form?: HTMLFormElement) => Promise<boolean>};
function localDate(value?: string | null) { if (!value) return ""; const date = new Date(value); return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0,16); }

export function ScheduledContentEditor({kind, items, busy, dirty, clearDirty, perform}: Props) {
  const [editing, setEditing] = useState<ScheduledRecord | null>(null);
  const [revision, setRevision] = useState(0);
  const [zone, setZone] = useState("your local time zone");
  const [showArchived, setShowArchived] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);
  const confirm = useConfirm();
  const call = kind === "calls";
  const noun = call ? "Call for Papers" : "announcement";
  const path = `/admin/${call ? "calls-for-papers" : "announcements"}`;
  useEffect(() => { setZone(Intl.DateTimeFormat().resolvedOptions().timeZone); }, []);
  async function edit(item: ScheduledRecord | null) {
    if (dirty && !await confirm({title: "Discard unsaved changes?", description: "Your unsaved entries will be discarded.", confirmLabel: "Discard changes", danger: true})) return;
    clearDirty(); setEditing(item); setRevision(value => value + 1);
    requestAnimationFrame(() => { formRef.current?.scrollIntoView({behavior: "smooth", block: "start"}); formRef.current?.querySelector<HTMLInputElement>("input")?.focus(); });
  }
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget, data = new FormData(form);
    const text = (key: string) => String(data.get(key) ?? "").trim();
    const date = (key: string) => text(key) ? new Date(text(key)).toISOString() : null;
    const payload = call ? {title: text("title"), description: text("description"), scope: text("scope"), manuscript_types: text("manuscript_types").split(",").map(x => x.trim()).filter(Boolean), instructions: text("instructions"), opens_at: date("opens_at"), deadline_at: date("deadline_at"), time_zone: zone, contact: text("contact"), display_order: editing?.display_order ?? 0, related_issue_id: editing?.related_issue_id ?? null} : {title: text("title"), body: text("body"), publish_at: date("publish_at")};
    if (await perform(() => api(editing ? `${path}/${editing.id}?version=${editing.version}` : path, {method: editing ? "PATCH" : "POST", body: JSON.stringify(payload)}), "Draft saved. Review and approve it to publish or schedule.", form)) { setEditing(null); setRevision(value => value + 1); }
  }
  async function action(item: ScheduledRecord, operation: string, label: string) {
    if (!await confirm({title: `${label}: ${item.title}?`, description: operation === "delete" ? "This removes the unpublished item. Its audit record is retained." : operation === "archive" ? "This item will be removed from the public site." : "Confirm this change to the publication schedule.", confirmLabel: label, danger: operation === "delete" || operation === "archive"})) return;
    const future = !!item.opens_at && Date.parse(item.opens_at) > Date.now();
    const url = `${path}/${item.id}${operation === "delete" ? "" : `/${operation}`}?version=${item.version}`;
    if (await perform(() => api(url, {method: operation === "delete" ? "DELETE" : "POST", ...(operation === "approve" ? {body: JSON.stringify({status: future ? "scheduled" : "open"})} : {})}), `${noun} updated.`)) { if (editing?.id === item.id) { setEditing(null); setRevision(value => value + 1); } }
  }
  return <section className="admin-work-panel">
    <div className="admin-section-heading"><div><p className="eyebrow">Journal updates</p><h2>{call ? "Calls for Papers" : "Announcements"}</h2></div><p>Save a draft, then approve publication. Future items appear automatically at the scheduled time.</p></div>
    <label className="checkbox-row"><input type="checkbox" checked={showArchived} onChange={event => setShowArchived(event.target.checked)} />Show archived items</label>
    <ul className="admin-record-list">{items.filter(item => showArchived || item.status !== "archived").map(item => {
      const editable = item.status === "draft" || item.status === "scheduled";
      const date = call ? item.opens_at : item.publish_at;
      const future = !!date && Date.parse(date) > Date.now();
      return <li className="admin-record" key={item.id}><div><h3>{item.title}</h3><p className="small-copy"><span className="status-pill">{item.status}</span>{date && <> · {call ? "Opens" : "Publication"}: <time dateTime={date}>{new Date(date).toLocaleString()}</time></>}{call && item.deadline_at && <> · Deadline: {new Date(item.deadline_at).toLocaleString()}</>}</p></div><div className="content-record-actions">
        {editable && <button type="button" className="secondary-button" disabled={busy} onClick={() => void edit(item)}>{item.status === "scheduled" ? "Edit / reschedule" : "Edit"}</button>}
        {item.status === "draft" && <button type="button" className="secondary-button" disabled={busy || dirty} onClick={() => void action(item, call ? "approve" : future ? "schedule" : "publish", future ? "Approve schedule" : "Publish now")}>{future ? "Approve schedule" : "Publish now"}</button>}
        {item.status === "scheduled" && <button type="button" className="secondary-button" disabled={busy || dirty} onClick={() => void action(item, "cancel-schedule", "Cancel schedule")}>Cancel schedule</button>}
        {call && item.status === "open" && <button type="button" className="secondary-button" disabled={busy || dirty} onClick={() => void action(item, "close", "Close call")}>Close call</button>}
        {editable ? <button type="button" className="text-button button--danger" disabled={busy || dirty} onClick={() => void action(item, "delete", "Delete")}>Delete</button> : item.status !== "archived" && <button type="button" className="text-button" disabled={busy || dirty} onClick={() => void action(item, "archive", "Archive")}>Archive</button>}
      </div></li>;
    })}</ul>
    {items.length === 0 && <p className="admin-empty-state">No {call ? "calls" : "announcements"} saved yet.</p>}
    <form ref={formRef} key={`${editing?.id ?? "new"}:${revision}`} className="inline-form scheduled-content-form" onSubmit={save}>
      <h3>{editing ? `Edit ${noun}` : `Create ${noun}`}</h3>
      <p className="form-help">Times use {zone}. Editing a scheduled item cancels its approval; approve the saved draft again.</p>
      <fieldset className="form-fields" disabled={busy}>
        <label><span>Title <span className="required-mark">*</span></span><input name="title" required maxLength={300} defaultValue={editing?.title ?? ""} /></label>
        <label><span>{call ? "Description" : "Announcement text"} <span className="required-mark">*</span></span><textarea name={call ? "description" : "body"} required maxLength={call ? 30000 : 20000} rows={4} defaultValue={(call ? editing?.description : editing?.body) ?? ""} /></label>
        {call ? <>
          <label>Scope<textarea name="scope" maxLength={10000} defaultValue={editing?.scope ?? ""} /></label>
          <label>Manuscript types, separated by commas<input name="manuscript_types" defaultValue={editing?.manuscript_types?.join(", ") ?? ""} /></label>
          <label>Submission instructions<textarea name="instructions" maxLength={10000} defaultValue={editing?.instructions ?? ""} /></label>
          <div className="content-date-grid"><DateTimeField label="Opening time" name="opens_at" defaultValue={localDate(editing?.opens_at)} /><DateTimeField label="Deadline" name="deadline_at" defaultValue={localDate(editing?.deadline_at)} /></div>
          <label>Contact<input name="contact" maxLength={320} defaultValue={editing?.contact ?? ""} /></label>
        </> : <DateTimeField label="Publication time" name="publish_at" hint="Leave blank for immediate publication after approval." defaultValue={localDate(editing?.publish_at)} />}
        <div className="content-record-actions"><button className="button-link">Save draft</button>{editing && <button type="button" className="secondary-button" onClick={() => void edit(null)}>Cancel editing</button>}</div>
      </fieldset>
    </form>
  </section>;
}
