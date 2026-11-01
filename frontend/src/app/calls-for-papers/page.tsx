"use client";

import { DemoBadge, PublicLoadError, PublicPageLayout } from "@/components/public-site";
import { demoCalls } from "@/lib/demo-content";
import { formatCallDeadline } from "@/lib/public-format";
import { usePublicCollection } from "@/lib/use-public-collection";

export default function CallsForPapersPage() {
  const { items, loading, error, reload } = usePublicCollection("/public/calls-for-papers", demoCalls, "Calls for Papers could not be loaded.");

  return (
    <PublicPageLayout eyebrow="For researchers and authors" title="Calls for Papers" activeHref="/calls-for-papers" breadcrumb="Calls for Papers">
      <p className="muted-copy">This page lists calls approved for public display. Demo samples are fictional and are not open for submissions.</p>
      {loading && <p className="notice-message" role="status">Loading approved calls...</p>}
      {items.length === 0 && !loading && !error && <p className="notice-message" role="status">No approved Calls for Papers are currently listed.</p>}
      {!loading && !error && items.map((item) => (
        <article className="public-call" key={item.id}>
          <header className="public-record-heading">
            <h2>{item.title}</h2>
            {item.demo ? <DemoBadge /> : <span className="public-state">{item.status.replaceAll("_", " ")}</span>}
          </header>
          {item.deadline_at && <p className="public-call__deadline"><strong>Deadline: </strong><time dateTime={item.deadline_at}>{formatCallDeadline(item.deadline_at, item.time_zone)}</time></p>}
          <p>{item.description}</p>
          <dl className="public-definition-list">
            {item.scope && <div><dt>Scope</dt><dd>{item.scope}</dd></div>}
            <div><dt>Manuscript types</dt><dd>{item.manuscript_types.join(", ") || "See call instructions"}</dd></div>
          </dl>
          {item.instructions.length > 600 ? <details className="public-call-instructions"><summary>Submission instructions</summary><p>{item.instructions}</p></details>
            : <section className="public-call-instructions"><h3>Submission instructions</h3><p>{item.instructions}</p></section>}
        </article>
      ))}
      {error && <PublicLoadError message={error} retry={reload} />}
    </PublicPageLayout>
  );
}
