"use client";
import Link from "next/link";
import { PublicPageLayout } from "@/components/public-site";
import { JournalIcon } from "@/components/journal-art";
import { useSubmissionOptions } from "@/lib/submission-options";
export default function SubmitPage() {
  const {options, error} = useSubmissionOptions();
  const body = "Title: \nManuscript type: \nArea of research: \nOther area: \nAbstract: \nKeywords: \nAffiliation: \n\nPlease attach your manuscript as PDF or DOCX. You will receive a link to confirm your draft and complete the submission checklist.";
  return <PublicPageLayout eyebrow="For authors" title="Submit your manuscript" activeHref="/submit" breadcrumb="Submit manuscript">
    <p className="public-reading">Choose how to start. Both routes lead to the same author checklist, editorial assessment and review process.</p>
    <div className="submission-option-grid"><section className="submission-option"><JournalIcon name="file" size={28}/><h2>Submit online</h2><p>Sign in to prepare your manuscript details, upload files and complete the required declarations.</p><Link className="button-link" href="/author">Open author workspace <JournalIcon name="arrow" /></Link><p className="small-copy">Use your invited author account. New authors can use email intake when available.</p></section>
    <section className="submission-option"><JournalIcon name="mail" size={28}/><h2>Start by email</h2><p>Email your manuscript and receive a private link to review an imported draft. Sending an email does not complete formal submission.</p>{options?.email_available && options.submission_email ? <><a className="button-link button-link--outline" href={`mailto:${options.submission_email}?subject=${encodeURIComponent("Manuscript submission")}&body=${encodeURIComponent(body)}`}>Compose submission email <JournalIcon name="arrow" /></a><p className="small-copy">{options.submission_email} · PDF or DOCX · Maximum email size {options.max_email_mb} MB.</p></> : <p className="notice-message" role="status">{error ? "Email availability could not be loaded. Please try again later." : options ? "Email intake is not yet configured. Existing authors can use the online workspace." : "Checking email submission availability…"}</p>}</section></div>
    <p>Before submitting, review the <Link href="/pages/author-guidelines">author guidelines</Link>, <Link href="/pages/publication-ethics">publication ethics</Link> and <Link href="/templates">manuscript templates</Link>.</p>
  </PublicPageLayout>;
}
