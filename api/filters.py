from django.db.models import Q
from django_filters import rest_framework as filters

from shop.models import BaseProduct, Category, Product


def category_with_descendants(category_id):
    """Return the id of a category and all of its sub-categories."""
    ids = {category_id}
    frontier = [category_id]
    while frontier:
        children = Category.objects.filter(parent_category_id__in=frontier).values_list(
            "id", flat=True
        )
        frontier = [c for c in children if c not in ids]
        ids.update(frontier)
    return ids


class BaseProductFilter(filters.FilterSet):
    category = filters.NumberFilter(
        method="filter_category", help_text="Category id (sub-categories included)"
    )
    min_price = filters.NumberFilter(
        field_name="min_price", lookup_expr="gte", help_text="Lowest variant price >= value"
    )
    max_price = filters.NumberFilter(
        field_name="min_price", lookup_expr="lte", help_text="Lowest variant price <= value"
    )
    in_stock = filters.BooleanFilter(method="filter_in_stock")

    class Meta:
        model = BaseProduct
        fields = ["category", "min_price", "max_price", "in_stock"]

    def filter_category(self, queryset, name, value):
        return queryset.filter(category_id__in=category_with_descendants(int(value)))

    def filter_in_stock(self, queryset, name, value):
        if value:
            return queryset.filter(total_stock__gt=0)
        return queryset.filter(Q(total_stock__lte=0) | Q(total_stock__isnull=True))


class ProductFilter(filters.FilterSet):
    category = filters.NumberFilter(
        method="filter_category", help_text="Category id (sub-categories included)"
    )
    min_price = filters.NumberFilter(field_name="price", lookup_expr="gte")
    max_price = filters.NumberFilter(field_name="price", lookup_expr="lte")
    in_stock = filters.BooleanFilter(method="filter_in_stock")

    class Meta:
        model = Product
        fields = ["base_product", "warranty", "category", "min_price", "max_price", "in_stock"]

    def filter_category(self, queryset, name, value):
        return queryset.filter(
            base_product__category_id__in=category_with_descendants(int(value))
        )

    def filter_in_stock(self, queryset, name, value):
        return queryset.filter(stock__gt=0) if value else queryset.filter(stock=0)
