from rest_framework import serializers

from messagerie.models import Conversation, Message


class MessagingUserSerializer(serializers.Serializer):
    """Représentation minimale d'un participant — volontairement limitée aux
    champs qu'`AbstractUser` garantit toujours, plus `profile_picture` en
    best-effort (`getattr`) pour les projets qui l'ont sans en dépendre pour
    ceux qui ne l'ont pas. `serializers.Serializer` plutôt que ModelSerializer :
    ça découple complètement cette app du modèle User concret du projet hôte."""

    id = serializers.IntegerField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    email = serializers.EmailField()
    profile_picture = serializers.SerializerMethodField()

    def get_profile_picture(self, obj):
        picture = getattr(obj, "profile_picture", None)
        if not picture:
            return None
        try:
            url = picture.url
        except ValueError:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request else url


class MessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = ["id", "conversation", "sender", "sender_name", "text", "attachment", "created_at"]
        read_only_fields = ["id", "sender", "created_at"]

    def get_sender_name(self, obj):
        return obj.sender.get_full_name() if obj.sender else None

    def validate(self, attrs):
        text = (attrs.get("text") or "").strip()
        # `attachment` peut être absent d'un PATCH partiel sans texte modifié —
        # on ne regarde l'instance existante que pour ce cas-là.
        attachment = attrs.get("attachment", getattr(self.instance, "attachment", None))
        if not text and not attachment:
            raise serializers.ValidationError("Le message doit contenir du texte ou une pièce jointe.")
        return attrs


class ConversationSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    display_name = serializers.SerializerMethodField()
    participants = MessagingUserSerializer(many=True, read_only=True)
    other_participant = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            "id",
            "kind",
            "kind_display",
            "name",
            "display_name",
            "participants",
            "other_participant",
            "last_message",
            "unread_count",
            "created_at",
        ]
        read_only_fields = fields

    def get_other_participant(self, obj):
        if obj.kind != Conversation.Kind.DIRECT:
            return None
        request = self.context.get("request")
        if not request:
            return None
        other = next((p for p in obj.participants.all() if p.pk != request.user.pk), None)
        return MessagingUserSerializer(other, context=self.context).data if other else None

    def get_display_name(self, obj):
        if obj.kind == Conversation.Kind.GROUP:
            return obj.name
        other = self.get_other_participant(obj)
        return f"{other['first_name']} {other['last_name']}".strip() if other else obj.name

    def get_last_message(self, obj):
        message = obj.messages.order_by("-created_at").first()
        return MessageSerializer(message).data if message else None

    def get_unread_count(self, obj):
        request = self.context.get("request")
        if not request:
            return 0
        membership = next((m for m in obj.memberships.all() if m.user_id == request.user.pk), None)
        if not membership:
            return 0
        messages = [m for m in obj.messages.all() if m.sender_id != request.user.pk]
        if membership.last_read_at:
            messages = [m for m in messages if m.created_at > membership.last_read_at]
        return len(messages)
