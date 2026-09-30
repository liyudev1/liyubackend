from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.db import transaction
from .models import Profile, CategoryModel, ProductImage, ProductItem, Order, ContactUs

User = get_user_model()   

class UserSerializer(serializers.ModelSerializer):
    phone = serializers.CharField(write_only=True, required=False)
    is_delivery = serializers.BooleanField(write_only=True, required=False)
    chat_id = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password', 'phone', 'is_delivery', 'chat_id']
        extra_kwargs = {
            "password": {"write_only": True}
        }

    def create(self, validated_data):
        phone = validated_data.pop("phone", None)
        # Profile.is_delivery is NOT NULL, so passing None when the client omits it
        # made the Profile insert fail and left a user without a Profile.
        is_delivery = validated_data.pop("is_delivery", False)
        chat_id = validated_data.pop("chat_id", None)

        # all or nothing: never keep a user whose Profile could not be created
        with transaction.atomic():
            user = User.objects.create_user(**validated_data)

            # Create profile with phone
            Profile.objects.create(
                user=user,
                phone=phone,
                is_delivery=is_delivery,
                chat_id=chat_id
            )
        return user



class ProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    class Meta:
        model = Profile
        fields = '__all__'

from rest_framework import serializers
from .models import CategoryModel

class CategorySerializer(serializers.ModelSerializer):
    category = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = CategoryModel
        fields = "__all__"

    def to_representation(self, instance):
        # Every product carries its category, and there are only a few categories.
        # Build each one once per request instead of once per product.
        cache = self.context.setdefault("_category_cache", {})
        if instance.pk in cache:
            return cache[instance.pk]

        data = super().to_representation(instance)

        # The ImageField already returned an absolute URL when a request is in the
        # context, so there is no need to call instance.image.url (storage work) again.
        if data.get("image"):
            data["image"] = data["image"].replace("http://", "https://")

        cache[instance.pk] = data
        return data



class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = "__all__"

class ProductItemSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True,read_only=True)
    category = CategorySerializer(read_only=True)
    class Meta:
        model = ProductItem
        fields = "__all__"

class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = '__all__'

class ContactUsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactUs
        fields = "__all__"
