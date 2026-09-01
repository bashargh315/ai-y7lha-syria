from flask import Flask, request, jsonify, send_from_directory
import json
import time
import os
import urllib.request
import urllib.parse
from pathlib import Path

app = Flask(__name__)

DB = Path("data.json")
QR_FILE = "IMG-20260829-WA0010.jpg"

DEFAULT_SERVICES = {
    "AI محتوى للمطاعم": 15,
    "AI محتوى المنتجات": 15,
    "AI تنظيم العملاء والردود": 20,
    "AI تحليل وحل مشكلة النشاط": 10
}


# =========================
# قاعدة البيانات
# =========================

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
    data = json.loads(DB.read_text(encoding="utf-8"))

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


# =========================
# Telegram
# =========================

def send_telegram(message):

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("Telegram environment variables are missing")
        return False

    try:

        url = f"https://api.telegram.org/bot{token}/sendMessage"

        data = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": message
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=data,
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=15) as response:

            return response.status == 200

    except Exception as e:

        print("Telegram error:", e)

        return False


# =========================
# الصفحة الرئيسية
# =========================

@app.get("/")
def home():

    return send_from_directory(
        ".",
        "index.html"
    )


# =========================
# صفحة الإدارة
# =========================

@app.get("/admin")
def admin():

    return send_from_directory(
        ".",
        "index.html"
    )


# =========================
# QR شام كاش
# =========================

@app.get("/qr")
def qr():

    if not Path(QR_FILE).exists():

        return jsonify({
            "ok": False,
            "error": "QR image not found"
        }), 404

    return send_from_directory(
        ".",
        QR_FILE
    )


# =========================
# الخدمات والأسعار
# =========================

@app.get("/api/services")
def services():

    data = db()

    return jsonify(
        data["services"]
    )


# =========================
# إنشاء عميل
# =========================

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

        return jsonify({
            "ok": False,
            "error": "الاسم ووسيلة التواصل ووصف المشكلة مطلوبة"
        }), 400

    now = time.time()

    # منع إنشاء نفس العميل/المشكلة
    # عدة مرات خلال 10 دقائق

    for old in data["leads"]:

        if (
            old.get("name") == name
            and old.get("contact") == contact
            and old.get("problem") == problem
            and now - old.get("created_at", 0) < 600
        ):

            return jsonify(old)

    lead_id = "L" + str(
        int(time.time() * 1000)
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
        new_lead
    )


# =========================
# إنشاء طلب
# =========================

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

        return jsonify({
            "ok": False,
            "error": "بيانات الطلب ناقصة"
        }), 400

    if service not in data["services"]:

        return jsonify({
            "ok": False,
            "error": "الخدمة غير موجودة"
        }), 400

    # منع تكرار الطلب

    active_statuses = [
        "awaiting_payment",
        "payment_submitted",
        "payment_verified_manual",
        "processing",
        "completed"
    ]

    for old in data["orders"]:

        if (
            old.get("lead_id") == lead_id
            and old.get("service") == service
            and old.get("status") in active_statuses
        ):

            return jsonify({
                "ok": True,
                "id": old["id"],
                "lead_id": old["lead_id"],
                "service": old["service"],
                "price": old["price"],
                "price_usd": old["price"],
                "status": old["status"]
            })

    order_id = "ORD" + str(
        int(time.time() * 1000)
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
        "status": "awaiting_payment",
        "created_at": time.time()
    }

    data["orders"].append(
        new_order
    )

    save(data)

    return jsonify({
        "ok": True,
        "id": order_id,
        "lead_id": lead_id,
        "service": service,
        "price": price,
        "price_usd": price,
        "status": "awaiting_payment"
    })


# =========================
# العميل يقول: دفعت
# =========================

@app.post("/api/paid")
def paid():

    data = db()
    body = request.json or {}

    order_id = body.get(
        "order_id"
    )

    if not order_id:

        return jsonify({
            "ok": False,
            "error": "رقم الطلب مفقود"
        }), 400

    for order in data["orders"]:

        if order["id"] != order_id:
            continue

        # منع إرسال الإشعار مرتين

        if order["status"] == "payment_submitted":

            return jsonify({
                "ok": True,
                "already_submitted": True,
                "order": order
            })

        if order["status"] in [
            "payment_verified_manual",
            "processing",
            "completed"
        ]:

            return jsonify({
                "ok": True,
                "already_submitted": True,
                "order": order
            })

        order["status"] = "payment_submitted"

        order["payment_submitted_at"] = time.time()

        client = None

        for lead in data["leads"]:

            if lead["id"] == order["lead_id"]:

                client = lead

                break

        if client:

            client_name = client["name"]
            client_contact = client["contact"]
            client_problem = client["problem"]

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

يرجى التحقق يدويًا من وصول المبلغ في شام كاش قبل تأكيد الطلب.
"""

        telegram_sent = send_telegram(
            message
        )

        save(data)

        return jsonify({
            "ok": True,
            "already_submitted": False,
            "telegram_sent": telegram_sent,
            "order": order
        })

    return jsonify({
        "ok": False,
        "error": "الطلب غير موجود"
    }), 404


# =========================
# تأكيد الدفع يدويًا
# =========================

@app.post("/api/verify")
def verify():

    data = db()
    body = request.json or {}

    order_id = body.get(
        "order_id"
    )

    if not order_id:

        return jsonify({
            "ok": False,
            "error": "رقم الطلب مفقود"
        }), 400

    for order in data["orders"]:

        if order["id"] != order_id:
            continue

        if order["status"] == "completed":

            return jsonify({
                "ok": True,
                "order": order
            })

        if order["status"] == "processing":

            return jsonify({
                "ok": True,
                "order": order
            })

        order["status"] = "payment_verified_manual"

        order["payment_verified_at"] = time.time()

        save(data)

        return jsonify({
            "ok": True,
            "order": order
        })

    return jsonify({
        "ok": False,
        "error": "الطلب غير موجود"
    }), 404


# =========================
# بيانات الإدارة
# =========================

@app.get("/api/admin")
def admin_api():

    return jsonify(
        db()
    )


# =========================
# تشغيل التطبيق
# =========================

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
