import { Button } from "@/components/ui/button";
import { israeliMobile, whatsAppUrl } from "@/lib/dispatch";
import { applyOfficeTemplate, readOfficeSettings } from "@/lib/office-settings";
import { useOfficeSettings } from "@/lib/use-office-settings";

export function reminderMessage(clientName: string, formTitle: string) {
  const settings = readOfficeSettings();
  return applyOfficeTemplate(settings.reminderTemplate, { client_name: clientName, process_title: formTitle, link: "" }, settings);
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
  const settings = useOfficeSettings();
  const mobile = israeliMobile(phone);
  const text = applyOfficeTemplate(settings.reminderTemplate, { client_name: clientName, process_title: formTitle, link: "" }, settings);
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
      <a href={whatsAppUrl(mobile, text)} target="_blank" rel="noopener noreferrer">
        תזכורת ב-WhatsApp
      </a>
    </Button>
  );
}
