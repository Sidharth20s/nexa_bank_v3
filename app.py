import os, random, string
from datetime import datetime, timedelta, timezone
from functools import wraps
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, make_response
from flask_bcrypt import Bcrypt
from flask_jwt_extended import (
    JWTManager, create_access_token, get_jwt_identity,
    jwt_required, set_access_cookies, unset_jwt_cookies, verify_jwt_in_request
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

load_dotenv()
app = Flask(__name__)

# ── CONFIG ────────────────────────────────────────────────────────────────────
app.config["SECRET_KEY"]                  = os.environ.get("SECRET_KEY","dev-secret")
app.config["SQLALCHEMY_DATABASE_URI"]     = os.environ.get("DATABASE_URL","sqlite:///nexabank.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JWT_SECRET_KEY"]              = os.environ.get("JWT_SECRET_KEY","dev-jwt")
app.config["JWT_TOKEN_LOCATION"]          = ["cookies"]
app.config["JWT_COOKIE_HTTPONLY"]         = True
app.config["JWT_COOKIE_SAMESITE"]         = "Lax"
app.config["JWT_ACCESS_TOKEN_EXPIRES"]    = timedelta(hours=2)
app.config["JWT_COOKIE_CSRF_PROTECT"]     = True
app.config["WTF_CSRF_TIME_LIMIT"]         = 7200

db      = SQLAlchemy(app)
bcrypt  = Bcrypt(app)
jwt     = JWTManager(app)
csrf    = CSRFProtect(app)
limiter = Limiter(get_remote_address, app=app,
                  default_limits=["500 per day","100 per hour"],
                  storage_uri="memory://")

BANK_IFSC = "NEXA0261"
BANK_NAME = "NexaBank"

# ── MODELS ────────────────────────────────────────────────────────────────────
class User(db.Model):
    __tablename__ = "users"
    id             = db.Column(db.Integer, primary_key=True)
    name           = db.Column(db.String(100), nullable=False)
    email          = db.Column(db.String(150), unique=True, nullable=False)
    mobile         = db.Column(db.String(20))
    password_hash  = db.Column(db.String(255), nullable=False)
    account_type   = db.Column(db.String(20), default="Savings")
    account_number = db.Column(db.String(20), unique=True)
    ifsc           = db.Column(db.String(20), default=BANK_IFSC)
    bank_name      = db.Column(db.String(50), default=BANK_NAME)
    upi_id         = db.Column(db.String(100))
    balance        = db.Column(db.Float, default=0.0)
    status         = db.Column(db.String(20), default="active")
    loyalty_points = db.Column(db.Integer, default=0)
    two_fa_enabled = db.Column(db.Boolean, default=False)
    referral_code  = db.Column(db.String(20), unique=True)
    created_at     = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    transactions_sent     = db.relationship("Transaction", foreign_keys="Transaction.sender_id",   backref="sender",   lazy=True)
    transactions_received = db.relationship("Transaction", foreign_keys="Transaction.receiver_id", backref="receiver", lazy=True)
    loans                 = db.relationship("Loan",        backref="user",        lazy=True)
    complaints            = db.relationship("Complaint",   backref="user",        lazy=True)
    savings_goals         = db.relationship("SavingsGoal", backref="user",        lazy=True)
    budgets               = db.relationship("Budget",      backref="user",        lazy=True)
    investments           = db.relationship("Investment",  backref="user",        lazy=True)
    virtual_cards         = db.relationship("VirtualCard", backref="user",        lazy=True)
    notifications         = db.relationship("Notification",backref="user",        lazy=True)
    system_logs           = db.relationship("SystemLog",   backref="user",        lazy=True)

    def set_password(self, p): self.password_hash = bcrypt.generate_password_hash(p).decode("utf-8")
    def check_password(self, p): return bcrypt.check_password_hash(self.password_hash, p)

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "email": self.email,
            "mobile": self.mobile, "account_type": self.account_type,
            "account_number": self.account_number, "ifsc": self.ifsc,
            "bank_name": self.bank_name, "upi_id": self.upi_id,
            "balance": round(self.balance, 2), "status": self.status,
            "loyalty_points": self.loyalty_points,
            "two_fa_enabled": self.two_fa_enabled,
            "referral_code": self.referral_code,
            "created_at": self.created_at.strftime("%d %b %Y"),
        }


class Transaction(db.Model):
    __tablename__ = "transactions"
    id          = db.Column(db.Integer, primary_key=True)
    sender_id   = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    amount      = db.Column(db.Float, nullable=False)
    mode        = db.Column(db.String(20), default="Bank Transfer")
    remarks     = db.Column(db.String(200))
    ref_no      = db.Column(db.String(20), unique=True)
    status      = db.Column(db.String(20), default="completed")
    created_at  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "sender_id": self.sender_id,
            "sender_name": self.sender.name if self.sender else "Unknown",
            "receiver_id": self.receiver_id,
            "receiver_name": self.receiver.name if self.receiver else "Unknown",
            "amount": round(self.amount, 2),
            "mode": self.mode, "remarks": self.remarks,
            "ref_no": self.ref_no, "status": self.status,
            "date": self.created_at.strftime("%d %b %Y, %I:%M %p"),
        }


