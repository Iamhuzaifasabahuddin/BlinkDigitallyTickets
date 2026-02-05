import datetime
import os

import pandas as pd
import pytz
import streamlit as st
from notion_client import Client
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

hide_st_style = """
    <style>   
    ._link_gzau3_10 {visibility: hidden;}
    ._profilePreview_gzau3_63 {visibility: hidden;}
    .st-emotion-cache-scp8yw{visibility: hidden;}
    </style>
    """
st.markdown(hide_st_style, unsafe_allow_html=True)
st.set_page_config(page_title="Support tickets", page_icon="🎫", layout="centered")
st.title("🎫 Support Tickets for Blink Digitally")
st.write(
    """
    Use this app to submit in any publishing updates, republication details, or reminders.
    """
)
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
                results = notion.data_sources.query(data_source_id=DATASOURCE_ID,
                                                 sorts=[{"timestamp": "created_time", "direction": "ascending"}])

            for page in results["results"]:
                props = page["properties"]

                ticket_id = props["ID"]["title"][0]["text"]["content"] if props["ID"]["title"] else ""
                if not ticket_id or "-" not in ticket_id:
                    ticket_id = "TICKET-0001"

                ticket = {
                    "page_id": page["id"],
                    "ID": ticket_id,
                    "Issue": props["Issue"]["rich_text"][0]["text"]["content"] if props["Issue"]["rich_text"] else "",
                    "Status": props["Status"]["select"]["name"] if props["Status"]["select"] else "Open",
                    "Priority": props["Priority"]["select"]["name"] if props["Priority"]["select"] else "Medium",
                    "Date Submitted": props["Date Submitted"]["date"]["start"] if props["Date Submitted"][
                        "date"] else "",
                    "Submitted Time": props["Submitted Time"]["rich_text"][0]["text"] ["content"] if props["Submitted Time"]["rich_text"] else "",
                    "Created By": props["Created By"]["select"]["name"] if props["Created By"]["select"][
                        "name"] else "",
                    "Assigned To": props["Assigned To"]["select"]["name"] if props["Assigned To"]["select"][
                        "name"] else "",
                    "Resolved Date": props["Resolved Date"]["date"]["start"] if props.get("Resolved Date") and
                                                                                props["Resolved Date"][
                                                                                    "date"] else None,
                    "Resolved Time": props["Resolved Time"]["rich_text"][0]["text"] ["content"] if props["Resolved Time"]["rich_text"] else "",
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
                df["Date Submitted"] = pd.to_datetime(df["Date Submitted"],format="%Y-%m-%d", errors='coerce')
            if "Resolved Date" in df.columns:
                df["Resolved Date"] = pd.to_datetime(df["Resolved Date"], format="%Y-%m-%d", errors='coerce')

        return df
    except Exception as e:
        st.error(f"Error fetching tickets from Notion: {e}")
        return pd.DataFrame(columns=["page_id", "ID", "Issue", "Status", "Priority", "Date Submitted", "Submitted Time", "Resolved Date", "Resolved Time", "Comments", "Ticket Type"])


def send_ticket_notifications(ticket_id, issue, priority, status,date, time,  user_details, creator_name, assigned_name):
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

*❓ Issue:*
{issue}

Please review and update the ticket status accordingly."""

            send_dm(user_details['receiver_id'], assigned_message)
            print(f"✅ Notification sent to {assigned_name} ({user_details['receiver_email']})")
        else:
            print(f"⚠️ Could not send notification to {assigned_name} - Slack ID not found")

        if user_details['sender_id'] and user_details['sender_id'] != user_details['receiver_id']:
            creator_message = f"""✅ *Ticket Created Successfully*

*🆔 Ticket ID:* {ticket_id}
*⏰ Priority:* {priority}
*📊 Status:* {status}
*📅 Created Date (PKST):* {date}
*⌛ Created Time (PKST):* {time}
*📕 Assigned To:* {assigned_name}

*❓ Issue:*
{issue}

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
        # Get email addresses from name_all dictionary
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


def create_ticket_in_notion(ticket_id, issue, status, priority, date_submitted, name, assigned):
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

        notion.pages.create(
            parent={"data_source_id": DATASOURCE_ID},
            properties={
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
        )

        user_details = get_user_details(name, assigned)
        send_ticket_notifications(ticket_id, issue, priority, status,formatted_date, formatted_time, user_details, name, assigned)
        return True
    except Exception as e:
        st.error(f"Error creating ticket: {e}")
        return False


def send_ticket_update_notifications(ticket_id, old_status, new_status, old_priority, new_priority,
                                     issue, creator_name, assigned_name, comments, resolved_date=None):
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
        if not changes:
            return

        changes_text = "\n".join(changes)

        user_details = get_user_details(creator_name, assigned_name)

        if user_details['receiver_id']:
            assigned_message = f"""🔔 *Ticket Updated*

*🆔 Ticket ID:* {ticket_id}
*➕ Created By:* {creator_name}

*✏ Changes:*
{changes_text}

*❓ Issue:*
{issue}"""

            send_dm(user_details['receiver_id'], assigned_message)
            print(f"✅ Update notification sent to {assigned_name} ({user_details['receiver_email']})")

        if user_details['sender_id'] and user_details['sender_id'] != user_details['receiver_id']:
            creator_message = f"""🔔 *Your Ticket Was Updated*

*🆔 Ticket ID:* {ticket_id}
*📕 Assigned To:* {assigned_name}

*✏ Changes:*
{changes_text}

*❓ Issue:*
{issue}"""

            send_dm(user_details['sender_id'], creator_message)
            print(f"✅ Update notification sent to {creator_name} ({user_details['sender_email']})")

    except Exception as e:
        print(f"❌ Error sending update notifications: {e}")


def update_ticket_in_notion(page_id, issue, status, priority, resolved_date, comments,
                            old_status=None, old_priority=None, ticket_id=None,
                            creator_name=None, assigned_name=None, new_notify=None, old_notify=None):
    """Update an existing ticket in Notion and send notifications."""
    try:
        properties = {
            "Issue": {"rich_text": [{"text": {"content": issue}}]},
            "Status": {"select": {"name": status}},
            "Priority": {"select": {"name": priority}},
        }

        if resolved_date and pd.notna(resolved_date):
            if isinstance(resolved_date, (pd.Timestamp, datetime.datetime, datetime.date)):
                resolved_date_str = resolved_date.strftime("%Y-%m-%d") if hasattr(resolved_date, 'strftime') else str(
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
                ticket_id, old_status, status, old_priority, priority,
                issue, creator_name, assigned_name,
                comments,
                formatted_resolved_date,
            )
            if new_notify != old_notify and new_notify:
                st.success(f"{ticket_id} Notification Updated to {new_notify}")
        return True
    except Exception as e:
        st.error(f"Error updating ticket: {e}")
        return False


if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

with st.sidebar:
    st.header("🔐 Admin Access")
    if not st.session_state.authenticated:
        password_input = st.text_input("Enter admin password:", type="password", key="password")
        if st.button("Login"):
            if password_input == ADMIN_PASSWORD:
                st.session_state.authenticated = True
                st.success("Access granted!")
                st.rerun()
            else:
                st.error("Incorrect password")
    else:
        st.success("✅ Authenticated")
        if st.button("Logout"):
            st.session_state.authenticated = False
            st.rerun()

if st.button("🔄 Fetch Latest"):
    with st.spinner("Loading tickets from Notion..."):
        st.session_state.df = fetch_tickets_from_notion()
        st.session_state.original_df = st.session_state.df.copy()

col1, col2 = st.tabs(["Add Ticket", "Update Ticket"])

with col1:
    st.header("➕ Add a New Ticket")
    pkt = pytz.timezone("Asia/Karachi")
    now_pkt = datetime.datetime.now(pkt)

    with st.form("add_ticket_form"):
        issue = st.text_area("Describe the issue")
        today = st.date_input("Date (PKST)", now_pkt.date())
        priority = st.selectbox("Priority", ["High", "Medium", "Low"])
        name = st.selectbox("Created By", st.secrets.get("NAMES", ""))
        assigned = st.selectbox("Assigned To", st.secrets.get("NAMES", ""), index=st.secrets.get("NAMES", "").index("Huzaifa Sabah Uddin"))
        submitted = st.form_submit_button("Submit")

    if submitted:
        if not issue.strip():
            st.error("⚠️ Please describe the issue before submitting.")
        elif not name or not assigned:
            st.warning("⚠️ Please select both 'Created By' and 'Assigned To' before submitting.")
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
                            latest_id = latest_id_prop[0]["text"]["content"] if latest_id_prop else "TICKET-0000"

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
                            new_ticket_id, issue, "Open", priority, today, name, assigned
                        )

                        if success:
                            st.success(f"✅ Ticket **{new_ticket_id}** created successfully in Notion!")
                            st.session_state.df = fetch_tickets_from_notion()
                            st.session_state.original_df = st.session_state.df.copy()
                            st.rerun()
                        else:
                            st.error("❌ Failed to create the ticket in Notion. Please try again later.")

                    except Exception as e:
                        st.error(f"🚨 Error while creating ticket in Notion: {e}")
            except Exception as e:
                st.error(f"🚨 Error while creating ticket in Notion: {e}")

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

            st.markdown(f"<h3>📄 <b>Issue:</b> {ticket_data['Issue']}</h3>", unsafe_allow_html=True)
            st.markdown(f"<p style='font-size:20px;'>📊 <b>Current Status:</b> {ticket_data['Status']}</p>",
                        unsafe_allow_html=True)
            st.markdown(f"<p style='font-size:20px;'>⏰ <b>Current Priority:</b> {ticket_data['Priority']}</p>",
                        unsafe_allow_html=True)
            st.markdown(f"<p style='font-size:20px;'>➕ <b>Created By:</b> {ticket_data['Created By']}</p>",
                        unsafe_allow_html=True)
            st.markdown(f"<p style='font-size:20px;'>📕 <b>Assigned To:</b> {ticket_data['Assigned To']}</p>",
                        unsafe_allow_html=True)
            new_notify = ticket_data["Notify"]
        if st.session_state.authenticated:
            new_notify = st.selectbox("Update Notify", ["Yes", "No"], index=["Yes", "No"].index(ticket_data["Notify"]))
        with st.form("update_ticket_form"):
                new_status = st.selectbox("Update Status",
                                          ["Open", "In Progress", "Closed"],
                                          index=["Open", "In Progress", "Closed"].index(ticket_data["Status"]))

                new_priority = st.selectbox("Update Priority",
                                            ["High", "Medium", "Low"],
                                            index=["High", "Medium", "Low"].index(ticket_data["Priority"]))

                resolved_date = None
                if new_status == "Closed":
                    resolved_date = st.date_input("Resolved Date (PKST)", now_pkt.date())

                comments = st.text_area("Comments")

                update_submitted = st.form_submit_button("Update Ticket")

                has_changes = (
                        new_status != ticket_data["Status"] or
                        new_priority != ticket_data["Priority"] or
                        comments.strip() != ""
                )

                if update_submitted and not has_changes:
                    st.warning("⚠️ No changes detected for this ticket.")
                if update_submitted and has_changes:
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
                                old_notify=ticket_data["Notify"]
                            )

                            if success:
                                st.success(f"✅ Ticket **{selected_ticket}** updated successfully!")
                                st.session_state.df = fetch_tickets_from_notion()
                                st.session_state.original_df = st.session_state.df.copy()
                                st.rerun()
                            else:
                                st.error("❌ Failed to update the ticket.")
                        except Exception as e:
                            st.error(f"🚨 Error updating ticket: {e}")
