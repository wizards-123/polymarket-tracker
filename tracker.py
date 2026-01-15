#!/usr/bin/env python3
"""
Polymarket Copy Trading Bot
Monitora trades do @cashy e envia notificações no Telegram
"""

import os
import json
import requests
from datetime import datetime

# Configurações (serão substituídas por secrets do GitHub)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
TARGET_WALLET = os.environ.get("TARGET_WALLET", "0x8f42ae0a01c0383c7ca8bd060b86a645ee74b88f")

# Seu bankroll e bankroll estimado do @cashy
YOUR_BANKROLL = float(os.environ.get("YOUR_BANKROLL", "50"))
TARGET_BANKROLL = float(os.environ.get("TARGET_BANKROLL", "25800"))

# Arquivo para rastrear trades já notificadas
STATE_FILE = "state.json"

# APIs
POLYMARKET_DATA_API = "https://data-api.polymarket.com"
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


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


def get_recent_trades():
    """Busca trades recentes do wallet alvo"""
    url = f"{POLYMARKET_DATA_API}/activity"
    params = {
        "user": TARGET_WALLET,
        "type": "TRADE",
        "limit": 20
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Erro ao buscar trades: {e}")
        return []


def calculate_size(trade_size_usd):
    """
    Calcula o tamanho da sua trade
    Regra: MAX(proporcional, $1)
    """
    proportional = trade_size_usd * (YOUR_BANKROLL / TARGET_BANKROLL)
    return max(proportional, 1.0)


def format_trade_message(trade):
    """Formata a mensagem de notificação"""
    side = trade.get("side", "UNKNOWN")
    side_emoji = "🟢 BUY" if side == "BUY" else "🔴 SELL"
    
    title = trade.get("title", "Unknown Market")
    outcome = trade.get("outcome", "?")
    price = trade.get("price", 0)
    size_tokens = trade.get("size", 0)
    size_usd = trade.get("usdcSize", 0)
    
    # Calcular seu tamanho sugerido
    your_size = calculate_size(size_usd)
    
    # Porcentagem do bankroll do @cashy
    cashy_pct = (size_usd / TARGET_BANKROLL) * 100 if TARGET_BANKROLL > 0 else 0
    
    # Link para o mercado
    slug = trade.get("slug", "")
    event_slug = trade.get("eventSlug", "")
    market_url = f"https://polymarket.com/event/{event_slug}/{slug}" if slug else "https://polymarket.com"
    
    message = f"""
🔔 *NOVA TRADE DETECTADA*

📊 *Mercado:* {title}
🔗 [Abrir no Polymarket]({market_url})

{side_emoji} *{outcome}*
💰 Preço: ${price:.2f}
📦 Tamanho @cashy: ${size_usd:.2f} ({cashy_pct:.2f}% do bankroll)

━━━━━━━━━━━━━━━━━━━━━
💡 *Sugestão para você:*
→ {side} *{outcome}* @ ~${price:.2f}
→ Tamanho: *${your_size:.2f}*
━━━━━━━━━━━━━━━━━━━━━

⏱️ Detectado: {datetime.now().strftime("%H:%M:%S")}
"""
    return message


def send_telegram_message(message):
    """Envia mensagem no Telegram"""
    url = f"{TELEGRAM_API}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        print("Mensagem enviada com sucesso!")
        return True
    except Exception as e:
        print(f"Erro ao enviar mensagem: {e}")
        return False


def create_trade_id(trade):
    """Cria um ID único para a trade"""
    return f"{trade.get('transactionHash', '')}_{trade.get('timestamp', '')}"


def main():
    print(f"=== Polymarket Tracker ===")
    print(f"Monitorando: {TARGET_WALLET}")
    print(f"Seu bankroll: ${YOUR_BANKROLL}")
    print(f"Bankroll alvo: ${TARGET_BANKROLL}")
    print()
    
    # Verificar configurações
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERRO: TELEGRAM_TOKEN e TELEGRAM_CHAT_ID são obrigatórios!")
        return
    
    # Carregar estado
    state = load_state()
    notified_trades = set(state.get("notified_trades", []))
    
    # Buscar trades recentes
    print("Buscando trades recentes...")
    trades = get_recent_trades()
    
    if not trades:
        print("Nenhuma trade encontrada ou erro na API")
        state["last_check"] = datetime.now().isoformat()
        save_state(state)
        return
    
    print(f"Encontradas {len(trades)} trades")
    
    # Processar trades
    new_trades = []
    for trade in trades:
        trade_id = create_trade_id(trade)
        
        if trade_id not in notified_trades:
            new_trades.append(trade)
            notified_trades.add(trade_id)
    
    print(f"Novas trades: {len(new_trades)}")
    
    # Enviar notificações para novas trades
    for trade in new_trades:
        print(f"\nNotificando trade: {trade.get('title', 'Unknown')}")
        message = format_trade_message(trade)
        send_telegram_message(message)
    
    # Salvar estado atualizado
    # Manter apenas os últimos 100 IDs para não crescer indefinidamente
    state["notified_trades"] = list(notified_trades)[-100:]
    state["last_check"] = datetime.now().isoformat()
    save_state(state)
    
    print(f"\nVerificação concluída: {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
