#!/usr/bin/env python3
"""
Polymarket Copy Trading Bot v7
Monitora múltiplas wallets e envia notificações no Telegram
- Formato: @Conta / Mercado (hiperlink) / Operação / Volume / Position / Data
- Position buscada em tempo real via API de positions
"""

import os
import json
import hashlib
import requests
from datetime import datetime, timezone, timedelta

# Configurações do Telegram
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

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


def timestamp_to_brt(timestamp_val):
    """Converte timestamp da API para datetime BRT"""
    if not timestamp_val:
        return None
    try:
        ts = float(timestamp_val)
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.astimezone(BRT)
    except (ValueError, TypeError, OSError):
        pass
    try:
        ts_str = str(timestamp_val)
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt.astimezone(BRT)
    except:
        pass
    try:
        dt = datetime.fromisoformat(str(timestamp_val))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
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


def get_position(wallet_address, condition_id):
    """Busca a posição atual de uma wallet num mercado específico"""
    url = f"{POLYMARKET_DATA_API}/positions"
    params = {
        "user": wallet_address,
        "market": condition_id,
        "sizeThreshold": 0
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        positions = response.json()

        # Somar currentValue de todas as posições neste mercado
        total_value = 0
        for pos in positions:
            cv = pos.get("currentValue", 0)
            if cv:
                total_value += float(cv)

        return total_value
    except Exception as e:
        print(f"  Erro ao buscar position: {e}")
        return None


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


def format_trade_message(trade, trader_name, wallet_address):
    """Formata a mensagem de notificação"""
    side = trade.get("side", "UNKNOWN")
    outcome = trade.get("outcome", "?")
    title = trade.get("title", "Unknown Market")
    price = trade.get("price", 0)
    size_usd = trade.get("usdcSize", 0)
    condition_id = trade.get("conditionId", "")

    # Emojis
    side_emoji = "➕ BUY" if side == "BUY" else "➖ SELL"
    outcome_emoji = "🟢" if outcome.upper() in ("YES", "Y") else "🔴"

    # Hiperlink para o mercado (HTML parse mode)
    slug = trade.get("slug", "")
    event_slug = trade.get("eventSlug", "")
    if slug and event_slug:
        market_url = f"https://polymarket.com/event/{event_slug}/{slug}"
        title_line = f'<a href="{market_url}">{title}</a>'
    else:
        title_line = title

    # Horário da trade em BRT
    trade_timestamp = trade.get("timestamp")
    trade_dt_brt = timestamp_to_brt(trade_timestamp)
    trade_time_str = format_brt_datetime(trade_dt_brt) if trade_dt_brt else "Horário indisponível"

    # Buscar posição atual
    position_value = get_position(wallet_address, condition_id)
    if position_value is not None:
        position_str = f"${position_value:,.2f}"
    else:
        position_str = "N/A"

    message = f"""@{trader_name}
{title_line}
{side_emoji} | {outcome_emoji} {outcome.upper()} | ${price:.2f}
Volume: ${size_usd:.2f} | Position: {position_str}
{trade_time_str}"""

    return message


def send_telegram_message(message):
    """Envia mensagem no Telegram"""
    url = f"{TELEGRAM_API}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        print("  ✓ Mensagem enviada")
        return True
    except Exception as e:
        print(f"  ✗ Erro ao enviar: {e}")
        try:
            print(f"  Resposta: {response.text}")
        except:
            pass
        return False


def main():
    wallets = get_wallets()
    now_brt = format_brt_datetime()

    print(f"{'='*50}")
    print(f"Polymarket Tracker v7")
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

            message = format_trade_message(trade, name, address)
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
