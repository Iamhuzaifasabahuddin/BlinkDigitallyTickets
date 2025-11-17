import os
from collections import defaultdict
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from notion_client import Client
import pandas as pd

bot = WebClient(token=os.environ['SLACK_BOT_TOKEN'])

notion_token = os.environ['NOTION_TOKEN']
notion = Client(auth=notion_token)

DATABASE_ID = os.environ['NOTION_DATABASE_ID']

def fetch_tickets_from_notion():
    """Fetch all tickets from Notion database with pagination."""
    try:
        tickets = []
        has_more = True
        start_cursor = None
        while has_more:
            if start_cursor:
                results = notion.data_sources.query(
                    data_source_id=DATABASE_ID,
                    start_cursor=start_cursor,
                    sorts=[{"timestamp": "created_time", "direction": "descending"}]
                )
            else:
                results = notion.data_sources.query(data_source_id=DATABASE_ID,
                                                 sorts=[{"timestamp": "created_time", "direction": "descending"}])

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

        df = df[df["Status"].isin(["Open", "In Progress"])]

        name_list_assigned = df["Assigned To"].unique().tolist()
        name_list_created = df["Created By"].unique().tolist()
        combined = list(set(name_list_assigned + name_list_created))

        ticket_list = defaultdict(list)

        for name in combined:
            tickets = df[(df["Created By"] == name) | (df["Assigned To"] == name)]

            ticket_list[name].extend(tickets["ID"].tolist())

        return combined, ticket_list
    except Exception as e:
        print(e)
        return pd.DataFrame()

def get_user_id_by_email(email):
    try:
        response = bot.users_lookupByEmail(email=email)
        return response['user']['id']
    except SlackApiError as e:
        print(f"Error finding user: {e.response['error']} {email}")
        return None


def send_dm(user_id, message):
    try:
        response = bot.chat_postMessage(
            channel=user_id,
            text=message
        )
    except SlackApiError as e:
        print(f"❌ Error sending message: {e.response['error']}")


if __name__ == '__main__':
    names = {
        "Aiza Ali": "aiza.ali@topsoftdigitals.pk",
        "Ahmed Asif": "ahmed.asif@topsoftdigitals.pk",
        "Asad Waqas": "asad.waqas@topsoftdigitals.pk",
        "Kamal Muhammad Issa" : "kamal.muhammed.issa@topsoftdigitals.pk",
        "Maheen Sami": "maheen.sami@topsoftdigitals.pk",
        "Mubashir Khan": "Mubashir.khan@topsoftdigitals.pk",
        "Muhammad Ali": "muhammad.ali@topsoftdigitals.pk",
        "Valencia Angelo": "valencia.angelo@topsoftdigitals.pk",
        "Ukasha Asadullah": "ukasha.asadullah@topsoftdigitals.pk",
        "Ahsan Javed": "ahsan.javed@topsoftdigitals.pk",
        "Youha": "youha.khan@topsoftdigitals.pk",
        "Emaan Zaidi": "emaan.zaidi@topsoftdigitals.pk",
        "Elishba": "elishba@topsoftdigitals.pk",
        "Shahrukh Yousuf": "shahrukh.yousuf@topsoftdigitals.pk",
        "Hassan Siddiqui": "hassan.siddiqui@topsoftdigitals.pk",
        "Farman Ali": "farmanali@topsoftdigitals.pk"
    }
    name_list, ticket_dict = fetch_tickets_from_notion()
    name_list = [name for name in name_list if name != "Huzaifa Sabah Uddin"]
    hexz_id = get_user_id_by_email("huzaifa.sabah@topsoftdigitals.pk")
    for name in name_list:
        id_ = get_user_id_by_email(names.get(name))
        message = (
            f"🔔 *Reminder for:* *<@{id_}>* \n"
            f"‼ Please check your open tickets @ https://blinkdigitallytickets.streamlit.app/ and provide an update to *<@{hexz_id}>* or update it on the app when possible. 📝"
        )
        send_dm(
            id_,
            message
        )
        send_dm(
            hexz_id,
        f"🚀 Notification sent to *<@{id_}>*!")
    send_dm(hexz_id,
            "🔔 Reminder: Check your open tickets!")