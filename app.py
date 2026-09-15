# -*- coding: utf-8 -*-
"""Приёмник заявок с сайта sandowfitness.ru/bogoroditsk.

Полностью изолирован от московского sandow-lead-bot: не трогает 1С, не
трогает рабочий чат заказов Москвы. Заявки уходят в Telegram на chat_id
из переменной окружения TARGET_CHAT_ID — сейчас личка Ольги, после
создания группы «Заявки Сандов Богородицк» переключается одной правкой
переменной окружения в панели Render, без изменения кода.
"""
import os
import re
import time
import threading
from datetime import datetime, timezone, timedelta

import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TARGET_CHAT_ID = os.environ.get("TARGET_CHAT_ID", "").strip()
MSK = timezone(timedelta(hours=3))

_SEEN_LOCK = threading.Lock()
_SEEN = {}  # телефон -> unix time последней заявки


def _cors(resp, origin):
    resp.headers["Access-Control-Allow-Origin"] = origin or "*"
    resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


def api(method, **payload):
    r = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
        json=payload, timeout=15)
    return r.json()


@app.route("/health")
def health():
    return jsonify(ok=True, service="sandow-bogoroditsk-leads")


@app.route("/lead", methods=["POST", "OPTIONS"])
def lead():
    origin = request.headers.get("Origin", "")
    if request.method == "OPTIONS":
        return _cors(app.make_response(("", 204)), origin)

    data = request.get_json(silent=True) or request.form or {}

    # ловушка для роботов — скрытое поле, люди его не видят и не заполняют
    if (data.get("company") or "").strip():
        return _cors(jsonify(ok=True), origin)

    raw_phone = (data.get("phone") or "").strip()
    digits = re.sub(r"\D", "", raw_phone)
    if len(digits) < 10:
        return _cors(jsonify(ok=False, error="phone")), 400
    phone = "+7" + digits[-10:]

    name = (data.get("name") or "").strip()[:60]
    source = (data.get("source") or "").strip()[:80]  # форма-заявка / конструктор / липкая панель
    page = (data.get("page") or "").strip()[:120]
    extra = (data.get("extra") or "").strip()[:400]  # выбор конструктора и т.п.
    when = datetime.now(MSK).strftime("%d.%m в %H:%M")

    now = time.time()
    with _SEEN_LOCK:
        last = _SEEN.get(phone, 0)
        _SEEN[phone] = now
    if now - last < 600:
        return _cors(jsonify(ok=True, repeat=True), origin)

    text = (
        "🏗 <b>БОГОРОДИЦК — ЗАЯВКА С САЙТА</b>\n\n"
        f"<b>Имя:</b> {name or 'не указано'}\n"
        f"<b>Телефон:</b> <code>{phone}</code>\n"
        + (f"<b>Источник:</b> {source}\n" if source else "")
        + (f"<b>Страница:</b> {page}\n" if page else "")
        + (f"<b>Детали:</b> {extra}\n" if extra else "")
        + f"\n{when} МСК"
    )
    if TARGET_CHAT_ID:
        api("sendMessage", chat_id=TARGET_CHAT_ID, parse_mode="HTML", text=text)
    return _cors(jsonify(ok=True), origin)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
