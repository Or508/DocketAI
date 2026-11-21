# העלאה לפרודקשן ב-AWS תל אביב

המדריך מעלה את DocketFlow לשרת אחד ב-AWS באזור תל אביב (`il-central-1`). המידע של הלקוחות נשאר בישראל.
הוא מתאים לפיילוט של כמה משרדים. כשיהיו עשרות משרדים, עוברים לכמה שרתים מאחורי Load Balancer.

| רכיב | שירות AWS | למה |
|---|---|---|
| האתר וה-API | EC2 אחד עם Docker Compose (`deploy/docker-compose.prod.yml`) | פשוט לתחזוקה. רק Caddy פתוח לאינטרנט, והוא מנפיק HTTPS לבד |
| מסד הנתונים | RDS PostgreSQL 16 | גיבוי יומי אוטומטי, הצפנה, ושחזור לכל נקודת זמן |
| קבצי התיקים | S3 פרטי | גרסאות קבצים והצפנה. לא נמחק עם השרת |
| מיילים | SES דרך ה-API | בתל אביב אין ל-SES נקודת SMTP, לכן השרת שולח דרך ה-API עם התפקיד (IAM) של השרת, בלי סיסמת מייל |

השרת מסרב לעלות עם הגדרות פיתוח (`ENVIRONMENT=production`): SQLite, קבצים מקומיים, מיילים לקובץ,
כתובת בלי https, או בלי `MFA_SECRET_KEY`. אם חסר משהו, השגיאה בלוג אומרת בדיוק מה.

סימון: ✋ = פעולה שלך בקונסולה של AWS או אצל רשם הדומיין. ⌨️ = פקודה בשרת.

## 1. חשבון AWS ✋
1. פותחים חשבון, ומפעילים MFA למשתמש הראשי (root). לא עובדים איתו ביום-יום: יוצרים משתמש IAM עם הרשאות מנהל, וגם לו MFA.
2. אזור תל אביב צריך הפעלה ידנית: Account → AWS Regions → Israel (Tel Aviv) → Enable. ההפעלה לוקחת כמה דקות.
3. מגדירים התראת תקציב (Billing → Budgets), למשל 100$ בחודש, כדי שלא תהיה הפתעה.
4. מכאן והלאה כל השירותים נפתחים באזור **Israel (Tel Aviv) il-central-1** (בחירה בפינה הימנית העליונה).

## 2. קבצים: S3 ✋
1. S3 → Create bucket, שם ייחודי (למשל `docketflow-files-<משהו>`), אזור il-central-1.
2. Block all public access: מסומן (ברירת המחדל).
3. Bucket Versioning: Enable. קובץ שנמחק או נדרס בטעות אפשר לשחזר.
4. Default encryption: SSE-S3.
5. אחרי היצירה: Management → Lifecycle rule שמוחק *גרסאות קודמות* אחרי 90 יום (Noncurrent versions), כדי שהעלות לא תתנפח.

## 3. מסד נתונים: RDS ✋
1. RDS → Create database → PostgreSQL 16, Standard create.
2. Templates: Production אם התקציב מאפשר (Multi-AZ). לפיילוט מספיק Single-AZ עם `db.t4g.small`.
3. שם משתמש `docket`, וסיסמה חזקה **בלי** התווים `@ : / %` (הם שוברים את הכתובת). שומרים אותה במנהל סיסמאות.
4. Storage: gp3, 20GB, Storage autoscaling מופעל. Encryption: מופעל.
5. Connectivity: **Public access: No**. Security group חדש בשם `docketflow-db`.
6. Additional configuration: Initial database name `docketai`. Backup retention: 14 ימים. Deletion protection: מופעל.
7. אחרי שה-EC2 קיים (שלב 6), חוזרים ל-security group `docketflow-db` ומאפשרים כניסה ל-5432 **רק** מה-security group של השרת.

## 4. מיילים: SES ✋
1. SES → Identities → Create identity → Domain → הדומיין שלכם. Easy DKIM, RSA 2048.
2. מוסיפים אצל רשם הדומיין את שלוש רשומות ה-CNAME שמוצגות. האימות לוקח בין דקות לשעות.
3. Custom MAIL FROM domain, למשל `mail.<הדומיין>`, ומוסיפים את רשומות ה-MX וה-SPF שמוצגות.
4. רשומת DMARC (TXT) בשם `_dmarc.<הדומיין>`: `v=DMARC1; p=none; rua=mailto:<כתובת שלכם>`. אחרי חודש שקט אפשר להחמיר ל-`p=quarantine`.
5. **חשוב:** חשבון SES חדש נמצא ב-sandbox ושולח רק לכתובות מאומתות. מבקשים יציאה: Account dashboard → Request production access.
   מתארים: "מערכת למשרדים ששולחת ללקוחות שלהם קישורים להעלאת מסמכים וחתימה, הזמנות לעובדים ואיפוס סיסמה. רק הודעות שהמשרד יזם, בלי דיוור שיווקי."
   האישור לוקח בדרך כלל יום.