st.divider()

if "df" not in st.session_state:
    st.session_state.df = fetch_tickets_from_notion()
    st.session_state.original_df = st.session_state.df.copy()

df = st.session_state.df.copy()

df["Month"] = df["Date Submitted"].dt.strftime("%B")

unique_months = sorted(df["Month"].unique().tolist())
months = ["All"] + unique_months

current_month = datetime.datetime.now(pkt).strftime("%B")
default_index = months.index("All") if current_month in months else 0

selected_month = st.selectbox("📅 Choose a month to filter tickets", months, index=default_index)
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

if st.session_state.authenticated:
    st.info(
        "You can edit tickets by double-clicking a cell. Click 'Save Changes to Notion' "
        "to sync your edits. You can also sort columns by clicking headers.",
        icon="✍️",
    )

display_active_df = active_df.drop(columns=["page_id", "Month", "Resolved Time"], errors="ignore")

disabled_columns = ["ID", "Date Submitted", "Month", "Resolved Time", "Submitted Time",  "Created By", "Assigned To", "Ticket Type"]
if not st.session_state.authenticated:
    disabled_columns = list(display_active_df.columns)

edited_active_df = st.data_editor(
    display_active_df,
    width="stretch",
    hide_index=True,
    key="active_editor",
    column_config={
        "Status": st.column_config.SelectboxColumn("Status", options=["Open", "In Progress", "Closed"], required=True),
        "Priority": st.column_config.SelectboxColumn("Priority", options=["High", "Medium", "Low"], required=True),
        "Date Submitted": st.column_config.DateColumn("Date Submitted", format="YYYY-MM-DD"),
        "Resolved Date": st.column_config.DateColumn("Resolved Date", format="YYYY-MM-DD"),
    },
    disabled=disabled_columns,
)

if st.session_state.authenticated and not edited_active_df.equals(display_active_df):
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

        disabled_closed_columns = ["ID", "Date Submitted", "Month", "Resolved Time", "Submitted Time", "Created By", "Assigned To", "Ticket Type"]
        if not st.session_state.authenticated:
            disabled_closed_columns = list(display_closed_df.columns)

        edited_closed_df = st.data_editor(
            display_closed_df,
            width="stretch",
            hide_index=True,
            key="closed_editor",
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

        if st.session_state.authenticated and not edited_closed_df.equals(display_closed_df):
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
