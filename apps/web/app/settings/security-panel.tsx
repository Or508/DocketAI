"use client";

import QRCode from "qrcode";
import { FormEvent, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError, api, type SecurityStatus } from "@/lib/api";

function securityMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return "הפעולה נכשלה. בדקו את החיבור ונסו שוב.";
  const text = error.message;
  if (text === "The current password is incorrect.") return "הסיסמה הנוכחית שגויה.";
  if (/at least \d+ characters/i.test(text)) return "הסיסמה החדשה קצרה מדי.";
  if (text === "The new password must differ from the current one.") return "הסיסמה החדשה חייבת להיות שונה מהנוכחית.";
  if (text === "The code is incorrect or has expired.") return "הקוד שגוי או שפג תוקפו.";
  if (/already on/i.test(text)) return "האימות הדו-שלבי כבר פעיל.";
  if (/is not on/i.test(text)) return "האימות הדו-שלבי כבוי.";
  if (/start the setup first/i.test(text)) return "יש להתחיל את ההפעלה לפני הזנת הקוד.";
  if (error.status === 502) return "לא ניתן להגיע לשירות המשרד.";
  return "הפעולה נכשלה.";
}

function SetupQr({ value }: { value: string }) {
  const [svg, setSvg] = useState("");
  useEffect(() => {
    let cancelled = false;
    void QRCode.toString(value, {
      type: "svg",
      margin: 1,
      width: 168,
      errorCorrectionLevel: "M",
      color: { dark: "#16130f", light: "#ffffff" },
    }).then((markup) => {
      if (!cancelled) setSvg(markup);
    });
    return () => {
      cancelled = true;
    };
  }, [value]);
  if (!svg) return null;
  return (
    <div
      className="h-[168px] w-[168px] rounded-md border border-ink/15 bg-white p-2 [&_svg]:h-full [&_svg]:w-full"
      role="img"
      aria-label="קוד QR לאפליקציית האימות"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}

function RecoveryCodes({ codes }: { codes: string[] }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    await navigator.clipboard.writeText(codes.join("\n"));
    setCopied(true);
  }

  return (
    <div className="mt-4 rounded-md border border-ink/15 bg-[#fbfbf9] p-4">
      <p className="text-sm font-semibold">שמרו את שמונת קודי השחזור. הם מוצגים פעם אחת בלבד.</p>
      <ul dir="ltr" className="mt-3 grid grid-cols-2 gap-2 text-center font-mono text-sm">
        {codes.map((code) => (
          <li key={code} className="rounded-md border border-line bg-white px-2 py-1">
            {code}
          </li>
        ))}
      </ul>
      <Button type="button" variant="outline" className="mt-3" onClick={() => void copy()}>
        {copied ? "הועתקו" : "העתקה"}
      </Button>
    </div>
  );
}

