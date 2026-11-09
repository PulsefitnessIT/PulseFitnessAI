# Iteration 293: ONE real email send to TEST_RECIPIENT_EMAIL + read-only Resend domains check. Never prints the key.
import asyncio, os, sys, requests
sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")


async def main():
    to = os.environ["TEST_RECIPIENT_EMAIL"]
    from utils.email import send_email
    from utils.database import db, RESEND_API_KEY
    print("key present:", bool(RESEND_API_KEY))
    # domains (read-only)
    r = requests.get("https://api.resend.com/domains", headers={"Authorization": f"Bearer {RESEND_API_KEY}"}, timeout=20)
    print("domains status:", r.status_code)
    if r.status_code == 200:
        for d in r.json().get("data", []):
            print("  domain:", d.get("name"), d.get("status"))
    else:
        print("  body:", r.text[:200])
    if "--send" not in sys.argv:
        return
    res = await send_email(to=to, subject="MODService email key check",
                           html="<p>Test from MODService preview</p>",
                           kind="system.ops_alert", category="mod")
    print("send_email returned truthy:", bool(res))
    ev = await db.email_send_events.find({"to": to}, {"_id": 0, "payload": 0}).sort("created_at", -1).limit(1).to_list(1)
    if ev:
        e = ev[0]
        print("newest event status:", e.get("status"), "| sender:", e.get("sender"), "| kind:", e.get("kind"),
              "| subject:", e.get("subject"), "| error:", (e.get("error") or "")[:200])

asyncio.run(main())
