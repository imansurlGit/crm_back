from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("L'adresse email est obligatoire.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self._create_user(email, password, **extra_fields)

    def get_by_natural_key(self, email):
        return self.get(**{self.model.USERNAME_FIELD: email})


class Role(models.TextChoices):
    ADMIN = "ADMIN", "Administrateur"
    DG = "DG", "Directeur Général"
    ADCH = "ADCH", "Gestion du Capital Humain"
    CDV = "CDV", "Chef Division Ventes"
    CDM = "CDM", "Chef Division Marketing"
    CDN = "CDN", "Chef Division Numérique"
    COMMERCIAL = "COMMERCIAL", "Commercial"
    CHARGE_PARTENARIAT = "CHARGE_PARTENARIAT", "Chargé(e) de Partenariat"
    GRAPHISTE = "GRAPHISTE", "Graphiste"
    COMPTABLE_GENERAL = "COMPTABLE_GENERAL", "Comptable Général"
    ASSISTANT_COMPTABLE = "ASSISTANT_COMPTABLE", "Assistant Comptable"
    DEVELOPPEUR = "DEVELOPPEUR", "Développeur"
    RDW = "RDW", "Responsable Développement Web"
    RSI = "RSI", "Responsable Systèmes d'Information"
    VIP = "VIP", "Chef Division VIP"
    RESPONSABLE_VISIBILITE = "RESPONSABLE_VISIBILITE", "Responsable Visibilité"


# Fonctions n'ayant qu'un seul titulaire à la fois.
UNIQUE_ROLES = {
    Role.DG,
    Role.ADCH,
    Role.CDV,
    Role.CDM,
    Role.CDN,
    Role.COMPTABLE_GENERAL,
    Role.VIP,
    Role.RDW,
    Role.RSI,
    Role.RESPONSABLE_VISIBILITE,
}


class User(AbstractUser):
    Role = Role
    UNIQUE_ROLES = UNIQUE_ROLES

    username = None
    email = models.EmailField("adresse email", unique=True)
    role = models.CharField(
        "fonction", max_length=30, choices=Role.choices, null=True, blank=True
    )
    profile_picture = models.ImageField(
        "photo de profil", upload_to="profile_pictures/", blank=True, null=True
    )
    division = models.ForeignKey(
        "Division",
        verbose_name="division",
        related_name="users",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["role"],
                # Trié : `UNIQUE_ROLES` est un set, dont l'ordre d'itération
                # n'est pas garanti — sans tri, `makemigrations` génère une
                # migration parasite (réordonnancement de cette liste) à
                # chaque exécution.
                condition=Q(role__in=sorted(r.value for r in UNIQUE_ROLES)),
                name="unique_role_holder",
            )
        ]

    def clean(self):
        super().clean()
        if self.role in UNIQUE_ROLES:
            already_taken = (
                User.objects.filter(role=self.role).exclude(pk=self.pk).exists()
            )
            if already_taken:
                raise ValidationError(
                    {
                        "role": (
                            f"La fonction « {self.get_role_display()} » est déjà "
                            "occupée par un autre utilisateur."
                        )
                    }
                )

    def __str__(self):
        return self.get_full_name() or self.email


