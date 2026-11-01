import type { Metadata } from "next";

import "@fontsource-variable/inter";
import "@fontsource-variable/source-serif-4";
import "./globals.css";
import "@/components/public-content.css";
import "./journal-theme.css";
import "./interface-refinements.css";
import "./workflow-refinements.css";
import "@/components/manuscript-progress.css";
import "./journal-control.css";
import { ConfirmProvider } from "@/components/ui";
import { JournalHeader } from "@/components/journal-header";
import { WorkspaceNav } from "@/components/workspace-nav";

export const metadata: Metadata = {
  title: {
    default: "Noble Scientific Advances Journal",
    template: "%s | Noble Scientific Advances Journal",
  },
  description:
    "Explore published journal content and approved resources from the Noble Scientific Advances Journal.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" data-scroll-behavior="smooth">
      <body>
        <ConfirmProvider>
        <a className="skip-link" href="#main-content">
          Skip to content
        </a>
        <div className="site-masthead">
          <JournalHeader />
          <WorkspaceNav />
        </div>
        {children}
        </ConfirmProvider>
      </body>
    </html>
  );
}
