from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import Event
from core.serializers import EventSerializer


class EventViewSet(viewsets.ModelViewSet):
    """Rendez-vous programmés (appel/réunion) sur un contact : le frontend
    filtre via `?contact=<id>`."""

    serializer_class = EventSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Event.objects.select_related("created_by", "contact").all()
        contact_id = self.request.query_params.get("contact")
        if contact_id:
            queryset = queryset.filter(contact_id=contact_id)
        return queryset

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"])
    def respond(self, request, pk=None):
        """Le destinataire répond à une demande de rendez-vous : accepte,
        décline, ou reporte (auquel cas `starts_at` est requis — l'horaire
        initial est conservé dans `original_starts_at` avant écrasement)."""
        event = self.get_object()
        decision = request.data.get("decision")
        valid_decisions = {Event.Status.ACCEPTED, Event.Status.DECLINED, Event.Status.POSTPONED}
        if decision not in valid_decisions:
            return Response({"detail": "decision invalide."}, status=400)

        if decision == Event.Status.POSTPONED:
            new_starts_at = request.data.get("starts_at")
            if not new_starts_at:
                return Response({"detail": "starts_at requis pour un report."}, status=400)
            if event.original_starts_at is None:
                event.original_starts_at = event.starts_at
            event.starts_at = new_starts_at

        event.status = decision
        event.save()
        return Response(EventSerializer(event).data)
