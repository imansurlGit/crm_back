from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from core.models import Division, Role, User
from messagerie.models import Conversation
from messagerie.views import ConversationViewSet as BaseConversationViewSet


def sync_default_conversations():
    """Garantit l'existence du canal « Général » et d'un canal par division,
    et tient leurs membres à jour (comptes actifs, affectation courante).

    Le module `messagerie` est une app générique et réutilisable : elle ne
    sait pas ce qu'est une « Division ». Ce provisionnement automatique est
    donc de la logique propre à Agence Iman, qui vit ici plutôt que dans
    l'app — le lien entre un canal et « sa » division passe par le champ
    générique `Conversation.linked_object`. Appelée à la demande depuis
    `ConversationViewSet.get_queryset` (plutôt que via des signaux), pour
    rester robuste à un reset des données (`reset.py`) sans dépendre de
    l'ordre de création des comptes/divisions.

    Le DG supervise toutes les divisions : il est donc membre de chaque
    canal de division, même s'il n'est rattaché à aucune (`User.division`
    reste `null` pour ce rôle)."""
    general, _ = Conversation.objects.get_or_create(
        kind=Conversation.Kind.GROUP, content_type=None, object_id=None, defaults={"name": "Général"}
    )
    general.participants.set(User.objects.filter(is_active=True))

    division_content_type = ContentType.objects.get_for_model(Division)
    for division in Division.objects.all():
        group, created = Conversation.objects.get_or_create(
            kind=Conversation.Kind.GROUP,
            content_type=division_content_type,
            object_id=division.pk,
            defaults={"name": division.name},
        )
        if not created and group.name != division.name:
            group.name = division.name
            group.save(update_fields=["name"])
        group.participants.set(
            User.objects.filter(is_active=True).filter(Q(division=division) | Q(role=Role.DG))
        )


class ConversationViewSet(BaseConversationViewSet):
    """Étend le ViewSet générique de `messagerie` en garantissant, à chaque
    liste, l'existence et la bonne composition des canaux par défaut
    d'Agence Iman (Général + un par division)."""

    def get_queryset(self):
        sync_default_conversations()
        return super().get_queryset()
