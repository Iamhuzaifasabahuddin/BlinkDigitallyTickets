import os

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

bot = WebClient(token=os.environ['SLACK_BOT_TOKEN'])


def get_user_id_by_email(email):
    try:
        response = bot.users_lookupByEmail(email=email)
        return response['user']['id']
    except SlackApiError as e:
        print(f"Error finding user: {e.response['error']}")
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
    send_dm(get_user_id_by_email('huzaifa.sabah@topsoftdigitals.pk'),
            "🔔 Reminder: Check your open tickets!")
