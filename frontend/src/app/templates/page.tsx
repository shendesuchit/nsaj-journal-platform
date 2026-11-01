"use client";

import { AuthorDownloads } from "@/components/author-downloads";
import { DemoBadge, PublicLoadError, PublicPageLayout } from "@/components/public-site";
import { demoTemplates } from "@/lib/demo-content";
import { friendlyFileFormat } from "@/lib/public-format";
import { usePublicCollection } from "@/lib/use-public-collection";

export default function TemplatesPage() {
  const { items, loading, error, reload } = usePublicCollection("/public/templates", demoTemplates, "The template library could not be loaded.");
  return (
    <PublicPageLayout eyebrow="Author resources" title="Templates and downloads" activeHref="/templates" breadcrumb="Templates and downloads">
      <p className="muted-copy">Use the current journal files below when preparing a manuscript. Additional approved resources published through the journal system appear underneath.</p>
      <AuthorDownloads heading="Journal forms and templates" />
      <section className="public-resource-section" aria-labelledby="managed-resources-title">
        <div className="public-section-heading"><p className="eyebrow">RESOURCE LIBRARY</p><h2 id="managed-resources-title">Additional approved resources</h2></div>
        {loading && <p className="notice-message" role="status">Loading approved resources...</p>}
        {items.length === 0 && !loading && !error && <p className="notice-message" role="status">No additional managed resources are currently listed.</p>}
        {!loading && !error && items.map((item) => (
          <article className="public-resource-row" key={item.id}>
            <div>
              <h2>{item.title}</h2>
              {item.demo && <DemoBadge />}
              <p>{item.description}</p>
              <p className="public-card__meta">{[item.category.replaceAll("_", " "), `Version ${item.version}`, item.language, item.file_type ? friendlyFileFormat(item.file_type) : null].filter(Boolean).join(" | ")}</p>
            </div>
            {item.download_url && <a className="button-link button-link--outline" href={item.download_url}>Download {item.title}</a>}
          </article>
        ))}
        {error && <PublicLoadError message={error} retry={reload} />}
      </section>
    </PublicPageLayout>
  );
}
