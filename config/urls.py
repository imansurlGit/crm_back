from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.static import serve

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("core.urls")),
]

# `static()` sert les fichiers via `XFrameOptionsMiddleware` (X-Frame-Options:
# DENY par défaut), ce qui bloque leur prévisualisation en <iframe> dans le
# frontend (autre origine : port Vite ≠ port Django en dev, domaine GitHub
# Pages ≠ domaine Render en prod). On sert donc les médias nous-mêmes,
# exemptés de cette protection — acceptable ici puisque ce sont des documents
# déjà accessibles par leur URL, jamais du contenu tiers. Servi en dev ET en
# prod (pas de CDN/stockage dédié pour l'instant — voir TODO stockage cloud
# pour la persistance des fichiers sur Render, dont le disque est éphémère).
media_prefix = settings.MEDIA_URL.lstrip("/")
urlpatterns += [
    re_path(rf"^{media_prefix}(?P<path>.*)$", xframe_options_exempt(serve), {"document_root": settings.MEDIA_ROOT}),
]
