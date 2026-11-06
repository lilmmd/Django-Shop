import io
import textwrap
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont

from shop.models import (
    BaseProduct,
    Cart,
    Category,
    Color,
    Feature,
    FeatureName,
    FeatureValue,
    Option,
    Product,
    ProductImage,
    Profile,
    Warranty,
)

User = get_user_model()

PALETTE = ["#1E88E5", "#43A047", "#F4511E", "#8E24AA", "#00897B", "#FB8C00", "#3949AB", "#6D4C41"]


def placeholder_image(text, color, size=600):
    """Return a simple coloured PNG with the text in the middle (Pillow)."""
    image = Image.new("RGB", (size, size), color)
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.load_default(size=40)
    except TypeError:  # very old Pillow
        font = ImageFont.load_default()
    lines = textwrap.wrap(text, width=16) or [text]
    y = size / 2 - (len(lines) - 1) * 28
    for i, line in enumerate(lines):
        draw.text((size / 2, y + i * 56), line, fill="white", font=font, anchor="mm")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return ContentFile(buffer.getvalue())

CATEGORIES = {
    "کالای دیجیتال": ["موبایل", "لپ‌تاپ", "هدفون"],
    "لوازم خانگی": ["آشپزخانه", "جارو برقی"],
    "پوشاک": ["مردانه", "زنانه"],
}

WARRANTIES = ["گارانتی ۱۸ ماهه شرکتی", "گارانتی ۱۲ ماهه اصالت و سلامت فیزیکی", "بدون گارانتی"]

# name, name_en, subcategory, [(price, discount, stock)], colors, options, features
PRODUCTS = [
    ("گوشی سامسونگ A15", "Samsung Galaxy A15", "موبایل",
     [(9_500_000, 500_000, 20), (11_200_000, 0, 10)],
     [("مشکی", "#000000"), ("آبی", "#1E88E5")],
     [("حافظه", "128GB"), ("رم", "6GB")],
     {"مشخصات فنی": {"صفحه نمایش": ["6.5 اینچ AMOLED"], "باتری": ["5000 mAh"]}}),
    ("گوشی شیائومی Note 13", "Xiaomi Redmi Note 13", "موبایل",
     [(8_700_000, 0, 15)],
     [("سبز", "#2E7D32"), ("مشکی", "#000000")],
     [("حافظه", "256GB"), ("رم", "8GB")],
     {"مشخصات فنی": {"دوربین": ["108 مگاپیکسل"], "باتری": ["5000 mAh"]}}),
    ("لپ‌تاپ لنوو IdeaPad 3", "Lenovo IdeaPad 3", "لپ‌تاپ",
     [(32_000_000, 2_000_000, 5)],
     [("نقره‌ای", "#C0C0C0")],
     [("پردازنده", "Core i5"), ("رم", "16GB")],
     {"مشخصات فنی": {"صفحه نمایش": ["15.6 اینچ FHD"], "حافظه": ["512GB SSD"]}}),
    ("لپ‌تاپ ایسوس Vivobook", "Asus Vivobook 15", "لپ‌تاپ",
     [(28_500_000, 0, 0)],
     [("آبی", "#1565C0")],
     [("پردازنده", "Ryzen 5"), ("رم", "8GB")],
     {"مشخصات فنی": {"صفحه نمایش": ["15.6 اینچ"], "وزن": ["1.7 کیلوگرم"]}}),
    ("هدفون بی‌سیم سونی", "Sony WH-CH520", "هدفون",
     [(2_900_000, 300_000, 40)],
     [("مشکی", "#000000"), ("سفید", "#FFFFFF")],
     [("اتصال", "بلوتوث 5.2")],
     {"مشخصات فنی": {"عمر باتری": ["50 ساعت"]}}),
    ("جاروبرقی بوش", "Bosch BGL3", "جارو برقی",
     [(7_800_000, 0, 8)],
     [("قرمز", "#C62828")],
     [("توان", "2200 وات")],
     {"مشخصات فنی": {"ظرفیت": ["4 لیتر"]}}),
    ("پیراهن مردانه", "Men Shirt", "مردانه",
     [(850_000, 150_000, 60), (900_000, 0, 30)],
     [("سفید", "#FFFFFF"), ("آبی", "#1E88E5")],
     [("جنس", "نخی")],
     {"مشخصات فنی": {"سایز": ["M", "L", "XL"]}}),
    ("مانتو زنانه", "Women Coat", "زنانه",
     [(1_450_000, 0, 25)],
     [("مشکی", "#000000"), ("کرمی", "#F5F5DC")],
     [("جنس", "کرپ")],
     {"مشخصات فنی": {"سایز": ["38", "40", "42"]}}),
]


