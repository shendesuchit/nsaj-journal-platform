"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { JournalIcon } from "@/components/journal-art";

const accountPaths = new Set(["/sign-in", "/register", "/recover", "/accept-invitation", "/email-submission"]);

function isPublicJournalPath(pathname: string): boolean {
  return (
    pathname === "/" ||
    pathname === "/issues" ||
    pathname === "/search" ||
    pathname === "/calls-for-papers" ||
    pathname === "/editorial-board" ||
    pathname === "/publishing-process" || pathname === "/submit" ||
    pathname === "/templates" ||
    pathname === "/presentations" ||
    pathname.startsWith("/articles/") ||
    pathname.startsWith("/pages/")
  );
}

export function HeaderContext() {
  const pathname = usePathname() ?? "/";
  const privateWorkspace = /^\/(author|reviewer|editorial|admin)(\/|$)/.test(pathname);

  if (privateWorkspace) {
    return (
      <Link className="header-view-public" href="/">
        View public site
      </Link>
    );
  }

  if (!isPublicJournalPath(pathname) || accountPaths.has(pathname) || pathname === "/search") {
    return null;
  }

  return (
    <details className="header-search-popover"><summary aria-label="Search published articles"><JournalIcon name="search" size={19} /></summary><form
      className="header-public-search"
      action="/search"
      method="get"
      role="search"
      aria-label="Journal article search"
    >
      <label className="visually-hidden" htmlFor="header-public-search-query">
        Search published articles
      </label>
      <input
        id="header-public-search-query"
        name="q"
        type="search"
        minLength={2}
        placeholder="Search articles, authors, keywords"
      />
      <button type="submit">Search</button>
    </form></details>
  );
}
