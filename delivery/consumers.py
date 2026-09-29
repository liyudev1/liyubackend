import asyncio
import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.db.models import Q
from environ import Env

from .serializers import OrderSerializer
from .send_message import send_telegram_message

logger = logging.getLogger(__name__)

env = Env()

Env.read_env()


@database_sync_to_async
def serialize_order(order):
    # serializing can touch related rows, so do it in a DB-safe thread
    return OrderSerializer(order).data


@database_sync_to_async
def is_staff_profile(profile):
    return bool(profile.is_delivery or profile.user.is_superuser)


@database_sync_to_async
def get_profile_info(profile):
    return profile.user.username, profile.phone


@database_sync_to_async
def get_delivery_chat_ids():
    from .models import Profile
    return list(
        Profile.objects
        .filter(Q(is_delivery=True) | Q(user__is_superuser=True))
        .values_list("chat_id", flat=True)
    )


def build_items_details(items):
    lines = []
    for item in items:
        item_name = item.get("name", "Unknown Item")
        quantity = item.get("quantity", 1)
        price = item.get("price", 0)

        category_data = item.get("category", {})
        if isinstance(category_data, dict):
            category_name = category_data.get("name", "Unknown Category")
        else:
            category_name = str(category_data)

        lines.append(
            f"• {item_name} - Qty: {quantity} - Price: {price} Birr - Location: {category_name}"
        )
    return "\n".join(lines)


class OrderStatusMonitor(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = f'status_{self.room_name}'

        # The middleware sets AnonymousUser when the token is missing, invalid,
        # expired, or the user has no Profile. Refuse those connections instead
        # of accepting them and failing later inside receive().
        user = self.scope.get("user")
        if user is None or isinstance(user, AnonymousUser):
            await self.close(code=4401)
            return

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def send_error(self, message):
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': message
        }))

    async def notify_telegram(self, message, chat_ids):
        """Send Telegram messages in worker threads so the event loop is never blocked."""
        async def send_one(chat_id):
            try:
                await asyncio.to_thread(send_telegram_message, message, chat_id)
            except Exception as e:
                logger.warning("Telegram send failed for %s: %s", chat_id, e)

        await asyncio.gather(*(send_one(c) for c in chat_ids if c))

    async def receive(self, text_data):
        from .models import Order
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type')
            data = text_data_json.get('data', {})
            profile = self.scope['user']

            if message_type == 'status_update':
                # only delivery people and admins may change order status
                if not await is_staff_profile(profile):
                    await self.send_error("You are not allowed to update orders")
                    return

                if 'order_id' in data and 'status' in data:
                    try:
                        order = await database_sync_to_async(Order.objects.get)(id=data["order_id"])
                    except Order.DoesNotExist:
                        await self.send_error("Order does not exist")
                        return

                    order.status = data["status"]
                    if 'person' in data:
                        order.delivery_person = data["person"]
                    await database_sync_to_async(order.save)()

                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            'type': 'status_update',
                            'data': await serialize_order(order)
                        }
                    )

            elif message_type == 'add_order':
                try:
                    items = data["items"]
                    total_price = data["total_price"]
                    address = data["address"]
                    special_instraction = data["special_instraction"]
                    item_count = data["item_count"]
                except KeyError as e:
                    await self.send_error(f"Missing field: {e.args[0]}")
                    return

                username, phone = await get_profile_info(profile)

                order = await database_sync_to_async(Order.objects.create)(
                    item_count=item_count,
                    owner=profile,
                    items=items,
                    total_price=total_price,
                    shipping_address=address,
                    special_instraction=special_instraction
                )

                # Broadcast new order to group
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'add_order',
                        'data': await serialize_order(order)
                    }
                )

                message = "\n".join([
                    "🛒 *NEW ORDER RECEIVED*",
                    "",
                    f"👤 *Customer:* {username}",
                    f"📞 *Phone:* {phone}",
                    f"📍 *Delivery Address:* {address}",
                    "",
                    "📋 *ORDER ITEMS:*",
                    build_items_details(items),
                    f"📊 *Item Count:* {item_count}",
                    f"💰 *Total Amount:* {total_price} Birr",
                    f"📝 *Special Instructions:* {special_instraction}",
                    "",
                    "⏰ *Action required immediately*",
                ])
                await self.notify_telegram(
                    message,
                    [env("TELEGRAM_CHAT_ID"), env("TELEGRAM_ADMIN_CHAT_ID")]
                )

            elif message_type == "cancel_order":
                if 'order_id' not in data:
                    return

                try:
                    order = await database_sync_to_async(Order.objects.get)(id=data["order_id"])
                except Order.DoesNotExist:
                    await self.send_error("Order does not exist")
                    return

                staff = await is_staff_profile(profile)
                is_owner = order.owner_id == profile.id
                if not (staff or (is_owner and order.status == "pending")):
                    await self.send_error("You cannot cancel this order")
                    return

                # the client no longer chooses the status for a cancel
                order.status = "cancelled"
                await database_sync_to_async(order.save)()

                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'status_update',
                        'data': await serialize_order(order)
                    }
                )

                username, phone = await database_sync_to_async(
                    lambda: (order.owner.user.username, order.owner.phone)
                )()
                delivery_chat_ids = await get_delivery_chat_ids()

                message = "\n".join([
                    "🛒 *ORDER CANCELED*",
                    "",
                    f"👤 *Customer:* {username}",
                    f"📦 *Items:* {order.item_count}",
                    f"💰 *Total:* {order.total_price} Birr",
                    f"📍 *Address:* {order.shipping_address}",
                    f"📞 *Phone:* {phone}",
                    "",
                    "⏰ *Action required immediately*",
                ])
                await self.notify_telegram(
                    message,
                    [env("TELEGRAM_CHAT_ID"), env("TELEGRAM_ADMIN_CHAT_ID")] + delivery_chat_ids
                )

            elif 'text-message' in text_data_json:
                await self.send(text_data=json.dumps({
                    'type': 'connection_ack',
                    'message': 'WebSocket connection established successfully'
                }))
            else:
                logger.warning("Unknown message format: %s", message_type)

        except json.JSONDecodeError as e:
            logger.warning("Error decoding JSON: %s", e)
            await self.send_error("Invalid JSON")
        except Exception:
            # log the full traceback and tell the client, so orders never fail silently
            logger.exception("Error in receive method")
            await self.send_error("Something went wrong, please try again")

    async def status_update(self, event):
        try:
            await self.send(text_data=json.dumps({
                'type': 'status_update',
                'data': event['data']
            }))
        except Exception as e:
            logger.warning("Error sending status update: %s", e)

    async def add_order(self, event):
        try:
            await self.send(text_data=json.dumps({
                'type': 'add_order',
                'data': event['data']
            }))
        except Exception as e:
            logger.warning("Error sending new order: %s", e)
