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
# إعداد Gemini
# =========================================================

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-2.5-flash"
)


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
            DB.read_text(
                encoding="utf-8"
            )
        )

    except Exception as e:

        print(
            "Database read error:",
            e
        )

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
# البحث عن عميل
# =========================================================

def find_lead(data, lead_id):

    for lead in data["leads"]:

        if lead.get("id") == lead_id:

            return lead

    return None


# =========================================================
# البحث عن طلب
# =========================================================

def find_order(data, order_id):

    for order in data["orders"]:

        if order.get("id") == order_id:

            return order

    return None


# =========================================================
# Telegram API
# =========================================================

def telegram_request(method, payload):

    token = os.getenv(
        "TELEGRAM_BOT_TOKEN"
    )

    if not token:

        print(
            "Telegram token is missing"
        )

        return False, None

    try:

        url = (
            "https://api.telegram.org/"
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
                result.get(
                    "ok",
                    False
                ),
                result
            )

    except Exception as e:

        print(
            f"Telegram {method} error:",
            e
        )

        return False, None


# =========================================================
# إرسال Telegram
# =========================================================

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


# =========================================================
# جواب زر Telegram
# =========================================================

def answer_callback(
    callback_id,
    text="تم تنفيذ العملية."
):

    if not callback_id:

        return

    telegram_request(
        "answerCallbackQuery",
        {
            "callback_query_id":
                callback_id,

            "text":
                text
        }
    )


# =========================================================
# إزالة زر التأكيد من Telegram
# =========================================================

def remove_telegram_button(
    callback
):

    try:

        message = callback.get(
            "message"
        )

        if not message:

            return

        chat = message.get(
            "chat",
            {}
        )

        chat_id = chat.get(
            "id"
        )

        message_id = message.get(
            "message_id"
        )

        if not chat_id or not message_id:

            return

        telegram_request(
            "editMessageReplyMarkup",
            {
                "chat_id":
                    chat_id,

                "message_id":
                    message_id,

                "reply_markup":
                    json.dumps(
                        {
                            "inline_keyboard": []
                        }
                    )
            }
        )

    except Exception as e:

        print(
            "Remove Telegram button error:",
            e
        )


# =========================================================
# زر تأكيد الدفع
# =========================================================

def payment_confirmation_keyboard(
    order_id
):

    return {

        "inline_keyboard": [

            [

                {
                    "text":
                        "✅ تأكيد استلام الدفع",

                    "callback_data":
                        f"confirm_payment:{order_id}"
                }

            ]

        ]

    }


# =========================================================
# إعداد Telegram Webhook
# =========================================================

def get_app_url():

    render_url = os.getenv(
        "RENDER_EXTERNAL_URL"
    )

    if render_url:

        return render_url.rstrip("/")

    app_url = os.getenv(
        "APP_URL"
    )

    if app_url:

        return app_url.rstrip("/")

    return (
        "https://ai-y7lha-syria.onrender.com"
    )


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

    webhook_url = (
        f"{app_url}/telegram/webhook"
    )

    ok, result = telegram_request(
        "setWebhook",
        {
            "url":
                webhook_url
        }
    )

    if ok:

        print(
            "Telegram webhook configured:",
            webhook_url
        )

    else:

        print(
            "Telegram webhook failed:",
            result
        )


# =========================================================
# Gemini API
# =========================================================

