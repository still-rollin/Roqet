import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Roqet — Semantic search for Rocq",
  description: "Find theorems, lemmas and definitions across Rocq/Coq libraries using natural language.",
  openGraph: {
    title: "Roqet",
    description: "Find theorems faster in Rocq/Coq",
    siteName: "Roqet",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
