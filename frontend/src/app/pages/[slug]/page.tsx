"use client";

import { use } from "react";
import { useEffect, useState } from "react";

import { AuthorDownloads } from "@/components/author-downloads";
import { DemoBadge, PublicLoadError, PublicPageLayout } from "@/components/public-site";
import { api, type ApiError } from "@/lib/api";
import {
  demoJournalPages,
  isDemoContentEnabled,
  type PublicJournalPage,
} from "@/lib/demo-content";
import { formatPublicDate } from "@/lib/public-format";

export default function JournalContentPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  const [page, setPage] = useState<PublicJournalPage | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    setPage(null);
    setError("");
    void api<PublicJournalPage>(`/public/pages/${encodeURIComponent(slug)}`)
      .then((data) => { if (active) setPage(data); })
      .catch((reason: ApiError) => {
        if (!active) return;
        const sample = demoJournalPages[slug];
        if (isDemoContentEnabled && reason.status === 404 && sample) setPage(sample);
        else setError("This approved journal page is not available.");
      });
    return () => { active = false; };
  }, [slug, attempt]);

  return (
    <PublicPageLayout
      eyebrow="Journal information"
      title={page?.title ?? (error ? "Journal information unavailable" : "Journal information")}
      activeHref={`/pages/${slug}`}
      breadcrumb={page?.title ?? "Journal information"}
    >
      {page ? (
        <article className="published-page-body public-reading">
          {page.demo && <DemoBadge />}
          {formatPublicDate(page.published_at) && <p className="public-card__meta">Published <time dateTime={page.published_at!}>{formatPublicDate(page.published_at)}</time></p>}
          <p>{page.body}</p>
          {slug === "author-guidelines" && <AuthorDownloads compact heading="Files for manuscript preparation" />}
        </article>
      ) : error ? (
        <PublicLoadError message={error} retry={() => setAttempt((value) => value + 1)} />
      ) : (
        <p className="notice-message" role="status">Loading approved journal information…</p>
      )}
    </PublicPageLayout>
  );
}
