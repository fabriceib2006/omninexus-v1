# ════════════════════════════════════════════════════════════════
# OMNINEXUS — tg_bot/bot.py
# Telegram Command & Control Terminal
# Full live signal bot with entry/SL/TP alert system
# ════════════════════════════════════════════════════════════════

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import json
import logging
import re
import threading
import time
from datetime import datetime
from pathlib import Path

from telegram import Update, Bot
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    ConversationHandler,
)
from config import config

logger = logging.getLogger('omninexus.telegram')

# ── CHALLENGE STATE FILE ───────────────────────────────────────
CHALLENGE_STATE_FILE = Path(
    os.path.dirname(os.path.abspath(__file__))
) / 'challenge_state.json'

# ── CONVERSATION STATES ────────────────────────────────────────
CAPITAL, TARGET, DAYS = range(3)


# ── CHALLENGE PERSISTENCE ──────────────────────────────────────

def save_challenge_state():
    state = {
        'active':     config.CHALLENGE_ACTIVE,
        'capital':    getattr(config, 'CHALLENGE_CAPITAL',    0),
        'target_pct': getattr(config, 'CHALLENGE_TARGET_PCT', 0),
        'days':       getattr(config, 'CHALLENGE_DAYS',       0),
        'start_date': (
            config.CHALLENGE_START_DATE.isoformat()
            if getattr(config, 'CHALLENGE_START_DATE', None)
            else None
        ),
    }
    with open(CHALLENGE_STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def load_challenge_state():
    if not CHALLENGE_STATE_FILE.exists():
        return
    try:
        with open(CHALLENGE_STATE_FILE, 'r') as f:
            state = json.load(f)
        config.CHALLENGE_ACTIVE     = state.get('active', False)
        config.CHALLENGE_CAPITAL    = state.get('capital', 0)
        config.CHALLENGE_TARGET_PCT = state.get('target_pct', 0)
        config.CHALLENGE_DAYS       = state.get('days', 0)
        raw = state.get('start_date')
        config.CHALLENGE_START_DATE = (
            datetime.fromisoformat(raw) if raw else None
        )
    except Exception as e:
        logger.warning(f'Challenge load error: {e}')


# ── ALERT SENDER ───────────────────────────────────────────────

async def send_alert(message: str, parse_mode: str = 'HTML'):
    """Sends message to Telegram. Called by all system components."""
    try:
        bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
        await bot.send_message(
            chat_id    = config.TELEGRAM_CHAT_ID,
            text       = message,
            parse_mode = parse_mode,
        )
        logger.info(f'Alert sent: {message[:60]}...')
    except Exception as e:
        logger.error(f'Alert send error: {e}')


# ── ALERT FORMATTER ────────────────────────────────────────────

def _format_entry_alert(alert: dict) -> str:
    inst = alert['instrument']
    dec  = 2 if inst == 'XAUUSD' else 5
    fmt  = f'{{:.{dec}f}}'
    return (
        f'🎯 <b>ENTRY HIT — {inst}</b>\n\n'
        f'Direction:   <b>{alert["direction"]}</b>\n'
        f'Entry Price: <b>{fmt.format(alert["entry"])}</b>\n'
        f'Stop Loss:   {fmt.format(alert["sl"])}\n'
        f'Take Profit: {fmt.format(alert["tp"])}\n'
        f'Current:     {fmt.format(alert["price"])}\n\n'
        f'<i>Trade is now active. Monitoring SL/TP...</i>'
    )


def _format_tp_alert(alert: dict) -> str:
    inst = alert['instrument']
    dec  = 2 if inst == 'XAUUSD' else 5
    fmt  = f'{{:.{dec}f}}'
    return (
        f'✅ <b>TAKE PROFIT HIT — {inst}</b>\n\n'
        f'Direction: <b>{alert["direction"]}</b>\n'
        f'TP Price:  <b>{fmt.format(alert["tp"])}</b>\n'
        f'Exit:      {fmt.format(alert["price"])}\n\n'
        f'🏆 <b>RESULT: WIN</b>'
    )


def _format_sl_alert(alert: dict, study: dict = None) -> str:
    inst = alert['instrument']
    dec  = 2 if inst == 'XAUUSD' else 5
    fmt  = f'{{:.{dec}f}}'

    notes_line = ''
    if study and study.get('notes'):
        notes = '\n'.join(
            f'• {n}' for n in study['notes']
        )
        notes_line = (
            f'\n\n🧠 <b>BRAIN ANALYSIS:</b>\n{notes}'
        )

    return (
        f'❌ <b>STOP LOSS HIT — {inst}</b>\n\n'
        f'Direction: <b>{alert["direction"]}</b>\n'
        f'SL Price:  <b>{fmt.format(alert["sl"])}</b>\n'
        f'Exit:      {fmt.format(alert["price"])}\n\n'
        f'📉 <b>RESULT: LOSS</b>'
        f'{notes_line}'
    )


# ── PRICE MONITOR LOOP ─────────────────────────────────────────

async def _monitor_loop(app: Application):
    """
    Background loop that checks active signal levels
    every 10 seconds and sends alerts when levels are hit.
    """
    logger.info('Signal monitor loop started')
    while True:
        try:
            from signals.engine import check_signal_levels
            alerts = check_signal_levels()

            for alert in alerts:
                alert_type = alert.get('type')
                if alert_type == 'ENTRY_HIT':
                    msg = _format_entry_alert(alert)
                elif alert_type == 'TP_HIT':
                    msg = _format_tp_alert(alert)
                elif alert_type == 'SL_HIT':
                    msg = _format_sl_alert(alert)
                else:
                    continue

                await send_alert(msg)

        except Exception as e:
            logger.error(f'Monitor loop error: {e}')

        await asyncio.sleep(10)


# ── /start ─────────────────────────────────────────────────────

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        '⚡ <b>OMNINEXUS v2 — ONLINE</b>\n\n'
        'Synthetic World-Mirror Engine\n'
        'XAUUSD · GBPUSD · GBPJPY\n\n'
        'Powered by Twelve Data + FRED + Finnhub\n\n'
        'Type /status for system health.\n'
        'Type /signal for live signals.\n'
        'Type /help for all commands.',
        parse_mode='HTML',
    )


