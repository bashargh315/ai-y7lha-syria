from flask import Flask, request, jsonify, send_from_directory
import json
import time
import os
import urllib.request
import urllib.parse
from pathlib import Path
import threading


app = Flask(__name__)


# =========================================================
# إعدادات المشروع
# =========================================================

DB = Path("data.json")

QR_FILE = "IMG-20260829-WA0010.jpg"

DEFAULT_SERVICES = {
    "AI محتوى للمطاعم": 15,
    "AI محتوى المنتجات": 15,
    "AI تنظيم العملاء والردود": 20,
    "AI تحليل وحل مشكلة النشاط": 10
}


# =========================================================
# قاعدة البيانات
# =========================================================

if not DB.exists():

    DB.write_text(
        json.dumps(
            {
                "leads": [],
                "orders": [],
                "services": DEFAULT_SERVICES
            },
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


def db():

    try:

        data = json.loads(
            DB.read_text(encoding="utf-8")
        )

    except Exception:

        data = {
            "leads": [],
            "orders": [],
            "services": DEFAULT_SERVICES.copy()
        }

    if "leads" not in data:
        data["leads"] = []

    if "orders" not in data:
        data["orders"] = []

    if "services" not in data:
        data["services"] = DEFAULT_SERVICES.copy()

    return data


def save(data):

    DB.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


# =========================================================
# Telegram
# =========================================================

def telegram_request(method, payload):

    token = os.getenv("TELEGRAM_BOT_TOKEN")

    if not token:

        print("Telegram token is missing")

        return False, None

    try:

        url = (
            f"https://api.telegram.org/"
            f"bot{token}/{method}"
        )

        encoded = urllib.parse.urlencode(
            payload
        ).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=encoded,
            method="POST"
        )

        with urllib.request.urlopen(
            req,
            timeout=20
        ) as response:

            raw = response.read().decode(
                "utf-8"
            )

            result = json.loads(raw)

            return (
                result.get("ok", False),
                result
            )

    except Exception as e:

        print(
            f"Telegram {method} error:",
            e
        )

        return False, None


def send_telegram(
    message,
    reply_markup=None
):

    chat_id = os.getenv(
        "TELEGRAM_CHAT_ID"
    )

    if not chat_id:

        print(
            "Telegram chat ID is missing"
        )

        return False

    payload = {
        "chat_id": chat_id,
        "text": message
    }

    if reply_markup:

        payload["reply_markup"] = json.dumps(
            reply_markup,
            ensure_ascii=False
        )

    ok, result = telegram_request(
        "sendMessage",
        payload
    )

    return ok


def answer_callback(callback_id):

    if not callback_id:

        return

    telegram_request(
        "answerCallbackQuery",
        {
            "callback_query_id": callback_id,
            "text": "تم استلام التأكيد."
        }
    )


# =========================================================
# Telegram Webhook
# =========================================================

def get_app_url():

    # Render يوفر هذا المتغير تلقائيًا
    render_url = os.getenv(
        "RENDER_EXTERNAL_URL"
    )

    if render_url:

        return render_url.rstrip("/")

    # إمكانية وضع الرابط يدويًا
    app_url = os.getenv(
        "APP_URL"
    )

    if app_url:

        return app_url.rstrip("/")

    return None


def setup_telegram_webhook():

    token = os.getenv(
        "TELEGRAM_BOT_TOKEN"
    )

    if not token:

        print(
            "Telegram webhook skipped: "
            "TELEGRAM_BOT_TOKEN missing"
        )

        return

    app_url = get_app_url()

    if not app_url:

        print(
            "Telegram webhook skipped: "
            "APP_URL/RENDER_EXTERNAL_URL missing"
        )

        return

    webhook_url = (
        f"{app_url}/telegram/webhook"
    )

    ok, result = telegram_request(
        "setWebhook",
        {
            "url": webhook_url
        }
    )

    if ok:

        print(
            "Telegram webhook configured:",
            webhook_url
        )

    else:

        print(
            "Telegram webhook configuration failed:",
            result
        )


# =========================================================
# البحث عن العميل
# =========================================================

def find_lead(data, lead_id):

    for lead in data["leads"]:

        if lead.get("id") == lead_id:

            return lead

    return None


def find_order(data, order_id):

    for order in data["orders"]:

        if order.get("id") == order_id:

            return order

    return None


# =========================================================
# إنشاء رسالة تأكيد الدفع
# =========================================================

def payment_confirmation_keyboard(
    order_id
):

    return {
        "inline_keyboard": [
            [
                {
                    "text": "✅ تأكيد استلام الدفع",
                    "callback_data":
                        f"confirm_payment:{order_id}"
                }
            ]
        ]
    }


def send_payment_notification(
    order,
    client
):

    if client:

        client_name = client.get(
            "name",
            "غير معروف"
        )

        client_contact = client.get(
            "contact",
            "غير معروف"
        )

        client_problem = client.get(
            "problem",
            "غير معروف"
        )

    else:

        client_name = "غير معروف"
        client_contact = "غير معروف"
        client_problem = "غير معروف"


    message = f"""
🔔 طلب دفع جديد

🆔 رقم الطلب:
{order["id"]}

🛠 الخدمة:
{order["service"]}

💵 السعر:
${order["price_usd"]}

👤 العميل:
{client_name}

📞 التواصل:
{client_contact}

📝 المشكلة:
{client_problem}

⚠️ العميل ضغط "دفعت".

قم بالتحقق يدويًا من وصول المبلغ في شام كاش.

بعد التأكد اضغط الزر بالأسفل.
"""


    return send_telegram(
        message,
        payment_confirmation_keyboard(
            order["id"]
        )
    )


# =========================================================
# بدء تنفيذ AI - المرحلة الحالية
# =========================================================

def notify_ai_ready(order):

    message = f"""
🤖 الطلب جاهز للذكاء الاصطناعي

🆔 رقم الطلب:
{order["id"]}

🛠 الخدمة:
{order["service"]}

💵 السعر:
${order["price_usd"]}

✅ تم تأكيد استلام الدفع يدويًا.

الحالة الحالية:
ready_for_ai

سيتم ربط محرك تنفيذ AI في المرحلة التالية.
"""

    return send_telegram(
        message
    )


# =========================================================
# الصفحة الرئيسية
# =========================================================

@app.get("/")
def home():

    return send_from_directory(
        ".",
        "index.html"
    )


# =========================================================
# لوحة الإدارة الحالية
# =========================================================

@app.get("/admin")
def admin():

    return send_from_directory(
        ".",
        "index.html"
    )


# =========================================================
# QR شام كاش
# =========================================================

@app.get("/qr")
def qr():

    qr_path = Path(QR_FILE)

    if not qr_path.exists():

        return jsonify(
            {
                "ok": False,
                "error":
                    "QR image not found"
            }
        ), 404

    return send_from_directory(
        ".",
        QR_FILE
    )


# =========================================================
# الخدمات والأسعار
# =========================================================

@app.get("/api/services")
def services():

    data = db()

    return jsonify(
        data["services"]
    )


# =========================================================
# إنشاء عميل / Lead
# =========================================================

@app.post("/api/lead")
def lead():

    data = db()

    body = request.json or {}

    name = str(
        body.get("name", "")
    ).strip()

    contact = str(
        body.get("contact", "")
    ).strip()

    problem = str(
        body.get("problem", "")
    ).strip()

    link = str(
        body.get("link", "")
    ).strip()


    if not name or not contact or not problem:

        return jsonify(
            {
                "ok": False,
                "error":
                    "الاسم ووسيلة التواصل ووصف المشكلة مطلوبة"
            }
        ), 400


    now = time.time()


    # منع الطلب المتكرر خلال 10 دقائق
    for old in data["leads"]:

        if (
            old.get("name") == name
            and old.get("contact") == contact
            and old.get("problem") == problem
            and now - old.get(
                "created_at",
                0
            ) < 600
        ):

            return jsonify(
                {
                    "ok": True,
                    **old
                }
            )


    lead_id = (
        "L" +
        str(
            int(
                time.time() * 1000
            )
        )
    )


    new_lead = {

        "id": lead_id,

        "name": name,

        "contact": contact,

        "problem": problem,

        "link": link,

        "status": "new",

        "created_at": now

    }


    data["leads"].append(
        new_lead
    )

    save(data)


    return jsonify(
        {
            "ok": True,
            **new_lead
        }
    )


# =========================================================
# إنشاء طلب
# =========================================================

@app.post("/api/order")
def order():

    data = db()

    body = request.json or {}

    lead_id = body.get(
        "lead_id"
    )

    service = body.get(
        "service"
    )


    if not lead_id or not service:

        return jsonify(
            {
                "ok": False,
                "error":
                    "بيانات الطلب ناقصة"
            }
        ), 400


    if service not in data["services"]:

        return jsonify(
            {
                "ok": False,
                "error":
                    "الخدمة غير موجودة"
            }
        ), 400


    lead = find_lead(
        data,
        lead_id
    )


    if not lead:

        return jsonify(
            {
                "ok": False,
                "error":
                    "العميل غير موجود"
            }
        ), 404


    active_statuses = [

        "awaiting_payment",

        "payment_submitted",

        "payment_verified_manual",

        "ready_for_ai",

        "processing",

        "completed"

    ]


    # منع إنشاء نفس الطلب مرتين
    for old in data["orders"]:

        if (
            old.get("lead_id") == lead_id
            and old.get("service") == service
            and old.get("status")
            in active_statuses
        ):

            return jsonify(
                {
                    "ok": True,

                    "id": old["id"],

                    "lead_id":
                        old["lead_id"],

                    "service":
                        old["service"],

                    "price":
                        old["price"],

                    "price_usd":
                        old["price_usd"],

                    "status":
                        old["status"]
                }
            )


    order_id = (

        "ORD" +

        str(
            int(
                time.time() * 1000
            )
        )

    )


    price = float(
        data["services"][service]
    )


    new_order = {

        "id": order_id,

        "lead_id": lead_id,

        "service": service,

        "price": price,

        "price_usd": price,

        "status":
            "awaiting_payment",

        "created_at":
            time.time()

    }


    data["orders"].append(
        new_order
    )

    save(data)


    return jsonify(
        {
            "ok": True,

            "id": order_id,

            "lead_id": lead_id,

            "service": service,

            "price": price,

            "price_usd": price,

            "status":
                "awaiting_payment"
        }
    )


# =========================================================
# العميل يقول: دفعت
# =========================================================

@app.post("/api/paid")
def paid():

    data = db()

    body = request.json or {}

    order_id = body.get(
        "order_id"
    )


    if not order_id:

        return jsonify(
            {
                "ok": False,
                "error":
                    "رقم الطلب مفقود"
            }
        ), 400


    order = find_order(
        data,
        order_id
    )


    if not order:

        return jsonify(
            {
                "ok": False,
                "error":
                    "الطلب غير موجود"
            }
        ), 404


    # إذا تم الإرسال مسبقًا
    if order["status"] in [

        "payment_submitted",

        "payment_verified_manual",

        "ready_for_ai",

        "processing",

        "completed"

    ]:

        return jsonify(
            {
                "ok": True,

                "already_submitted":
                    True,

                "telegram_sent":
                    True,

                "order":
                    order
            }
        )


    order["status"] = (
        "payment_submitted"
    )

    order["payment_submitted_at"] = (
        time.time()
    )


    client = find_lead(
        data,
        order["lead_id"]
    )


    save(data)


    # إرسال Telegram
    telegram_sent = (
        send_payment_notification(
            order,
            client
        )
    )


    return jsonify(
        {
            "ok": True,

            "already_submitted":
                False,

            "telegram_sent":
                telegram_sent,

            "order":
                order
        }
    )


# =========================================================
# تأكيد الدفع من لوحة الإدارة
# =========================================================

@app.post("/api/verify")
def verify():

    data = db()

    body = request.json or {}

    order_id = body.get(
        "order_id"
    )


    if not order_id:

        return jsonify(
            {
                "ok": False,
                "error":
                    "رقم الطلب مفقود"
            }
        ), 400


    order = find_order(
        data,
        order_id
    )


    if not order:

        return jsonify(
            {
                "ok": False,
                "error":
                    "الطلب غير موجود"
            }
        ), 404


    # إذا كان مكتملًا أو قيد التنفيذ
    if order["status"] in [

        "processing",

        "completed"

    ]:

        return jsonify(
            {
                "ok": True,
                "order": order
            }
        )


    # إذا كان مؤكدًا مسبقًا
    if order["status"] == "ready_for_ai":

        return jsonify(
            {
                "ok": True,
                "already_verified":
                    True,
                "order": order
            }
        )


    order["status"] = (
        "ready_for_ai"
    )

    order["payment_verified_at"] = (
        time.time()
    )

    save(data)


    # إرسال إشعار بأن AI أصبح جاهزًا
    ai_notification_sent = (
        notify_ai_ready(
            order
        )
    )


    return jsonify(
        {
            "ok": True,

            "already_verified":
                False,

            "ai_notification_sent":
                ai_notification_sent,

            "order":
                order
        }
    )


# =========================================================
# Telegram Webhook
# =========================================================

@app.post("/telegram/webhook")
def telegram_webhook():

    update = request.get_json(
        silent=True
    ) or {}


    callback = update.get(
        "callback_query"
    )


    # لسنا بحاجة لمعالجة الرسائل العادية هنا
    if not callback:

        return jsonify(
            {
                "ok": True
            }
        )


    callback_id = callback.get(
        "id"
    )

    callback_data = callback.get(
        "data",
        ""
    )


    answer_callback(
        callback_id
    )


    # نتأكد أن الزر خاص بتأكيد الدفع
    prefix = "confirm_payment:"


    if not callback_data.startswith(
        prefix
    ):

        return jsonify(
            {
                "ok": True
            }
        )


    order_id = callback_data[
        len(prefix):
    ]


    data = db()


    order = find_order(
        data,
        order_id
    )


    if not order:

        # إخبار المالك أن الطلب غير موجود
        send_telegram(
            f"""
❌ تعذر تأكيد الدفع

رقم الطلب:
{order_id}

السبب:
الطلب غير موجود.
"""
        )

        return jsonify(
            {
                "ok": True
            }
        )


    # منع التأكيد مرتين
    if order["status"] in [

        "ready_for_ai",

        "processing",

        "completed"

    ]:

        send_telegram(
            f"""
ℹ️ هذا الطلب مؤكد مسبقًا

🆔 {order["id"]}

الحالة:
{order["status"]}
"""
        )

        return jsonify(
            {
                "ok": True
            }
        )


    # لا نسمح بالتأكيد إلا بعد أن يقول العميل إنه دفع
    if order["status"] != (
        "payment_submitted"
    ):

        send_telegram(
            f"""
⚠️ لا يمكن تأكيد هذا الطلب الآن

🆔 {order["id"]}

الحالة الحالية:
{order["status"]}

يجب أن يضغط العميل أولًا:
"دفعت — أرسل للمراجعة"
"""
        )

        return jsonify(
            {
                "ok": True
            }
        )


    # تأكيد الدفع
    order["status"] = (
        "ready_for_ai"
    )

    order["payment_verified_at"] = (
        time.time()
    )

    order["payment_verified_source"] = (
        "telegram_button"
    )


    save(data)


    # إرسال رسالة نجاح
    send_telegram(
        f"""
✅ تم تأكيد استلام الدفع

🆔 رقم الطلب:
{order["id"]}

🛠 الخدمة:
{order["service"]}

💵 السعر:
${order["price_usd"]}

الحالة:
ready_for_ai

🤖 الطلب أصبح جاهزًا لبدء تنفيذ AI.
"""
    )


    # إشعار منفصل ببدء مرحلة AI
    notify_ai_ready(
        order
    )


    return jsonify(
        {
            "ok": True
        }
    )


# =========================================================
# فحص حالة الطلب
# =========================================================

@app.get("/api/order/<order_id>")
def order_status(order_id):

    data = db()

    order = find_order(
        data,
        order_id
    )


    if not order:

        return jsonify(
            {
                "ok": False,
                "error":
                    "الطلب غير موجود"
            }
        ), 404


    # لا نرسل معلومات العميل الحساسة
    return jsonify(
        {
            "ok": True,

            "order": {

                "id":
                    order["id"],

                "service":
                    order["service"],

                "price_usd":
                    order["price_usd"],

                "status":
                    order["status"],

                "result":
                    order.get(
                        "result"
                    )

            }
        }
    )


# =========================================================
# API الإدارة الحالية
# =========================================================

@app.get("/api/admin")
def admin_api():

    return jsonify(
        db()
    )


# =========================================================
# فحص صحة التطبيق
# =========================================================

@app.get("/health")
def health():

    return jsonify(
        {
            "ok": True,

            "service":
                "AI يحلها سوريا",

            "telegram":
                bool(
                    os.getenv(
                        "TELEGRAM_BOT_TOKEN"
                    )
                ),

            "qr":
                Path(
                    QR_FILE
                ).exists()
        }
    )


# =========================================================
# تشغيل التطبيق
# =========================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )


    # محاولة إعداد Telegram
    # بعد تشغيل Flask
    threading.Thread(
        target=setup_telegram_webhook,
        daemon=True
    ).start()


    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
