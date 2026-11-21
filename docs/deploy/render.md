# העלאה לפרודקשן ב-Render

המדריך מעלה את DocketFlow לשלושה שירותים שמנהלים מהדפדפן:

| מה | איפה | אזור |
|---|---|---|
| האתר, ה-API, תור העבודה ומסד הנתונים | **Render**, מוקם כולו מהקובץ `render.yaml` | פרנקפורט |
| קבצי התיקים | **Cloudflare R2** (תואם S3) | תחום שיפוט: האיחוד האירופי |
| מיילים | **Resend** (SMTP) | אירלנד (eu-west-1) |
| דומיין ו-DNS | **Cloudflare** | |

כל המידע של המשרדים נשאר באיחוד האירופי. צריך לציין את זה במדיניות הפרטיות. העברת מידע מישראל לאיחוד מותרת בדרך כלל,
אבל זה משפט לעו"ד לאשר. קריאת AI (אם מופעלת) שולחת טקסט של מסמכים לספק ה-AI בארה"ב, וכל משרד יכול לכבות אותה בהגדרות.

השרת מסרב לעלות עם הגדרות פיתוח (`ENVIRONMENT=production`). אם חסר משהו, הלוג של `docketflow-api` אומר בדיוק מה.

סימון: ✋ = פעולה שלך באתר של השירות. ⌨️ = פקודה.
המדריך ל-AWS ([aws-tel-aviv.md](aws-tel-aviv.md)) נשאר כחלופה.

## 0. לפני הכל: הקוד ב-GitHub ✋
Render בונה מהמאגר ב-GitHub, מה-branch הראשי (`main`) כברירת מחדל. העבודה צריכה להיות committed, pushed וממוזגת ל-`main`
(או לבחור ב-Render branch אחר בשלב 5).

## 1. חשבונות ✋
1. **Render** (render.com): הרשמה עם GitHub, ואישור גישה למאגר. מוסיפים אמצעי תשלום (Billing).
2. **Cloudflare** (cloudflare.com): הרשמה. MFA בחשבון.
3. **Resend** (resend.com): הרשמה. MFA בחשבון.
4. בכל השלושה: מפעילים אימות דו-שלבי. אלה המפתחות לכל המידע של הלקוחות.

## 2. דומיין ✋
- **`.com`**: קונים ישירות ב-Cloudflare → Domain Registration. מחיר עלות, וה-DNS כבר שם.
- **`.co.il`**: קונים אצל רשם ישראלי, ואז ב-Cloudflare → Add a site → מקבלים שני nameservers ומעדכנים אותם אצל הרשם.
  ההחלפה לוקחת בין שעה ליום.

בהמשך המדריך: `example.co.il` = הדומיין שלך, והאתר יהיה `app.example.co.il`.

## 3. קבצים: Cloudflare R2 ✋
1. Cloudflare → R2 → מפעילים (יש מכסה חינמית, אבל נדרש אמצעי תשלום).
2. Create bucket: שם `docketflow-files`. ב-**Location** בוחרים **Specify jurisdiction → European Union**.
3. R2 → **Manage API tokens** → Create API token:
   - Permissions: **Object Read & Write**
   - Specify bucket: רק `docketflow-files`
4. שומרים במנהל סיסמאות את שלושת הערכים שמוצגים פעם אחת: **Access Key ID**, **Secret Access Key**, ואת **ה-endpoint של
   ה-jurisdiction האירופי** (נראה כמו `https://<מספר>.eu.r2.cloudflarestorage.com`).

> לפי מה שאני יודע R2 לא שומר גרסאות קודמות של קבצים, בשונה מ-S3. המערכת עצמה לא דורסת קבצים חתומים, אבל כדאי לתכנן גיבוי
> תקופתי של ה-bucket לפני שיש הרבה משרדים.

## 4. מיילים: Resend ✋
1. Resend → Domains → Add domain: `example.co.il` (או תת-דומיין כמו `mail.example.co.il`). Region: **Ireland (eu-west-1)**.
2. Resend מציג רשומות DNS (DKIM, SPF, MX). אם הדומיין ב-Cloudflare, יש כפתור שמוסיף אותן אוטומטית. אחרת מוסיפים ידנית
   ב-Cloudflare → DNS. לוחצים Verify. זה לוקח מכמה דקות עד שעה.
3. ב-Cloudflare → DNS מוסיפים רשומת DMARC: TXT בשם `_dmarc`, ערך `v=DMARC1; p=none; rua=mailto:<המייל שלך>`.
4. Resend → API Keys → Create: הרשאה **Sending access**, דומיין: שלך. שומרים את המפתח (מתחיל ב-`re_`).

## 5. השרתים: Render Blueprint ✋
1. Render → **New → Blueprint** → בוחרים את המאגר. Render קורא את `render.yaml` ומראה מה ייווצר:
   `docketflow-web`, `docketflow-api`, `docketflow-worker`, `docketflow-redis`, `docketflow-db`, ושתי קבוצות הגדרות.
2. בודקים את המחיר שמוצג. ה-API וה-worker על 2GB, כי קריאת PDF צריכה זיכרון. אפשר להקטין אחר כך.
   לדמו ציבורי מספיקות תוכניות קטנות יותר: קריאת המסמכים כבויה במשרד הדמו, אז אין צורך בזיכרון של קריאת PDF.
3. **Apply**.

ה-API וה-worker **ייכשלו בעלייה הראשונה**. זה צפוי: חסרים להם הערכים של שלב 6, והשרת מסרב לעלות בלעדיהם.