# ── /help ──────────────────────────────────────────────────────

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        '⚡ <b>OMNINEXUS COMMAND LIST</b>\n\n'
        '<b>MARKET DATA</b>\n'
        '/status    — System health + API usage\n'
        '/prices    — Live prices for all pairs\n'
        '/signal    — Full signal analysis now\n'
        '/signals   — All pair signals + levels\n\n'
        '<b>INTELLIGENCE</b>\n'
        '/regime    — Market regime report\n'
        '/halflife  — Signal health report\n'
        '/darkpool  — Dark pool Z-scores\n'
        '/memory    — Episodic memory matches\n'
        '/history   — Historical data status\n\n'
        '<b>ACTIVE SIGNALS</b>\n'
        '/active    — Current active signals\n'
        '/losses    — Recent SL studies\n\n'
        '<b>CHALLENGE MODE</b>\n'
        '/challenge        — Start challenge\n'
        '/challenge_status — Live P&L\n'
        '/challenge_stop   — End challenge\n\n'
        '<b>SYSTEM</b>\n'
        '/kill      — Emergency stop\n'
        '/api       — API usage stats\n',
        parse_mode='HTML',
    )


# ── /status ────────────────────────────────────────────────────

async def status_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

    try:
        from data.market_data import (
            get_all_prices, get_market_status,
            get_api_usage, _streamer
        )
        prices   = get_all_prices()
        market   = get_market_status()
        api_use  = get_api_usage()
        ws_status= 'CONNECTED' if _streamer.connected else 'RECONNECTING'

        price_lines = ''
        for inst, price in prices.items():
            dec = 2 if inst == 'XAUUSD' else 5
            val = f'{price:.{dec}f}' if price else 'LOADING...'
            price_lines += f'{inst}:    <b>{val}</b>\n'

        await update.message.reply_text(
            f'📊 <b>SYSTEM STATUS</b>\n'
            f'<code>{now} UTC</code>\n\n'
            f'Engine:      ACTIVE\n'
            f'WebSocket:   {ws_status}\n'
            f'Session:     {market["session"]}\n'
            f'Market Open: {"YES" if market["is_open"] else "NO"}\n\n'
            f'<b>LIVE PRICES</b>\n'
            f'{price_lines}\n'
            f'<b>API BUDGET</b>\n'
            f'Used today:  {api_use["calls_today"]}/'
            f'{api_use["daily_budget"]}\n'
            f'Remaining:   {api_use["remaining"]}\n'
            f'Used:        {api_use["pct_used"]}%\n\n'
            f'<i>Signal data live from Twelve Data + FRED</i>',
            parse_mode='HTML',
        )
    except Exception as e:
        await update.message.reply_text(
            f'📊 <b>SYSTEM STATUS</b>\n'
            f'<code>{now} UTC</code>\n\n'
            f'Engine: ACTIVE\n'
            f'Error fetching live data: {e}\n\n'
            f'<i>Run /signal to force refresh</i>',
            parse_mode='HTML',
        )