def gemini_request(prompt):

    api_key = os.getenv(
        "GEMINI_API_KEY"
    )

    if not api_key:

        return (
            False,
            "GEMINI_API_KEY غير موجود في Render."
        )

    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/{GEMINI_MODEL}:generateContent"
    )

    payload = {

        "contents": [

            {

                "role":
                    "user",

                "parts": [

                    {
                        "text":
                            prompt
                    }

                ]

            }

        ],

        "generationConfig": {

            "temperature":
                0.7,

            "maxOutputTokens":
                4000

        }

    }

    try:

        body = json.dumps(
            payload,
            ensure_ascii=False
        ).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type":
                    "application/json",

                "x-goog-api-key":
                    api_key
            }
        )

        with urllib.request.urlopen(
            req,
            timeout=120
        ) as response:

            raw = response.read().decode(
                "utf-8"
            )

            result = json.loads(raw)

        candidates = result.get(
            "candidates",
            []
        )

        if not candidates:

            error_message = result.get(
                "error",
                {}
            ).get(
                "message",
                "Gemini لم يعطِ نتيجة."
            )

            return (
                False,
                error_message
            )

        content = candidates[0].get(
            "content",
            {}
        )

        parts = content.get(
            "parts",
            []
        )

        texts = []

        for part in parts:

            text = part.get(
                "text"
            )

            if text:

                texts.append(
                    text
                )

        final_text = "\n".join(
            texts
        ).strip()

        if final_text:

            return (
                True,
                final_text
            )

        return (
            False,
            "Gemini أعاد استجابة بدون نص."
        )

    except urllib.error.HTTPError as e:

        try:

            error_body = e.read().decode(
                "utf-8"
            )

            error_data = json.loads(
                error_body
            )

            error_message = error_data.get(
                "error",
                {}
            ).get(
                "message",
                error_body
            )

        except Exception:

            error_message = str(e)

        print(
            "Gemini HTTP error:",
            error_message
        )

        return (
            False,
            f"Gemini HTTP Error {e.code}: {error_message}"
        )

    except Exception as e:

        print(
            "Gemini error:",
            e
        )

        return (
            False,
            str(e)
        )


# =========================================================
# بناء مهمة AI
# =========================================================

def build_ai_prompt(
    order,
    lead
):

    name = lead.get(
        "name",
        "العميل"
    )

    problem = lead.get(
        "problem",
        ""
    )

    link = lead.get(
        "link",
        ""
    )

    service = order.get(
        "service",
        ""
    )

    prompt = f"""
أنت الذكاء الاصطناعي التنفيذي في شركة
"AI يحلها سوريا".

مهمتك تنفيذ الخدمة التي دفع العميل ثمنها.

بيانات العميل:
الاسم: {name}

الخدمة المطلوبة:
{service}

مشكلة العميل:
{problem}

رابط النشاط إن وجد:
{link}

نفّذ العمل بشكل عملي ومفيد، وليس مجرد نصائح عامة.

إذا كانت الخدمة:

- AI محتوى للمطاعم:
  أنشئ محتوى تسويقي عملي مناسب للمطعم،
  مثل منشورات جاهزة، أفكار عروض،
  نصوص إعلانية وأفكار فيديوهات قصيرة.

- AI محتوى المنتجات:
  أنشئ وصفًا احترافيًا للمنتجات،
  عناوين تسويقية، منشورات وإعلانات جاهزة،
  ونقاط بيع قوية.

- AI تنظيم العملاء والردود:
  أنشئ نظامًا عمليًا للرد على العملاء
  وتنظيم المحادثات، مع ردود جاهزة،
  وتصنيف العملاء وسيناريوهات متابعة.

- AI تحليل وحل مشكلة النشاط:
  حلّل المشكلة بعمق،
  حدد الأسباب المحتملة،
  ثم قدم خطة تنفيذ واضحة خطوة بخطوة،
  مع مؤشرات يمكن استخدامها لقياس التحسن.

لا تدّعِ أنك دخلت إلى حسابات العميل
أو نفذت إجراءات خارج النص.

يجب أن تكون النتيجة عملية وجاهزة
ليتم تسليمها للعميل.

اكتب النتيجة باللغة العربية
وبأسلوب احترافي واضح.

قسّم النتيجة إلى عناوين ونقاط واضحة.
لا تكرر وصف المشكلة فقط.
ابدأ مباشرة بالحل والتنفيذ.
"""

    return prompt


# =========================================================
# إشعار AI بدأ العمل
# =========================================================

def notify_ai_started(
    order,
    lead
):

    name = lead.get(
        "name",
        "غير معروف"
    )

    message = f"""
🚀 بدأ الذكاء الاصطناعي العمل

🆔 الطلب:
{order["id"]}

👤 العميل:
{name}

🛠 الخدمة:
{order["service"]}

💵 السعر:
${order["price_usd"]}

🤖 المحرك:
Gemini

🟡 الحالة:
processing

الذكاء الاصطناعي يعمل الآن على تنفيذ الطلب.
"""

    return send_telegram(
        message
    )


