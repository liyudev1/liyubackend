from django.urls import path
from .views import CreateUserView,ListProduct,ListCategory,GetProduct,CreateOrder,GetOrders,ListFilterCategory,ListFilterProduct,GetProfile,SaveToken,GetAdminToken,CancelOrder,CreateContactUsView,GetOrdersForMonitor,GetDeliveryInfo


urlpatterns = [
    path("create-user/",CreateUserView.as_view(),name="create-user"),
    path("list-product/",ListProduct.as_view(),name="list-product"),
    path("list-category/",ListCategory.as_view(),name="list-category"),
    path("product-detail/<slug:slug>/",GetProduct.as_view(),name="list-category"),
    path("create-order/",CreateOrder.as_view(),name="create-order"),
    path("get-orders/",GetOrders.as_view(),name="get-orders"),
    path("get-orders-monitor/",GetOrdersForMonitor.as_view(),name="get-orders-for-monitor"),
    path("sub-products/",ListFilterProduct.as_view(),name="sub-products"),
    path("sub-categorys/",ListFilterCategory.as_view(),name="sub-categorys"),
    path("get-profile/",GetProfile.as_view(),name="get-profile"),
    path("save-token/",SaveToken.as_view(),name="save-token"),
    path("get-token/",GetAdminToken.as_view(),name="get-token"),
    path("cancel-order/<int:order_id>/",CancelOrder.as_view(),name="cancel-view"),
    path("contact-us/",CreateContactUsView.as_view(),name="contact-us"),
    path("get-delivery-info/",GetDeliveryInfo.as_view(),name="get-delivery-info")
]
