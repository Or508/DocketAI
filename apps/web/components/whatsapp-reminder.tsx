import { Button } from "@/components/ui/button";
import { israeliMobile, whatsAppUrl } from "@/lib/dispatch";

export function reminderMessage(clientName: string) {
  const name = clientName.trim() || "לקוח";
  return `שלום ${name}, תזכורת ידידותית להשלמת החתימה הדיגיטלית על טופס בל/6101. הטופס ממתין לחתימתך.`;
}

export function WhatsAppReminder({
  clientName,
  phone,
  className,
  explain = false,
}: {
  clientName: string;
  phone: string;
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
      <a href={whatsAppUrl(mobile, reminderMessage(clientName))} target="_blank" rel="noopener noreferrer">
        תזכורת ב-WhatsApp
      </a>
    </Button>
  );
}
