"use client";

import { researchAreaLabel } from "@/lib/research-areas";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { DemoBadge, PublicLoadError, PublicPageLayout } from "@/components/public-site";
import { api, type ApiError } from "@/lib/api";
import { demoArticle, isDemoContentEnabled, type PublicArticle } from "@/lib/demo-content";
import { formatPublicDate as formatDate } from "@/lib/public-format";

export default function ArticlePage() {
  const params = useParams<{ slug: string }>();
  const [article, setArticle] = useState<PublicArticle | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    setArticle(null);
    setError("");
    if (params.slug) {
      void api<PublicArticle>(`/public/articles/${encodeURIComponent(params.slug)}`)
        .then((data) => { if (active) setArticle(data); })
        .catch((reason: ApiError) => {
          if (!active) return;
          if (
            isDemoContentEnabled &&
            reason.status === 404 &&
            params.slug === demoArticle.slug
          ) {
            setArticle(demoArticle);
          } else {
            setError("This published article is unavailable.");
          }
        });
    }
    return () => { active = false; };
  }, [params.slug, attempt]);

  return (
    <PublicPageLayout
      eyebrow={article?.demo ? "Demo article" : "Published article"}
      title={article?.title ?? (error ? "Article unavailable" : "Published article")}
      activeHref="/issues"
      breadcrumb="Article"
    >
      {error ? <PublicLoadError message={error} retry={() => setAttempt((value) => value + 1)} /> : !article ? (
        <p className="notice-message" role="status">Loading published article…</p>
      ) : (
        <article className="public-article">
          {article.demo && <DemoBadge />}
          {article.publication_notice && (
            <p className="draft-warning" role="status">
              {article.publication_notice.type.replaceAll("_", " ")}: {article.publication_notice.statement}
            </p>
          )}
          <section className="public-article__byline" aria-labelledby="article-authors-title">
            <h2 className="visually-hidden" id="article-authors-title">Authors</h2>
            <ol className="public-author-list">
              {article.authors.map((author, index) => (
                <li key={`${author.full_name}-${index}`}>
                  <strong>{author.full_name}</strong>
                  {author.affiliation && <span>{author.affiliation}</span>}
                  {author.orcid && <span>ORCID: {author.orcid}</span>}
                </li>
              ))}
            </ol>
            <p className="public-article__metadata">
              {[article.volume && `Volume ${article.volume.number} (${article.volume.year})`, article.issue && `Issue ${article.issue.number}`, formatDate(article.published_at) && `Published ${formatDate(article.published_at)}`]
                .filter(Boolean).join(" · ")}
            </p>
            {article.manuscript_reference && <p><strong>Paper ID:</strong> {article.manuscript_reference}</p>}
            {article.discipline && <p><strong>Area of research:</strong> {researchAreaLabel(article.discipline, article.discipline_other)}</p>}
            {article.manuscript_type && <p><strong>Article type:</strong> {article.manuscript_type.replaceAll("_", " ")}</p>}
            {article.doi && <p><strong>DOI:</strong> <a href={`https://doi.org/${article.doi}`}>{article.doi}</a></p>}
            {article.license && <p><strong>License:</strong> {article.license}</p>}
          </section>
          <div className="public-article__reading-grid">
          <section className="public-article__summary" aria-labelledby="article-abstract-title">
            <h2 id="article-abstract-title">Abstract</h2>
            <p className="public-article__abstract">{article.abstract}</p>
            {article.keywords.length > 0 && <p><strong>Keywords:</strong> {article.keywords.join(", ")}</p>}
          </section>
          <aside className="public-article__actions" aria-labelledby="article-citation-title">
            {article.file_url && <p><a className="button-link" href={article.file_url}>Download published article</a></p>}
            <h2 id="article-citation-title">Citation</h2>
            <p className="public-article__citation">{article.citation}</p>
            <div className="public-card__links">
              {!article.demo && <a href={`/api/v1/public/articles/${encodeURIComponent(article.slug)}/citation.ris`}>Download citation (RIS)</a>}
            </div>
          </aside>
          </div>
        </article>
      )}
    </PublicPageLayout>
  );
}
