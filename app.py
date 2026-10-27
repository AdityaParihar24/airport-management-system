import os
from functools import wraps
from flask import Flask, request, redirect, session, render_template_string, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "local-development-key-change-me")

url = os.environ.get("DATABASE_URL", "sqlite:///airport.db")
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)


class Flight(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(20), unique=True, nullable=False)
    airline = db.Column(db.String(100), nullable=False)
    destination = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="Scheduled")


class Gate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), unique=True, nullable=False)
    status = db.Column(db.String(30), nullable=False, default="Available")


class Passenger(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    flight = db.Column(db.String(20), nullable=False)


with app.app_context():
    db.create_all()
    username = os.environ.get("ADMIN_USERNAME", "admin")
    password = os.environ.get("ADMIN_PASSWORD", "")
    if password and not Admin.query.filter_by(username=username).first():
        db.session.add(Admin(
            username=username,
            password=generate_password_hash(password)
        ))
        db.session.commit()


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "admin" not in session:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


PAGE = """
<!doctype html>
<html lang="en">
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Airport Management System</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f1f5f9;font:15px Arial;color:#172033}
header{background:#10243b;color:white;padding:20px}
nav{background:#1d3552;padding:12px;display:flex;gap:8px;flex-wrap:wrap}
nav a{color:white;text-decoration:none;padding:10px;border-radius:5px}
nav a:hover{background:#355477}.wrap{max-width:1100px;margin:25px auto;padding:0 16px}
.card{background:white;border-radius:10px;padding:20px;margin-bottom:18px;box-shadow:0 2px 10px #0000000b}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px}
.stat{font-size:28px;font-weight:bold;color:#2563eb;margin-top:10px}
input,select{padding:11px;width:100%;margin:5px 0 12px;border:1px solid #cbd5e1;border-radius:6px}
button,.btn{background:#2563eb;color:white;border:0;border-radius:6px;padding:10px 14px;cursor:pointer;text-decoration:none;display:inline-block}
.danger{background:#dc2626}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:11px;border-bottom:1px solid #e2e8f0}
.table{overflow-x:auto}.msg{background:#dcfce7;padding:10px;margin-bottom:12px;border-radius:6px}
@media(max-width:600px){th,td{padding:7px;font-size:13px}}
</style>
</head>
<body>
<header><h2>✈ Airport Management System</h2>
<small>Airport administration dashboard</small></header>
{% if logged %}
<nav>
<a href="{{url_for('home')}}">Dashboard</a>
<a href="{{url_for('manage',kind='flights')}}">Flights</a>
<a href="{{url_for('manage',kind='gates')}}">Gates</a>
<a href="{{url_for('manage',kind='passengers')}}">Passengers</a>
<a href="{{url_for('logout')}}">Logout</a>
</nav>
{% endif %}
<div class="wrap">
{% for m in messages %}<div class="msg">{{m}}</div>{% endfor %}
{{content|safe}}
</div>
</body></html>
"""


def page(content, **kwargs):
    return render_template_string(
        PAGE, content=render_template_string(content, **kwargs),
        logged=("admin" in session),
        messages=session.pop("messages", [])
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = Admin.query.filter_by(
            username=request.form.get("username", "")
        ).first()
        if user and check_password_hash(
            user.password, request.form.get("password", "")
        ):
            session.clear()
            session["admin"] = user.id
            return redirect(url_for("home"))
        return page("""
        <div class="card"><h2>Admin Login</h2>
        <p style="color:red">Incorrect username or password</p>
        <form method="post">
        <input name="username" placeholder="Username" required>
        <input name="password" type="password" placeholder="Password" required>
        <button>Login</button></form></div>""")
    return page("""
    <div class="card" style="max-width:420px;margin:50px auto">
    <h2>Admin Login</h2><p>Sign in to manage the airport.</p>
    <form method="post">
    <input name="username" placeholder="Username" required>
    <input name="password" type="password" placeholder="Password" required>
    <button>Login</button></form></div>""")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def home():
    return page("""
    <h2>Dashboard</h2>
    <div class="stats">
    <div class="card">Total Flights<div class="stat">{{f}}</div></div>
    <div class="card">Total Gates<div class="stat">{{g}}</div></div>
    <div class="card">Passengers<div class="stat">{{p}}</div></div>
    </div><div class="card"><h3>Welcome, Admin!</h3>
    Use the navigation menu to manage airport records.</div>
    """, f=Flight.query.count(), g=Gate.query.count(),
         p=Passenger.query.count())


DATA = {
    "flights": {
        "model": Flight, "title": "Flight Management",
        "fields": [("number", "Flight Number"), ("airline", "Airline"),
                   ("destination", "Destination")],
        "columns": ["number", "airline", "destination", "status"],
        "defaults": {"status": "Scheduled"},
        "choices": {"status": ["Scheduled", "Boarding", "Departed",
                               "Landed", "Delayed", "Cancelled"]}
    },
    "gates": {
        "model": Gate, "title": "Gate Management",
        "fields": [("name", "Gate Name")],
        "columns": ["name", "status"],
        "defaults": {"status": "Available"},
        "choices": {"status": ["Available", "Occupied", "Maintenance"]}
    },
    "passengers": {
        "model": Passenger, "title": "Passenger Records",
        "fields": [("name", "Passenger Name"), ("flight", "Flight Number")],
        "columns": ["name", "flight"], "defaults": {}, "choices": {}
    }
}


@app.route("/manage/<kind>", methods=["GET", "POST"])
@login_required
def manage(kind):
    if kind not in DATA:
        return "Not found", 404

    config = DATA[kind]
    model = config["model"]

    if request.method == "POST":
        action = request.form.get("action")
        record_id = request.form.get("id", type=int)

        if action == "delete":
            record = db.session.get(model, record_id)
            if record:
                db.session.delete(record)
                db.session.commit()
            session["messages"] = ["Record deleted."]
            return redirect(url_for("manage", kind=kind))

        try:
            record = db.session.get(model, record_id) if record_id else model()
            if not record:
                return "Record not found", 404

            for field, label in config["fields"]:
                value = request.form.get(field, "").strip()
                if not value:
                    return page(FORM, title=config["title"],
                                fields=config["fields"], choices=config["choices"],
                                record=record, kind=kind, error=label + " is required")

                setattr(record, field, value)

            for field in config["defaults"]:
                setattr(record, field, config["defaults"][field])

            for field, options in config["choices"].items():
                if field in request.form:
                    if request.form[field] not in options:
                        return "Invalid selection", 400
                    setattr(record, field, request.form[field])

            if not record_id:
                db.session.add(record)
            db.session.commit()
            session["messages"] = ["Record saved successfully."]
        except Exception:
            db.session.rollback()
            session["messages"] = [
                "Could not save. Check required fields and duplicate values."
            ]
        return redirect(url_for("manage", kind=kind))

    records = model.query.order_by(model.id.desc()).all()
    edit_id = request.args.get("edit", type=int)
    record = db.session.get(model, edit_id) if edit_id else None

    return page(MANAGE, config=config, records=records,
                kind=kind, record=record)


FORM = """
<div class="card">
<h3>{{'Edit' if record and record.id else 'Add'}} {{title}}</h3>
{% if error %}<p style="color:red">{{error}}</p>{% endif %}
<form method="post">
<input type="hidden" name="id" value="{{record.id or ''}}">
{% for field,label in fields %}
<label>{{label}}</label>
<input name="{{field}}" value="{{record|attr(field) or ''}}" required>
{% endfor %}
{% for field,options in choices.items() %}
<label>{{field|title}}</label><select name="{{field}}">
{% for option in options %}
<option value="{{option}}" {% if record and record|attr(field)==option %}selected{% endif %}>{{option}}</option>
{% endfor %}
</select>
{% endfor %}
<button name="action" value="save">Save</button>
<a class="btn" style="background:#64748b" href="{{url_for('manage',kind=kind)}}">Cancel</a>
</form></div>
"""


MANAGE = """
<h2>{{config.title}}</h2>
""" + FORM + """
<div class="card"><div class="table">
<table><thead><tr>
{% for col in config.columns %}<th>{{col|title}}</th>{% endfor %}
<th>Actions</th></tr></thead><tbody>
{% for r in records %}<tr>
{% for col in config.columns %}<td>{{r|attr(col)}}</td>{% endfor %}
<td><a class="btn" href="{{url_for('manage',kind=kind,edit=r.id)}}">Edit</a>
<form method="post" style="display:inline" onsubmit="return confirm('Delete record?')">
<input type="hidden" name="id" value="{{r.id}}">
<button class="danger" name="action" value="delete">Delete</button>
</form></td></tr>
{% else %}<tr><td colspan="{{config.columns|length+1}}">No records yet.</td></tr>
{% endfor %}</tbody></table></div></div>
"""


@app.route("/health")
def health():
    return {"status": "ok"}, 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))