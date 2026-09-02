from flask import Flask, request, jsonify, send_from_directory
import json
import time
import os
import urllib.request
import urllib.parse
import threading
import secrets
from pathlib import Path


app = Flask(__name__)


# =========================================================
# إعدادات المشروع
# =========================================================

DB = Path("data.json")

QR_FILE = "IMG-20260829-WA0010.jpg"

OPENAI_MODEL = os.getenv(
    "OPENAI_MODEL",
    "gpt-5.6-luna"
)

DEFAULT_SERVICES = {
    "AI محتوى للمطاعم": 15,
    "AI محتوى المنتجات": 15,
    "AI تنظيم العملاء والردود": 20,
    "AI تحليل وحل مشكلة النشاط": 10
}


# =========================================================
# قاعدة البيانات
# =========================================================

def create_database_if_needed():

    if not DB.exists():

        DB.write_text(
            json.dumps(
                {
                    "leads": [],
                    "orders": [],
                    "services": DEFAULT_SERVICES.copy()
                },
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )


create_database_if_needed()


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

    temporary_file = Path(
        str(DB) + ".tmp"
    )

    temporary_file.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    temporary_file.replace(DB)


# =========================================================
# أدوات البحث
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
# Telegram
# =========================================================

def telegram_request(
    method,
    payload
):

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


    ok, _ = telegram_request(
        "sendMessage",
        payload
    )

    return ok


def answer_callback(
    callback_id
):

    if not callback_id:
        return

    telegram_request(
        "answerCallbackQuery",
        {
            "callback_query_id":
                callback_id,
            "text":
                "تم استلام التأكيد ✅"
        }
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
# إرسال إشعار الدفع إلى Telegram
# =========================================================

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

تحقق يدويًا من وصول المبلغ في شام كاش.

بعد التأكد اضغط:
✅ تأكيد استلام الدفع
"""


    return send_telegram(
        message,
        payment_confirmation_keyboard(
            order["id"]
        )
    )


# =========================================================
# OpenAI
# =========================================================

def call_openai(
    service,
    client,
    order
):

    api_key = os.getenv(
        "OPENAI_API_KEY"
    )

    if not api_key:

        raise RuntimeError(
            "OPENAI_API_KEY غير موجود في Render"
        )


    client_name = client.get(
        "name",
        ""
    )

    client_contact = client.get(
        "contact",
        ""
    )

    client_link = client.get(
        "link",
        ""
    )

    client_problem = client.get(
        "problem",
        ""
    )


    prompt = f"""
أنت الذكاء الاصطناعي التنفيذي في شركة
"AI يحلها سوريا".

لديك طلب مدفوع من عميل حقيقي.

رقم الطلب:
{order["id"]}

اسم العميل / النشاط:
{client_name}

وسيلة التواصل:
{client_contact}

رابط النشاط:
{client_link}

الخدمة المطلوبة:
{service}

المشكلة التي وصفها العميل:
{client_problem}

مهمتك:
حل المشكلة بشكل عملي ومفيد وقابل للتطبيق.

لا تكتفِ بنصائح عامة.

قم بتحليل المشكلة ثم قدم نتيجة عملية يستطيع العميل استخدامها مباشرة.

إذا كانت الخدمة محتوى:
أنشئ المحتوى المطلوب بشكل جاهز للاستخدام.

إذا كانت الخدمة تحليل مشكلة:
قدم تشخيصًا واضحًا وخطة تنفيذ عملية.

إذا كانت الخدمة تنظيم العملاء والردود:
أنشئ نظامًا واضحًا للردود والتنظيم.

إذا كانت الخدمة تخص المنتجات:
أنشئ محتوى تسويقيًا مناسبًا للمنتج.

اكتب النتيجة باللغة العربية.

لا تقل إنك ستقوم بالعمل لاحقًا.
نفذ المهمة الآن.

في نهاية الإجابة ضع قسمًا بعنوان:
"النتيجة الجاهزة للعميل"
"""


    payload = {

        "model": OPENAI_MODEL,

        "input": prompt

    }


    body = json.dumps(
        payload,
        ensure_ascii=False
    ).encode("utf-8")


    req = urllib.request.Request(

        "https://api.openai.com/v1/responses",

        data=body,

        method="POST",

        headers={
            "Content-Type":
                "application/json",

            "Authorization":
                f"Bearer {api_key}"
        }

    )


    with urllib.request.urlopen(
        req,
        timeout=180
    ) as response:

        raw = response.read().decode(
            "utf-8"
        )


    result = json.loads(raw)


    # Responses API يعيد النص في output_text
    text = result.get(
        "output_text"
    )


    if text:

        return text.strip()


    # احتياط في حال تغيّر شكل الاستجابة
    output = result.get(
        "output",
        []
    )


    parts = []


    for item in output:

        content = item.get(
            "content",
            []
        )


        for piece in content:

            if piece.get("type") in [
                "output_text",
                "text"
            ]:

                piece_text = piece.get(
                    "text",
                    ""
                )

                if piece_text:
                    parts.append(
                        piece_text
                    )


    text = "\n".join(
        parts
    ).strip()


    if not text:

        raise RuntimeError(
            "لم تصل نتيجة نصية من OpenAI"
        )


    return text


# =========================================================
# تنفيذ AI في الخلفية
# =========================================================

def run_ai_order(
    order_id
):

    print(
        "AI worker started:",
        order_id
    )


    # -----------------------------------------------------
    # نضع processing أولًا
    # -----------------------------------------------------

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


    # حماية من تشغيل نفس الطلب مرتين
    if order.get("status") in [
        "completed"
    ]:

        print(
            "AI worker: order already completed"
        )

        return


    if order.get("status") != "processing":

        print(
            "AI worker: invalid status:",
            order.get("status")
        )

        return


    lead = find_lead(
        data,
        order.get("lead_id")
    )


    if not lead:

        order["status"] = "failed"

        order["error"] = (
            "العميل المرتبط بالطلب غير موجود"
        )

        order["failed_at"] = time.time()

        save(data)

        send_telegram(
            f"""
❌ فشل تنفيذ AI

🆔 الطلب:
{order_id}

السبب:
العميل المرتبط بالطلب غير موجود.
"""
        )

        return


    # -----------------------------------------------------
    # إخبار المالك
    # -----------------------------------------------------

    send_telegram(
        f"""
🚀 بدأ AI العمل الآن

🆔 رقم الطلب:
{order_id}

🛠 الخدمة:
{order["service"]}

🤖 الحالة:
processing

سيتم إرسال إشعار عند انتهاء التنفيذ.
"""
    )


    try:

        # -------------------------------------------------
        # تنفيذ AI الحقيقي
        # -------------------------------------------------

        result_text = call_openai(
            order["service"],
            lead,
            order
        )


        # -------------------------------------------------
        # حفظ النتيجة
        # -------------------------------------------------

        data = db()

        order = find_order(
            data,
            order_id
        )


        if not order:

            return


        # حماية إضافية
        if order.get("status") == "completed":

            return


        order["result"] = result_text

        order["status"] = "completed"

        order["completed_at"] = time.time()

        order["ai_model"] = OPENAI_MODEL


        # رابط النتيجة سيُستخدم في index.html
        order["result_token"] = secrets.token_urlsafe(
            24
        )


        save(data)


        # -------------------------------------------------
        # إشعار النجاح
        # -------------------------------------------------

        send_telegram(
            f"""
🎉 اكتمل تنفيذ AI

🆔 رقم الطلب:
{order_id}

🛠 الخدمة:
{order["service"]}

✅ الحالة:
completed

🤖 تم إنشاء النتيجة بنجاح.

يمكن للعميل الآن استلام النتيجة من صفحة طلبه.
"""
        )


        print(
            "AI worker completed:",
            order_id
        )


    except Exception as e:

        print(
            "AI execution error:",
            e
        )


        data = db()

        order = find_order(
            data,
            order_id
        )


        if not order:

            return


        order["status"] = "failed"

        order["error"] = str(e)

        order["failed_at"] = time.time()


        save(data)


        send_telegram(
            f"""
❌ حدث خطأ أثناء تنفيذ AI

🆔 رقم الطلب:
{order_id}

الخدمة:
{order["service"]}

الحالة:
failed

الخطأ:
{str(e)[:500]}
"""
        )


# =========================================================
# تشغيل AI مرة واحدة فقط
# =========================================================

def start_ai_once(
    order_id
):

    data = db()

    order = find_order(
        data,
        order_id
    )


    if not order:

        return False


    # إذا بدأ أو انتهى بالفعل
    if order.get("status") in [

        "processing",

        "completed"

    ]:

        return False


    if order.get("status") != (
        "payment_submitted"
    ):

        return False


    order["status"] = "processing"

    order["processing_started_at"] = (
        time.time()
    )


    save(data)


    # تشغيل العامل في الخلفية
    worker = threading.Thread(

        target=run_ai_order,

        args=(order_id,),

        daemon=True

    )

    worker.start()


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
# لوحة الإدارة
# =========================================================

@app.get("/admin")
def admin():

    return send_from_directory(
        ".",
        "index.html"
    )


# =========================================================
# QR
# =========================================================

@app.get("/qr")
def qr():

    if not Path(QR_FILE).exists():

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
def create_lead():

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


    # منع التكرار خلال 10 دقائق
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
# إنشاء Order
# =========================================================

@app.post("/api/order")
def create_order():

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

        "processing",

        "completed"

    ]


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
                        old["status"],

                    "result":
                        old.get("result")

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
# العميل يقول دفعت
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


    if order.get("status") in [

        "payment_submitted",

        "processing",

        "completed"

    ]:

        return jsonify(
            {
                "ok": True,

                "already_submitted":
                    True,

                "order":
                    order
            }
        )


    if order.get("status") != (
        "awaiting_payment"
    ):

        return jsonify(
            {
                "ok": False,

                "error":
                    "لا يمكن إرسال هذا الطلب للمراجعة حاليًا",

                "order":
                    order
            }
        ), 400


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


    if order.get("status") in [

        "processing",

        "completed"

    ]:

        return jsonify(
            {
                "ok": True,
                "order":
                    order
            }
        )


    if order.get("status") != (
        "payment_submitted"
    ):

        return jsonify(
            {
                "ok": False,

                "error":
                    "الطلب ليس بانتظار تأكيد الدفع",

                "order":
                    order
            }
        ), 400


    # نفس العملية التي ينفذها زر Telegram
    started = start_ai_once(
        order_id
    )


    if not started:

        data = db()

        order = find_order(
            data,
            order_id
        )

        return jsonify(
            {
                "ok": True,
                "order":
                    order
            }
        )


    data = db()

    order = find_order(
        data,
        order_id
    )


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

        send_telegram(
            f"""
❌ تعذر العثور على الطلب

🆔 {order_id}
"""
        )

        return jsonify(
            {
                "ok": True
            }
        )


    # إذا بدأ AI بالفعل
    if order.get("status") == "processing":

        send_telegram(
            f"""
ℹ️ AI يعمل بالفعل

🆔 الطلب:
{order_id}

الحالة:
processing
"""
        )

        return jsonify(
            {
                "ok": True
            }
        )


    # إذا انتهى
    if order.get("status") == "completed":

        send_telegram(
            f"""
ℹ️ الطلب مكتمل بالفعل

🆔 الطلب:
{order_id}
"""
        )

        return jsonify(
            {
                "ok": True
            }
        )


    # الزر لا يعمل إلا بعد أن يقول العميل "دفعت"
    if order.get("status") != (
        "payment_submitted"
    ):

        send_telegram(
            f"""
⚠️ لا يمكن بدء AI لهذا الطلب الآن

🆔 {order_id}

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


    # -----------------------------------------------------
    # بدء AI الحقيقي
    # -----------------------------------------------------

    started = start_ai_once(
        order_id
    )


    if started:

        send_telegram(
            f"""
🚀 بدأ AI العمل

🆔 رقم الطلب:
{order_id}

🛠 الخدمة:
{order["service"]}

🟡 الحالة:
processing

🤖 الذكاء الاصطناعي يعمل الآن على حل مشكلة العميل.

سأرسل لك إشعارًا عند اكتمال النتيجة.
"""
        )

    else:

        data = db()

        order = find_order(
            data,
            order_id
        )

        send_telegram(
            f"""
ℹ️ لم يتم بدء الطلب

🆔 {order_id}

الحالة الحالية:
{order.get("status") if order else "غير معروف"}
"""
        )


    return jsonify(
        {
            "ok": True
        }
    )


# =========================================================
# حالة الطلب
# =========================================================

@app.get("/api/order/<order_id>")
def get_order_status(
    order_id
):

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
                    order.get("id"),

                "service":
                    order.get("service"),

                "price_usd":
                    order.get(
                        "price_usd"
                    ),

                "status":
                    order.get(
                        "status"
                    ),

                "result":
                    order.get(
                        "result"
                    ) if order.get(
                        "status"
                    ) == "completed"
                    else None,

                "created_at":
                    order.get(
                        "created_at"
                    ),

                "processing_started_at":
                    order.get(
                        "processing_started_at"
                    ),

                "completed_at":
                    order.get(
                        "completed_at"
                    )

            }
        }
    )