## 6. ההגדרות הסודיות ✋
Render → **Environment Groups → `docketflow-secrets`** → Add Environment Variable, לכל אחד מאלה:

| מפתח | ערך |
|---|---|
| `PUBLIC_WEB_URL` | `https://app.example.co.il` (לפני שיש דומיין: הכתובת `https://docketflow-web.onrender.com`) |
| `EMAIL_FROM` | כתובת על הדומיין המאומת ב-Resend, למשל `office@example.co.il` |
| `SMTP_PASSWORD` | מפתח ה-API של Resend (`re_...`) |
| `S3_BUCKET` | `docketflow-files` |
| `S3_ENDPOINT_URL` | ה-endpoint האירופי מ-R2 |
| `S3_ACCESS_KEY_ID` | מ-R2 |
| `S3_SECRET_ACCESS_KEY` | מ-R2 |
| `ANTHROPIC_API_KEY` | אופציונלי: בלעדיו המסמכים מסווגים ידנית |

**חשוב:** בקבוצה כבר יש `MFA_SECRET_KEY` שנוצר אוטומטית. **מעתיקים אותו למנהל סיסמאות.** בלעדיו אי אפשר לפתוח את האימות
הדו-שלבי של העובדים ואת קישורי התזכורות, ואין דרך לשחזר אותו.

Save, ואז בכל אחד מ-`docketflow-api`, `docketflow-worker`, `docketflow-web`: **Manual Deploy → Deploy latest commit**.
ה-API מריץ את מיגרציות מסד הנתונים בכל עלייה, לפני שהוא מקבל בקשות.

## דמו ציבורי
בקבוצה `docketflow-config` יש `DEMO_MODE`. ברירת המחדל היא `false`, והכתובת `/demo` לא פותחת משרד.
כדי להציג את המערכת בלי הרשמה, משנים את הערך ל-`true` ופורסים מחדש את ה-API. כל כניסה פותחת משרד פרטי שנמחק אחרי יממה.
המותג בדמו הוא DocFlow, והפנייה היא לוואטסאפ `972547302757`. כתובת `*.onrender.com` מספיקה להתחלה, לפני שיש דומיין.

## 7. הדומיין על האתר ✋
1. Render → `docketflow-web` → Settings → **Custom Domains** → Add: `app.example.co.il`.
2. Cloudflare → DNS → Add record: **CNAME**, שם `app`, יעד `docketflow-web.onrender.com`,
   **Proxy status: DNS only (ענן אפור)**. ענן כתום מוסיף עוד שכבת proxy ומבלבל את זיהוי כתובת המבקר.
3. חוזרים ל-Render ולוחצים Verify. התעודה (HTTPS) מונפקת לבד תוך כמה דקות.
4. אם `PUBLIC_WEB_URL` עדיין על onrender.com: מעדכנים ל-`https://app.example.co.il` ופורסים מחדש את ה-API וה-worker.

## 8. מנהל המשרד הראשון ⌨️
Render → `docketflow-api` → **Shell**:
```bash
python -m app.cli create-user --organization "<שם המשרד>" --email <המייל שלו> --display-name "<השם שלו>"
```
הפקודה מבקשת סיסמה (12 תווים לפחות). את שאר העובדים הוא מזמין מתוך המערכת, בהגדרות → צוות המשרד.

## 9. בדיקות אחרי העלייה
- [ ] `https://app.example.co.il` נפתח עם מנעול.
- [ ] כניסה עם המנהל, והפעלת אימות דו-שלבי בהגדרות → אבטחה.
- [ ] הזמנת עובד: המייל מגיע (לא לספאם), הקישור עובד, העובד נכנס.
- [ ] "שכחתי סיסמה": המייל מגיע.
- [ ] תיק לדוגמה: העלאת קובץ (מופיע ב-R2 → `docketflow-files`), שליחת קישור ללקוח, חתימה, הורדת ה-PDF החתום.
- [ ] **כתובת המבקר:** בתעודת החתימה של תיק הבדיקה מופיעה כתובת IP. היא צריכה להיות הכתובת שלך (בודקים ב-whatismyip.com).
      אם מופיעה כתובת של Cloudflare (מתחילה למשל ב-104. או 172.), תגיד לי.
- [ ] **קובץ גדול:** העלאה של PDF בגודל 15–20MB. אם מתקבלת שגיאה 413, ל-Render יש מגבלת גודל שלא מתועדת. תגיד לי, ונקטין את המגבלה באפליקציה כך שתתאים.

## 10. שוטף
- **עדכון גרסה:** כל push ל-`main` נפרס לבד (`autoDeployTrigger: commit`, ברירת המחדל).
- **גיבויים:** Render Postgres בתוכנית בתשלום מגבה לבד. בודקים בלשונית **Recovery** של `docketflow-db` כמה ימים אחורה אפשר לשחזר.
  פעם בחודש כדאי לנסות שחזור למסד חדש, לוודא שעובד, ולמחוק.
- **לוגים ושגיאות:** Render → כל שירות → Logs. כדאי להגדיר ב-Render → Notifications התראה במייל על deploy שנכשל ועל שירות שנפל.

## לפני שמכניסים מידע אמיתי של לקוחות
- מדיניות פרטיות, תנאי שימוש והסכם עיבוד מידע מול כל משרד. כולל: אחסון באיחוד האירופי, ושקריאת AI שולחת טקסט לספק בארה"ב.
- בדיקת חדירות חיצונית, ובדיקה של נוסח תעודת החתימה ע"י עו"ד.
