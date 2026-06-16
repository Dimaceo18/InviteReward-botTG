from dotenv import load_dotenv
import os
import sqlite3
import telebot
import time
import random
import string
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from telebot.apihelper import ApiTelegramException

load_dotenv(dotenv_path='config.env')

API_TOKEN = os.getenv('BOT_TOKEN')
if not API_TOKEN:
    raise ValueError("❌ Токен не найден! Проверьте переменную BOT_TOKEN")

bot = telebot.TeleBot(API_TOKEN)

# === ПРИНУДИТЕЛЬНЫЙ СБРОС ===
print("🔄 Принудительный сброс состояния...")
try:
    bot.remove_webhook()
    print("✅ Webhook удален")
except Exception as e:
    print(f"⚠️ Ошибка удаления webhook: {e}")

try:
    updates = bot.get_updates(offset=-1, timeout=10)
    print(f"✅ Очищено {len(updates)} обновлений")
except Exception as e:
    print(f"⚠️ Ошибка очистки обновлений: {e}")

time.sleep(2)
print("🚀 Бот готов к запуску!")

# ===== КОНФИГУРАЦИЯ =====
ADMIN_USERNAMES = ['Sub_Pielea_Mea']
CHANNEL_USERNAME = '@vestiminska'  # Ваш канал
GOAL_INVITES = 5  # Цель: пригласить 5 человек
PRIZE_MESSAGE = "🎁 ПОЗДРАВЛЯЮ! Вы пригласили 5 человек и получаете ПРИЗ!"

# ===== БАЗА ДАННЫХ =====
DB_PATH = os.path.join('/app/data', 'database.db')

def init_db():
    """Создает таблицы, если их нет"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                invite_code TEXT UNIQUE,
                invites_count INTEGER DEFAULT 0,
                prize_received INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица приглашенных
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS invites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inviter_id INTEGER,
                invited_id INTEGER,
                invited_username TEXT,
                invited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (inviter_id) REFERENCES users (user_id)
            )
        ''')
        
        conn.commit()
        print("✅ База данных инициализирована")

def execute_query(query, parameters=()):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(query, parameters)
        conn.commit()
        return cursor

# Инициализируем базу при запуске
init_db()

# ===== ФУНКЦИИ =====
def generate_invite_code():
    """Генерирует уникальный код для приглашения"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

def get_user(user_id):
    """Получает пользователя из базы"""
    result = execute_query(
        "SELECT user_id, username, invite_code, invites_count, prize_received FROM users WHERE user_id = ?",
        (user_id,)
    ).fetchone()
    return result

def create_user(user_id, username):
    """Создает нового пользователя с уникальным кодом"""
    invite_code = generate_invite_code()
    execute_query(
        "INSERT INTO users (user_id, username, invite_code, invites_count, prize_received) VALUES (?, ?, ?, ?, ?)",
        (user_id, username, invite_code, 0, 0)
    )
    return invite_code

def get_invite_link(user_id):
    """Генерирует пригласительную ссылку для пользователя"""
    user = get_user(user_id)
    if not user:
        return None
    
    invite_code = user[2]
    # Ссылка на бота с параметром invite_code
    return f"https://t.me/refererbottg_bot?start={invite_code}"

