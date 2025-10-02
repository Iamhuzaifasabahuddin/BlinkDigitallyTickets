import datetime
import os

import pandas as pd
import pytz
import streamlit as st
from notion_client import Client

# Show app title and description.
st.set_page_config(page_title="Support tickets", page_icon="🎫", layout="centered")
st.title("🎫 Support Tickets for Blink Digitally")
st.write(
    """
    Use this app to submit in any publishing updates, republication details, or reminders.
    """
)


@st.cache_resource
def get_notion_client():
    notion_token = os.getenv("NOTION_TOKEN") or st.secrets.get("NOTION_TOKEN", "")
    if not notion_token:
        st.error("Please set NOTION_TOKEN in your environment or Streamlit secrets.")
        st.stop()
    return Client(auth=notion_token)


DATABASE_ID = os.getenv("NOTION_DATABASE_ID") or st.secrets.get("NOTION_DATABASE_ID", "")
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


def fetch_tickets_from_notion():
    """Fetch all tickets from Notion database with pagination."""
    try:
        tickets = []
        has_more = True
        start_cursor = None
        while has_more:
            if start_cursor:
                results = notion.databases.query(
                    database_id=DATABASE_ID,
                    start_cursor=start_cursor
                )
            else:
                results = notion.databases.query(database_id=DATABASE_ID)

            for page in results["results"]:
                props = page["properties"]

                ticket_id = props["ID"]["title"][0]["text"]["content"] if props["ID"]["title"] else ""
                if not ticket_id or "-" not in ticket_id:
                    ticket_id = "TICKET-1000"

                ticket = {
                    "page_id": page["id"],
                    "ID": ticket_id,
                    "Issue": props["Issue"]["rich_text"][0]["text"]["content"] if props["Issue"]["rich_text"] else "",
                    "Status": props["Status"]["select"]["name"] if props["Status"]["select"] else "Open",
                    "Priority": props["Priority"]["select"]["name"] if props["Priority"]["select"] else "Medium",
                    "Date Submitted": props["Date Submitted"]["date"]["start"] if props["Date Submitted"][
                        "date"] else "",
                    "Created By": props["Created By"]["select"]["name"] if props["Created By"]["select"]["name"] else "",
                    "Resolved Date": props["Resolved Date"]["date"]["start"] if props.get("Resolved Date") and
                                                                                props["Resolved Date"][
                                                                                    "date"] else None,
                }
                tickets.append(ticket)

            has_more = results.get("has_more", False)
            start_cursor = results.get("next_cursor", None)

        df = pd.DataFrame(tickets)

        # Convert date columns to datetime
        if not df.empty:
            if "Date Submitted" in df.columns:
                df["Date Submitted"] = pd.to_datetime(df["Date Submitted"], errors='coerce')
            if "Resolved Date" in df.columns:
                df["Resolved Date"] = pd.to_datetime(df["Resolved Date"], errors='coerce')

        return df
    except Exception as e:
        st.error(f"Error fetching tickets from Notion: {e}")
        return pd.DataFrame(columns=["page_id", "ID", "Issue", "Status", "Priority", "Date Submitted", "Resolved Date"])


def create_ticket_in_notion(ticket_id, issue, status, priority, date_submitted, name):
    """Create a new ticket in Notion database."""
    try:
        notion.pages.create(
            parent={"database_id": DATABASE_ID},
            properties={
                "ID": {"title": [{"text": {"content": ticket_id}}]},
                "Issue": {"rich_text": [{"text": {"content": issue}}]},
                "Status": {"select": {"name": status}},
                "Priority": {"select": {"name": priority}},
                "Created By": {"select": {"name": name}},
                "Date Submitted": {"date": {"start": date_submitted}},
            }
        )
        return True
    except Exception as e:
        st.error(f"Error creating ticket: {e}")
        return False


