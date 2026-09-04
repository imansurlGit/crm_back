from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from messagerie.models import Conversation, ConversationParticipant, Message
from messagerie.serializers import ConversationSerializer, MessageSerializer

User = get_user_model()


class ConversationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Conversations (groupes ou messages directs) de l'utilisateur connecté.

    Générique : ne crée aucun groupe automatiquement. Un projet hôte qui veut
    provisionner des canaux par défaut (ex: un « Général », un par équipe...)
    doit le faire lui-même — typiquement via une sous-classe qui surcharge
    `get_queryset` pour appeler sa propre logique avant `super()` (voir
    `core.views.messaging.ConversationViewSet` pour l'exemple)."""

    serializer_class = ConversationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Conversation.objects.filter(participants=self.request.user)
            .prefetch_related("participants", "messages", "memberships")
            .distinct()
        )

    @action(detail=False, methods=["post"], url_path="direct")
    def direct(self, request):
        """Récupère (ou crée) la conversation directe avec un autre utilisateur."""
        other_id = request.data.get("user")
        try:
            other = User.objects.get(pk=other_id, is_active=True)
        except (User.DoesNotExist, ValueError, TypeError):
            raise ValidationError({"user": "Utilisateur introuvable."})
        if other.pk == request.user.pk:
            raise ValidationError({"user": "Impossible de démarrer une conversation avec vous-même."})

        conversation = (
            Conversation.objects.filter(kind=Conversation.Kind.DIRECT, participants=request.user)
            .filter(participants=other)
            .first()
        )
        if not conversation:
            conversation = Conversation.objects.create(kind=Conversation.Kind.DIRECT)
            ConversationParticipant.objects.bulk_create(
                [
                    ConversationParticipant(conversation=conversation, user=request.user),
                    ConversationParticipant(conversation=conversation, user=other),
                ]
            )
        serializer = self.get_serializer(conversation)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="mark-read")
    def mark_read(self, request, pk=None):
        conversation = self.get_object()
        ConversationParticipant.objects.filter(conversation=conversation, user=request.user).update(
            last_read_at=timezone.now()
        )
        return Response(status=204)


class MessageViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """Messages d'une conversation — le frontend filtre via `?conversation=<id>`.
    Lecture et écriture réservées aux participants de la conversation."""

    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Message.objects.filter(conversation__participants=self.request.user).select_related("sender")
        conversation_id = self.request.query_params.get("conversation")
        if conversation_id:
            queryset = queryset.filter(conversation_id=conversation_id)
        return queryset

    def perform_create(self, serializer):
        conversation = serializer.validated_data["conversation"]
        if not conversation.participants.filter(pk=self.request.user.pk).exists():
            raise PermissionDenied("Vous ne participez pas à cette conversation.")
        serializer.save(sender=self.request.user)
