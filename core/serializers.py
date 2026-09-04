from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from core.models import (
    Contact,
    Division,
    DivisionObjective,
    Document,
    DocumentAnnotation,
    DocumentReview,
    DocumentVersion,
    Event,
    Interaction,
    Note,
    Notification,
    PartnershipDossier,
    PartnershipTask,
    PartnershipTimelineEntry,
    Prestation,
    Project,
    ProjectPayment,
    Task,
    User,
)


class UserSerializer(serializers.ModelSerializer):
    role_display = serializers.CharField(source="get_role_display", read_only=True)
    division_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "role",
            "role_display",
            "division",
            "division_name",
            "profile_picture",
            "is_active",
            "is_staff",
            "date_joined",
            "last_login",
        ]
        # `is_active` est en lecture seule : avec multipart/form-data (requis pour
        # l'upload de photo), un BooleanField absent est interprété par DRF comme
        # une case décochée (False), ce qui désactiverait le compte à chaque
        # création/édition si le champ était modifiable ici.
        read_only_fields = ["id", "is_staff", "is_active", "date_joined", "last_login"]

    def get_division_name(self, obj):
        return obj.division.name if obj.division else None

    def validate_role(self, value):
        if not value:
            return value
        queryset = User.objects.filter(role=value)
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        if value in User.UNIQUE_ROLES and queryset.exists():
            raise serializers.ValidationError(
                f"Cette fonction est déjà occupée par un autre utilisateur."
            )
        return value


class UserCreateSerializer(UserSerializer):
    # Mot de passe provisoire créé par l'admin (ex: "1234") — l'utilisateur le
    # change ensuite lui-même, d'où un minimum bas plutôt que la politique
    # stricte d'un mot de passe choisi par l'utilisateur final.
    password = serializers.CharField(write_only=True, min_length=4)

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ["password"]

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User.objects.create_user(password=password, **validated_data)
        return user


class ContactSerializer(serializers.ModelSerializer):
    contact_type_display = serializers.CharField(source="get_contact_type_display", read_only=True)
    entity_type_display = serializers.CharField(source="get_entity_type_display", read_only=True)
    stage_display = serializers.CharField(source="get_stage_display", read_only=True)
    assigned_to_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Contact
        fields = [
            "id",
            "contact_type",
            "contact_type_display",
            "entity_type",
            "entity_type_display",
            "name",
            "company",
            "sector",
            "email",
            "phone",
            "address",
            "source",
            "notes",
            "stage",
            "stage_display",
            "score",
            "next_followup_at",
            "assigned_to",
            "assigned_to_name",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
            "converted_at",
        ]
        # `assigned_to` par défaut = la personne qui enregistre le contact ;
        # `created_by` est un historique immuable. Les deux ne changent que via
        # l'action dédiée `transfer`, jamais par un PATCH direct du formulaire.
        # `converted_at` n'est posé que par l'action `convert`.
        read_only_fields = ["id", "assigned_to", "created_by", "created_at", "updated_at", "converted_at"]

    def get_assigned_to_name(self, obj):
        return obj.assigned_to.get_full_name() if obj.assigned_to else None

    def get_created_by_name(self, obj):
        return obj.created_by.get_full_name() if obj.created_by else None