## 5. הרשאות השרת: IAM ✋
1. IAM → Policies → Create policy → JSON. מדביקים את `deploy/iam-policy.json` ומחליפים את `BUCKET_NAME` ואת `YOUR_DOMAIN`. שם: `docketflow-server`.
2. IAM → Roles → Create role → AWS service → EC2. מצרפים את `docketflow-server` ואת `AmazonSSMManagedInstanceCore`
   (מאפשר להתחבר לשרת מהקונסולה בלי לפתוח SSH לאינטרנט). שם: `docketflow-server`.

## 6. השרת: EC2 ✋
1. EC2 → Launch instance: Ubuntu Server 24.04, סוג `t3.medium` (2 מעבדים, 4GB).
2. Key pair: לא חובה (מתחברים דרך Session Manager).
3. Network: security group חדש `docketflow-web` עם כניסה רק ל-**80 ו-443** מכל מקום. בלי 22.
4. Storage: 30GB gp3, Encrypted.
5. Advanced details: IAM instance profile = `docketflow-server`. Metadata version: **V2 only**, Metadata response hop limit: **2**
   (בלי 2, הקונטיינרים לא מקבלים את הרשאות התפקיד, וההעלאה ל-S3 ושליחת המייל נכשלות).
6. אחרי ההפעלה: Elastic IPs → Allocate → Associate לשרת. ככה הכתובת לא משתנה באתחול.
7. אצל רשם הדומיין: רשומת A, למשל `app.<הדומיין>`, אל ה-Elastic IP.
8. חוזרים לשלב 3.7 ופותחים את מסד הנתונים לשרת הזה בלבד.

## 7. התקנה ⌨️
מתחברים: EC2 → השרת → Connect → Session Manager.

```bash
sudo -i
curl -fsSL https://get.docker.com | sh
mkdir -p /opt/docketflow && cd /opt/docketflow
# המאגר פרטי: יוצרים ב-GitHub deploy key לקריאה בלבד, או מעבירים את הקוד בדרך אחרת.
git clone <כתובת המאגר> .
cp deploy/.env.production.example deploy/.env
chmod 600 deploy/.env
nano deploy/.env        # ממלאים: דומיין, DATABASE_URL, S3_BUCKET, EMAIL_FROM, MFA_SECRET_KEY, מפתחות AI
```

את `MFA_SECRET_KEY` מייצרים פעם אחת (הפקודה כתובת בקובץ), **ושומרים עותק במנהל סיסמאות**. בלעדיו אי אפשר לפתוח את
האימות הדו-שלבי של העובדים ואת קישורי התזכורות.

```bash
docker compose -f deploy/docker-compose.prod.yml up -d --build
docker compose -f deploy/docker-compose.prod.yml ps        # כולם healthy / running
docker compose -f deploy/docker-compose.prod.yml logs api --tail 50
```

ה-API מריץ את מיגרציות Alembic בכל עלייה, לפני שהוא מקבל בקשות.

**מנהל המשרד הראשון** (את שאר העובדים הוא מזמין מתוך המערכת):
```bash
docker compose -f deploy/docker-compose.prod.yml exec api \
  python -m app.cli create-user --organization "<שם המשרד>" --email <המייל שלו> --display-name "<השם שלו>"
```
הפקודה מבקשת סיסמה (12 תווים לפחות).

## 8. בדיקות אחרי העלייה
- [ ] `https://app.<הדומיין>` נפתח עם מנעול, ו-`http://` מפנה ל-https.
- [ ] כניסה עם המנהל הראשון, והפעלת אימות דו-שלבי בהגדרות → אבטחה.
- [ ] הזמנת עובד מ"צוות המשרד": המייל מגיע (לא לספאם), הקישור עובד.
- [ ] "שכחתי סיסמה": המייל מגיע.
- [ ] תיק לדוגמה: העלאת קובץ (מופיע ב-S3 בקונסולה), שליחת קישור ללקוח, חתימה, הורדת PDF חתום.
- [ ] `docker compose ... restart`, והכל חוזר לעבוד והמידע נשאר.

## 9. שוטף
- **עדכון גרסה:** `cd /opt/docketflow && git pull && docker compose -f deploy/docker-compose.prod.yml up -d --build`.
- **גיבויים:** RDS מגבה כל יום ושומר 14 ימים. ב-S3 נשמרות גרסאות קודמות 90 יום. פעם בחודש כדאי לנסות לשחזר snapshot של RDS
  למסד חדש, לוודא שזה עובד, ולמחוק אותו.
- **מה לא מגובה בשרת עצמו:** כלום שחשוב. אם השרת נמחק, מקימים חדש לפי שלבים 6 ו-7 עם אותו `deploy/.env`.

## לפני שמכניסים מידע אמיתי של לקוחות
אלה לא חלק מהשרת, אבל הם חלק מלהיות מוכנים:
- מדיניות פרטיות, תנאי שימוש והסכם עיבוד מידע מול כל משרד. כולל גילוי שקריאת AI שולחת טקסט של מסמכים לספק מחוץ לישראל, ושכל משרד יכול לכבות אותה.
- ניטור: התראת CloudWatch על השרת (CPU, דיסק), והתראה כשהאתר לא עונה (למשל Route 53 health check).
- בדיקת חדירות חיצונית, ובדיקה של נוסח תעודת החתימה ע"י עו"ד.
