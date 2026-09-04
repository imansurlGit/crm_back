from rest_framework.permissions import BasePermission

from core.models import User

# Fonctions habilitées à créer/modifier/supprimer des comptes utilisateurs.
# Le DG est un titre métier, pas un accès technique : il n'y figure pas.
USER_MANAGEMENT_ROLES = {User.Role.ADMIN, User.Role.ADCH}


class CanManageUsers(BasePermission):
    """Autorise la gestion des utilisateurs (CRUD) à l'Administrateur et à la
    personne en charge du capital humain (ADCH). Les autres utilisateurs
    authentifiés ne peuvent que consulter/modifier leur propre profil (voir
    la vue `me`)."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role in USER_MANAGEMENT_ROLES)
