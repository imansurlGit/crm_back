from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from core.models import Division, DivisionObjective
from core.serializers import DivisionObjectiveSerializer, DivisionSerializer


class DivisionViewSet(viewsets.ModelViewSet):
    """Référentiel des divisions de l'agence (Ventes, Marketing, Numérique,
    Visibilité/Infrastructure/Production...)."""

    queryset = Division.objects.all()
    serializer_class = DivisionSerializer
    permission_classes = [IsAuthenticated]


class DivisionObjectiveViewSet(viewsets.ModelViewSet):
    """Objectifs mensuels de CA par division, fixés par le DG (voir
    DgFinancePage.tsx) : le frontend filtre via `?month=YYYY-MM-01`."""

    serializer_class = DivisionObjectiveSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = DivisionObjective.objects.select_related("division", "set_by").all()
        month = self.request.query_params.get("month")
        if month:
            queryset = queryset.filter(month=month)
        return queryset

    def perform_create(self, serializer):
        serializer.save(set_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(set_by=self.request.user)
