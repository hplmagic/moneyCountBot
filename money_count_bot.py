import logging
import os
import re
from datetime import datetime
from typing import List, Optional

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# ======================
# CONFIGURATION
# ======================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GOOGLE_CREDENTIALS_FILE = "credentials.json"
MASTER_SHEET_ID = os.getenv("MASTER_SHEET_ID")  # The ID of your single, existing Google Sheet
SHEET_NAME = os.getenv("SHEET_NAME", "Sheet1")  # Tab name inside the sheet (default: "Sheet1")

# Column order expected in your sheet (must match your actual header row)
COLUMNS = ["Timestamp", "User", "Name", "Email", "Product", "Status"]  # Customize as needed

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ======================
# GOOGLE SHEETS INTEGRATION
# ======================

def get_sheets_service():
    """Return authenticated Google Sheets service."""
    creds = Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_FILE,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return build("sheets", "v4", credentials=creds)


def get_sheet_data(range_name: str = f"{SHEET_NAME}!A:Z") -> List[List[str]]:
    """Read all data from the sheet."""
    service = get_sheets_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=MASTER_SHEET_ID,
        range=range_name
    ).execute()
    return result.get("values", [])


def append_row(values: List[str]):
    """Append a new row to the sheet."""
    service = get_sheets_service()
    body = {"values": [values]}
    service.spreadsheets().values().append(
        spreadsheetId=MASTER_SHEET_ID,
        range=f"{SHEET_NAME}!A:Z",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body=body
    ).execute()


def update_cell(row_index: int, col_letter: str, value: str):
    """Update a specific cell (e.g., Status in row 5)."""
    service = get_sheets_service()
    range_name = f"{SHEET_NAME}!{col_letter}{row_index}"
    body = {"values": [[value]]}
    service.spreadsheets().values().update(
        spreadsheetId=MASTER_SHEET_ID,
        range=range_name,
        valueInputOption="USER_ENTERED",
        body=body
    ).execute()


# ======================
# MESSAGE PARSING
# ======================

def parse_message_to_dict(text: str) -> dict:
    """
    Parse message like:
    Name: John
    Email: john@example.com
    Product: Premium
    """
    pattern = r"([A-Za-z\s]+):\s*(.+)"
    matches = re.findall(pattern, text.strip())
    return {key.strip(): value.strip() for key, value in matches}


def dict_to_row(data: dict) -> List[str]:
    """Convert parsed dict to row in correct column order."""
    row = []
    for col in COLUMNS:
        if col == "Timestamp":
            row.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        elif col == "User":
            row.append("Telegram User")  # Could be improved with username if available
        else:
            row.append(data.get(col, ""))
    return row


# ======================
# TELEGRAM HANDLERS
# ======================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hi! Send me structured data like:\n\n"
        "Name: Alice\n"
        "Email: alice@example.com\n"
        "Product: Basic Plan\n\n"
        "I’ll add it to the master Google Sheet!"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or f"user_{user_id}"
    text = update.message.text

    try:
        # Parse message
        data = parse_message_to_dict(text)
        if not data:
            await update.message.reply_text(
                "⚠️ Please send data in the format:\nField: Value"
            )
            return

        # Convert to row (with timestamp, user, etc.)
        row = dict_to_row(data)
        logger.info(f"Parsed row: {row}")

        # Append to Google Sheet
        append_row(row)

        # Confirm success
        sheet_url = f"https://docs.google.com/spreadsheets/d/{MASTER_SHEET_ID}/edit#gid=0"
        await update.message.reply_text(
            "✅ Data added to the master sheet!\n" f"[Open Sheet]({sheet_url})",
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Error for user {user_id}: {e}")
        await update.message.reply_text("❌ Failed to update sheet. Please notify admin.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    example = "\n".join([f"{col}: {col.lower()}_example" for col in COLUMNS if col not in ("Timestamp", "User")])
    await update.message.reply_text(
        f"Send your data like this:\n\n{example}"
    )


# ======================
# MAIN
# ======================

def main():
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("Missing TELEGRAM_BOT_TOKEN env var")
    if not MASTER_SHEET_ID:
        raise ValueError("Missing MASTER_SHEET_ID env var")
    if not os.path.exists(GOOGLE_CREDENTIALS_FILE):
        raise FileNotFoundError(f"Missing {GOOGLE_CREDENTIALS_FILE}")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot started. Listening for messages...")
    app.run_polling()


if __name__ == "__main__":
    main()