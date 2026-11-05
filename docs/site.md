# The website: qasmin.com

`site/` is a static site with two pages: a home page and the privacy policy
that Google Play links to. `firebase.json` at the repository root serves it
from Firebase Hosting.

| Page | URL |
| --- | --- |
| Home | https://qasmin.com |
| Privacy policy | https://qasmin.com/privacy |

**Firebase Hosting is fine here, and only here.** The API stays off it
(see [deploy.md](deploy.md)) because Hosting cuts every request off at 60
seconds and reading a long bill takes longer. A static page answers in
milliseconds, so the limit never applies. Hosting is free at this size,
manages the certificate itself, and can serve the bare `qasmin.com`. Cloud
Run in Mumbai cannot map a domain without a paid load balancer.

## First time

1. **Install the Firebase CLI.** Run from any directory:

   ```sh
   npm install -g firebase-tools
   firebase login
   ```

2. **Add Firebase to the Google Cloud project the API already runs in.**
   Run from any directory. This only switches Firebase on for the project;
   it changes nothing about Cloud Run.

   ```sh
   firebase projects:addfirebase YOUR_PROJECT_ID
   ```

   If it says Firebase is already enabled, carry on.

3. **Deploy.** Run from the repository root, where `firebase.json` is:

   ```sh
   firebase deploy --only hosting --project YOUR_PROJECT_ID
   ```

   It prints `https://YOUR_PROJECT_ID.web.app`. Open `/privacy` on that
   address to check the page before any DNS changes.

4. **Put it on qasmin.com.** In the [Firebase console](https://console.firebase.google.com),
   open the project and go to *Hosting* → *Add custom domain*:

   - Enter `qasmin.com`. Firebase shows a `TXT` record and one or more `A`
     records. Add exactly those at your domain registrar, and delete any
     other `A` or `AAAA` records on `qasmin.com`, such as the registrar's
     parking page. Otherwise Firebase can't issue the certificate.
   - Add `www.qasmin.com` too, and choose *Redirect to qasmin.com*.

   The domain usually goes live within an hour. The certificate can take up
   to 24 hours.

5. **Make sure `support@qasmin.com` receives mail.** The policy gives it as
   the address for privacy requests, account deletion and complaints, so
   Play reviewers and users will write to it. Most registrars offer free
   email forwarding. Its `MX` records don't conflict with Firebase's `A`
   records.

## Changing the policy

Edit `site/privacy.html`, change the *Effective* date at the top, and deploy
again (step 3). If the change affects what is collected or how it is used,
also change the consent version in `api/auth.py` (`CONSENT_VERSION`) or
`api/lab.py` (`LAB_CONSENT_VERSION`) so that people are asked again, as the
policy promises. Keep the Play Console's *Data safety* answers in step with
the page.

The policy describes what the code does. If any of these change, change the
policy with them:

- what the API stores (`api/tables.py`);
- who processes data: Anthropic for reading, Google Cloud, Supabase, MSG91;
- where those providers run. The policy says Mumbai for Cloud Run and
  Supabase, as [deploy.md](deploy.md) recommends.
