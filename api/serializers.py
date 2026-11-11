from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from shop.models import (
    BaseProduct,
    Cart,
    CartItem,
    Category,
    Color,
    Feature,
    FeatureName,
    FeatureValue,
    Option,
    Order,
    OrderItem,
    Payment,
    Product,
    ProductImage,
    Profile,
)


# Accounts

User = get_user_model()


class SignUpSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    class Meta:
        model = User
        fields = ["id", "username", "email", "password", "first_name", "last_name"]
        extra_kwargs = {"email": {"required": True}}

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate(self, attrs):
        user = User(**{k: v for k, v in attrs.items() if k != "password"})
        validate_password(attrs["password"], user)
        return attrs

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        Profile.objects.create(user=user)
        return user


class ProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", required=False)
    first_name = serializers.CharField(
        source="user.first_name", required=False, allow_blank=True
    )
    last_name = serializers.CharField(
        source="user.last_name", required=False, allow_blank=True
    )

    class Meta:
        model = Profile
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "phone",
            "address",
            "birth_date",
        ]

    def _apply_user_data(self, user, user_data):
        for field, value in user_data.items():
            setattr(user, field, value)
        if user_data:
            user.save()

    def create(self, validated_data):
        user = self.context["request"].user
        self._apply_user_data(user, validated_data.pop("user", {}))
        return Profile.objects.create(user=user, **validated_data)

    def update(self, instance, validated_data):
        self._apply_user_data(instance.user, validated_data.pop("user", {}))
        return super().update(instance, validated_data)



# Catalog

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "parent_category"]


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ["id", "image"]


class OptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Option
        fields = ["id", "name", "value"]


class ColorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Color
        fields = ["id", "name", "color_code"]


class FeatureValueSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeatureValue
        fields = ["id", "value"]


class FeatureNameSerializer(serializers.ModelSerializer):
    values = FeatureValueSerializer(many=True, read_only=True)

    class Meta:
        model = FeatureName
        fields = ["id", "name", "values"]


class FeatureSerializer(serializers.ModelSerializer):
    feature_names = FeatureNameSerializer(many=True, read_only=True)

    class Meta:
        model = Feature
        fields = ["id", "name", "feature_names"]


class ProductSerializer(serializers.ModelSerializer):
    """The sellable variant (price, stock, warranty...)."""

    name = serializers.CharField(source="base_product.name", read_only=True)
    name_en = serializers.CharField(source="base_product.name_en", read_only=True)
    final_price = serializers.IntegerField(read_only=True)
    colors = ColorSerializer(many=True, read_only=True)
    features = FeatureSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "base_product",
            "name",
            "name_en",
            "price",
            "discount",
            "discount_expiry",
            "final_price",
            "warranty",
            "stock",
            "sku",
            "colors",
            "features",
        ]

    def validate(self, attrs):
        price = attrs.get("price", getattr(self.instance, "price", None))
        discount = attrs.get("discount", getattr(self.instance, "discount", 0))
        if price is not None and discount > price:
            raise serializers.ValidationError(
                {"discount": "Discount cannot be greater than the price."}
            )
        return attrs


class BaseProductListSerializer(serializers.ModelSerializer):
    min_price = serializers.IntegerField(read_only=True)
    in_stock = serializers.SerializerMethodField()

    class Meta:
        model = BaseProduct
        fields = ["id", "name", "name_en", "category", "image", "min_price", "in_stock"]

    def get_in_stock(self, obj) -> bool:
        return (getattr(obj, "total_stock", 0) or 0) > 0


class BaseProductSerializer(serializers.ModelSerializer):
    """Create / update / detail. Nested data is read-only."""

    images = ProductImageSerializer(many=True, read_only=True)
    options = OptionSerializer(many=True, read_only=True)
    products = ProductSerializer(many=True, read_only=True)

    class Meta:
        model = BaseProduct
        fields = [
            "id",
            "name",
            "name_en",
            "category",
            "image",
            "images",
            "options",
            "products",
        ]



# Basket

class CartItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.base_product.name", read_only=True)
    unit_price = serializers.IntegerField(source="product.final_price", read_only=True)
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ["id", "product", "product_name", "unit_price", "quantity", "subtotal"]
        extra_kwargs = {"quantity": {"min_value": 1}}

    def get_subtotal(self, obj) -> int:
        return obj.product.final_price * obj.quantity

    def validate(self, attrs):
        request = self.context["request"]
        product = attrs["product"]
        quantity = attrs["quantity"]
        existing = CartItem.objects.filter(
            cart__user=request.user, product=product
        ).first()
        wanted = quantity + (existing.quantity if existing else 0)
        if wanted > product.stock:
            raise serializers.ValidationError(
                {"quantity": f"Only {product.stock} item(s) in stock."}
            )
        return attrs

    def create(self, validated_data):
        user = self.context["request"].user
        cart, _ = Cart.objects.get_or_create(user=user)
        item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=validated_data["product"],
            defaults={"quantity": validated_data["quantity"]},
        )
        if not created:
            item.quantity += validated_data["quantity"]
            item.save(update_fields=["quantity"])
        return item


class CartItemUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CartItem
        fields = ["quantity"]
        extra_kwargs = {"quantity": {"min_value": 1}}

    def validate_quantity(self, value):
        if value > self.instance.product.stock:
            raise serializers.ValidationError(
                f"Only {self.instance.product.stock} item(s) in stock."
            )
        return value


class BasketSerializer(serializers.Serializer):
    items = CartItemSerializer(many=True)
    total_price = serializers.IntegerField()



# Orders / payments

class OrderItemSerializer(serializers.ModelSerializer):
    subtotal = serializers.IntegerField(read_only=True)

    class Meta:
        model = OrderItem
        fields = ["id", "product", "product_name", "sku", "unit_price", "quantity", "subtotal"]


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["authority", "amount", "status", "ref_id", "created_at", "verified_at"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = ["id", "status", "total_price", "created_at", "paid_at", "items", "payments"]


class PaymentStartSerializer(serializers.Serializer):
    authority = serializers.CharField()
    payment_url = serializers.URLField()


class PaymentResultSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["success", "failed"])
    order_id = serializers.IntegerField()
    ref_id = serializers.CharField(allow_blank=True)
    detail = serializers.CharField(required=False)
