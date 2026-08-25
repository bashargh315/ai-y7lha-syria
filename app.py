from flask import Flask, request, jsonify, send_from_directory
import json, time
from pathlib import Path
app=Flask(__name__)
DB=Path("data.json")
if not DB.exists(): DB.write_text(json.dumps({"leads":[],"orders":[]},ensure_ascii=False),encoding="utf-8")
def db(): return json.loads(DB.read_text(encoding="utf-8"))
def save(x): DB.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding="utf-8")
@app.get("/")
def home(): return send_from_directory(".", "index.html")
@app.get("/admin")
def admin(): return send_from_directory(".", "index.html")
@app.post("/api/lead")
def lead():
 x=db(); b=request.json or {}; q={"id":"L"+str(int(time.time()*1000)),"name":b.get("name",""),"contact":b.get("contact",""),"problem":b.get("problem",""),"link":b.get("link",""),"status":"new"}; x["leads"].append(q); save(x); return jsonify(q)
@app.post("/api/order")
def order():
 x=db(); b=request.json or {}; q={"id":"ORD"+str(int(time.time()*1000)),"lead_id":b.get("lead_id"),"service":b.get("service"),"price":int(b.get("price",0)),"status":"awaiting_payment"}; x["orders"].append(q); save(x); return jsonify(q)
@app.post("/api/verify")
def verify():
 x=db(); oid=(request.json or {}).get("order_id")
 for q in x["orders"]:
  if q["id"]==oid: q["status"]="payment_verified_manual"; save(x); return jsonify(ok=True)
 return jsonify(ok=False),404
@app.get("/api/admin")
def admin_api(): return jsonify(db())
if __name__=="__main__": app.run(host="127.0.0.1",port=5000,debug=True)
