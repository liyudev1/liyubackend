from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.text import slugify
from django.conf import settings




class Profile(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    notification_token = models.CharField(max_length=500, null=True, blank=True)
    phone = models.CharField(max_length=15, blank=True, null=True)
    is_delivery = models.BooleanField(default=False, blank=True)
    chat_id = models.CharField(max_length=500, null=True, blank=True)

    def __str__(self):
        return f"test's Profile"


class CategoryModel(models.Model):
    name = models.CharField(max_length=50)
    type = models.CharField(max_length=50, null=True, blank=True)
    image = models.ImageField(upload_to="category_image", null=True, blank=True)
    note = models.CharField(max_length=50, null=True, blank=True)
    is_sub_category = models.BooleanField(default=False, blank=True)
    category = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='sub_categories'
    )

    def save(self, *args, **kwargs):
        self.name = self.name.capitalize()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class ProductImage(models.Model):
    image = models.ImageField(upload_to="category_images/")
    caption = models.CharField(max_length=100, blank=True, null=True)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    alt = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        ordering = ['order', 'created_at']

    def __str__(self):
        return f"{self.image}"


class ProductItem(models.Model):
    name = models.CharField(max_length=50)
    description = models.TextField(max_length=500, null=True, blank=True, default="product description")
    images = models.ManyToManyField(ProductImage)
    location = models.CharField(max_length=200)
    price = models.IntegerField(default=0)
    rate = models.DecimalField(max_digits=2, decimal_places=1, default=0.0)
    date_time = models.DateTimeField(auto_now_add=True)
    is_sub_category = models.BooleanField(default=False, blank=True)
    category = models.ForeignKey(CategoryModel, on_delete=models.CASCADE)
    slug = models.SlugField(unique=True, blank=True)
    delivery_fee = models.IntegerField(default=0)

    def save(self, *args, **kwargs):
        if not self.id:
            # First save to get an ID
            super().save(*args, **kwargs)

        # Now generate slug with the ID
        if not self.slug:  # Only set slug if it's empty
            self.slug = slugify(f'{self.name}_{self.id}')

        # Save again with the slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Order(models.Model):
    ORDER_STATUS = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]
    owner = models.ForeignKey(Profile, on_delete=models.CASCADE)
    special_instraction = models.TextField(max_length=1000, default="none", blank=True, null=True)
    items = models.JSONField(default=dict)
    order_number = models.CharField(max_length=20, unique=True, blank=True)
    total_price = models.IntegerField()
    shipping_address = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=ORDER_STATUS, default='pending')
    item_count = models.IntegerField(null=True, blank=True)
    phone = models.CharField(max_length=15, null=True, blank=True)
    delivery_person = models.CharField(max_length=100, null=True, blank=True)

    def __str__(self):
        return f"Order {self.order_number} - {self.owner.user.username}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = self.generate_order_number()
        self.phone = self.owner.phone
        super().save(*args, **kwargs)

    def generate_order_number(self):
        import random
        import string
        return f"ORD{self.owner.id}{''.join(random.choices(string.digits, k=6))}"


class ContactUs(models.Model):
    name = models.CharField(max_length=50, null=True, blank=True)
    contact = models.CharField(max_length=100, null=True, blank=True)
    message = models.TextField(max_length=200, null=True, blank=True)