class Loan(db.Model):
    __tablename__ = "loans"
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    loan_type  = db.Column(db.String(30))
    amount     = db.Column(db.Float)
    status     = db.Column(db.String(20), default="Approved")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {"id": self.id, "loan_type": self.loan_type,
                "amount": self.amount, "status": self.status,
                "date": self.created_at.strftime("%d %b %Y")}


class Complaint(db.Model):
    __tablename__ = "complaints"
    id             = db.Column(db.Integer, primary_key=True)
    user_id        = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    subject        = db.Column(db.String(200))
    description    = db.Column(db.Text)
    status         = db.Column(db.String(20), default="Pending")
    admin_response = db.Column(db.Text)
    ip_address     = db.Column(db.String(50))
    location       = db.Column(db.String(100))
    created_at     = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id, "user_id": self.user_id,
            "user_name": self.user.name if self.user else "Unknown",
            "user_email": self.user.email if self.user else "",
            "subject": self.subject, "description": self.description,
            "status": self.status, "admin_response": self.admin_response,
            "ip_address": self.ip_address, "location": self.location,
            "date": self.created_at.strftime("%d %b %Y, %I:%M %p"),
        }


class SavingsGoal(db.Model):
    __tablename__ = "savings_goals"
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name        = db.Column(db.String(100))
    description = db.Column(db.String(200))
    target      = db.Column(db.Float)
    saved       = db.Column(db.Float, default=0.0)
    created_at  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {"id": self.id, "name": self.name, "description": self.description,
                "target": self.target, "saved": self.saved,
                "progress": round((self.saved / self.target * 100), 1) if self.target else 0}


class Budget(db.Model):
    __tablename__ = "budgets"
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    category   = db.Column(db.String(50))
    limit_amt  = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {"id": self.id, "category": self.category, "limit": self.limit_amt}


class Investment(db.Model):
    __tablename__ = "investments"
    id            = db.Column(db.Integer, primary_key=True)
    user_id       = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    inv_type      = db.Column(db.String(50))
    amount        = db.Column(db.Float)
    current_value = db.Column(db.Float)
    created_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        gain = self.current_value - self.amount
        return {"id": self.id, "type": self.inv_type, "amount": self.amount,
                "current_value": round(self.current_value, 2),
                "gain": round(gain, 2),
                "gain_pct": round((gain / self.amount * 100), 2) if self.amount else 0}


class VirtualCard(db.Model):
    __tablename__ = "virtual_cards"
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    card_type  = db.Column(db.String(20))
    number     = db.Column(db.String(30))
    masked     = db.Column(db.String(30))
    cvv        = db.Column(db.String(5))
    expiry     = db.Column(db.String(10), default="12/28")
    is_active  = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {"id": self.id, "type": self.card_type, "masked": self.masked,
                "cvv": self.cvv, "expiry": self.expiry, "is_active": self.is_active}


class Notification(db.Model):
    __tablename__ = "notifications"
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    message    = db.Column(db.String(300))
    notif_type = db.Column(db.String(20), default="info")
    is_read    = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {"id": self.id, "message": self.message, "type": self.notif_type,
                "is_read": self.is_read, "time": self.created_at.strftime("%I:%M %p")}


class SystemLog(db.Model):
    __tablename__ = "system_logs"
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action      = db.Column(db.String(100))
    details     = db.Column(db.Text)
    ip_address  = db.Column(db.String(50))
    location    = db.Column(db.String(100))
    browser     = db.Column(db.String(50))
    user_type   = db.Column(db.String(20), default="system")
    created_at  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "user_name": self.user.name if self.user else "System",
            "action": self.action, "details": self.details,
            "ip_address": self.ip_address, "location": self.location,
            "browser": self.browser, "user_type": self.user_type,
            "time": self.created_at.strftime("%d %b %Y, %I:%M %p"),
        }


class RecurringPayment(db.Model):
    __tablename__ = "recurring_payments"
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name       = db.Column(db.String(100))
    amount     = db.Column(db.Float)
    frequency  = db.Column(db.String(20))
    next_date  = db.Column(db.String(30))
    is_active  = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {"id": self.id, "name": self.name, "amount": self.amount,
                "frequency": self.frequency, "next_date": self.next_date, "is_active": self.is_active}


