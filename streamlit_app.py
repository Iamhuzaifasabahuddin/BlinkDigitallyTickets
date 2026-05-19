import datetime
import hashlib
import os
import time
from datetime import timedelta
import plotly.express as px
import plotly.graph_objects as go
import extra_streamlit_components as stx
import pandas as pd
import pytz
import streamlit as st
from notion_client import Client
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


def setup_page():
    """Configure Streamlit page settings"""
    st.set_page_config(
        page_title="Support tickets",
        page_icon="🎫",
        layout="centered",
        initial_sidebar_state="collapsed"
    )


def hash_password(password):
    """Hash password using SHA256"""
    return hashlib.sha256(password.encode()).hexdigest()


class CookieAuth:
    """Handle cookie-based passwordless authentication with password fallback"""

    def __init__(self):
        self.cookie_manager = stx.CookieManager()
        self.cookie_name = st.secrets.get("ticket_cookie_name", "blink_ticket_cookie")
        self.cookie_key = st.secrets.get("cookie_key", "secret_key_tickets")
        self.expiry_days = int(st.secrets.get("ticket_cookie_expiry_days", 30))
        self.username = st.secrets.get("auth_username_user", "admin")
        self.user_name = st.secrets.get("auth_name_user", "Admin User")
        self.password_hash = st.secrets.get("auth_password_user", "")

    def generate_token(self):
        """Generate a secure token"""
        timestamp = datetime.datetime.now().isoformat()
        data = f"{self.username}:{self.cookie_key}:{timestamp}"
        return hashlib.sha256(data.encode()).hexdigest()

    def verify_token(self, token):
        """Verify if token is valid"""
        return len(token) == 64 and token.isalnum()

    def verify_password(self, password):
        """Verify password against hash"""
        return hash_password(password) == self.password_hash

    def set_auth_cookie(self):
        """Set authentication cookie"""
        token = self.generate_token()
        expiry = datetime.datetime.now() + timedelta(days=self.expiry_days)

        self.cookie_manager.set(
            self.cookie_name,
            token,
            expires_at=expiry
        )

        st.session_state.authentication_status = True
        st.session_state.username = self.username
        st.session_state.name = self.user_name
        st.session_state.authenticated = True

    def check_cookie(self):
        """Check if valid cookie exists"""
        cookies = self.cookie_manager.get_all()

        if self.cookie_name in cookies:
            token = cookies[self.cookie_name]

            if self.verify_token(token):
                st.session_state.authentication_status = True
                st.session_state.username = self.username
                st.session_state.name = self.user_name
                st.session_state.authenticated = True
                return True

        return False

    def is_authenticated(self):
        """Check if user is authenticated"""
        if st.session_state.get('authentication_status') is False:
            return False

        if st.session_state.get('authentication_status') is True:
            return True
        return self.check_cookie()

    def logout(self):
        """Clear authentication"""
        self.cookie_manager.delete(self.cookie_name)
        st.session_state.authentication_status = False
        st.session_state.username = None
        st.session_state.name = None
        st.session_state.authenticated = False


def login_page(auth):
    """Display login page"""
    st.title("🔑 Support Tickets Login")
    st.write("Access the Blink Digitally support ticket system")

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login")

        if submit:
            if username == auth.username and auth.verify_password(password):
                auth.set_auth_cookie()
                st.success("✅ Login successful!")
                time.sleep(0.5)
                st.rerun()
            else:
                print(auth.username, password)
                st.error("❌ Invalid username or password")


# Initialize Slack client
client = WebClient(token=st.secrets.get("Slack", ""))
name_all = st.secrets.get("name_all", {})


@st.cache_resource
def get_notion_client():
    notion_token = os.getenv("NOTION_TOKEN") or st.secrets.get("NOTION_TOKEN", "")
    if not notion_token:
        st.error("Please set NOTION_TOKEN in your environment or Streamlit secrets.")
        st.stop()
    return Client(auth=notion_token)


