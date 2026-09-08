from django.db.models import Q, Sum
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated

from core.models import DIVISION_CHIEF_ROLES, Notification, Prestation, Project, ProjectPayment, User
from core.serializers import PrestationSerializer, ProjectPaymentSerializer, ProjectSerializer

# Seule la Comptabilité (+ Admin) peut enregistrer un encaissement — même
# principe que le gating de `deposit_received`/`final_payment_received` dans
# `ProjectSerializer.validate`.
ACCOUNTING_ROLES = {User.Role.COMPTABLE_GENERAL, User.Role.ASSISTANT_COMPTABLE, User.Role.ADMIN}

# Rôles voyant tous les projets, tous clients et toutes divisions confondus
# (pilotage commercial/marketing global, direction générale, ou suivi
# financier transverse). Tous les autres utilisateurs ne voient que les
# projets qu'ils ont créés ou dans lesquels leur division intervient (au
# moins une prestation affectée à `user.division`).
FULL_VISIBILITY_ROLES = {
    User.Role.CDM,
    User.Role.CDV,
    User.Role.DG,
    User.Role.COMPTABLE_GENERAL,
    User.Role.ASSISTANT_COMPTABLE,
}


class ProjectViewSet(viewsets.ModelViewSet):
    """Projets clients : le frontend filtre via `?client=<id>` pour la
    fiche client et `?kind=OPPORTUNITE|PROJET` pour séparer les
    opportunités des projets confirmés. Créé avec ses prestations en une
    seule requête (voir `ProjectSerializer.create`)."""

    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = (
            Project.objects.select_related("client", "created_by")
            .prefetch_related("prestations__division", "payments")
            .all()
        )
        user = self.request.user
        if user.role not in FULL_VISIBILITY_ROLES:
            visible = Q(created_by=user)
            if user.division_id:
                visible |= Q(prestations__division_id=user.division_id)
            queryset = queryset.filter(visible).distinct()
        client_id = self.request.query_params.get("client")
        if client_id:
            queryset = queryset.filter(client_id=client_id)
        kind = self.request.query_params.get("kind")
        if kind:
            queryset = queryset.filter(kind=kind)
        return queryset

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class ProjectPaymentViewSet(viewsets.ModelViewSet):
    """Journal des encaissements d'un projet — le frontend filtre via
    `?project=<id>`. Un paiement peut être échelonné en autant de lignes que
    nécessaire ; `deposit_received`/`final_payment_received` se déduisent
    automatiquement du total encaissé dès qu'il franchit le montant de
    l'acompte, puis le budget total, pour rester cohérents avec le reste de
    l'application (gating "démarrer le projet", étape PAIEMENT_FINAL du
    dossier commercial) sans dupliquer la logique côté frontend."""

    serializer_class = ProjectPaymentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = ProjectPayment.objects.select_related("project", "recorded_by").all()
        project_id = self.request.query_params.get("project")
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        return queryset

    def perform_create(self, serializer):
        if self.request.user.role not in ACCOUNTING_ROLES:
            raise PermissionDenied("Seule la Comptabilité peut enregistrer un encaissement.")
        instance = serializer.save(recorded_by=self.request.user)
        self._sync_project_flags(instance.project)

    @staticmethod
    def _sync_project_flags(project):
        total = project.payments.aggregate(total=Sum("amount"))["total"] or 0
        update_fields = []
        if (
            project.requires_deposit
            and not project.deposit_received
            and project.deposit_amount
            and total >= project.deposit_amount
        ):
            project.deposit_received = True
            update_fields.append("deposit_received")
        if project.budget and not project.final_payment_received and total >= project.budget:
            project.final_payment_received = True
            update_fields.append("final_payment_received")
        if update_fields:
            project.save(update_fields=update_fields)


class PrestationViewSet(viewsets.ModelViewSet):
    """Prestations d'un projet : le frontend filtre via `?project=<id>` ou
    `?division=<id>`. Affecter une prestation à une division notifie le
    chef de cette division (voir `DIVISION_CHIEF_ROLES`)."""

    serializer_class = PrestationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Prestation.objects.select_related("project", "division").all()
        project_id = self.request.query_params.get("project")
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        division_id = self.request.query_params.get("division")
        if division_id:
            queryset = queryset.filter(division_id=division_id)
        return queryset

    def perform_create(self, serializer):
        # `project` est en lecture seule sur le serializer (on ne veut pas
        # qu'un client déplace une prestation d'un projet à l'autre par ce
        # biais) : on le résout nous-mêmes depuis le corps de la requête.
        project = get_object_or_404(Project, pk=self.request.data.get("project"))
        self._check_deadline(project, serializer.validated_data.get("deadline"))
        instance = serializer.save(project=project)
        self._notify_division_chief_if_newly_assigned(instance, previous_division=None, note=instance.note)

    def perform_update(self, serializer):
        previous_division = serializer.instance.division
        deadline = serializer.validated_data.get("deadline", serializer.instance.deadline)
        self._check_deadline(serializer.instance.project, deadline)
        instance = serializer.save()
        self._notify_division_chief_if_newly_assigned(instance, previous_division, note=instance.note)

    @staticmethod
    def _check_deadline(project, deadline):
        # Même règle que `ProjectSerializer.validate` (création groupée d'un
        # projet) : à respecter aussi ici, puisqu'une prestation peut
        # désormais être créée/modifiée individuellement.
        if project.deadline and deadline and deadline > project.deadline:
            raise ValidationError(
                {
                    "deadline": (
                        "L'échéance d'une prestation ne peut pas dépasser "
                        f"l'échéance globale du projet ({project.deadline})."
                    )
                }
            )

    def _notify_division_chief_if_newly_assigned(self, prestation, previous_division, note=""):
        if not prestation.division or prestation.division == previous_division:
            return
        role = DIVISION_CHIEF_ROLES.get(prestation.division.name)
        if not role:
            return
        chief = User.objects.filter(role=role, is_active=True).first()
        if not chief:
            return
        message = (
            f"La prestation « {prestation.label} » du projet « {prestation.project.name} » "
            f"a été affectée à votre division ({prestation.division.name})."
        )
        if note:
            message += f" Note : {note}"
        Notification.objects.create(recipient=chief, message=message[:255], urgency=Notification.Urgency.MEDIUM)
