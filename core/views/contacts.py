from datetime import timedelta

from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from core.models import Contact, Notification, User
from core.serializers import ContactSerializer


class ContactViewSet(viewsets.ModelViewSet):
    """Table unique pour prospects/clients/partenaires : le frontend filtre
    via `?contact_type=PROSPECT|CLIENT|PARTENAIRE`. À la création, le
    commercial assigné est toujours la personne qui enregistre le contact
    (voir `perform_create`) ; il ne change ensuite que via `transfer`."""

    serializer_class = ContactSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Contact.objects.select_related("assigned_to", "created_by").all()
        contact_type = self.request.query_params.get("contact_type")
        if contact_type:
            queryset = queryset.filter(contact_type=contact_type)
        return queryset

    def perform_create(self, serializer):
        extra = {"created_by": self.request.user, "assigned_to": self.request.user}
        contact_type = serializer.validated_data.get("contact_type")
        # Un client créé directement (sans passer par la conversion d'un
        # prospect) doit déjà porter les marqueurs de conversion, sinon il
        # resterait affiché comme "Prise de Contact".
        if contact_type == Contact.ContactType.CLIENT:
            extra["stage"] = Contact.Stage.CONVERSION_CLIENT
            extra["converted_at"] = timezone.now()
        # Un nouveau prospect doit toujours avoir une relance programmée par
        # défaut, pour qu'aucun ne soit oublié dans les 72h suivant sa saisie.
        elif contact_type == Contact.ContactType.PROSPECT:
            extra["next_followup_at"] = timezone.now() + timedelta(hours=72)
        serializer.save(**extra)

    @action(detail=True, methods=["post"], url_path="transfer")
    def transfer(self, request, pk=None):
        contact = self.get_object()
        try:
            new_assignee = User.objects.get(
                pk=request.data.get("assigned_to"), role=User.Role.COMMERCIAL, is_active=True
            )
        except (User.DoesNotExist, ValueError, TypeError):
            return Response({"detail": "Commercial introuvable."}, status=400)

        previous_assignee = contact.assigned_to
        contact.assigned_to = new_assignee
        contact.save(update_fields=["assigned_to"])

        Notification.objects.create(
            recipient=new_assignee,
            message=f"Le prospect « {contact.name} » vous a été affecté.",
            contact=contact,
        )
        if previous_assignee and previous_assignee != new_assignee:
            Notification.objects.create(
                recipient=previous_assignee,
                message=f"Vous n'êtes plus en charge du prospect « {contact.name} ».",
                contact=contact,
            )
        return Response(ContactSerializer(contact, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="convert")
    def convert(self, request, pk=None):
        contact = self.get_object()
        if contact.contact_type != Contact.ContactType.PROSPECT:
            return Response({"detail": "Seul un prospect peut être converti en client."}, status=400)

        contact.contact_type = Contact.ContactType.CLIENT
        contact.stage = Contact.Stage.CONVERSION_CLIENT
        contact.converted_at = timezone.now()
        contact.save(update_fields=["contact_type", "stage", "converted_at"])
        return Response(ContactSerializer(contact, context={"request": request}).data)
    