DATABASE_ID = os.getenv("NOTION_DATABASE_ID") or st.secrets.get("NOTION_DATABASE_ID", "")
DATASOURCE_ID = os.getenv("NOTION_DATASOURCE_ID") or st.secrets.get("NOTION_DATASOURCE_ID", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD") or st.secrets.get("ADMIN_PASSWORD", "")

if not DATABASE_ID:
    st.error("Please set NOTION_DATABASE_ID in your environment or Streamlit secrets.")
    st.info("""
    **Setup Instructions:**
    1. Create a Notion integration at https://www.notion.so/my-integrations
    2. Create a database in Notion with these properties:
       - ID (Title)
       - Issue (Text)
       - Status (Select: Open, In Progress, Closed)
       - Priority (Select: High, Medium, Low)
       - Date Submitted (Date)
       - Resolved Date (Date)
       - Created By (Select)
    3. Share your database with your integration
    4. Set NOTION_TOKEN, NOTION_DATABASE_ID, and ADMIN_PASSWORD in your environment or `.streamlit/secrets.toml`
    """)
    st.stop()

notion = get_notion_client()


def get_user_id_by_email(email):
    try:
        response = client.users_lookupByEmail(email=email)
        return response['user']['id']
    except SlackApiError as e:
        print(f"Error finding user: {e.response['error']}")
        return None


def send_dm(user_id, message):
    try:
        response = client.chat_postMessage(
            channel=user_id,
            text=message
        )
    except SlackApiError as e:
        print(f"❌ Error sending message: {e.response['error']}")


def send_files_to_slack(user_id, files, ticket_id, issue):
    """Upload files to Slack and send them in a DM."""
    try:
        if not files:
            return True

        intro_message = f"📎 *Files attached to Ticket {ticket_id}*\n*Issue:* {issue}\n"
        client.chat_postMessage(channel=user_id, text=intro_message)

        for uploaded_file in files:
            conversation = client.conversations_open(users=user_id)
            channel_id = conversation['channel']['id']

            response = client.files_upload_v2(
                channel=channel_id,
                file=uploaded_file,
                filename=uploaded_file.name
            )

        print(f"✅ {len(files)} file(s) sent to Slack user {user_id}")
        return True

    except SlackApiError as e:
        print(f"❌ Error uploading files to Slack: {e.response['error']}")
        return False


def fetch_tickets_from_notion():
    """Fetch all tickets from Notion database with pagination."""
    try:
        tickets = []
        has_more = True
        start_cursor = None

        while has_more:
            if start_cursor:
                results = notion.data_sources.query(
                    data_source_id=DATASOURCE_ID,
                    start_cursor=start_cursor,
                    sorts=[{"timestamp": "created_time", "direction": "ascending"}]
                )
            else:
                results = notion.data_sources.query(
                    data_source_id=DATASOURCE_ID,
                    sorts=[{"timestamp": "created_time", "direction": "ascending"}]
                )

            for page in results["results"]:
                props = page["properties"]
                ticket_id = props["ID"]["title"][0]["text"]["content"] if props["ID"]["title"] else ""
                if not ticket_id or "-" not in ticket_id:
                    ticket_id = "TICKET-0001"

                ticket = {
                    "page_id": page["id"],
                    "ID": ticket_id,
                    "Issue": props["Issue"]["rich_text"][0]["text"]["content"] if props["Issue"][
                        "rich_text"] else "",
                    "Status": props["Status"]["select"]["name"] if props["Status"]["select"] else "Open",
                    "Priority": props["Priority"]["select"]["name"] if props["Priority"]["select"] else "Medium",
                    "Date Submitted": props["Date Submitted"]["date"]["start"] if props["Date Submitted"][
                        "date"] else "",
                    "Submitted Time": props["Submitted Time"]["rich_text"][0]["text"][
                        "content"] if props["Submitted Time"]["rich_text"] else "",
                    "Created By": props["Created By"]["select"]["name"] if props["Created By"]["select"][
                        "name"] else "",
                    "Assigned To": props["Assigned To"]["select"]["name"] if props["Assigned To"]["select"][
                        "name"] else "",
                    "Resolved Date": props["Resolved Date"]["date"]["start"] if props.get("Resolved Date") and
                                                                                props["Resolved Date"][
                                                                                    "date"] else None,
                    "Resolved Time": props["Resolved Time"]["rich_text"][0]["text"][
                        "content"] if props["Resolved Time"]["rich_text"] else "",
                    "Comments": props["Comments"]["rich_text"][0]["text"]["content"] if props["Comments"][
                        "rich_text"] else "",
                    "Ticket Type": props["Ticket Type"]["rich_text"][0]["text"]["content"] if props["Ticket Type"][
                        "rich_text"] else "",
                    "Notify": props["Notify"]["rich_text"][0]["text"]["content"] if props["Notify"][
                        "rich_text"] else ""
                }
                tickets.append(ticket)

            has_more = results.get("has_more", False)
            start_cursor = results.get("next_cursor", None)

        df = pd.DataFrame(tickets)
        if not df.empty:
            if "Date Submitted" in df.columns:
                df["Date Submitted"] = pd.to_datetime(df["Date Submitted"], format="%Y-%m-%d", errors='coerce')
            if "Resolved Date" in df.columns:
                df["Resolved Date"] = pd.to_datetime(df["Resolved Date"], format="%Y-%m-%d", errors='coerce')

        return df

    except Exception as e:
        st.error(f"Error fetching tickets from Notion: {e}")
        return pd.DataFrame(
            columns=["page_id", "ID", "Issue", "Status", "Priority", "Date Submitted", "Submitted Time",
                     "Resolved Date", "Resolved Time", "Comments", "Ticket Type"])


def send_ticket_notifications(ticket_id, issue, priority, status, date, time, user_details, creator_name,
                              assigned_name, uploaded_files=None):
    """Send Slack notifications to both ticket creator and assigned user."""
    try:
        if user_details['receiver_id']:
            assigned_message = f"""🎫 *New Ticket Assigned to You*
*🆔 Ticket ID:* {ticket_id}
*⏰ Priority:* {priority}
*📊 Status:* {status}
*📅 Created Date (PKST):* {date}
*⌛ Created Time (PKST):* {time}
*➕ Created By:* {creator_name}
*❓ Issue:* \n{issue}

Please review and update the ticket status accordingly."""
            send_dm(user_details['receiver_id'], assigned_message)

            if uploaded_files:
                send_files_to_slack(user_details['receiver_id'], uploaded_files, ticket_id, issue)

            print(f"✅ Notification sent to {assigned_name} ({user_details['receiver_email']})")
        else:
            print(f"⚠️ Could not send notification to {assigned_name} - Slack ID not found")

        if user_details['sender_id'] and user_details['sender_id'] != user_details['receiver_id']:
            files_text = f"\n*📎 Attachments:* {len(uploaded_files)} file(s)" if uploaded_files else ""

            creator_message = f"""✅ *Ticket Created Successfully*
*🆔 Ticket ID:* {ticket_id}
*⏰ Priority:* {priority}
*📊 Status:* {status}
*📅 Created Date (PKST):* {date}
*⌛ Created Time (PKST):* {time}
*📕 Assigned To:* {assigned_name}
*❓ Issue:* \n{issue}{files_text}

Your ticket has been submitted and assigned. You'll be notified of any updates."""
            send_dm(user_details['sender_id'], creator_message)
            print(f"✅ Confirmation sent to {creator_name} ({user_details['sender_email']})")
        elif user_details['sender_id'] == user_details['receiver_id']:
            print(f"ℹ️ Creator and assignee are the same person - sent only one notification")
        else:
            print(f"⚠️ Could not send confirmation to {creator_name} - Slack ID not found")

    except Exception as e:
        print(f"❌ Error sending Slack notifications: {e}")


def get_user_details(name, assigned):
    """Get sender and receiver email addresses and Slack IDs."""
    try:
        sender_email = name_all.get(name)
        receiver_email = name_all.get(assigned)

        if not sender_email:
            print(f"Warning: No email found for '{name}'")
            sender_id = None
        else:
            sender_id = get_user_id_by_email(sender_email)

        if not receiver_email:
            print(f"Warning: No email found for '{assigned}'")
            receiver_id = None
        else:
            receiver_id = get_user_id_by_email(receiver_email)

        return {
            "sender_email": sender_email,
            "receiver_email": receiver_email,
            "sender_id": sender_id,
            "receiver_id": receiver_id
        }

    except Exception as e:
        print(f"Error getting user details: {e}")
        return {
            "sender_email": None,
            "receiver_email": None,
            "sender_id": None,
            "receiver_id": None
        }


def create_ticket_in_notion(ticket_id, issue, status, priority, date_submitted, name, assigned, uploaded_files=None):
    """Create a new ticket in Notion database."""
    try:
        if isinstance(date_submitted, (datetime.date, datetime.datetime)):
            date_submitted_str = date_submitted.strftime("%Y-%m-%d")
        else:
            date_submitted_str = str(date_submitted)

        pkt = pytz.timezone("Asia/Karachi")
        now_pkt = datetime.datetime.now(pkt)
        formatted_time = now_pkt.time().strftime("%I:%M %p")
        formatted_date = date_submitted.strftime("%d-%B-%Y")

        ticket_type = None
        if name == assigned:
            ticket_type = "Personal"
        else:
            ticket_type = "Normal"

        properties = {
            "ID": {"title": [{"text": {"content": ticket_id}}]},
            "Issue": {"rich_text": [{"text": {"content": issue}}]},
            "Status": {"select": {"name": status}},
            "Priority": {"select": {"name": priority}},
            "Created By": {"select": {"name": name}},
            "Assigned To": {"select": {"name": assigned}},
            "Date Submitted": {"date": {"start": date_submitted_str}},
            "Submitted Time": {"rich_text": [{"text": {"content": formatted_time}}]},
            "Ticket Type": {"rich_text": [{"text": {"content": ticket_type}}]},
            "Notify": {"rich_text": [{"text": {"content": "Yes"}}]},
        }

        notion.pages.create(
            parent={"data_source_id": DATASOURCE_ID},
            properties=properties
        )

        user_details = get_user_details(name, assigned)
        send_ticket_notifications(ticket_id, issue, priority, status, formatted_date, formatted_time, user_details,
                                  name, assigned, uploaded_files)
        return True

    except Exception as e:
        st.error(f"Error creating ticket: {e}")
        return False


def send_ticket_update_notifications(ticket_id, old_status, new_status, old_priority, new_priority, issue,
                                     creator_name, assigned_name, comments, resolved_date=None,
                                     uploaded_files=None):
    """Send Slack notifications when a ticket is updated."""
    try:
        pkt = pytz.timezone("Asia/Karachi")
        now_pkt = datetime.datetime.now(pkt)
        formatted_time = now_pkt.time().strftime("%I:%M %p")

        changes = []
        if old_status != new_status:
            changes.append(f"*Status:* {old_status} → {new_status}")
        if old_priority != new_priority:
            changes.append(f"*Priority:* {old_priority} → {new_priority}")
        if resolved_date and new_status == "Closed":
            changes.append(f"*Resolved Date (PKST):* {resolved_date}")
            changes.append(f"*Resolved Time (PKST):* {formatted_time}")
        if comments:
            changes.append(f"*Comments:* {comments}")
        if uploaded_files:
            changes.append(f"*📎 Attachments:* {len(uploaded_files)} file(s)")

        if not changes:
            return

        changes_text = "\n".join(changes)
        user_details = get_user_details(creator_name, assigned_name)

        if user_details['receiver_id']:
            assigned_message = f"""🔔 *Ticket Updated*
*🆔 Ticket ID:* {ticket_id}
*➕ Created By:* {creator_name}
*❓ Issue:* \n{issue}
*✏ Changes:*
{changes_text}
"""
            send_dm(user_details['receiver_id'], assigned_message)
            if uploaded_files:
                send_files_to_slack(user_details['receiver_id'], uploaded_files, ticket_id, issue)

            print(f"✅ Update notification sent to {assigned_name} ({user_details['receiver_email']})")

        if user_details['sender_id'] and user_details['sender_id'] != user_details['receiver_id']:
            creator_message = f"""🔔 *Your Ticket Was Updated*
*🆔 Ticket ID:* {ticket_id}
*📕 Assigned To:* {assigned_name}
*❓ Issue:* \n{issue}
*✏ Changes:*
{changes_text}
"""
            send_dm(user_details['sender_id'], creator_message)

            print(f"✅ Update notification sent to {creator_name} ({user_details['sender_email']})")

    except Exception as e:
        print(f"❌ Error sending update notifications: {e}")


def update_ticket_in_notion(page_id, issue, status, priority, resolved_date, comments, old_status=None,
                            old_priority=None, ticket_id=None, creator_name=None, assigned_name=None, new_notify=None,
                            old_notify=None, uploaded_files=None):
    """Update an existing ticket in Notion and send notifications."""
    try:
        properties = {
            "Issue": {"rich_text": [{"text": {"content": issue}}]},
            "Status": {"select": {"name": status}},
            "Priority": {"select": {"name": priority}},
        }

        if resolved_date and pd.notna(resolved_date):
            if isinstance(resolved_date, (pd.Timestamp, datetime.datetime, datetime.date)):
                resolved_date_str = resolved_date.strftime("%Y-%m-%d") if hasattr(resolved_date,
                                                                                  'strftime') else str(
                    resolved_date)
                pkt = pytz.timezone("Asia/Karachi")
                now_pkt = datetime.datetime.now(pkt)
                formatted_time = now_pkt.time().strftime("%I:%M %p")

                properties["Resolved Date"] = {"date": {"start": resolved_date_str}}
                properties["Resolved Time"] = {"rich_text": [{"text": {"content": formatted_time}}]}
        else:
            properties["Resolved Date"] = {"date": None}

        if comments:
            properties["Comments"] = {"rich_text": [{"text": {"content": comments}}]}

        if new_notify != old_notify and new_notify:
            properties["Notify"] = {"rich_text": [{"text": {"content": new_notify}}]}

        notion.pages.update(
            page_id=page_id,
            properties=properties
        )

        if all([ticket_id, old_status, old_priority, creator_name, assigned_name]):
            formatted_resolved_date = None
            if resolved_date and pd.notna(resolved_date):
                formatted_resolved_date = resolved_date.strftime("%d-%B-%Y")

            send_ticket_update_notifications(
                ticket_id,
                old_status,
                status,
                old_priority,
                priority,
                issue,
                creator_name,
                assigned_name,
                comments,
                formatted_resolved_date,
                uploaded_files=uploaded_files,
            )

        if new_notify != old_notify and new_notify:
            st.success(f"{ticket_id} Notification Updated to {new_notify}")

        return True

    except Exception as e:
        st.error(f"Error updating ticket: {e}")
        return False


def main():
    """Main application entry point"""
    setup_page()

    auth = CookieAuth()

    if not auth.is_authenticated():
        with st.spinner("🔄 Initializing secure session..."):
            time.sleep(1.5)
        login_page(auth)
        return

    st.title(f"🎫 Support Tickets for Blink Digitally")
    st.write(f"Welcome, **{st.session_state.get('name')}**!")
    st.write("Use this app to submit in any publishing updates, republication details, or reminders.")

    with st.sidebar:
        st.header(f"👤 {st.session_state.get('name')}")
        if st.button("🚪 Logout"):
            auth.logout()
            st.rerun()

        st.divider()
        st.header("🔐 Admin Access")
        if not st.session_state.get("admin_authenticated", False):
            password_input = st.text_input("Enter admin password:", type="password", key="admin_password")
            if st.button("Admin Login"):
                if password_input == ADMIN_PASSWORD:
                    st.session_state.admin_authenticated = True
                    st.success("Admin access granted!")
                    st.rerun()
                else:
                    st.error("Incorrect password")
        else:
            st.success("✅ Admin Authenticated")
            if st.button("Admin Logout"):
                st.session_state.admin_authenticated = False
                st.rerun()

    if st.button("🔄 Fetch Latest"):
        with st.spinner("Loading tickets from Notion..."):
            st.session_state.df = fetch_tickets_from_notion()
            st.session_state.original_df = st.session_state.df.copy()

    def showcase(key):
        if "df" not in st.session_state:
            st.session_state.df = fetch_tickets_from_notion()
            st.session_state.original_df = st.session_state.df.copy()

        df = st.session_state.df.copy()
        df["Month"] = df["Date Submitted"].dt.strftime("%B")
        unique_months = sorted(df["Month"].unique().tolist())
        months = ["All"] + unique_months

        pkt = pytz.timezone("Asia/Karachi")
        current_month = datetime.datetime.now(pkt).strftime("%B")
        default_index = months.index("All") if current_month in months else 0

        selected_month = st.selectbox("📅 Choose a month to filter tickets", months, index=default_index, key=key)

        if selected_month == "All":
            filtered_df = df.copy()
        else:
            filtered_df = df[df["Month"] == selected_month].copy()

        st.subheader(f"📊 Showing tickets for: **{selected_month}**")

        normal_count = len(filtered_df[filtered_df["Ticket Type"] == "Normal"])
        personal_count = len(filtered_df[filtered_df["Ticket Type"] == "Personal"])

        st.metric(label="Total Normal Tickets Found", value=normal_count)
        st.metric(label="Total Personal Tickets Found", value=personal_count)

        if filtered_df.empty:
            st.info("No tickets found for the selected month.")
            st.stop()

        active_df = filtered_df[filtered_df["Status"].isin(["Open", "In Progress"])].copy()
        personal_active = active_df[active_df["Ticket Type"] == "Personal"]
        active_df = active_df[active_df["Ticket Type"] == "Normal"]

        closed_df = filtered_df[filtered_df["Status"] == "Closed"].copy()
        personal_closed = closed_df[closed_df["Ticket Type"] == "Personal"]
        closed_df = closed_df[closed_df["Ticket Type"] == "Normal"]

        st.header("🟢 Active Tickets")

        if selected_month == "All":
            st.metric(
                label="Number of active tickets",
                value=f"{len(active_df):,}"
            )
        else:
            st.metric(
                label=f"Number of active tickets this month ({selected_month})",
                value=f"{len(active_df):,}"
            )

        st.metric(label="Number of active personal tickets", value=len(personal_active))

        if st.session_state.get("admin_authenticated", False):
            st.info(
                "You can edit tickets by double-clicking a cell. Click 'Save Changes to Notion' "
                "to sync your edits. You can also sort columns by clicking headers.",
                icon="✍️",
            )

        display_active_df = active_df.drop(columns=["page_id", "Month", "Resolved Time"], errors="ignore")

        disabled_columns = ["ID", "Date Submitted", "Month", "Resolved Time", "Submitted Time", "Created By",
                            "Assigned To",
                            "Ticket Type"]
        if not st.session_state.get("admin_authenticated", False):
            disabled_columns = list(display_active_df.columns)

        edited_active_df = st.data_editor(
            display_active_df,
            width="stretch",
            hide_index=True,
            key=f"active_editor_{key}",
            column_config={
                "Status": st.column_config.SelectboxColumn("Status", options=["Open", "In Progress", "Closed"],
                                                           required=True),
                "Priority": st.column_config.SelectboxColumn("Priority", options=["High", "Medium", "Low"],
                                                             required=True),
                "Date Submitted": st.column_config.DateColumn("Date Submitted", format="YYYY-MM-DD"),
                "Resolved Date": st.column_config.DateColumn("Resolved Date", format="YYYY-MM-DD"),
            },
            disabled=disabled_columns,
        )

        if st.session_state.get("admin_authenticated", False) and not edited_active_df.equals(display_active_df):
            if st.button("💾 Save Active Tickets to Notion", type="primary", key="save_active"):
                with st.spinner("Saving changes to Notion..."):
                    success_count, error_count = 0, 0

                    for idx in edited_active_df.index:
                        original_row = display_active_df.loc[idx]
                        edited_row = edited_active_df.loc[idx]

                        if not original_row.equals(edited_row):
                            page_id = active_df.loc[idx, "page_id"]
                            success = update_ticket_in_notion(
                                page_id=page_id,
                                issue=edited_row["Issue"],
                                status=edited_row["Status"],
                                priority=edited_row["Priority"],
                                resolved_date=edited_row["Resolved Date"],
                                comments=edited_row["Comments"],
                                old_status=original_row["Status"],
                                old_priority=original_row["Priority"],
                                ticket_id=original_row["ID"],
                                creator_name=original_row.get("Created By", "Unknown"),
                                assigned_name=original_row.get("Assigned To", "Unknown"),
                            )

                            if success:
                                success_count += 1
                            else:
                                error_count += 1

                    if success_count > 0:
                        st.success(f"✅ {success_count} ticket(s) updated successfully! Notifications sent.")
                    if error_count > 0:
                        st.error(f"❌ {error_count} ticket(s) failed to update.")

                    st.session_state.df = fetch_tickets_from_notion()
                    st.session_state.original_df = st.session_state.df.copy()
                    st.rerun()

        st.divider()

        st.header("📦 Closed Tickets")

        if selected_month == "All":
            st.metric(
                label="Number of closed tickets",
                value=f"{len(closed_df):,}"
            )
        else:
            st.metric(
                label=f"Number of closed tickets this month ({selected_month})",
                value=f"{len(closed_df):,}"
            )

        st.metric(label="Number of closed personal tickets", value=len(personal_closed))

        if closed_df.empty:
            st.info("No closed tickets for the selected month.")
        else:
            with st.expander("View Closed Tickets", expanded=False):
                display_closed_df = closed_df.drop(columns=["page_id", "Month"], errors="ignore")

                disabled_closed_columns = ["ID", "Date Submitted", "Month", "Resolved Time", "Submitted Time",
                                           "Created By",
                                           "Assigned To", "Ticket Type"]
                if not st.session_state.get("admin_authenticated", False):
                    disabled_closed_columns = list(display_closed_df.columns)

                edited_closed_df = st.data_editor(
                    display_closed_df,
                    width="stretch",
                    hide_index=True,
                    key=f"closed_editor_{key}",
                    column_config={
                        "Status": st.column_config.SelectboxColumn("Status", options=["Open", "In Progress", "Closed"],
                                                                   required=True),
                        "Priority": st.column_config.SelectboxColumn("Priority", options=["High", "Medium", "Low"],
                                                                     required=True),
                        "Date Submitted": st.column_config.DateColumn("Date Submitted", format="YYYY-MM-DD"),
                        "Resolved Date": st.column_config.DateColumn("Resolved Date", format="YYYY-MM-DD"),
                    },
                    disabled=disabled_closed_columns,
                )

                if st.session_state.get("admin_authenticated", False) and not edited_closed_df.equals(
                        display_closed_df):
                    if st.button("💾 Save Closed Tickets to Notion", type="primary", key="save_closed"):
                        with st.spinner("Saving changes to Notion..."):
                            success_count, error_count = 0, 0

                            for idx in edited_closed_df.index:
                                original_row = display_closed_df.loc[idx]
                                edited_row = edited_closed_df.loc[idx]

                                if not original_row.equals(edited_row):
                                    page_id = closed_df.loc[idx, "page_id"]
                                    success = update_ticket_in_notion(
                                        page_id=page_id,
                                        issue=edited_row["Issue"],
                                        status=edited_row["Status"],
                                        priority=edited_row["Priority"],
                                        resolved_date=edited_row["Resolved Date"],
                                        comments=edited_row["Comments"],
                                        old_status=original_row["Status"],
                                        old_priority=original_row["Priority"],
                                        ticket_id=original_row["ID"],
                                        creator_name=original_row.get("Created By", "Unknown"),
                                        assigned_name=original_row.get("Assigned To", "Unknown"),
                                    )

                                    if success:
                                        success_count += 1
                                    else:
                                        error_count += 1

                            if success_count > 0:
                                st.success(f"✅ {success_count} ticket(s) updated successfully! Notifications sent.")
                            if error_count > 0:
                                st.error(f"❌ {error_count} ticket(s) failed to update.")

                            st.session_state.df = fetch_tickets_from_notion()
                            st.session_state.original_df = st.session_state.df.copy()
                            st.rerun()

    # ── Tabs: Add Ticket / Update Ticket / Analytics ──────────────────────────
    col1, col2, col3 = st.tabs(["Add Ticket", "Update Ticket", "📊 Analytics"])

    with col1:
        expander = st.expander("Order Details Template 📄")

        expander.info(
            """Follow the template:

        Printed Copies
        Example: 25 Printed Copies (Paperback)

        Client Name:
        (Example: John Doe)

        Client Brand:
        (Example: Bookmarketeers)

        Client Phone Number:
        (Example: 0122345567)

        Client Address:
        (Example: 3811 Ditmars Blvd, Queens, New York, USA)
        """
        )

        st.header("➕ Add a New Ticket")
        pkt = pytz.timezone("Asia/Karachi")
        now_pkt = datetime.datetime.now(pkt)

        with st.form("add_ticket_form"):
            issue = st.text_area("Describe the issue", height=200)

            uploaded_files = st.file_uploader(
                "Attach files (optional)",
                accept_multiple_files=True,
                help="You can attach images, PDFs, documents, etc."
            )

            if uploaded_files:
                total_size = sum(f.size for f in uploaded_files)
                max_size = 200 * 1024 * 1024

                st.info(f"📎 {len(uploaded_files)} file(s) selected ({total_size / 1024 / 1024:.2f} MB)")

                if total_size > max_size:
                    st.warning(f"⚠️ Total file size exceeds 200 MB limit. Please reduce file size.")

            today = st.date_input("Date (PKST)", now_pkt.date())
            priority = st.selectbox("Priority", ["High", "Medium", "Low"])
            name = st.selectbox("Created By", st.secrets.get("NAMES", ""))
            assigned = st.selectbox("Assigned To", st.secrets.get("NAMES", ""),
                                    index=st.secrets.get("NAMES", "").index("Huzaifa Sabah Uddin"))
            submitted = st.form_submit_button("Submit")

            if submitted:
                if not issue.strip():
                    st.error("⚠️ Please describe the issue before submitting.")
                elif not name or not assigned:
                    st.warning("⚠️ Please select both 'Created By' and 'Assigned To' before submitting.")
                elif uploaded_files and sum(f.size for f in uploaded_files) > 200 * 1024 * 1024:
                    st.error("⚠️ Total file size exceeds 200 MB. Please reduce file size before submitting.")
                else:
                    try:
                        with st.spinner("Fetching latest ticket from Notion..."):
                            try:
                                results = notion.data_sources.query(
                                    data_source_id=DATASOURCE_ID,
                                    page_size=1,
                                    sorts=[{"timestamp": "created_time", "direction": "descending"}]
                                )

                                if results.get("results"):
                                    latest_page = results["results"][0]
                                    latest_id_prop = latest_page["properties"]["ID"]["title"]
                                    latest_id = latest_id_prop[0]["text"][
                                        "content"] if latest_id_prop else "TICKET-0000"

                                    if "-" in latest_id:
                                        recent_ticket_number = int(latest_id.split("-")[1])
                                    else:
                                        recent_ticket_number = 0
                                else:
                                    recent_ticket_number = 0

                            except Exception as e:
                                st.warning(f"⚠️ Could not fetch the latest ticket ID: {e}. Defaulting to TICKET-0000")
                                recent_ticket_number = 0

                            new_ticket_id = f"TICKET-{recent_ticket_number + 1}"

                        with st.spinner("Creating ticket in Notion..."):
                            try:
                                success = create_ticket_in_notion(
                                    new_ticket_id,
                                    issue,
                                    "Open",
                                    priority,
                                    today,
                                    name,
                                    assigned,
                                    uploaded_files
                                )

                                if success:
                                    st.success(f"✅ Ticket **{new_ticket_id}** created successfully in Notion!")
                                    if uploaded_files:
                                        st.success(f"📎 {len(uploaded_files)} file(s) sent to {assigned}")
                                    st.session_state.df = fetch_tickets_from_notion()
                                    st.session_state.original_df = st.session_state.df.copy()
                                    st.rerun()
                                else:
                                    st.error("❌ Failed to create the ticket in Notion. Please try again later.")

                            except Exception as e:
                                st.error(f"🚨 Error while creating ticket in Notion: {e}")

                    except Exception as e:
                        st.error(f"🚨 Error while creating ticket in Notion: {e}")
        showcase(key="add_ticket")
    with col2:
        st.header("✏️ Update an Existing Ticket")

        if "df" not in st.session_state:
            st.session_state.df = fetch_tickets_from_notion()
            st.session_state.original_df = st.session_state.df.copy()

        temp_df = st.session_state.df.copy()
        active_tickets = temp_df[temp_df["Status"].isin(["Open", "In Progress"])]

        if active_tickets.empty:
            st.info("No active tickets available to update.")
        else:
            ticket_options = active_tickets["ID"].tolist()
            selected_ticket = st.selectbox("Select Ticket to Update", ticket_options)

            if selected_ticket:
                ticket_data = active_tickets[active_tickets["ID"] == selected_ticket].iloc[0]

                st.markdown(f"<p style='font-size: 16px;'>📄 Issue: {ticket_data['Issue']}</p>", unsafe_allow_html=True)
                st.markdown(f"<p style='font-size: 16px;'>📊 Current Status: {ticket_data['Status']}</p>",
                            unsafe_allow_html=True)
                st.markdown(f"<p style='font-size: 16px;'>⏰ Current Priority: {ticket_data['Priority']}</p>",
                            unsafe_allow_html=True)
                st.markdown(f"<p style='font-size: 16px;'>➕ Created By: {ticket_data['Created By']}</p>",
                            unsafe_allow_html=True)
                st.markdown(f"<p style='font-size: 16px;'>📕 Assigned To: {ticket_data['Assigned To']}</p>",
                            unsafe_allow_html=True)

                pkt = pytz.timezone("Asia/Karachi")
                now_pkt = datetime.datetime.now(pkt)

                new_notify = ticket_data["Notify"]
                if st.session_state.get("admin_authenticated", False):
                    new_notify = st.selectbox("Update Notify", ["Yes", "No"],
                                              index=["Yes", "No"].index(ticket_data["Notify"]))

                with st.form("update_ticket_form"):
                    new_status = st.selectbox("Update Status", ["Open", "In Progress", "Closed"],
                                              index=["Open", "In Progress", "Closed"].index(ticket_data["Status"]))
                    new_priority = st.selectbox("Update Priority", ["High", "Medium", "Low"],
                                                index=["High", "Medium", "Low"].index(ticket_data["Priority"]))

                    resolved_date = None
                    if new_status == "Closed":
                        resolved_date = st.date_input("Resolved Date (PKST)", now_pkt.date())

                    comments = st.text_area("Comments")

                    update_uploaded_files = st.file_uploader(
                        "Attach files (optional)",
                        accept_multiple_files=True,
                        help="Attach images, PDFs, documents, etc. Files will be sent via Slack.",
                        key="update_file_uploader"
                    )

                    if update_uploaded_files:
                        total_update_size = sum(f.size for f in update_uploaded_files)
                        max_size = 50 * 1024 * 1024
                        st.info(
                            f"📎 {len(update_uploaded_files)} file(s) selected "
                            f"({total_update_size / 1024 / 1024:.2f} MB)"
                        )
                        if total_update_size > max_size:
                            st.warning("⚠️ Total file size exceeds 50 MB limit. Please reduce file size.")

                    update_submitted = st.form_submit_button("Update Ticket")

                    has_changes = (
                            new_status != ticket_data["Status"] or
                            new_priority != ticket_data["Priority"] or
                            comments.strip() != "" or
                            bool(update_uploaded_files)
                            or new_notify != ticket_data["Notify"]
                    )

                    if update_submitted and not has_changes:
                        st.warning("⚠️ No changes detected for this ticket.")

                    if update_submitted and has_changes:
                        if update_uploaded_files and sum(f.size for f in update_uploaded_files) > 50 * 1024 * 1024:
                            st.error("⚠️ Total file size exceeds 50 MB. Please reduce file size before submitting.")
                        else:
                            with st.spinner("Updating ticket in Notion..."):
                                try:
                                    page_id = ticket_data["page_id"]
                                    success = update_ticket_in_notion(
                                        page_id=page_id,
                                        issue=ticket_data["Issue"],
                                        status=new_status,
                                        priority=new_priority,
                                        resolved_date=resolved_date,
                                        comments=comments,
                                        old_status=ticket_data["Status"],
                                        old_priority=ticket_data["Priority"],
                                        ticket_id=ticket_data["ID"],
                                        creator_name=ticket_data.get("Created By", "Unknown"),
                                        assigned_name=ticket_data.get("Assigned To", "Unknown"),
                                        new_notify=new_notify,
                                        old_notify=ticket_data["Notify"],
                                        uploaded_files=update_uploaded_files if update_uploaded_files else None,
                                    )

                                    if success:
                                        st.success(f"✅ Ticket **{selected_ticket}** updated successfully!")
                                        if update_uploaded_files:
                                            st.success(
                                                f"📎 {len(update_uploaded_files)} file(s) sent via Slack."
                                            )
                                        st.session_state.df = fetch_tickets_from_notion()
                                        st.session_state.original_df = st.session_state.df.copy()
                                        st.rerun()
                                    else:
                                        st.error("❌ Failed to update the ticket.")

                                except Exception as e:
                                    st.error(f"🚨 Error updating ticket: {e}")
        showcase(key="update_ticket")
    # ── Analytics tab ─────────────────────────────────────────────────────────
    with col3:
        if "df" not in st.session_state:
            st.session_state.df = fetch_tickets_from_notion()
            st.session_state.original_df = st.session_state.df.copy()

        display_analytics_dashboard(st.session_state.df)

    st.divider()


def calculate_analytics_metrics(df):
    """Calculate key analytics metrics."""
    if df.empty:
        return {}

    pkt = pytz.timezone("Asia/Karachi")

    metrics = {
        "total_tickets": len(df),
        "open_tickets": len(df[df["Status"] == "Open"]),
        "in_progress_tickets": len(df[df["Status"] == "In Progress"]),
        "closed_tickets": len(df[df["Status"] == "Closed"]),
        "high_priority": len(df[df["Priority"] == "High"]),
        "medium_priority": len(df[df["Priority"] == "Medium"]),
        "low_priority": len(df[df["Priority"] == "Low"]),
    }

    # Calculate average resolution time
    closed_tickets = df[df["Status"] == "Closed"].copy()
    if not closed_tickets.empty:
        closed_tickets["resolution_days"] = (
                pd.to_datetime(closed_tickets["Resolved Date"]) -
                pd.to_datetime(closed_tickets["Date Submitted"])
        ).dt.days
        metrics["avg_resolution_time"] = closed_tickets["resolution_days"].mean()
        metrics["max_resolution_time"] = closed_tickets["resolution_days"].max()
        metrics["min_resolution_time"] = closed_tickets["resolution_days"].min()
    else:
        metrics["avg_resolution_time"] = 0
        metrics["max_resolution_time"] = 0
        metrics["min_resolution_time"] = 0

    # Calculate overdue tickets
    open_tickets = df[df["Status"].isin(["Open", "In Progress"])].copy()
    if not open_tickets.empty:
        today = datetime.datetime.now(pkt).date()  # FIX: was datetime.now(pkt).date()
        open_tickets["Date Submitted"] = pd.to_datetime(open_tickets["Date Submitted"])
        open_tickets["days_open"] = (today - open_tickets["Date Submitted"].dt.date).apply(lambda x: x.days)

        # Tickets open for more than 7 days
        metrics["overdue_tickets"] = len(open_tickets[open_tickets["days_open"] > 7])
        metrics["oldest_ticket_days"] = open_tickets["days_open"].max()
    else:
        metrics["overdue_tickets"] = 0
        metrics["oldest_ticket_days"] = 0

    return metrics


def display_analytics_dashboard(df):
    """Display comprehensive analytics dashboard."""

    if df.empty:
        st.warning("⚠️ No data available for analytics")
        return

    st.header("📊 Ticket Analytics Dashboard")

    metrics = calculate_analytics_metrics(df)

    # Display KPI Cards
    st.subheader("📈 Key Performance Indicators")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label="Total Tickets",
            value=metrics["total_tickets"],
            delta="All Time"
        )

    with col2:
        st.metric(
            label="Active Tickets",
            value=metrics["open_tickets"] + metrics["in_progress_tickets"],
            delta_color="inverse"
        )

    with col3:
        st.metric(
            label="Closed Tickets",
            value=metrics["closed_tickets"],
            delta="Completed"
        )

    with col4:
        st.metric(
            label="Avg Resolution",
            value=f"{metrics['avg_resolution_time']:.1f} days",
            delta="Average"
        )

    st.divider()

    # Ticket Status Overview
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🎯 Ticket Status Distribution")
        status_data = pd.DataFrame({
            "Status": ["Open", "In Progress", "Closed"],
            "Count": [
                metrics["open_tickets"],
                metrics["in_progress_tickets"],
                metrics["closed_tickets"]
            ],
            "Color": ["#FF6B6B", "#FFA94D", "#51CF66"]
        })

        fig_status = px.pie(
            status_data,
            values="Count",
            names="Status",
            title="Tickets by Status",
            color_discrete_map=dict(zip(status_data["Status"], status_data["Color"]))
        )
        fig_status.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig_status, width="stretch")

    with col2:
        st.subheader("🔥 Priority Distribution")
        priority_data = pd.DataFrame({
            "Priority": ["High", "Medium", "Low"],
            "Count": [
                metrics["high_priority"],
                metrics["medium_priority"],
                metrics["low_priority"]
            ],
            "Color": ["#FF6B6B", "#FFA94D", "#74C0FC"]
        })

        fig_priority = px.pie(
            priority_data,
            values="Count",
            names="Priority",
            title="Tickets by Priority",
            color_discrete_map=dict(zip(priority_data["Priority"], priority_data["Color"]))
        )
        fig_priority.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig_priority, width="stretch")

    st.divider()

    # Tickets Over Time
    st.subheader("📅 Tickets Created Over Time")

    df_copy = df.copy()
    df_copy["Date Submitted"] = pd.to_datetime(df_copy["Date Submitted"])
    df_copy["Date"] = df_copy["Date Submitted"].dt.date

    tickets_by_date = df_copy.groupby("Date").size().reset_index(name="Count")
    tickets_by_date["Cumulative"] = tickets_by_date["Count"].cumsum()

    fig_timeline = go.Figure()

    fig_timeline.add_trace(go.Bar(
        x=tickets_by_date["Date"],
        y=tickets_by_date["Count"],
        name="Daily Tickets",
        marker_color="#4C72B0",
        yaxis="y1"
    ))

    fig_timeline.add_trace(go.Scatter(
        x=tickets_by_date["Date"],
        y=tickets_by_date["Cumulative"],
        name="Cumulative Tickets",
        marker_color="#DD8452",
        yaxis="y2",
        mode="lines+markers"
    ))

    fig_timeline.update_layout(
        xaxis_title="Date",
        yaxis=dict(title="Daily Tickets"),
        yaxis2=dict(title="Cumulative Tickets", overlaying="y", side="right"),
        hovermode="x unified"
    )

    st.plotly_chart(fig_timeline, width="stretch")

    st.divider()

    # Performance Metrics
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            label="⏱️ Max Resolution Time",
            value=f"{metrics['max_resolution_time']:.0f} days",
            delta="Highest"
        )

    with col2:
        st.metric(
            label="⚡ Min Resolution Time",
            value=f"{metrics['min_resolution_time']:.0f} days",
            delta="Lowest"
        )

    with col3:
        st.metric(
            label="⚠️ Overdue Tickets",
            value=metrics["overdue_tickets"],
            delta_color="inverse"
        )

    st.divider()

    # Tickets by Priority & Status
    st.subheader("🔍 Tickets by Priority and Status")

    priority_status = pd.crosstab(
        df["Priority"],
        df["Status"],
        margins=True
    )

    fig_matrix = go.Figure(data=go.Heatmap(
        z=priority_status.iloc[:-1, :-1].values,
        x=priority_status.columns[:-1],
        y=priority_status.index[:-1],
        colorscale="RdYlGn_r",
        text=priority_status.iloc[:-1, :-1].values,
        texttemplate="%{text}",
        textfont={"size": 12}
    ))

    fig_matrix.update_layout(
        title="Priority × Status Matrix",
        xaxis_title="Status",
        yaxis_title="Priority"
    )

    st.plotly_chart(fig_matrix, width="stretch")

    st.divider()

    # Team Performance
    st.subheader("👥 Team Performance")

    col1, col2 = st.columns(2)

    with col1:
        st.write("**Tickets Created By:**")
        created_by = df["Created By"].value_counts().head(10)
        fig_created = px.bar(
            x=created_by.values,
            y=created_by.index,
            orientation="h",
            title="Top 10 Ticket Creators",
            labels={"x": "Count", "y": "User"}
        )
        fig_created.update_layout(height=400)
        st.plotly_chart(fig_created, width="stretch")

    with col2:
        st.write("**Tickets Assigned To:**")
        assigned_to = df["Assigned To"].value_counts().head(10)
        fig_assigned = px.bar(
            x=assigned_to.values,
            y=assigned_to.index,
            orientation="h",
            title="Top 10 Assignees",
            labels={"x": "Count", "y": "User"},
            color_discrete_sequence=["#FF6B6B"]
        )
        fig_assigned.update_layout(height=400)
        st.plotly_chart(fig_assigned, width="stretch")

    st.divider()

    # Personal vs Normal Tickets
    st.subheader("📋 Ticket Type Breakdown")

    col1, col2 = st.columns(2)

    with col1:
        ticket_type_count = df["Ticket Type"].value_counts()
        fig_type = px.pie(
            values=ticket_type_count.values,
            names=ticket_type_count.index,
            title="Personal vs Normal Tickets",
            color_discrete_map={"Personal": "#9D4EDD", "Normal": "#3A86FF"}
        )
        fig_type.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig_type, width="stretch")

    with col2:
        # Resolution Rate
        total = len(df)
        closed = len(df[df["Status"] == "Closed"])
        resolution_rate = (closed / total * 100) if total > 0 else 0

        fig_resolution = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=resolution_rate,
            title={'text': "Resolution Rate (%)"},
            delta={'reference': 100},
            gauge={
                'axis': {'range': [0, 100]},
                'bar': {'color': "darkblue"},
                'steps': [
                    {'range': [0, 50], 'color': "lightgray"},
                    {'range': [50, 100], 'color': "gray"}
                ],
                'threshold': {
                    'line': {'color': "red", 'width': 4},
                    'thickness': 0.75,
                    'value': 100
                }
            }
        ))
        st.plotly_chart(fig_resolution, width="stretch")

    st.divider()

    # Detailed Analytics Table
    st.subheader("📊 Detailed Analytics")

    analytics_data = {
        "Metric": [
            "Total Tickets",
            "Open",
            "In Progress",
            "Closed",
            "High Priority",
            "Medium Priority",
            "Low Priority",
            "Personal Tickets",
            "Normal Tickets",
            "Avg Resolution Time (days)",
            "Overdue Tickets (>7 days)",
            "Oldest Ticket (days)",
            "Resolution Rate (%)"
        ],
        "Value": [
            metrics["total_tickets"],
            metrics["open_tickets"],
            metrics["in_progress_tickets"],
            metrics["closed_tickets"],
            metrics["high_priority"],
            metrics["medium_priority"],
            metrics["low_priority"],
            len(df[df["Ticket Type"] == "Personal"]),
            len(df[df["Ticket Type"] == "Normal"]),
            f"{metrics['avg_resolution_time']:.2f}",
            metrics["overdue_tickets"],
            metrics["oldest_ticket_days"],
            f"{(len(df[df['Status'] == 'Closed']) / len(df) * 100):.2f}" if len(df) > 0 else "0"
        ]
    }

    analytics_df = pd.DataFrame(analytics_data)
    st.dataframe(analytics_df, width="stretch", hide_index=True)

    # Export Analytics
    st.divider()
    st.subheader("📥 Export Analytics")

    col1, col2 = st.columns(2)

    with col1:
        csv = analytics_df.to_csv(index=False)
        st.download_button(
            label="📊 Download Analytics CSV",
            data=csv,
            file_name=f"ticket_analytics_{datetime.datetime.now().strftime('%Y-%m-%d')}.csv",  # FIX
            mime="text/csv"
        )

    with col2:
        # Create summary report
        summary_report = f"""
TICKET ANALYTICS REPORT
Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

SUMMARY
-------
Total Tickets: {metrics['total_tickets']}
Active Tickets: {metrics['open_tickets'] + metrics['in_progress_tickets']}
Closed Tickets: {metrics['closed_tickets']}

STATUS BREAKDOWN
----------------
Open: {metrics['open_tickets']} ({metrics['open_tickets'] / metrics['total_tickets'] * 100:.1f}%)
In Progress: {metrics['in_progress_tickets']} ({metrics['in_progress_tickets'] / metrics['total_tickets'] * 100:.1f}%)
Closed: {metrics['closed_tickets']} ({metrics['closed_tickets'] / metrics['total_tickets'] * 100:.1f}%)

PRIORITY BREAKDOWN
------------------
High Priority: {metrics['high_priority']} ({metrics['high_priority'] / metrics['total_tickets'] * 100:.1f}%)
Medium Priority: {metrics['medium_priority']} ({metrics['medium_priority'] / metrics['total_tickets'] * 100:.1f}%)
Low Priority: {metrics['low_priority']} ({metrics['low_priority'] / metrics['total_tickets'] * 100:.1f}%)

PERFORMANCE METRICS
-------------------
Average Resolution Time: {metrics['avg_resolution_time']:.2f} days
Max Resolution Time: {metrics['max_resolution_time']:.0f} days
Min Resolution Time: {metrics['min_resolution_time']:.0f} days
Overdue Tickets (>7 days): {metrics['overdue_tickets']}
Oldest Ticket: {metrics['oldest_ticket_days']} days
Resolution Rate: {(metrics['closed_tickets'] / metrics['total_tickets'] * 100):.2f}%
        """

        st.download_button(
            label="📄 Download Full Report",
            data=summary_report,
            file_name=f"ticket_report_{datetime.datetime.now().strftime('%Y-%m-%d')}.txt",  # FIX
            mime="text/plain"
        )


