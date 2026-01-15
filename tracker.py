#!/usr/bin/env python3
"""
Polymarket Copy Trading Bot v2
Monitora múltiplas wallets e envia notificações no Telegram
"""

import os
import json
import requests
from datetime import datetime

# Configurações do Telegram
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Seu bankroll
YOUR_BANKROLL = float(os.environ.get("YOUR_BANKROLL", "50"))

# Wallets a monitorar (formato: wallet:nome:bankroll)
# Configurado via variável de ambiente WALLETS ou usa padrão
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


def calculate_size(trade_size_usd, target_bankroll):
    """
    Calcula o tamanho da sua trade
    Regra: MAX(proporcional, $1)
    """
    if target_bankroll <= 0:
        return 1.0
    proportional = trade_size_usd * (YOUR_BANKROLL / target_bankroll)
    return max(proportional, 1.0)


def format_trade_message(trade, trader_name, trader_bankroll):
    """Formata a mensagem de notificação"""
    side = trade.get("side", "UNKNOWN")
    side_emoji = "🟢 BUY" if side == "BUY" else "🔴 SELL"
    
    title = trade.get("title", "Unknown Market")
    outcome = trade.get("outcome", "?")
    price = trade.get("price", 0)
    size_tokens = trade.get("size", 0)
    size_usd = trade.get("usdcSize", 0)
    
    # Calcular seu tamanho sugerido
    your_size = calculate_size(size_usd, trader_bankroll)
    
    # Porcentagem do bankroll do trader
    trader_pct = (size_usd / trader_bankroll) * 100 if trader_bankroll > 0 else 0
    
    # Link para o mercado
    slug = trade.get("slug", "")
    event_slug = trade.get("eventSlug", "")
    market_url = f"https://polymarket.com/event/{event_slug}/{slug}" if slug else "https://polymarket.com"
    
    message = f"""
🔔 *NOVA TRADE: @{trader_name}*

📊 *Mercado:* {title}
🔗 [Abrir no Polymarket]({market_url})

{side_emoji} *{outcome}*
💰 Preço: ${price:.2f}
📦 Tamanho @{trader_name}: ${size_usd:.2f} ({trader_pct:.1f}%)

━━━━━━━━━━━━━━━━━━━━━
💡 *Sugestão para você:*
→ {side} *{outcome}* @ ~${price:.2f}
→ Tamanho: *${your_size:.2f}*
━━━━━━━━━━━━━━━━━━━━━

⏱️ {datetime.now().strftime("%H:%M:%S")}
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


def create_trade_id(trade, wallet_address):
    """Cria um ID único para a trade"""
    return f"{wallet_address}_{trade.get('transactionHash', '')}_{trade.get('timestamp', '')}"


def main():
    wallets = get_wallets()
    
    print(f"=== Polymarket Tracker v2 ===")
    print(f"Seu bankroll: ${YOUR_BANKROLL}")
    print(f"Monitorando {len(wallets)} wallets:")
    for w in wallets:
        print(f"  - @{w['name']}: {w['address'][:10]}... (${w['bankroll']:,})")
    print()
    
    # Verificar configurações
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERRO: TELEGRAM_TOKEN e TELEGRAM_CHAT_ID são obrigatórios!")
        return
    
    # Carregar estado
    state = load_state()
    notified_trades = set(state.get("notified_trades", []))
    
    total_new_trades = 0
    
    # Processar cada wallet
    for wallet in wallets:
        address = wallet["address"]
        name = wallet["name"]
        bankroll = wallet["bankroll"]
        
        print(f"\nBuscando trades de @{name}...")
        trades = get_recent_trades(address)
        
        if not trades:
            print(f"  Nenhuma trade encontrada")
            continue
        
        print(f"  Encontradas {len(trades)} trades")
        
        # Processar trades
        new_trades = []
        for trade in trades:
            trade_id = create_trade_id(trade, address)
            
            if trade_id not in notified_trades:
                new_trades.append(trade)
                notified_trades.add(trade_id)
        
        print(f"  Novas trades: {len(new_trades)}")
        total_new_trades += len(new_trades)
        
        # Enviar notificações
        for trade in new_trades:
            print(f"  Notificando: {trade.get('title', 'Unknown')}")
            message = format_trade_message(trade, name, bankroll)
            send_telegram_message(message)
    
    # Salvar estado atualizado
    state["notified_trades"] = list(notified_trades)[-200:]  # Manter últimos 200
    state["last_check"] = datetime.now().isoformat()
    save_state(state)
    
    print(f"\n=== Concluído ===")
    print(f"Total de novas trades notificadas: {total_new_trades}")
    print(f"Horário: {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
