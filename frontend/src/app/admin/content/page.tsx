"use client";

import {DateTimeField} from "@/components/date-time-field";
import { ScheduledContentEditor, type ScheduledRecord } from "@/components/scheduled-content-editor";
import Link from "next/link";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { api, type ApiError } from "@/lib/api";
import { LoadingState, Notice, useConfirm } from "@/components/ui";
import { useUnsavedChanges } from "@/components/use-unsaved-changes";

type SectionId =
  | "overview"
  | "accounts"
  | "pages"
  | "calls"
  | "announcements"
  | "templates"
  | "board"
  | "resources";

type AdminUser = {
  id: string;
  email: string;
  display_name: string;
  roles: string[];
  is_active: boolean;
};
type PublicPage = {
  id: string;
  slug: string;
  title: string;
  status: string;
  version: number;
  updated_at: string;
};
type CallForPapers = ScheduledRecord;
type Announcement = ScheduledRecord;
type Template = {
  id: string;
  title: string;
  category: string;
  status: string;
  scan_status: string;
};
type BoardProfile = {
  id: string;
  full_name: string;
  institution?: string;
  role: string;
  is_active: boolean;
  identity_verified: boolean;
  qualification_verified: boolean;
  affiliation_verified: boolean;
  appointment_confirmed: boolean;
  consent_status: string;
  public_approved: boolean;
};
type PresentationResource = {
  id: string;
  title: string;
  resource_type: string;
  status: string;
  occurred_at: string | null;
  has_external_url: boolean;
  scan_status: string | null;
};
type OverviewData = {
  users: AdminUser[];
  pages: PublicPage[];
  calls: CallForPapers[];
  announcements: Announcement[];
  templates: Template[];
  board: BoardProfile[];
  resources: PresentationResource[];
};
type SuccessMessage = string | ((result: unknown) => string);

const EMPTY_DATA: OverviewData = {
  users: [],
  pages: [],
  calls: [],
  announcements: [],
  templates: [],
  board: [],
  resources: [],
};

const SECTION_INFO: Array<{ id: SectionId; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "pages", label: "Public pages" },
  { id: "calls", label: "Calls for Papers" },
  { id: "announcements", label: "Announcements" },
  { id: "templates", label: "Templates & downloads" },
  { id: "board", label: "Editorial board" },
  { id: "resources", label: "Presentations & resources" },
  { id: "accounts", label: "Accounts" },
];

const ROLE_OPTIONS = [
  { value: "author", label: "Author" },
  { value: "reviewer", label: "Reviewer" },
  { value: "associate_editor", label: "Associate Editor" },
  { value: "managing_editor", label: "Managing Editor" },
  { value: "editor_in_chief", label: "Editor-in-Chief" },
  { value: "site_admin", label: "Site Admin" },
];

function statusText(value: string): string {
  return value.replaceAll("_", " ").replaceAll("-", " ");
}

function statusClass(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-");
}

function formatDate(value: string | null): string {
  if (!value) return "Not set";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Invalid date" : date.toLocaleString();
}

function StatusBadge({ status }: { status: string }) {
  return <span className={`admin-status admin-status--${statusClass(status)}`}>{statusText(status)}</span>;
}

