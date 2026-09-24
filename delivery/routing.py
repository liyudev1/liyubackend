from django.urls import path 
from . import consumers


websocket_urlpatterns = [
        path('ws/livestatus/<str:room_name>/', consumers.OrderStatusMonitor.as_asgi()),
]