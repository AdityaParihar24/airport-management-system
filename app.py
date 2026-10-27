import os
from functools import wraps

from dotenv import load_dotenv
from flask import (
    Flask, request, redirect, session,
    render_template_string, url_for
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY")

if not app.secret_key:
    if os.environ.get("RENDER"):
        raise RuntimeError("SECRET_KEY must be configured on Render.")
    app.secret_key = "local-development-key-change-me"

database_url = os.environ.get("DATABASE_URL", "sqlite:///airport.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = bool(os.environ.get("RENDER"))

db = SQLAlchemy(app)


# -------------------- DATABASE MODELS --------------------

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


# -------------------- INITIAL DATABASE SETUP --------------------

with app.app_context():
    db.create_all()

    admin_username = os.environ.get("ADMIN_USERNAME", "admin")
    admin_password = os.environ.get("ADMIN_PASSWORD", "")

    # Configure ADMIN_PASSWORD in Render before the first deployment.
    if admin_password and not Admin.query.filter_by(
        username=admin_username
    ).first():
        db.session.add(Admin(
            username=admin_username,
            password=generate_password_hash(admin_password)
        ))
        db.session.commit()


# -------------------- HTML LAYOUT --------------------

PAGE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SkyPort | Airport Management</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#f1f5f9;color:#172033;font:15px Arial,sans-serif}
header{background:#10243b;color:white;padding:22px max(16px,calc((100% - 1100px)/2))}
header h2{margin:0 0 6px}
nav{background:#1d3552;padding:10px max(12px,calc((100% - 1100px)/2));display:flex;gap:6px;flex-wrap:wrap}
nav a{color:white;text-decoration:none;padding:11px;border-radius:6px}
nav a:hover{background:#355477}
.wrap{max-width:1100px;margin:25px auto;padding:0 16px}
.card{background:white;border-radius:10px;padding:20px;margin-bottom:18px;box-shadow:0 2px 12px #0000000b}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px}
.stat{font-size:30px;font-weight:bold;color:#2563eb;margin-top:12px}
input,select{width:100%;padding:11px;margin:6px 0 14px;border:1px solid #cbd5e1;border-radius:6px;background:white}
button,.btn{display:inline-block;background:#2563eb;color:white;border:0;border-radius:6px;padding:10px 14px;text-decoration:none;cursor:pointer}
.danger{background:#dc2626}.secondary{background:#64748b}
.table{overflow-x:auto}table{width:100%;border-collapse:collapse;min-width:480px}
th,td{text-align:left;padding:11px;border-bottom:1px solid #e2e8f0}
th{background:#f8fafc}
.msg{background:#dcfce7;padding:12px;margin-bottom:12px;border-radius:6px}
.error{background:#fee2e2;color:#991b1b;padding:10px;border-radius:6px}
.muted{color:#64748b}.actions{display:flex;gap:6px;align-items:center}
.actions form{margin:0}
@media(max-width:600px){.card{padding:14px}header{padding:20px 16px}th,td{padding:8px;font-size:13px}}
</style>
</head>
<body>
<header>
<h2>✈ SkyPort Airport</h2>
<small>Airport Management System</small>
</header>
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
{% for message in messages %}
<div class="msg">{{message}}</div>
{% endfor %}
{{content|safe}}
</div>
</body>
</html>
"""


def page(content, **kwargs):
    return render_template_string(
        PAGE,
        content=render_template_string(content, **kwargs),
        logged=("admin" in session),
        messages=session.pop("messages", [])
    )


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "admin" not in session:
            return redirect(url_for("login"))
        if not db.session.get(Admin, session["admin"]):
            session.clear()
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


# -------------------- LOGIN AND LOGOUT --------------------

LOGIN = """
<div class="card" style="max-width:420px;margin:45px auto">
<h2>Admin Login</h2>
<p class="muted">Sign in to manage airport operations.</p>
{% if error %}<p class="error">{{error}}</p>{% endif %}
<form method="post">
<label>Username</label>
<input name="username" autocomplete="username" required>
<label>Password</label>
<input name="password" type="password" autocomplete="current-password" required>
<button type="submit">Login</button>
</form>
</div>
"""


@app.route("/login", methods=["GET", "POST"])
def login():
    if "admin" in session:
        return redirect(url_for("home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        admin = Admin.query.filter_by(username=username).first()

        if admin and check_password_hash(admin.password, password):
            session.clear()
            session["admin"] = admin.id
            return redirect(url_for("home"))

        return page(LOGIN, error="Incorrect username or password.")

    return page(LOGIN, error="")


@app.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


# -------------------- DASHBOARD --------------------

@app.route("/")
@login_required
def home():
    return page("""
    <h2>Dashboard</h2>
    <p class="muted">Airport administration overview</p>
    <div class="stats">
        <div class="card">Total Flights<div class="stat">{{f}}</div></div>
        <div class="card">Total Gates<div class="stat">{{g}}</div></div>
        <div class="card">Passengers<div class="stat">{{p}}</div></div>
    </div>
    <div class="card">
        <h3>Welcome, Admin!</h3>
        <p>Manage airport records from the navigation menu.</p>
        <a class="btn" href="{{url_for('manage',kind='flights')}}">Manage Flights</a>
        <a class="btn" href="{{url_for('manage',kind='gates')}}">Manage Gates</a>
        <a class="btn" href="{{url_for('manage',kind='passengers')}}">Manage Passengers</a>
    </div>
    <div class="card">
        <h3>Recent Flights</h3>
        <div class="table"><table>
        <thead><tr><th>Flight</th><th>Airline</th><th>Destination</th><th>Status</th></tr></thead>
        <tbody>
        {% for r in recent %}
        <tr><td>{{r.number}}</td><td>{{r.airline}}</td><td>{{r.destination}}</td><td>{{r.status}}</td></tr>
        {% else %}
        <tr><td colspan="4">No flights added yet.</td></tr>
        {% endfor %}
        </tbody></table></div>
    </div>
    """,
    f=Flight.query.count(),
    g=Gate.query.count(),
    p=Passenger.query.count(),
    recent=Flight.query.order_by(Flight.id.desc()).limit(5).all()
    )


# -------------------- MANAGEMENT SETTINGS --------------------

DATA = {
    "flights": {
        "model": Flight,
        "title": "Flight Management",
        "fields": [
            ("number", "Flight Number"),
            ("airline", "Airline"),
            ("destination", "Destination")
        ],
        "columns": ["number", "airline", "destination", "status"],
        "choices": {
            "status": [
                "Scheduled", "Boarding", "Departed",
                "Landed", "Delayed", "Cancelled"
            ]
        },
        "defaults": {"status": "Scheduled"}
    },
    "gates": {
        "model": Gate,
        "title": "Gate Management",
        "fields": [("name", "Gate Name")],
        "columns": ["name", "status"],
        "choices": {
            "status": ["Available", "Occupied", "Maintenance"]
        },
        "defaults": {"status": "Available"}
    },
    "passengers": {
        "model": Passenger,
        "title": "Passenger Records",
        "fields": [
            ("name", "Passenger Name"),
            ("flight", "Flight Number")
        ],
        "columns": ["name", "flight"],
        "choices": {},
        "defaults": {}
    }
}


FORM = """
<div class="card">
<h3>{{'Edit' if record else 'Add'}} {{config.title}}</h3>
{% if error %}<p class="error">{{error}}</p>{% endif %}
<form method="post">
<input type="hidden" name="id" value="{{record.id if record else ''}}">
{% for field,label in config.fields %}
<label>{{label}}</label>
<input name="{{field}}" maxlength="120"
value="{{record|attr(field) if record else ''}}" required>
{% endfor %}
{% for field,options in config.choices.items() %}
<label>{{field|title}}</label>
<select name="{{field}}" required>
{% for option in options %}
<option value="{{option}}"
{% if record and record|attr(field)==option %}selected
{% elif not record and config.defaults.get(field)==option %}selected
{% endif %}>{{option}}</option>
{% endfor %}
</select>
{% endfor %}
<button name="action" value="save" type="submit">Save Record</button>
<a class="btn secondary" href="{{url_for('manage',kind=kind)}}">Cancel</a>
</form>
</div>
"""


MANAGE = """
<h2>{{config.title}}</h2>
""" + FORM + """
<div class="card">
<h3>All Records ({{records|length}})</h3>
<div class="table"><table>
<thead><tr>
{% for col in config.columns %}<th>{{col|title}}</th>{% endfor %}
<th>Actions</th>
</tr></thead>
<tbody>
{% for r in records %}
<tr>
{% for col in config.columns %}<td>{{r|attr(col)}}</td>{% endfor %}
<td><div class="actions">
<a class="btn" href="{{url_for('manage',kind=kind,edit=r.id)}}">Edit</a>
<form method="post" onsubmit="return confirm('Delete this record?')">
<input type="hidden" name="id" value="{{r.id}}">
<button class="danger" name="action" value="delete">Delete</button>
</form>
</div></td>
</tr>
{% else %}
<tr><td colspan="{{config.columns|length+1}}">No records yet.</td></tr>
{% endfor %}
</tbody></table></div>
</div>
"""


# -------------------- ADD, EDIT AND DELETE --------------------

@app.route("/manage/<kind>", methods=["GET", "POST"])
@login_required
def manage(kind):
    if kind not in DATA:
        return "Page not found", 404

    config = DATA[kind]
    model = config["model"]

    if request.method == "POST":
        action = request.form.get("action", "")
        record_id = request.form.get("id", type=int)

        if action == "delete":
            record = db.session.get(model, record_id) if record_id else None

            if record:
                db.session.delete(record)
                db.session.commit()
                session["messages"] = ["Record deleted successfully."]
            else:
                session["messages"] = ["Record not found."]

            return redirect(url_for("manage", kind=kind))

        if action != "save":
            return "Invalid action", 400

        record = db.session.get(model, record_id) if record_id else model()

        if record_id and record is None:
            return "Record not found", 404

        error = ""

        for field, label in config["fields"]:
            value = request.form.get(field, "").strip()

            if not value:
                error = label + " is required."
                break

            if len(value) > 120:
                error = label + " is too long."
                break

            setattr(record, field, value)

        if not error:
            for field, options in config["choices"].items():
                value = request.form.get(field, "")

                if value not in options:
                    error = "Invalid " + field + " selection."
                    break

                setattr(record, field, value)

        if error:
            return page(
                MANAGE, config=config,
                records=model.query.order_by(model.id.desc()).all(),
                kind=kind, record=record, error=error
            ), 400

        try:
            if not record_id:
                for field, value in config["defaults"].items():
                    if field not in config["choices"]:
                        setattr(record, field, value)
                db.session.add(record)

            db.session.commit()
            session["messages"] = ["Record saved successfully."]
            return redirect(url_for("manage", kind=kind))

        except IntegrityError:
            db.session.rollback()
            return page(
                MANAGE, config=config,
                records=model.query.order_by(model.id.desc()).all(),
                kind=kind, record=record,
                error="Duplicate value or database constraint error."
            ), 400

        except Exception:
            db.session.rollback()
            app.logger.exception("Failed to save airport record")
            return page(
                MANAGE, config=config,
                records=model.query.order_by(model.id.desc()).all(),
                kind=kind, record=record,
                error="Could not save the record. Please try again."
            ), 500

    records = model.query.order_by(model.id.desc()).all()
    edit_id = request.args.get("edit", type=int)
    record = db.session.get(model, edit_id) if edit_id else None

    if edit_id and not record:
        return "Record not found", 404

    return page(
        MANAGE, config=config, records=records,
        kind=kind, record=record, error=""
    )


# -------------------- HEALTH CHECK --------------------

@app.route("/health")
def health():
    return {"status": "ok"}, 200


# Render runs the app through Gunicorn using app:app.
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)))
