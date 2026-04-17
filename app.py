import os
from flask import Flask, render_template, request, redirect, Response, session, url_for
import requests
from datetime import datetime
import jpholiday

app = Flask(__name__)
app.secret_key = "yashoya_secret_key_fixed" # セッション用の秘密鍵

FIREBASE_URL = os.environ.get("FIREBASE_URL", "https://izakaya-reserve-default-rtdb.firebaseio.com")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "1234")

def is_sunday_or_holiday(date_obj):
    return date_obj.weekday() == 6 or jpholiday.is_holiday(date_obj)

def build_time_options(date_str):
    if not date_str:
        end_hour = 25
    else:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        end_hour = 23 if is_sunday_or_holiday(date_obj) else 25

    options = []
    for hour in range(17, end_hour + 1):
        for minute in [0, 15, 30, 45]:
            if hour == end_hour and minute != 0:
                continue
            options.append(f"{hour:02d}:{minute:02d}")
    return options

def get_all_reservations():
    try:
        res = requests.get(FIREBASE_URL + "/reservations.json")
        data = res.json()
    except:
        data = {}

    reservations = []
    if data:
        for key, value in data.items():
            if value:
                value["id"] = key
                reservations.append(value)
    return reservations

def send_notification(message):
    print("="*40)
    print("🔔 [通知] \n" + message)
    print("="*40)

def assign_seat(date, time, people):
    people = int(people)
    if people >= 7:
        return "保留", "pending"
    reservations = get_all_reservations()
    confirmed = [r for r in reservations if r.get("date") == date and r.get("time") == time and r.get("status") == "確定"]
    counter_used = sum(int(r["people"]) for r in confirmed if r.get("seat_type") == "counter")
    table4_used = sum(1 for r in confirmed if r.get("seat_type") == "table4")
    zashiki4_used = sum(1 for r in confirmed if r.get("seat_type") == "zashiki4")
    zashiki6_used = sum(1 for r in confirmed if r.get("seat_type") == "zashiki6")
    if 1 <= people <= 2:
        if counter_used + people <= 10: return "確定", "counter"
    elif 3 <= people <= 4:
        if table4_used < 4: return "確定", "table4"
        elif zashiki4_used < 3: return "確定", "zashiki4"
    elif 5 <= people <= 6:
        if zashiki6_used < 1: return "確定", "zashiki6"
    return "保留", "pending"

def get_fallback_seat(people):
    people = int(people)
    if 1 <= people <= 2: return "counter"
    elif 3 <= people <= 4: return "table4"
    elif 5 <= people <= 6: return "zashiki6"
    return "pending"

@app.route("/", methods=["GET", "POST"])
def index():
    now = datetime.now()
    year = now.year
    month = now.month
    today_str = now.strftime("%Y-%m-%d")
    
    holidays = jpholiday.month_holidays(year, month)
    holiday_days = [h[0].day for h in holidays]
    
    selected_date = request.form.get("date", "")
    time_options = build_time_options(selected_date)
    error_msg = None

    if request.method == "POST" and "name" in request.form:
        name = request.form.get("name")
        phone = request.form.get("phone")
        people = request.form.get("people")
        date = request.form.get("date")
        time = request.form.get("time")
        course = request.form.get("course")

        if date < today_str:
            return redirect("/")

        status, seat_type = assign_seat(date, time, people)
        data = {"name": name, "phone": phone, "people": people, "date": date, "time": time, "course": course, "status": status, "seat_type": seat_type}
        requests.post(FIREBASE_URL + "/reservations.json", json=data)
        send_notification(f"【新規予約】{name}様 {people}名 ({date} {time})")
        return render_template("complete.html", data=data)

    return render_template("index.html", today_str=today_str, selected_date=selected_date, time_options=time_options, error_msg=error_msg, year=year, month=month, holiday_days=holiday_days)

@app.route("/menu")
def menu():
    menu_items = [
        {"name": "職人手打ち 焼き鳥盛り合わせ", "price": "880円", "image": "menu_yakitori.png", "desc": "一本一本丁寧に手打ちし、炭火で香ばしく焼き上げた自慢の串です。"},
        {"name": "本日入荷！鮮魚の五種盛り", "price": "1,280円", "image": "menu_sashimi.png", "desc": "市場から直送された新鮮な旬の魚を贅沢に盛り合わせました。"},
        {"name": "秘伝のタレ漬け 唐揚げ", "price": "650円", "image": "menu_karaage.png", "desc": "外はカリッと、中はジュワッと肉汁溢れる当店一番人気の揚げ物です。"},
        {"name": "キンキンに冷えた 生ビール", "price": "550円", "image": "menu_beer.png", "desc": "仕事帰りの一杯に最高！徹底した品質管理で最高の喉越しをお届けします。"}
    ]
    return render_template("menu.html", menu_items=menu_items)

@app.route("/check", methods=["GET", "POST"])
def check():
    reservations = []
    today_str = datetime.now().strftime("%Y-%m-%d")
    if request.method == "POST":
        name = request.form.get("name")
        phone = request.form.get("phone")
        data = get_all_reservations()
        for r in data:
            if r["name"] == name and r["phone"] == phone: reservations.append(r)
    return render_template("check.html", reservations=reservations, today_str=today_str)

@app.route("/cancel/<id>", methods=["POST"])
def cancel(id):
    today_str = datetime.now().strftime("%Y-%m-%d")
    data = requests.get(FIREBASE_URL + f"/reservations/{id}.json").json()
    if data and data.get("date", "") > today_str:
        requests.delete(FIREBASE_URL + f"/reservations/{id}.json")
    return redirect("/check")

@app.route("/admin")
def admin():
    auth = request.authorization
    if not auth or auth.username != ADMIN_USERNAME or auth.password != ADMIN_PASSWORD:
        return Response("認証が必要", 401, {"WWW-Authenticate": 'Basic realm="Login"'})
    reservations = get_all_reservations()
    reservations.sort(key=lambda x: (x.get("date", ""), x.get("time", "")))
    return render_template("admin.html", reservations=reservations)

@app.route("/approve/<id>", methods=["POST"])
def approve(id):
    data = requests.get(FIREBASE_URL + f"/reservations/{id}.json").json()
    _, seat_type = assign_seat(data["date"], data["time"], data["people"])
    data["status"] = "確定"
    data["seat_type"] = seat_type if seat_type != "pending" else get_fallback_seat(data["people"])
    requests.put(FIREBASE_URL + f"/reservations/{id}.json", json=data)
    return redirect("/admin")

@app.route("/reject/<id>", methods=["POST"])
def reject(id):
    data = requests.get(FIREBASE_URL + f"/reservations/{id}.json").json()
    data["status"] = "却下"
    requests.put(FIREBASE_URL + f"/reservations/{id}.json", json=data)
    return redirect("/admin")

@app.route("/delete/<id>", methods=["POST"])
def delete(id):
    requests.delete(FIREBASE_URL + f"/reservations/{id}.json")
    return redirect("/admin")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