# =========================================================
# إشعار اكتمال AI
# =========================================================

def notify_ai_completed(
    order,
    lead
):

    name = lead.get(
        "name",
        "غير معروف"
    )

    message = f"""
🎉 اكتمل تنفيذ الطلب

🆔 الطلب:
{order["id"]}

👤 العميل:
{name}

🛠 الخدمة:
{order["service"]}

💵 السعر:
${order["price_usd"]}

🤖 المحرك:
Gemini

🟢 الحالة:
completed

✅ نتيجة AI أصبحت جاهزة للتسليم للعميل.
"""

    return send_telegram(
        message
    )


# =========================================================
# إشعار فشل AI
# =========================================================

def notify_ai_failed(
    order,
    error
):

    message = f"""
❌ تعذر تنفيذ طلب AI

🆔 الطلب:
{order["id"]}

🛠 الخدمة:
{order["service"]}

🤖 المحرك:
Gemini

⚠️ السبب:
{error}

الحالة:
ai_failed

يمكن إعادة المحاولة من النظام لاحقًا.
"""

    return send_telegram(
        message
    )


# =========================================================
# تنفيذ AI في الخلفية
# =========================================================

def execute_ai_order(
    order_id
):

    print(
        "AI worker started:",
        order_id
    )

    data = db()

    order = find_order(
        data,
        order_id
    )

    if not order:

        print(
            "AI worker: order not found"
        )

        return

    # حماية من التنفيذ المكرر
    if order.get(
        "status"
    ) == "completed":

        print(
            "AI worker: already completed"
        )

        return

    if order.get(
        "status"
    ) != "processing":

        print(
            "AI worker: invalid status:",
            order.get("status")
        )

        return

    lead = find_lead(
        data,
        order.get(
            "lead_id"
        )
    )

    if not lead:

        order["status"] = (
            "ai_failed"
        )

        order["ai_error"] = (
            "العميل غير موجود."
        )

        save(data)

        notify_ai_failed(
            order,
            "العميل غير موجود."
        )

        return

    prompt = build_ai_prompt(
        order,
        lead
    )

    ok, result = gemini_request(
        prompt
    )

    # إعادة قراءة البيانات
    # حتى لا نكتب فوق تغييرات حديثة
    data = db()

    order = find_order(
        data,
        order_id
    )

    if not order:

        return

    if not ok:

        order["status"] = (
            "ai_failed"
        )

        order["ai_error"] = (
            result
        )

        order["ai_failed_at"] = (
            time.time()
        )

        save(data)

        notify_ai_failed(
            order,
            result
        )

        return

    # حفظ النتيجة
    order["result"] = result

    order["status"] = (
        "completed"
    )

    order["completed_at"] = (
        time.time()
    )

    order["ai_model"] = (
        GEMINI_MODEL
    )

    order["ai_provider"] = (
        "gemini"
    )

    save(data)

    notify_ai_completed(
        order,
        lead
    )

    print(
        "AI worker completed:",
        order_id
    )


# =========================================================
# تشغيل AI بعد تأكيد الدفع
# =========================================================

def start_ai_for_order(
    order_id
):

    data = db()

    order = find_order(
        data,
        order_id
    )

    if not order:

        return False

    # حماية قوية من التكرار
    if order.get(
        "status"
    ) in [
        "processing",
        "completed"
    ]:

        return False

    if order.get(
        "status"
    ) != "payment_submitted":

        return False

    order["status"] = (
        "processing"
    )

    order["ai_started_at"] = (
        time.time()
    )

    save(data)

    lead = find_lead(
        data,
        order.get(
            "lead_id"
        )
    )

    if lead:

        notify_ai_started(
            order,
            lead
        )

    # تشغيل العامل في الخلفية
    thread = threading.Thread(
        target=execute_ai_order,
        args=(order_id,),
        daemon=True
    )

    thread.start()

    return True


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

    qr_path = Path(
        QR_FILE
    )

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
# الخدمات
# =========================================================

@app.get("/api/services")
def services():

    data = db()

    return jsonify(
        data["services"]
    )


# =========================================================
# إنشاء Lead
# =========================================================

