# Polymarket Copy Trading Bot

Bot que monitora as trades do @cashy no Polymarket e envia notificações no Telegram com sugestões de sizing proporcional ao seu bankroll.

## Como funciona

- A cada 5 minutos, o bot verifica se o @cashy fez novas trades
- Se houver trade nova, você recebe uma notificação no Telegram com:
  - Mercado e direção (BUY/SELL)
  - Preço de entrada
  - Tamanho sugerido para você (proporcional ou mínimo de $1)
  - Link direto para o mercado

## Configuração

### Passo 1: Fork este repositório

Clique no botão **Fork** no canto superior direito desta página.

### Passo 2: Configurar os Secrets

No seu repositório (fork), vá em:
**Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Adicione os seguintes secrets:

| Nome | Valor |
|------|-------|
| `TELEGRAM_TOKEN` | `8522671399:AAG63jJ7gTkSWu4lIVv81RAJ0iIST97ecMM` |
| `TELEGRAM_CHAT_ID` | `799385529` |
| `TARGET_WALLET` | `0x8f42ae0a01c0383c7ca8bd060b86a645ee74b88f` |
| `YOUR_BANKROLL` | `50` |
| `TARGET_BANKROLL` | `25800` |

### Passo 3: Ativar GitHub Actions

1. Vá na aba **Actions** do seu repositório
2. Clique em **I understand my workflows, go ahead and enable them**
3. Clique no workflow **Polymarket Tracker**
4. Clique em **Enable workflow** (se necessário)

### Passo 4: Testar

1. Na aba **Actions**, clique em **Polymarket Tracker**
2. Clique em **Run workflow** → **Run workflow**
3. Aguarde alguns segundos e verifique seu Telegram

## Regra de Sizing

```
seu_tamanho = MAX(proporcional, $1)

onde:
  proporcional = trade_cashy × (seu_bankroll / bankroll_cashy)
```

Exemplos com bankroll de $50 e @cashy com $25,800:

| @cashy aposta | Proporcional | Você aposta |
|---------------|--------------|-------------|
| $100 | $0.19 | $1.00 (mínimo) |
| $500 | $0.97 | $1.00 (mínimo) |
| $1,000 | $1.94 | $1.94 |
| $5,000 | $9.70 | $9.70 |

## Ajustes

Para alterar seu bankroll ou o wallet monitorado, edite os secrets no GitHub.

## Limitações

- Delay de até 5 minutos entre a trade do @cashy e sua notificação
- GitHub Actions pode ter atrasos ocasionais
- O bot não executa trades automaticamente (você precisa fazer manualmente)

## Custos

**Gratuito.** GitHub Actions oferece 2,000 minutos/mês grátis, suficiente para rodar 24/7.
