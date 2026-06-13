"""
URL configuration for zproject project.
"""

from django.contrib import admin
from django.urls import include, path
from zserver.views import health_check

urlpatterns = [
    path("admin/",  admin.site.urls),
    path("health/", health_check, name="health_check"),
    path("",        include("zserver.urls")),   # mounts /jobs/...
]
