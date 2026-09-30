from .models import Profile
from rest_framework.views import APIView
from django.core.exceptions import FieldDoesNotExist
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.response import Response
from rest_framework.generics import ListAPIView,CreateAPIView,RetrieveAPIView
from rest_framework.permissions import IsAuthenticated,AllowAny
from rest_framework.pagination import PageNumberPagination
from .serializers import ProductItemSerializer,CategorySerializer,OrderSerializer,UserSerializer,ProfileSerializer,ContactUsSerializer
from .models import ProductItem,CategoryModel,Order,ContactUs
from .send_message import send_telegram_message
from environ import Env

env = Env()

Env.read_env()


def product_queryset():
    """
    Products with their related rows loaded up front.

    Without select_related / prefetch_related, the serializer runs extra
    database queries for every single product (category, images), which is
    what makes /list-product/ slow when the database is not on the same machine.
    """
    # the category serializer prints the category's parent, so load it in the same query
    related = ["category"]
    try:
        if CategoryModel._meta.get_field("category").is_relation:
            related.append("category__category")
    except FieldDoesNotExist:
        pass

    qs = ProductItem.objects.select_related(*related)
    try:
        # only prefetch if "images" really is a relation on the model
        ProductItem._meta.get_field("images")
        qs = qs.prefetch_related("images")
    except FieldDoesNotExist:
        pass
    return qs


class ProductPagination(PageNumberPagination):
    """
    Opt-in pagination: /list-product/ still returns the full plain list unless
    the request has a ?page= parameter, so existing callers keep working.

    Paginated response: {"count": N, "next": url|null, "previous": url|null, "results": [...]}
    """
    page_size = 24
    page_size_query_param = "page_size"
    max_page_size = 100

    def paginate_queryset(self, queryset, request, view=None):
        if "page" not in request.query_params:
            return None
        return super().paginate_queryset(queryset, request, view)


class CreateUserView(CreateAPIView):
    serializer_class = UserSerializer
    permission_classes = [AllowAny]
    queryset  = User.objects.all()