class Command(BaseCommand):
    help = "Fill the database with demo data (categories, products, users)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete existing catalog data (not users/orders) before seeding.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["clear"]:
            self.stdout.write("Clearing catalog data...")
            Cart.objects.all().delete()
            for obj in [*BaseProduct.objects.all(), *ProductImage.objects.all()]:
                if obj.image:
                    obj.image.delete(save=False)  # removes the file from media/
            BaseProduct.objects.all().delete()
            Feature.objects.all().delete()
            Category.objects.all().delete()
            Warranty.objects.all().delete()

        self._users()
        categories = self._categories()
        warranties = [Warranty.objects.get_or_create(name=n)[0] for n in WARRANTIES]
        self._products(categories, warranties)

        self.stdout.write(self.style.SUCCESS("Seed data created."))
        self.stdout.write("Admin: admin / admin12345   |   Demo user: demo / demo12345")

    def _users(self):
        admin, created = User.objects.get_or_create(
            username="admin",
            defaults={"email": "admin@example.com", "is_staff": True, "is_superuser": True},
        )
        if created:
            admin.set_password("admin12345")
            admin.save()
        demo, created = User.objects.get_or_create(
            username="demo", defaults={"email": "demo@example.com"}
        )
        if created:
            demo.set_password("demo12345")
            demo.save()
        for user in (admin, demo):
            Profile.objects.get_or_create(user=user)

    def _categories(self):
        result = {}
        for parent_name, children in CATEGORIES.items():
            parent, _ = Category.objects.get_or_create(name=parent_name, parent_category=None)
            result[parent_name] = parent
            for child_name in children:
                child, _ = Category.objects.get_or_create(name=child_name, parent_category=parent)
                result[child_name] = child
        return result

    def _products(self, categories, warranties):
        sku = 100000
        for n, (name, name_en, cat, variants, colors, options, features) in enumerate(PRODUCTS):
            slug = name_en.lower().replace(" ", "-")
            color = PALETTE[n % len(PALETTE)]
            base, _ = BaseProduct.objects.get_or_create(
                name_en=name_en,
                defaults={"name": name, "category": categories[cat]},
            )
            if not base.image:
                base.image.save(f"{slug}.png", placeholder_image(name_en, color), save=True)
            for i in range(1, 4):
                file_name = f"{slug}-{i}.png"
                if not ProductImage.objects.filter(product=base, image__endswith=file_name).exists():
                    gallery = ProductImage(product=base)
                    gallery.image.save(
                        file_name, placeholder_image(f"{name_en} #{i}", color), save=True
                    )
            for opt_name, opt_value in options:
                Option.objects.get_or_create(
                    base_product=base, name=opt_name, value=opt_value
                )

            for index, (price, discount, stock) in enumerate(variants):
                sku += 1
                product, _ = Product.objects.get_or_create(
                    sku=sku,
                    defaults={
                        "base_product": base,
                        "price": price,
                        "discount": discount,
                        "discount_expiry": timezone.now() + timedelta(days=30)
                        if discount
                        else None,
                        "warranty": warranties[index % len(warranties)],
                        "stock": stock,
                    },
                )
                for color_name, code in colors:
                    Color.objects.get_or_create(
                        product=product, name=color_name, color_code=code
                    )
                for feature_title, names in features.items():
                    feature, _ = Feature.objects.get_or_create(
                        name=f"{feature_title} - {name_en}"
                    )
                    feature.products.add(product)
                    for fname, values in names.items():
                        feature_name, _ = FeatureName.objects.get_or_create(
                            feature=feature, name=fname
                        )
                        for value in values:
                            FeatureValue.objects.get_or_create(
                                feature_name=feature_name, value=value
                            )
