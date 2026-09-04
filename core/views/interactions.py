from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from core.models import Interaction
from core.serializers import InteractionSerializer


class InteractionViewSet(viewsets.ModelViewSet):
    """Historique des échanges (appel/réunion/email) d'un contact : le
    frontend filtre via `?contact=<id>` pour afficher la fiche d'un
    prospect/client donné."""

    serializer_class = InteractionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Interaction.objects.select_related("created_by", "contact").all()
        contact_id = self.request.query_params.get("contact")
        if contact_id:
            queryset = queryset.filter(contact_id=contact_id)
        return queryset

    def perform_create(self, serializer):
        contact = serializer.validated_data["contact"]
        serializer.save(created_by=self.request.user, stage=contact.stage)
