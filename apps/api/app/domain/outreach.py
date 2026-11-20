"""Pure rules for messages to clients: contact details, the WhatsApp link, the wording, and when reminders go out."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo

ISRAEL = ZoneInfo("Asia/Jerusalem")
_EMAIL = re.compile(r"^[^@\s<>\"',;]{1,64}@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9-]{1,63})+$")


def clean_email(raw: str | None) -> str | None:
    """A plain address, lower-cased, or None. No display names and nothing that could add a header."""
    if raw is None:
        return None
    value = raw.strip()
    if not value or len(value) > 254 or not _EMAIL.fullmatch(value):
        return None
    return value.lower()


def clean_phone(raw: str | None) -> str | None:
    """A mobile number as international digits for WhatsApp: 0501234567 → 972501234567. None if it is not one."""
    if raw is None:
        return None
    text = raw.strip()
    digits = re.sub(r"\D", "", text)
    if text.startswith("+") or text.startswith("00"):
        digits = digits[2:] if text.startswith("00") else digits
        return digits if 10 <= len(digits) <= 15 else None
    if digits.startswith("972"):
        return digits if len(digits) == 12 else None
    # An Israeli mobile: 05X and seven more digits.
    if re.fullmatch(r"05\d{8}", digits):
        return "972" + digits[1:]
    return None


def show_phone(phone: str) -> str:
    """972501234567 → 050-1234567 for the office's screen; other countries as +digits."""
    if phone.startswith("972") and len(phone) == 12:
        local = "0" + phone[3:]
        return f"{local[:3]}-{local[3:]}"
    return f"+{phone}"


def mask_email(email: str) -> str:
    name, _, domain = email.partition("@")
    return f"{name[:1]}***@{domain}"


def mask_phone(phone: str) -> str:
    return f"***{phone[-3:]}"


def whatsapp_url(phone: str, text: str) -> str:
    """A link that opens WhatsApp on the office's device with the message written and the client chosen."""
    return f"https://wa.me/{phone}?text={quote(text, safe='')}"


@dataclass(frozen=True)
class Wording:
    subject: str
    text: str
    button: str


def wording(purpose: str, kind: str, *, office: str, client: str | None, url: str, expires: datetime | None) -> Wording:
    """Hebrew, gender-neutral, short. The link is the only way in, so it is always in the message."""
    hello = f"שלום {client}," if client else "שלום,"
    until = f"\nהקישור אישי ובתוקף עד {expires.astimezone(ISRAEL):%d/%m/%Y %H:%M}." if expires else "\nהקישור אישי."
    if purpose == "intake":
        if kind == "reminder":
            subject = f"תזכורת: עדיין חסרים מסמכים בתיק אצל {office}"
            body = f"{hello}\nתזכורת: עדיין חסרים כמה מסמכים כדי להתקדם בתיק אצל {office}.\nאפשר להעלות אותם כאן, מהנייד או מהמחשב:\n{url}"
        else:
            subject = f"{office}: מסמכים לתיק שלך"
            body = f"{hello}\n{office} מבקשים להעלות כמה מסמכים לתיק.\nזה לוקח כמה דקות, מהנייד או מהמחשב:\n{url}"
        button = "להעלאת המסמכים"
    else:
        if kind == "reminder":
            subject = f"תזכורת: טופס מחכה לחתימה אצל {office}"
            body = f"{hello}\nתזכורת: הטופס שהכינו עבורך ב{office} עדיין מחכה לחתימה.\nאפשר לעבור עליו ולחתום כאן:\n{url}"
        else:
            subject = f"{office}: טופס מוכן לחתימה"
            body = f"{hello}\nהטופס שהכינו עבורך ב{office} מוכן.\nאפשר לעבור על הפרטים ולחתום כאן:\n{url}"
        button = "לצפייה ולחתימה"
    footer = "\n\nאם לא ציפית להודעה הזאת, אפשר להתעלם ממנה."
    return Wording(subject=subject, text=body + until + footer, button=button)


def reminder_at(
    first_sent_at: datetime,
    reminders_sent: int,
    schedule_days: list[int],
    *,
    start_hour: int,
    end_hour: int,
) -> datetime | None:
    """When the next reminder is due, in UTC, or None when the schedule is used up.

    A time outside the day's hours, or on Saturday, moves to the next allowed hour (Israel time).
    """
    if reminders_sent >= len(schedule_days):
        return None
    due = first_sent_at + timedelta(days=schedule_days[reminders_sent])
    return next_allowed(due, start_hour=start_hour, end_hour=end_hour)


def next_allowed(moment: datetime, *, start_hour: int, end_hour: int) -> datetime:
    local = moment.astimezone(ISRAEL)
    for _ in range(8):
        if local.weekday() == 5:  # Saturday
            local = (local + timedelta(days=1)).replace(hour=start_hour, minute=0, second=0, microsecond=0)
            continue
        if local.hour < start_hour:
            local = local.replace(hour=start_hour, minute=0, second=0, microsecond=0)
        elif local.hour >= end_hour:
            local = (local + timedelta(days=1)).replace(hour=start_hour, minute=0, second=0, microsecond=0)
            continue
        break
    return local.astimezone(ZoneInfo("UTC"))


def allowed_now(now: datetime, *, start_hour: int, end_hour: int) -> bool:
    return next_allowed(now, start_hour=start_hour, end_hour=end_hour) <= now
