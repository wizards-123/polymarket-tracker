#!/usr/bin/env python3
"""
Polymarket Copy Trading Bot v4
Monitora múltiplas wallets e envia notificações no Telegram
- Horário da TRADE em BRT (não da execução)
- Deduplicação robusta de trades
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
    """Formata datetime em BRT"""
    if dt is None:
        dt = get_brt_now()
    return dt.strftime("%d/%m/%Y %H:%M:%S")


def timestamp_to_brt(timestamp):
    """
    Converte timestamp Unix (segundos) para datetime em BRT
    """
    try:
        if timestamp:
            # Timestamp em segundos -> datetime UTC -> converter para BRT
            dt_utc = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
            dt_brt = dt_utc.astimezone(BRT)
            return dt_brt
    except Exception as e:
        print(f"Erro ao converter timestamp {timestamp}: {e}")
    return None


def load_state():
    """Carrega o estado (trades já notificadas)"""
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                # Garantir que notified_trades é um dicionário
                if isinstance(data.get("notified_trades"), list):
                    # Migrar de lista para dicionário
                    data["notified_trades"] = {tid: True for tid in data["notified_trades"]}
                return data
    except Exception as e:
        print(f"Erro ao carregar estado: {e}")
    return {"notified_trades": {}, "last_check": None}


def save_state(state):
    """Salva o estado"""
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
        print(f"Estado salvo: {len(state.get('notified_trades', {}))} trades registradas")
    except Exception as e:
        print(f"Erro ao salvar estado: {e}")


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


def create_trade_id(trade, wallet_address):
    """
    Cria um ID único e robusto para a trade
    Usa hash de múltiplos campos para garantir unicidade
    """
    # Combinar múltiplos campos para criar ID único
    unique_string = "|".join([
        wallet_address.lower(),
        str(trade.get("transactionHash", "")),
        str(trade.get("timestamp", "")),
        str(trade.get("conditionId", "")),
        str(trade.get("side", "")),
        str(trade.get("size", "")),
        str(trade.get("price", ""))
    ])
    
    # Criar hash MD5 para ID compacto
    trade_hash = hashlib.md5(unique_string.encode()).hexdigest()[:16]
    
    return trade_hash


def format_trade_message(trade, trader_name, trader_bankroll):
    """Formata a mensagem de notificação"""
    side = trade.get("side", "UNKNOWN")
    side_emoji = "🟢 BUY" if side == "BUY" else "🔴 SELL"
    
    title = trade.get("title", "Unknown Market")
    outcome = trade.get("outcome", "?")
    price = trade.get("price", 0)
    size_usd = trade.get("usdcSize", 0)
    
    # Calcular seu tamanho sugerido
    your_size = calculate_size(size_usd, trader_bankroll)
    
    # Porcentagem do bankroll do trader
    trader_pct = (size_usd / trader_bankroll) * 100 if trader_bankroll > 0 else 0
    
    # Link para o mercado
    slug = trade.get("slug", "")
    event_slug = trade.get("eventSlug", "")
    market_url = f"https://polymarket.com/event/{event_slug}/{slug}" if slug else "https://polymarket.com"
    
    # Horário da TRADE (não da execução do bot)
    trade_timestamp = trade.get("timestamp")
    trade_dt_brt = timestamp_to_brt(trade_timestamp)
    
    if trade_dt_brt:
        trade_time_str = format_brt_datetime(trade_dt_brt)
    else:
        trade_time_str = "Horário indisponível"
    
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

🕐 Trade realizada: {trade_time_str} (BRT)
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
        print("  ✓ Mensagem enviada")
        return True
    except Exception as e:
        print(f"  ✗ Erro ao enviar: {e}")
        return False


def main():
    wallets = get_wallets()
    now_brt = format_brt_datetime()
    
    print(f"{'='*50}")
    print(f"Polymarket Tracker v4")
    print(f"Execução: {now_brt} (BRT)")
    print(f"{'='*50}")
    print(f"Seu bankroll: ${YOUR_BANKROLL}")
    print(f"Monitorando {len(wallets)} wallets:")
    for w in wallets:
        print(f"  • @{w['name']}: ${w['bankroll']:,}")
    print()
    
    # Verificar configurações
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERRO: TELEGRAM_TOKEN e TELEGRAM_CHAT_ID são obrigatórios!")
        return
    
    # Carregar estado
    state = load_state()
    notified_trades = state.get("notified_trades", {})
    print(f"Trades já notificadas no histórico: {len(notified_trades)}")
    print()
    
    total_new_trades = 0
    
    # Processar cada wallet
    for wallet in wallets:
        address = wallet["address"]
        name = wallet["name"]
        bankroll = wallet["bankroll"]
        
        print(f"[{name}] Buscando trades...")
        trades = get_recent_trades(address)
        
        if not trades:
            print(f"[{name}] Nenhuma trade encontrada")
            continue
        
        print(f"[{name}] {len(trades)} trades na API")
        
        # Processar trades
        new_trades = []
        for trade in trades:
            trade_id = create_trade_id(trade, address)
            
            if trade_id not in notified_trades:
                new_trades.append((trade, trade_id))
        
        print(f"[{name}] {len(new_trades)} trades NOVAS")
        total_new_trades += len(new_trades)
        
        # Enviar notificações apenas para trades novas
        for trade, trade_id in new_trades:
            print(f"[{name}] Notificando: {trade.get('title', 'Unknown')[:40]}...")
            message = format_trade_message(trade, name, bankroll)
            if send_telegram_message(message):
                # Marcar como notificada SOMENTE se enviou com sucesso
                notified_trades[trade_id] = {
                    "timestamp": get_brt_now().isoformat(),
                    "trader": name,
                    "title": trade.get("title", "")[:50]
                }
    
    # Limpar trades antigas (manter últimas 500)
    if len(notified_trades) > 500:
        sorted_trades = sorted(
            notified_trades.items(),
            key=lambda x: x[1].get("timestamp", "") if isinstance(x[1], dict) else "",
            reverse=True
        )
        notified_trades = dict(sorted_trades[:500])
        print(f"\nLimpeza: mantendo últimas 500 trades no histórico")
    
    # Salvar estado atualizado
    state["notified_trades"] = notified_trades
    state["last_check"] = get_brt_now().isoformat()
    save_state(state)
    
    print()
    print(f"{'='*50}")
    print(f"RESUMO")
    print(f"{'='*50}")
    print(f"Novas trades notificadas: {total_new_trades}")
    print(f"Total no histórico: {len(notified_trades)}")
    print(f"Concluído: {format_brt_datetime()}")


if __name__ == "__main__":
    main()
