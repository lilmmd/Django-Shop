from django.conf import settings
from django.db import transaction
from django.db.models import Min, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import generics, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from shop.models import BaseProduct, CartItem, Category, Order, Payment, Product, Profile

from . import zarinpal
from .filters import BaseProductFilter, ProductFilter
from .permissions import IsAdminOrReadOnly
from .serializers import (
    BaseProductListSerializer,
    BaseProductSerializer,
    BasketSerializer,
    CartItemSerializer,
    CartItemUpdateSerializer,
    CategorySerializer,
    OrderSerializer,
    PaymentResultSerializer,
    PaymentStartSerializer,
    ProductSerializer,
    ProfileSerializer,
    SignUpSerializer,
)
from .services import cancel_order, create_order_from_basket, mark_order_paid


# Auth & profile

@extend_schema(tags=["auth"])
class SignUpView(generics.CreateAPIView):
    """Create a new account (and its empty profile)."""

    serializer_class = SignUpSerializer
    permission_classes = [AllowAny]


@extend_schema(tags=["profile"])
class ProfileView(generics.GenericAPIView):
    """CRUD for the profile of the logged-in user."""

    serializer_class = ProfileSerializer

    def get_profile(self):
        return Profile.objects.select_related("user").filter(user=self.request.user).first()

    def _not_found(self):
        return Response({"detail": "Profile not found."}, status=status.HTTP_404_NOT_FOUND)

    def get(self, request):
        profile = self.get_profile()
        if profile is None:
            return self._not_found()
        return Response(self.get_serializer(profile).data)

    def post(self, request):
        """Create the profile (only if the user does not have one)."""
        if self.get_profile() is not None:
            return Response(
                {"detail": "Profile already exists."}, status=status.HTTP_400_BAD_REQUEST
            )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def put(self, request):
        return self._update(request, partial=False)

    def patch(self, request):
        return self._update(request, partial=True)

    def _update(self, request, partial):
        profile = self.get_profile()
        if profile is None:
            return self._not_found()
        serializer = self.get_serializer(profile, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request):
        profile = self.get_profile()
        if profile is None:
            return self._not_found()
        profile.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["auth"], summary="Sign in (get JWT access/refresh tokens)")
class SignInView(TokenObtainPairView):
    pass


@extend_schema(tags=["auth"], summary="Get a new access token")
class RefreshView(TokenRefreshView):
    pass



# Catalog

@extend_schema(tags=["catalog"])
class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all().order_by("id")
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]
    search_fields = ["name"]


@extend_schema(tags=["catalog"])
@extend_schema_view(
    list=extend_schema(summary="Search / filter products (base products)"),
)
class BaseProductViewSet(viewsets.ModelViewSet):
    """
    Catalog items. Use `search` (name, English name, category name),
    filters (`category`, `min_price`, `max_price`, `in_stock`)
    and `ordering` (`min_price`, `name`, `id`; prefix with `-` for descending).
    """

    permission_classes = [IsAdminOrReadOnly]
    filterset_class = BaseProductFilter
    search_fields = ["name", "name_en", "category__name"]
    ordering_fields = ["min_price", "name", "id"]
    ordering = ["id"]

    def get_queryset(self):
        return (
            BaseProduct.objects.select_related("category")
            .prefetch_related(
                "images",
                "options",
                "products__colors",
                "products__features__feature_names__values",
            )
            .annotate(min_price=Min("products__price"), total_stock=Sum("products__stock"))
        )

    def get_serializer_class(self):
        if self.action == "list":
            return BaseProductListSerializer
        return BaseProductSerializer


@extend_schema(tags=["catalog"])
class ProductViewSet(viewsets.ModelViewSet):
    """Sellable variants of a base product (price, discount, stock, sku)."""

    queryset = (
        Product.objects.select_related("base_product", "warranty")
        .prefetch_related("colors", "features__feature_names__values")
        .order_by("id")
    )
    serializer_class = ProductSerializer
    permission_classes = [IsAdminOrReadOnly]
    filterset_class = ProductFilter
    search_fields = ["base_product__name", "base_product__name_en"]
    ordering_fields = ["price", "stock", "id"]



# Basket