def update_ticket_in_notion(page_id, issue, status, priority, resolved_date):
    """Update an existing ticket in Notion."""
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
                properties["Resolved Date"] = {"date": {"start": resolved_date_str}}
        else:
            properties["Resolved Date"] = {"date": None}

        notion.pages.update(
            page_id=page_id,
            properties=properties
        )
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

if "df" not in st.session_state or st.button("🔄 Refresh from Notion"):
    with st.spinner("Loading tickets from Notion..."):
        st.session_state.df = fetch_tickets_from_notion()
        st.session_state.original_df = st.session_state.df.copy()

st.header("Add a ticket")

pkt = pytz.timezone("Asia/Karachi")
now_pkt = datetime.datetime.now(pkt)
with st.form("add_ticket_form"):
    issue = st.text_area("Describe the issue")
    today = st.date_input("Date", now_pkt.date())
    priority = st.selectbox("Priority", ["High", "Medium", "Low"])
    name = st.selectbox("PM", st.secrets.get("NAMES", ""))
    submitted = st.form_submit_button("Submit")

if submitted:
    if not issue.strip():
        st.error("Please describe the issue before submitting.")
    else:
        with st.spinner("Fetching latest ticket from Notion..."):
            try:
                results = notion.databases.query(
                    database_id=DATABASE_ID,
                    page_size=1,
                    sorts=[{"timestamp": "created_time", "direction": "descending"}]
                )

                if results["results"]:
                    latest_page = results["results"][0]
                    latest_id = latest_page["properties"]["ID"]["title"][0]["text"]["content"] if \
                        latest_page["properties"]["ID"]["title"] else "TICKET-0000"

                    if "-" in latest_id:
                        recent_ticket_number = int(latest_id.split("-")[1])
                    else:
                        recent_ticket_number = 0000
                else:
                    recent_ticket_number = 0000
            except Exception as e:
                st.warning(f"Could not fetch latest ticket: {e}. Starting from TICKET-1001")
                recent_ticket_number = 0000

        new_ticket_id = f"TICKET-{recent_ticket_number + 1}"

        with st.spinner("Creating ticket in Notion..."):
            success = create_ticket_in_notion(new_ticket_id, issue, "Open", priority, today, name)

        if success:
            st.success("Ticket submitted successfully!")
            st.session_state.df = fetch_tickets_from_notion()
            st.session_state.original_df = st.session_state.df.copy()
            st.rerun()

# Separate active and closed tickets
active_df = st.session_state.df[st.session_state.df["Status"].isin(["Open", "In Progress"])].copy()
closed_df = st.session_state.df[st.session_state.df["Status"] == "Closed"].copy()

st.header("Active Tickets")
st.write(f"Number of active tickets: `{len(active_df)}`")

if st.session_state.authenticated:
    st.info(
        "You can edit the tickets by double clicking on a cell. Click 'Save Changes to Notion' "
        "to sync your edits. You can also sort the table by clicking on the column headers.",
        icon="✍️",
    )
else:
    st.warning("🔒 Login with admin password to edit tickets", icon="⚠️")

display_active_df = active_df.drop(columns=["page_id"]) if "page_id" in active_df.columns else active_df

disabled_columns = ["ID", "Date Submitted"]
if not st.session_state.authenticated:
    disabled_columns = list(display_active_df.columns)

edited_active_df = st.data_editor(
    display_active_df,
    use_container_width=True,
    hide_index=True,
    key="active_editor",
    column_config={
        "Status": st.column_config.SelectboxColumn(
            "Status",
            help="Ticket status",
            options=["Open", "In Progress", "Closed"],
            required=True,
        ),
        "Priority": st.column_config.SelectboxColumn(
            "Priority",
            help="Priority",
            options=["High", "Medium", "Low"],
            required=True,
        ),
        "Date Submitted": st.column_config.DateColumn(
            "Date Submitted",
            help="Date when ticket was submitted",
            format="YYYY-MM-DD",
        ),
        "Resolved Date": st.column_config.DateColumn(
            "Resolved Date",
            help="Date when ticket was resolved",
            format="YYYY-MM-DD",
        ),
    },
    disabled=disabled_columns,
)

