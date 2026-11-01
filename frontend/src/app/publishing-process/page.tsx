import type { Metadata } from "next";
import Link from "next/link";

import { AuthorDownloads } from "@/components/author-downloads";
import { PublicPageLayout } from "@/components/public-site";
import { PublicationJourney } from "@/components/publication-journey";

export const metadata: Metadata = {
  title: "Publishing process",
  description: "An overview of the manuscript journey at the Noble Scientific Advances Journal.",
};

export default function PublishingProcessPage() {
  return (
    <PublicPageLayout
      title="The publishing process"
      activeHref="/publishing-process"
      breadcrumb="Publishing process"
    >
      <p className="public-reading">
        This preview outlines the manuscript journey. Submissions are not open through this site. Final journal policies and operational details will be published before submissions open.
      </p>

      <PublicationJourney variant="detailed" />

      <AuthorDownloads compact heading="Files for authors" />

      <section className="process-privacy" aria-labelledby="process-privacy-title">
        <h2 id="process-privacy-title">What is visible to the public?</h2>
        <p>
          The public archive contains only articles and issues that have been explicitly published. Manuscripts, reviewer reports, reviewer identities, and editorial records are handled in private workspaces with access limited by role and record.
        </p>
        <p>
          Reviewer recommendations are kept separate from editorial decisions. An authorized editor records and communicates the journal’s decision.
        </p>
      </section>

      <p className="process-author-link">
        Preparing a manuscript? Start with the <Link href="/pages/author-guidelines">author guidelines</Link> and <Link href="/pages/aims-and-scope">journal scope</Link>.
      </p>
    </PublicPageLayout>
  );
}
