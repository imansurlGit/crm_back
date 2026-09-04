from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import Document, DocumentAnnotation, DocumentReview, DocumentVersion, Notification
from core.serializers import DocumentAnnotationSerializer, DocumentSerializer

DECISION_LABELS = {
    DocumentReview.Decision.VALIDE: "validé",
    DocumentReview.Decision.MODIFICATIONS_DEMANDEES: "renvoyé pour modifications",
    DocumentReview.Decision.REJETE: "rejeté",
}


class DocumentViewSet(viewsets.ModelViewSet):
    """Mini-GED de l'application : le frontend filtre via `?contact=<id>`,
    `?project=<id>`, `?task=<id>` (soumissions liées à une tâche précise),
    `?prestation=<id>` (briefs/références joints lors de l'affectation d'une
    prestation à une division), `?validator=<id>` (documents où l'utilisateur
    donné doit se prononcer — Centre de validation) ou `?uploaded_by=<id>`
    (mes propres soumissions — pages "Mes validations")."""

    serializer_class = DocumentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Document.objects.select_related(
            "contact", "project", "task", "prestation", "uploaded_by"
        ).prefetch_related("validators", "reviews__author", "versions__uploaded_by")
        contact_id = self.request.query_params.get("contact")
        if contact_id:
            queryset = queryset.filter(contact_id=contact_id)
        project_id = self.request.query_params.get("project")
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        task_id = self.request.query_params.get("task")
        if task_id:
            queryset = queryset.filter(task_id=task_id)
        prestation_id = self.request.query_params.get("prestation")
        if prestation_id:
            queryset = queryset.filter(prestation_id=prestation_id)
        validator_id = self.request.query_params.get("validator")
        if validator_id:
            queryset = queryset.filter(validators__id=validator_id)
        uploaded_by_id = self.request.query_params.get("uploaded_by")
        if uploaded_by_id:
            queryset = queryset.filter(uploaded_by_id=uploaded_by_id)
        return queryset.distinct()

    def perform_create(self, serializer):
        instance = serializer.save(uploaded_by=self.request.user)
        if instance.file:
            DocumentVersion.objects.create(document=instance, file=instance.file, uploaded_by=self.request.user)
        validators = list(instance.validators.all())
        if validators:
            DocumentReview.objects.create(document=instance, author=self.request.user, decision=DocumentReview.Decision.SOUMIS)
        owner_label = instance.contact.name if instance.contact else instance.project.name if instance.project else None
        for validator in validators:
            message = f"« {instance.label or instance.get_document_type_display()} » soumis pour validation"
            if owner_label:
                message += f" ({owner_label})"
            Notification.objects.create(recipient=validator, message=message[:255], contact=instance.contact)

    def _all_validators_approved(self, document):
        """Vrai si chaque validateur désigné a rendu VALIDE comme dernière
        décision de la soumission en cours (les avis d'un envoi précédent,
        avant le dernier SOUMIS, ne comptent pas)."""
        last_soumis = document.reviews.filter(decision=DocumentReview.Decision.SOUMIS).order_by("created_at").last()
        round_reviews = document.reviews.exclude(decision=DocumentReview.Decision.SOUMIS).order_by("created_at")
        if last_soumis:
            round_reviews = round_reviews.filter(created_at__gte=last_soumis.created_at)
        latest_by_author = {}
        for entry in round_reviews:
            latest_by_author[entry.author_id] = entry.decision
        validator_ids = set(document.validators.values_list("id", flat=True))
        return bool(validator_ids) and all(
            latest_by_author.get(validator_id) == DocumentReview.Decision.VALIDE for validator_id in validator_ids
        )

    @action(detail=True, methods=["post"], url_path="review")
    def review(self, request, pk=None):
        document = self.get_object()
        if request.user not in document.validators.all():
            return Response({"detail": "Vous n'êtes pas validateur de ce document."}, status=403)
        if document.status != Document.Status.A_VALIDER:
            return Response({"detail": "Ce document n'est pas en attente de validation."}, status=400)

        decision = request.data.get("decision")
        valid_decisions = {
            DocumentReview.Decision.VALIDE,
            DocumentReview.Decision.MODIFICATIONS_DEMANDEES,
            DocumentReview.Decision.REJETE,
        }
        if decision not in valid_decisions:
            return Response({"detail": "Décision invalide."}, status=400)

        comment = (request.data.get("comment") or "").strip()
        if decision != DocumentReview.Decision.VALIDE and not comment:
            return Response({"detail": "Un commentaire est requis pour demander une modification ou rejeter."}, status=400)

        DocumentReview.objects.create(document=document, author=request.user, decision=decision, comment=comment)

        # Un rejet ou une demande de modification d'un seul validateur clôt
        # immédiatement le circuit ; une validation n'y met fin que si TOUS
        # les validateurs désignés ont eux aussi validé cette soumission.
        closes_review = decision != DocumentReview.Decision.VALIDE or self._all_validators_approved(document)
        if closes_review:
            document.status = decision
            document.save(update_fields=["status"])

            if document.uploaded_by:
                message = f"Votre document « {document.label or document.get_document_type_display()} » a été {DECISION_LABELS[decision]}."
                Notification.objects.create(recipient=document.uploaded_by, message=message[:255], contact=document.contact)

        return Response(DocumentSerializer(document, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="resubmit")
    def resubmit(self, request, pk=None):
        document = self.get_object()
        if request.user != document.uploaded_by:
            return Response({"detail": "Seul l'auteur de la soumission peut la renvoyer."}, status=403)
        if document.status != Document.Status.MODIFICATIONS_DEMANDEES:
            return Response({"detail": "Ce document n'attend pas de renvoi."}, status=400)

        new_file = request.FILES.get("file")
        if new_file:
            document.file = new_file
            DocumentVersion.objects.create(document=document, file=new_file, uploaded_by=request.user)
        document.status = Document.Status.A_VALIDER
        document.save()

        comment = (request.data.get("comment") or "").strip()
        DocumentReview.objects.create(document=document, author=request.user, decision=DocumentReview.Decision.SOUMIS, comment=comment)

        owner_label = document.contact.name if document.contact else document.project.name if document.project else None
        for validator in document.validators.all():
            message = f"« {document.label or document.get_document_type_display()} » renvoyé pour validation"
            if owner_label:
                message += f" ({owner_label})"
            Notification.objects.create(recipient=validator, message=message[:255], contact=document.contact)

        return Response(DocumentSerializer(document, context={"request": request}).data)


class DocumentAnnotationViewSet(viewsets.ModelViewSet):
    """Repères/cercles laissés par les validateurs sur l'aperçu d'une version
    de document — le frontend filtre via `?version=<id>`. Seuls les
    validateurs désignés du document peuvent en ajouter ou les résoudre,
    comme pour la décision de validation elle-même."""

    serializer_class = DocumentAnnotationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = DocumentAnnotation.objects.select_related("author", "version__document")
        version_id = self.request.query_params.get("version")
        if version_id:
            queryset = queryset.filter(version_id=version_id)
        return queryset

    def _ensure_validator(self, document):
        if self.request.user not in document.validators.all():
            raise PermissionDenied("Seul un validateur désigné peut annoter ce document.")

    def perform_create(self, serializer):
        version = serializer.validated_data["version"]
        self._ensure_validator(version.document)
        serializer.save(author=self.request.user)

    def perform_update(self, serializer):
        self._ensure_validator(serializer.instance.version.document)
        serializer.save()

    def perform_destroy(self, instance):
        self._ensure_validator(instance.version.document)
        instance.delete()
