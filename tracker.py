#!/usr/bin/env python3
"""
Polymarket Copy Trading Bot v6
Monitora múltiplas wallets e envia notificações no Telegram
"""

import os
import json
import hashlib
import requests
from datetime import datetime, timezone, timedelta

# Configurações do Telegram
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Seu bankroll
YOUR_BANKROLL = float(os.environ.get("YOUR_BANKROLL", "50"))

# Timezone BRT (UTC-3)
BRT = timezone(timedelta(hours=-3))

# Wallets a monitorar
DEFAULT_WALLETS = [
    {
        "address": "0x8f42ae0a01c0383c7ca8bd060b86a645ee74b88f",
        "name": "cashy",
        "bankroll": 25800
    },
    {
        "address": "0x61837ce7e447a35cafd173dec3e0815326003834",
        "name": "Midas14",
        "bankroll": 1000
    }
]

def get_wallets():
    """Carrega configuração de wallets"""
    wallets_json = os.environ.get("WALLETS")
    if wallets_json:
        try:
            return json.loads(wallets_json)
        except:
            pass
    return DEFAULT_WALLETS

# Arquivo para rastrear trades já notificadas
STATE_FILE = "state.json"

# APIs
POLYMARKET_DATA_API = "https://data-api.polymarket.com"
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


def get_brt_now():
    """Retorna datetime atual em BRT"""
    return datetime.now(BRT)


def format_brt_datetime(dt=None):
    """Formata datetime em DD/MM/AAAA - HH:MM (BRT)"""
    if dt is None:
        dt = get_brt_now()
    return dt.strftime("%d/%m/%Y - %H:%M")


def timestamp_to_brt(timestamp_str):
    """Converte timestamp ISO da API para datetime BRT"""
    if not timestamp_str:
        return None
    try:
        # Tentar formato ISO com timezone
        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        return dt.astimezone(BRT)
    except:
        pass
    try:
        # Tentar formato ISO sem timezone (assume UTC)
        dt = datetime.fromisoformat(timestamp_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(BRT)
    except:
        pass
    try:
        # Tentar timestamp Unix em segundos
        dt = datetime.fromtimestamp(float(timestamp_str), tz=timezone.utc)
        return dt.astimezone(BRT)
    except:
        return None


def load_state():
    """Carrega o estado (trades já notificadas)"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"notified_trades": [], "last_check": None}


def save_state(state):
    """Salva o estado"""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def get_recent_trades(wallet_address):
    """Busca trades recentes de uma wallet"""
    url = f"{POLYMARKET_DATA_API}/activity"
    params = {
        "user": wallet_address,
        "type": "TRADE",
        "limit": 20
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Erro ao buscar trades de {wallet_address}: {e}")
        return []


def generate_trade_hash(trade, wallet_address):
    """Gera hash único para identificar uma trade"""
    fields = [
        wallet_address,
        str(trade.get("timestamp", "")),
        str(trade.get("title", "")),
        str(trade.get("outcome", "")),
        str(trade.get("side", "")),
        str(trade.get("price", "")),
        str(trade.get("usdcSize", "")),
        str(trade.get("transactionHash", "")),
    ]
    combined = "|".join(fields)
    return hashlib.sha256(combined.encode()).hexdigest()[:16]


def format_trade_message(trade, trader_name, trader_bankroll):
    """Formata a mensagem de notificação no novo formato"""
    side = trade.get("side", "UNKNOWN")
    outcome = trade.get("outcome", "?")
    title = trade.get("title", "Unknown Market")
    price = trade.get("price", 0)
    size_usd = trade.get("usdcSize", 0)

    # Emoji do círculo: verde para BUY, vermelho para SELL
    if side == "BUY":
        side_line = f'🟢 BUY "{outcome}" @${price:.2f}'
    else:
        side_line = f'🔴 SELL "{outcome}" @${price:.2f}'

    # Horário da trade em BRT
    trade_timestamp = trade.get("timestamp")
    trade_dt_brt = timestamp_to_brt(trade_timestamp)
    trade_time_str = format_brt_datetime(trade_dt_brt) if trade_dt_brt else "Horário indisponível"

    message = f"""@{trader_name} - {title}
{side_line}
Volume: ${size_usd:.2f}
{trade_time_str}"""

    return message


def send_telegram_message(message):
    """Envia mensagem no Telegram"""
    url = f"{TELEGRAM_API}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "disable_web_page_preview": True
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        print("  ✓ Mensagem enviada")
        return True
    except Exception as e:
        print(f"  ✗ Erro ao enviar: {e}")
        return False


def main():
    wallets = get_wallets()
    now_brt = format_brt_datetime()

    print(f"{'='*50}")
    print(f"Polymarket Tracker v6")
    print(f"Execução: {now_brt} (BRT)")
    print(f"{'='*50}")
    print(f"Monitorando {len(wallets)} wallets:")
    for w in wallets:
        print(f"  • @{w['name']}")
    print()

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERRO: TELEGRAM_TOKEN e TELEGRAM_CHAT_ID são obrigatórios!")
        return

    state = load_state()
    notified = set(state.get("notified_trades", []))
    new_trades_found = 0

    for wallet in wallets:
        address = wallet["address"]
        name = wallet["name"]
        bankroll = wallet.get("bankroll", 1000)

        print(f"\n--- @{name} ---")
        trades = get_recent_trades(address)

        if not trades:
            print("  Nenhuma trade encontrada")
            continue

        print(f"  {len(trades)} trades recentes")

        for trade in trades:
            trade_hash = generate_trade_hash(trade, address)

            if trade_hash in notified:
                continue

            print(f"  Nova trade: {trade.get('title', '?')} | {trade.get('side', '?')} {trade.get('outcome', '?')}")

            message = format_trade_message(trade, name, bankroll)
            if send_telegram_message(message):
                notified.add(trade_hash)
                new_trades_found += 1

    # Manter apenas os últimos 500 hashes
    notified_list = list(notified)
    if len(notified_list) > 500:
        notified_list = notified_list[-500:]

    state["notified_trades"] = notified_list
    state["last_check"] = get_brt_now().isoformat()
    save_state(state)

    print(f"\n{'='*50}")
    print(f"Resumo: {new_trades_found} novas trades notificadas")
    print(f"Total de trades rastreadas: {len(notified_list)}")


if __name__ == "__main__":
    main()
