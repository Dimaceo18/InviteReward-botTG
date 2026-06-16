from dotenv import load_dotenv
import os
import sqlite3
import telebot
import numpy as np
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

import random
def generate_captcha():
    operators = ['+', '-', '*', '/']
    num1 = random.randint(1, 10)
    num2 = random.randint(1, 10)
    operator = random.choice(operators)

    if operator == '/':
        # Для деления убеждаемся, что делитель не 0 и деление даёт целый результат
        num1 = num1 * num2

    captcha = f"{num1} {operator} {num2}"
    answer = eval(captcha)

    return captcha, int(answer)

# Загружаем переменные из файла config.env
load_dotenv(dotenv_path='config.env')

# Токен для бота
API_TOKEN = os.getenv('TELEGRAM_API_TOKEN')

# Инициализация бота
bot = telebot.TeleBot(API_TOKEN, skip_pending=True)

# Список администраторов по ID и username
ADMIN_USERNAMES = ['Sub_Pielea_Mea']

# Список обязательных каналов для подписки
REQUIRED_CHANNELS = ['@test1_PythonPI', '@test2_PythonPI']

# Переменная для хранения количества победителей (по умолчанию 1)
MAX_WINNERS = 1

# Функция проверки прав администратора
def is_admin(message):
    username = message.from_user.username
    return username and username in ADMIN_USERNAMES

# Функция для подключения к базе данных и выполнения SQL запросов
def execute_query(query, parameters=()):
    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()
        cursor.execute(query, parameters)
        conn.commit()
        return cursor

# Функция для проверки подписки на все обязательные каналы
def check_subscriptions(user_id):
    for channel in REQUIRED_CHANNELS:
        if not is_subscribed(user_id, channel):
            return False, channel
    return True, None

# Функция для проверки подписки на один канал
def is_subscribed(user_id, channel_id):
    try:
        status = bot.get_chat_member(channel_id, user_id).status
        return status in ['member', 'administrator', 'creator']
    except Exception as e:
        # print(f"Ошибка при проверке подписки на {channel_id}: {e}")
        return False

# Универсальная функция отправки сообщений
def send_message(chat_id, text):
    bot.send_message(chat_id, text)

# Словарь для хранения состояния пользователей
user_cache = {}

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id

    # Проверка на существование пользователя в базе данных
    does_exist = bool(execute_query("SELECT telegram_id FROM users WHERE telegram_id = ?", (user_id,)).fetchone())

    if does_exist:
        subscribed, unsubscribed_channel = check_subscriptions(user_id)

        if not subscribed:
            # Если пользователь не подписан, отправляем предупреждение
            photo_path = 'fashion_welcome.jpg'
            message_text = (
                f'<b>Добро пожаловать в "FashionBot"!</b>\n\n'
                f'💄 Здесь вы найдете всё о моде, стиле и вдохновении.\n\n'
                f'🌸 Мы создаем атмосферу красоты и утонченности:\n\n'
                f'🔗 <a href="https://t.me/test1_PythonPI">БЛЕСК И ШЁПОТ</a>\n'
                f'🔗 <a href="https://t.me/test2_PythonPI">МИР АРОМАТОВ</a>\n\n'
                f'✨ Чтобы полностью раскрыть ваш стиль и получить вознаграждение 🎁, подпишитесь на наши каналы и нажмите "Участвовать".'
            )

            markup = InlineKeyboardMarkup()
            participate_button = InlineKeyboardButton(text="🎉 Участвовать", callback_data="participate")
            markup.add(participate_button)

            with open(photo_path, 'rb') as photo:
                bot.send_photo(message.chat.id, photo, caption=message_text, parse_mode='HTML', reply_markup=markup)
        else:
            bot.send_message(message.chat.id, '⚠️ Вы уже зарегистрированы в конкурсе.', parse_mode='HTML')

    else:
        # Если пользователя нет в базе, генерируем капчу
        captcha_question, captcha_answer = generate_captcha()

        # Сохраняем данные пользователя
        user_cache[user_id] = {"captcha_answer": captcha_answer, "message": message}

        bot.send_message(
            message.chat.id,
            f"Чтобы начать, решите капчу: {captcha_question} = ?\nВведите ваш ответ:"
        )


