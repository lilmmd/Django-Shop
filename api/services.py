from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from shop.models import CartItem, Order, OrderItem, Product


@transaction.atomic
def create_order_from_basket(user):
    """Turn the user's basket into an order and reserve the stock."""
    cart_items = list(
        CartItem.objects.filter(cart__user=user).select_related("product__base_product")
    )
    if not cart_items:
        raise ValidationError({"detail": "Your basket is empty."})

    # Lock the product rows so two buyers cannot take the same last item.
    products = {
        p.id: p
        for p in Product.objects.select_for_update()
        .filter(id__in=[c.product_id for c in cart_items])
        .order_by("id")
    }

    order = Order.objects.create(user=user, total_price=0)
    total = 0
    for item in cart_items:
        product = products[item.product_id]
        if item.quantity > product.stock:
            raise ValidationError(
                {
                    "detail": f"Not enough stock for '{product.base_product.name}' "
                    f"(available: {product.stock})."
                }
            )
        unit_price = product.final_price
        OrderItem.objects.create(
            order=order,
            product=product,
            product_name=product.base_product.name,
            sku=product.sku,
            unit_price=unit_price,
            quantity=item.quantity,
        )
        product.stock -= item.quantity
        product.save(update_fields=["stock"])
        total += unit_price * item.quantity

    order.total_price = total
    order.save(update_fields=["total_price"])
    CartItem.objects.filter(cart__user=user).delete()
    return order


@transaction.atomic
def cancel_order(order):
    """Cancel a pending order and give the reserved stock back."""
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status != Order.Status.PENDING:
        raise ValidationError({"detail": "Only pending orders can be cancelled."})
    for item in order.items.exclude(product__isnull=True):
        Product.objects.filter(pk=item.product_id).update(stock=F("stock") + item.quantity)
    order.status = Order.Status.CANCELLED
    order.save(update_fields=["status"])
    return order


def mark_order_paid(order):
    order.status = Order.Status.PAID
    order.paid_at = timezone.now()
    order.save(update_fields=["status", "paid_at"])
