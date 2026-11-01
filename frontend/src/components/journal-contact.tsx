"use client";
import { useSubmissionOptions } from "@/lib/submission-options";
export function JournalContact() {
  const {options} = useSubmissionOptions();
  return <div className="home-trust__contact"><h3>Contact</h3>{options?.contact_email ? <a href={`mailto:${options.contact_email}`}>{options.contact_email}</a> : <p>Verified journal contact details will appear here when configured.</p>}<div className="journal-metric"><span>Impact factor</span><strong aria-label="Not available">—</strong><small>Verified value not available</small></div></div>;
}
