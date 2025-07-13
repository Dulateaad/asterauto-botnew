import os
import datetime
import openai
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)
from config import TELEGRAM_BOT_TOKEN, OPENAI_API_KEY

client = openai.OpenAI(api_key=OPENAI_API_KEY)
user_states = {}
user_results = {}

THEMES = {
    "Гарантия 365": {
        "presentation": "files/presentation.pdf",
        "video_url": "https://youtu.be/fdVDF42lehU",
        "quiz": [
            {
                "q": "1. Что входит в гарантийный ремонт по программе \"Гарантия 365\"?",
                "options": [
                    "A) Только работа",
                    "B) Только запчасти",
                    "C) Только расходные материалы",
                    "D) Работа, запчасти и расходные материалы"
                ],
                "answer": 3
            },
            {
                "q": "2. Есть ли ограничение по количеству обращений?",
                "options": [
                    "A) Да, не более трёх",
                    "B) Да, не более пяти",
                    "C) Нет ограничений по количеству обращений",
                    "D) Только одно обращение"
                ],
                "answer": 2
            }
        ]
    }
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = ReplyKeyboardMarkup(
        [["📌 Гарантия 365"], ["📂 Мои результаты", "❓ Задать вопрос"], ["🧠 Потренироваться"]],
        resize_keyboard=True
    )
    await update.message.reply_text("👋 Добро пожаловать! Выберите тему или режим:", reply_markup=keyboard)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if text == "📌 Гарантия 365":
        user_states[user_id] = {"mode": "theme", "theme": "Гарантия 365", "current": 0, "score": 0}
        await update.message.reply_text("📄 Презентация:")
        await update.message.reply_document(open(THEMES["Гарантия 365"]["presentation"], "rb"))
        await update.message.reply_text(f"🎬 Видео: {THEMES['Гарантия 365']['video_url']}")
        await update.message.reply_text("🧪 Когда будете готовы, нажмите кнопку ниже для начала квиза.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🧪 Пройти квиз", callback_data="start_quiz")]]))
        return

    if text == "📂 Мои результаты":
        results = user_results.get(user_id, [])
        if not results:
            await update.message.reply_text("📭 Вы ещё не проходили квизы.")
        else:
            result_text = "🗂 Ваши результаты:\n" + "\n".join(
                [f"• {r['theme']} — {r['score']}/{r['total']} ({r['date']})" for r in results]
            )
            await update.message.reply_text(result_text)
        return

    if text == "❓ Задать вопрос":
        user_states[user_id] = {"mode": "chat"}
        await update.message.reply_text("✍️ Введите свой вопрос:")
        return

    if text == "🧠 Потренироваться":
        user_states[user_id] = {"mode": "select_role"}
        await update.message.reply_text("Выберите роль:",
            reply_markup=ReplyKeyboardMarkup(
                [["🙋‍♂️ Я клиент", "💼 Я менеджер"]],
                resize_keyboard=True
            )
        )
        return

    if text == "🙋‍♂️ Я клиент":
        user_states[user_id] = {"mode": "train", "role": "client"}
        await update.message.reply_text(
            "Отлично! Задавайте свои вопросы как клиент.",
            reply_markup=ReplyKeyboardMarkup([["⬅️ Назад в меню"]], resize_keyboard=True)
        )
        return

    if text == "💼 Я менеджер":
        user_states[user_id] = {"mode": "train", "role": "manager"}
        await update.message.reply_text(
            "Хорошо! Задавайте вопросы, как будто вы — менеджер.",
            reply_markup=ReplyKeyboardMarkup([["⬅️ Назад в меню"]], resize_keyboard=True)
        )
        return

    if text == "⬅️ Назад в меню":
        await start(update, context)
        return

    mode = user_states.get(user_id, {}).get("mode", "")

    if mode in ["chat", "train"]:
        role = user_states[user_id].get("role", "client")
        if mode == "chat":
            system_prompt = "Ты — помощник автосалона. Отвечай кратко и по делу."
        elif role == "client":
            system_prompt = "Ты — консультант автосалона AsterAuto. Отвечай просто и понятно, как клиенту."
        else:
            system_prompt = "Ты — тренер для новых менеджеров автосалона. Объясняй чётко, подробно и профессионально."

        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ]
            )
            await update.message.reply_text(response.choices[0].message.content.strip())
        except Exception as e:
            await update.message.reply_text(f"⚠ Ошибка OpenAI: {str(e)}")
        return

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    data = query.data

    if data == "start_quiz":
        user_states[user_id]["mode"] = "quiz"
        user_states[user_id]["current"] = 0
        user_states[user_id]["score"] = 0
        await send_question(update, context, user_id)
        return

    if ":" in data:
        q_index, selected = map(int, data.split(":"))
        theme = user_states[user_id]["theme"]
        quiz = THEMES[theme]["quiz"]
        correct = quiz[q_index]["answer"]
        if selected == correct:
            user_states[user_id]["score"] += 1
        user_states[user_id]["current"] += 1
        await send_question(update, context, user_id)

async def send_question(update_or_query, context, user_id):
    state = user_states[user_id]
    theme = state["theme"]
    quiz = THEMES[theme]["quiz"]
    index = state["current"]

    if index >= len(quiz):
        score = state["score"]
        total = len(quiz)
        user_results.setdefault(user_id, []).append({
            "theme": theme,
            "score": score,
            "total": total,
            "date": datetime.datetime.now().strftime("%Y-%m-%d")
        })
        user_states[user_id]["mode"] = "theme"
        await context.bot.send_message(
            chat_id=user_id,
            text=f"✅ Квиз завершён!\nВы ответили правильно на {score} из {total}."
        )
        return

    q = quiz[index]
    buttons = [[InlineKeyboardButton(opt, callback_data=f"{index}:{i}")] for i, opt in enumerate(q["options"])]
    await context.bot.send_message(chat_id=user_id, text=f"🧪 {q['q']}", reply_markup=InlineKeyboardMarkup(buttons))

def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))
    print("🚀 Бот AsterAuto запущен")
    app.run_polling()

if __name__ == "__main__":
    main()