# =========================================================
# صفحة النتيجة
# =========================================================

@app.get("/result/<order_id>")
def result_page(
    order_id
):

    data = db()

    order = find_order(
        data,
        order_id
    )


    if not order:

        return """
        <!doctype html>
        <html lang="ar" dir="rtl">
        <head>
        <meta charset="utf-8">
        <meta name="viewport"
        content="width=device-width,initial-scale=1">
        <title>الطلب غير موجود</title>
        </head>
        <body style="font-family:Arial;padding:30px">
        <h2>❌ الطلب غير موجود</h2>
        </body>
        </html>
        """, 404


    status = order.get(
        "status"
    )


    if status != "completed":

        return f"""
        <!doctype html>
        <html lang="ar" dir="rtl">
        <head>
        <meta charset="utf-8">
        <meta name="viewport"
        content="width=device-width,initial-scale=1">
        <title>حالة الطلب</title>

        <style>
        body {{
            font-family:Arial;
            background:#f5f7fb;
            padding:20px;
        }}

        .box {{
            max-width:700px;
            margin:auto;
            background:white;
            padding:25px;
            border-radius:15px;
        }}

        .status {{
            padding:18px;
            border-radius:10px;
            background:#fff4ce;
        }}
        </style>

        </head>

        <body>

        <div class="box">

        <h1>🤖 AI يحلها سوريا</h1>

        <h2>طلبك قيد التنفيذ</h2>

        <p>
        🆔 رقم الطلب:
        <b>{order_id}</b>
        </p>

        <div class="status">

        🟡
        {"جاري تنفيذ طلبك بواسطة الذكاء الاصطناعي." 
        if status == "processing"
        else
        "بانتظار تأكيد الدفع."}

        </div>

        <p>
        يمكنك إبقاء هذه الصفحة مفتوحة،
        وسيتم تحديث حالة الطلب تلقائيًا في النسخة القادمة من الواجهة.
        </p>

        </div>

        </body>
        </html>
        """


    result = order.get(
        "result",
        ""
    )


    # حماية HTML
    safe_result = (
        result
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


    return f"""
    <!doctype html>

    <html lang="ar" dir="rtl">

    <head>

    <meta charset="utf-8">

    <meta name="viewport"
    content="width=device-width,initial-scale=1">

    <title>نتيجة الطلب</title>

    <style>

    body {{
        font-family:Arial;
        background:#f5f7fb;
        padding:20px;
    }}

    .box {{
        max-width:800px;
        margin:auto;
        background:white;
        padding:25px;
        border-radius:15px;
    }}

    .success {{
        background:#e8f7ee;
        padding:15px;
        border-radius:10px;
    }}

    .result {{
        margin-top:20px;
        padding:20px;
        background:#f8fafc;
        border-radius:10px;
        white-space:pre-wrap;
        line-height:1.8;
    }}

    </style>

    </head>

    <body>

    <div class="box">

    <h1>🤖 AI يحلها سوريا</h1>

    <div class="success">

    🎉 تم إنجاز طلبك بنجاح.

    </div>

    <p>
    🆔 رقم الطلب:
    <b>{order_id}</b>
    </p>

    <p>
    🛠 الخدمة:
    <b>{order["service"]}</b>
    </p>

    <h2>📄 النتيجة</h2>

    <div class="result">
    {safe_result}
    </div>

    </div>

    </body>

    </html>
    """


# =========================================================
# API الإدارة
# =========================================================

@app.get("/api/admin")
def admin_api():

    return jsonify(
        db()
    )


# =========================================================
# فحص صحة النظام
# =========================================================

@app.get("/health")
def health():

    return jsonify(
        {
            "ok": True,

            "service":
                "AI يحلها سوريا",

            "qr":
                Path(
                    QR_FILE
                ).exists(),

            "telegram":
                bool(
                    os.getenv(
                        "TELEGRAM_BOT_TOKEN"
                    )
                ),

            "openai":
                bool(
                    os.getenv(
                        "OPENAI_API_KEY"
                    )
                ),

            "model":
                OPENAI_MODEL
        }
    )


# =========================================================
# Telegram Webhook
# =========================================================

def setup_telegram_webhook():

    token = os.getenv(
        "TELEGRAM_BOT_TOKEN"
    )

    if not token:

        print(
            "Webhook: Telegram token missing"
        )

        return


    app_url = os.getenv(
        "RENDER_EXTERNAL_URL"
    )


    if not app_url:

        app_url = os.getenv(
            "APP_URL"
        )


    if not app_url:

        print(
            "Webhook: APP_URL missing"
        )

        return


    app_url = app_url.rstrip("/")


    webhook_url = (
        app_url +
        "/telegram/webhook"
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
# التشغيل
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
