from django.conf import settings
from django.db import models
from django.utils import timezone




# Category

class Category(models.Model):
    name = models.CharField(max_length=255)
    parent_category = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="children",
    )

    class Meta:
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name



# Products

class BaseProduct(models.Model):
    name = models.CharField(max_length=255)
    name_en = models.CharField(max_length=255)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="base_products"
    )
    image = models.ImageField()

    def __str__(self):
        return self.name


class ProductImage(models.Model):
    image = models.ImageField()
    product = models.ForeignKey(
        BaseProduct, on_delete=models.CASCADE, related_name="images"
    )

    def __str__(self):
        return f"Image of {self.product}"


class Option(models.Model):
    name = models.CharField(max_length=255)
    value = models.CharField(max_length=255)
    base_product = models.ForeignKey(
        BaseProduct, on_delete=models.CASCADE, related_name="options"
    )

    def __str__(self):
        return f"{self.name}: {self.value}"


class Warranty(models.Model):
    name = models.CharField(max_length=255)

    class Meta:
        verbose_name_plural = "warranties"

    def __str__(self):
        return self.name


class Product(models.Model):
    base_product = models.ForeignKey(
        BaseProduct, on_delete=models.CASCADE, related_name="products"
    )
    price = models.PositiveIntegerField()
    discount = models.PositiveIntegerField(default=0)
    discount_expiry = models.DateTimeField(null=True, blank=True)
    warranty = models.ForeignKey(
        Warranty,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )
    stock = models.PositiveIntegerField(default=0)
    sku = models.PositiveIntegerField(unique=True)

    def __str__(self):
        return f"{self.base_product} (SKU {self.sku})"

    @property
    def has_active_discount(self):
        if not self.discount:
            return False
        return self.discount_expiry is None or self.discount_expiry > timezone.now()

    @property
    def final_price(self):
        if self.has_active_discount:
            return max(self.price - self.discount, 0)
        return self.price


class Color(models.Model):
    name = models.CharField(max_length=50)
    color_code = models.CharField(max_length=7, help_text="e.g. #FF0000")
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="colors"
    )

    def __str__(self):
        return self.name



# Features (Feature -> FeatureName -> FeatureValue)

class Feature(models.Model):
    name = models.CharField(max_length=255)
    products = models.ManyToManyField(Product, related_name="features", blank=True)

    def __str__(self):
        return self.name


class FeatureName(models.Model):
    name = models.CharField(max_length=255)
    feature = models.ForeignKey(
        Feature, on_delete=models.CASCADE, related_name="feature_names"
    )

    def __str__(self):
        return self.name


class FeatureValue(models.Model):
    value = models.CharField(max_length=255)
    feature_name = models.ForeignKey(
        FeatureName, on_delete=models.CASCADE, related_name="values"
    )

    def __str__(self):
        return self.value



# User related

class UserFavorite(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favorites"
    )
    base_product = models.ForeignKey(
        BaseProduct, on_delete=models.CASCADE, related_name="favorited_by"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "base_product"], name="unique_user_favorite"
            )
        ]

    def __str__(self):
        return f"{self.user} -> {self.base_product}"


class Cart(models.Model):
    """One basket per user; the products live in CartItem."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cart"
    )

    def __str__(self):
        return f"Cart of {self.user.username}"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="cart_items"
    )
    quantity = models.PositiveSmallIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["cart", "product"], name="unique_cart_item")
        ]

    def __str__(self):
        return f"{self.cart.user.username}: {self.product} x{self.quantity}"



# Accounts

class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    phone = models.CharField(max_length=15, blank=True)
    address = models.TextField(blank=True)
    birth_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"Profile of {self.user}"



# Orders & payments

class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending payment"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="orders"
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    total_price = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"Order #{self.pk} ({self.status})"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    # The product may be deleted later, so we keep a snapshot of its data.
    product = models.ForeignKey(
        Product, on_delete=models.SET_NULL, null=True, related_name="order_items"
    )
    product_name = models.CharField(max_length=255)
    sku = models.PositiveIntegerField()
    unit_price = models.PositiveIntegerField()
    quantity = models.PositiveSmallIntegerField()

    @property
    def subtotal(self):
        return self.unit_price * self.quantity

    def __str__(self):
        return f"{self.product_name} x{self.quantity}"


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="payments")
    authority = models.CharField(max_length=64, unique=True)
    amount = models.PositiveBigIntegerField(help_text="Amount in Rial")
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    ref_id = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Payment {self.authority} ({self.status})"
