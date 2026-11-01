"use client";

import { DemoBadge, PublicLoadError, PublicPageLayout } from "@/components/public-site";
import { demoResources } from "@/lib/demo-content";
import { formatPublicDate } from "@/lib/public-format";
import { usePublicCollection } from "@/lib/use-public-collection";

export default function PresentationsPage() {
  const { items, loading, error, reload } = usePublicCollection("/public/presentations", demoResources, "Journal resources could not be loaded.");
  return (
    <PublicPageLayout eyebrow="Presentations and resources" title="Journal resources" activeHref="/presentations" breadcrumb="Presentations and resources">
      {loading && <p className="notice-message" role="status">Loading approved resources...</p>}
      {items.length === 0 && !loading && !error && <p className="notice-message" role="status">Approved presentations and resources will appear here.</p>}
      {!loading && !error && items.map((item) => (
        <article className="public-resource-row" key={item.id}>
          <div>
            <h2>{item.title}</h2>
            {item.demo && <DemoBadge />}
            <p className="public-card__meta">{[item.presenter, formatPublicDate(item.occurred_at), item.resource_type.replaceAll("_", " ")].filter(Boolean).join(" | ")}</p>
            <p>{item.summary}</p>
            <div className="public-card__links">
              {item.file_url && <a href={item.file_url}>Download {item.title}</a>}
              {item.external_url && <a href={item.external_url} rel="noreferrer">{item.resource_type === "video" || item.resource_type === "recording" ? "Watch" : "Open resource:"} {item.title}</a>}
            </div>
          </div>
        </article>
      ))}
      {error && <PublicLoadError message={error} retry={reload} />}
    </PublicPageLayout>
  );
}
