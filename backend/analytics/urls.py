from django.urls import path

from analytics import views

urlpatterns = [
    path("analytics/business/", views.business),
    path("analytics/ngo/", views.ngo),
    path("analytics/impact/", views.impact),
    path("analytics/admin/", views.admin_overview),
]