class MoneyRequest(db.Model):
    __tablename__ = "money_requests"
    id          = db.Column(db.Integer, primary_key=True)
    from_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    to_id       = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    amount      = db.Column(db.Float)
    message     = db.Column(db.String(200))
    status      = db.Column(db.String(20), default="Pending")
    created_at  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    from_user   = db.relationship("User", foreign_keys=[from_id])
    to_user     = db.relationship("User", foreign_keys=[to_id])

    def to_dict(self):
        return {
            "id": self.id,
            "from_id": self.from_id, "from_name": self.from_user.name if self.from_user else "",
            "to_id": self.to_id, "to_name": self.to_user.name if self.to_user else "",
            "amount": self.amount, "message": self.message, "status": self.status,
            "date": self.created_at.strftime("%d %b %Y"),
        }


# ── HELPERS ──────────────────────────────────────────────────────────────────
def gen_account_no():
    return "NXB" + "".join(random.choices(string.digits, k=7))

def gen_ref_no():
    return "TXN" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))

def gen_referral_code():
    return "REF" + "".join(random.choices(string.ascii_uppercase + string.digits, k=9))

def clean(val, mn=1, mx=200):
    if not val or not isinstance(val, str): return None
    val = val.strip()
    return val if mn <= len(val) <= mx else None

def add_notification(user_id, message, ntype="info"):
    n = Notification(user_id=user_id, message=message, notif_type=ntype)
    db.session.add(n)

def add_log(action, details, user_id=None, ip=None, location=None, browser=None, user_type="user"):
    log = SystemLog(user_id=user_id, action=action, details=details,
                    ip_address=ip or "Unknown", location=location or "Unknown",
                    browser=browser or "Unknown", user_type=user_type)
    db.session.add(log)

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            verify_jwt_in_request()
            if get_jwt_identity().get("role") != "admin":
                return jsonify({"error": "Admin access required"}), 403
        except Exception:
            return jsonify({"error": "Authentication required"}), 401
        return fn(*args, **kwargs)
    return wrapper

def user_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            verify_jwt_in_request()
            if get_jwt_identity().get("role") != "user":
                return jsonify({"error": "User access required"}), 403
        except Exception:
            return jsonify({"error": "Authentication required"}), 401
        return fn(*args, **kwargs)
    return wrapper

# ── PAGE ROUTES ───────────────────────────────────────────────────────────────
@app.route("/")
def index(): return render_template("bank.html")

# ── AUTH ──────────────────────────────────────────────────────────────────────
@app.route("/api/admin/login", methods=["POST"])
@limiter.limit("5 per minute")
def admin_login():
    d = request.get_json()
    if not d: return jsonify({"error":"Invalid request"}), 400
    u = clean(d.get("username"), 1, 50)
    p = clean(d.get("password"), 1, 100)
    if not u or not p: return jsonify({"error":"Invalid input"}), 400
    ip = request.remote_addr
    if u != os.environ.get("ADMIN_USERNAME") or p != os.environ.get("ADMIN_PASSWORD"):
        add_log("LOGIN_FAILED", f"Failed admin login for '{u}'", ip=ip, user_type="admin")
        db.session.commit()
        return jsonify({"error":"Invalid credentials"}), 401
    token = create_access_token(identity={"role":"admin","username":u})
    resp  = jsonify({"success":True})
    set_access_cookies(resp, token)
    add_log("ADMIN_LOGIN", f"Admin '{u}' logged in", ip=ip, user_type="admin")
    db.session.commit()
    return resp

@app.route("/api/user/login", methods=["POST"])
@limiter.limit("10 per minute")
def user_login():
    d = request.get_json()
    if not d: return jsonify({"error":"Invalid request"}), 400
    email = clean(d.get("email"), 3, 150)
    pwd   = clean(d.get("password"), 1, 100)
    if not email or not pwd: return jsonify({"error":"Invalid input"}), 400
    ip = request.remote_addr
    user = User.query.filter_by(email=email.lower()).first()
    if not user or not user.check_password(pwd):
        add_log("LOGIN_FAILED", f"Failed login for '{email}'", ip=ip)
        db.session.commit()
        return jsonify({"error":"Access denied! Invalid credentials or account suspended."}), 401
    if user.status == "suspended":
        return jsonify({"error":"Account suspended. Contact your bank."}), 403
    token = create_access_token(identity={"role":"user","user_id":user.id})
    resp  = jsonify({"success":True})
    set_access_cookies(resp, token)
    add_notification(user.id, f"👋 Welcome back, {user.name}!")
    add_log("USER_LOGIN", f"User '{user.name}' logged in", user_id=user.id, ip=ip)
    db.session.commit()
    return resp

@app.route("/api/logout", methods=["POST"])
def logout():
    resp = jsonify({"success":True})
    unset_jwt_cookies(resp)
    return resp

# ── USER API ──────────────────────────────────────────────────────────────────
@app.route("/api/user/me")
@user_required
def get_me():
    uid = get_jwt_identity()["user_id"]
    u = User.query.get(uid)
    if not u: return jsonify({"error":"Not found"}), 404
    return jsonify(u.to_dict())