export function SecurityPanel() {
  const [status, setStatus] = useState<SecurityStatus | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordNotice, setPasswordNotice] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [setup, setSetup] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [setupCode, setSetupCode] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);
  const [mfaError, setMfaError] = useState<string | null>(null);
  const [mfaBusy, setMfaBusy] = useState(false);
  const [confirmPassword2, setConfirmPassword2] = useState("");
  const [confirmCode, setConfirmCode] = useState("");

  useEffect(() => {
    let cancelled = false;
    api
      .security()
      .then((next) => {
        if (!cancelled) setStatus(next);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setLoadError(securityMessage(reason));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const minLength = status?.min_password_length ?? 12;

  async function changePassword(event: FormEvent) {
    event.preventDefault();
    setPasswordNotice(null);
    setPasswordError(null);
    if (newPassword.length < minLength) {
      setPasswordError(`הסיסמה החדשה חייבת להיות באורך של לפחות ${minLength} תווים.`);
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError("הסיסמאות אינן תואמות.");
      return;
    }
    setPasswordBusy(true);
    try {
      await api.changePassword(currentPassword, newPassword);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setPasswordNotice("הסיסמה הוחלפה. שאר המכשירים נותקו.");
    } catch (reason) {
      setPasswordError(securityMessage(reason));
    } finally {
      setPasswordBusy(false);
    }
  }

  async function startSetup() {
    setMfaError(null);
    setCodes(null);
    setMfaBusy(true);
    try {
      const next = await api.mfaSetup();
      setSetup(next);
      setSetupCode("");
    } catch (reason) {
      setMfaError(securityMessage(reason));
    } finally {
      setMfaBusy(false);
    }
  }

  async function enable(event: FormEvent) {
    event.preventDefault();
    setMfaError(null);
    setMfaBusy(true);
    try {
      const confirmed = await api.mfaEnable(setupCode.trim());
      setCodes(confirmed.recovery_codes);
      setSetup(null);
      setSetupCode("");
      setStatus((current) =>
        current ? { ...current, mfa_enabled: true, recovery_codes_left: confirmed.recovery_codes.length } : current,
      );
    } catch (reason) {
      setMfaError(securityMessage(reason));
    } finally {
      setMfaBusy(false);
    }
  }

  async function disable(event: FormEvent) {
    event.preventDefault();
    setMfaError(null);
    setMfaBusy(true);
    try {
      await api.mfaDisable(confirmPassword2, confirmCode.trim());
      setConfirmPassword2("");
      setConfirmCode("");
      setCodes(null);
      setStatus((current) => (current ? { ...current, mfa_enabled: false, recovery_codes_left: 0 } : current));
    } catch (reason) {
      setMfaError(securityMessage(reason));
    } finally {
      setMfaBusy(false);
    }
  }

  async function renew() {
    setMfaError(null);
    setMfaBusy(true);
    try {
      const renewed = await api.mfaRecoveryCodes(confirmPassword2, confirmCode.trim());
      setCodes(renewed.recovery_codes);
      setConfirmPassword2("");
      setConfirmCode("");
      setStatus((current) => (current ? { ...current, recovery_codes_left: renewed.recovery_codes.length } : current));
    } catch (reason) {
      setMfaError(securityMessage(reason));
    } finally {
      setMfaBusy(false);
    }
  }

  return (
    <div className="mt-8 grid gap-6">
      {loadError ? (
        <p className="text-sm font-medium text-clay" role="alert">
          {loadError}
        </p>
      ) : null}

      <section className="rounded-lg border border-ink/15 bg-white p-5">
        <h2 className="font-serif text-2xl">החלפת סיסמה</h2>
        <form className="mt-4 grid gap-4" onSubmit={(event) => void changePassword(event)}>
          <label className="block text-sm font-semibold" htmlFor="current-password">
            סיסמה נוכחית
            <Input
              id="current-password"
              className="mt-2"
              type="password"
              autoComplete="current-password"
              value={currentPassword}
              onChange={(event) => setCurrentPassword(event.target.value)}
              required
            />
          </label>
          <label className="block text-sm font-semibold" htmlFor="new-password">
            סיסמה חדשה
            <Input
              id="new-password"
              className="mt-2"
              type="password"
              autoComplete="new-password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              required
              minLength={minLength}
            />
          </label>
          <p className="text-xs text-mist">לפחות {minLength} תווים.</p>
          <label className="block text-sm font-semibold" htmlFor="confirm-password">
            אימות הסיסמה החדשה
            <Input
              id="confirm-password"
              className="mt-2"
              type="password"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              required
            />
          </label>
          {passwordError ? (
            <p className="text-sm font-medium text-clay" role="alert">
              {passwordError}
            </p>
          ) : null}
          {passwordNotice ? (
            <p className="text-sm font-semibold text-[#0d4a2e]" role="status">
              {passwordNotice}
            </p>
          ) : null}
          <Button type="submit" disabled={passwordBusy}>
            {passwordBusy ? "מעדכנים…" : "החלפת סיסמה"}
          </Button>
        </form>
      </section>

      <section className="rounded-lg border border-ink/15 bg-white p-5">
        <h2 className="font-serif text-2xl">אימות דו-שלבי</h2>
        {status ? (
          <p className="mt-2 text-sm text-mist">
            {status.mfa_enabled
              ? `פעיל. נותרו ${status.recovery_codes_left} קודי שחזור.`
              : "כבוי. בכניסה נדרשות רק דוא״ל וסיסמה."}
          </p>
        ) : null}
        {mfaError ? (
          <p className="mt-3 text-sm font-medium text-clay" role="alert">
            {mfaError}
          </p>
        ) : null}
        {codes ? <RecoveryCodes codes={codes} /> : null}

        {status && !status.mfa_enabled && !setup ? (
          <Button type="button" className="mt-4" disabled={mfaBusy} onClick={() => void startSetup()}>
            {mfaBusy ? "מכינים…" : "הפעלת אימות דו-שלבי"}
          </Button>
        ) : null}

        {setup ? (
          <form className="mt-4 grid gap-4" onSubmit={(event) => void enable(event)}>
            <p className="text-sm">סרקו את הקוד באפליקציית האימות, או הקלידו את המפתח.</p>
            <SetupQr value={setup.otpauth_uri} />
            <p dir="ltr" className="font-mono text-sm">
              {setup.secret}
            </p>
            <label className="block text-sm font-semibold" htmlFor="setup-code">
              קוד מאפליקציית האימות
              <Input
                id="setup-code"
                className="mt-2"
                dir="ltr"
                inputMode="numeric"
                autoComplete="one-time-code"
                value={setupCode}
                onChange={(event) => setSetupCode(event.target.value)}
                required
              />
            </label>
            <Button type="submit" disabled={mfaBusy}>
              {mfaBusy ? "מפעילים…" : "אישור והפעלה"}
            </Button>
          </form>
        ) : null}

        {status?.mfa_enabled ? (
          <form className="mt-4 grid gap-4" onSubmit={(event) => void disable(event)}>
            <label className="block text-sm font-semibold" htmlFor="mfa-password">
              סיסמה
              <Input
                id="mfa-password"
                className="mt-2"
                type="password"
                autoComplete="current-password"
                value={confirmPassword2}
                onChange={(event) => setConfirmPassword2(event.target.value)}
                required
              />
            </label>
            <label className="block text-sm font-semibold" htmlFor="mfa-code">
              קוד מאפליקציית האימות או קוד שחזור
              <Input
                id="mfa-code"
                className="mt-2"
                dir="ltr"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={9}
                value={confirmCode}
                onChange={(event) => setConfirmCode(event.target.value)}
                required
              />
            </label>
            <div className="flex flex-wrap gap-2">
              <Button type="submit" variant="danger" disabled={mfaBusy}>
                כיבוי האימות הדו-שלבי
              </Button>
              <Button type="button" variant="outline" disabled={mfaBusy} onClick={() => void renew()}>
                חידוש קודי שחזור
              </Button>
            </div>
          </form>
        ) : null}
      </section>
    </div>
  );
}