def display_user_analytics(df, username):
    """Display analytics for a specific user."""

    user_df = df[
        (df["Created By"] == username) | (df["Assigned To"] == username)
        ].copy()

    if user_df.empty:
        st.warning(f"No data available for {username}")
        return

    st.subheader(f"👤 {username} - Personal Analytics")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        created = len(df[df["Created By"] == username])
        st.metric("Tickets Created", created)

    with col2:
        assigned = len(df[df["Assigned To"] == username])
        st.metric("Tickets Assigned", assigned)

    with col3:
        closed = len(user_df[user_df["Status"] == "Closed"])
        st.metric("Tickets Closed", closed)

    with col4:
        resolution_rate = (closed / len(user_df) * 100) if len(user_df) > 0 else 0
        st.metric("Resolution Rate", f"{resolution_rate:.1f}%")

    col1, col2 = st.columns(2)

    with col1:
        status_counts = user_df["Status"].value_counts()
        fig = px.pie(
            values=status_counts.values,
            names=status_counts.index,
            title=f"{username}'s Tickets by Status"
        )
        st.plotly_chart(fig, width="stretch")

    with col2:
        priority_counts = user_df["Priority"].value_counts()
        fig = px.pie(
            values=priority_counts.values,
            names=priority_counts.index,
            title=f"{username}'s Tickets by Priority"
        )
        st.plotly_chart(fig, width="stretch")


if __name__ == "__main__":
    main()