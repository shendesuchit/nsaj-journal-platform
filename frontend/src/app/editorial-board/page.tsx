"use client";

import { DemoBadge, PublicLoadError, PublicPageLayout } from "@/components/public-site";
import { demoBoardMembers, type PublicBoardMember } from "@/lib/demo-content";
import { usePublicCollection } from "@/lib/use-public-collection";

function roleLabel(role: string) {
  return role.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export default function EditorialBoardPage() {
  const { items, loading, error, reload } = usePublicCollection("/public/editorial-board", demoBoardMembers, "The editorial board could not be loaded.");
  const groups = new Map<string, PublicBoardMember[]>();
  for (const item of items) {
    const role = item.role || "Editorial profiles";
    groups.set(role, [...(groups.get(role) ?? []), item]);
  }
  return (
    <PublicPageLayout eyebrow="Editorial board" title="Journal editors" activeHref="/editorial-board" breadcrumb="Editorial board">
      <p className="muted-copy">Only approved editorial profiles are displayed here. Demo samples are fictional and do not represent actual appointments.</p>
      {loading && <p className="notice-message" role="status">Loading approved profiles...</p>}
      {items.length === 0 && !loading && !error && <p className="notice-message" role="status">Editorial board profiles will appear here after verification, consent, and approval.</p>}
      {!loading && !error && [...groups].map(([role, members], index) => <section className="public-board-group" key={role} aria-labelledby={`board-role-${index}`}>
        <h2 id={`board-role-${index}`}>{roleLabel(role)}</h2>
        <div className="public-board-directory">{members.map((item) => <article className="public-profile" key={item.id}>
          <h3>{item.full_name ?? "Editorial profile"}</h3>
          {item.demo && <DemoBadge />}
          {item.qualifications && <p className="public-profile__qualification">{item.qualifications}</p>}
          {(item.department || item.institution || item.country) && <p className="public-article__metadata">{[item.department, item.institution, item.country].filter(Boolean).join(" | ")}</p>}
          {item.specializations?.length ? <p><strong>Specializations:</strong> {item.specializations.join(", ")}</p> : null}
          {item.biography && <p>{item.biography}</p>}
          <div className="public-card__links">
            {item.professional_url && <a href={item.professional_url} rel="noreferrer">Professional profile of {item.full_name ?? "editor"}</a>}
            {item.orcid && <span>ORCID: {item.orcid}</span>}
          </div>
        </article>)}</div>
      </section>)}
      {error && <PublicLoadError message={error} retry={reload} />}
    </PublicPageLayout>
  );
}
