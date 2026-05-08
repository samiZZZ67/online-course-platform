from django.contrib import admin
from django.urls import include, path


admin.site.site_header = "SkillForge Admin"
admin.site.site_title = "SkillForge Admin"
admin.site.index_title = "Platform Management"


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("academy.urls")),
]