class InteractionSerializer(serializers.ModelSerializer):
    interaction_type_display = serializers.CharField(source="get_interaction_type_display", read_only=True)
    stage_display = serializers.CharField(source="get_stage_display", read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Interaction
        fields = [
            "id",
            "contact",
            "interaction_type",
            "interaction_type_display",
            "stage",
            "stage_display",
            "title",
            "description",
            "occurred_at",
            "attachment",
            "created_by",
            "created_by_name",
            "created_at",
        ]
        read_only_fields = ["id", "stage", "created_by", "created_at"]

    def get_created_by_name(self, obj):
        return obj.created_by.get_full_name() if obj.created_by else None


class NoteSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Note
        fields = ["id", "contact", "text", "created_by", "created_by_name", "created_at", "updated_at"]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

    def get_created_by_name(self, obj):
        return obj.created_by.get_full_name() if obj.created_by else None


class TaskSerializer(serializers.ModelSerializer):
    task_type_display = serializers.CharField(source="get_task_type_display", read_only=True)
    priority_display = serializers.CharField(source="get_priority_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    assignee_name = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = [
            "id",
            "task_type",
            "task_type_display",
            "contact",
            "prestation",
            "label",
            "description",
            "due_at",
            "priority",
            "priority_display",
            "done",
            "status",
            "status_display",
            "assignee",
            "assignee_name",
            "created_by",
            "created_at",
        ]
        read_only_fields = ["id", "created_by", "created_at"]

    def get_assignee_name(self, obj):
        return obj.assignee.get_full_name() if obj.assignee else None

    def validate(self, attrs):
        task_type = attrs.get("task_type", getattr(self.instance, "task_type", Task.TaskType.CONTACT))
        contact = attrs.get("contact", getattr(self.instance, "contact", None))
        prestation = attrs.get("prestation", getattr(self.instance, "prestation", None))

        if task_type == Task.TaskType.CONTACT:
            if not contact or prestation:
                raise serializers.ValidationError(
                    "Une tâche de suivi contact doit avoir un contact et aucune prestation."
                )
        else:
            if not prestation or contact:
                raise serializers.ValidationError(
                    "Une tâche de prestation doit avoir une prestation et aucun contact."
                )
        return attrs


class DocumentReviewSerializer(serializers.ModelSerializer):
    decision_display = serializers.CharField(source="get_decision_display", read_only=True)
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = DocumentReview
        fields = ["id", "author", "author_name", "decision", "decision_display", "comment", "created_at"]
        read_only_fields = fields

    def get_author_name(self, obj):
        return obj.author.get_full_name() if obj.author else None


class DocumentAnnotationSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = DocumentAnnotation
        fields = ["id", "version", "kind", "x", "y", "width", "height", "comment", "author", "author_name", "resolved", "created_at"]
        read_only_fields = ["id", "author", "author_name", "created_at"]

    def get_author_name(self, obj):
        return obj.author.get_full_name() if obj.author else None


class DocumentVersionSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.SerializerMethodField()
    annotations = DocumentAnnotationSerializer(many=True, read_only=True)

    class Meta:
        model = DocumentVersion
        fields = ["id", "file", "uploaded_by", "uploaded_by_name", "uploaded_at", "annotations"]
        read_only_fields = ["id", "file", "uploaded_by", "uploaded_by_name", "uploaded_at"]

    def get_uploaded_by_name(self, obj):
        return obj.uploaded_by.get_full_name() if obj.uploaded_by else None


class DocumentSerializer(serializers.ModelSerializer):
    owner_type_display = serializers.CharField(source="get_owner_type_display", read_only=True)
    document_type_display = serializers.CharField(source="get_document_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    uploaded_by_name = serializers.SerializerMethodField()
    contact_name = serializers.SerializerMethodField()
    project_name = serializers.SerializerMethodField()
    validators = serializers.PrimaryKeyRelatedField(many=True, queryset=User.objects.all(), required=False)
    validator_names = serializers.SerializerMethodField()
    validators_detail = serializers.SerializerMethodField()
    reviews = DocumentReviewSerializer(many=True, read_only=True)
    versions = DocumentVersionSerializer(many=True, read_only=True)

    class Meta:
        model = Document
        fields = [
            "id",
            "owner_type",
            "owner_type_display",
            "contact",
            "contact_name",
            "project",
            "project_name",
            "task",
            "prestation",
            "document_type",
            "document_type_display",
            "status",
            "status_display",
            "file",
            "link",
            "label",
            "uploaded_by",
            "uploaded_by_name",
            "validators",
            "validator_names",
            "validators_detail",
            "reviews",
            "versions",
            "uploaded_at",
        ]
        read_only_fields = ["id", "uploaded_by", "uploaded_at"]

    def get_uploaded_by_name(self, obj):
        return obj.uploaded_by.get_full_name() if obj.uploaded_by else None

    def get_contact_name(self, obj):
        return (obj.contact.company or obj.contact.name) if obj.contact else None

    def get_validator_names(self, obj):
        return [validator.get_full_name() for validator in obj.validators.all()]

    def get_validators_detail(self, obj):
        return [{"id": validator.id, "name": validator.get_full_name()} for validator in obj.validators.all()]

    def get_project_name(self, obj):
        return obj.project.name if obj.project else None

    def validate(self, attrs):
        owner_type = attrs.get("owner_type", getattr(self.instance, "owner_type", Document.OwnerType.CONTACT))
        contact = attrs.get("contact", getattr(self.instance, "contact", None))
        project = attrs.get("project", getattr(self.instance, "project", None))

        if owner_type == Document.OwnerType.CONTACT:
            if not contact or project:
                raise serializers.ValidationError(
                    "Un document de contact doit avoir un contact et aucun projet."
                )
        else:
            if not project or contact:
                raise serializers.ValidationError(
                    "Un document de projet doit avoir un projet et aucun contact."
                )

        if self.instance and "validators" in attrs:
            current_ids = set(self.instance.validators.values_list("id", flat=True))
            new_ids = {validator.id for validator in attrs["validators"]}
            if new_ids != current_ids:
                request = self.context.get("request")
                if request and request.user.id not in current_ids:
                    raise serializers.ValidationError(
                        {"validators": "Seul un validateur déjà désigné peut modifier la liste des validateurs."}
                    )
                status_value = attrs.get("status", self.instance.status)
                if status_value != Document.Status.A_VALIDER:
                    raise serializers.ValidationError(
                        {"validators": "Impossible de modifier les validateurs une fois le document traité."}
                    )

        file_value = attrs.get("file", getattr(self.instance, "file", None))
        link_value = attrs.get("link", getattr(self.instance, "link", ""))
        if not self.instance and not file_value and not link_value:
            raise serializers.ValidationError("Un fichier ou un lien est requis.")

        return attrs


class EventSerializer(serializers.ModelSerializer):
    event_type_display = serializers.CharField(source="get_event_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            "id",
            "contact",
            "event_type",
            "event_type_display",
            "title",
            "starts_at",
            "location",
            "status",
            "status_display",
            "original_starts_at",
            "created_by",
            "created_by_name",
            "created_at",
        ]
        read_only_fields = ["id", "original_starts_at", "created_by", "created_at"]

    def get_created_by_name(self, obj):
        return obj.created_by.get_full_name() if obj.created_by else None


class NotificationSerializer(serializers.ModelSerializer):
    contact_name = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = ["id", "message", "contact", "contact_name", "is_read", "created_at"]
        read_only_fields = ["id", "message", "contact", "contact_name", "created_at"]

    def get_contact_name(self, obj):
        return (obj.contact.company or obj.contact.name) if obj.contact else None


class DivisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Division
        fields = ["id", "name"]


class DivisionObjectiveSerializer(serializers.ModelSerializer):
    division_name = serializers.CharField(source="division.name", read_only=True)
    set_by_name = serializers.SerializerMethodField()

    class Meta:
        model = DivisionObjective
        fields = ["id", "division", "division_name", "month", "amount", "set_by", "set_by_name", "created_at", "updated_at"]
        read_only_fields = ["id", "set_by", "created_at", "updated_at"]

    def get_set_by_name(self, obj):
        return obj.set_by.get_full_name() if obj.set_by else None


class PrestationSerializer(serializers.ModelSerializer):
    division_name = serializers.SerializerMethodField()

    class Meta:
        model = Prestation
        fields = ["id", "project", "division", "division_name", "label", "deadline", "note"]
        read_only_fields = ["id", "project"]

    def get_division_name(self, obj):
        return obj.division.name if obj.division else None


class ProjectPaymentSerializer(serializers.ModelSerializer):
    method_display = serializers.CharField(source="get_method_display", read_only=True)
    recorded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ProjectPayment
        fields = [
            "id",
            "project",
            "amount",
            "method",
            "method_display",
            "note",
            "recorded_by",
            "recorded_by_name",
            "paid_at",
            "created_at",
        ]
        read_only_fields = ["id", "recorded_by", "created_at"]

    def get_recorded_by_name(self, obj):
        return obj.recorded_by.get_full_name() if obj.recorded_by else None


class ProjectSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    priority_display = serializers.CharField(source="get_priority_display", read_only=True)
    client_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    collected_amount = serializers.SerializerMethodField()
    prestations = PrestationSerializer(many=True, required=False)

    class Meta:
        model = Project
        fields = [
            "id",
            "kind",
            "kind_display",
            "client",
            "client_name",
            "name",
            "description",
            "deadline",
            "priority",
            "priority_display",
            "budget",
            "probability",
            "requires_deposit",
            "deposit_amount",
            "deposit_decided",
            "deposit_received",
            "final_payment_received",
            "collected_amount",
            "status",
            "status_display",
            "prestations",
            "converted_at",
            "created_by",
            "created_by_name",
            "created_at",
        ]
        read_only_fields = ["id", "converted_at", "created_by", "created_at"]

    def get_client_name(self, obj):
        # L'entreprise fait foi si elle est renseignée — un contact
        # PARTICULIER n'en a pas, d'où le repli sur son nom propre (même
        # convention que partout côté frontend : `contact.company || contact.name`).
        return obj.client.company or obj.client.name

    def get_created_by_name(self, obj):
        return obj.created_by.get_full_name() if obj.created_by else None

    def get_collected_amount(self, obj):
        # Somme en Python plutôt qu'un .aggregate() : exploite le
        # prefetch_related("payments") du queryset (ProjectViewSet) au lieu
        # d'émettre une requête par projet listé.
        total = sum((p.amount for p in obj.payments.all()), Decimal("0"))
        return str(total)

    def validate(self, attrs):
        kind = attrs.get("kind", getattr(self.instance, "kind", Project.Kind.PROJET))
        deadline = attrs.get("deadline", getattr(self.instance, "deadline", None))
        budget = attrs.get("budget", getattr(self.instance, "budget", None))
        prestations = attrs.get("prestations")

        if prestations is not None:
            for prestation in prestations:
                if deadline and prestation["deadline"] > deadline:
                    raise serializers.ValidationError(
                        {
                            "prestations": (
                                "L'échéance d'une prestation ne peut pas dépasser "
                                f"l'échéance globale du projet ({deadline})."
                            )
                        }
                    )

        if kind == Project.Kind.PROJET:
            if not deadline:
                raise serializers.ValidationError(
                    {"deadline": "L'échéance est requise pour un projet confirmé."}
                )
            if budget is None:
                raise serializers.ValidationError(
                    {"budget": "Le budget est requis pour un projet confirmé."}
                )
            prestation_count = (
                len(prestations) if prestations is not None else (self.instance.prestations.count() if self.instance else 0)
            )
            if prestation_count == 0:
                raise serializers.ValidationError(
                    {"prestations": "Un projet confirmé doit contenir au moins une prestation."}
                )

        requires_deposit = attrs.get("requires_deposit", getattr(self.instance, "requires_deposit", False))
        deposit_amount = attrs.get("deposit_amount", getattr(self.instance, "deposit_amount", None))

        if requires_deposit:
            if not deposit_amount:
                raise serializers.ValidationError(
                    {"deposit_amount": "Le montant de l'acompte est requis lorsqu'un acompte est demandé."}
                )
            if budget and deposit_amount > budget:
                raise serializers.ValidationError(
                    {"deposit_amount": "Le montant de l'acompte ne peut pas dépasser le budget du projet."}
                )
        else:
            attrs["deposit_amount"] = None

        deposit_received = attrs.get("deposit_received", getattr(self.instance, "deposit_received", False))
        if kind == Project.Kind.PROJET and requires_deposit and not deposit_received:
            raise serializers.ValidationError(
                {"deposit_received": "Le projet ne peut démarrer tant que l'acompte requis n'a pas été reçu."}
            )

        accounting_roles = {User.Role.COMPTABLE_GENERAL, User.Role.ASSISTANT_COMPTABLE, User.Role.ADMIN}
        request = self.context.get("request")

        if "deposit_received" in attrs and attrs["deposit_received"] != getattr(self.instance, "deposit_received", False):
            if request and request.user.role not in accounting_roles:
                raise serializers.ValidationError(
                    {"deposit_received": "Seule la Comptabilité peut confirmer l'encaissement de l'acompte."}
                )

        if "final_payment_received" in attrs and attrs["final_payment_received"] != getattr(
            self.instance, "final_payment_received", False
        ):
            if request and request.user.role not in accounting_roles:
                raise serializers.ValidationError(
                    {"final_payment_received": "Seule la Comptabilité peut confirmer l'encaissement du paiement final."}
                )

        return attrs

    def create(self, validated_data):
        prestations_data = validated_data.pop("prestations", [])
        project = Project.objects.create(**validated_data)
        Prestation.objects.bulk_create(
            [Prestation(project=project, **prestation_data) for prestation_data in prestations_data]
        )
        return project

    def update(self, instance, validated_data):
        prestations_data = validated_data.pop("prestations", None)
        was_opportunity = instance.kind == Project.Kind.OPPORTUNITE
        instance = super().update(instance, validated_data)
        if was_opportunity and instance.kind == Project.Kind.PROJET:
            instance.converted_at = timezone.now()
            instance.save(update_fields=["converted_at"])
        if prestations_data is not None:
            instance.prestations.all().delete()
            Prestation.objects.bulk_create(
                [Prestation(project=instance, **prestation_data) for prestation_data in prestations_data]
            )
        return instance


class PartnershipTimelineEntrySerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = PartnershipTimelineEntry
        fields = ["id", "author", "author_name", "label", "kind", "created_at"]
        read_only_fields = fields

    def get_author_name(self, obj):
        return obj.author.get_full_name() if obj.author else None


class PartnershipTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = PartnershipTask
        fields = ["id", "dossier", "label", "done", "created_at"]
        read_only_fields = ["id", "dossier", "label", "created_at"]


class PartnershipDossierSerializer(serializers.ModelSerializer):
    current_step_display = serializers.CharField(source="get_current_step_display", read_only=True)
    convention_status_display = serializers.CharField(source="get_convention_status_display", read_only=True)
    partenaire_name = serializers.SerializerMethodField()
    contact_name = serializers.SerializerMethodField()
    head_marketing_name = serializers.SerializerMethodField()
    timeline = PartnershipTimelineEntrySerializer(many=True, read_only=True)
    tasks = PartnershipTaskSerializer(many=True, read_only=True)

    class Meta:
        model = PartnershipDossier
        fields = [
            "id",
            "reference",
            "partenaire",
            "partenaire_name",
            "contact_name",
            "evenement",
            "evenement_debut",
            "evenement_fin",
            "montant",
            "current_step",
            "current_step_display",
            "urgent",
            "head_marketing",
            "head_marketing_name",
            "requires_payment",
            "payment_received",
            "convention_status",
            "convention_status_display",
            "bilan_valide",
            "created_by",
            "created_at",
            "timeline",
            "tasks",
        ]
        read_only_fields = [
            "id",
            "reference",
            "current_step",
            "urgent",
            "head_marketing",
            "payment_received",
            "convention_status",
            "bilan_valide",
            "created_by",
            "created_at",
        ]

    def get_partenaire_name(self, obj):
        return obj.partenaire.company or obj.partenaire.name

    def get_contact_name(self, obj):
        return obj.partenaire.name

    def get_head_marketing_name(self, obj):
        return obj.head_marketing.get_full_name() if obj.head_marketing else None


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Mot de passe actuel incorrect.")
        return value