# ── /prices ────────────────────────────────────────────────────

async def prices_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    try:
        from data.market_data import get_live_price
        now = datetime.utcnow().strftime('%H:%M:%S')
        lines = [
            f'💰 <b>LIVE PRICES</b>\n'
            f'<code>{now} UTC</code>\n'
        ]
        for inst in config.INSTRUMENTS:
            data = get_live_price(inst)
            dec  = 2 if inst == 'XAUUSD' else 5
            if data:
                price  = f'{data["price"]:.{dec}f}'
                source = data.get('source', 'ws')
                lines.append(
                    f'<b>{inst}</b>: {price} '
                    f'<code>[{source}]</code>'
                )
            else:
                lines.append(f'<b>{inst}</b>: LOADING...')

        await update.message.reply_text(
            '\n'.join(lines),
            parse_mode='HTML',
        )
    except Exception as e:
        await update.message.reply_text(
            f'❌ Price fetch error: {e}'
        )


# ── /signal ────────────────────────────────────────────────────

# ── PAIR SELECTION STATE ──────────────────────────────────────
PAIR_SELECT = 10  # conversation state for pair selection

async def signal_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    """Asks user to choose a pair before fetching signal.
    Saves API credits — fetches one pair instead of three."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    keyboard = [
        [
            InlineKeyboardButton(
                'XAUUSD (Gold)',   callback_data='sig_XAUUSD'
            ),
        ],
        [
            InlineKeyboardButton(
                'GBPUSD',          callback_data='sig_GBPUSD'
            ),
            InlineKeyboardButton(
                'GBPJPY',          callback_data='sig_GBPJPY'
            ),
        ],
        [
            InlineKeyboardButton(
                'ALL PAIRS (uses 3x credits)',
                callback_data='sig_ALL'
            ),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        '📡 <b>SELECT PAIR FOR SIGNAL</b>\n\n'
        'Choose one pair to save API credits.\n'
        'ALL PAIRS uses 3x more requests.',
        parse_mode='HTML',
        reply_markup=reply_markup,
    )


async def signal_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    """Handles pair selection button press."""
    query = update.callback_query
    await query.answer()

    choice = query.data  # e.g. sig_XAUUSD or sig_ALL

    if choice == 'sig_ALL':
        instruments = config.INSTRUMENTS
        await query.edit_message_text(
            '🔍 Analysing all 3 pairs... please wait.\n'
            '<i>(Uses ~12 API credits)</i>',
            parse_mode='HTML',
        )
    else:
        instruments = [choice.replace('sig_', '')]
        await query.edit_message_text(
            f'🔍 Analysing {instruments[0]}... please wait.\n'
            f'<i>(Uses ~4 API credits)</i>',
            parse_mode='HTML',
        )

    try:
        from signals.engine import (
            calculate_signal, format_signal_message
        )
        from data.market_data import get_api_usage

        for inst in instruments:
            sig = calculate_signal(inst)
            msg = format_signal_message(sig)
            await context.bot.send_message(
                chat_id    = query.message.chat_id,
                text       = msg,
                parse_mode = 'HTML',
            )
            await asyncio.sleep(0.3)

        # Show remaining API budget
        usage = get_api_usage()
        await context.bot.send_message(
            chat_id = query.message.chat_id,
            text    = (
                f'<i>API budget: '
                f'{usage["remaining"]} requests remaining today</i>'
            ),
            parse_mode='HTML',
        )

    except Exception as e:
        await context.bot.send_message(
            chat_id    = query.message.chat_id,
            text       = f'Signal error: {e}',
            parse_mode = 'HTML',
        )


# ── /signals ───────────────────────────────────────────────────

async def signals_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    """Same as /signal — shows pair selection."""
    await signal_command(update, context)


# ── /active ────────────────────────────────────────────────────

async def active_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    try:
        from signals.engine import get_active_signals_summary
        msg = get_active_signals_summary()
        await update.message.reply_text(
            f'📌 <b>ACTIVE SIGNALS</b>\n\n{msg}',
            parse_mode='HTML',
        )
    except Exception as e:
        await update.message.reply_text(
            f'❌ Error: {e}'
        )


# ── /losses ────────────────────────────────────────────────────

async def losses_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    """Shows last 3 SL studies from brain analysis."""
    try:
        study_file = Path(
            os.path.dirname(os.path.abspath(__file__))
        ).parent / 'signals' / 'loss_studies.json'

        if not study_file.exists():
            await update.message.reply_text(
                '🧠 No loss studies yet.\n'
                'Brain will study each SL hit automatically.'
            )
            return

        with open(study_file, 'r') as f:
            studies = json.load(f)

        if not studies:
            await update.message.reply_text(
                '🧠 No loss studies yet.'
            )
            return

        lines = ['🧠 <b>RECENT LOSS STUDIES</b>\n']
        for study in studies[-3:]:
            notes = '\n'.join(
                f'  • {n}' for n in study.get('notes', [])
            )
            lines.append(
                f'<b>{study["instrument"]} '
                f'{study["direction"]}</b>\n'
                f'{study["timestamp"][:19]}\n'
                f'Confidence: {study["confidence"]}%\n'
                f'Notes:\n{notes or "  None"}\n'
            )

        await update.message.reply_text(
            '\n'.join(lines),
            parse_mode='HTML',
        )
    except Exception as e:
        await update.message.reply_text(f'❌ Error: {e}')


# ── /history ───────────────────────────────────────────────────

async def history_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    try:
        from data.history import get_history_stats
        stats = get_history_stats()

        if not stats:
            await update.message.reply_text(
                '📚 No history files yet.\n'
                'History downloads automatically on startup.'
            )
            return

        lines = ['📚 <b>HISTORICAL DATA</b>\n']
        for name, info in sorted(stats.items()):
            if 'error' in info:
                lines.append(f'❌ {name}: corrupted')
            else:
                lines.append(
                    f'<b>{name}</b>: '
                    f'{info["bars"]} bars | '
                    f'{info["from"]} → {info["to"]} | '
                    f'{info["size_kb"]} KB'
                )

        await update.message.reply_text(
            '\n'.join(lines),
            parse_mode='HTML',
        )
    except Exception as e:
        await update.message.reply_text(f'❌ Error: {e}')


# ── /api ───────────────────────────────────────────────────────

async def api_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    try:
        from data.market_data import get_api_usage
        usage = get_api_usage()
        await update.message.reply_text(
            f'📡 <b>API USAGE</b>\n\n'
            f'Provider:   Twelve Data\n'
            f'Plan:       Free (800/day)\n'
            f'Used today: {usage["calls_today"]}\n'
            f'Remaining:  {usage["remaining"]}\n'
            f'Used:       {usage["pct_used"]}%\n\n'
            f'WebSocket:  Live prices (0 credits)\n'
            f'Finnhub:    News + Sentiment (60/min)\n'
            f'FRED:       Yields (unlimited)\n'
            f'yfinance:   History (unlimited)',
            parse_mode='HTML',
        )
    except Exception as e:
        await update.message.reply_text(f'❌ Error: {e}')


# ── /regime ────────────────────────────────────────────────────

async def regime_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    try:
        from brain.autoencoder import AutoencoderRegimeDetector
        ae = AutoencoderRegimeDetector()
        result = ae.detect_regime()
        await update.message.reply_text(
            f'🔬 <b>REGIME REPORT</b>\n\n'
            f'Autoencoder Error: {result.get("recon_error", "LOADING...")}\n'
            f'Regime State:      {result.get("regime", "LOADING...")}\n'
            f'Is Anomaly:        {result.get("is_anomaly", "LOADING...")}\n',
            parse_mode='HTML',
        )
    except Exception as e:
        await update.message.reply_text(
            f'🔬 <b>REGIME REPORT</b>\n\n'
            f'Brain layer loading...\n'
            f'<i>{e}</i>',
            parse_mode='HTML',
        )


# ── /halflife ──────────────────────────────────────────────────

async def halflife_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    try:
        from memory.half_life import SignalHalfLifeTracker
        tracker = SignalHalfLifeTracker()
        summary = tracker.get_summary()
        await update.message.reply_text(
            f'📉 <b>SIGNAL HALF-LIFE</b>\n\n'
            f'Signals tracked: {summary.get("total", 0)}\n'
            f'Healthy:         {summary.get("healthy", 0)}\n'
            f'Degraded:        {summary.get("degraded", 0)}\n',
            parse_mode='HTML',
        )
    except Exception as e:
        await update.message.reply_text(
            f'📉 <b>SIGNAL HALF-LIFE</b>\n\n'
            f'Memory layer loading...\n'
            f'<i>{e}</i>',
            parse_mode='HTML',
        )


# ── /darkpool ──────────────────────────────────────────────────

async def darkpool_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    try:
        from ingestion.darkpool import scan_dark_pools
        data = scan_dark_pools()
        results = data.get('results', {})

        lines = ['👻 <b>DARK POOL REPORT</b>\n']
        for symbol, info in results.items():
            z = info.get('z_score', 0)
            lines.append(
                f'{symbol}: {z:.2f}σ'
            )

        lines.append(
            f'\nAnomalies: {data.get("anomaly_count", 0)}\n'
            f'Threshold: 2.0σ'
        )
        await update.message.reply_text(
            '\n'.join(lines),
            parse_mode='HTML',
        )
    except Exception as e:
        await update.message.reply_text(
            f'👻 <b>DARK POOL REPORT</b>\n\n'
            f'Ingestion layer loading...\n<i>{e}</i>',
            parse_mode='HTML',
        )


# ── /memory ────────────────────────────────────────────────────

async def memory_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    try:
        from memory.fingerprint import MemoryFingerprintStore
        store   = MemoryFingerprintStore()
        matches = store.latest_n(5)

        if not matches:
            await update.message.reply_text(
                '🧠 <b>EPISODIC MEMORY</b>\n\n'
                'No fingerprints stored yet.\n'
                'Memory builds as the system runs.',
                parse_mode='HTML',
            )
            return

        lines = ['🧠 <b>EPISODIC MEMORY — LAST 5</b>\n']
        for m in matches:
            lines.append(
                f'{m.get("timestamp","?")[:10]}: '
                f'{m.get("instrument","?")} '
                f'{m.get("result","?")}'
            )
        await update.message.reply_text(
            '\n'.join(lines),
            parse_mode='HTML',
        )
    except Exception as e:
        await update.message.reply_text(
            f'🧠 <b>EPISODIC MEMORY</b>\n\n'
            f'Memory layer loading...\n<i>{e}</i>',
            parse_mode='HTML',
        )


# ── /kill ──────────────────────────────────────────────────────

async def kill_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    logger.critical('KILL SWITCH activated via Telegram')
    # Clear all active signals
    try:
        from signals.engine import _active_signals, _save_signals
        _active_signals.clear()
        _save_signals()
    except Exception:
        pass

    await update.message.reply_text(
        '🛑 <b>EMERGENCY STOP</b>\n\n'
        'All active signals cleared.\n'
        'Signal monitoring paused.\n\n'
        'Send /signal to re-activate.',
        parse_mode='HTML',
    )


# ── CHALLENGE HANDLERS ─────────────────────────────────────────

async def challenge_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if config.CHALLENGE_ACTIVE:
        await update.message.reply_text(
            '⚠️ <b>Challenge already active.</b>\n'
            'Use /challenge_status or /challenge_stop.',
            parse_mode='HTML',
        )
        return ConversationHandler.END

    await update.message.reply_text(
        '🏆 <b>CHALLENGE MODE SETUP</b>\n\n'
        'Question 1 of 3:\n'
        '<b>What is your starting capital in USD?</b>\n'
        '<i>Example: 500</i>',
        parse_mode='HTML',
    )
    return CAPITAL


async def challenge_capital(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    try:
        capital = float(update.message.text.strip())
        if capital <= 0:
            raise ValueError
        context.user_data['challenge_capital'] = capital
        await update.message.reply_text(
            f'✅ Capital: <b>${capital:,.2f}</b>\n\n'
            f'Question 2 of 3:\n'
            f'<b>Profit target percentage?</b>\n'
            f'<i>Example: 10 for 10%</i>',
            parse_mode='HTML',
        )
        return TARGET
    except ValueError:
        await update.message.reply_text(
            '❌ Enter a valid number. Example: 500'
        )
        return CAPITAL


async def challenge_target(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    try:
        target = float(update.message.text.strip())
        if target <= 0 or target > 100:
            raise ValueError
        context.user_data['challenge_target'] = target
        await update.message.reply_text(
            f'✅ Target: <b>{target}%</b>\n\n'
            f'Question 3 of 3:\n'
            f'<b>How many days?</b>\n'
            f'<i>Example: 30</i>',
            parse_mode='HTML',
        )
        return DAYS
    except ValueError:
        await update.message.reply_text(
            '❌ Enter a number between 1 and 100.'
        )
        return TARGET


async def challenge_days(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    try:
        days    = int(update.message.text.strip())
        if days <= 0:
            raise ValueError

        capital    = context.user_data['challenge_capital']
        target_pct = context.user_data['challenge_target']

        profit_target  = capital * (target_pct / 100)
        daily_target   = profit_target / days
        max_daily_loss = capital * config.MAX_DAILY_LOSS_PCT
        max_drawdown   = capital * config.MAX_TOTAL_DRAWDOWN_PCT

        config.CHALLENGE_ACTIVE     = True
        config.CHALLENGE_CAPITAL    = capital
        config.CHALLENGE_TARGET_PCT = target_pct
        config.CHALLENGE_DAYS       = days
        config.CHALLENGE_START_DATE = datetime.utcnow()

        save_challenge_state()

        await update.message.reply_text(
            f'🏆 <b>CHALLENGE ACTIVATED</b>\n\n'
            f'Capital:     <b>${capital:,.2f}</b>\n'
            f'Target:      <b>{target_pct}% = '
            f'${profit_target:,.2f}</b>\n'
            f'Duration:    <b>{days} days</b>\n'
            f'━━━━━━━━━━━━━━━━━━━━\n'
            f'Daily Target:   ${daily_target:,.2f}/day\n'
            f'Max Daily Loss: ${max_daily_loss:,.2f} (2%)\n'
            f'Max Drawdown:   ${max_drawdown:,.2f} (5%)\n'
            f'Min R:R:        1:{config.TP_MULTIPLIER}\n'
            f'━━━━━━━━━━━━━━━━━━━━\n\n'
            f'Signals now monitored under challenge rules.\n'
            f'Use /challenge_status to track progress.',
            parse_mode='HTML',
        )
        return ConversationHandler.END

    except ValueError:
        await update.message.reply_text(
            '❌ Enter a valid number of days.'
        )
        return DAYS


async def challenge_cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text('Challenge setup cancelled.')
    return ConversationHandler.END


async def challenge_status_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not config.CHALLENGE_ACTIVE:
        await update.message.reply_text(
            '⚠️ No active challenge. Use /challenge to start.'
        )
        return

    now            = datetime.utcnow()
    elapsed        = (now - config.CHALLENGE_START_DATE).days + 1
    remaining      = max(0, config.CHALLENGE_DAYS - elapsed)
    profit_target  = (
        config.CHALLENGE_CAPITAL * (config.CHALLENGE_TARGET_PCT / 100)
    )
    daily_target   = profit_target / config.CHALLENGE_DAYS

    # Count wins/losses from signal history
    try:
        from signals.engine import _signal_history
        wins   = sum(1 for s in _signal_history if s.get('result') == 'WIN')
        losses = sum(1 for s in _signal_history if s.get('result') == 'LOSS')
        total  = wins + losses
        win_rate = round(wins / total * 100, 1) if total > 0 else 0
    except Exception:
        wins = losses = total = 0
        win_rate = 0

    await update.message.reply_text(
        f'🏆 <b>CHALLENGE STATUS</b>\n'
        f'Day {elapsed} of {config.CHALLENGE_DAYS}\n\n'
        f'Capital:         ${config.CHALLENGE_CAPITAL:,.2f}\n'
        f'Target:          {config.CHALLENGE_TARGET_PCT}%\n'
        f'Daily Target:    ${daily_target:,.2f}\n'
        f'Days Remaining:  {remaining}\n\n'
        f'<b>SIGNAL PERFORMANCE</b>\n'
        f'Total Signals:   {total}\n'
        f'Wins:            {wins}\n'
        f'Losses:          {losses}\n'
        f'Win Rate:        {win_rate}%\n\n'
        f'<i>P&L tracking adds when execution is connected.</i>',
        parse_mode='HTML',
    )


async def challenge_stop_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not config.CHALLENGE_ACTIVE:
        await update.message.reply_text(
            '⚠️ No active challenge.'
        )
        return

    config.CHALLENGE_ACTIVE = False
    save_challenge_state()
    if CHALLENGE_STATE_FILE.exists():
        CHALLENGE_STATE_FILE.unlink()

    await update.message.reply_text(
        '🏁 <b>CHALLENGE ENDED</b>\n\n'
        'Final report saved.\n'
        'Use /losses to review brain studies.',
        parse_mode='HTML',
    )


# ── MAIN ───────────────────────────────────────────────────────

def main():
    logger.info('Starting OmniNexus Telegram bot...')

    load_challenge_state()

    # Start live price stream
    try:
        from data.market_data import start_price_stream
        start_price_stream()
        logger.info('Price stream started')
    except Exception as e:
        logger.warning(f'Price stream start error: {e}')

    # Run startup backtest in background — no manual trigger needed
    try:
        from brain.brain_update import run_startup_backtest
        threading.Thread(
            target=run_startup_backtest,
            daemon=True,
        ).start()
        logger.info('Startup backtest running in background')
    except Exception as e:
        logger.warning(f'Startup backtest error: {e}')

    # Download history if needed
    try:
        from data.history import download_all_history
        threading.Thread(
            target=download_all_history,
            kwargs={'force_reload': False},
            daemon=True,
        ).start()
        logger.info('History download started in background')
    except Exception as e:
        logger.warning(f'History download error: {e}')

    app = Application.builder().token(
        config.TELEGRAM_BOT_TOKEN
    ).build()

    # Challenge conversation
    challenge_handler = ConversationHandler(
        entry_points=[
            CommandHandler('challenge', challenge_start)
        ],
        states={
            CAPITAL: [MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                challenge_capital
            )],
            TARGET: [MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                challenge_target
            )],
            DAYS: [MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                challenge_days
            )],
        },
        fallbacks=[
            CommandHandler('cancel', challenge_cancel)
        ],
    )

    # Register all handlers
    app.add_handler(CommandHandler('start',            start_command))
    app.add_handler(CommandHandler('help',             help_command))
    app.add_handler(CommandHandler('status',           status_command))
    app.add_handler(CommandHandler('prices',           prices_command))
    app.add_handler(CommandHandler('signal',           signal_command))
    app.add_handler(CommandHandler('signals',          signals_command))
    app.add_handler(CommandHandler('active',           active_command))
    app.add_handler(CommandHandler('losses',           losses_command))
    app.add_handler(CommandHandler('history',          history_command))
    app.add_handler(CommandHandler('api',              api_command))
    app.add_handler(CommandHandler('regime',           regime_command))
    app.add_handler(CommandHandler('halflife',         halflife_command))
    app.add_handler(CommandHandler('darkpool',         darkpool_command))
    app.add_handler(CommandHandler('memory',           memory_command))
    app.add_handler(CommandHandler('kill',             kill_command))
    app.add_handler(CommandHandler('challenge_status', challenge_status_command))
    app.add_handler(CommandHandler('challenge_stop',   challenge_stop_command))
    app.add_handler(CallbackQueryHandler(signal_callback, pattern='^sig_'))
    app.add_handler(challenge_handler)

    # Start background loops
    async def post_init(application: Application):
        asyncio.create_task(_monitor_loop(application))

        # Auto-refresh indicators one pair at a time
        from data.market_data import auto_refresh_loop
        asyncio.create_task(auto_refresh_loop())

        # Weekend brain update scheduler
        from brain.brain_update import weekend_update_loop
        asyncio.create_task(weekend_update_loop())

        # Sunday calendar refresh
        from brain.event_interrupt import get_interrupt
        asyncio.create_task(
            get_interrupt().weekly_calendar_refresh_loop()
        )

        logger.info('All background loops started')

    app.post_init = post_init

    logger.info('OmniNexus Telegram bot LIVE')
    app.run_polling()


if __name__ == '__main__':
    main()