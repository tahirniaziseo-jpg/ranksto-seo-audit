# One-time setup (free, ~10 minutes)

The audit reads your data straight from Google's own APIs. Google does not charge for these
APIs at audit-sized volumes. You need a free Google Cloud project and **one** of two ways
to sign in:

| | **A. Service account (recommended)** | **B. OAuth sign-in** |
|---|---|---|
| What it is | A "robot" Google account you add as a read-only user | You sign in as yourself in the browser |
| Consent screen / test users | Not needed | Needed |
| Expires | Never (until you delete the key) | Every 7 days in *Testing* mode |
| Works for clients' sites | Yes, the client adds the robot email as a user | Only sites your own account can see |

> No credit card is required. Google Cloud may show a "free trial" banner; you can ignore
> it. These APIs work without billing enabled.

Do steps 1–2, then **either** section A **or** steps 3–5 (B).

## 1. Create a Google Cloud project

1. Open <https://console.cloud.google.com/> and sign in with the Google account that has
   access to your Search Console property (and GA4 property).
2. Top bar → project picker → **New project** → name it `free-seo-audit` → **Create**.

## 2. Enable the APIs

Open each link (with the new project selected) and press **Enable**:

- Search Console API — <https://console.cloud.google.com/apis/library/searchconsole.googleapis.com>
- Google Analytics Data API — <https://console.cloud.google.com/apis/library/analyticsdata.googleapis.com>
- Google Analytics Admin API — <https://console.cloud.google.com/apis/library/analyticsadmin.googleapis.com>
- PageSpeed Insights API (optional) — <https://console.cloud.google.com/apis/library/pagespeedonline.googleapis.com>

## A. Service account (recommended)

1. **IAM & Admin → Service accounts → Create service account**. Name it `seo-audit-reader`,
   press **Create and continue**, then **Done**. No project roles are needed.
2. Open the new service account → **Keys → Add key → Create new key → JSON → Create**.
   A `.json` file downloads.
3. Save it as:
   - macOS / Linux: `~/.config/free-seo-audit/service_account.json`
   - Windows: `C:\Users\<you>\.config\free-seo-audit\service_account.json`

   (Or point `GOOGLE_APPLICATION_CREDENTIALS` at it.) Never commit or share this file.
4. Copy the service account's email (`seo-audit-reader@<project-id>.iam.gserviceaccount.com`)
   and give it read access:
   - **Search Console** → your property → **Settings → Users and permissions → Add user**
     → paste the email → permission **Restricted** → **Add**.
   - **GA4** → **Admin → Property access management → + → Add users** → paste the email →
     role **Viewer** → untick "Notify new users by email" → **Add**.
5. Check it:

```bash
pip install -r requirements.txt
python skills/free-seo-audit/scripts/fetch.py sites
python skills/free-seo-audit/scripts/fetch.py ga4-properties
```

When a `service_account.json` file exists, the scripts use it automatically. Skip to step 6.

## B. OAuth sign-in

### 3. Configure the consent screen

1. **APIs & Services → OAuth consent screen** (called "Google Auth Platform" in newer consoles).
2. User type **External** → fill in app name (`free-seo-audit`), your email for support and
   developer contact → save.
3. **Audience / Test users** → **Add users** → add your own Google account.
   Leaving the app in *Testing* mode is fine and keeps it private to you.

### 4. Create the OAuth client

1. **APIs & Services → Credentials → Create credentials → OAuth client ID**.
2. Application type **Desktop app** → name `free-seo-audit` → **Create**.
3. **Download JSON** and save it as:
   - macOS / Linux: `~/.config/free-seo-audit/client_secret.json`
   - Windows: `C:\Users\<you>\.config\free-seo-audit\client_secret.json`

   (Or set the `FREE_SEO_AUDIT_HOME` environment variable to another folder.)

### 5. Install and sign in

```bash
pip install -r requirements.txt
python skills/free-seo-audit/scripts/fetch.py auth
```

A browser window opens. Pick your account and allow **read-only** access to Search Console
and Google Analytics. Google warns "app isn't verified" because it is *your own* private
app — click **Continue**. The token is saved next to `client_secret.json` and never leaves
your computer.

Check it worked:

```bash
python skills/free-seo-audit/scripts/fetch.py sites
python skills/free-seo-audit/scripts/fetch.py ga4-properties
```

## 6. PageSpeed API key (recommended, free)

Google now rate-limits anonymous PageSpeed Insights calls, so Core Web Vitals checks
usually need a key:

1. **APIs & Services → Credentials → Create credentials → API key**.
2. Click the key → **API restrictions → Restrict key → PageSpeed Insights API** → save.
3. Set it as an environment variable:
   - macOS / Linux: `export PAGESPEED_API_KEY=your-key`
   - Windows (PowerShell): `setx PAGESPEED_API_KEY "your-key"` (then open a new terminal)

No billing account is needed.

## Notes

- **7-day sign-in limit:** while the consent screen is in *Testing* mode, Google expires
  the sign-in after 7 days. Just run `fetch.py auth` again. (Publishing the app removes the
  limit but is not needed.)
- **Quotas:** URL Inspection allows 2,000 inspections per property per day; Search Analytics
  and GA4 quotas are far above what an audit uses.
- **Revoke access any time:** <https://myaccount.google.com/permissions>

## No setup at all? Use CSV mode

1. Search Console → **Performance** → set date range to *Last 3 months* → **Export → CSV**.
   From the zip keep `Queries.csv` and `Pages.csv`.
2. Repeat with a custom range for the previous 3 months.
3. Give the four files to Claude, or run:

```bash
python skills/free-seo-audit/scripts/analyze.py \
  --cur-queries cur/Queries.csv --prev-queries prev/Queries.csv \
  --cur-pages cur/Pages.csv --prev-pages prev/Pages.csv \
  --out findings.json
```

Indexation, Core Web Vitals, on-page and robots checks still work in this mode because they
use public data. Only cannibalization and GA4 sections need the API path.