@app.route("/api/user/transactions")
@user_required
def get_user_txs():
    uid = get_jwt_identity()["user_id"]
    txs = Transaction.query.filter(
        (Transaction.sender_id==uid)|(Transaction.receiver_id==uid)
    ).order_by(Transaction.created_at.desc()).all()
    return jsonify([t.to_dict() for t in txs])

@app.route("/api/user/transfer", methods=["POST"])
@user_required
@limiter.limit("30 per hour")
def transfer():
    uid    = get_jwt_identity()["user_id"]
    sender = User.query.get(uid)
    d      = request.get_json()
    if not d: return jsonify({"error":"Invalid request"}), 400
    try:    amount = float(d.get("amount", 0))
    except: return jsonify({"error":"Invalid amount"}), 400
    mode    = clean(d.get("mode","Bank Transfer"),1,30) or "Bank Transfer"
    remarks = clean(d.get("remarks","Transfer"),1,200) or "Transfer"
    rid     = d.get("receiver_id")
    if not rid:           return jsonify({"error":"Recipient required"}), 400
    if amount <= 0:       return jsonify({"error":"Amount must be > 0"}), 400
    if amount > 500000:   return jsonify({"error":"Exceeds daily limit ₹5,00,000"}), 400
    if sender.id == int(rid): return jsonify({"error":"Cannot transfer to yourself"}), 400
    if sender.balance < amount: return jsonify({"error":"Insufficient balance"}), 400
    recv = User.query.get(int(rid))
    if not recv or recv.status != "active": return jsonify({"error":"Recipient not found"}), 404
    sender.balance   = round(sender.balance   - amount, 2)
    recv.balance     = round(recv.balance     + amount, 2)
    pts = max(1, int(amount // 100))
    sender.loyalty_points += pts
    tx = Transaction(sender_id=sender.id, receiver_id=recv.id,
                     amount=amount, mode=mode, remarks=remarks, ref_no=gen_ref_no())
    db.session.add(tx)
    add_notification(sender.id, f"💸 Transferred ₹{amount:,.0f} to {recv.name}")
    add_notification(recv.id,   f"💰 Received ₹{amount:,.0f} from {sender.name}")
    add_log("TRANSFER", f"₹{amount} from {sender.name} to {recv.name}", user_id=sender.id,
            ip=request.remote_addr)
    db.session.commit()
    return jsonify({"success":True,"new_balance":sender.balance,"ref":tx.ref_no,"loyalty_earned":pts})

@app.route("/api/user/upi", methods=["POST"])
@user_required
@limiter.limit("30 per hour")
def upi_transfer():
    uid = get_jwt_identity()["user_id"]
    sender = User.query.get(uid)
    d = request.get_json()
    try:    amount = float(d.get("amount",0))
    except: return jsonify({"error":"Invalid amount"}), 400
    upi_id = clean(d.get("upi_id",""),3,100)
    if not upi_id: return jsonify({"error":"UPI ID required"}), 400
    if sender.balance < amount: return jsonify({"error":"Insufficient balance"}), 400
    recv = User.query.filter_by(upi_id=upi_id).first()
    if not recv: return jsonify({"error":"UPI ID not found"}), 404
    if recv.id == sender.id: return jsonify({"error":"Cannot pay yourself"}), 400
    sender.balance = round(sender.balance - amount, 2)
    recv.balance   = round(recv.balance   + amount, 2)
    tx = Transaction(sender_id=sender.id, receiver_id=recv.id,
                     amount=amount, mode="UPI", remarks="UPI Payment", ref_no=gen_ref_no())
    db.session.add(tx)
    add_notification(sender.id, f"🪙 UPI payment ₹{amount:,.0f} to {recv.name}")
    db.session.commit()
    return jsonify({"success":True,"new_balance":sender.balance})

@app.route("/api/user/bill", methods=["POST"])
@user_required
def pay_bill():
    uid = get_jwt_identity()["user_id"]
    u = User.query.get(uid)
    d = request.get_json()
    try:    amount = float(d.get("amount",0))
    except: return jsonify({"error":"Invalid amount"}), 400
    if u.balance < amount: return jsonify({"error":"Insufficient balance"}), 400
    bill_type = clean(d.get("bill_type","Bill"),1,50) or "Bill"
    u.balance = round(u.balance - amount, 2)
    add_notification(u.id, f"📄 {bill_type} ₹{amount:,.0f} paid successfully")
    db.session.commit()
    return jsonify({"success":True,"new_balance":u.balance})

@app.route("/api/user/recharge", methods=["POST"])
@user_required
def recharge():
    uid = get_jwt_identity()["user_id"]
    u = User.query.get(uid)
    d = request.get_json()
    try:    amount = float(d.get("amount",0))
    except: return jsonify({"error":"Invalid amount"}), 400
    if u.balance < amount: return jsonify({"error":"Insufficient balance"}), 400
    operator = clean(d.get("operator",""),1,30) or "Operator"
    u.balance = round(u.balance - amount, 2)
    add_notification(u.id, f"📱 Recharge ₹{amount:,.0f} ({operator}) done!")
    db.session.commit()
    return jsonify({"success":True,"new_balance":u.balance})

@app.route("/api/user/loans", methods=["GET"])
@user_required
def get_loans():
    uid = get_jwt_identity()["user_id"]
    return jsonify([l.to_dict() for l in Loan.query.filter_by(user_id=uid).all()])

@app.route("/api/user/loans", methods=["POST"])
@user_required
def apply_loan():
    uid = get_jwt_identity()["user_id"]
    u = User.query.get(uid)
    d = request.get_json()
    try:    amount = float(d.get("amount",0))
    except: return jsonify({"error":"Invalid amount"}), 400
    if amount < 50000: return jsonify({"error":"Min loan amount ₹50,000"}), 400
    ltype = clean(d.get("loan_type","Personal"),1,30) or "Personal"
    loan = Loan(user_id=uid, loan_type=ltype, amount=amount, status="Approved")
    u.balance = round(u.balance + amount, 2)
    db.session.add(loan)
    add_notification(uid, f"🏦 {ltype} Loan ₹{amount:,.0f} approved!")
    db.session.commit()
    return jsonify({"success":True,"new_balance":u.balance,"loan":loan.to_dict()})

@app.route("/api/user/complaints", methods=["GET"])
@user_required
def get_complaints():
    uid = get_jwt_identity()["user_id"]
    return jsonify([c.to_dict() for c in Complaint.query.filter_by(user_id=uid).order_by(Complaint.created_at.desc()).all()])

@app.route("/api/user/complaints", methods=["POST"])
@user_required
def file_complaint():
    uid = get_jwt_identity()["user_id"]
    d = request.get_json()
    subject = clean(d.get("subject",""),2,200)
    desc    = clean(d.get("description",""),5,2000)
    if not subject or not desc: return jsonify({"error":"Subject and description required"}), 400
    c = Complaint(user_id=uid, subject=subject, description=desc,
                  ip_address=request.remote_addr,
                  location=clean(d.get("location","Unknown"),1,100) or "Unknown")
    db.session.add(c)
    add_log("COMPLAINT_FILED", f"Complaint: {subject}", user_id=uid, ip=request.remote_addr)
    db.session.commit()
    return jsonify({"success":True,"complaint":c.to_dict()})

@app.route("/api/user/savings-goals", methods=["GET"])
@user_required
def get_goals():
    uid = get_jwt_identity()["user_id"]
    return jsonify([g.to_dict() for g in SavingsGoal.query.filter_by(user_id=uid).all()])

@app.route("/api/user/savings-goals", methods=["POST"])
@user_required
def create_goal():
    uid = get_jwt_identity()["user_id"]
    d = request.get_json()
    name = clean(d.get("name",""),1,100)
    try:    target = float(d.get("target",0))
    except: return jsonify({"error":"Invalid target"}), 400
    if not name or target <= 0: return jsonify({"error":"Name and target required"}), 400
    g = SavingsGoal(user_id=uid, name=name, description=d.get("description",""), target=target)
    db.session.add(g)
    db.session.commit()
    return jsonify({"success":True,"goal":g.to_dict()})

@app.route("/api/user/savings-goals/<int:gid>/add", methods=["POST"])
@user_required
def add_to_goal(gid):
    uid = get_jwt_identity()["user_id"]
    u = User.query.get(uid)
    g = SavingsGoal.query.filter_by(id=gid, user_id=uid).first_or_404()
    d = request.get_json()
    try:    amount = float(d.get("amount",0))
    except: return jsonify({"error":"Invalid amount"}), 400
    if u.balance < amount: return jsonify({"error":"Insufficient balance"}), 400
    u.balance = round(u.balance - amount, 2)
    g.saved   = round(g.saved   + amount, 2)
    db.session.commit()
    return jsonify({"success":True,"new_balance":u.balance,"goal":g.to_dict()})

@app.route("/api/user/savings-goals/<int:gid>", methods=["DELETE"])
@user_required
def delete_goal(gid):
    uid = get_jwt_identity()["user_id"]
    g = SavingsGoal.query.filter_by(id=gid, user_id=uid).first_or_404()
    db.session.delete(g); db.session.commit()
    return jsonify({"success":True})

@app.route("/api/user/budgets", methods=["GET"])
@user_required
def get_budgets():
    uid = get_jwt_identity()["user_id"]
    return jsonify([b.to_dict() for b in Budget.query.filter_by(user_id=uid).all()])

@app.route("/api/user/budgets", methods=["POST"])
@user_required
def create_budget():
    uid = get_jwt_identity()["user_id"]
    d = request.get_json()
    cat = clean(d.get("category",""),1,50)
    try:    limit = float(d.get("limit",0))
    except: return jsonify({"error":"Invalid limit"}), 400
    if not cat or limit <= 0: return jsonify({"error":"Category and limit required"}), 400
    Budget.query.filter_by(user_id=uid, category=cat).delete()
    b = Budget(user_id=uid, category=cat, limit_amt=limit)
    db.session.add(b); db.session.commit()
    return jsonify({"success":True,"budget":b.to_dict()})

@app.route("/api/user/budgets/<int:bid>", methods=["DELETE"])
@user_required
def delete_budget(bid):
    uid = get_jwt_identity()["user_id"]
    b = Budget.query.filter_by(id=bid, user_id=uid).first_or_404()
    db.session.delete(b); db.session.commit()
    return jsonify({"success":True})

@app.route("/api/user/investments", methods=["GET"])
@user_required
def get_investments():
    uid = get_jwt_identity()["user_id"]
    return jsonify([i.to_dict() for i in Investment.query.filter_by(user_id=uid).all()])

@app.route("/api/user/investments", methods=["POST"])
@user_required
def invest():
    uid = get_jwt_identity()["user_id"]
    u = User.query.get(uid)
    d = request.get_json()
    try:    amount = float(d.get("amount",0))
    except: return jsonify({"error":"Invalid amount"}), 400
    itype = clean(d.get("type","Stocks"),1,50) or "Stocks"
    if u.balance < amount: return jsonify({"error":"Insufficient balance"}), 400
    variance = random.uniform(-10, 15)
    curr_val = round(amount * (1 + variance/100), 2)
    u.balance = round(u.balance - amount, 2)
    inv = Investment(user_id=uid, inv_type=itype, amount=amount, current_value=curr_val)
    db.session.add(inv)
    add_notification(uid, f"📈 Invested ₹{amount:,.0f} in {itype}")
    db.session.commit()
    return jsonify({"success":True,"new_balance":u.balance,"investment":inv.to_dict()})

@app.route("/api/user/virtual-cards", methods=["GET"])
@user_required
def get_vcards():
    uid = get_jwt_identity()["user_id"]
    return jsonify([c.to_dict() for c in VirtualCard.query.filter_by(user_id=uid).all()])

@app.route("/api/user/virtual-cards", methods=["POST"])
@user_required
def create_vcard():
    uid = get_jwt_identity()["user_id"]
    d = request.get_json()
    ctype = clean(d.get("card_type","Visa"),1,20) or "Visa"
    num   = "VCARD" + "".join(random.choices(string.ascii_uppercase+string.digits,k=9))
    masked= "VCARD****" + num[-4:]
    cvv   = str(random.randint(100,999))
    vc = VirtualCard(user_id=uid, card_type=ctype, number=num, masked=masked, cvv=cvv)
    db.session.add(vc)
    add_notification(uid, f"🔐 New virtual {ctype} card created!")
    db.session.commit()
    return jsonify({"success":True,"card":vc.to_dict()})

@app.route("/api/user/virtual-cards/<int:cid>/toggle", methods=["POST"])
@user_required
def toggle_vcard(cid):
    uid = get_jwt_identity()["user_id"]
    vc = VirtualCard.query.filter_by(id=cid, user_id=uid).first_or_404()
    vc.is_active = not vc.is_active
    db.session.commit()
    return jsonify({"success":True,"is_active":vc.is_active})

@app.route("/api/user/virtual-cards/<int:cid>", methods=["DELETE"])
@user_required
def delete_vcard(cid):
    uid = get_jwt_identity()["user_id"]
    vc = VirtualCard.query.filter_by(id=cid, user_id=uid).first_or_404()
    db.session.delete(vc); db.session.commit()
    return jsonify({"success":True})

@app.route("/api/user/notifications", methods=["GET"])
@user_required
def get_notifications():
    uid = get_jwt_identity()["user_id"]
    notifs = Notification.query.filter_by(user_id=uid).order_by(Notification.created_at.desc()).limit(20).all()
    return jsonify([n.to_dict() for n in notifs])

@app.route("/api/user/notifications/read", methods=["POST"])
@user_required
def mark_read():
    uid = get_jwt_identity()["user_id"]
    Notification.query.filter_by(user_id=uid, is_read=False).update({"is_read":True})
    db.session.commit()
    return jsonify({"success":True})

@app.route("/api/user/recurring", methods=["GET"])
@user_required
def get_recurring():
    uid = get_jwt_identity()["user_id"]
    return jsonify([r.to_dict() for r in RecurringPayment.query.filter_by(user_id=uid).all()])

@app.route("/api/user/recurring", methods=["POST"])
@user_required
def create_recurring():
    uid = get_jwt_identity()["user_id"]
    d = request.get_json()
    name = clean(d.get("name",""),1,100)
    try:    amount = float(d.get("amount",0))
    except: return jsonify({"error":"Invalid amount"}), 400
    freq = clean(d.get("frequency","Monthly"),1,20) or "Monthly"
    if not name or amount <= 0: return jsonify({"error":"Name and amount required"}), 400
    r = RecurringPayment(user_id=uid, name=name, amount=amount, frequency=freq,
                         next_date=datetime.now(timezone.utc).strftime("%d %b %Y"))
    db.session.add(r); db.session.commit()
    return jsonify({"success":True,"recurring":r.to_dict()})

@app.route("/api/user/recurring/<int:rid>", methods=["DELETE"])
@user_required
def delete_recurring(rid):
    uid = get_jwt_identity()["user_id"]
    r = RecurringPayment.query.filter_by(id=rid, user_id=uid).first_or_404()
    db.session.delete(r); db.session.commit()
    return jsonify({"success":True})

@app.route("/api/user/money-requests", methods=["GET"])
@user_required
def get_money_requests():
    uid = get_jwt_identity()["user_id"]
    reqs = MoneyRequest.query.filter((MoneyRequest.from_id==uid)|(MoneyRequest.to_id==uid)).order_by(MoneyRequest.created_at.desc()).all()
    return jsonify([r.to_dict() for r in reqs])

@app.route("/api/user/money-requests", methods=["POST"])
@user_required
def create_money_request():
    uid = get_jwt_identity()["user_id"]
    d = request.get_json()
    to_id = d.get("to_id")
    try:    amount = float(d.get("amount",0))
    except: return jsonify({"error":"Invalid amount"}), 400
    msg = clean(d.get("message",""),0,200) or "No message"
    if not to_id or amount <= 0: return jsonify({"error":"Missing fields"}), 400
    mr = MoneyRequest(from_id=uid, to_id=int(to_id), amount=amount, message=msg)
    db.session.add(mr); db.session.commit()
    return jsonify({"success":True})

@app.route("/api/user/money-requests/<int:rid>/respond", methods=["POST"])
@user_required
def respond_request(rid):
    uid = get_jwt_identity()["user_id"]
    d = request.get_json()
    response = d.get("response","Declined")
    mr = MoneyRequest.query.filter_by(id=rid, to_id=uid).first_or_404()
    if response == "Accepted":
        u = User.query.get(uid)
        requester = User.query.get(mr.from_id)
        if u.balance < mr.amount: return jsonify({"error":"Insufficient balance"}), 400
        u.balance         = round(u.balance         - mr.amount, 2)
        requester.balance = round(requester.balance + mr.amount, 2)
        tx = Transaction(sender_id=uid, receiver_id=mr.from_id,
                         amount=mr.amount, mode="Money Request",
                         remarks=mr.message, ref_no=gen_ref_no())
        db.session.add(tx)
        mr.status = "Completed"
    else:
        mr.status = "Declined"
    db.session.commit()
    return jsonify({"success":True})

@app.route("/api/user/2fa/toggle", methods=["POST"])
@user_required
def toggle_2fa():
    uid = get_jwt_identity()["user_id"]
    u = User.query.get(uid)
    u.two_fa_enabled = not u.two_fa_enabled
    add_notification(uid, f"🔐 2FA {'enabled' if u.two_fa_enabled else 'disabled'}")
    db.session.commit()
    return jsonify({"success":True,"enabled":u.two_fa_enabled})

@app.route("/api/user/beneficiaries")
@user_required
def get_beneficiaries():
    uid = get_jwt_identity()["user_id"]
    users = User.query.filter(User.id!=uid, User.status=="active").all()
    return jsonify([{"id":u.id,"name":u.name,"account_number":u.account_number,"upi_id":u.upi_id} for u in users])

# ── ADMIN API ─────────────────────────────────────────────────────────────────
@app.route("/api/admin/stats")
@admin_required
def admin_stats():
    users = User.query.all()
    txs   = Transaction.query.all()
    complaints = Complaint.query.all()
    total_bal  = sum(u.balance for u in users)
    total_vol  = sum(t.amount for t in txs)
    return jsonify({
        "total_users":    len(users),
        "active_users":   sum(1 for u in users if u.status=="active"),
        "suspended_users":sum(1 for u in users if u.status=="suspended"),
        "total_deposits": round(total_bal,2),
        "total_txs":      len(txs),
        "total_volume":   round(total_vol,2),
        "pending_complaints": sum(1 for c in complaints if c.status=="Pending"),
    })

@app.route("/api/admin/users", methods=["GET"])
@admin_required
def admin_get_users():
    return jsonify([u.to_dict() for u in User.query.order_by(User.created_at.desc()).all()])

@app.route("/api/admin/users", methods=["POST"])
@admin_required
def admin_add_user():
    d = request.get_json()
    name   = clean(d.get("name",""),2,100)
    email  = clean(d.get("email",""),5,150)
    mobile = clean(d.get("mobile",""),7,20)
    pwd    = clean(d.get("password",""),6,100)
    try:    balance = float(d.get("balance",0))
    except: balance = 0.0
    acc_type = clean(d.get("account_type","Savings"),1,20) or "Savings"
    if not all([name,email,mobile,pwd]): return jsonify({"error":"Required fields missing"}), 400
    if User.query.filter_by(email=email.lower()).first(): return jsonify({"error":"Email already registered"}), 409
    slug = name.lower().replace(" ","")
    upi  = f"{slug}@nexabank"
    u = User(name=name, email=email.lower(), mobile=mobile, account_type=acc_type,
             account_number=gen_account_no(), upi_id=upi,
             balance=max(0.0,balance), referral_code=gen_referral_code())
    u.set_password(pwd)
    db.session.add(u)
    db.session.flush()
    add_notification(u.id, f"🎉 Welcome to NexaBank, {name}!")
    add_log("USER_CREATED", f"Admin created account for {name}", ip=request.remote_addr, user_type="admin")
    db.session.commit()
    return jsonify({"success":True,"user":u.to_dict()}), 201

@app.route("/api/admin/users/<int:uid>/toggle", methods=["POST"])
@admin_required
def admin_toggle_user(uid):
    u = User.query.get_or_404(uid)
    u.status = "suspended" if u.status=="active" else "active"
    db.session.commit()
    return jsonify({"success":True,"status":u.status})

@app.route("/api/admin/users/<int:uid>", methods=["DELETE"])
@admin_required
def admin_delete_user(uid):
    u = User.query.get_or_404(uid)
    db.session.delete(u); db.session.commit()
    return jsonify({"success":True})

@app.route("/api/admin/users/<int:uid>/balance", methods=["POST"])
@admin_required
def admin_edit_balance(uid):
    u = User.query.get_or_404(uid)
    d = request.get_json()
    action = d.get("action","deposit")
    try:    amount = float(d.get("amount",0))
    except: return jsonify({"error":"Invalid amount"}), 400
    if amount <= 0: return jsonify({"error":"Amount must be > 0"}), 400
    if action == "deposit":
        u.balance = round(u.balance + amount, 2)
    else:
        if amount > u.balance: return jsonify({"error":"Cannot withdraw more than balance"}), 400
        u.balance = round(u.balance - amount, 2)
    add_notification(u.id, f"💰 Admin {'deposited' if action=='deposit' else 'withdrew'} ₹{amount:,.0f}")
    add_log(f"BALANCE_{action.upper()}", f"Admin {action}ed ₹{amount} for {u.name}",
            ip=request.remote_addr, user_type="admin")
    db.session.commit()
    return jsonify({"success":True,"new_balance":u.balance})

@app.route("/api/admin/transactions")
@admin_required
def admin_get_txs():
    txs = Transaction.query.order_by(Transaction.created_at.desc()).all()
    return jsonify([t.to_dict() for t in txs])

@app.route("/api/admin/complaints", methods=["GET"])
@admin_required
def admin_get_complaints():
    return jsonify([c.to_dict() for c in Complaint.query.order_by(Complaint.created_at.desc()).all()])

@app.route("/api/admin/complaints/<int:cid>", methods=["POST"])
@admin_required
def admin_update_complaint(cid):
    c = Complaint.query.get_or_404(cid)
    d = request.get_json()
    c.status         = clean(d.get("status","Pending"),1,20) or c.status
    c.admin_response = clean(d.get("response",""),0,1000) or c.admin_response
    db.session.commit()
    return jsonify({"success":True})

@app.route("/api/admin/logs")
@admin_required
def admin_get_logs():
    logs = SystemLog.query.order_by(SystemLog.created_at.desc()).limit(500).all()
    return jsonify([l.to_dict() for l in logs])

@app.route("/api/admin/loyalty/bulk", methods=["POST"])
@admin_required
def bulk_loyalty():
    d = request.get_json()
    ids    = d.get("user_ids",[])
    points = int(d.get("points",0))
    if not ids or points <= 0: return jsonify({"error":"Missing fields"}), 400
    for uid in ids:
        u = User.query.get(uid)
        if u:
            u.loyalty_points += points
            add_notification(uid, f"🎁 +{points} loyalty points awarded by admin!")
    db.session.commit()
    return jsonify({"success":True})

# ── SECURITY HEADERS ──────────────────────────────────────────────────────────
@app.after_request
def security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"]         = "DENY"
    resp.headers["X-XSS-Protection"]        = "1; mode=block"
    resp.headers["Referrer-Policy"]          = "strict-origin-when-cross-origin"
    return resp

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG")=="1")
