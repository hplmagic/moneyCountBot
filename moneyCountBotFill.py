import logging
import os
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler
)
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# Load environment variables
load_dotenv()

# Google Sheets configuration
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SPREADSHEET_ID = os.getenv('GOOGLE_SHEETS_ID')
RANGE_NAME = 'Sheet1!A:E'  # Adjust sheet name if needed

# Telegram states
B, C, D, E = range(4)

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the conversation and ask for Operation."""
    await update.message.reply_text(
        "Enter operation (income/outcome):"
    )
    return B


async def get_b(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store Operation and ask for Card."""
    context.user_data['B'] = update.message.text
    await update.message.reply_text("Enter card (bank name):")
    return C


async def get_c(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store Card and ask for Category."""
    context.user_data['C'] = update.message.text
    await update.message.reply_text("Enter category:")
    return D


async def get_d(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store Category and ask for Subcategory."""
    context.user_data['D'] = update.message.text
    await update.message.reply_text("Enter subcategory:")
    return E


async def get_e(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store Subcategory, write to Google Sheets, and end conversation."""
    context.user_data['E'] = update.message.text

    # Get current date in DD.MM.YY format
    current_date = datetime.now().strftime("%d.%m.%y")

    # Prepare row data
    row_data = [
        current_date,
        context.user_data['B'],
        context.user_data['C'],
        context.user_data['D'],
        context.user_data['E']
    ]

    try:
        # Authenticate and connect to Google Sheets
        creds = Credentials.from_service_account_file(
            'credentials.json',
            scopes=SCOPES
        )
        service = build('sheets', 'v4', credentials=creds)
        sheet = service.spreadsheets()

        # Get last row number
        result = sheet.values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=RANGE_NAME
        ).execute()
        values = result.get('values', [])
        next_row = len(values) + 1

        # Write new row
        body = {'values': [row_data]}
        sheet.values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f'Sheet1!A{next_row}:E{next_row}',
            valueInputOption='RAW',
            body=body
        ).execute()

        await update.message.reply_text("✅ Data saved successfully!")

    except Exception as e:
        logger.error(f"Google Sheets error: {e}")
        await update.message.reply_text("❌ Error saving data. Please try again.")

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel conversation."""
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END


def main():
    """Start the bot."""
    # Create application
    application = Application.builder().token(os.getenv('BOT_TOKEN')).build()

    # Conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            B: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_b)],
            C: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_c)],
            D: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_d)],
            E: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_e)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    application.add_handler(conv_handler)

    # Start polling
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()