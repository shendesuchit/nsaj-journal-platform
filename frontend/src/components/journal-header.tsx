"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

import { HeaderAccount } from "@/components/header-account";
import { HeaderContext } from "@/components/header-context";
import { JournalIcon } from "@/components/journal-art";
import { isDemoContentEnabled } from "@/lib/demo-content";

const navigation = [
  { label: "About the journal", links: [["About NSAJ", "/pages/about"], ["Aims & scope", "/pages/aims-and-scope"], ["Editorial Board", "/editorial-board"], ["Publication ethics", "/pages/publication-ethics"], ["Editorial policies", "/pages/editorial-policies"], ["Corrections & retractions", "/pages/corrections-and-retractions"], ["Contact", "/#contact"]] },
  { label: "Explore research", links: [["Search published research", "/search"], ["Issues & archive", "/issues"], ["Calls for papers", "/calls-for-papers"]] },
  { label: "For authors", links: [["Submit a manuscript", "/submit"], ["Create author account", "/register"], ["Author guidelines", "/pages/author-guidelines"], ["Publishing process", "/publishing-process"], ["Templates & downloads", "/templates"], ["Fees & licensing", "/pages/fees-and-licensing"], ["Author workspace", "/author"]] },
] as const;

export function JournalHeader() {
  const pathname = usePathname() ?? "/";
  const root = useRef<HTMLElement>(null);
  const privatePage = /^\/(author|reviewer|editorial|admin)(\/|$)/.test(pathname);
  const accountPage = ["/sign-in", "/register", "/recover", "/accept-invitation", "/email-submission"].includes(pathname);

  useEffect(() => {
    root.current?.querySelectorAll("details[open]").forEach(item => item.removeAttribute("open"));
  }, [pathname]);

  useEffect(() => {
    const dismiss = (event: MouseEvent) => {
      if (root.current && !root.current.contains(event.target as Node)) root.current.querySelectorAll("details[open]").forEach(item => item.removeAttribute("open"));
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      const open = root.current?.querySelectorAll<HTMLDetailsElement>("details[open]");
      open?.forEach(item => { item.open = false; });
      open?.[0]?.querySelector<HTMLElement>("summary")?.focus();
    };
    document.addEventListener("click", dismiss);
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("click", dismiss); document.removeEventListener("keydown", escape); };
  }, []);

  function links() {
    return navigation.map(group => <details className="journal-nav-group" key={group.label}><summary>{group.label}<JournalIcon name="chevron" size={12} /></summary><div className="journal-nav-panel">{group.links.map(([label, href]) => <Link key={href} href={href} aria-current={pathname === href ? "page" : undefined}>{label}</Link>)}</div></details>);
  }

  return <>
    <div className="journal-utility"><div><span>Advancing ideas across disciplines.</span><span>{isDemoContentEnabled && <span className="journal-preview-flag">Design preview</span>}<Link href="/sign-in">Journal workspace <JournalIcon name="external" size={11} /></Link></span></div></div>
    <header ref={root} className={`brand-header journal-header${privatePage ? " journal-header--workspace" : ""}${accountPage ? " journal-header--account" : ""}`}>
      <div className="brand-header__inner">
        <Link className="wordmark" href="/"><img className="wordmark__image-mark" src="/nsaj-navbar-mark.png" alt="" aria-hidden="true" /><span className="wordmark__text"><span className="wordmark__name">Noble Scientific<br />Advances Journal</span><span className="wordmark__discipline">RESEARCH ACROSS DISCIPLINES</span></span></Link>
        {/* Journal identifiers are shown only after NSAJ verifies and approves them. */}
        {!privatePage && !accountPage && <nav className="journal-desktop-nav" aria-label="Public journal navigation">{links()}</nav>}
        <div className="brand-header__actions">
          {!accountPage && <HeaderContext />}
          {accountPage && <Link className="header-back-journal" href="/">Back to the journal <JournalIcon name="arrow" size={14} /></Link>}
          {!accountPage && <HeaderAccount />}
          {!privatePage && !accountPage && <details className="journal-mobile-nav"><summary aria-label="Journal menu"><JournalIcon name="menu" size={22} /></summary><nav aria-label="Mobile journal navigation">{links()}<Link href="/templates">Templates & downloads</Link><Link href="/author">Author workspace</Link><Link href="/sign-in">Account sign in</Link></nav></details>}
        </div>
      </div>
    </header>
  </>;
}
