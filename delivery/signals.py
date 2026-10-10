"""
order_notifications.py — Telegram messages when an Order's status changes.

Customer         -> told when the order is confirmed, delivered or cancelled.
Delivery person  -> told when an order is assigned to them (confirmed), and when
                    it is later delivered or cancelled.

New-order and cancel messages to the admin chats stay in views.py (CreateOrder /
CancelOrder), so nothing is sent twice.

Wire it up by importing this module once when Django starts, in apps.py:

    def ready(self):
        from . import order_notifications  # noqa: F401

(or paste the contents into your existing signals.py).

Signals only fire on .save(). Order.objects.filter(...).update(status=...) and
bulk_update() skip them, so status changes must go through order.save().
"""

import logging
import threading

from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Order, Profile
from .send_message import send_telegram_message

logger = logging.getLogger(__name__)


# ── helpers ───────────────────────────────────────────────────────────────────

def _md(value) -> str:
    """Escape Telegram Markdown characters so a name like 'abel_k' can't break the message."""
    text = "" if value is None else str(value)
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, "\\" + ch)
    return text


def _delivery_profile(order):
    """Order.delivery_person holds the delivery Profile's id as a string."""
    value = (order.delivery_person or "").strip()
    if not value.isdigit():
        return None
    return Profile.objects.filter(pk=int(value)).first()


def _send_async(messages):
    """
    Send in a background thread so a slow Telegram API never delays the order request,
    and swallow errors so a failed message can never break saving an order.
    """
    def run():
        for chat_id, text in messages:
            try:
                send_telegram_message(text, chat_id)
            except Exception:
                logger.exception("Could not send Telegram message to chat %s", chat_id)

    threading.Thread(target=run, daemon=True).start()


# ── message texts ─────────────────────────────────────────────────────────────

def _customer_text(order):
    num = _md(order.order_number)
    if order.status == "confirmed":
        return (
            f"✅ *Order accepted*\n\n"
            f"Your order *{num}* was accepted and a delivery person is on the way."
        )
    if order.status == "delivered":
        return (
            f"📦 *Order delivered*\n\n"
            f"Your order *{num}* has been delivered. Enjoy your meal!"
        )
    if order.status == "cancelled":
        return (
            f"❌ *Order cancelled*\n\n"
            f"Your order *{num}* was cancelled."
        )
    return None


def _delivery_assigned_text(order):
    return (
        f"🛵 *Order assigned to you*\n\n"
        f"🔖 *Order:* {_md(order.order_number)}\n"
        f"👤 *Customer:* {_md(order.owner.user.username)}\n"
        f"📞 *Phone:* {_md(order.owner.phone)}\n"
        f"📍 *Address:* {_md(order.shipping_address)}\n"
        f"📦 *Items:* {order.item_count}\n"
        f"💰 *Total:* {order.total_price} Birr"
    )


def _delivery_status_text(order):
    num = _md(order.order_number)
    if order.status == "delivered":
        return f"✅ *Order delivered*\n\nOrder *{num}* is marked as delivered. Thank you!"
    if order.status == "cancelled":
        return f"❌ *Order cancelled*\n\nOrder *{num}* was cancelled. No delivery is needed."
    return None


# ── signals ───────────────────────────────────────────────────────────────────

@receiver(pre_save, sender=Order)
def remember_old_order_state(sender, instance, **kwargs):
    """Keep the status and delivery person from before this save, so post_save can see what changed."""
    instance._order_old = None
    if instance.pk:
        instance._order_old = (
            Order.objects.filter(pk=instance.pk)
            .values("status", "delivery_person")
            .first()
        )


@receiver(post_save, sender=Order)
def notify_order_status(sender, instance, created, **kwargs):
    old = getattr(instance, "_order_old", None)
    if created or not old:
        return  # new orders are announced by CreateOrder in views.py

    status_changed = old["status"] != instance.status
    delivery_changed = bool(instance.delivery_person) and old["delivery_person"] != instance.delivery_person
    if not status_changed and not delivery_changed:
        return

    messages = []

    # customer: only when the status changes
    if status_changed:
        customer_text = _customer_text(instance)
        if customer_text and instance.owner.chat_id:
            messages.append((instance.owner.chat_id, customer_text))

    # delivery person: assignment, or a later delivered / cancelled
    rider = _delivery_profile(instance)
    if rider and rider.chat_id:
        if status_changed and instance.status == "confirmed":
            messages.append((rider.chat_id, _delivery_assigned_text(instance)))
        elif status_changed:
            rider_text = _delivery_status_text(instance)
            if rider_text:
                messages.append((rider.chat_id, rider_text))
        elif delivery_changed and instance.status == "confirmed":
            # reassigned to a new rider without a status change
            messages.append((rider.chat_id, _delivery_assigned_text(instance)))

    if messages:
        # send only after the database transaction is committed
        transaction.on_commit(lambda: _send_async(messages))
