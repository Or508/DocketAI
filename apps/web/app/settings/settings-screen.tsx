"use client";

import { useEffect, useState } from "react";

import { OfficeTopNav } from "@/components/OfficeTopNav";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  DEFAULT_OFFICE_SETTINGS,
  readOfficeSettings,
  resetOfficeSettings,
  writeOfficeSettings,
  type OfficeSettings,
} from "@/lib/office-settings";

export function SettingsScreen() {
  const [settings, setSettings] = useState<OfficeSettings>(DEFAULT_OFFICE_SETTINGS);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    setSettings(readOfficeSettings());
  }, []);

  function update(patch: Partial<OfficeSettings>) {
    setNotice(null);
    setSettings((current) => ({ ...current, ...patch }));
  }

  function save() {
    writeOfficeSettings(settings);
    setNotice("ההגדרות נשמרו.");
  }

  function reset() {
    resetOfficeSettings();
    setSettings(DEFAULT_OFFICE_SETTINGS);
    setNotice("הוחזרו ברירות המחדל.");
  }

  return (
    <main className="mx-auto min-h-screen max-w-3xl px-5 py-6 lg:px-10 lg:py-10">
      <OfficeTopNav />
      <header>
        <h1 className="text-3xl font-bold tracking-tight text-ink">הגדרות המשרד</h1>
        <p className="mt-3 text-mist">ההגדרות נשמרות בדפדפן הזה ומשמשות את הודעות הוואטסאפ, האימייל ופתיחת התיק המהירה.</p>
      </header>

      <form
        className="mt-8 grid gap-6"
        onSubmit={(event) => {
          event.preventDefault();
          save();
        }}
      >
        <section className="rounded-lg border border-ink/15 bg-white p-5">
          <h2 className="font-serif text-2xl">פרטי המשרד ומיתוג</h2>
          <label className="mt-4 block text-sm font-semibold" htmlFor="office-name">
            שם המשרד לתצוגה
          </label>
          <Input id="office-name" className="mt-2" value={settings.officeName} onChange={(event) => update({ officeName: event.target.value })} />
          <label className="mt-4 block text-sm font-semibold" htmlFor="office-phone">
            טלפון המשרד
          </label>
          <Input id="office-phone" className="mt-2" dir="ltr" value={settings.officePhone} onChange={(event) => update({ officePhone: event.target.value })} />
          <label className="mt-4 block text-sm font-semibold" htmlFor="office-email">
            דוא״ל לחזרה
          </label>
          <Input id="office-email" className="mt-2" dir="ltr" type="email" value={settings.replyEmail} onChange={(event) => update({ replyEmail: event.target.value })} />
          <label className="mt-4 block text-sm font-semibold" htmlFor="office-footer">
            חתימת תחתית
          </label>
          <textarea
            id="office-footer"
            className="mt-2 min-h-24 w-full rounded-md border border-ink/25 bg-white px-3 py-2"
            value={settings.signatureFooter}
            onChange={(event) => update({ signatureFooter: event.target.value })}
          />
        </section>

        <section className="rounded-lg border border-ink/15 bg-white p-5">
          <h2 className="font-serif text-2xl">תבניות הודעה חכמות (WhatsApp ו-Email)</h2>
          <p className="mt-2 text-sm text-mist">אפשר להשתמש ב־{"{client_name}"} {"{process_title}"} {"{link}"}.</p>
          <TemplateField
            id="template-signing"
            label="שליחת טופס לחתימה דיגיטלית"
            value={settings.signingTemplate}
            onChange={(signingTemplate) => update({ signingTemplate })}
          />
          <TemplateField
            id="template-reminder"
            label="תזכורת חתימה ידידותית"
            value={settings.reminderTemplate}
            onChange={(reminderTemplate) => update({ reminderTemplate })}
          />
          <TemplateField
            id="template-intake"
            label="בקשה להשלמת והעלאת מסמכים (קישור להעלאת מסמכים)"
            value={settings.intakeTemplate}
            onChange={(intakeTemplate) => update({ intakeTemplate })}
          />
        </section>

        <section className="rounded-lg border border-ink/15 bg-white p-5">
          <h2 className="font-serif text-2xl">העדפות עבודה ואוטומציה</h2>
          <label className="mt-4 flex items-start gap-3 text-sm font-semibold">
            <input type="checkbox" className="mt-1 h-4 w-4" checked={settings.autoLoadForm} onChange={(event) => update({ autoLoadForm: event.target.checked })} />
            <span>טעינת הטופס הריק אוטומטית בפתיחת תיק מהיר</span>
          </label>
          <label className="mt-3 flex items-start gap-3 text-sm font-semibold">
            <input
              type="checkbox"
              className="mt-1 h-4 w-4"
              checked={settings.showChecksumWarnings}
              onChange={(event) => update({ showChecksumWarnings: event.target.checked })}
            />
            <span>הצגת אזהרות ספרת ביקורת ונייד על כרטיסי השדות</span>
          </label>
        </section>

        {notice ? (
          <p className="text-sm font-semibold text-[#0d4a2e]" role="status">
            {notice}
          </p>
        ) : null}
        <div className="flex flex-wrap gap-2">
          <Button type="submit">שמור הגדרות ✓</Button>
          <Button type="button" variant="outline" onClick={reset}>
            אפס לברירת מחדל
          </Button>
        </div>
      </form>
    </main>
  );
}

function TemplateField({ id, label, value, onChange }: { id: string; label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="mt-4 block text-sm font-semibold" htmlFor={id}>
      {label}
      <textarea
        id={id}
        className="mt-2 min-h-24 w-full rounded-md border border-ink/25 bg-white px-3 py-2 font-normal"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}
