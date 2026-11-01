import Link from "next/link";
import { JournalIcon, JournalMark } from "@/components/journal-art";
import { demoPreviewNotice, isDemoContentEnabled } from "@/lib/demo-content";

export function PublicSiteHeader({ activeHref }: { activeHref?: string }) {
  return isDemoContentEnabled ? <div className="demo-preview-banner" role="status">{demoPreviewNotice}</div> : null;
}

export function DemoBadge() {
  return <span className="demo-badge">Demo sample</span>;
}

export function PublicSiteFooter() {
  return <footer className="public-footer"><div className="public-footer__inner"><div className="journal-footer-grid"><div className="journal-footer-brand"><Link className="wordmark" href="/"><JournalMark className="wordmark__mark" /><span className="wordmark__name">Noble Scientific<br />Advances Journal</span></Link><p>A dedicated space for research across disciplines.</p></div><div><h2>The journal</h2><Link href="/pages/about">About NSAJ</Link><Link href="/pages/aims-and-scope">Aims & scope</Link><Link href="/editorial-board">Editorial Board</Link><Link href="/#contact">Contact</Link></div><div><h2>For researchers</h2><Link href="/pages/author-guidelines">Author guidelines</Link><Link href="/publishing-process">Publishing process</Link><Link href="/templates">Templates & downloads</Link><Link href="/calls-for-papers">Calls for papers</Link></div><div><h2>Explore & learn</h2><Link href="/search">Search research</Link><Link href="/issues">Issues & archive</Link><Link href="/pages/publication-ethics">Publication ethics</Link></div></div><div className="journal-footer-bottom"><p>© {new Date().getFullYear()} Noble Scientific Advances Journal.</p><span><Link href="/pages/fees-and-licensing">Fees & licensing</Link><Link href="/sign-in">Account sign in <JournalIcon name="external" size={12} /></Link></span></div></div></footer>;
}

export function PublicSiteChrome({ children, activeHref }: { children: React.ReactNode; activeHref?: string }) {
  return <div className="journal-shell"><PublicSiteHeader activeHref={activeHref} />{children}<PublicSiteFooter /></div>;
}

export function PublicPageLayout({ eyebrow = "Noble Scientific Advances Journal", title, activeHref, breadcrumb = "Journal pages", children }: { eyebrow?: string; title: string; activeHref?: string; breadcrumb?: string; children: React.ReactNode }) {
  const fullWidth = activeHref === "/search" || activeHref === "/issues";
  return <div className="journal-shell"><PublicSiteHeader activeHref={activeHref} /><div className={`public-page-grid${fullWidth ? " public-page-grid--wide" : ""}`}><main className="public-page-content" id="main-content" tabIndex={-1}><header className="public-page-heading"><nav className="public-breadcrumb" aria-label="Breadcrumb"><ol><li><Link href="/">Home</Link></li><li aria-current="page">{breadcrumb}</li></ol></nav><p className="public-page-heading__eyebrow">{eyebrow}</p><h1 id="public-page-title">{title}</h1></header>{children}</main>{!fullWidth && <aside className="public-author-sidebar"><div><p className="eyebrow">FOR RESEARCHERS</p><h2>A helpful place<br />to begin.</h2><nav aria-label="Researcher resources"><Link href="/pages/author-guidelines">Author guidelines <JournalIcon name="arrow" size={14} /></Link><Link href="/pages/aims-and-scope">Aims & scope <JournalIcon name="arrow" size={14} /></Link><Link href="/templates">Templates & downloads <JournalIcon name="arrow" size={14} /></Link><Link href="/publishing-process">Publishing process <JournalIcon name="arrow" size={14} /></Link></nav></div><div className="public-sidebar-callout"><JournalIcon name="book" size={25} /><h2>Your next chapter<br />starts here.</h2><p>Review the author guidance and prepare your contribution.</p><Link href="/author" className="button-link">Author workspace <JournalIcon name="arrow" size={14} /></Link></div></aside>}</div><PublicSiteFooter /></div>;
}

export function PublicLoadError({ message, retry }: { message: string; retry: () => void }) {
  return <div className="public-load-error"><p className="error-message" role="alert">{message}</p><button className="secondary-button" type="button" onClick={retry}>Try again</button></div>;
}
