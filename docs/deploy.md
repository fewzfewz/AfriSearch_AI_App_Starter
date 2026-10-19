# Deploying AfriSearch on one server

This guide puts AfriSearch on a single cloud server with HTTPS, sign-in, backups, error tracking and uptime monitoring. It's enough for a pilot with a few organisations. Allow about an hour.

## 1. What you need

| | Recommendation |
|---|---|
| **Server** | Ubuntu 24.04 with **4 vCPU, 8 GB RAM, 80 GB disk** (more RAM if you'll run a local answer model). Any provider works: Hetzner, DigitalOcean, AWS Lightsail, or a local provider. Choose a region close to your users and allowed by your data-protection rules. |
| **Domain** | A name such as `search.example.org`, with access to its DNS settings |
| **Supabase** | A free project at [supabase.com](https://supabase.com) for sign-in |
| **AI model** | An API key for Claude, ChatGPT or Gemini (recommended: the small local model gets many answers wrong, especially in Amharic) |
| Optional | A [Sentry](https://sentry.io) project for error reports; an uptime monitor such as [UptimeRobot](https://uptimerobot.com) or Better Stack |

## 2. Prepare the server

```bash
ssh root@YOUR_SERVER_IP
apt update && apt upgrade -y
apt install -y docker.io docker-compose-v2 git ufw
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw --force enable   # only SSH and web traffic
adduser --disabled-password afrisearch && usermod -aG docker afrisearch
su - afrisearch
git clone https://github.com/fewzfewz/AfriSearch_AI_App_Starter.git afrisearch && cd afrisearch
git checkout v0.2.0   # or the latest release tag
```

## 3. Point the domain at the server

In your DNS settings, add an **A record**: `search.example.org` → your server's IP address. Wait until `ping search.example.org` shows that IP (minutes to an hour).

## 4. Set up sign-in (Supabase)

1. Create a project. Under **Project Settings → API**, note the **Project URL**, the **anon public** key and the **service_role** key.
2. Under **Authentication → Providers → Email**, keep **Confirm email** turned **on**. AfriSearch adds people to workspaces by email, so emails must be verified.
3. Under **Authentication → URL Configuration**, set **Site URL** to `https://search.example.org` and add `https://search.example.org/app` and `https://search.example.org/signin` to the redirect URLs.
4. Optional: enable **Google** under **Authentication → Providers**.
5. For real users, set up your own email sender under **Authentication → SMTP Settings**; Supabase's built-in sender is only for testing and limits emails per hour.

## 5. Configure AfriSearch

```bash
cp .env.example .env
nano .env
```

Fill in at least:

```bash
AFRISEARCH_AUTH=supabase
SUPABASE_URL=https://YOUR-PROJECT.supabase.co
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...     # lets "Delete my account" remove the sign-in account too
AFRISEARCH_DOMAIN=search.example.org
AFRISEARCH_ORG_NAME=Your Organisation Ltd
AFRISEARCH_CONTACT_EMAIL=privacy@example.org
ANTHROPIC_API_KEY=...              # or OPENAI_API_KEY / GEMINI_API_KEY
AFRISEARCH_DEFAULT_PROVIDER=claude
```

Keep `.env` private (`chmod 600 .env`). It holds secret keys.

## 6. Start it

```bash
mkdir -p backups && sudo chown 1000:1000 backups   # the app runs as user 1000 inside the container
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml logs -f    # Ctrl+C to stop following
```

The first start builds the image and downloads about 1 GB of models. Caddy gets the HTTPS certificate automatically. Open `https://search.example.org`, create an account, and upload a test document.

## 7. Review the legal pages

Open `/privacy` and `/terms`. They describe what AfriSearch stores and sends, with your organisation name and contact email filled in, but they are a **template**: have a lawyer check them for your country (for example Ethiopia's Personal Data Protection Proclamation 2024 or Kenya's Data Protection Act 2019), and fill in the governing law in the terms. Edit them in `web/src/pages/LegalPage.tsx`.

## 8. Backups

Create a backup every night, and keep 14:

```bash
crontab -e
# add this line (as the afrisearch user):
15 3 * * * cd ~/afrisearch && docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml exec -T afrisearch python -m backend.backup create --out /app/backups --keep 14 >> ~/backup.log 2>&1
```

Backups land in `~/afrisearch/backups/`. **Copy them off the server** as well, for example nightly with `rclone` to object storage or another machine. A backup on the same disk doesn't survive losing the server.

**Test a restore** before you need one (on a spare machine or the same one with the app stopped):

```bash
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml stop afrisearch
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml run --rm afrisearch \
  python -m backend.backup restore /app/backups/afrisearch-backup-YYYYMMDD-HHMMSS.tar.gz --force
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml start afrisearch
```

`--force` moves the current data aside (into `data.before-restore-…` inside the volume) instead of deleting it.

## 9. Error tracking (Sentry)

Create a project for Python (FastAPI) and one for the browser (JavaScript) in Sentry, put their DSNs in `.env` as `SENTRY_DSN` and `SENTRY_DSN_WEB`, and restart. Reports never include documents, questions, IP addresses or cookies.

## 10. Uptime monitoring

Add a monitor for `https://search.example.org/api/health`. It returns **200** when the database answers and the data folder is writable, and **503** otherwise. Check every 5 minutes and alert by email or SMS.

## 11. Updating

```bash
cd ~/afrisearch
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml exec -T afrisearch python -m backend.backup create --out /app/backups
git fetch --tags && git checkout vX.Y.Z
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build
```

Read `CHANGELOG.md` before updating; until 1.0, a version may need re-indexing (the Library shows **Re-index now** when it does).

## Limits and costs

The defaults are set in `.env`: 500 MB of documents per workspace, 20 questions per minute and 500 per day per user, 200 uploaded files per hour per user. Raise or lower them to fit your plans and your AI bill. Limits are counted per server process; with one server that's exact.
