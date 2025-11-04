import asyncio
import requests
from telethon import TelegramClient
from telethon.sessions import StringSession
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
import random
import sqlite3
from datetime import datetime, timedelta
import time
import os  # Добавлен импорт os

# ТОКЕН БОТА
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8575805626:AAGoQdXHEHucmUE317sOUyMr4LLGXjdHYN8')

# API ключи для Telethon
API_ID = 2181397
API_HASH = 'a96783dc5007eb2c6bd00e7eeb79a0c1'

# ID админа
ADMIN_ID = 812877930

class SnuserBot:
    def __init__(self):
        self.proxies = self.get_free_proxies()
        self.active_reports = {}
        self.stats = {}  # Статистика по чатам: {chat_id: {"success": X, "failed": Y}}
        self.init_database()
        
    def init_database(self):
        """Инициализация базы данных"""
        self.conn = sqlite3.connect('users.db', check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                subscription_until INTEGER,
                is_banned BOOLEAN DEFAULT FALSE
            )
        ''')
        # Добавляем админа с вечной подпиской
        self.cursor.execute(
            'INSERT OR IGNORE INTO users (user_id, subscription_until, is_banned) VALUES (?, ?, ?)',
            (ADMIN_ID, -1, False)  # -1 = вечная подписка
        )
        self.conn.commit()
        
    def get_free_proxies(self):
        """Автоматически получает свежие прокси"""
        sources = [
            'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt',
            'https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks5&timeout=10000&country=all'
        ]
        proxies = []
        for source in sources:
            try:
                response = requests.get(source, timeout=10)
                proxies.extend([p.strip() for p in response.text.split('\n') if ':' in p])
            except: pass
        return list(set(proxies))

    def check_subscription(self, user_id):
        """Проверяет наличие активной подписки"""
        if user_id == ADMIN_ID:
            return True
            
        self.cursor.execute('SELECT subscription_until FROM users WHERE user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        
        if not result:
            return False
            
        subscription_until = result[0]
        if subscription_until == -1:  # Вечная подписка
            return True
        elif subscription_until > time.time():  # Подписка активна
            return True
        else:
            return False

    def check_ban(self, user_id):
        """Проверяет забанен ли пользователь"""
        self.cursor.execute('SELECT is_banned FROM users WHERE user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        return result and result[0]

    def add_user(self, user_id):
        """Добавляет пользователя в базу"""
        self.cursor.execute(
            'INSERT OR IGNORE INTO users (user_id, subscription_until, is_banned) VALUES (?, ?, ?)',
            (user_id, 0, False)
        )
        self.conn.commit()

    async def start_report(self, target_username, chat_id):
        """Запускает автоматические жалобы на цель"""
        self.active_reports[chat_id] = True
        self.stats[chat_id] = {"success": 0, "failed": 0}
        
        while self.active_reports.get(chat_id, False):
            try:
                # Создаем временный клиент
                proxy = random.choice(self.proxies) if self.proxies else None
                client = TelegramClient(
                    StringSession(), 
                    API_ID, 
                    API_HASH,
                    proxy=('socks5', proxy.split(':')[0], int(proxy.split(':')[1])) if proxy and ':' in proxy else None
                )
                
                await client.start()
                await client.report_user(target_username, 'spam')
                await client.disconnect()
                
                # Обновляем статистику
                self.stats[chat_id]["success"] += 1
                
                # Отправляем отчет каждые 10 жалоб
                if self.stats[chat_id]["success"] % 10 == 0:
                    stats_text = f"""
📊 Статистика жалоб на @{target_username}:
✅ Успешных: {self.stats[chat_id]["success"]}
❌ Неудачных: {self.stats[chat_id]["failed"]}
                    """
                    await app.bot.send_message(chat_id=chat_id, text=stats_text)
                
                # Пауза между жалобами
                await asyncio.sleep(random.randint(30, 60))
                
            except Exception as e:
                self.stats[chat_id]["failed"] += 1
                await asyncio.sleep(10)
                continue

    async def stop_report(self, chat_id):
        """Останавливает жалобы для чата"""
        self.active_reports[chat_id] = False
        
        if chat_id in self.stats:
            stats = self.stats[chat_id]
            return f"""
🛑 Авто-жалобы остановлены

Итоговая статистика:
✅ Успешных жалоб: {stats['success']}
❌ Неудачных: {stats['failed']}
            """
        return "🛑 Авто-жалобы остановлены"

    # Админ-функции
    def ban_user(self, user_id):
        """Банит пользователя"""
        self.cursor.execute(
            'INSERT OR REPLACE INTO users (user_id, subscription_until, is_banned) VALUES (?, ?, ?)',
            (user_id, 0, True)
        )
        self.conn.commit()
        return True

    def unban_user(self, user_id):
        """Разбанивает пользователя"""
        self.cursor.execute(
            'UPDATE users SET is_banned = ? WHERE user_id = ?',
            (False, user_id)
        )
        self.conn.commit()
        return True

    def grant_subscription(self, user_id, days=0):
        """Выдает подписку (days=0 - вечная)"""
        if days == 0:  # Вечная подписка
            subscription_until = -1
        else:
            subscription_until = time.time() + (days * 24 * 60 * 60)
            
        self.cursor.execute(
            'INSERT OR REPLACE INTO users (user_id, subscription_until, is_banned) VALUES (?, ?, ?)',
            (user_id, subscription_until, False)
        )
        self.conn.commit()
        return True

    def revoke_subscription(self, user_id):
        """Забирает подписку"""
        self.cursor.execute(
            'UPDATE users SET subscription_until = ? WHERE user_id = ?',
            (0, user_id)
        )
        self.conn.commit()
        return True

    def get_user_info(self, user_id):
        """Получает информацию о пользователе"""
        self.cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        
        if not result:
            return "Пользователь не найден в базе"
            
        user_id, subscription_until, is_banned = result
        
        status = "🔴 ЗАБАНЕН" if is_banned else "🟢 АКТИВЕН"
        
        if subscription_until == -1:
            sub_info = "♾️ ВЕЧНАЯ ПОДПИСКА"
        elif subscription_until == 0:
            sub_info = "❌ НЕТ ПОДПИСКИ"
        else:
            days_left = (subscription_until - time.time()) / (24 * 60 * 60)
            sub_info = f"⏳ {days_left:.1f} дней осталось"
            
        return f"""
👤 ID: {user_id}
📊 Статус: {status}
🎫 Подписка: {sub_info}
        """

# Создаем экземпляр бота
snuser_bot = SnuserBot()

# Команды для пользователей
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    snuser_bot.add_user(user_id)
    
    # Проверяем бан
    if snuser_bot.check_ban(user_id):
        await update.message.reply_text("❌ Вы забанены в системе!")
        return
        
    keyboard = [
        [InlineKeyboardButton("💰 Купить подписку", callback_data="buy_sub")],
        [InlineKeyboardButton("📊 Моя подписка", callback_data="my_sub")],
        [InlineKeyboardButton("🚀 Начать репорты", callback_data="start_report")]
    ]
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("👑 Админ-панель", callback_data="admin_panel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🚀 Snuser Bot активирован!\n"
        "Выберите действие:",
        reply_markup=reply_markup
    )

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    # Проверяем бан и подписку
    if snuser_bot.check_ban(user_id):
        await update.message.reply_text("❌ Вы забанены в системе!")
        return
        
    if not snuser_bot.check_subscription(user_id):
        await update.message.reply_text("❌ У вас нет активной подписки!")
        return
        
    if not context.args:
        await update.message.reply_text("❌ Укажи username цели: /report @username")
        return
    
    target = context.args[0].replace('@', '')
    chat_id = update.message.chat_id
    
    await update.message.reply_text(f"🎯 Начинаю авто-жалобы на @{target}...")
    
    # Запускаем в фоне
    asyncio.create_task(snuser_bot.start_report(target, chat_id))

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    result = await snuser_bot.stop_report(chat_id)
    await update.message.reply_text(result)

# Обработчик кнопок
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    
    await query.answer()
    
    # Проверяем бан
    if snuser_bot.check_ban(user_id):
        await query.edit_message_text("❌ Вы забанены в системе!")
        return
    
    if query.data == "buy_sub":
        keyboard = [
            [
                InlineKeyboardButton("1 день - 170₽", callback_data="buy_1"),
                InlineKeyboardButton("7 дней - 650₽", callback_data="buy_7")
            ],
            [
                InlineKeyboardButton("30 дней - 930₽", callback_data="buy_30"),
                InlineKeyboardButton("НАВСЕГДА - 1300₽", callback_data="buy_forever")
            ],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "💰 Выберите тип подписки:\n\n"
            "💳 Для оплаты:\n"
            "Карта: 2200 1234 5678 9012\n"
            "QIWI: +79991234567\n\n"
            "После оплаты отправьте скриншот @admin",
            reply_markup=reply_markup
        )
        
    elif query.data.startswith("buy_"):
        periods = {"buy_1": 1, "buy_7": 7, "buy_30": 30, "buy_forever": 0}
        period = periods[query.data]
        
        if period == 0:
            text = "♾️ ВЕЧНАЯ ПОДПИСКA - 1300₽"
        else:
            text = f"⏳ {period} день - {[170, 650, 930][period//10]}₽"
            
        await query.edit_message_text(
            f"{text}\n\n"
            "💳 Реквизиты для оплаты:\n"
            "Карта: 2200 1234 5678 9012\n"
            "QIWI: +79991234567\n\n"
            "После оплаты отправьте скриншот @admin"
        )
        
    elif query.data == "my_sub":
        user_info = snuser_bot.get_user_info(user_id)
        await query.edit_message_text(
            f"📊 Ваша информация:\n{user_info}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="back_main")]])
        )
        
    elif query.data == "start_report":
        await query.edit_message_text(
            "🎯 Для начала репортов введите команду:\n"
            "/report @username\n\n"
            "Где @username - цель для массовых жалоб"
        )
        
    elif query.data == "admin_panel" and user_id == ADMIN_ID:
        keyboard = [
            [InlineKeyboardButton("👤 Инфо о пользователе", callback_data="admin_user_info")],
            [InlineKeyboardButton("🔨 Забанить", callback_data="admin_ban")],
            [InlineKeyboardButton("🔓 Разбанить", callback_data="admin_unban")],
            [InlineKeyboardButton("🎫 Выдать подписку", callback_data="admin_grant")],
            [InlineKeyboardButton("❌ Забрать подписку", callback_data="admin_revoke")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "👑 Админ-панель\nВыберите действие:",
            reply_markup=reply_markup
        )
        
    elif query.data == "back_main":
        keyboard = [
            [InlineKeyboardButton("💰 Купить подписку", callback_data="buy_sub")],
            [InlineKeyboardButton("📊 Моя подписка", callback_data="my_sub")],
            [InlineKeyboardButton("🚀 Начать репорты", callback_data="start_report")]
        ]
        if user_id == ADMIN_ID:
            keyboard.append([InlineKeyboardButton("👑 Админ-панель", callback_data="admin_panel")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "🚀 Snuser Bot\nВыберите действие:",
            reply_markup=reply_markup
        )
        
    # Админские функции
    elif query.data == "admin_user_info":
        await query.edit_message_text(
            "👤 Получить информацию о пользователе:\n"
            "Используйте команду: /user_info [user_id]"
        )
        
    elif query.data == "admin_ban":
        await query.edit_message_text(
            "🔨 Забанить пользователя:\n"
            "Используйте команду: /ban [user_id]"
        )
        
    elif query.data == "admin_unban":
        await query.edit_message_text(
            "🔓 Разбанить пользователя:\n"
            "Используйте команду: /unban [user_id]"
        )
        
    elif query.data == "admin_grant":
        await query.edit_message_text(
            "🎫 Выдать подписку:\n"
            "Используйте команду: /grant [user_id] [дни]\n"
            "0 дней = вечная подписка"
        )
        
    elif query.data == "admin_revoke":
        await query.edit_message_text(
            "❌ Забрать подписку:\n"
            "Используйте команду: /revoke [user_id]"
        )

# Админ-команды
async def user_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Недостаточно прав!")
        return
        
    if not context.args:
        await update.message.reply_text("❌ Укажите user_id: /user_info [user_id]")
        return
        
    user_id = int(context.args[0])
    info = snuser_bot.get_user_info(user_id)
    await update.message.reply_text(f"👤 Информация о пользователе:\n{info}")

async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Недостаточно прав!")
        return
        
    if not context.args:
        await update.message.reply_text("❌ Укажите user_id: /ban [user_id]")
        return
        
    user_id = int(context.args[0])
    if snuser_bot.ban_user(user_id):
        await update.message.reply_text(f"✅ Пользователь {user_id} забанен!")

async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Недостаточно прав!")
        return
        
    if not context.args:
        await update.message.reply_text("❌ Укажите user_id: /unban [user_id]")
        return
        
    user_id = int(context.args[0])
    if snuser_bot.unban_user(user_id):
        await update.message.reply_text(f"✅ Пользователь {user_id} разбанен!")

async def grant_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Недостаточно прав!")
        return
        
    if len(context.args) < 2:
        await update.message.reply_text("❌ Используйте: /grant [user_id] [дни]")
        return
        
    user_id = int(context.args[0])
    days = int(context.args[1])
    
    if snuser_bot.grant_subscription(user_id, days):
        if days == 0:
            await update.message.reply_text(f"✅ Пользователю {user_id} выдана вечная подписка!")
        else:
            await update.message.reply_text(f"✅ Пользователю {user_id} выдана подписка на {days} дней!")

async def revoke_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Недостаточно прав!")
        return
        
    if not context.args:
        await update.message.reply_text("❌ Укажите user_id: /revoke [user_id]")
        return
        
    user_id = int(context.args[0])
    if snuser_bot.revoke_subscription(user_id):
        await update.message.reply_text(f"✅ Подписка у пользователя {user_id} отозвана!")

# Запуск бота
if __name__ == "__main__":
    # Создаем приложение
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Добавляем обработчики
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("report", report_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("user_info", user_info_command))
    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("unban", unban_command))
    app.add_handler(CommandHandler("grant", grant_command))
    app.add_handler(CommandHandler("revoke", revoke_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("🤖 Snuser Bot запущен!")
    app.run_polling()
