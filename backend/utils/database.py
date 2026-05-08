# Shared database, storage, and environment config
from motor.motor_asyncio import AsyncIOMotorClient
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional
import os
import requests
import resend

ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / '.env')

# Iter 216o-4 — In dev/preview, the Kubernetes pod ships with stub
# placeholders for STRIPE_*  (e.g. STRIPE_API_KEY=sk_test_emergent).
# load_dotenv() defaults to override=False, so the pod stub wins over
# our real keys in /app/backend/.env. Explicitly re-load STRIPE_* with
# override=True so the .env file is the source of truth for Stripe in
# every environment. Production deploys that set real STRIPE_API_KEY
# via the platform env will continue to work — those values will be in
# the .env file too.
from dotenv import dotenv_values  # noqa: E402
_env_file = dotenv_values(ROOT_DIR / '.env')
for _k, _v in _env_file.items():
    if _k.startswith('STRIPE_') and _v:
        os.environ[_k] = _v

# MongoDB
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Environment variables
EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY')
STRIPE_API_KEY = os.environ.get('STRIPE_API_KEY')
STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET')
STRIPE_PRICE_STARTER = os.environ.get('STRIPE_PRICE_STARTER')
STRIPE_PRICE_PRO = os.environ.get('STRIPE_PRICE_PRO')
STRIPE_PRICE_ENTERPRISE = os.environ.get('STRIPE_PRICE_ENTERPRISE')
# Iter 215be — new flexible pricing model. Each Stripe Price ID lives in
# the dashboard and is stamped here from /app/backend/.env. The bundle
# (GymAxis Pro) costs £150/mo for 1 site; the per-site add-on costs £50/mo
# and is sent as a quantity-based line item so Stripe handles proration
# automatically when sites are added/removed mid-cycle.
STRIPE_PRICE_GYMAXIS_PRO   = os.environ.get('STRIPE_PRICE_GYMAXIS_PRO')
STRIPE_PRICE_SITE_ADDON    = os.environ.get('STRIPE_PRICE_SITE_ADDON')
STRIPE_PRICE_MEMBERSHIPS   = os.environ.get('STRIPE_PRICE_MEMBERSHIPS')
STRIPE_PRICE_CRM           = os.environ.get('STRIPE_PRICE_CRM')
STRIPE_PRICE_MARKETING     = os.environ.get('STRIPE_PRICE_MARKETING')
STRIPE_PRICE_OPERATIONS    = os.environ.get('STRIPE_PRICE_OPERATIONS')
RESEND_API_KEY = os.environ.get('RESEND_API_KEY')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', 'onboarding@resend.dev')
JWT_SECRET = os.environ.get('JWT_SECRET')
JWT_ALGORITHM = os.environ.get('JWT_ALGORITHM', 'HS256')

# Initialize Resend
if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY

# Object Storage
STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
APP_NAME = "gymaxis-ai"
storage_key: Optional[str] = None


def init_storage() -> str:
    global storage_key
    if storage_key:
        return storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_LLM_KEY}, timeout=30)
    resp.raise_for_status()
    storage_key = resp.json()["storage_key"]
    return storage_key


def put_object(path: str, data: bytes, content_type: str) -> dict[str, str]:
    key = init_storage()
    resp = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data, timeout=120
    )
    resp.raise_for_status()
    return resp.json()


def get_object(path: str) -> tuple[bytes, str]:
    key = init_storage()
    resp = requests.get(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key}, timeout=60
    )
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")
