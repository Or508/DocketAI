import type { Metadata } from "next";

import { LegalFooter } from "@/app/(legal)/legal-footer";

import { DemoStart } from "./demo-start";

const WHATSAPP = "972547302757";
const WHATSAPP_TEXT = "היי, ראיתי את הדמו של DocFlow ואשמח לשמוע עוד";

export const metadata: Metadata = {
  title: "דמו חי — DocFlow",
};

export default function DemoPage() {
  return (
    <div className="flex min-h-screen flex-col">
      <main className="mx-auto w-full max-w-3xl flex-1 px-5 py-10">
        <p className="text-sm font-semibold text-tide">DocFlow</p>
        <h1 className="mt-2 text-3xl font-bold text-ink">דמו בלי הרשמה</h1>
        <p className="mt-2 text-sm">
          <a
            className="text-tide underline-offset-2 hover:underline"
            href={`https://wa.me/${WHATSAPP}?text=${encodeURIComponent(WHATSAPP_TEXT)}`}
          >
            דברו איתנו בוואטסאפ: 054-7302757
          </a>
        </p>
        <p className="mt-6 text-sm leading-6 text-ink">שלושה צעדים, בלי חשבון ובלי סיסמה. כל כניסה פותחת משרד פרטי משלה.</p>
        <ol className="mt-4 list-decimal space-y-2 pe-5 text-sm leading-6 text-ink">
          <li>פותחים תיק ומעלים את המסמכים.</li>
          <li>הפרטים נכנסים לטופס, ורואים מה עוד חסר.</li>
          <li>שולחים קישור לחתימה מהטלפון, ומקבלים עותק חתום.</li>
        </ol>
        <p className="mt-4 text-sm leading-6 text-ink">מה תראו: תיק אחד מוכן לחתימה, ושניים שעוד מחכים למסמכים מהלקוח.</p>
        <p className="mt-4 text-sm leading-6 text-mist">הדמו נמחק אחרי יממה. אין להעלות אליו מידע אמיתי.</p>
        <DemoStart />
      </main>
      <LegalFooter frame="max-w-3xl px-5" />
    </div>
  );
}
