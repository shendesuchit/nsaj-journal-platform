"use client";

import { researchAreas, researchAreaLabel } from "@/lib/research-areas";
import Link from "next/link";
import { useEffect, useState } from "react";

import { DemoBadge, PublicLoadError, PublicPageLayout } from "@/components/public-site";
import { api } from "@/lib/api";
import { type PublicSearchResult } from "@/lib/demo-content";

export default function SearchResults({ initialQuery, initialDiscipline = "" }: { initialQuery: string; initialDiscipline?: string }) {
  const query = initialQuery.trim();
  const discipline = researchAreas.some(area => area.value === initialDiscipline) ? initialDiscipline : "";
  const canSearch = query.length >= 2 || !!discipline;
  const [items, setItems] = useState<PublicSearchResult[]>([]);
  const [loading, setLoading] = useState(canSearch);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!canSearch) return;
    let active = true;
    setLoading(true);
    setError("");
    void api<{ items: PublicSearchResult[] }>(`/public/search?q=${encodeURIComponent(query)}${discipline ? `&discipline=${encodeURIComponent(discipline)}` : ""}`)
      .then((data) => { if (active) setItems(data.items); })
      .catch(() => { if (active) setError("Published content search is unavailable."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [query, discipline, canSearch, attempt]);

  return (
    <PublicPageLayout eyebrow="Published content" title="Search articles" activeHref="/search" breadcrumb="Search">
      <form className="public-search-form" action="/search" method="get" role="search" aria-label="Search articles" id="article-search">
        <label htmlFor="search-query">Title, author, abstract, or keyword</label>
        <div>
          <input id="search-query" type="search" name="q" maxLength={200} defaultValue={initialQuery} aria-describedby="search-help" />
          <button className="button-link" type="submit">Search</button>
        </div>
        <label htmlFor="search-discipline">Area of research</label><select id="search-discipline" name="discipline" defaultValue={discipline}><option value="">All areas</option>{researchAreas.map(area => <option key={area.value} value={area.value}>{area.label}</option>)}</select>
        <p id="search-help">Enter at least two characters or select an area. Search includes published articles only.</p>
      </form>
      {!query && <p className="notice-message">Search published research by title, author, topic, or keyword.</p>}
      {query.length === 1 && <p className="notice-message" role="status">Enter at least two characters to search published articles.</p>}
      {loading && <p className="notice-message" role="status">Searching published articles...</p>}
      {canSearch && !loading && !error && <p className="public-result-summary" role="status">{items.length ? `${items.length} ${items.length === 1 ? "result" : "results"} shown for "${query || researchAreaLabel(discipline)}".` : `No published articles matched "${query || researchAreaLabel(discipline)}".`}{items.some((item) => item.demo) && " Results include fictional demo samples."}</p>}
      {!loading && !error && items.map((item) => <article className="public-search-result" key={item.slug}>
        {item.demo && <DemoBadge />}
        <h2><Link href={`/articles/${encodeURIComponent(item.slug)}`}>{item.title}</Link></h2>
        <p className="public-article__authors">{item.authors.map((author) => author.full_name).join(", ")}</p>
        <p>{item.abstract.slice(0, 280)}{item.abstract.length > 280 ? "..." : ""}</p>
        {item.doi && <p className="public-card__meta"><strong>DOI:</strong> {item.doi}</p>}
      </article>)}
      {error && <PublicLoadError message={error} retry={() => setAttempt((value) => value + 1)} />}
    </PublicPageLayout>
  );
}
