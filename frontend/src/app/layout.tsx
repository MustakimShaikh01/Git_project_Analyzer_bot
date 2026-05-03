import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RepoAnalyzer — AI Code Intelligence",
  description:
    "Multi-tenant AI platform for semantic code search and RAG-powered repository understanding.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      </head>
      <body>{children}</body>
    </html>
  );
}