class Contact(models.Model):
    """Une seule table pour les prospects, clients et partenaires : les pages
    Prospection / Clients / Partenaires du frontend ne sont que ce même
    modèle filtré par `contact_type`. `INTERNE` est un cas particulier : un
    unique enregistrement représentant l'agence elle-même, utilisé comme
    `client` des projets internes — il n'apparaît dans aucune de ces pages
    puisqu'elles ne filtrent que PROSPECT/CLIENT/PARTENAIRE."""

    class ContactType(models.TextChoices):
        PROSPECT = "PROSPECT", "Prospect"
        CLIENT = "CLIENT", "Client"
        PARTENAIRE = "PARTENAIRE", "Partenaire"
        INTERNE = "INTERNE", "Interne (Agence)"

    class EntityType(models.TextChoices):
        PARTICULIER = "PARTICULIER", "Particulier"
        PME = "PME", "PME"
        INSTITUTION = "INSTITUTION", "Institution"
        GRANDE_ENTREPRISE = "GRANDE_ENTREPRISE", "Grande Entreprise"

    class Stage(models.TextChoices):
        PRISE_DE_CONTACT = "PRISE_DE_CONTACT", "Prise de Contact"
        QUALIFICATION = "QUALIFICATION", "Qualification"
        ECHANGES = "ECHANGES", "Échanges"
        CHIFFRAGE_OFFRE = "CHIFFRAGE_OFFRE", "Chiffrage & Offre"
        CONVERSION_CLIENT = "CONVERSION_CLIENT", "Conversion Client"

    contact_type = models.CharField("type de contact", max_length=20, choices=ContactType.choices)
    entity_type = models.CharField("type de prospect", max_length=20, choices=EntityType.choices)

    name = models.CharField("nom complet", max_length=150)
    company = models.CharField("entreprise / institution", max_length=150, blank=True)
    sector = models.CharField("secteur d'activité", max_length=100, blank=True)
    email = models.EmailField("email")
    phone = models.CharField("téléphone", max_length=30)
    address = models.CharField("adresse", max_length=200, blank=True)
    source = models.CharField("source du prospect", max_length=100, blank=True)
    notes = models.TextField("notes", blank=True)

    stage = models.CharField(
        "étape", max_length=30, choices=Stage.choices, default=Stage.PRISE_DE_CONTACT
    )
    score = models.PositiveSmallIntegerField("score", default=20)
    converted_at = models.DateTimeField("converti le", null=True, blank=True)

    assigned_to = models.ForeignKey(
        User,
        verbose_name="commercial assigné",
        related_name="assigned_contacts",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        User,
        verbose_name="enregistré par",
        related_name="created_contacts",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    next_followup_at = models.DateTimeField("prochaine relance", null=True, blank=True)

    created_at = models.DateTimeField("créé le", auto_now_add=True)
    updated_at = models.DateTimeField("mis à jour le", auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class Division(models.Model):
    """Division opérationnelle de l'agence (Ventes, Marketing, Numérique,
    Visibilité/Infrastructure/Production...). Le responsable de division
    (head) sera géré plus tard — pour l'instant, juste un nom."""

    name = models.CharField("nom", max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


# Rôle qui reçoit une notification quand une prestation est affectée à la
# division correspondante (voir `PrestationViewSet.perform_update`). En
# attendant un vrai champ "responsable" sur `Division` (cf. docstring
# ci-dessus), chaque rôle listé ici est de toute façon à titulaire unique
# (voir `UNIQUE_ROLES`), donc résoluble sans ambiguïté.
DIVISION_CHIEF_ROLES = {
    "Ventes": Role.CDV,
    "Marketing": Role.CDM,
    "Numérique": Role.CDN,
    "Visibilité, Infrastructure et Production": Role.VIP,
    "Comptabilité": Role.COMPTABLE_GENERAL,
}


class DivisionObjective(models.Model):
    """Objectif mensuel de chiffre d'affaires fixé par le DG pour une
    division (voir DgFinancePage.tsx côté frontend). `month` est toujours
    ramené au 1er du mois — sert de clé de période, comparable directement
    entre objectifs d'un même mois."""

    division = models.ForeignKey(Division, verbose_name="division", related_name="objectives", on_delete=models.CASCADE)
    month = models.DateField("mois")
    amount = models.DecimalField("objectif (FCFA)", max_digits=14, decimal_places=2)
    set_by = models.ForeignKey(User, verbose_name="fixé par", related_name="+", on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField("créé le", auto_now_add=True)
    updated_at = models.DateTimeField("modifié le", auto_now=True)

    class Meta:
        ordering = ["-month", "division__name"]
        constraints = [
            models.UniqueConstraint(fields=["division", "month"], name="unique_division_objective_per_month"),
        ]

    def save(self, *args, **kwargs):
        self.month = self.month.replace(day=1)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.division.name} — {self.month:%B %Y} — {self.amount}"


class Project(models.Model):
    """Un projet client : un ensemble de prestations, chacune confiée à uneGabarit — Fiche client
    division. Créé typiquement après conversion d'un prospect en client.

    `kind` distingue une opportunité (projet potentiel, champs flous : pas
    d'échéance ni de budget ni de prestations obligatoires) d'un projet
    confirmé — même table, même id, comme `Contact.contact_type` pour les
    prospects/clients. Le passage d'OPPORTUNITE à PROJET (voir
    `ProjectSerializer`) exige alors échéance, budget et au moins une
    prestation, et horodate `converted_at`."""

    class Kind(models.TextChoices):
        OPPORTUNITE = "OPPORTUNITE", "Opportunité"
        PROJET = "PROJET", "Projet"

    class Status(models.TextChoices):
        NOUVEAU = "NOUVEAU", "Nouveau"
        A_TRAITER = "A_TRAITER", "À traiter"
        EN_COURS = "EN_COURS", "En cours"
        EN_VALIDATION_INTERNE = "EN_VALIDATION_INTERNE", "En validation interne"
        EN_VALIDATION_CLIENT = "EN_VALIDATION_CLIENT", "En validation client"
        EN_CORRECTION = "EN_CORRECTION", "En correction"
        PRET_POUR_EXECUTION = "PRET_POUR_EXECUTION", "Prêt pour exécution"
        PRET_POUR_LIVRAISON = "PRET_POUR_LIVRAISON", "Prêt pour livraison"
        LIVRE = "LIVRE", "Livré"
        CLOTURE = "CLOTURE", "Clôturé"
        BLOQUE = "BLOQUE", "Bloqué"
        PERDUE = "PERDUE", "Perdue"

    class Priority(models.TextChoices):
        HIGH = "HIGH", "Élevée"
        MEDIUM = "MEDIUM", "Moyenne"
        LOW = "LOW", "Faible"

    kind = models.CharField(
        "type", max_length=15, choices=Kind.choices, default=Kind.PROJET
    )
    client = models.ForeignKey(
        Contact, verbose_name="client", related_name="projects", on_delete=models.CASCADE
    )
    name = models.CharField("nom du projet", max_length=200)
    description = models.TextField("description", blank=True)
    deadline = models.DateTimeField("échéance globale", null=True, blank=True)
    priority = models.CharField(
        "priorité", max_length=10, choices=Priority.choices, default=Priority.MEDIUM
    )
    budget = models.DecimalField("budget", max_digits=12, decimal_places=2, null=True, blank=True)
    probability = models.PositiveSmallIntegerField(
        "probabilité (%)",
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    requires_deposit = models.BooleanField("acompte requis", default=False)
    deposit_amount = models.DecimalField(
        "montant de l'acompte", max_digits=12, decimal_places=2, null=True, blank=True
    )
    # Distingue "pas encore répondu à la question de l'acompte" de "réponse
    # = non requis" (les deux se traduisent par requires_deposit=False) —
    # sans ce marqueur l'étape Acompte ne pourrait pas savoir si elle doit
    # encore poser la question ou afficher le résultat.
    deposit_decided = models.BooleanField("acompte : décision prise", default=False)
    # Coché uniquement par la Comptabilité (jamais par le commercial), une
    # fois l'acompte effectivement encaissé — voir `ProjectViewSet`.
    deposit_received = models.BooleanField("acompte reçu", default=False)
    final_payment_received = models.BooleanField("paiement final reçu", default=False)
    status = models.CharField(
        "statut", max_length=30, choices=Status.choices, default=Status.NOUVEAU
    )
    converted_at = models.DateTimeField("converti en projet le", null=True, blank=True)
    created_by = models.ForeignKey(
        User,
        verbose_name="créé par",
        related_name="projects",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField("créé le", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class ProjectPayment(models.Model):
    """Un encaissement réel sur un projet, enregistré par la Comptabilité.
    Permet un paiement échelonné en un nombre quelconque de fois plutôt que
    le seul schéma acompte/solde — `Project.deposit_received` et
    `final_payment_received` sont mis à jour automatiquement dès que la somme
    des paiements atteint le montant de l'acompte, puis le budget total (voir
    `ProjectPaymentViewSet`), pour ne rien casser du gating existant
    ("démarrer le projet", étape PAIEMENT_FINAL du dossier commercial)."""

    class Method(models.TextChoices):
        VIREMENT = "VIREMENT", "Virement bancaire"
        CHEQUE = "CHEQUE", "Chèque"
        ESPECES = "ESPECES", "Espèces"
        MOBILE_MONEY = "MOBILE_MONEY", "Mobile Money"

    project = models.ForeignKey(
        Project, verbose_name="projet", related_name="payments", on_delete=models.CASCADE
    )
    amount = models.DecimalField("montant", max_digits=12, decimal_places=2)
    method = models.CharField("mode de règlement", max_length=20, choices=Method.choices, default=Method.VIREMENT)
    note = models.CharField("note", max_length=200, blank=True)
    recorded_by = models.ForeignKey(
        User,
        verbose_name="enregistré par",
        related_name="recorded_payments",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    paid_at = models.DateTimeField("encaissé le")
    created_at = models.DateTimeField("créé le", auto_now_add=True)

    class Meta:
        ordering = ["-paid_at"]

    def __str__(self):
        return f"{self.project} — {self.amount}"


class Prestation(models.Model):
    """Un lot de travail au sein d'un projet. La division qui s'en charge
    n'est pas connue à la création du projet : elle est assignée plus tard,
    d'où `division` nullable. Son échéance ne peut pas dépasser l'échéance
    globale du projet (contrôle fait dans `PrestationSerializer`, pas ici,
    pour un message d'erreur clair renvoyé au formulaire)."""

    project = models.ForeignKey(
        Project, verbose_name="projet", related_name="prestations", on_delete=models.CASCADE
    )
    division = models.ForeignKey(
        Division,
        verbose_name="division",
        related_name="prestations",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    label = models.CharField("intitulé", max_length=200)
    deadline = models.DateTimeField("échéance")
    # Consignes du détenteur transmises au chef de division au moment de
    # l'affectation (voir `PrestationViewSet`) — affichées telles quelles
    # dans le poste de travail du chef (`PrestationChiefView.tsx`).
    note = models.TextField("consignes", blank=True)

    class Meta:
        ordering = ["deadline"]

    def __str__(self):
        return f"{self.label} ({self.division})" if self.division else self.label


class Document(models.Model):
    """Pièce jointe du mini-GED de l'application : devis/factures d'un
    contact, contrats/livrables d'un projet... Même modèle pour les deux
    usages, `owner_type` indique laquelle des deux FK ci-dessous est
    renseignée (contrôlé dans `DocumentSerializer`), comme pour `Task`.
    Distinct de `Interaction.attachment`, qui reste ponctuel à un échange."""

    class OwnerType(models.TextChoices):
        CONTACT = "CONTACT", "Contact"
        PROJECT = "PROJECT", "Projet"

    class DocumentType(models.TextChoices):
        CONTRAT = "CONTRAT", "Contrat"
        CONVENTION = "CONVENTION", "Convention"
        DEVIS = "DEVIS", "Devis"
        FACTURE = "FACTURE", "Facture"
        BRIEF = "BRIEF", "Brief"
        FICHE_BAT = "FICHE_BAT", "Fiche BAT"
        VISUEL = "VISUEL", "Visuel"
        PRESENTATION = "PRESENTATION", "Présentation"
        LIVRABLE_FINAL = "LIVRABLE_FINAL", "Livrable final"
        JUSTIFICATIF = "JUSTIFICATIF", "Justificatif"
        RAPPORT = "RAPPORT", "Rapport"

    class Status(models.TextChoices):
        A_VALIDER = "A_VALIDER", "À valider"
        VALIDE = "VALIDE", "Validé"
        MODIFICATIONS_DEMANDEES = "MODIFICATIONS_DEMANDEES", "Modifications demandées"
        REJETE = "REJETE", "Rejeté"
        PIECE_JOINTE = "PIECE_JOINTE", "Pièce jointe"

    owner_type = models.CharField(
        "rattaché à", max_length=10, choices=OwnerType.choices, default=OwnerType.CONTACT
    )
    contact = models.ForeignKey(
        Contact, verbose_name="contact", related_name="documents", on_delete=models.CASCADE, null=True, blank=True
    )
    project = models.ForeignKey(
        Project, verbose_name="projet", related_name="documents", on_delete=models.CASCADE, null=True, blank=True
    )
    # Optionnel — renseigné quand le document est le livrable d'une tâche de
    # prestation précise (ex : page "Traiter" du développeur), pour
    # retrouver l'historique de soumissions propre à cette tâche.
    task = models.ForeignKey(
        "Task", verbose_name="tâche", related_name="documents", on_delete=models.SET_NULL, null=True, blank=True
    )
    # Optionnel — renseigné quand le fichier est joint lors de l'affectation
    # d'une prestation à une division (brief, références visuelles...), pour
    # l'afficher dans le poste de travail du chef de division correspondant.
    prestation = models.ForeignKey(
        Prestation, verbose_name="prestation", related_name="documents", on_delete=models.SET_NULL, null=True, blank=True
    )
    document_type = models.CharField(
        "type de document", max_length=20, choices=DocumentType.choices
    )
    status = models.CharField(
        "statut", max_length=30, choices=Status.choices, default=Status.PIECE_JOINTE
    )
    # L'un des deux (fichier ou lien) est requis, jamais aucun — contrôlé
    # dans `DocumentSerializer.validate`. Un livrable de développeur est
    # généralement un lien (accès à un environnement, une PR...) plutôt
    # qu'un fichier.
    file = models.FileField("fichier", upload_to="documents/", blank=True)
    link = models.URLField("lien", blank=True)
    label = models.CharField("libellé", max_length=200, blank=True)
    uploaded_by = models.ForeignKey(
        User,
        verbose_name="ajouté par",
        related_name="documents",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    # Renseigné quand le document est soumis pour validation (ex : devis en
    # fin de cadrage) — qui doit se prononcer, pas qui l'a déjà fait (voir
    # `status` pour l'issue). Notifiés à la création (`DocumentViewSet`).
    validators = models.ManyToManyField(
        User, verbose_name="validateurs", related_name="documents_to_validate", blank=True
    )
    uploaded_at = models.DateTimeField("ajouté le", auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.label or self.file.name


class DocumentReview(models.Model):
    """Un point du cycle de relecture d'un `Document` soumis à validation :
    la soumission initiale (SOUMIS) puis chaque décision d'un validateur —
    reconstitue l'historique affiché au Centre de validation. N'existe que
    pour les documents effectivement soumis (avec au moins un validateur) ;
    un document interne sans validateur n'a pas d'entrée."""

    class Decision(models.TextChoices):
        SOUMIS = "SOUMIS", "Soumis"
        VALIDE = "VALIDE", "Validé"
        MODIFICATIONS_DEMANDEES = "MODIFICATIONS_DEMANDEES", "Modifications demandées"
        REJETE = "REJETE", "Rejeté"

    document = models.ForeignKey(
        Document, verbose_name="document", related_name="reviews", on_delete=models.CASCADE
    )
    author = models.ForeignKey(
        User, verbose_name="auteur", related_name="document_reviews", on_delete=models.SET_NULL, null=True, blank=True
    )
    decision = models.CharField("décision", max_length=30, choices=Decision.choices)
    comment = models.TextField("commentaire", blank=True)
    created_at = models.DateTimeField("le", auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.document} — {self.decision}"


class DocumentVersion(models.Model):
    """Historique des fichiers d'un `Document` — une entrée à la création,
    puis une de plus à chaque renvoi après des modifications demandées (voir
    `DocumentViewSet.resubmit`). `Document.file` reste le fichier courant ;
    ceci permet de retrouver les versions précédentes."""

    document = models.ForeignKey(
        Document, verbose_name="document", related_name="versions", on_delete=models.CASCADE
    )
    file = models.FileField("fichier", upload_to="documents/versions/")
    uploaded_by = models.ForeignKey(
        User, verbose_name="ajouté par", related_name="document_versions", on_delete=models.SET_NULL, null=True, blank=True
    )
    uploaded_at = models.DateTimeField("ajouté le", auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at"]

    def __str__(self):
        return f"{self.document} — {self.uploaded_at}"


class DocumentAnnotation(models.Model):
    """Repère ou cercle laissé par un validateur désigné sur l'aperçu d'une
    `DocumentVersion` — persisté pour que le déposant retrouve les remarques
    visuelles quand il rouvre le document, plutôt qu'une annotation locale
    perdue à la fermeture de l'onglet."""

    class Kind(models.TextChoices):
        PIN = "PIN", "Commentaire"
        CIRCLE = "CIRCLE", "Cercle"

    version = models.ForeignKey(
        DocumentVersion, verbose_name="version", related_name="annotations", on_delete=models.CASCADE
    )
    kind = models.CharField("type", max_length=10, choices=Kind.choices)
    x = models.FloatField("position x (%)")
    y = models.FloatField("position y (%)")
    width = models.FloatField("largeur (%)", null=True, blank=True)
    height = models.FloatField("hauteur (%)", null=True, blank=True)
    comment = models.TextField("commentaire")
    author = models.ForeignKey(
        User, verbose_name="auteur", related_name="document_annotations", on_delete=models.SET_NULL, null=True, blank=True
    )
    resolved = models.BooleanField("résolue", default=False)
    created_at = models.DateTimeField("créée le", auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.version} — {self.get_kind_display()}"


class Interaction(models.Model):
    """Un échange enregistré (appel, réunion, email) sur la fiche d'un
    contact — alimente à la fois l'historique et, via `occurred_at`, la
    frise chronologique affichée sur les pages de détail."""

    class InteractionType(models.TextChoices):
        CALL = "CALL", "Appel"
        MEETING = "MEETING", "Réunion"
        EMAIL = "EMAIL", "Email"
        MESSAGE = "MESSAGE", "Message"

    contact = models.ForeignKey(
        Contact, verbose_name="contact", related_name="interactions", on_delete=models.CASCADE
    )
    interaction_type = models.CharField(
        "type d'échange", max_length=20, choices=InteractionType.choices
    )
    # Capturé automatiquement depuis `contact.stage` à la création (voir
    # `InteractionViewSet.perform_create`) — permet de rattacher chaque
    # échange à l'étape du parcours où il a eu lieu, au lieu de le montrer
    # partout où l'étape courante se trouve désormais.
    stage = models.CharField(
        "étape du contact au moment de l'échange", max_length=30, choices=Contact.Stage.choices, null=True, blank=True
    )
    title = models.CharField("objet", max_length=200, blank=True)
    description = models.TextField("note", blank=True)
    occurred_at = models.DateTimeField("date de l'échange")
    attachment = models.FileField(
        "pièce jointe", upload_to="interaction_attachments/", blank=True, null=True
    )
    created_by = models.ForeignKey(
        User,
        verbose_name="enregistré par",
        related_name="interactions",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField("créé le", auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at"]

    def __str__(self):
        return f"{self.get_interaction_type_display()} — {self.contact.name}"


class Note(models.Model):
    """Note libre sur un contact — plusieurs par contact, modifiables et
    supprimables. À ne pas confondre avec `Contact.notes`, un champ unique
    qui porte le besoin exprimé capturé à la qualification."""

    contact = models.ForeignKey(Contact, verbose_name="contact", related_name="dossier_notes", on_delete=models.CASCADE)
    text = models.TextField("note")
    created_by = models.ForeignKey(
        User, verbose_name="auteur", related_name="notes", on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField("créée le", auto_now_add=True)
    updated_at = models.DateTimeField("modifiée le", auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Note sur {self.contact.name} — {self.text[:40]}"


class Task(models.Model):
    """Tâche à faire, liée soit à un contact (suivi commercial : relance,
    préparer une offre), soit à une prestation (suivi de production) — le
    même modèle sert aux deux usages, `task_type` indique lequel des deux
    FK ci-dessous est renseigné (contrôlé dans `TaskSerializer`).
    Contrairement à `Event`, pas de créneau qui bloque un calendrier — mais
    l'échéance porte quand même une heure (ex : "à envoyer avant 17h"), pas
    seulement une date."""

    class TaskType(models.TextChoices):
        CONTACT = "CONTACT", "Suivi contact"
        PRESTATION = "PRESTATION", "Tâche de prestation"

    class Status(models.TextChoices):
        TODO = "TODO", "À faire"
        IN_PROGRESS = "IN_PROGRESS", "En cours"
        DONE = "DONE", "Terminée"

    task_type = models.CharField(
        "type", max_length=20, choices=TaskType.choices, default=TaskType.CONTACT
    )
    contact = models.ForeignKey(
        Contact, verbose_name="contact", related_name="tasks", on_delete=models.CASCADE, null=True, blank=True
    )
    prestation = models.ForeignKey(
        Prestation, verbose_name="prestation", related_name="tasks", on_delete=models.CASCADE, null=True, blank=True
    )
    label = models.CharField("intitulé", max_length=200)
    description = models.TextField("description", blank=True)
    due_at = models.DateTimeField("échéance", null=True, blank=True)
    # Réutilise l'échelle de priorité de Project — même sémantique, pas besoin
    # d'une deuxième énumération HIGH/MEDIUM/LOW.
    priority = models.CharField(
        "priorité", max_length=10, choices=Project.Priority.choices, default=Project.Priority.MEDIUM
    )
    done = models.BooleanField("terminée", default=False)
    # `status` affine `done` pour les vues type kanban (À faire / En cours /
    # Terminée) sans remettre en cause les usages existants qui ne
    # connaissent que `done` (voir `save()` pour la synchronisation).
    status = models.CharField(
        "statut", max_length=20, choices=Status.choices, default=Status.TODO
    )
    assignee = models.ForeignKey(
        User,
        verbose_name="assignée à",
        related_name="assigned_tasks",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        User,
        verbose_name="créée par",
        related_name="tasks",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField("créée le", auto_now_add=True)

    class Meta:
        # Les tâches à faire en premier, triées par échéance ; les tâches
        # terminées (done=True) sont reléguées en fin de liste.
        ordering = ["done", "due_at"]

    def save(self, *args, **kwargs):
        # `done` reste la source de vérité pour les usages existants qui
        # l'utilisent seuls (cases à cocher simples) ; `status` l'affine pour
        # les vues kanban. On les garde synchronisés dans les deux sens.
        if self.status == Task.Status.DONE:
            self.done = True
        elif self.done and self.status != Task.Status.DONE:
            self.status = Task.Status.DONE
        elif not self.done and self.status == Task.Status.DONE:
            self.status = Task.Status.TODO
        super().save(*args, **kwargs)

    def __str__(self):
        return self.label


class Event(models.Model):
    """Rendez-vous programmé sur un contact — contrairement à `Task`, a un
    créneau horaire réel à bloquer sur un calendrier. L'appel, la réunion et
    la livraison confirmée ont cette nature ; une simple relance est une
    `Task` avec échéance, pas un `Event`."""

    class EventType(models.TextChoices):
        CALL = "CALL", "Appel"
        MEETING = "MEETING", "Réunion"
        LIVRAISON = "LIVRAISON", "Livraison"

    class Status(models.TextChoices):
        PENDING = "PENDING", "En attente"
        ACCEPTED = "ACCEPTED", "Accepté"
        DECLINED = "DECLINED", "Décliné"
        POSTPONED = "POSTPONED", "Reporté"

    contact = models.ForeignKey(Contact, verbose_name="contact", related_name="events", on_delete=models.CASCADE)
    event_type = models.CharField("type", max_length=20, choices=EventType.choices)
    title = models.CharField("intitulé", max_length=200)
    starts_at = models.DateTimeField("date et heure")
    location = models.CharField("lieu", max_length=150, blank=True)
    status = models.CharField("statut", max_length=20, choices=Status.choices, default=Status.ACCEPTED)
    # Renseigné uniquement lors d'un report (voir EventViewSet.respond), pour
    # garder trace de l'horaire initialement proposé.
    original_starts_at = models.DateTimeField("date et heure initiale", null=True, blank=True)
    created_by = models.ForeignKey(
        User,
        verbose_name="créé par",
        related_name="events",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField("créé le", auto_now_add=True)

    class Meta:
        ordering = ["starts_at"]

    def __str__(self):
        return f"{self.get_event_type_display()} — {self.contact.name}"


class Notification(models.Model):
    """Notification interne à un utilisateur (ex : affectation d'un
    prospect) — alimente le badge cloche de la topbar. Générée uniquement
    côté serveur, jamais créée directement via l'API."""

    # Alias pratique — évite d'importer Project juste pour son enum dans les
    # vues qui créent des notifications (même pattern que User.Role = Role).
    Urgency = Project.Priority

    recipient = models.ForeignKey(
        User, verbose_name="destinataire", related_name="notifications", on_delete=models.CASCADE
    )
    message = models.CharField("message", max_length=255)
    contact = models.ForeignKey(
        Contact,
        verbose_name="contact concerné",
        related_name="notifications",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    # Réutilise l'échelle de priorité de Project (même sémantique que
    # Task.priority) — LOW reste dans la cloche uniquement ; MEDIUM/HIGH
    # s'affichent aussi en bande sous l'en-tête (jaune / rouge côté frontend).
    urgency = models.CharField(
        "urgence", max_length=10, choices=Project.Priority.choices, default=Project.Priority.LOW
    )
    is_read = models.BooleanField("lue", default=False)
    created_at = models.DateTimeField("créée le", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.message


class PartnershipDossier(models.Model):
    """Dossier de suivi d'un partenariat, du premier contact jusqu'à la
    clôture de l'événement — porté par un `Contact(contact_type=PARTENAIRE)`.
    Contrairement au dossier commercial (vue dérivée sans table dédiée), ce
    workflow a son propre vocabulaire (convention, bilan, événement) qui ne
    correspond à rien d'existant : il mérite son propre modèle."""

    class Step(models.TextChoices):
        CREATION = "CREATION", "Création du dossier partenariat"
        TRANSMISSION = "TRANSMISSION", "Transmission au Head of Marketing"
        DISCUSSIONS = "DISCUSSIONS", "Discussions, qualification, réunions et fiche signalétique"
        ACCORD_PRINCIPE = "ACCORD_PRINCIPE", "Accord de principe"
        PREPARATION_CONVENTION = "PREPARATION_CONVENTION", "Préparation de la convention"
        SIGNATURE_CONVENTION = "SIGNATURE_CONVENTION", "Envoi et signature de la convention"
        PAIEMENT_INITIAL = "PAIEMENT_INITIAL", "Paiement initial si nécessaire"
        SUPPORTS_COMMUNICATION = "SUPPORTS_COMMUNICATION", "Mise au format et création des supports de communication"
        DEPLOIEMENT = "DEPLOIEMENT", "Déploiement, installation et préparation de l'événement"
        REALISATION = "REALISATION", "Réalisation de l'événement"
        BILAN = "BILAN", "Bilan"
        CLOTURE = "CLOTURE", "Clôture"

    class ConventionStatus(models.TextChoices):
        NON_DEMARREE = "NON_DEMARREE", "Non démarrée"
        EN_PREPARATION = "EN_PREPARATION", "En préparation"
        ENVOYEE = "ENVOYEE", "Envoyée pour signature"
        SIGNEE = "SIGNEE", "Signée"

    # Généré à la création (voir PartnershipDossierViewSet.perform_create) —
    # format PART-<année>-<id sur 3 chiffres>, comme le prototype frontend.
    reference = models.CharField("référence", max_length=30, unique=True, editable=False)
    partenaire = models.ForeignKey(
        Contact, verbose_name="partenaire", related_name="partnership_dossiers", on_delete=models.CASCADE
    )
    evenement = models.CharField("événement lié", max_length=200)
    evenement_debut = models.DateField("début de l'événement", null=True, blank=True)
    evenement_fin = models.DateField("fin de l'événement", null=True, blank=True)
    montant = models.DecimalField("montant du partenariat", max_digits=12, decimal_places=2)
    current_step = models.CharField("étape courante", max_length=30, choices=Step.choices, default=Step.CREATION)
    urgent = models.BooleanField("urgent", default=False)
    head_marketing = models.ForeignKey(
        User,
        verbose_name="responsable marketing",
        related_name="partnership_dossiers",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    requires_payment = models.BooleanField("paiement initial requis", default=False)
    payment_received = models.BooleanField("paiement initial reçu", default=False)
    convention_status = models.CharField(
        "statut de la convention", max_length=20, choices=ConventionStatus.choices, default=ConventionStatus.NON_DEMARREE
    )
    bilan_valide = models.BooleanField("bilan validé", default=False)
    created_by = models.ForeignKey(
        User,
        verbose_name="créé par",
        related_name="created_partnership_dossiers",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField("créé le", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} — {self.partenaire}"


class PartnershipTimelineEntry(models.Model):
    """Un point du journal d'un `PartnershipDossier` — étapes franchies et
    actions manuelles (paiement, convention, bilan), dans l'ordre où elles
    se sont produites."""

    class Kind(models.TextChoices):
        SYSTEM = "SYSTEM", "Système"
        ACTION = "ACTION", "Action"

    dossier = models.ForeignKey(
        PartnershipDossier, verbose_name="dossier", related_name="timeline", on_delete=models.CASCADE
    )
    author = models.ForeignKey(
        User, verbose_name="auteur", related_name="partnership_timeline_entries", on_delete=models.SET_NULL, null=True, blank=True
    )
    label = models.CharField("libellé", max_length=255)
    kind = models.CharField("type", max_length=10, choices=Kind.choices, default=Kind.SYSTEM)
    created_at = models.DateTimeField("le", auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.dossier} — {self.label}"


class PartnershipTask(models.Model):
    """Tâche de suivi générée automatiquement en avançant dans le workflow
    d'un `PartnershipDossier` (ex : préparer la fiche signalétique) — simple
    liste à cocher, sans priorité ni assignation contrairement à `Task`."""

    dossier = models.ForeignKey(
        PartnershipDossier, verbose_name="dossier", related_name="tasks", on_delete=models.CASCADE
    )
    label = models.CharField("intitulé", max_length=255)
    done = models.BooleanField("terminée", default=False)
    created_at = models.DateTimeField("créée le", auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return self.label
