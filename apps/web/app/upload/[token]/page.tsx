import type { Metadata } from "next";

import { UploadScreen } from "./upload-screen";

export const metadata: Metadata = {
  title: "העלאת מסמכים מאובטחת לתיק",
  description: "העלאת המסמכים שהמשרד ביקש, ישירות לתיק שלכם.",
  robots: { index: false, follow: false },
  // The link itself is the credential: it must not travel to other sites in a Referer header.
  referrer: "no-referrer",
};

export default async function UploadPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return <UploadScreen token={token} />;
}
