# NexaBank — Secure Flask Version

Rebuilt from your original bank.html with all vulnerabilities fixed.

## Vulnerabilities Fixed

| Original (Insecure)                     | This Version (Secure)                        |
|-----------------------------------------|----------------------------------------------|
| Hardcoded `sidharth@2007` in JS         | Stored in `.env` — never in source code      |
| Client-side JS auth (bypassable)        | Server-side Flask auth — cannot be bypassed  |
| Passwords visible in localStorage       | bcrypt hashed in SQLite database             |
| All data in localStorage                | SQLite database with proper models           |
| No session management                   | JWT in HTTP-only cookies (JS can't steal)    |
| No CSRF protection                      | Flask-WTF CSRF on every POST request         |
| No rate limiting                        | 5 admin attempts/min, 10 user/min            |
| No input validation                     | Server-side validation on all endpoints      |
| No security headers                     | X-Frame-Options, XSS-Protection added        |

## Setup

```bash
# 1. Install Python from python.org — check "Add to PATH"

# 2. Create virtual environment
python -m venv venv

# 3. Activate
venv\Scripts\activate       # Windows
source venv/bin/activate    # Mac/Linux

# 4. Install packages
pip install -r requirements.txt

# 5. Run
python app.py
```

Open http://localhost:5000

## Features (matching original bank.html)

### User Pages
- Dashboard, Account Details, Cards, Virtual Cards
- Spending Analytics, Loyalty Points
- Savings Goals, Budget Planner, Investments
- Recurring Payments, Money Requests, Referral
- Security & 2FA, Receipts, Exchange Rates, AI Advice
- UPI Transfer, Bill Payments, Mobile Recharge
- Loans, Bank Transfer, Transactions, Complaints

### Admin Pages (35+ pages)
- Dashboard with security vulnerability summary
- Revenue, User Analytics, Transaction Reports, Audit Logs
- Suspicious Activity, Fraud Detection, Security Settings
- Manage Users, Add User, Segmentation, Bulk Loyalty, KYC
- Balance Management, Disputes, Rate Management
- Bulk Messaging, Support Tickets, Announcements
- System Health, Data Export, System/Security Logs
- Campaigns, Achievements

## Burp Suite Testing
Since this app makes real HTTP requests you can now intercept:
```
POST /api/admin/login  → {"username":"sidharth","password":"..."}
POST /api/user/login   → {"email":"...","password":"..."}
POST /api/user/transfer → {"receiver_id":2,"amount":5000}
```
Security behaviors to test:
- Rate limit: >5 admin logins/min → 429 error
- CSRF: Remove X-CSRFToken header → 400 error
- JWT cookie: Try reading in console → undefined (HTTP-only)
- Auth bypass: Try accessing /api/user/me without login → 401
