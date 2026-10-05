from rest_framework.routers import DefaultRouter

from marketplace import views

router = DefaultRouter()
router.register("marketplace/listings", views.ListingViewSet, basename="listing")
router.register("marketplace/requirements", views.RequirementViewSet, basename="requirement")
router.register("pickups", views.PickupViewSet, basename="pickup")
urlpatterns = router.urls