class ListProduct(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ProductItemSerializer
    pagination_class = ProductPagination

    def get_queryset(self):
        params = self.request.query_params
        qs = product_queryset()

        # optional filters: ?category=Food&search=pizza
        category = params.get("category")
        if category:
            qs = qs.filter(category__name__iexact=category.strip())

        search = params.get("search")
        if search and search.strip():
            qs = qs.filter(name__icontains=search.strip())

        # ?ordering=id gives oldest first; default stays newest first
        return qs.order_by("id" if params.get("ordering") == "id" else "-id")

class ListCategory(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CategorySerializer
    queryset = CategoryModel.objects.all()
    
class ListFilterProduct(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ProductItemSerializer
    
    def get_queryset(self):
        category_id = self.request.query_params.get('category_id')
        if not category_id:
            return ProductItem.objects.none()
        category = get_object_or_404(CategoryModel, id=category_id)
        return product_queryset().filter(category=category)

class ListFilterCategory(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CategorySerializer
    
    def get_queryset(self):
        category_id = self.request.query_params.get('category_id')
        if not category_id:
            return CategoryModel.objects.none()
        category = get_object_or_404(CategoryModel, id=category_id)
        return CategoryModel.objects.filter(category=category)

class GetProduct(APIView):
    def get(self,request,**kwargs):
        product_slug = kwargs.get("slug")
        product = get_object_or_404(product_queryset(), slug=product_slug)
        product_serializers = ProductItemSerializer(product)
        return Response(product_serializers.data,status=status.HTTP_200_OK)

class CreateOrder(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, **kwargs):
        owner = get_object_or_404(Profile, user=request.user)
        items = request.data["items"]
        total_price = request.data["total_price"]
        address = request.data["address"]
        special_instraction = request.data["special_instraction"]
        item_count = request.data["item_count"]

        Order.objects.create(
            item_count=item_count,
            owner=owner,
            items=items,
            total_price=total_price,
            shipping_address=address,
            special_instraction=special_instraction
        )
        

        items_details = ""
        for item in items:
            item_name = item.get("name", "Unknown Item")
            quantity = item.get("quantity", 1)
            price = item.get("price", 0)

            category_data = item.get("category", {})
            if isinstance(category_data, dict):
                category_name = category_data.get("name", "Unknown Category")
            else:
                category_name = str(category_data)
            
            items_details += f"• {item_name} - Qty: {quantity} - Price: {price} Birr - Location: {category_name}\n"
        
        CHAT_ID = env("TELEGRAM_CHAT_ID")  
        ADMIN_CHAT_ID = env("TELEGRAM_ADMIN_CHAT_ID")
        id_list = [CHAT_ID, ADMIN_CHAT_ID]
        
        for id in id_list:
            message = f"""
🛒 *NEW ORDER RECEIVED*

👤 *Customer:* {owner.user.username}
📞 *Phone:* {owner.phone}
📍 *Delivery Address:* {address}

📋 *ORDER ITEMS:*
{items_details}
📊 *Item Count:* {item_count}
💰 *Total Amount:* {total_price} Birr
📝 *Special Instructions:* {special_instraction}

⏰ *Action required immediately*
            """

            send_telegram_message(message, id)
        return Response(status=status.HTTP_201_CREATED)

class GetOrders(APIView):
    permission_classes = [IsAuthenticated]

    def get(self,request,**kwargs):
        owner = get_object_or_404(Profile, user=request.user)
        my_orders = Order.objects.filter(owner=owner)
        order_serializer = OrderSerializer(my_orders,many=True)
        return Response(order_serializer.data,status=status.HTTP_200_OK)

class GetOrdersForMonitor(APIView):
    permission_classes = [IsAuthenticated]
    def get(self,request,**kwargs):
        person = get_object_or_404(Profile, user=request.user)
        if person.user.is_superuser:
            my_orders = Order.objects.all()
        elif person.is_delivery:
            my_orders = Order.objects.filter(status="pending")
            my_orders = my_orders.union(Order.objects.filter(status="confirmed",delivery_person=f"{person.id}"))
            my_orders = my_orders.union(Order.objects.filter(status="delivered",delivery_person=f"{person.id}"))
        else:
            # previously this response was created but not returned,
            # which crashed with an unbound variable (HTTP 500)
            return Response(status=status.HTTP_403_FORBIDDEN)

        order_serializer = OrderSerializer(my_orders,many=True)
        return Response(order_serializer.data,status=status.HTTP_200_OK)

class GetDeliveryInfo(APIView):
    permission_classes = [IsAuthenticated]
    def get(self,request):
        profile = get_object_or_404(Profile, user=request.user)
        data = {"is_delivery":profile.is_delivery,"person":f"{profile.id}","is_admin":profile.user.is_superuser}
        return Response(data=data)

class GetProfile(RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ProfileSerializer
    def get_object(self):
        try:
            return Profile.objects.get(user=self.request.user)
        except Profile.DoesNotExist:
            raise Http404("Profile does not exist")
        
class SaveToken(APIView):
    def post(self,*args, **kwargs):
        token = self.request.data.get("token")
        if self.request.user.is_authenticated:
            profile = get_object_or_404(Profile, user=self.request.user)
            profile.notification_token = token
            profile.save()
            return Response(status=status.HTTP_202_ACCEPTED)
        return Response(status=status.HTTP_403_FORBIDDEN)

class GetAdminToken(APIView):
    def get(self,*args, **kwargs):
        admin = User.objects.get(username="root")
        profile = Profile.objects.get(user=admin)
        if profile:
            # NOTE: send_to_token is not imported in this file, so this line
            # raises NameError. Import it from wherever it is defined.
            send_to_token(
                token=profile.notification_token,
                title="Hello from Python",
                body="This is a test notification",
                data={"key1": "value1", "key2": "value2"}
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

class CancelOrder(APIView):
    def get(self,*args, **kwargs):
        order_id = kwargs.get("order_id")
        order = get_object_or_404(Order, id=order_id)
        if order.status == "pending":
            order.status = "cancelled"
            order.save()
            CHAT_ID = env("TELEGRAM_CHAT_ID")  
            ADMIN_CHAT_ID = env("TELEGRAM_ADMIN_CHAT_ID")
            id_list = [CHAT_ID,ADMIN_CHAT_ID]
            for id in id_list:
                message = f"""
🛒 *ORDER CANCELED*

👤 *Customer:* {order.owner.user.username}
📦 *Items:* {order.item_count}
💰 *Total:* {order.total_price} Birr
📍 *Address:* {order.shipping_address}
   *Phone:* {order.owner.phone}

⏰ *Action required immediately*
        """

                send_telegram_message(message,id)
            return Response(status=status.HTTP_200_OK) 
        return Response(status=status.HTTP_204_NO_CONTENT)
    
class CreateContactUsView(CreateAPIView):
    serializer_class = ContactUsSerializer
    permission_classes = [IsAuthenticated]
    queryset  = ContactUs.objects.all()
