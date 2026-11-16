import { Button } from "@/components/ui/button";
import { israeliMobile, whatsAppUrl } from "@/lib/dispatch";

export function reminderMessage(clientName: string, formTitle: string) {
  const name = clientName.trim() || "לקוח";
  return `שלום ${name}, תזכורת ידידותית להשלמת החתימה הדיגיטלית על ${formTitle}. הטופס ממתין לחתימתך.`;
}

export function WhatsAppReminder({
  clientName,
  phone,
  formTitle,
  className,
  explain = false,
}: {
  clientName: string;
  phone: string;
  formTitle: string;
  className?: string;
  explain?: boolean;
}) {
  const mobile = israeliMobile(phone);
  if (!mobile) {
    return (
      <div className={className}>
        <Button type="button" className="w-full" disabled>
          תזכורת ב-WhatsApp
        </Button>
        {explain ? <p className="mt-2 text-sm text-clay">אין מספר נייד ישראלי בתיק, ולכן אי אפשר לפתוח את וואטסאפ.</p> : null}
      </div>
    );
  }
  return (
    <Button asChild className={className}>
      <a href={whatsAppUrl(mobile, reminderMessage(clientName, formTitle))} target="_blank" rel="noopener noreferrer">
        תזכורת ב-WhatsApp
      </a>
    </Button>
  );
}
