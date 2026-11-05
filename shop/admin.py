from django.contrib import admin

from . import models


class OrderItemInline(admin.TabularInline):
    model = models.OrderItem
    extra = 0


@admin.register(models.Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "status", "total_price", "created_at"]
    list_filter = ["status"]
    inlines = [OrderItemInline]


for model in (
    models.Category,
    models.BaseProduct,
    models.ProductImage,
    models.Option,
    models.Warranty,
    models.Product,
    models.Color,
    models.Feature,
    models.FeatureName,
    models.FeatureValue,
    models.UserFavorite,
    models.Cart,
    models.CartItem,
    models.Profile,
    models.Payment,
):
    admin.site.register(model)