@bot.message_handler(func=lambda msg: msg.from_user.id in user_cache)
def captcha_check(msg):
    user_id = msg.from_user.id
    original_message = user_cache[user_id]["message"]

    try:
        user_answer = int(msg.text)

        if user_answer == user_cache[user_id]["captcha_answer"]:
            bot.send_message(msg.chat.id, "✅ Капча пройдена успешно!")

            # Удаляем пользователя из словаря капчи
            del user_cache[user_id]

            # Обрабатываем реферальный код
            args = original_message.text.split()
            referral_link = f'ref_{user_id}'

            if len(args) > 1:  # Если есть реферальный код
                ref_code = args[1]
                inviter = execute_query("SELECT telegram_id FROM users WHERE referral_code = ?", (ref_code,)).fetchone()

                if inviter:
                    inviter_id = inviter[0]
                    # Увеличиваем счетчик приглашений у пригласившего
                    execute_query(
                        "UPDATE users SET invites_count = invites_count + 1 WHERE telegram_id = ?",
                        (inviter_id,)
                    )
                    # Добавляем нового пользователя
                    execute_query(
                        "INSERT INTO users (telegram_id, referral_code, inviter, invites_count) VALUES (?, ?, ?, ?)",
                        (user_id, referral_link, inviter_id, 0)
                    )
                    bot.send_message(inviter_id, f"🎉 У вас новый реферал: {user_id}!")
                else:
                    bot.send_message(msg.chat.id, "❌ Неверный реферальный код.")
                    return
            else:
                # Регистрируем пользователя без реферального кода
                execute_query(
                    "INSERT INTO users (telegram_id, referral_code, inviter, invites_count) VALUES (?, ?, ?, ?)",
                    (user_id, referral_link, None, 0)
                )

            # Приветственное сообщение
            photo_path = 'fashion_welcome.jpg'
            message_text = (
                f'<b>Добро пожаловать в "FashionBot"!</b>\n\n'
                f'💄 Здесь вы найдете всё о моде, стиле и вдохновении.\n\n'
                f'🌸 Мы создаем атмосферу красоты и утонченности:\n\n'
                f'🔗 <a href="https://t.me/test1_PythonPI">БЛЕСК И ШЁПОТ</a>\n'
                f'🔗 <a href="https://t.me/test2_PythonPI">МИР АРОМАТОВ</a>\n\n'
                f'✨ Чтобы полностью раскрыть ваш стиль и получить вознаграждение 🎁, подпишитесь на наши каналы и нажмите "Участвовать".'
            )

            # Кнопка "Участвовать"
            markup = InlineKeyboardMarkup()
            participate_button = InlineKeyboardButton(text="🎉 Участвовать", callback_data="participate")
            markup.add(participate_button)

            with open(photo_path, 'rb') as photo:
                bot.send_photo(msg.chat.id, photo, caption=message_text, parse_mode='HTML', reply_markup=markup)
        else:
            bot.send_message(msg.chat.id, "❌ Неверный ответ на капчу. Попробуйте снова.")
    except ValueError:
        bot.send_message(msg.chat.id, "❌ Пожалуйста, введите число.")



