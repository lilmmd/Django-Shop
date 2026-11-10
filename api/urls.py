from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("categories", views.CategoryViewSet, basename="category")
router.register("base-products", views.BaseProductViewSet, basename="base-product")
router.register("products", views.ProductViewSet, basename="product")
router.register("basket", views.BasketViewSet, basename="basket")
router.register("orders", views.OrderViewSet, basename="order")

urlpatterns = [
    path("auth/signup/", views.SignUpView.as_view(), name="signup"),
    path("auth/signin/", views.SignInView.as_view(), name="signin"),
    path("auth/token/refresh/", views.RefreshView.as_view(), name="token-refresh"),
    path("profile/", views.ProfileView.as_view(), name="profile"),
    path("payments/verify/", views.PaymentVerifyView.as_view(), name="payment-verify"),
] + router.urls
