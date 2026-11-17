import { PublicBrand } from "@/app/verify/public-brand";

export default function SignLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <PublicBrand />
      {children}
    </>
  );
}
