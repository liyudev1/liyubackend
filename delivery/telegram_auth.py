"""
telegram_auth.py — verifies Telegram Mini App identity and links it to a Profile.

Why this exists
---------------
A chat_id sent as plain JSON from the browser can be faked, which would let
someone point their account at another person's Telegram and receive that
person's order messages. Telegram signs `Telegram.WebApp.initData` with your
bot token, so the backend can prove the id is real.

Setup
-----
Set TELEGRAM_BOT_TOKEN in your .env to the token of the bot that OPENS the
Mini App (Liyu_delivery_bot). A signature made by one bot can't be verified
with another bot's token.

Used by
-------
  auth_views.py  — LoginView / CreateUserView
  consumers.py   — "save_chat_id" WebSocket message (already-logged-in users)
"""

import hashlib
import hmac
import json
import logging
import time
from urllib.parse import parse_qsl

from django.db.models import Q
from environ import Env

from .models import Profile

logger = logging.getLogger(__name__)

env = Env()
Env.read_env()

# initData older than this is rejected (replay protection).
INIT_DATA_MAX_AGE_SECONDS = 24 * 60 * 60


def verify_init_data(init_data: str):
    """
    Return the Telegram `user` dict if init_data is genuinely signed by
    Telegram for our bot and still fresh. Otherwise return None.
    """
    if not init_data:
        return None

    bot_token = env("TELEGRAM_BOT_TOKEN", default="")
    if not bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN is not set — cannot verify Telegram initData")
        return None

    try:
        fields = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    except ValueError:
        return None

    received_hash = fields.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        return None

    try:
        auth_date = int(fields.get("auth_date", "0"))
    except ValueError:
        return None
    if time.time() - auth_date > INIT_DATA_MAX_AGE_SECONDS:
        return None

    try:
        user = json.loads(fields.get("user", ""))
    except (TypeError, ValueError):
        return None

    return user if isinstance(user, dict) and "id" in user else None


def get_verified_chat_id(init_data: str):
    """Verified Telegram user id as a string, or None."""
    user = verify_init_data(init_data)
    return str(user["id"]) if user else None


def get_or_create_profile(user):
    """
    Profile.user is a ForeignKey, so get_or_create() can raise
    MultipleObjectsReturned if a user ever ends up with two profiles.
    Take the oldest one instead.
    """
    profile = Profile.objects.filter(user=user).order_by("id").first()
    return profile or Profile.objects.create(user=user)


def link_chat_id_to_profile(profile, chat_id: str) -> bool:
    """
    Store chat_id on the profile ONLY if the profile has none yet, and no
    other profile already uses it. Never overwrites an existing value.

    Returns True when the profile ends up linked to this chat_id.
    """
    if not chat_id:
        return False

    # one Telegram account -> one profile, so messages can't leak across accounts
    if Profile.objects.filter(chat_id=chat_id).exclude(pk=profile.pk).exists():
        return False

    # the filter makes this atomic: only a still-empty profile gets updated
    updated = (
        Profile.objects
        .filter(pk=profile.pk)
        .filter(Q(chat_id__isnull=True) | Q(chat_id=""))
        .update(chat_id=chat_id)
    )
    if updated:
        profile.chat_id = chat_id
        return True

    return Profile.objects.filter(pk=profile.pk, chat_id=chat_id).exists()