def process_invite(invite_code, new_user_id, new_username):
    """Обрабатывает переход по пригласительной ссылке"""
    # Находим пригласившего по коду
    inviter = execute_query(
        "SELECT user_id FROM users WHERE invite_code = ?",
        (invite_code,)
    ).fetchone()
    
    if not inviter:
        return False, "Пригласительный код не найден"
    
    inviter_id = inviter[0]
    
    # Проверяем, не пригласил ли пользователь сам себя
    if inviter_id == new_user_id:
        return False, "Нельзя пригласить самого себя"
    
    # Проверяем, не был ли уже приглашен этот пользователь
    existing_invite = execute_query(
        "SELECT id FROM invites WHERE invited_id = ?",
        (new_user_id,)
    ).fetchone()
    
    if existing_invite:
        return False, "Этот пользователь уже был приглашен"
    
    # Проверяем, подписан ли новый пользователь на канал
    if not is_subscribed(new_user_id, CHANNEL_USERNAME):
        return False, "Пользователь не подписан на канал"
    
    # Записываем приглашение
    execute_query(
        "INSERT INTO invites (inviter_id, invited_id, invited_username) VALUES (?, ?, ?)",
        (inviter_id, new_user_id, new_username)
    )
    
    # Увеличиваем счетчик у пригласившего
    execute_query(
        "UPDATE users SET invites_count = invites_count + 1 WHERE user_id = ?",
        (inviter_id,)
    )
    
    # Проверяем, достиг ли пригласивший цели
    inviter_data = get_user(inviter_id)
    invites_count = inviter_data[3]
    prize_received = inviter_data[4]
    
    if invites_count >= GOAL_INVITES and prize_received == 0:
        # Отмечаем, что приз получен
        execute_query(
            "UPDATE users SET prize_received = 1 WHERE user_id = ?",
            (inviter_id,)
        )
        
        # Отправляем поздравление пригласившему
        try:
            bot.send_message(
                inviter_id,
                f"🎉 ПОЗДРАВЛЯЮ!\n\n"
                f"Вы пригласили {invites_count} человек в канал {CHANNEL_USERNAME}!\n\n"
                f"{PRIZE_MESSAGE}"
            )
        except Exception as e:
            print(f"Не удалось отправить поздравление {inviter_id}: {e}")
    
    return True, f"Приглашение засчитано! У {inviter_id} теперь {invites_count} приглашений"

def is_subscribed(user_id, channel_id):
    """Проверяет, подписан ли пользователь на канал"""
    try:
        status = bot.get_chat_member(channel_id, user_id).status
        return status in ['member', 'administrator', 'creator']
    except Exception as e:
        print(f"Ошибка проверки подписки: {e}")
        return False

# ===== КОМАНДЫ =====
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username or str(user_id)
    
    # Разбираем параметры команды
    args = message.text.split()
    invite_code = args[1] if len(args) > 1 else None
    
    # Проверяем, есть ли пользователь в базе
    user = get_user(user_id)
    
    if not user:
        # Создаем нового пользователя
        new_code = create_user(user_id, username)
        
        # Если есть invite_code, обрабатываем приглашение
        if invite_code:
            success, msg = process_invite(invite_code, user_id, username)
            if not success:
                bot.send_message(user_id, f"❌ {msg}")
            else:
                bot.send_message(user_id, f"✅ {msg}")
        
        # Отправляем приветственное сообщение
        welcome_text = (
            f"👋 Добро пожаловать!\n\n"
            f"Твой уникальный код для приглашения: `{new_code}`\n\n"
            f"🔗 Приглашай друзей:\n"
            f"`https://t.me/refererbottg_bot?start={new_code}`\n\n"
            f"📊 Статистика: 0/{GOAL_INVITES} приглашений\n\n"
            f"🎯 Пригласи {GOAL_INVITES} человек в канал {CHANNEL_USERNAME} и получи приз!"
        )
        bot.send_message(user_id, welcome_text, parse_mode='Markdown')
    
    else:
        # Пользователь уже есть
        user_id, username, invite_code, invites_count, prize_received = user
        
        status_text = f"📊 Твоя статистика:\n\n"
        status_text += f"👥 Приглашено: {invites_count}/{GOAL_INVITES}\n"
        status_text += f"🔗 Твоя ссылка:\n`https://t.me/refererbottg_bot?start={invite_code}`\n\n"
        
        if prize_received == 1:
            status_text += f"🎁 Вы уже получили приз за {GOAL_INVITES} приглашений!"
        elif invites_count >= GOAL_INVITES:
            status_text += f"🎉 Вы достигли цели! Напишите администратору для получения приза."
        else:
            status_text += f"🎯 Пригласи еще {GOAL_INVITES - invites_count} человек и получи приз!"
        
        bot.send_message(user_id, status_text, parse_mode='Markdown')

