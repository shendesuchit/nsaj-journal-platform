const paths: Record<string, React.ReactNode> = {
  mail: <><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 6 9 7 9-7"/></>,
  flask: <><path d="M9 3h6m-5 0v6L4 19a1 1 0 0 0 1 2h14a1 1 0 0 0 1-2L14 9V3M7 15h10"/></>,
  dna: <><path d="M6 2c0 9 12 11 12 20M18 2C18 11 6 13 6 22M7 5h10M9 9h6m-6 6h6M7 19h10"/></>,
  math: <><path d="M4 6h7M7.5 2.5v7M15 6h6M4 16l7 6m0-6-7 6m11-5h6m-6 4h6"/></>,
  layers: <><path d="m12 3 10 5-10 5L2 8l10-5Zm-10 9 10 5 10-5M2 16l10 5 10-5"/></>,
  paw: <><ellipse cx="5" cy="9" rx="2" ry="3"/><ellipse cx="10" cy="5" rx="2" ry="3"/><ellipse cx="16" cy="5" rx="2" ry="3"/><ellipse cx="21" cy="10" rx="2" ry="3"/><path d="M8 13c3-4 6-3 8 0 6 8 0 10-4 7-5 3-10 0-4-7Z"/></>,
  medical: <><path d="M9 3h6v6h6v6h-6v6H9v-6H3V9h6Z"/></>,
  compass: <><circle cx="12" cy="12" r="9"/><path d="m16 8-2 6-6 2 2-6 6-2Z"/></>,
  review: <><circle cx="9" cy="8" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3m1-15a3 3 0 0 1 0 6m2 3a5 5 0 0 1 3 5"/></>,
  revision: <><path d="M20 7v6h-6M4 17v-6h6"/><path d="M5 7a8 8 0 0 1 14 0M5 17a8 8 0 0 0 14 0"/></>,
  plus: <path d="M12 5v14M5 12h14"/>,
  close: <path d="m6 6 12 12M6 18 18 6"/>,
  calendar: <><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 11h18m-13 4h2m4 0h2"/></>,
  clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
  bell: <><path d="M5 9a7 7 0 0 1 14 0c0 7 3 7 3 8H2c0-1 3-1 3-8Zm4 12h6"/></>,
  megaphone: <><path d="m3 9 13-5v16L3 15V9Zm13-2h4v10h-4M6 16l2 6h4l-3-5"/></>,
  arrow: <path d="M4 12h15m-6-6 6 6-6 6" />,
  external: <><path d="M14 3h7v7m0-7L10 14M10 3H3v18h18v-7" /></>,
  search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4.5 4.5" /></>,
  atom: <><ellipse cx="12" cy="12" rx="10" ry="4" transform="rotate(-30 12 12)" /><ellipse cx="12" cy="12" rx="10" ry="4" transform="rotate(30 12 12)" /><ellipse cx="12" cy="12" rx="10" ry="4" transform="rotate(90 12 12)" /><circle cx="12" cy="12" r="1" fill="currentColor" /></>,
  engineering: <><path d="m12 3 9 5v9l-9 5-9-5V8l9-5Z" /><path d="m3 8 9 5 9-5M12 13v9M7 5.8l10 5.5v8.5" /></>,
  technology: <><rect x="5" y="5" width="14" height="14" rx="2" /><path d="M9 2v3m6-3v3m-6 14v3m6-3v3M2 9h3m-3 6h3m14-6h3m-3 6h3" /><rect x="9" y="9" width="6" height="6" rx="1" /></>,
  book: <><path d="M3 5c4-1 6 0 9 2 3-2 5-3 9-2v15c-4-1-6 0-9 2-3-2-5-3-9-2zM12 7v15" /><path d="m6 9 3 1m-3 3 3 1m6-4 3-1m-3 5 3-1" /></>,
  file: <><path d="M14 3H5v18h14V8l-5-5Z" /><path d="M14 3v5h5M8 12h8m-8 4h6" /></>,
  shield: <><path d="m12 3 9 4v6c0 5-9 9-9 9s-9-4-9-9V7l9-4Z" /><path d="m8 12 3 3 5-6" /></>,
  check: <path d="m5 12 4 4L19 6" />,
  download: <path d="M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4" />,
  lock: <><rect x="5" y="10" width="14" height="11" rx="2" /><path d="M8 10V6a4 4 0 0 1 8 0v4m-4 5v3" /></>,
  eye: <><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" /></>,
  eyeOff: <><path d="m3 3 18 18M9 5.5A11 11 0 0 1 12 5c6 0 10 7 10 7a19 19 0 0 1-4 4M6 6C3.5 8.3 2 12 2 12s4 7 10 7a12 12 0 0 0 5-1.2" /><path d="M10 10a3 3 0 0 0 4 4" /></>,
  chevron: <path d="m8 10 4 4 4-4" />,
  menu: <path d="M4 6h16M4 12h16M4 18h16" />,
};

export function JournalIcon({ name, size = 18, className = "" }: { name: keyof typeof paths; size?: number; className?: string }) {
  return <svg className={className} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] ?? paths.file}</svg>;
}

export function JournalMark({ className = "" }: { className?: string }) {
  return <svg className={className} width="44" height="44" viewBox="0 0 48 48" fill="none" aria-hidden="true"><path d="M6 10c7-1 12 1 18 5 6-4 11-6 18-5v27c-7-1-12 1-18 5-6-4-11-6-18-5V10Z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" /><path d="M24 15v27M12 17l6 2m-6 6 6 2m12-8 6-2m-6 10 6-2" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" /><circle cx="35" cy="8" r="4" fill="var(--teal, #487d82)" /><path d="M35 6v4m-2-2h4" stroke="white" strokeWidth="1" /></svg>;
}

export function ScientificWave({ dark = false, className = "" }: { dark?: boolean; className?: string }) {
  return <svg className={className} viewBox="0 0 500 300" fill="none" aria-hidden="true">{Array.from({ length: 45 }, (_, i) => {
    const d = Array.from({ length: 101 }, (_, x) => {
      const t = x / 100;
      const y = 145 + Math.sin(t * 5.3 + i * .055) * 62 + Math.cos(t * 8.1 + i * .08) * 32 + (i - 22) * 2.2;
      return `${x ? "L" : "M"}${x * 5},${y.toFixed(2)}`;
    }).join(" ");
    return <path key={i} d={d} stroke={dark ? i % 5 === 0 ? "#d6c49d" : "#91bfcd" : i % 4 === 0 ? "#a4b5a6" : "#7b9ba7"} strokeWidth=".8" opacity={.25 + i % 8 * .065} />;
  })}</svg>;
}

export function JournalCover() {
  return <div className="journal-cover-scene" role="img" aria-label="Noble Scientific Advances Journal cover design, with an abstract scientific wave"><div className="journal-cover-orbit" /><div className="journal-cover-back" /><div className="journal-cover"><div className="journal-cover__top"><span>NSAJ</span><span>IDEAS ACROSS DISCIPLINES</span></div><p className="journal-cover__title">Noble Scientific<br />Advances Journal</p><p className="journal-cover__subtitle">RESEARCH ACROSS DISCIPLINES</p><ScientificWave dark className="journal-cover__wave" /><div className="journal-cover__bottom"><span>CONNECTED KNOWLEDGE</span><span>JOURNAL COVER CONCEPT</span></div></div><div className="journal-cover-caption"><span><JournalIcon name="book" size={19} /></span><div><strong>A broader perspective.</strong><small>Connected ideas. New possibilities.</small></div></div></div>;
}
