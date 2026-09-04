from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from core.models import Note
from core.serializers import NoteSerializer


class NoteViewSet(viewsets.ModelViewSet):
    """Notes libres sur un contact — le frontend filtre via `?contact=<id>`.
    Plusieurs par contact, modifiables et supprimables, contrairement à
    `Contact.notes` (le besoin exprimé, un champ unique)."""

    serializer_class = NoteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Note.objects.select_related("created_by", "contact").all()
        contact_id = self.request.query_params.get("contact")
        if contact_id:
            queryset = queryset.filter(contact_id=contact_id)
        return queryset

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
