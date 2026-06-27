#!/usr/bin/env python3
"""Test Telegram bot connection for FX Trading System."""

import sys
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv
import os

# Load .env from the backend directory
backend_dir = Path(__file__).resolve().parent.parent / "backend"
env_path = backend_dir / ".env"
load_dotenv(env_path)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


def check_config():
    """Check that Telegram credentials are configured."""
    if not BOT_TOKEN or not CHAT_ID:
        print("=" * 60)
        print("  Telegram Bot is NOT configured")
        print("=" * 60)
        print()
        if not BOT_TOKEN:
            print("  TELEGRAM_BOT_TOKEN is missing.")
        if not CHAT_ID:
            print("  TELEGRAM_CHAT_ID is missing.")
        print()
        print("  To set up a Telegram bot:")
        print("  1. Open Telegram and search for @BotFather")
        print("  2. Send /newbot and follow the prompts")
        print("  3. Copy the bot token you receive")
        print("  4. Send a message to your new bot, then visit:")
        print(f"     https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates")
        print("     to find your chat_id")
        print()
        print(f"  Add these to: {env_path}")
        print("    TELEGRAM_BOT_TOKEN=your_bot_token_here")
        print("    TELEGRAM_CHAT_ID=your_chat_id_here")
        print()
        sys.exit(1)


def test_get_me():
    """Test the getMe endpoint to verify bot token is valid."""
    print("-" * 50)
    print("Testing getMe endpoint...")
    print("-" * 50)
    try:
        resp = httpx.get(f"{TELEGRAM_API}/getMe", timeout=10)
        data = resp.json()
        if data.get("ok"):
            bot = data["result"]
            print(f"  Bot ID:       {bot['id']}")
            print(f"  Bot Name:     {bot.get('first_name', 'N/A')}")
            print(f"  Bot Username: @{bot.get('username', 'N/A')}")
            print(f"  Can Join Groups: {bot.get('can_join_groups', 'N/A')}")
            print("  [OK] Bot token is valid.")
            return True
        else:
            print(f"  [FAIL] API returned error: {data.get('description', 'Unknown error')}")
            return False
    except httpx.HTTPError as e:
        print(f"  [FAIL] HTTP error: {e}")
        return False


def test_send_message():
    """Send a test message to the configured chat."""
    print()
    print("-" * 50)
    print("Sending test message...")
    print("-" * 50)

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = (
        "\U0001f514 FX Trading System - Telegram Alert Test\n"
        "\n"
        "\u2705 Connection successful!\n"
        "Bot is ready to send trade alerts.\n"
        f"\nTimestamp: {current_time}"
    )

    try:
        resp = httpx.post(
            f"{TELEGRAM_API}/sendMessage",
            json={
                "chat_id": CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
            },
            timeout=10,
        )
        data = resp.json()
        if data.get("ok"):
            msg = data["result"]
            print(f"  Message ID: {msg['message_id']}")
            print(f"  Chat ID:    {msg['chat']['id']}")
            print(f"  Date:       {datetime.fromtimestamp(msg['date'])}")
            print("  [OK] Test message sent successfully!")
            return True
        else:
            print(f"  [FAIL] API returned error: {data.get('description', 'Unknown error')}")
            print(f"  Response: {data}")
            return False
    except httpx.HTTPError as e:
        print(f"  [FAIL] HTTP error: {e}")
        return False


def main():
    print()
    print("=" * 50)
    print("  FX Trading System - Telegram Bot Test")
    print("=" * 50)
    print(f"  .env path: {env_path}")
    print()

    check_config()

    bot_ok = test_get_me()
    msg_ok = test_send_message()

    print()
    print("=" * 50)
    if bot_ok and msg_ok:
        print("  ALL TESTS PASSED")
    else:
        print("  SOME TESTS FAILED")
        if not bot_ok:
            print("    - getMe failed (check your bot token)")
        if not msg_ok:
            print("    - sendMessage failed (check your chat ID)")
    print("=" * 50)
    print()

    sys.exit(0 if (bot_ok and msg_ok) else 1)


if __name__ == "__main__":
    main()
