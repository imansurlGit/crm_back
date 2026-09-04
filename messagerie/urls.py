from rest_framework.routers import DefaultRouter

from messagerie.views import ConversationViewSet, MessageViewSet

# Inclus tel quel par un projet qui n'a pas besoin de canaux provisionnés
# automatiquement. Un projet qui en a besoin (voir core/urls.py) enregistre
# plutôt sa propre sous-classe de `ConversationViewSet` sous cette même route.
router = DefaultRouter()
router.register("conversations", ConversationViewSet, basename="conversation")
router.register("messages", MessageViewSet, basename="message")

urlpatterns = router.urls
