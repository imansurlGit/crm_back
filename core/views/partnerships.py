from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import Notification, PartnershipDossier, PartnershipTask, PartnershipTimelineEntry, User
from core.serializers import PartnershipDossierSerializer, PartnershipTaskSerializer

Step = PartnershipDossier.Step
ConventionStatus = PartnershipDossier.ConventionStatus
Kind = PartnershipTimelineEntry.Kind
STEP_ORDER = [choice[0] for choice in Step.choices]
STEP_LABELS = dict(Step.choices)
CONVENTION_STATUS_LABELS = dict(ConventionStatus.choices)


class PartnershipDossierViewSet(viewsets.ModelViewSet):
    """Dossiers de suivi partenariat, du premier contact à la clôture de
    l'événement. `advance` reproduit le moteur de transitions du prototype
    frontend (timeline, tâches générées, blocages) côté serveur."""

    serializer_class = PartnershipDossierSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            PartnershipDossier.objects.select_related("partenaire", "head_marketing", "created_by")
            .prefetch_related("timeline__author", "tasks")
            .all()
        )

    def perform_create(self, serializer):
        head_marketing = User.objects.filter(role=User.Role.CDM, is_active=True).first()
        instance = serializer.save(created_by=self.request.user, head_marketing=head_marketing)
        instance.reference = f"PART-{instance.created_at.year}-{instance.id:03d}"
        instance.save(update_fields=["reference"])
        PartnershipTimelineEntry.objects.create(
            dossier=instance, author=self.request.user, label="Dossier partenariat créé.", kind=Kind.SYSTEM
        )

    def _apply_step_transition(self, dossier, from_step, author):
        if from_step == Step.CREATION:
            head_name = dossier.head_marketing.get_full_name() if dossier.head_marketing else "le Head of Marketing"
            PartnershipTimelineEntry.objects.create(
                dossier=dossier, author=author, label=f"Dossier transmis à {head_name} — notification envoyée.", kind=Kind.SYSTEM
            )
            if dossier.head_marketing:
                Notification.objects.create(
                    recipient=dossier.head_marketing,
                    message=f"Le dossier partenariat « {dossier.reference} » vous a été transmis."[:255],
                    urgency=Notification.Urgency.MEDIUM,
                )
        elif from_step == Step.TRANSMISSION:
            PartnershipTimelineEntry.objects.create(
                dossier=dossier,
                author=author,
                label="Réunion de qualification ajoutée au calendrier collaboratif.",
                kind=Kind.SYSTEM,
            )
            PartnershipTask.objects.create(dossier=dossier, label="Préparer la fiche signalétique du partenaire")
        elif from_step == Step.DISCUSSIONS:
            PartnershipTimelineEntry.objects.create(dossier=dossier, author=author, label="Accord de principe obtenu.", kind=Kind.ACTION)
        elif from_step == Step.ACCORD_PRINCIPE:
            dossier.convention_status = ConventionStatus.EN_PREPARATION
            dossier.save(update_fields=["convention_status"])
            PartnershipTask.objects.create(dossier=dossier, label="Rédiger la convention de partenariat")
            PartnershipTimelineEntry.objects.create(
                dossier=dossier, author=author, label="Préparation de la convention lancée.", kind=Kind.SYSTEM
            )
        elif from_step == Step.PREPARATION_CONVENTION:
            dossier.convention_status = ConventionStatus.ENVOYEE
            dossier.save(update_fields=["convention_status"])
            PartnershipTimelineEntry.objects.create(
                dossier=dossier, author=author, label="Convention envoyée pour signature.", kind=Kind.SYSTEM
            )
        elif from_step == Step.SIGNATURE_CONVENTION:
            label = "Convention signée — paiement initial attendu." if dossier.requires_payment else "Aucun paiement requis pour ce dossier."
            PartnershipTimelineEntry.objects.create(dossier=dossier, author=author, label=label, kind=Kind.SYSTEM)
        elif from_step == Step.PAIEMENT_INITIAL:
            PartnershipTimelineEntry.objects.create(
                dossier=dossier, author=author, label="Dossier transféré aux équipes de production.", kind=Kind.SYSTEM
            )
        elif from_step == Step.SUPPORTS_COMMUNICATION:
            PartnershipTask.objects.create(dossier=dossier, label="Installation sur site")
            PartnershipTask.objects.create(dossier=dossier, label="Suivi terrain le jour J")
            PartnershipTimelineEntry.objects.create(
                dossier=dossier, author=author, label="Actions de déploiement et de suivi terrain créées.", kind=Kind.SYSTEM
            )
        elif from_step == Step.DEPLOIEMENT:
            PartnershipTimelineEntry.objects.create(
                dossier=dossier, author=author, label="Événement réalisé — bilan à préparer.", kind=Kind.SYSTEM
            )
        elif from_step == Step.BILAN:
            PartnershipTimelineEntry.objects.create(dossier=dossier, author=author, label="Dossier clôturé.", kind=Kind.SYSTEM)

    @action(detail=True, methods=["post"], url_path="advance")
    def advance(self, request, pk=None):
        dossier = self.get_object()
        current_index = STEP_ORDER.index(dossier.current_step)
        if current_index + 1 >= len(STEP_ORDER):
            return Response({"detail": "Ce dossier est déjà clôturé."}, status=400)

        if dossier.current_step == Step.SIGNATURE_CONVENTION and dossier.convention_status != ConventionStatus.SIGNEE:
            return Response({"detail": "La convention doit être signée avant de continuer."}, status=400)
        if dossier.current_step == Step.PAIEMENT_INITIAL and dossier.requires_payment and not dossier.payment_received:
            return Response({"detail": "Le paiement initial n'a pas encore été reçu."}, status=400)
        if dossier.current_step == Step.BILAN and not dossier.bilan_valide:
            return Response({"detail": "Le bilan doit être déposé et validé avant de clôturer."}, status=400)

        self._apply_step_transition(dossier, dossier.current_step, request.user)

        next_step = STEP_ORDER[current_index + 1]
        dossier.current_step = next_step
        dossier.save(update_fields=["current_step"])
        PartnershipTimelineEntry.objects.create(
            dossier=dossier, author=request.user, label=f"Étape « {STEP_LABELS[next_step]} » démarrée.", kind=Kind.ACTION
        )
        return Response(PartnershipDossierSerializer(dossier, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="convention-status")
    def convention_status(self, request, pk=None):
        dossier = self.get_object()
        new_status = request.data.get("status")
        if new_status not in CONVENTION_STATUS_LABELS:
            return Response({"detail": "Statut invalide."}, status=400)
        dossier.convention_status = new_status
        dossier.save(update_fields=["convention_status"])
        PartnershipTimelineEntry.objects.create(
            dossier=dossier,
            author=request.user,
            label=f"Convention marquée « {CONVENTION_STATUS_LABELS[new_status]} ».",
            kind=Kind.ACTION,
        )
        return Response(PartnershipDossierSerializer(dossier, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="mark-payment-received")
    def mark_payment_received(self, request, pk=None):
        dossier = self.get_object()
        if not dossier.payment_received:
            dossier.payment_received = True
            dossier.save(update_fields=["payment_received"])
            PartnershipTimelineEntry.objects.create(
                dossier=dossier, author=request.user, label="Paiement initial reçu et enregistré.", kind=Kind.ACTION
            )
        return Response(PartnershipDossierSerializer(dossier, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="mark-bilan-valide")
    def mark_bilan_valide(self, request, pk=None):
        dossier = self.get_object()
        if not dossier.bilan_valide:
            dossier.bilan_valide = True
            dossier.save(update_fields=["bilan_valide"])
            PartnershipTimelineEntry.objects.create(
                dossier=dossier, author=request.user, label="Bilan déposé et validé.", kind=Kind.ACTION
            )
        return Response(PartnershipDossierSerializer(dossier, context={"request": request}).data)


class PartnershipTaskViewSet(viewsets.ModelViewSet):
    """Tâches de suivi d'un dossier partenariat — le frontend filtre via
    `?dossier=<id>` et ne fait que basculer `done`."""

    serializer_class = PartnershipTaskSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = PartnershipTask.objects.select_related("dossier").all()
        dossier_id = self.request.query_params.get("dossier")
        if dossier_id:
            queryset = queryset.filter(dossier_id=dossier_id)
        return queryset
