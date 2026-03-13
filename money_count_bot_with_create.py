import logging
import os
import re
from datetime import datetime
from typing import List

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes, CallbackQueryHandler
)


from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from dotenv import load_dotenv
load_dotenv()

# ======================
# CONFIGURATION
# ======================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GOOGLE_CREDENTIALS_FILE = "credentials.json"
MASTER_SHEET_ID = os.getenv("MASTER_SHEET_ID")  # The ID of your single, existing Google Sheet
SHEET_NAME = os.getenv("SHEET_NAME", "Sheet1")  # Tab name inside the sheet (default: "Sheet1")

# Column order expected in your sheet (must match your actual header row)
# COLUMNS = ["Timestamp", "User", "Date", "Operation type", "Bank", "Category", "Subcategory", "Cost", "Comment"]  # Customize as needed
COLUMNS = ["Дата", "Операция", "Карта", "Категория", "Подкатегория", "Сумма", "Комментарий"]
CATEGORIES = {
    "Продукты": ["Овощи", "Фрукты", "Хлеб"],
    "Транспорт": ["Метро", "Автобус", "Такси"],
    "Домашние нужды": ["Электричество", "Интернет", "Ремонт"],
    "Досуг": ["Кино", "Театр", "Концерт"]
}
BANK_TYPES = {
    "Валя Т-Банк",
    "Валя Сбер",
    "Наташа Т-Банк",
    "Наташа Газпром"
}
OPERATION_TYPES = {
    "Приход",
    "Расход"
}
TEMP_DATA = {}

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
        scopes=[
            'https://www.googleapis.com/auth/drive',
            'https://www.googleapis.com/auth/spreadsheets'
        ]
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

    pattern = r"([\w\sёЁа-яА-Я]+):\s*([\w\sёЁа-яА-Я\d.,]+)"
    matches = re.findall(pattern, text.strip())
    return {key.strip(): value.strip() for key, value in matches}


def dict_to_row(data: dict, update: Update) -> List[str]:
    """Convert parsed dict to row in correct column order."""
    row = []
    for col in COLUMNS:
        if col == "Timestamp":
            row.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        elif col == "User":
            row.append(
                update.effective_user.username or f"{update.effective_user.first_name} {update.effective_user.last_name}".strip())
        else:
            row.append(data.get(col, ""))
    return row


# ======================
# TELEGRAM HANDLERS
# ======================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Отправьте сумму для внесения:")

# async def test_kb(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     keyboard = [
#         [InlineKeyboardButton("Category A", callback_data="a")],
#         [InlineKeyboardButton("Category B", callback_data="b")]
#     ]
#     reply_markup = InlineKeyboardMarkup(keyboard)
#     await update.message.reply_text("Choose an option:", reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    choice = query.data
    temp_data = TEMP_DATA.get(query.from_user.id, {})

    # Обрабатываем различные состояния
    if "sum" in temp_data:
        sum_value = temp_data["sum"]
        del temp_data["sum"]

        if "category" not in temp_data:
            # Пользователь выбрал категорию
            temp_data["category"] = choice

            # Показываем подкатегории
            subcategories = CATEGORIES.get(choice, [])
            keyboard = [[InlineKeyboardButton(subcat, callback_data=subcat)] for subcat in subcategories]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text=f"Ваша категория: {choice}. Выберите подкатегорию:", reply_markup=reply_markup)
        else:
            # Пользователь выбрал подкатегорию
            temp_data["subcategory"] = choice
            category = temp_data["category"]
            subcategory = temp_data["subcategory"]

            # Готовим данные для сохранения
            row = [
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                query.from_user.username or f"{query.from_user.first_name} {query.from_user.last_name}",
                category,
                subcategory,
                sum_value
            ]

            # Тут можно сохранить данные в Google Sheets
            print("Row saved:", row)

            await query.edit_message_text(text=f"Данные сохранены: {sum_value} руб. ({category}/{subcategory})")
    else:
        # Начинаем процесс: пользователь выбирает категорию
        categories = list(CATEGORIES.keys())
        keyboard = [[InlineKeyboardButton(cat, callback_data=cat)] for cat in categories]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text="Выберите категорию:", reply_markup=reply_markup)

# Основной обработчик сообщений

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text
    try:
        sum_value = float(message.replace(",", "."))
        temp_data = TEMP_DATA.setdefault(update.effective_user.id, {"sum": sum_value})
        await update.message.reply_text("Выберите категорию расхода:", reply_markup=None)
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите число!")

    # try:
    #     # Parse message
    #     data = parse_message_to_dict(text)
    #     if not data:
    #         await update.message.reply_text(
    #             "⚠️ Please send data in the format:\nField: Value"
    #         )
    #         return
    #
    #     # Convert to row (with timestamp, user, etc.)
    #     parsed_data = parse_message_to_dict(update.message.text)
    #     row = dict_to_row(parsed_data, update)
    #     logger.info(f"Parsed row: {row}")
    #
    #     # Append to Google Sheet
    #     append_row(row)
    #
    #     # Confirm success
    #     sheet_url = f"https://docs.google.com/spreadsheets/d/{MASTER_SHEET_ID}/edit#gid=0"
    #     await update.message.reply_text(
    #         "✅ Data added to the master sheet!\n" f"[Open Sheet]({sheet_url})",
    #         parse_mode="Markdown"
    #     )
    #
    # except Exception as e:
    #     logger.error(f"Error for user {user_id}: {e}")
    #     await update.message.reply_text("❌ Failed to update sheet. Please notify admin.")


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

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.bot.initialize()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("test", test_kb))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))

    logger.info("Bot started. Listening for messages...")
    app.run_polling()


if __name__ == "__main__":
    main()