<!-- Save this file as README.md -->

# 🎟️ Ticket Management & Reminder System for BlinkDigitally

A lightweight yet powerful **ticket creation and management system** built with **Streamlit** and **Python**, integrated with **Notion** for storage and **Slack** for real-time notifications. The system also includes **daily automated reminders** powered by **GitHub Actions**, ensuring no ticket is overlooked.

---

## 🚀 Key Features

### 📝 Ticket Management (Streamlit App)

* Create, update, assign, and track tickets in real time
* Define ticket **status**, **priority**, **assignee**, and **creator**
* Automatic timestamping for submission and resolution
* Centralized ticket storage using **Notion Database**

### 🔔 Slack Notifications (Real-Time)

* Instant Slack notifications when:

  * A ticket is **created**
  * A ticket is **updated**
  * A ticket is **assigned or reassigned**
  * A ticket is **resolved**
* Both **ticket creator** and **assignee** are notified
* Admin receives visibility on all important updates

### ⏰ Daily Automated Reminders

* Daily scheduled reminders via **GitHub Actions**
* Reminds users of:

  * Open tickets
  * In-progress tickets
  * Personal tickets (created & assigned to the same user)
  * Pending print/production tickets (if applicable)
* Messages are delivered directly to Slack DMs

---

## 🧩 Tech Stack

| Component     | Technology                    |
| ------------- | ----------------------------- |
| Frontend      | Streamlit                     |
| Backend       | Python 3.11+                  |
| Database      | Notion API                    |
| Notifications | Slack API                     |
| Scheduling    | GitHub Actions                |
| Deployment    | Streamlit Cloud / Self-hosted |

---

## 🗂️ Architecture Overview

```
Streamlit App
   │
   ▼
Notion Database  ←→  Python Backend
   │                     │
   ▼                     ▼
Slack Notifications   GitHub Actions (Daily Reminders)
```

---

## ⚙️ Environment Variables

The following environment variables are required:

```bash
NOTION_TOKEN=your_notion_integration_token
NOTION_DATABASE_ID=your_notion_database_id
SLACK_BOT_TOKEN=xoxb-xxxxxxxx
ADMIN_EMAIL=admin@company.com
NAMES={"User Name": "user@company.com"}
```

> 💡 **Tip:** Store sensitive values as **GitHub Secrets** when using GitHub Actions.

---

## 📦 Installation & Setup

### 1️⃣ Clone the Repository

```bash
git clone https://github.com/your-org/ticket-management-app.git
cd ticket-management-app
```

### 2️⃣ Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\\Scripts\\activate
```

### 3️⃣ Install Dependencies

```bash
pip install -r requirements.txt
```

### 4️⃣ Run Streamlit App

```bash
streamlit run app.py
```

---

## 🔁 Slack Notification Logic

* **Ticket Created** → Creator + Admin notified
* **Ticket Assigned** → Assignee + Creator notified
* **Ticket Updated** → Creator + Assignee notified
* **Ticket Resolved** → Creator + Admin notified
* **Daily Reminder** → Assignee receives open tickets summary

All notifications are sent via **Slack DMs** for clarity and focus.

---

## ⏱️ GitHub Actions – Daily Reminder

The reminder job runs automatically on a schedule (example below):

```yaml
on:
  schedule:
    - cron: "0 9 * * 1-5"  # Weekdays at 9 AM
```

The workflow:

1. Fetches open tickets from Notion
2. Groups tickets by user
3. Resolves Slack user IDs
4. Sends personalized reminders

---

## 🛡️ Error Handling & Safeguards

* Skips users not found in Slack
* Prevents sending messages to invalid IDs
* Gracefully handles missing environment variables
* Logs skipped or failed notifications for debugging

---

## 📌 Use Cases

* Internal support teams
* Publishing & production tracking
* Operations & task management
* Remote team coordination
* SLA-driven workflows

---

## 🛣️ Roadmap (Optional Enhancements)

* Slack interactive buttons (Update / Resolve)
* Role-based permissions
* Ticket analytics dashboard
* File attachments support
* SLA breach alerts

---

## 🤝 Contributing

Pull requests are welcome. Please ensure code quality and test integrations with Slack and Notion before submitting.

---

## 📄 License

This project is licensed under the MIT License.

---

## ✨ Acknowledgments

Built with ❤️ using Streamlit, Notion API, Slack API, and GitHub Actions.