# Обработчик нажатия кнопки "Участвовать"
@bot.callback_query_handler(func=lambda call: call.data == "participate")
def participate(call):
    user_id = call.from_user.id

    # Проверяем, зарегистрирован ли пользователь для участия
    user = execute_query("SELECT particip FROM users WHERE telegram_id = ?", (user_id,)).fetchone()

    if user is None:
        bot.answer_callback_query(call.id, text='❌ Вы не зарегистрированы. Используйте /start для начала.',
                                  show_alert=True)
        return

    # Проверяем подписки
    subscribed, unsubscribed_channel = check_subscriptions(user_id)
    if not subscribed:
        bot.answer_callback_query(call.id, text=f'⚠️ Вы не подписаны на все каналы. Подпишитесь, чтобы участвовать!',
                                  show_alert=True)
        return

    # Если уже участвует
    if user[0] == 1:
        bot.answer_callback_query(call.id, text='⚠️ Вы уже участвуете в конкурсе.', show_alert=True)
        return

    # Завершаем регистрацию
    execute_query("UPDATE users SET particip = 1 WHERE telegram_id = ?", (user_id,))

    # Генерируем реферальную ссылку
    referral_code = execute_query("SELECT referral_code FROM users WHERE telegram_id = ?", (user_id,)).fetchone()[0]
    invite_link = f'https://t.me/APD52_bot?start={referral_code}'

    # Отправляем сообщение с ссылкой
    photo_path_2 = 'fashion_welcome2.jpg'  # Укажи путь к нужному изображению
    message_text_2 = (
        '🎉 <b>Поздравляю со вступлением</b>\n\n'
        f'❗️ Вот твоя уникальная ссылка:\n<a>{invite_link}</a>\n\n'
        'Приглашай по ней своих друзей, получай за каждого один билет, копи максимум билетов и увеличивай свои шансы на выигрыш!🏆'
    )
    with open(photo_path_2, 'rb') as photo:
        bot.send_photo(call.message.chat.id, photo, caption=message_text_2, parse_mode='HTML')

    bot.answer_callback_query(call.id, text='🎉 Вы успешно зарегистрировались!', show_alert=True)

# Команда для изменения количества победителей (только для админов)
@bot.message_handler(commands=['set_winners'])
def set_winners(message):
    if not is_admin(message):
        send_message(message.chat.id, 'У вас нет прав для выполнения этой команды.')
        return

    try:
        # Извлекаем количество победителей из сообщения (например, /set_winners 5)
        new_winners_count = int(message.text.split()[1])
        global MAX_WINNERS
        MAX_WINNERS = new_winners_count  # Обновляем переменную
        send_message(message.chat.id, f"Количество победителей успешно изменено на {MAX_WINNERS}.")
    except (IndexError, ValueError):
        send_message(message.chat.id,
                     "Пожалуйста, укажите корректное количество победителей. Пример: /set_winners 3")

