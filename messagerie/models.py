from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class Conversation(models.Model):
    """Un canal de groupe ou une conversation directe entre deux personnes.

    App volontairement autonome et réutilisable telle quelle d'un projet à
    l'autre : elle ne connaît que `settings.AUTH_USER_MODEL`, jamais les
    modèles métier du projet hôte (équipes, divisions, organisations...).
    Un projet qui veut provisionner automatiquement un canal pour l'un de
    ses propres regroupements (ex: une division) le fait en pointant
    `linked_object` vers l'instance concernée via la `GenericForeignKey`
    ci-dessous, côté code du projet — cette app n'a besoin d'en rien savoir.
    """

    class Kind(models.TextChoices):
        GROUP = "GROUP", "Groupe"
        DIRECT = "DIRECT", "Message direct"

    kind = models.CharField("type", max_length=10, choices=Kind.choices)
    # Nom affiché pour un groupe ; vide pour un message direct (le frontend
    # affiche alors le nom de l'interlocuteur).
    name = models.CharField("nom", max_length=150, blank=True)

    # Lien générique optionnel vers un objet du projet hôte (ex: une
    # Division) — permet à ce dernier de retrouver/synchroniser "le canal de
    # tel regroupement" sans que cette app ait à connaître son modèle.
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    linked_object = GenericForeignKey("content_type", "object_id")

    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        verbose_name="participants",
        through="ConversationParticipant",
        related_name="conversations",
    )
    created_at = models.DateTimeField("créée le", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name or f"Conversation #{self.pk}"


class ConversationParticipant(models.Model):
    """Table intermédiaire — porte `last_read_at`, qui sert à calculer le
    nombre de messages non lus par utilisateur et par conversation."""

    conversation = models.ForeignKey(Conversation, related_name="memberships", on_delete=models.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="conversation_memberships", on_delete=models.CASCADE
    )
    last_read_at = models.DateTimeField("lu jusqu'au", null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["conversation", "user"], name="unique_conversation_participant")
        ]


class Message(models.Model):
    """Un message dans une conversation — texte, pièce jointe, ou les deux."""

    conversation = models.ForeignKey(Conversation, verbose_name="conversation", related_name="messages", on_delete=models.CASCADE)
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="expéditeur",
        related_name="sent_messages",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    text = models.TextField("message", blank=True)
    attachment = models.FileField("pièce jointe", upload_to="message_attachments/", blank=True, null=True)
    created_at = models.DateTimeField("envoyé le", auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.sender} — {self.text[:40]}"
