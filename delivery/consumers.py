from channels.generic.websocket import AsyncWebsocketConsumer
import json
from channels.db import database_sync_to_async
from .serializers import OrderSerializer
from .send_message import send_telegram_message
from environ import Env
from django.db.models import Q


env = Env()

Env.read_env()

class OrderStatusMonitor(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = f'status_{self.room_name}'
        
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        print(f"WebSocket connected for room: {self.room_name}")
        
    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        print(f"WebSocket disconnected for room: {self.room_name}")
        
    async def receive(self, text_data):
        from .models import Order,Profile
        try:
            text_data_json = json.loads(text_data)
            print(f"Received from client: {text_data_json}")

            message_type = text_data_json.get('type')
            print("message type",message_type)
            data = text_data_json.get('data', {})
            owner_profile = self.scope['user']
            delivery_profiles = await database_sync_to_async(
                lambda: Profile.objects.filter(Q(is_delivery=True) | Q(user__is_superuser=True))
            )()
            if message_type == 'status_update':
                
                if 'order_id' in data and 'status' in data:
                    try:
                        order = await database_sync_to_async(Order.objects.get)(id=data["order_id"])
                        order.status = data["status"]
                        
                        if 'person' in data:
                            order.delivery_person = data["person"]
                        
                        await database_sync_to_async(order.save)()

                        order_serialized = OrderSerializer(order)
                        await self.channel_layer.group_send(
                            self.room_group_name,
                            {
                                'type': 'status_update',
                                'data': order_serialized.data
                            }
                        )
                        
                    except Order.DoesNotExist:
                        print(f"Order with id {data.get('order_id')} does not exist")
                    except Exception as e:
                        print(f"Error updating order: {e}")
            
            elif message_type == 'add_order':
                print("no way")
                print("TEST 1 FROM C")
                items = data["items"]
                total_price = data["total_price"]
                address = data["address"]
                special_instraction = data["special_instraction"]
                item_count = data["item_count"]
                username = await database_sync_to_async(lambda: owner_profile.user.username)()
                phone = await database_sync_to_async(lambda: owner_profile.phone)()

                # Create order correctly with Profile
                order = await database_sync_to_async(Order.objects.create)(
                    item_count=item_count,
                    owner=owner_profile,
                    items=items,
                    total_price=total_price,
                    shipping_address=address,
                    special_instraction=special_instraction
                )
                # Broadcast new order to group
                order_serialized = OrderSerializer(order)
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'add_order',
                        'data': order_serialized.data
                    }
                )
                # Build item details for Telegram
                items_details = ""
                for item in items:
                    item_name = item.get("name", "Unknown Item")
                    quantity = item.get("quantity", 1)
                    price = item.get("price", 0)

                    category_data = item.get("category", {})
                    category_name = category_data.get("name", "Unknown Category") if isinstance(category_data, dict) else str(category_data)

                    items_details += f"• {item_name} - Qty: {quantity} - Price: {price} Birr - Location: {category_name}\n"

                CHAT_ID = env("TELEGRAM_CHAT_ID")  
                ADMIN_CHAT_ID = env("TELEGRAM_ADMIN_CHAT_ID")
                id_list = [CHAT_ID, ADMIN_CHAT_ID]

                for id in id_list:
                    message = f"""
            🛒 *NEW ORDER RECEIVED*

            👤 *Customer:* {username}
            📞 *Phone:* {phone}
            📍 *Delivery Address:* {address}

            📋 *ORDER ITEMS:*
            {items_details}
            📊 *Item Count:* {item_count}
            💰 *Total Amount:* {total_price} Birr
            📝 *Special Instructions:* {special_instraction}

            ⏰ *Action required immediately*
                    """

                    send_telegram_message(message, id)
            elif message_type == "cancel_order":
                if 'order_id' in data and 'status' in data:
                    try:
                        order = await database_sync_to_async(Order.objects.get)(id=data["order_id"])
                        order.status = data["status"]

                        await database_sync_to_async(order.save)()
                        order_serialized = OrderSerializer(order)
                        await self.channel_layer.group_send(
                            self.room_group_name,
                            {
                                'type': 'status_update',
                                'data': order_serialized.data
                            }
                        )
                        username = await database_sync_to_async(lambda: order.owner.user.username)()
                        phone = await database_sync_to_async(lambda: order.owner.phone)()
                        
                        # FIXED: Get delivery profiles properly in async context
                        delivery_profiles = await database_sync_to_async(list)(
                            Profile.objects.filter(Q(is_delivery=True) | Q(user__is_superuser=True))
                        )
                        
                        CHAT_ID = env("TELEGRAM_CHAT_ID")  
                        ADMIN_CHAT_ID = env("TELEGRAM_ADMIN_CHAT_ID")
                        
                        # Build the ID list properly
                        id_list = [CHAT_ID, ADMIN_CHAT_ID] + [
                            profile.chat_id for profile in delivery_profiles if profile.chat_id
                        ]
                        
                        for chat_id in id_list:
                            if chat_id:  # Only send if chat_id exists
                                message = f"""
                    🛒 *ORDER CANCELED*

                    👤 *Customer:* {username}
                    📦 *Items:* {order.item_count}
                    💰 *Total:* {order.total_price} Birr
                    📍 *Address:* {order.shipping_address}
                    📞 *Phone:* {phone}

                    ⏰ *Action required immediately*
                            """
                                send_telegram_message(message, chat_id)
                                
                    except Order.DoesNotExist:
                        print(f"Order with id {data.get('order_id')} does not exist")
                    except Exception as e:
                        print(f"Error updating order: {e}")
            elif 'text-message' in text_data_json:
                print(f"Test message received: {text_data_json['text-message']}")
                
                await self.send(text_data=json.dumps({
                    'type': 'connection_ack',
                    'message': 'WebSocket connection established successfully'
                }))
            else:
                print(f"Unknown message format: {text_data_json}")

        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")
        except Exception as e:
            print(f"Error in receive method: {e}")
            
    async def status_update(self, event):

        try:
            await self.send(text_data=json.dumps({
                'type': 'status_update',
                'data': event['data']
            }))
        except Exception as e:
            print(f"Error sending status update: {e}")
    async def add_order(self, event):

        try:
            await self.send(text_data=json.dumps({
                'type': 'add_order',
                'data': event['data']
            }))
        except Exception as e:
            print(f"Error sending status update: {e}")