@extend_schema(tags=["basket"])
class BasketViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """The shopping basket of the logged-in user."""

    queryset = CartItem.objects.none()  # real queryset is built per user in get_queryset
    pagination_class = None
    filter_backends = []
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return CartItem.objects.filter(cart__user=self.request.user).select_related(
            "product__base_product"
        )

    def get_serializer_class(self):
        if self.action in ("update", "partial_update"):
            return CartItemUpdateSerializer
        return CartItemSerializer

    @extend_schema(summary="List basket items and total", responses=BasketSerializer)
    def list(self, request, *args, **kwargs):
        items = list(self.get_queryset())
        total = sum(i.product.final_price * i.quantity for i in items)
        data = BasketSerializer(
            {"items": items, "total_price": total}, context={"request": request}
        ).data
        return Response(data)

    @extend_schema(summary="Add a product (increases quantity if already there)")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @extend_schema(summary="Remove every item from the basket", responses={204: None})
    @action(detail=False, methods=["delete"])
    def clear(self, request):
        self.get_queryset().delete()
        return Response(status=status.HTTP_204_NO_CONTENT)



# Orders (purchase) + payment

@extend_schema(tags=["orders"])
class OrderViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    queryset = Order.objects.none()  # real queryset is built per user in get_queryset
    serializer_class = OrderSerializer
    pagination_class = None
    filter_backends = []

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related(
            "items", "payments"
        )

    @extend_schema(
        summary="Purchase: create an order from the basket",
        request=None,
        responses={201: OrderSerializer},
    )
    def create(self, request):
        order = create_order_from_basket(request.user)
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Start a Zarinpal payment for a pending order",
        request=None,
        responses={200: PaymentStartSerializer},
    )
    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        order = self.get_object()
        if order.status != Order.Status.PENDING:
            raise ValidationError({"detail": "This order is not waiting for payment."})

        amount_rial = order.total_price * settings.TOMAN_TO_RIAL
        try:
            authority = zarinpal.request_payment(
                amount_rial=amount_rial,
                description=f"Order #{order.id}",
                callback_url=settings.ZARINPAL_CALLBACK_URL,
            )
        except zarinpal.ZarinpalError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        Payment.objects.create(order=order, authority=authority, amount=amount_rial)
        return Response(
            {"authority": authority, "payment_url": zarinpal.start_pay_url(authority)}
        )

    @extend_schema(
        summary="Cancel a pending order (stock is returned)",
        request=None,
        responses={200: OrderSerializer},
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        order = cancel_order(self.get_object())
        return Response(OrderSerializer(order).data)


@extend_schema(
    tags=["orders"],
    summary="Zarinpal callback: verify the payment",
    description="Zarinpal redirects the buyer here with `Authority` and `Status` query parameters.",
    parameters=[
        OpenApiParameter("Authority", str, required=True),
        OpenApiParameter("Status", str, required=True, description="OK or NOK"),
    ],
    responses={200: PaymentResultSerializer},
)
class PaymentVerifyView(APIView):
    permission_classes = [AllowAny]  # called by the user's browser after the bank page
    authentication_classes = []

    def get(self, request):
        authority = request.query_params.get("Authority", "")
        gateway_status = request.query_params.get("Status", "")
        payment = get_object_or_404(Payment.objects.select_related("order"), authority=authority)

        if payment.status != Payment.Status.PENDING:  # already handled
            return self._response(payment)

        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(pk=payment.pk)
            if payment.status == Payment.Status.PENDING:
                self._finish(payment, gateway_status)
        return self._response(payment)

    def _finish(self, payment, gateway_status):
        payment.verified_at = timezone.now()
        if gateway_status != "OK":
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status", "verified_at"])
            return
        try:
            payment.ref_id = zarinpal.verify_payment(payment.amount, payment.authority)
        except zarinpal.ZarinpalError:
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status", "verified_at"])
            return
        payment.status = Payment.Status.SUCCESS
        payment.save(update_fields=["status", "ref_id", "verified_at"])
        mark_order_paid(payment.order)

    def _response(self, payment):
        ok = payment.status == Payment.Status.SUCCESS
        body = {
            "status": "success" if ok else "failed",
            "order_id": payment.order_id,
            "ref_id": payment.ref_id,
        }
        if not ok:
            body["detail"] = "Payment failed. The order is still pending; you can retry or cancel it."
        return Response(body)