@bot.message_handler(commands=['link'])
def get_link(message):
    """Отправляет ссылку для приглашения"""
    user_id = message.from_user.id
    link = get_invite_link(user_id)
    if link:
        bot.send_message(
            user_id,
            f"🔗 Твоя пригласительная ссылка:\n`{link}`\n\n"
            f"📤 Отправь ее друзьям, чтобы они подписались на {CHANNEL_USERNAME}!",
            parse_mode='Markdown'
        )
    else:
        bot.send_message(user_id, "❌ Ты не зарегистрирован. Напиши /start")

@bot.message_handler(commands=['stats'])
def stats(message):
    """Показывает статистику пользователя"""
    user_id = message.from_user.id
    user = get_user(user_id)
    
    if not user:
        bot.send_message(user_id, "❌ Ты не зарегистрирован. Напиши /start")
        return
    
    user_id, username, invite_code, invites_count, prize_received = user
    
    stats_text = f"📊 Твоя статистика:\n\n"
    stats_text += f"👤 ID: {user_id}\n"
    stats_text += f"👥 Приглашено: {invites_count}/{GOAL_INVITES}\n"
    stats_text += f"🔗 Код: `{invite_code}`\n\n"
    
    if prize_received == 1:
        stats_text += f"🎁 Приз уже получен!"
    elif invites_count >= GOAL_INVITES:
        stats_text += f"🎉 Поздравляю! Ты выполнил цель! Обратись к администратору."
    else:
        stats_text += f"🎯 Осталось пригласить: {GOAL_INVITES - invites_count} чел."
    
    # Показываем список приглашенных
    invites_list = execute_query(
        "SELECT invited_username, invited_at FROM invites WHERE inviter_id = ? ORDER BY invited_at DESC LIMIT 10",
        (user_id,)
    ).fetchall()
    
    if invites_list:
        stats_text += f"\n\n📋 Последние приглашенные:\n"
        for i, (invited_username, invited_at) in enumerate(invites_list, 1):
            stats_text += f"{i}. @{invited_username or 'скрыт'} ({invited_at[:10]})\n"
    
    bot.send_message(user_id, stats_text, parse_mode='Markdown')

# ===== АДМИН-КОМАНДЫ =====
@bot.message_handler(commands=['admin_stats'])
def admin_stats(message):
    """Показывает общую статистику (только для админов)"""
    if message.from_user.username not in ADMIN_USERNAMES:
        bot.send_message(message.chat.id, "❌ У вас нет прав для выполнения этой команды.")
        return
    
    total_users = execute_query("SELECT COUNT(*) FROM users").fetchone()[0]
    total_invites = execute_query("SELECT COUNT(*) FROM invites").fetchone()[0]
    prize_winners = execute_query("SELECT COUNT(*) FROM users WHERE prize_received = 1").fetchone()[0]
    
    stats_text = f"📊 Общая статистика:\n\n"
    stats_text += f"👥 Всего пользователей: {total_users}\n"
    stats_text += f"🔗 Всего приглашений: {total_invites}\n"
    stats_text += f"🎁 Получили приз: {prize_winners}\n"
    
    # Топ пригласивших
    top_inviters = execute_query(
        "SELECT user_id, username, invites_count FROM users ORDER BY invites_count DESC LIMIT 10"
    ).fetchall()
    
    if top_inviters:
        stats_text += f"\n🏆 Топ пригласивших:\n"
        for i, (user_id, username, invites_count) in enumerate(top_inviters, 1):
            stats_text += f"{i}. @{username or str(user_id)}: {invites_count} чел.\n"
    
    bot.send_message(message.chat.id, stats_text)

# ===== ЗАПУСК =====
print("🚀 Запускаю бота...")

while True:
    try:
        bot.remove_webhook()
        print("✅ Webhook удален перед запуском")
        bot.polling(none_stop=True, interval=0, timeout=60)
    except ApiTelegramException as e:
        if "409" in str(e) or "Conflict" in str(e):
            print(f"⚠️ Конфликт: {e}")
            time.sleep(5)
            continue
        else:
            print(f"❌ Ошибка API: {e}")
            time.sleep(5)
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        time.sleep(5)