@app.post("/api/lead")
def lead():

    data = db()

    body = request.json or {}

    name = str(
        body.get(
            "name",
            ""
        )
    ).strip()

    contact = str(
        body.get(
            "contact",
            ""
        )
    ).strip()

    problem = str(
        body.get(
            "problem",
            ""
        )
    ).strip()

    link = str(
        body.get(
            "link",
            ""
        )
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

    # منع التكرار لمدة 10 دقائق
    for old in data["leads"]:

        if (

            old.get("name") == name

            and

            old.get("contact") == contact

            and

            old.get("problem") == problem

            and

            now - old.get(
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

        "id":
            lead_id,

        "name":
            name,

        "contact":
            contact,

        "problem":
            problem,

        "link":
            link,

        "status":
            "new",

        "created_at":
            now

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
# إنشاء Order
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

    # منع الطلب نفسه مرتين
    for old in data["orders"]:

        if (

            old.get(
                "lead_id"
            ) == lead_id

            and

            old.get(
                "service"
            ) == service

            and

            old.get(
                "status"
            ) in active_statuses

        ):

            return jsonify(
                {
                    "ok": True,

                    "id":
                        old["id"],

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

        "id":
            order_id,

        "lead_id":
            lead_id,

        "service":
            service,

        "price":
            price,

        "price_usd":
            price,

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

            "id":
                order_id,

            "lead_id":
                lead_id,

            "service":
                service,

            "price":
                price,

            "price_usd":
                price,

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

    # إذا تم إرسال الدفع سابقًا
    if order.get(
        "status"
    ) in [

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

    telegram_sent = send_telegram(

        f"""
🔔 طلب دفع جديد

🆔 رقم الطلب:
{order["id"]}

🛠 الخدمة:
{order["service"]}

💵 السعر:
${order["price_usd"]}

👤 العميل:
{client.get("name", "غير معروف") if client else "غير معروف"}

📞 التواصل:
{client.get("contact", "غير معروف") if client else "غير معروف"}

📝 المشكلة:
{client.get("problem", "غير معروف") if client else "غير معروف"}

⚠️ العميل ضغط "دفعت".

تحقق يدويًا من وصول المبلغ في شام كاش.

بعد التأكد اضغط:
✅ تأكيد استلام الدفع
""",

        payment_confirmation_keyboard(
            order["id"]
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

    # إذا كان AI يعمل بالفعل
    if order.get(
        "status"
    ) == "processing":

        return jsonify(
            {
                "ok": True,
                "order":
                    order
            }
        )

    # إذا اكتمل
    if order.get(
        "status"
    ) == "completed":

        return jsonify(
            {
                "ok": True,
                "order":
                    order
            }
        )

    # إذا أكد سابقًا
    if order.get(
        "status"
    ) == "ready_for_ai":

        return jsonify(
            {
                "ok": True,

                "already_verified":
                    True,

                "order":
                    order
            }
        )

    # يجب أن يكون العميل قد ضغط دفعت
    if order.get(
        "status"
    ) != "payment_submitted":

        return jsonify(
            {
                "ok": False,

                "error":
                    "لا يمكن تأكيد الدفع في الحالة الحالية.",

                "order":
                    order
            }
        ), 400

    # تأكيد الدفع + تشغيل AI
    order["status"] = (
        "processing"
    )

    order["payment_verified_at"] = (
        time.time()
    )

    order["payment_verified_source"] = (
        "admin"
    )

    order["ai_started_at"] = (
        time.time()
    )

    save(data)

    lead = find_lead(
        data,
        order["lead_id"]
    )

    if lead:

        notify_ai_started(
            order,
            lead
        )

    thread = threading.Thread(
        target=execute_ai_order,
        args=(order["id"],),
        daemon=True
    )

    thread.start()

    return jsonify(
        {
            "ok": True,

            "ai_started":
                True,

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

    # Telegram يرسل أنواعًا أخرى من التحديثات
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

    if not callback_data.startswith(
        "confirm_payment:"
    ):

        answer_callback(
            callback_id,
            "هذا الزر غير معروف."
        )

        return jsonify(
            {
                "ok": True
            }
        )

    # رقم الطلب
    order_id = callback_data[
        len("confirm_payment:"):
    ]

    answer_callback(
        callback_id,
        "جارٍ تأكيد الدفع وبدء AI..."
    )

    data = db()

    order = find_order(
        data,
        order_id
    )

    if not order:

        send_telegram(
            f"""
❌ تعذر تأكيد الدفع

الطلب غير موجود:

{order_id}
"""
        )

        return jsonify(
            {
                "ok": True
            }
        )

    # منع الضغط مرتين
    if order.get(
        "status"
    ) in [

        "processing",

        "completed"

    ]:

        remove_telegram_button(
            callback
        )

        send_telegram(
            f"""
ℹ️ هذا الطلب تمت معالجته مسبقًا

🆔 {order["id"]}

الحالة الحالية:
{order["status"]}
"""
        )

        return jsonify(
            {
                "ok": True
            }
        )

    # لا يمكن التأكيد قبل ضغط العميل دفعت
    if order.get(
        "status"
    ) != "payment_submitted":

        send_telegram(
            f"""
⚠️ لا يمكن تأكيد الطلب الآن

🆔 {order["id"]}

الحالة:
{order.get("status")}

يجب أن يضغط العميل أولًا:
"دفعت — أرسل للمراجعة"
"""
        )

        return jsonify(
            {
                "ok": True
            }
        )

    # =====================================================
    # تأكيد الدفع + بدء AI
    # =====================================================

    order["status"] = (
        "processing"
    )

    order["payment_verified_at"] = (
        time.time()
    )

    order["payment_verified_source"] = (
        "telegram_button"
    )

    order["ai_started_at"] = (
        time.time()
    )

    save(data)

    # إزالة زر التأكيد
    remove_telegram_button(
        callback
    )

    lead = find_lead(
        data,
        order["lead_id"]
    )

    send_telegram(
        f"""
🚀 بدأ AI العمل الآن

🆔 رقم الطلب:
{order["id"]}

🛠 الخدمة:
{order["service"]}

👤 العميل:
{lead.get("name", "غير معروف") if lead else "غير معروف"}

💵 السعر:
${order["price_usd"]}

🤖 المحرك:
Gemini

🟢 الحالة:
processing

🤖 تم تأكيد الدفع وبدأ تنفيذ الطلب فعليًا.
"""
    )

    # تشغيل AI بالخلفية
    thread = threading.Thread(
        target=execute_ai_order,
        args=(order["id"],),
        daemon=True
    )

    thread.start()

    return jsonify(
        {
            "ok": True
        }
    )


# =========================================================
# حالة الطلب
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
                    ),

                "ai_provider":
                    order.get(
                        "ai_provider"
                    ),

                "ai_model":
                    order.get(
                        "ai_model"
                    ),

                "ai_error":
                    order.get(
                        "ai_error"
                    ),

                "ai_started_at":
                    order.get(
                        "ai_started_at"
                    ),

                "completed_at":
                    order.get(
                        "completed_at"
                    )

            }

        }
    )


# =========================================================
# API الإدارة
# =========================================================

@app.get("/api/admin")
def admin_api():

    return jsonify(
        db()
    )


# =========================================================
# صحة النظام
# =========================================================

@app.get("/health")
def health():

    return jsonify(
        {
            "ok":
                True,

            "service":
                "AI يحلها سوريا",

            "telegram":
                bool(
                    os.getenv(
                        "TELEGRAM_BOT_TOKEN"
                    )
                ),

            "telegram_chat":
                bool(
                    os.getenv(
                        "TELEGRAM_CHAT_ID"
                    )
                ),

            "openai":
                bool(
                    os.getenv(
                        "OPENAI_API_KEY"
                    )
                ),

            "gemini":
                bool(
                    os.getenv(
                        "GEMINI_API_KEY"
                    )
                ),

            "gemini_model":
                GEMINI_MODEL,

            "qr":
                Path(
                    QR_FILE
                ).exists()
        }
    )


# =========================================================
# إعداد Telegram عند تحميل التطبيق
# =========================================================

try:

    setup_telegram_webhook()

except Exception as e:

    print(
        "Webhook startup error:",
        e
    )


# =========================================================
# التشغيل المحلي
# =========================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
