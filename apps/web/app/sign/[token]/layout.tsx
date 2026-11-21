import { LegalFooter } from "@/app/(legal)/legal-footer";
import { PublicBrand } from "@/app/verify/public-brand";

export default function SignLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <PublicBrand />
      {children}
      <LegalFooter frame="max-w-3xl px-4" />
    </>
  );
}
