from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from core.views.contacts import ContactViewSet
from core.views.divisions import DivisionObjectiveViewSet, DivisionViewSet
from core.views.documents import DocumentAnnotationViewSet, DocumentViewSet
from core.views.events import EventViewSet
from core.views.interactions import InteractionViewSet
from core.views.messaging import ConversationViewSet
from core.views.notes import NoteViewSet
from core.views.notifications import NotificationViewSet
from core.views.partnerships import PartnershipDossierViewSet, PartnershipTaskViewSet
from core.views.projects import PrestationViewSet, ProjectPaymentViewSet, ProjectViewSet
from core.views.tasks import TaskViewSet
from core.views.users import UserViewSet
from messagerie.views import MessageViewSet

router = DefaultRouter()
router.register("users", UserViewSet, basename="user")
router.register("contacts", ContactViewSet, basename="contact")
router.register("interactions", InteractionViewSet, basename="interaction")
router.register("notes", NoteViewSet, basename="note")
router.register("tasks", TaskViewSet, basename="task")
router.register("events", EventViewSet, basename="event")
router.register("notifications", NotificationViewSet, basename="notification")
router.register("divisions", DivisionViewSet, basename="division")
router.register("division-objectives", DivisionObjectiveViewSet, basename="division-objective")
router.register("projects", ProjectViewSet, basename="project")
router.register("prestations", PrestationViewSet, basename="prestation")
router.register("project-payments", ProjectPaymentViewSet, basename="project-payment")
router.register("documents", DocumentViewSet, basename="document")
router.register("document-annotations", DocumentAnnotationViewSet, basename="document-annotation")
router.register("conversations", ConversationViewSet, basename="conversation")
router.register("messages", MessageViewSet, basename="message")
router.register("partnership-dossiers", PartnershipDossierViewSet, basename="partnership-dossier")
router.register("partnership-tasks", PartnershipTaskViewSet, basename="partnership-task")

urlpatterns = [
    path("auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("", include(router.urls)),
]