if st.session_state.authenticated and not edited_active_df.equals(display_active_df):
    if st.button("💾 Save Changes to Notion", type="primary", key="save_active"):
        with st.spinner("Saving changes to Notion..."):
            success_count = 0
            error_count = 0

            for idx in edited_active_df.index:
                original_row = display_active_df.loc[idx]
                edited_row = edited_active_df.loc[idx]

                if not original_row.equals(edited_row):
                    page_id = active_df.loc[idx, "page_id"]
                    success = update_ticket_in_notion(
                        page_id,
                        edited_row["Issue"],
                        edited_row["Status"],
                        edited_row["Priority"],
                        edited_row["Resolved Date"]
                    )
                    if success:
                        success_count += 1
                    else:
                        error_count += 1

            if success_count > 0:
                st.success(f"✅ {success_count} ticket(s) updated successfully!")
            if error_count > 0:
                st.error(f"❌ {error_count} ticket(s) failed to update")

            st.session_state.df = fetch_tickets_from_notion()
            st.session_state.original_df = st.session_state.df.copy()
            st.rerun()

# Closed Tickets Section
st.divider()
st.header("📦 Closed Tickets")
st.write(f"Number of closed tickets: `{len(closed_df)}`")

if not closed_df.empty:
    with st.expander("View Closed Tickets", expanded=False):
        display_closed_df = closed_df.drop(columns=["page_id"]) if "page_id" in closed_df.columns else closed_df

        disabled_closed_columns = ["ID", "Date Submitted"]
        if not st.session_state.authenticated:
            disabled_closed_columns = list(display_closed_df.columns)

        edited_closed_df = st.data_editor(
            display_closed_df,
            use_container_width=True,
            hide_index=True,
            key="closed_editor",
            column_config={
                "Status": st.column_config.SelectboxColumn(
                    "Status",
                    help="Ticket status",
                    options=["Open", "In Progress", "Closed"],
                    required=True,
                ),
                "Priority": st.column_config.SelectboxColumn(
                    "Priority",
                    help="Priority",
                    options=["High", "Medium", "Low"],
                    required=True,
                ),
                "Date Submitted": st.column_config.DateColumn(
                    "Date Submitted",
                    help="Date when ticket was submitted",
                    format="YYYY-MM-DD",
                ),
                "Resolved Date": st.column_config.DateColumn(
                    "Resolved Date",
                    help="Date when ticket was resolved",
                    format="YYYY-MM-DD",
                ),
            },
            disabled=disabled_closed_columns,
        )

        if st.session_state.authenticated and not edited_closed_df.equals(display_closed_df):
            if st.button("💾 Save Changes to Notion", type="primary", key="save_closed"):
                with st.spinner("Saving changes to Notion..."):
                    success_count = 0
                    error_count = 0

                    for idx in edited_closed_df.index:
                        original_row = display_closed_df.loc[idx]
                        edited_row = edited_closed_df.loc[idx]

                        if not original_row.equals(edited_row):
                            page_id = closed_df.loc[idx, "page_id"]
                            success = update_ticket_in_notion(
                                page_id,
                                edited_row["Issue"],
                                edited_row["Status"],
                                edited_row["Priority"],
                                edited_row["Resolved Date"]
                            )
                            if success:
                                success_count += 1
                            else:
                                error_count += 1

                    if success_count > 0:
                        st.success(f"✅ {success_count} ticket(s) updated successfully!")
                    if error_count > 0:
                        st.error(f"❌ {error_count} ticket(s) failed to update")

                    st.session_state.df = fetch_tickets_from_notion()
                    st.session_state.original_df = st.session_state.df.copy()
                    st.rerun()
else:
    st.info("No closed tickets yet.")