from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from core.models import Notification, Task
from core.serializers import TaskSerializer


class TaskViewSet(viewsets.ModelViewSet):
    """Tâches à faire sur un contact (`?contact=<id>`) ou sur une prestation
    (`?prestation=<id>`). Assigner une tâche à quelqu'un le notifie (voir
    `_notify_assignee_if_newly_assigned`), à l'image de l'affectation d'une
    prestation à une division (`PrestationViewSet`)."""

    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Task.objects.select_related("created_by", "contact", "prestation__project", "assignee").all()
        contact_id = self.request.query_params.get("contact")
        if contact_id:
            queryset = queryset.filter(contact_id=contact_id)
        prestation_id = self.request.query_params.get("prestation")
        if prestation_id:
            queryset = queryset.filter(prestation_id=prestation_id)
        return queryset

    def perform_create(self, serializer):
        instance = serializer.save(created_by=self.request.user)
        self._notify_assignee_if_newly_assigned(instance, previous_assignee=None)

    def perform_update(self, serializer):
        previous_assignee = serializer.instance.assignee
        instance = serializer.save()
        self._notify_assignee_if_newly_assigned(instance, previous_assignee)

    def _notify_assignee_if_newly_assigned(self, task, previous_assignee):
        if not task.assignee or task.assignee == previous_assignee or task.assignee == self.request.user:
            return
        if task.prestation:
            message = f"La tâche « {task.label} » ({task.prestation.project.name}) vous a été assignée."
        else:
            message = f"La tâche « {task.label} » vous a été assignée."
        Notification.objects.create(recipient=task.assignee, message=message[:255])
