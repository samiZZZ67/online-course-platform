from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularRedocView, SpectacularSwaggerView

from academy import api_docs


admin.site.site_header = "SkillForge Admin"
admin.site.site_title = "SkillForge Admin"
admin.site.index_title = "Platform Management"


urlpatterns = [
    path("api/docs/openapi.json", api_docs.auth_openapi_json, name="auth-openapi-json"),
    path("api/docs/openapi.yaml", api_docs.auth_openapi_yaml, name="auth-openapi-yaml"),
    path("api/docs/swagger/", SpectacularSwaggerView.as_view(url_name="auth-openapi-json"), name="auth-openapi-swagger"),
    path("api/docs/redoc/", SpectacularRedocView.as_view(url_name="auth-openapi-json"), name="auth-openapi-redoc"),
    path("admin/", admin.site.urls),
    path("", include("academy.urls")),
]