export default function ContentAdminPage() {
  const router = useRouter();
  const [data, setData] = useState<OverviewData>(EMPTY_DATA);
  const [activeSection, setActiveSection] = useState<SectionId>("overview");
  const [boardId, setBoardId] = useState("");
  const [currentUserId, setCurrentUserId] = useState("");
  const [roleAssignments, setRoleAssignments] = useState<Record<string, string[]>>({});
  const [isSiteAdmin, setIsSiteAdmin] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isWorking, setIsWorking] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [accessError, setAccessError] = useState("");
  const [loadFailed, setLoadFailed] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [boardRevision, setBoardRevision] = useState(0);
  const pending = useRef(false);
  const dirtyState = useRef(false);
  const dirtyForms = useRef(new Set<HTMLFormElement>());
  const dirtyRoles = useRef(new Set<string>());
  const sectionLocation = useRef("");
  dirtyState.current = dirty;
  const confirm = useConfirm();
  useUnsavedChanges(dirty, { history: false });
  const selectedBoard = data.board.find((profile) => profile.id === boardId);


  async function loadOverview(includeAccounts: boolean) {
    const [pages, calls, announcements, templates, board, resources, users] =
      await Promise.all([
        api<{ items: PublicPage[] }>("/admin/pages"),
        api<{ items: CallForPapers[] }>("/admin/calls-for-papers"),
        api<{ items: Announcement[] }>("/admin/announcements"),
        api<{ items: Template[] }>("/admin/templates"),
        api<{ items: BoardProfile[] }>("/admin/board"),
        api<{ items: PresentationResource[] }>("/admin/presentations"),
        includeAccounts
          ? api<{ items: AdminUser[] }>("/admin/users")
          : Promise.resolve({ items: [] as AdminUser[] }),
      ]);
    setData({
      users: users.items,
      pages: pages.items,
      calls: calls.items,
      announcements: announcements.items,
      templates: templates.items,
      board: board.items,
      resources: resources.items,
    });
    setRoleAssignments(current => Object.fromEntries(users.items.map(user => [user.id, dirtyRoles.current.has(user.id) ? (current[user.id] ?? user.roles) : user.roles])));
  }

  async function initialize() {
    setIsLoading(true); setLoadFailed(false); setAccessError("");
    try {
      const me = await api<{ id: string; roles: string[] }>("/auth/me");
      setCurrentUserId(me.id);
      const canManage = me.roles.some((role) => ["site_admin", "editor_in_chief", "managing_editor", "associate_editor"].includes(role));
      if (!canManage) { setAccessError("Content management access is required. Ask a Site Admin if your responsibilities have changed."); return; }
      const siteAdmin = me.roles.includes("site_admin");
      setIsSiteAdmin(siteAdmin);
      await loadOverview(siteAdmin);
    } catch (reason) {
      if ((reason as ApiError).status === 401) { router.replace("/sign-in"); return; }
      setAccessError((reason as ApiError).status === 403 ? "Your account does not have access to this content workspace." : "Content status could not be loaded. Your session may still be active. Please try again.");
      setLoadFailed((reason as ApiError).status !== 403);
    } finally { setIsLoading(false); }
  }

  useEffect(() => {
    sectionLocation.current = window.location.href;
    const section = new URLSearchParams(window.location.search).get("section");
    if (SECTION_INFO.some((item) => item.id === section)) setActiveSection(section as SectionId);
    const restoreSection = async () => {
      if (pending.current || (dirtyState.current && !await confirm({ title: "Discard unsaved changes?", description: "The entries in this content section have not been saved.", confirmLabel: "Discard changes", danger: true }))) {
        window.history.pushState(null, "", sectionLocation.current); return;
      }
      dirtyForms.current.clear(); dirtyRoles.current.clear(); setDirty(false); sectionLocation.current = window.location.href;
      const next = new URLSearchParams(window.location.search).get("section");
      setActiveSection(SECTION_INFO.some((item) => item.id === next) ? next as SectionId : "overview");
      setNotice(""); setError("");
    };
    window.addEventListener("popstate", restoreSection);
    void initialize();
    return () => window.removeEventListener("popstate", restoreSection);
  }, []);

  async function confirmPublication(action: () => Promise<unknown>, title: string, description: string, success: string) {
    if (pending.current) return;
    if (await confirm({ title, description, confirmLabel: "Approve publication" })) void perform(action, success);
  }

  async function perform(
    action: () => Promise<unknown>,
    successMessage: SuccessMessage,
    form?: HTMLFormElement,
  ): Promise<boolean> {
    if (pending.current) return false;
    pending.current = true; setNotice(""); setError(""); setIsWorking(true);
    try {
      const result = await action();
      form?.reset();
      if (form) dirtyForms.current.delete(form);
      setDirty([...dirtyForms.current].some(item => item.isConnected) || dirtyRoles.current.size > 0);
      if (form?.dataset.boardVerification) setBoardRevision(value => value + 1);
      setNotice(typeof successMessage === "function" ? successMessage(result) : successMessage);
      try { await loadOverview(isSiteAdmin); }
      catch { setError("The action was saved, but the refreshed content could not be loaded. Refresh this page to check its current status before continuing."); }
      return true;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The action could not be completed.");
      return false;
    } finally {
      pending.current = false; setIsWorking(false);
    }
  }

  function run(
    event: FormEvent<HTMLFormElement>,
    action: (formData: FormData) => Promise<unknown>,
    successMessage: SuccessMessage,
    confirmation?: string,
  ) {
    event.preventDefault();
    if (isWorking) return;
    const form = event.currentTarget;
    const formData = new FormData(form);
    void (async () => {
      if (confirmation && !await confirm({ title: "Save verification changes?", description: confirmation, confirmLabel: "Save verification" })) return;
      await perform(() => action(formData), successMessage, form);
    })();
  }

  async function navigateTo(section: SectionId) {
    if (section === activeSection || isWorking) return;
    if (dirty && !await confirm({ title: "Discard unsaved changes?", description: "The entries in this content section have not been saved.", confirmLabel: "Discard changes", danger: true })) return;
    dirtyForms.current.clear(); dirtyRoles.current.clear(); setDirty(false); setActiveSection(section);
    const url = new URL(window.location.href); url.searchParams.set("section", section);
    window.history.pushState(null, "", url); sectionLocation.current = url.href;
    setNotice("");
    setError("");
  }

  function toggleRole(userId: string, role: string, checked: boolean) {
    dirtyRoles.current.add(userId); setDirty(true);
    setRoleAssignments((current) => {
      const selected = new Set(current[userId] ?? []);
      if (checked) selected.add(role);
      else selected.delete(role);
      return { ...current, [userId]: [...selected] };
    });
  }

  function selectedRolesFor(user: AdminUser): string[] {
    return roleAssignments[user.id] ?? user.roles;
  }

  function userRolesChanged(user: AdminUser): boolean {
    const selected = selectedRolesFor(user);
    return selected.length !== user.roles.length || user.roles.some((role) => !selected.includes(role));
  }

  async function saveUserRoles(user: AdminUser, roles: string[]) {
    if (pending.current) return;
    if (!await confirm({ title: `Change roles for ${user.display_name}?`, description: `The selected roles (${roles.map(statusText).join(", ")}) will replace the current roles for ${user.email}. Existing sessions for this account will end.`, confirmLabel: "Save role changes" })) return;
    if (roles.length === 0) {
      setError("Assign at least one role before saving.");
      return;
    }
    pending.current = true; setNotice(""); setError(""); setIsWorking(true);
    try {
      await api(`/admin/users/${user.id}/roles`, {
        method: "PUT",
        body: JSON.stringify({ roles }),
      });
      if (user.id === currentUserId) {
        router.replace("/sign-in");
        return;
      }
      dirtyRoles.current.delete(user.id);
      for (const form of dirtyForms.current) { if (form.dataset.roleUser === user.id) dirtyForms.current.delete(form); }
      setDirty([...dirtyForms.current].some(item => item.isConnected) || dirtyRoles.current.size > 0);
      await loadOverview(isSiteAdmin);
      setNotice(`Roles updated for ${user.email}; existing sessions for that account were revoked.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The roles could not be updated.");
    } finally {
      pending.current = false; setIsWorking(false);
    }
  }

  const visibleSections = SECTION_INFO.filter(
    (section) => section.id !== "accounts" || isSiteAdmin,
  );

  function sectionCount(id: SectionId): number {
    switch (id) {
      case "accounts": return data.users.length;
      case "pages": return data.pages.length;
      case "calls": return data.calls.length;
      case "announcements": return data.announcements.length;
      case "templates": return data.templates.length;
      case "board": return data.board.length;
      case "resources": return data.resources.length;
      default: return 0;
    }
  }

  function sectionAttention(id: SectionId): number {
    switch (id) {
      case "accounts": return data.users.filter((user) => !user.is_active).length;
      case "pages": return data.pages.filter((page) => page.status === "draft").length;
      case "calls": return data.calls.filter((call) => call.status === "draft").length;
      case "announcements": return data.announcements.filter((item) => item.status === "draft").length;
      case "templates": return data.templates.filter((item) => item.status === "draft" || item.scan_status !== "clean").length;
      case "board": return data.board.filter((profile) => profile.is_active && !profile.public_approved).length;
      case "resources": return data.resources.filter((item) => item.status === "draft" || (item.scan_status !== null && item.scan_status !== "clean")).length;
      default: return 0;
    }
  }

  function renderOverview() {
    const cards = visibleSections.filter((section) => section.id !== "overview");
    return <div className="admin-overview">
      <div className="admin-section-heading">
        <div><p className="eyebrow">At a glance</p><h2>Content overview</h2></div>
        <p>Review content status, then open a section to create or publish an item.</p>
      </div>
      <div className="admin-overview-grid">
        {cards.map((section) => {
          const count = sectionCount(section.id);
          const attention = sectionAttention(section.id);
          return <button
            className="admin-overview-card"
            key={section.id}
            type="button"
            onClick={() => navigateTo(section.id)}
          >
            <span className="admin-overview-card__title">{section.label}</span>
            <span className="admin-overview-card__count">{count}</span>
            <span className="admin-overview-card__summary">
              {section.id === "pages" && `${data.pages.filter((item) => item.status === "published").length} published · ${data.pages.filter((item) => item.status === "draft").length} drafts`}
              {section.id === "calls" && `${data.calls.filter((item) => item.status === "open").length} open · ${data.calls.filter((item) => item.status === "scheduled").length} scheduled · ${data.calls.filter((item) => item.status === "draft").length} drafts`}
              {section.id === "announcements" && `${data.announcements.filter((item) => item.status === "published").length} published · ${data.announcements.filter((item) => item.status === "draft").length} drafts`}
              {section.id === "templates" && `${data.templates.filter((item) => item.status === "published").length} published · ${data.templates.filter((item) => item.scan_status !== "clean").length} awaiting clean scan`}
              {section.id === "board" && `${data.board.filter((item) => item.public_approved).length} public · ${sectionAttention("board")} need review`}
              {section.id === "resources" && `${data.resources.filter((item) => item.status === "published").length} published · ${data.resources.filter((item) => item.scan_status !== null && item.scan_status !== "clean").length} awaiting clean scan`}
              {section.id === "accounts" && `${data.users.filter((item) => item.is_active).length} active · ${data.users.filter((item) => !item.is_active).length} inactive`}
            </span>
            <span className="admin-overview-card__action">Manage section <span aria-hidden="true">→</span></span>
            {attention > 0 && <span className="admin-overview-card__attention">{attention} needs attention</span>}
          </button>;
        })}
      </div>
    </div>;
  }

  function renderActiveSection() {
    if (activeSection === "overview") return renderOverview();

    if (activeSection === "accounts" && isSiteAdmin) return <section className="admin-work-panel">
      <div className="admin-section-heading"><div><p className="eyebrow">Site administration</p><h2>Invited accounts</h2></div><p>Invite authors, reviewers, and staff, and manage account access.</p></div>
      <h3>Invite an account</h3>
      <form className="inline-form" onSubmit={(event) => run(event, async (form) => api("/invitations", { method: "POST", body: JSON.stringify({ email: form.get("email"), display_name: form.get("display_name"), role: form.get("role") }) }), (result) => result && typeof result === "object" && "message" in result && typeof result.message === "string" ? result.message : "Invitation created.")}>
        <label><span className="field-label">Email <span className="required-mark" aria-hidden="true">*</span><span className="visually-hidden"> (required)</span></span><input type="email" name="email" required /></label>
        <label><span className="field-label">Display name <span className="required-mark" aria-hidden="true">*</span><span className="visually-hidden"> (required)</span></span><input name="display_name" required /></label>
        <label>Role<select name="role"><option value="author">Author</option><option value="reviewer">Reviewer</option><option value="associate_editor">Associate Editor</option><option value="managing_editor">Managing Editor</option><option value="editor_in_chief">Editor-in-Chief</option><option value="site_admin">Site Admin</option></select></label>
        <button className="button-link" disabled={isWorking}>Send invitation</button>
      </form>
      <h3>Accounts and roles</h3>
      {data.users.length === 0 ? <p className="admin-empty-state">No accounts are available.</p> : <ul className="admin-record-list">
        {data.users.map((user) => <li className="admin-record" key={user.id}>
          <div className="admin-record__main"><strong>{user.display_name}</strong><span>{user.email} · {user.roles.join(", ")}</span></div>
          <StatusBadge status={user.is_active ? "active" : "inactive"} />
          {user.is_active && <button className="text-button button--danger" type="button" disabled={isWorking} onClick={async () => { if (await confirm({ title: `Deactivate ${user.display_name}?`, description: `${user.email} will lose account access.`, confirmLabel: "Deactivate account", danger: true })) void perform(() => api(`/admin/users/${user.id}/active`, { method: "PUT", body: JSON.stringify({ is_active: false }) }), `Deactivated ${user.email}.`); }}>Deactivate</button>}
          <details className="admin-role-detail"><summary>Manage access for {user.display_name}</summary><form className="admin-role-form" data-role-user={user.id} onSubmit={(event) => {
            event.preventDefault();
            if (userRolesChanged(user)) void saveUserRoles(user, selectedRolesFor(user));
          }}>
            <fieldset className="admin-role-editor">
              <legend>Assigned roles</legend>
              {user.roles.includes("editor") && <p className="admin-role-editor__note">This account has a legacy Editor role. Assign a specific editorial role to grant workspace access; the legacy role will be retained.</p>}
              {ROLE_OPTIONS.map((role) => <label className="admin-role-editor__option" key={role.value}>
                <input
                  type="checkbox"
                  checked={selectedRolesFor(user).includes(role.value)}
                  disabled={isWorking}
                  onChange={(event) => toggleRole(user.id, role.value, event.currentTarget.checked)}
                />
                {role.label}
              </label>)}
              <div className="admin-role-editor__actions">
                {selectedRolesFor(user).length === 0 && <span className="muted-copy" role="status">Select at least one role.</span>}
                <button className="secondary-button" type="submit" disabled={isWorking || selectedRolesFor(user).length === 0 || !userRolesChanged(user)}>
                  Save role changes
                </button>
              </div>
            </fieldset>
          </form></details>
        </li>)}
      </ul>}
    </section>;

    if (activeSection === "pages") return <section className="admin-work-panel">
      <div className="admin-section-heading"><div><p className="eyebrow">Public information</p><h2>Public pages</h2></div><p>Only approved page text becomes visible on the public site.</p></div>
      <h3>Existing pages</h3>
      {data.pages.length === 0 ? <p className="admin-empty-state">No public pages have been saved yet.</p> : <ul className="admin-record-list">
        {data.pages.map((page) => <li className="admin-record" key={page.id}>
          <div className="admin-record__main"><strong>{page.title}</strong><span>/{page.slug} · Version {page.version}</span></div>
          <StatusBadge status={page.status} />
          <span className="admin-record__meta">Updated {formatDate(page.updated_at)}</span>
          {page.status === "draft" && <button className="secondary-button" type="button" disabled={isWorking} onClick={async () => { if (await confirm({ title: `Publish ${page.title}?`, description: `Version ${page.version} will be visible on the public journal site.`, confirmLabel: "Publish version" })) void perform(() => api(`/admin/pages/${page.slug}/publish`, { method: "POST", body: JSON.stringify({}) }), `Page ${page.slug} published.`); }}>Publish version</button>}
        </li>)}
      </ul>}
      <h3>Create a public page</h3>
      <form className="inline-form" onSubmit={(event) => run(event, async (form) => api("/admin/pages", { method: "POST", body: JSON.stringify({ slug: form.get("slug"), title: form.get("title"), body: form.get("body") }) }), "Draft page saved. Publish it explicitly when approved.")}>
        <label><span className="field-label">Stable URL slug <span className="required-mark" aria-hidden="true">*</span><span className="visually-hidden"> (required)</span></span><input name="slug" required /></label>
        <label><span className="field-label">Title <span className="required-mark" aria-hidden="true">*</span><span className="visually-hidden"> (required)</span></span><input name="title" required /></label>
        <label className="admin-form-field--wide"><span className="field-label">Approved page text <span className="required-mark" aria-hidden="true">*</span><span className="visually-hidden"> (required)</span></span><textarea name="body" rows={8} required /></label>
        <button className="button-link" disabled={isWorking}>Save draft page</button>
      </form>
    </section>;

    if (activeSection === "calls" || activeSection === "announcements") return <ScheduledContentEditor key={activeSection} kind={activeSection} items={activeSection === "calls" ? data.calls : data.announcements} busy={isWorking} dirty={dirty} clearDirty={() => { dirtyForms.current.clear(); setDirty(false); }} perform={perform} />;

    if (activeSection === "templates") return <section className="admin-work-panel">
      <div className="admin-section-heading"><div><p className="eyebrow">Downloads</p><h2>Templates and downloads</h2></div><p>Files stay private until they pass scanning and are explicitly published.</p></div>
      <h3>Existing templates</h3>
      {data.templates.length === 0 ? <p className="admin-empty-state">No templates have been uploaded yet.</p> : <ul className="admin-record-list">
        {data.templates.map((item) => <li className="admin-record" key={item.id}>
          <div className="admin-record__main"><strong>{item.title}</strong><span>{item.category} · File scan: {statusText(item.scan_status)}</span></div>
          <StatusBadge status={item.status} />
          {item.status === "draft" && <button className="secondary-button" type="button" disabled={isWorking || item.scan_status !== "clean"} onClick={() => void confirmPublication(() => api(`/admin/templates/${item.id}/publish`, { method: "POST", body: JSON.stringify({}) }), `Publish ${item.title}?`, "This template file will become publicly downloadable.", "Template published after clean scan.")}>Publish template</button>}
        </li>)}
      </ul>}
      <h3>Upload a template draft</h3>
      <form className="inline-form" onSubmit={(event) => run(event, async (formData) => api("/admin/templates", { method: "POST", body: formData }), "Template stored privately; check scan status before publishing.")}>
        <label><span className="field-label">Title <span className="required-mark" aria-hidden="true">*</span><span className="visually-hidden"> (required)</span></span><input name="title" required /></label>
        <label><span className="field-label">Category <span className="required-mark" aria-hidden="true">*</span><span className="visually-hidden"> (required)</span></span><input name="category" required /></label>
        <label className="admin-form-field--wide">Description<textarea name="description" rows={3} /></label>
        <label>Language<input name="language" /></label>
        <label><span className="field-label">Version <span className="required-mark" aria-hidden="true">*</span><span className="visually-hidden"> (required)</span></span><input name="version" required /></label>
        <label><span className="field-label">PDF or DOCX file <span className="required-mark" aria-hidden="true">*</span><span className="visually-hidden"> (required)</span></span><input name="upload" type="file" accept=".pdf,.docx" required /></label>
        <button className="button-link" disabled={isWorking}>Upload private draft</button>
      </form>
    </section>;

    if (activeSection === "board") return <section className="admin-work-panel">
      <div className="admin-section-heading"><div><p className="eyebrow">People</p><h2>Editorial board</h2></div><p>Public display requires verification, confirmed appointments, consent evidence, and separate approval.</p></div>
      <p className="draft-warning" role="note">Add only confirmed appointments. Publish only fields that the person has consented to make public.</p>
      <h3>Profiles and review status</h3>
      {data.board.length === 0 ? <p className="admin-empty-state">No editorial board profiles have been added.</p> : <ul className="admin-record-list">
        {data.board.map((profile) => <li className="admin-record" key={profile.id}>
          <div className="admin-record__main"><strong>{profile.full_name}</strong><span>{statusText(profile.role)}{profile.consent_status ? ` · consent ${statusText(profile.consent_status)}` : ""}</span></div>
          <StatusBadge status={!profile.is_active ? "inactive" : profile.public_approved ? "public" : "needs verification"} />
        </li>)}
      </ul>}
      <h3>Add a private profile</h3>
      <form className="inline-form" onSubmit={(event) => run(event, async (form) => {
        const result = await api<{ id: string }>("/admin/board", { method: "POST", body: JSON.stringify({ full_name: form.get("full_name"), role: form.get("role"), qualifications: form.get("qualifications"), department: form.get("department"), institution: form.get("institution"), country: form.get("country"), specializations: String(form.get("specializations") ?? "").split(",").map((value) => value.trim()).filter(Boolean), biography: form.get("biography"), professional_url: form.get("professional_url") || null, orcid: form.get("orcid") || null, professional_email: form.get("professional_email") || null, appointment_start: form.get("appointment_start") ? new Date(`${String(form.get("appointment_start"))}T00:00:00Z`).toISOString() : null, appointment_end: form.get("appointment_end") ? new Date(`${String(form.get("appointment_end"))}T00:00:00Z`).toISOString() : null, display_order: 0 }) });
        setBoardId(result.id);
        return result;
      }, "Profile saved privately pending verification and consent.")}>
        <label><span className="field-label">Name <span className="required-mark" aria-hidden="true">*</span><span className="visually-hidden"> (required)</span></span><input name="full_name" required /></label>
        <label>Role<select name="role"><option value="editor_in_chief">Editor-in-Chief</option><option value="managing_editor">Managing Editor</option><option value="associate_editor">Associate Editor</option><option value="board_member">Board Member</option></select></label>
        <label>Qualifications<input name="qualifications" /></label>
        <label>Department<input name="department" /></label>
        <label>Institution<input name="institution" /></label>
        <label>Country<input name="country" /></label>
        <label>Specializations, comma separated<input name="specializations" /></label>
        <label className="admin-form-field--wide">Biography<textarea name="biography" rows={4} /></label>
        <label>Professional profile URL<input name="professional_url" type="url" /></label>
        <label>ORCID<input name="orcid" /></label>
        <label>Professional email<input name="professional_email" type="email" /></label>
        <DateTimeField name="appointment_start" label="Appointment starts" dateOnly />
        <DateTimeField name="appointment_end" label="Appointment ends" dateOnly />
        <button className="button-link" disabled={isWorking}>Save private profile</button>
      </form>
      <h3>Verify and publish a profile</h3>
      <label className="admin-select-field">Profile<select value={boardId} onChange={async (event) => { const nextId = event.target.value; if (dirty && !await confirm({ title: "Discard unsaved profile changes?", description: "Save or discard the current entries before selecting another person.", confirmLabel: "Discard changes", danger: true })) return; setBoardId(nextId); setDirty(false); setNotice(""); setError(""); }} disabled={isWorking}><option value="">Select profile</option>{data.board.map((profile) => <option key={profile.id} value={profile.id}>{profile.full_name} · {statusText(profile.consent_status)}</option>)}</select></label>
      {selectedBoard ? <section className="form-section" aria-labelledby="selected-board-heading">
        <header className="record-context"><p className="eyebrow">Selected profile</p><h3 id="selected-board-heading">{selectedBoard.full_name}</h3><p>{statusText(selectedBoard.role)}{selectedBoard.institution ? ` · ${selectedBoard.institution}` : ""}</p></header>
        <form data-board-verification="true" key={`${boardId}-${boardRevision}`} className="inline-form" aria-busy={isWorking} onSubmit={(event) => run(event, async (form) => api(`/admin/board/${boardId}/verification`, { method: "POST", body: JSON.stringify({ identity_verified: form.get("identity_verified") === "on", qualification_verified: form.get("qualification_verified") === "on", affiliation_verified: form.get("affiliation_verified") === "on", appointment_confirmed: form.get("appointment_confirmed") === "on", consent_status: form.get("consent_status"), consent_evidence_reference: form.get("consent_evidence_reference"), public_fields: String(form.get("public_fields") ?? "").split(",").map((value) => value.trim()).filter(Boolean) }) }), `Verification and consent saved for ${selectedBoard.full_name}. Public approval must be given separately.`, `This replaces the verification, consent evidence, and public field list for ${selectedBoard.full_name}. Any previous public approval will be removed. Confirm that you have entered the complete evidence and fields.`)}>
          <fieldset className="admin-form-field--wide"><legend>Verification and appointment</legend>
            <label><input type="checkbox" name="identity_verified" defaultChecked={selectedBoard.identity_verified} /> Identity checked</label>
            <label><input type="checkbox" name="qualification_verified" defaultChecked={selectedBoard.qualification_verified} /> Qualifications checked</label>
            <label><input type="checkbox" name="affiliation_verified" defaultChecked={selectedBoard.affiliation_verified} /> Affiliation checked</label>
            <label><input type="checkbox" name="appointment_confirmed" defaultChecked={selectedBoard.appointment_confirmed} /> Appointment confirmed</label>
          </fieldset>
          <label>Consent status<select name="consent_status" defaultValue={selectedBoard.consent_status}><option value="pending">Pending</option><option value="granted">Granted</option><option value="withdrawn">Withdrawn</option></select></label>
          <label>Consent evidence reference<input name="consent_evidence_reference" maxLength={500} /></label>
          <label className="admin-form-field--wide">Consented public fields, comma separated<input name="public_fields" placeholder="full_name, role" aria-describedby="board-consent-help" /></label>
          <p id="board-consent-help" className="admin-form-field--wide form-help">The saved evidence reference and public field list are not available in this view. Re-enter the complete approved evidence and fields when saving verification. Saving replaces those values and removes any previous public approval.</p>
          <button className="button-link" disabled={isWorking}>Save verification</button>
        </form>
        <button className="secondary-button" type="button" disabled={isWorking || dirty || selectedBoard.public_approved} onClick={async () => { if (await confirm({ title: `Publish ${selectedBoard.full_name}'s profile?`, description: "The verified, consented fields will appear on the public editorial board. Confirm that the appointment and consent evidence are current.", confirmLabel: "Approve public profile" })) void perform(() => api(`/admin/board/${boardId}/publish`, { method: "POST", body: JSON.stringify({ public_approved: true }) }), `Profile for ${selectedBoard.full_name} approved for public display.`); }}>Approve public profile</button>
        {dirty && <p className="form-help">Save verification changes before approving public display.</p>}
      </section> : <p className="admin-empty-state">Select a profile to review its verification and public display.</p>}

    </section>;

    if (activeSection === "resources") return <section className="admin-work-panel">
      <div className="admin-section-heading"><div><p className="eyebrow">Events and files</p><h2>Presentations and resources</h2></div><p>Only HTTPS links or files that pass scanning can be published.</p></div>
      <h3>Existing resources</h3>
      {data.resources.length === 0 ? <p className="admin-empty-state">No presentations or resources have been saved yet.</p> : <ul className="admin-record-list">
        {data.resources.map((item) => <li className="admin-record" key={item.id}>
          <div className="admin-record__main"><strong>{item.title}</strong><span>{item.resource_type} · {formatDate(item.occurred_at)} · File scan: {item.scan_status ? statusText(item.scan_status) : "not uploaded"}</span></div>
          <StatusBadge status={item.status} />
          {item.status === "draft" && <button className="secondary-button" type="button" disabled={isWorking || (!item.has_external_url && item.scan_status !== "clean")} onClick={() => void confirmPublication(() => api(`/admin/presentations/${item.id}/publish`, { method: "POST", body: JSON.stringify({}) }), `Publish ${item.title}?`, "This resource and its approved link or file will become publicly available.", "Resource published.")}>Publish resource</button>}
        </li>)}
      </ul>}
      <h3>Create a resource draft</h3>
      <form className="inline-form" onSubmit={(event) => run(event, async (form) => {
        let fileId: string | null = null;
        let scanStatus = "not uploaded";
        const file = form.get("upload");
        if (file instanceof File && file.size > 0) {
          const upload = new FormData();
          upload.set("upload", file);
          const stored = await api<{ id: string; scan_status: string }>("/admin/resources", { method: "POST", body: upload });
          fileId = stored.id;
          scanStatus = stored.scan_status;
        }
        const result = await api("/admin/presentations", { method: "POST", body: JSON.stringify({ title: form.get("title"), presenter: form.get("presenter"), resource_type: form.get("resource_type"), summary: form.get("summary"), occurred_at: form.get("occurred_at") ? new Date(String(form.get("occurred_at"))).toISOString() : null, external_url: form.get("external_url") || null, file_id: fileId, related_article_id: null, related_issue_id: null, display_order: 0 }) });
        return { result, scanStatus };
      }, "Resource saved as a private draft. Check the file scan status before publishing.")}>
        <label><span className="field-label">Title <span className="required-mark" aria-hidden="true">*</span><span className="visually-hidden"> (required)</span></span><input name="title" required /></label>
        <label>Presenter<input name="presenter" /></label>
        <label><span className="field-label">Resource type <span className="required-mark" aria-hidden="true">*</span><span className="visually-hidden"> (required)</span></span><input name="resource_type" required /></label>
        <label className="admin-form-field--wide">Summary<textarea name="summary" rows={4} /></label>
        <DateTimeField name="occurred_at" label="Date and time" />
        <label>HTTPS resource URL<input name="external_url" type="url" /></label>
        <label>Optional PDF or DOCX file<input name="upload" type="file" accept=".pdf,.docx" /></label>
        <button className="button-link" disabled={isWorking}>Save resource draft</button>
      </form>
    </section>;

    return <div className="admin-empty-state">This section is not available for your account.</div>;
  }

  return <main id="main-content" tabIndex={-1} className="workspace-page admin-content">
    <header className="workspace-header admin-content-header">
      <div><p className="eyebrow">Journal content</p><h1>Public pages and resources</h1></div>
      <Link href="/">Public site</Link>
    </header>
    <p className="draft-warning" role="note">Only approved content appears publicly. Do not enter unverified contacts, identifiers, charges, policies, board details, or official templates.</p>

    {accessError && <section className="workspace-access"><Notice tone={loadFailed ? "error" : "warning"}>{accessError}</Notice>{loadFailed && <button className="secondary-button" type="button" onClick={() => void initialize()}>Try again</button>}</section>}

    {!accessError && <div className="admin-console-layout" aria-busy={isLoading || isWorking}>
      <label className="admin-mobile-nav">
        <span>Content section</span>
        <select value={activeSection} onChange={(event) => navigateTo(event.target.value as SectionId)}>
          {visibleSections.map((section) => <option key={section.id} value={section.id}>{section.label}</option>)}
        </select>
      </label>
      <nav className="admin-rail" aria-label="Content management sections">
        <p className="admin-rail__label">Workspace</p>
        {visibleSections.map((section) => <button
          className={`admin-rail__item${activeSection === section.id ? " is-active" : ""}`}
          type="button"
          key={section.id}
          aria-current={activeSection === section.id ? "page" : undefined}
          onClick={() => navigateTo(section.id)}
        >
          <span>{section.label}</span>
          {section.id !== "overview" && <span className="admin-rail__count">{sectionCount(section.id)}</span>}
        </button>)}
      </nav>
      <div className="admin-main-panel" onChangeCapture={(event) => { const target = event.target; if (target instanceof Element) { const form = target.closest("form"); if (form) { dirtyForms.current.add(form); setDirty(true); } } }}>
        <div className="task-feedback">{notice && <Notice tone="success">{notice}</Notice>}{error && <Notice tone="error">{error}</Notice>}{isWorking && <p role="status">Saving changes...</p>}</div>
        {isLoading ? <LoadingState>Loading content status...</LoadingState> : <fieldset className="operation-fields" disabled={isWorking}><legend className="visually-hidden">Content editor</legend>{renderActiveSection()}</fieldset>}
      </div>
    </div>}

  </main>;
}
