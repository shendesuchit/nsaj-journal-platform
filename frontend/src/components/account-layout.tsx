import Link from "next/link";
import type { ReactNode } from "react";
import { JournalIcon, ScientificWave } from "@/components/journal-art";

export function AccountLayout({ children }: { children: ReactNode }) {
  return <div className="account-layout"><aside className="account-introduction"><div className="account-introduction__top"><span className="eyebrow">NOBLE SCIENTIFIC ADVANCES JOURNAL</span><span className="account-emblem"><JournalIcon name="atom" size={28} /></span></div><h2>A considered space<br />for meaningful<br /><em>research.</em></h2><p>Your work, your reviews, your journal.<br />One focused workspace.</p><div className="account-introduction__art"><ScientificWave dark /></div><div className="account-introduction__bottom"><span>SCIENCE · ENGINEERING · TECHNOLOGY</span><Link href="/pages/about">Discover the journal <JournalIcon name="arrow" size={14} /></Link></div></aside><div className="account-layout__form">{children}</div></div>;
}
