import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DocketAI",
  description: "Ingest a document bundle, find what is missing, fill the form, and sign.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="font-sans antialiased">{children}</body>
    </html>
  );
}
