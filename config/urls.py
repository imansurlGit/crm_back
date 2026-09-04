from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.static import serve

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("core.urls")),
]

if settings.DEBUG:
    # `static()` sert les fichiers via `XFrameOptionsMiddleware` (X-Frame-Options:
    # DENY par défaut), ce qui bloque leur prévisualisation en <iframe> dans le
    # frontend (autre origine en dev : port Vite ≠ port Django). On sert donc les
    # médias nous-mêmes, exemptés de cette protection — acceptable ici puisque ce
    # sont des documents déjà accessibles par leur URL, jamais du contenu tiers.
    media_prefix = settings.MEDIA_URL.lstrip("/")
    urlpatterns += [
        re_path(rf"^{media_prefix}(?P<path>.*)$", xframe_options_exempt(serve), {"document_root": settings.MEDIA_ROOT}),
    ]
