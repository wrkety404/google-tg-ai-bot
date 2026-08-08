 #!/usr/bin/env python3
# bot.py – Gmail Factory (Telegram bot) with ChatGPT + proxy rotation
import asyncio
import logging
import json
import random
import string
import sqlite3
import os
import time
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import openai
import requests

# ============================================================
#  КОНФИГ (твои данные)
# ============================================================
BOT_TOKEN = "8787576545:AAHn0QempeRNbHS7_QF5TrJWtKYjf1E-ar4"
ADMIN_ID = 7820732737  # твой Telegram ID
OPENAI_API_KEY = "sk-abcdef1234567890abcdef1234567890abcdef12"  # первый ключ из списка

# Список прокси – добавь свои (ip:port или user:pass@ip:port)
PROXY_LIST = [
    # "proxy1:8080",
    # "proxy2:8080",
]

DB_PATH = "accounts.db"

# Инициализация
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
openai.api_key = OPENAI_API_KEY
logging.basicConfig(level=logging.INFO)

# ============================================================
#  БАЗА ДАННЫХ
# ============================================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT,
            password TEXT,
            full_name TEXT,
            proxy TEXT,
            created_at TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def save_account(email, password, full_name, proxy):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO accounts (email, password, full_name, proxy, created_at) VALUES (?, ?, ?, ?, ?)',
              (email, password, full_name, proxy, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM accounts")
    total = c.fetchone()[0]
    conn.close()
    return total

# ============================================================
#  РОТАЦИЯ ПРОКСИ
# ============================================================
class ProxyManager:
    def __init__(self, proxies):
        self.proxies = proxies
        self.index = 0
    def next(self):
        if not self.proxies:
            return None
        proxy = self.proxies[self.index]
        self.index = (self.index + 1) % len(self.proxies)
        return proxy

proxy_manager = ProxyManager(PROXY_LIST)

# ============================================================
#  ГЕНЕРАЦИЯ ДАННЫХ ЧЕРЕЗ CHATGPT
# ============================================================
async def generate_user_data():
    prompt = """
    Сгенерируй данные для нового пользователя Google (США, реальное имя).
    Верни в JSON:
    {"first_name":"...", "last_name":"...", "birthday":"YYYY-MM-DD", "city":"...", "state":"...", "interests":["...","..."]}
    """
    try:
        resp = await openai.ChatCompletion.acreate(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=200
        )
        return json.loads(resp.choices[0].message.content)
    except:
        # Резерв (если ChatGPT недоступен)
        return {
            "first_name": random.choice(["John","Emma","Michael","Olivia"]),
            "last_name": random.choice(["Smith","Johnson","Williams","Brown"]),
            "birthday": f"{random.randint(1970,2000)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
            "city": "New York",
            "state": "NY",
            "interests": ["music", "sports"]
        }

# ============================================================
#  СОЗДАНИЕ АККАУНТА (Selenium)
# ============================================================
async def create_account(proxy_str):
    user = await generate_user_data()
    username_base = f"{user['first_name'].lower()}{user['last_name'].lower()}"
    username = f"{username_base}{random.randint(100, 999)}"
    password = ''.join(random.choices(string.ascii_letters + string.digits + "!@#$", k=12))

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)

    if proxy_str:
        chrome_options.add_argument(f'--proxy-server={proxy_str}')

    driver = None
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': '''
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.navigator.chrome = {runtime: {}};
            '''
        })

        driver.get("https://www.youtube.com")
        time.sleep(3)
        # Нажимаем "Войти"
        try:
            sign_in = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable((By.XPATH, "//paper-button[contains(text(),'Войти')]"))
            )
            sign_in.click()
        except:
            driver.find_element(By.CSS_SELECTOR, "ytd-button-renderer a[href*='accounts.google.com']").click()

        time.sleep(2)
        # Создать аккаунт
        WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.XPATH, "//span[text()='Создать аккаунт']"))
        ).click()
        time.sleep(1)
        WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.XPATH, "//span[text()='Для себя']"))
        ).click()
        time.sleep(2)

        # Имя
        first = WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "firstName")))
        first.send_keys(user['first_name'])
        driver.find_element(By.ID, "lastName").send_keys(user['last_name'])
        driver.find_element(By.XPATH, "//span[text()='Далее']").click()
        time.sleep(2)

        # Дата рождения
        month, day, year = user['birthday'].split('-')
        driver.find_element(By.ID, "month").send_keys(month)
        driver.find_element(By.ID, "day").send_keys(day)
        driver.find_element(By.ID, "year").send_keys(year)
        driver.find_element(By.XPATH, "//span[text()='Далее']").click()
        time.sleep(2)

        # Username
        username_field = WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "username")))
        username_field.clear()
        username_field.send_keys(username)
        driver.find_element(By.XPATH, "//span[text()='Далее']").click()
        time.sleep(2)

        # Пароль
        pwd = driver.find_element(By.NAME, "Passwd")
        pwd.send_keys(password)
        driver.find_element(By.NAME, "PasswdAgain").send_keys(password)
        driver.find_element(By.XPATH, "//span[text()='Далее']").click()
        time.sleep(3)

        # Пропускаем номер (если есть)
        try:
            skip = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, "//span[text()='Пропустить']")))
            skip.click()
            time.sleep(2)
        except:
            pass

        # Принять условия
        try:
            driver.find_element(By.XPATH, "//span[text()='Принять']").click()
        except:
            pass

        time.sleep(5)
        email = f"{username}@gmail.com"

        return {
            "email": email,
            "password": password,
            "full_name": f"{user['first_name']} {user['last_name']}",
            "proxy": proxy_str
        }
    except Exception as e:
        logging.error(f"Ошибка: {e}")
        return None
    finally:
        if driver:
            driver.quit()

# ============================================================
#  КОМАНДЫ ТЕЛЕГРАМ-БОТА
# ============================================================
@dp.message(Command("start"))
async def start_cmd(msg: types.Message):
    await msg.answer(
        "🤖 **Gmail Factory Bot**\n"
        "/create <количество> – создать до 10 аккаунтов\n"
        "/stats – статистика\n"
        "/set_proxy <ip:port> – добавить прокси\n"
        "/list_proxy – показать прокси"
    )

@dp.message(Command("create"))
async def create_cmd(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        await msg.answer("❌ Доступ запрещён.")
        return
    args = msg.text.split()
    if len(args) < 2:
        await msg.answer("❌ Укажи количество: /create 5")
        return
    try:
        count = int(args[1])
        if count < 1 or count > 10:
            await msg.answer("❌ От 1 до 10.")
            return
    except:
        await msg.answer("❌ Введи число.")
        return

    await msg.answer(f"⏳ Создаю {count} аккаунтов...")
    accounts = []
    for i in range(count):
        status = await msg.answer(f"🔄 {i+1}/{count}...")
        proxy = proxy_manager.next()
        if not proxy:
            await status.edit_text("❌ Нет прокси. Добавь через /set_proxy")
            break
        acc = await create_account(proxy)
        if acc:
            accounts.append(acc)
            save_account(acc['email'], acc['password'], acc['full_name'], acc['proxy'])
            await status.edit_text(f"✅ {acc['email']}")
        else:
            await status.edit_text(f"❌ Ошибка, пробую другой прокси...")
            proxy = proxy_manager.next()
            if proxy:
                acc = await create_account(proxy)
                if acc:
                    accounts.append(acc)
                    save_account(acc['email'], acc['password'], acc['full_name'], acc['proxy'])
                    await status.edit_text(f"✅ {acc['email']}")
                else:
                    await status.edit_text("❌ Ошибка с двумя прокси.")

    report = "📋 **Создано аккаунтов:**\n\n"
    for acc in accounts:
        report += f"📧 {acc['email']}\n🔑 {acc['password']}\n👤 {acc['full_name']}\n🌐 {acc['proxy']}\n\n"
    await msg.answer(report)

@dp.message(Command("stats"))
async def stats_cmd(msg: types.Message):
    total = get_stats()
    await msg.answer(f"📊 Всего создано: {total}")

@dp.message(Command("set_proxy"))
async def set_proxy_cmd(msg: types.Message):
    args = msg.text.split(maxsplit=1)
    if len(args) < 2:
        await msg.answer("❌ Укажи прокси: /set_proxy ip:port")
        return
    proxy = args[1]
    PROXY_LIST.append(proxy)
    proxy_manager.proxies = PROXY_LIST
    await msg.answer(f"✅ Прокси добавлен: {proxy}")

@dp.message(Command("list_proxy"))
async def list_proxy_cmd(msg: types.Message):
    if PROXY_LIST:
        await msg.answer("🌐 **Список прокси:**\n" + "\n".join(PROXY_LIST))
    else:
        await msg.answer("❌ Прокси не добавлены.")

# ============================================================
#  ЗАПУСК
# ============================================================
async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())