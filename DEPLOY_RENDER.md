# Deploying Signal Monitor to Render

## Prerequisites

- A [Render](https://render.com) account (free to sign up)
- A [GitHub](https://github.com) account
- An [Anthropic API key](https://console.anthropic.com/) for the Claude-powered analysis

---

## Step 1 — Push to GitHub

Create a new repository on GitHub, then push this code:

```bash
# Unzip and enter the project
unzip signal-monitor.zip
cd pngsm-repo

# Initialize git
git init
git add .
git commit -m "Initial commit — Signal Monitor"

# Connect to your GitHub repo
git remote add origin https://github.com/YOUR_USERNAME/signal-monitor.git
git branch -M main
git push -u origin main
```

---

## Step 2 — Deploy via Render Blueprint (Recommended)

The repository includes a `render.yaml` file that automates the entire setup.

1. Go to [dashboard.render.com](https://dashboard.render.com)
2. Click **New +** → **Blueprint**
3. Connect your GitHub account if you haven't already
4. Select your **signal-monitor** repository
5. Render will detect the `render.yaml` and show you the planned services:
   - **Web Service**: `signal-monitor` (Python, Starter plan)
   - **Persistent Disk**: `pngsm-data` (1 GB, mounted at `/var/data`)
6. Render will prompt you to enter your **ANTHROPIC_API_KEY** — paste it in
7. Click **Apply**

Render will build and deploy the service. The first build takes 3–5 minutes due to the WeasyPrint system dependencies.

---

## Step 2 (Alternative) — Manual Deploy

If you prefer manual setup:

### Create the Web Service

1. Go to [dashboard.render.com](https://dashboard.render.com)
2. Click **New +** → **Web Service**
3. Connect your GitHub repo
4. Configure:

| Setting | Value |
|---------|-------|
| **Name** | `signal-monitor` |
| **Runtime** | `Python` |
| **Build Command** | `./build.sh` |
| **Start Command** | `gunicorn main:app --workers 2 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT` |
| **Plan** | Starter ($7/mo) or higher |

### Add a Persistent Disk

SQLite needs a persistent disk so your data survives redeploys.

1. In your service settings, go to **Disks**
2. Click **Add Disk**
3. Configure:

| Setting | Value |
|---------|-------|
| **Name** | `pngsm-data` |
| **Mount Path** | `/var/data` |
| **Size** | 1 GB (expand later if needed) |

### Set Environment Variables

In your service settings, go to **Environment** and add:

| Key | Value |
|-----|-------|
| `ANTHROPIC_API_KEY` | `sk-ant-your-key-here` |
| `PNGSM_DB_PATH` | `/var/data/monitor.db` |
| `PNGSM_REPORT_DIR` | `/var/data/reports` |
| `PYTHON_VERSION` | `3.12.3` |

Click **Save Changes** — Render will automatically redeploy.

---

## Step 3 — Verify

Once the deploy finishes (check the **Events** tab for progress):

1. Open your service URL: `https://signal-monitor-XXXX.onrender.com`
2. You should see the Signal Monitor dashboard
3. Visit `https://signal-monitor-XXXX.onrender.com/docs` for the interactive API docs
4. Visit `https://signal-monitor-XXXX.onrender.com/health` to confirm the health check

---

## Step 4 — Start Using

1. **Add a company** through the dashboard UI (click "+ Add Company")
2. **Click "Ingest Sources"** to pull SEC filings and news
3. **Click "Run Analysis"** to execute all five analysis modules
4. **Click "Generate Diagnostic"** to create the weekly report
5. **Download the PDF** from the executive summary section

---

## Architecture on Render

```
┌─────────────────────────────────────────────┐
│              Render Web Service              │
│                                              │
│  gunicorn + uvicorn workers                  │
│  ┌──────────────────────────────────┐        │
│  │         FastAPI Application      │        │
│  │  ┌───────┐ ┌────────┐ ┌──────┐  │        │
│  │  │Routes │ │Services│ │Models│  │        │
│  │  └───────┘ └────────┘ └──────┘  │        │
│  └──────────────────────────────────┘        │
│                    │                         │
│              ┌─────┴──────┐                  │
│              │ /var/data   │  ← Persistent   │
│              │  monitor.db │    Disk (1 GB)   │
│              │  reports/   │                  │
│              └────────────┘                  │
└─────────────────────────────────────────────┘
         │                        │
         ▼                        ▼
   SEC EDGAR API          Anthropic Claude API
   Google News RSS         (analysis engine)
   Reuters RSS
```

---

## Costs

| Component | Cost |
|-----------|------|
| Render Starter plan | $7/month |
| Persistent Disk (1 GB) | $0.25/month |
| Anthropic API (Claude Sonnet) | ~$0.50–2.00 per full pipeline run |
| **Total** | **~$8–10/month** + API usage |

The free tier will work for testing but has limitations: services spin down after 15 minutes of inactivity and the filesystem is ephemeral (no persistent disk available).

---

## Troubleshooting

### Build fails with WeasyPrint errors

The `build.sh` script installs system dependencies. If it fails, check that:
- The build command is set to `./build.sh` (not `pip install -r requirements.txt`)
- The file has execute permissions (`chmod +x build.sh` and commit)

### Database resets on redeploy

This means the persistent disk is not configured correctly. Verify:
- A disk is attached with mount path `/var/data`
- The `PNGSM_DB_PATH` env var is set to `/var/data/monitor.db`

### Analysis endpoints return errors

- Check that `ANTHROPIC_API_KEY` is set correctly in environment variables
- Check the **Logs** tab in Render for detailed error messages

### Slow cold starts

On the Starter plan, the first request after idle may take a few seconds. This is normal. For faster response times, upgrade to a Standard plan or higher.

---

## Updating

Push to your `main` branch and Render will automatically redeploy:

```bash
git add .
git commit -m "Update"
git push origin main
```

Render will build, test the health check, and swap to the new version.
