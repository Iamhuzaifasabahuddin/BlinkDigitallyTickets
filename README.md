# 🎟 BlinkDigitally — Ticket Management & Reminder System

**Version:** v1.0.0

## Short description

BlinkDigitally Ticket Management & Reminder System is a Streamlit-based internal ticketing tool that uses **Notion as the canonical storage backend** and **Slack for real-time notifications and reminders**. It enables teams to create, assign, track, and resolve tickets through a simple UI, while automated Slack notifications and scheduled daily reminders ensure accountability and follow-through. A GitHub Actions workflow powers unattended reminder delivery.

**Repository & reference**

* Repo: [https://github.com/Iamhuzaifasabahuddin/BlinkDigitallyTickets](https://github.com/Iamhuzaifasabahuddin/BlinkDigitallyTickets)
* Primary app file: `app.py`

---

## Table of contents

* Key Features
* Architecture Overview
* Requirements
* Notion Schema (Recommended)
* Configuration (Environment Variables & Secrets)
* Install & Run (Local)
* GitHub Actions — Daily Reminders
* Slack Integration Details
* Development & Testing
* Roadmap
* Contributing
* License
* Changelog (v1.0.0)

---

## Key Features

* Create, update, assign, and resolve tickets via a Streamlit UI
* Centralized ticket storage in a Notion database (searchable, auditable, canonical)
* Real-time Slack notifications on ticket events:

  * Ticket created
  * Ticket updated
  * Ticket assigned or reassigned
  * Ticket resolved
* Automated daily Slack DM reminders for assignees with outstanding tickets
* GitHub Actions–based scheduler (no always-on server required)
* Safeguards to skip invalid Slack users and log notification failures
* Production-ready structure with clean separation of UI, storage, and notifications

---

## Architecture Overview

* Front-end UI: Streamlit
* Storage backend: Notion Database (CRUD operations via Notion API)
* Notifications: Slack API (DMs and admin notifications)
* Scheduling: GitHub Actions (cron-based reminder job)

**Flow:**
Streamlit UI → Python backend ↔ Notion Database
        ↘ Slack API (notifications)
        ↘ GitHub Actions (scheduled reminders)

---

## Requirements

Minimum tested environment:

* Python 3.9+
* streamlit
* notion-client
* slack-sdk
* requests
* python-dotenv (optional, for local use)

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## Notion Schema (Recommended)

Create a Notion database with the following properties (names are case-sensitive unless you update the mapping in code):

* **Title** (Title) — Ticket title
* **Description** (Rich Text) — Full ticket details
* **Status** (Select) — Open, In Progress, Resolved
* **Priority** (Select) — Low, Medium, High, Critical
* **Assigneed To* (Email or People) — Used to map to Slack user
* **Created By** (Email or People) — Ticket creator
* **Created** (Created time) — Automatic timestamp
* **Resolved** (Date) — Resolution date (optional)
* **Ticket ID** (Number or Formula) — Optional numeric identifier

If property names or types differ, update the backend mapping accordingly.

---

## Configuration (Environment Variables & Secrets)

Set these locally or (recommended) via GitHub Secrets for CI.

**Required:**

* `NOTION_TOKEN` — Notion integration token
* `NOTION_DATABASE_ID` — Target Notion database ID
* `SLACK_BOT_TOKEN` — Slack bot token (`xoxb-...`)
* `ADMIN_EMAIL` — Admin email for oversight notifications


**Security note:**
Never commit secrets to the repository. Use GitHub Secrets for CI and production deployments.

---

## Install & Run (Local)

1. Clone the repository

```bash
git clone https://github.com/Iamhuzaifasabahuddin/BlinkDigitallyTickets.git
cd BlinkDigitallyTickets
```

2. Create and activate a virtual environment

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
```

3. Install dependencies

```bash
pip install -r requirements.txt
```

4. Configure environment variables (`.env` or exports)

5. Run the Streamlit app

```bash
streamlit run app.py
```

Open the URL shown in the terminal (typically [http://localhost:8501](http://localhost:8501)).

---

## GitHub Actions — Daily Reminders

A scheduled workflow runs automatically to:

1. Query Notion for open or in-progress tickets
2. Group tickets by assignee
3. Resolve Slack user IDs via email lookup
4. Send personalized Slack DM reminders

Example cron schedule:

```yaml
on:
  schedule:
    - cron: "0 9 * * 1-5"  # Weekdays at 09:00 UTC
```

Ensure the workflow has access to all required secrets.

---

## Slack Integration Details

* Create a Slack App and install it to your workspace
* Required OAuth scopes:

  * `chat:write`
  * `users:read.email`
  * `im:write` (if opening DMs explicitly)
* Email → Slack user resolution is done via `users.lookupByEmail`
* Notifications include:

  * Immediate DMs on ticket lifecycle events
  * Daily reminder summaries per assignee
* Invalid or missing Slack users are skipped and logged

---

## Development & Testing

* Use a sandbox Notion database and test Slack workspace
* Keep secrets isolated via environment variables
* Logging captures API failures and skipped notifications
* Suggested local testing:

  1. Create test tickets via Streamlit
  2. Verify Slack notifications for each event
  3. Run reminder logic manually for validation

---

## Roadmap

Planned enhancements beyond v1.0.0:

* Interactive Slack buttons (Resolve / Update)
* Role-based permissions
* Ticket analytics dashboard
* File attachments
* SLA alerts and escalation workflows

---

## Contributing

Contributions are welcome:

1. Open an issue describing the change
2. Fork and create a feature branch
3. Submit a PR with clear description
4. Ensure CI passes and secrets are not exposed

---

## License

MIT — see `LICENSE` file.

---

## Changelog — v1.0.0

* Initial production-ready release
* Streamlit-based ticket CRUD
* Notion-backed persistent storage
* Slack notifications for ticket events
* GitHub Actions–powered daily reminders
* Basic error handling and logging

---
