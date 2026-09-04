from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import User
from core.permissions import CanManageUsers
from core.serializers import ChangePasswordSerializer, UserCreateSerializer, UserSerializer


class UserViewSet(viewsets.ModelViewSet):
    """CRUD complet réservé au DG/ADCH (`core.permissions.CanManageUsers`),
    plus deux actions ouvertes à tout utilisateur authentifié pour gérer son
    propre compte : `me` (profil + photo) et `change-password`."""

    queryset = User.objects.all().order_by("email")
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        return UserSerializer

    def get_permissions(self):
        if self.action in ("me", "change_password", "commercials", "by_division", "directory"):
            return [IsAuthenticated()]
        return [CanManageUsers()]

    @action(detail=False, methods=["get", "patch"], url_path="me")
    def me(self, request):
        if request.method == "PATCH":
            serializer = UserSerializer(
                request.user, data=request.data, partial=True, context={"request": request}
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)

        serializer = UserSerializer(request.user, context={"request": request})
        return Response(serializer.data)

    @action(detail=False, methods=["post"], url_path="change-password")
    def change_password(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        return Response({"detail": "Mot de passe mis à jour."})

    @action(detail=False, methods=["get"], url_path="roles")
    def roles(self, request):
        return Response([{"value": value, "label": label} for value, label in User.Role.choices])

    @action(detail=False, methods=["get"], url_path="commercials")
    def commercials(self, request):
        """Liste des commerciaux actifs, utilisée pour transférer un contact
        (prospect/client/partenaire). Ouverte à tout utilisateur authentifié,
        contrairement au reste du CRUD utilisateurs."""
        queryset = User.objects.filter(role=User.Role.COMMERCIAL, is_active=True).order_by("first_name")
        serializer = UserSerializer(queryset, many=True, context={"request": request})
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="by-division")
    def by_division(self, request):
        """Membres actifs d'une division (`?division=<id>`, ou la division du
        demandeur si omis) — utilisé par un chef de division pour affecter
        une tâche de prestation à un membre de son équipe. Ouverte à tout
        utilisateur authentifié, contrairement au reste du CRUD utilisateurs."""
        division_id = request.query_params.get("division") or request.user.division_id
        if not division_id:
            return Response([])
        queryset = User.objects.filter(division_id=division_id, is_active=True).order_by("first_name")
        serializer = UserSerializer(queryset, many=True, context={"request": request})
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="directory")
    def directory(self, request):
        """Annuaire des collègues actifs — utilisé pour démarrer une
        discussion directe depuis la messagerie. Ouvert à tout utilisateur
        authentifié, contrairement au reste du CRUD utilisateurs."""
        queryset = User.objects.filter(is_active=True).exclude(pk=request.user.pk).order_by("first_name")
        serializer = UserSerializer(queryset, many=True, context={"request": request})
        return Response(serializer.data)