# Команда для удаления пользователя по его telegram_id (только для админов)
@bot.message_handler(commands=['delete_user'])
def delete_user(message):
    if not is_admin(message):
        send_message(message.chat.id, 'У вас нет прав для выполнения этой команды.')
        return

    try:
        telegram_id = int(message.text.split()[1])
    except (IndexError, ValueError):
        send_message(message.chat.id, 'Пожалуйста, укажите корректный telegram_id. Пример: /delete_user 123456789')
        return

    user = execute_query("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
    if not user:
        send_message(message.chat.id, f'Пользователь с ID {telegram_id} не найден.')
    else:
        inviter_of_user = user[4]
        print(inviter_of_user)
        try:
            execute_query("UPDATE users SET invites_count = invites_count - 1 WHERE telegram_id = ?",
                          (inviter_of_user,))
            execute_query("DELETE FROM users WHERE telegram_id = ?", (telegram_id,))
            execute_query("UPDATE users SET particip = 0 WHERE invites_count < 1")
            send_message(message.chat.id, f'Пользователь с ID {telegram_id} был удален.')
        except:
            pass

# Команда для проведения розыгрыша (только для админов)
@bot.message_handler(commands=['draw'])
def draw_raffle(message):
    if not is_admin(message):
        bot.send_message(message.chat.id, '❌ У вас нет прав для выполнения этой команды.')
        return

    # Получаем всех пользователей с приглашениями
    all_partic = execute_query("SELECT telegram_id, invites_count FROM users WHERE invites_count >= 1").fetchall()
    if not all_partic:
        bot.send_message(message.chat.id, '❌ Нет участников, которые соответствуют условиям для розыгрыша.')
        return

    # Рассчитываем вероятности
    total_invites = sum([pair[1] for pair in all_partic])
    users = [pair[0] for pair in all_partic]
    probs = [pair[1] / total_invites for pair in all_partic]

    # Проверяем, что количество победителей не превышает количество участников
    max_winners = min(len(users), MAX_WINNERS)
    if max_winners == 0:
        bot.send_message(message.chat.id, '❌ Недостаточно участников для выбора победителей.')
        return

    # Выбираем победителей
    winners = np.random.choice(users, size=max_winners, replace=False, p=probs)

    # Формируем сообщение с победителями
    winners_message = ''
    for winner in winners:
        try:
            chat = bot.get_chat(winner)
            username = f'@{chat.username}' if chat.username else 'Без имени пользователя'
            winners_message += f'Победитель: {username} (ID: {winner})\n'
        except Exception as e:
            winners_message += f'Победитель: ID {winner} (не удалось получить имя пользователя)\n'

    bot.send_message(message.chat.id, f'🎉 Розыгрыш завершен! Победители:\n{winners_message}')

# Команда для сброса всех пользователей (только для админов)
@bot.message_handler(commands=['reset_users'])
def reset_users(message):
    if not is_admin(message):
        send_message(message.chat.id, 'У вас нет прав для выполнения этой команды.')
        return

    execute_query("DELETE FROM users")
    send_message(message.chat.id, 'Все пользователи были удалены.')

# Команда для отображения списка участников с количеством приглашенных (только для админов)
@bot.message_handler(commands=['participants'])
def show_participants(message):
    if not is_admin(message):
        send_message(message.chat.id, 'У вас нет прав для выполнения этой команды.')
        return

    # Получаем всех пользователей, сортируем по количеству приглашенных (сначала > 0, потом = 0)
    users = execute_query(
        "SELECT telegram_id, invites_count, inviter FROM users ORDER BY invites_count DESC").fetchall()

    print(users)
    if not users:
        send_message(message.chat.id, 'Нет зарегистрированных пользователей.')
        return

    # Формируем список участников
    participants_with_invites = []
    participants_without_invites = []

    participants_message = "Участники конкурса:\n"
    for user in users:
        telegram_id, invites_count, inviter = user

        if invites_count:
            username = bot.get_chat(telegram_id).username
            participants_message += f"ID:{telegram_id}, UserName:@{username},Added:{invites_count}:\n"
            n = 1
            for user_invited in users:
                telegram_id_invited, _, inviter_20 = user_invited
                if telegram_id == inviter_20 and telegram_id != telegram_id_invited:
                    username2 = bot.get_chat(telegram_id_invited).username
                    participants_message += f"\t{n}. ID:{telegram_id_invited}, UserName:@{username2}\n"
                    n += 1

    send_message(message.chat.id, participants_message)

# Команда для отображения списка команд для администраторов
@bot.message_handler(commands=['help_adm'])
def admin_help(message):
    if not is_admin(message):
        send_message(message.chat.id, 'У вас нет прав для выполнения этой команды.')
        return
    help_message = """
    Список команд для администраторов:
    /help_adm - Показать этот список команд.
    /set_winners [число] - Установить количество победителей в розыгрыше.
    /draw - Провести розыгрыш.
    /participants - Показать участников конкурса и количество приглашенных.
    /delete_user [telegram_id] - Удалить пользователя по его ID.
    /reset_users - Удалить всех пользователей.
    """
    send_message(message.chat.id, help_message)

# Запуск бота
bot.remove_webhook()
bot.polling(none_stop=True)
