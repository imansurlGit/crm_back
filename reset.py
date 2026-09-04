#!/usr/bin/env python
"""Vide les données transactionnelles de la base et réamorce un jeu de
données de démonstration riche et cohérent : partenaires et dossiers de
partenariat, prospects à divers stades (avec historique d'interactions et
relances), clients avec projets complets (prestations, tâches, documents,
encaissements échelonnés) à toutes les étapes du workflow, opportunités
perdues ou encore en pipeline, agenda (appels/réunions/livraisons) réparti
sur les dernières semaines et les prochaines. Idempotent : peut tourner sur
une base déjà peuplée (réamorce tout depuis zéro) ou toute neuve (recrée les
divisions et les titulaires de rôles uniques manquants).

Usage : ./venv/Scripts/python.exe reset.py
"""
import os
import random

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')

import django  # noqa: E402

django.setup()

from datetime import timedelta  # noqa: E402

from django.core.files.base import ContentFile  # noqa: E402
from django.utils import timezone  # noqa: E402

from core.models import (  # noqa: E402
    Contact, Division, Document, DocumentReview, DocumentVersion, Event,
    Interaction, Note, Notification, PartnershipDossier,
    PartnershipTimelineEntry, PartnershipTask, Prestation, Project,
    ProjectPayment, Task, User,
)
from core.views.messaging import sync_default_conversations  # noqa: E402
from messagerie.models import Conversation, ConversationParticipant, Message  # noqa: E402

random.seed(42)
NOW = timezone.now()
DEMO_PASSWORD = '1234'

TRANSACTIONAL_MODELS = [
    Notification, Message, ConversationParticipant, Conversation,
    PartnershipTask, PartnershipTimelineEntry, PartnershipDossier,
    ProjectPayment, DocumentReview, DocumentVersion, Document,
    Event, Task, Note, Interaction, Prestation, Project, Contact,
]

DIVISIONS = ['Ventes', 'Marketing', 'Numérique', 'Visibilité, Infrastructure et Production', 'Comptabilité']

# Titulaires des rôles uniques — recréés seulement s'ils manquent (base neuve).
UNIQUE_ROLE_SEEDS = [
    dict(email='dg@iman.ne', first_name='Dark', last_name='Vador', role='DG', division=None),
    dict(email='adch@iman.ne', first_name='Videl', last_name='Sat', role='ADCH', division=None),
    dict(email='cdv@iman.ne', first_name='Bulma', last_name='Brief', role='CDV', division='Ventes'),
    dict(email='cdm@iman.ne', first_name='Claire', last_name='Anthony', role='CDM', division='Marketing'),
    dict(email='cdn@iman.ne', first_name='Steve', last_name='Jobs', role='CDN', division='Numérique'),
    dict(email='vip@iman.ne', first_name='Billi', last_name='Bolt', role='VIP', division='Visibilité, Infrastructure et Production'),
    dict(email='cg@iman.ne', first_name='New', last_name='Comptable', role='COMPTABLE_GENERAL', division='Comptabilité'),
    dict(email='rdw@iman.ne', first_name='Bill', last_name='Gates', role='RDW', division='Numérique'),
]

# Rôles "en équipe" — complétés jusqu'au quota ci-dessous pour une démo qui a
# assez de monde à qui distribuer les prestations/tâches.
TEAM_ROLE_TARGETS = {
    'COMMERCIAL': [
        dict(email='v1@iman.ne', first_name='Franklin', last_name='Roosevelt'),
        dict(email='v2@iman.ne', first_name='Rose', last_name='Marie'),
        dict(email='v3@iman.ne', first_name='Aïssa', last_name='Boukari'),
        dict(email='v4@iman.ne', first_name='Karim', last_name='Ousmane'),
    ],
    'DEVELOPPEUR': [
        dict(email='dev2@iman.ne', first_name='Alker', last_name='Soumana'),
        dict(email='dev3@iman.ne', first_name='Amina', last_name='Tinaou'),
    ],
    'GRAPHISTE': [
        dict(email='g1@iman.ne', first_name='Krilin', last_name='Ball'),
        dict(email='g2@iman.ne', first_name='Nafissa', last_name='Elh'),
    ],
    'CHARGE_PARTENARIAT': [
        dict(email='spi@iman.ne', first_name='Lorie', last_name='Chen'),
    ],
    'ASSISTANT_COMPTABLE': [
        dict(email='ac1@iman.ne', first_name='Oumou', last_name='Sidibe'),
    ],
}
TEAM_DIVISION_BY_ROLE = {
    'COMMERCIAL': 'Ventes',
    'DEVELOPPEUR': 'Numérique',
    'GRAPHISTE': 'Marketing',
    'CHARGE_PARTENARIAT': 'Marketing',
    'ASSISTANT_COMPTABLE': 'Comptabilité',
}

PARTENAIRES = [
    dict(name='Rachid Maiga', company='Banque Horizon', sector='Finance', email='r.maiga@banquehorizon.ne', phone='+227 90 11 22 33', address='Avenue de la Liberté, Niamey'),
    dict(name='Salamatou Issoufou', company='Fondation Niger Solidarité', sector='ONG & développement', email='contact@nigersolidarite.org', phone='+227 96 44 55 66', address='Quartier Koira Kano, Niamey'),
    dict(name='Abdoulaye Chaibou', company='Nigelec', sector='Énergie', email='a.chaibou@nigelec.ne', phone='+227 90 77 88 99', address='Route de Say, Niamey'),
    dict(name='Mariama Tondi', company='Orange Niger', sector='Télécommunications', email='m.tondi@orange.ne', phone='+227 96 22 33 44', address='Avenue du Général de Gaulle, Niamey'),
]

# (personne, entreprise, secteur) — pool partagé prospects + clients.
COMPANY_POOL = [
    ('Fatouma Abdou Kadri', 'Niger BTP Services', 'BTP & construction'),
    ('Amadou Diallo', 'Zinder Mode & Textile', 'Textile & mode'),
    ('Zeinabou Garba', 'Banque Agricole du Niger', 'Finance'),
    ('Boubacar Hassane', 'Maiga Transport & Logistique', 'Transport & logistique'),
    ('Aminata Souley', 'Agro Niger Export', 'Agro-industrie'),
    ('Souleymane Harouna', 'Sahel Construction SARL', 'BTP & construction'),
    ('Hadiza Oumarou', "Ministère de l'Agriculture", 'Administration publique'),
    ('Idrissa Sani', 'Hôtel Gaweye', 'Hôtellerie & tourisme'),
    ('Bintou Alassane', 'Pharmacie Centrale du Niger', 'Santé'),
    ('Moussa Idrissa Chaibou', 'Université Abdou Moumouni', 'Éducation'),
    ('Fatima Zara', "Compagnie Nigérienne d'Assurances", 'Assurance'),
    ('Adamou Garba', 'Niger Poste', 'Services publics'),
    ('Roukaya Ibrahim', 'Coopérative Laitière de Niamey', 'Agroalimentaire'),
    ('Harouna Bako', 'Clinique Gamkalley', 'Santé'),
    ('Aissatou Barmou', 'Groupe Scolaire Excellence', 'Éducation'),
    ('Yahaya Moutari', 'Tahoua Céréales SARL', 'Agro-industrie'),
    ('Ramatou Seyni', 'Dosso Agro-Industrie', 'Agro-industrie'),
    ('Ali Oumarou', 'SEEN Niger', "Distribution d'eau"),
    ('Salifou Idi', 'Boulangerie Le Bon Pain', 'Agroalimentaire'),
    ('Aichatou Bello', 'SONITEXTIL', 'Textile & mode'),
    ('Moutari Kadri', 'Air Niger International', 'Transport aérien'),
    ('Djamila Alio', 'Fondation Karkara', 'ONG & développement'),
    ('Sani Abarchi', 'Compagnie Sucrière du Niger', 'Agro-industrie'),
    ('Balkissa Moussa', 'Clinique Pasteur Niamey', 'Santé'),
    ('Elh Moctar Boubé', 'Garage Sahel Auto', 'Automobile'),
    ('Nana Aïcha Kado', 'Librairie du Sahel', 'Commerce'),
]

SOURCES = ['Recommandation', 'Appel à froid', 'Site web', 'Conférence / Salon professionnel', 'Réseaux sociaux']
NIAMEY_ADDRESSES = [
    'Route de Tillabéri, Niamey', 'Quartier Terminus, Niamey', 'Avenue de la Radio, Niamey',
    'Quartier Plateau, Niamey', 'Boulevard de la Liberté, Niamey', 'Quartier Koira Kano, Niamey',
    'Route de Say, Niamey', 'Quartier Gamkalley, Niamey', 'Avenue du Général de Gaulle, Niamey',
]

PRESTATION_LABELS = ['Branding & identité visuelle', 'Campagne digitale', 'Refonte site web', 'Production audiovisuelle', 'Community management', 'Impression & supports print']

EVENT_TITLES_CALL = ['Point de suivi', 'Appel de qualification', 'Relance devis', 'Point budget', 'Retour sur besoin']
EVENT_TITLES_MEETING = ['Réunion de cadrage', 'Présentation de la proposition', 'Comité de pilotage', 'Réunion de lancement', "Atelier créatif"]

INTERACTION_TITLES = {
    'CALL': ['Appel de découverte', 'Point téléphonique', 'Relance téléphonique', 'Appel de suivi'],
    'MEETING': ['Réunion de cadrage', 'Présentation devis', 'Réunion de lancement', 'Comité de suivi'],
    'EMAIL': ['Envoi de la proposition', "Relance par email", 'Envoi du compte-rendu'],
    'MESSAGE': ['Message WhatsApp de suivi', 'Confirmation rapide'],
}


def rand_past(days_max, days_min=0):
    return NOW - timedelta(days=random.randint(days_min, days_max), hours=random.randint(8, 18))


def rand_future(days_max, days_min=1):
    return NOW + timedelta(days=random.randint(days_min, days_max), hours=random.randint(8, 18))


def rand_today(hour):
    return NOW.replace(hour=hour, minute=random.choice([0, 15, 30, 45]), second=0, microsecond=0)


def placeholder_file(name, text):
    return ContentFile(text.encode('utf-8'), name=name)


# ---------------------------------------------------------------------------
# Nettoyage + amorçage des acteurs (users/divisions)
# ---------------------------------------------------------------------------

def wipe_transactional_data():
    print('Vidage des données transactionnelles :')
    for model in TRANSACTIONAL_MODELS:
        count, _ = model.objects.all().delete()
        print(f'  {model.__name__}: {count} supprimé(s)')


def ensure_divisions():
    divisions = {}
    for name in DIVISIONS:
        division, _ = Division.objects.get_or_create(name=name)
        divisions[name] = division
    return divisions


def ensure_unique_role_holders(divisions):
    for seed in UNIQUE_ROLE_SEEDS:
        if User.objects.filter(role=seed['role']).exists():
            continue
        User.objects.create_user(
            email=seed['email'], password=DEMO_PASSWORD, first_name=seed['first_name'],
            last_name=seed['last_name'], role=seed['role'],
            division=divisions.get(seed['division']) if seed['division'] else None,
        )
        print(f"  Créé : {seed['first_name']} {seed['last_name']} ({seed['role']})")


def ensure_team(divisions):
    for role, seeds in TEAM_ROLE_TARGETS.items():
        division = divisions[TEAM_DIVISION_BY_ROLE[role]]
        for seed in seeds:
            user, created = User.objects.get_or_create(
                email=seed['email'],
                defaults=dict(first_name=seed['first_name'], last_name=seed['last_name'], role=role, division=division, is_active=True),
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save(update_fields=['password'])
                print(f"  Créé : {seed['first_name']} {seed['last_name']} ({role})")
            elif user.role != role or user.division_id != division.id:
                user.role = role
                user.division = division
                user.save(update_fields=['role', 'division'])


# ---------------------------------------------------------------------------
# Partenariats
# ---------------------------------------------------------------------------

def seed_partnership_dossiers(head_marketing, created_by):
    print('\nDossiers de partenariat :')
    events = [
        ('Foire Internationale de Niamey 2026', 60, 65, 3_000_000, True),
        ('Gala annuel de la Chambre de Commerce', 20, 20, 1_500_000, False),
        ('Conférence Digital Africa', -10, -8, 2_200_000, True),
        ('Semaine de la Finance Inclusive', 40, 42, 1_800_000, True),
    ]
    steps = ['DISCUSSIONS', 'PREPARATION_CONVENTION', 'DEPLOIEMENT', 'CLOTURE']
    for index, partner_data in enumerate(PARTENAIRES):
        partner = Contact.objects.create(
            contact_type='PARTENAIRE', entity_type='GRANDE_ENTREPRISE', assigned_to=head_marketing,
            created_by=created_by, source='Recommandation', notes='', **partner_data,
        )
        title, start_offset, end_offset, montant, requires_payment = events[index % len(events)]
        step = steps[index % len(steps)]
        dossier = PartnershipDossier.objects.create(
            partenaire=partner, evenement=title,
            evenement_debut=(NOW + timedelta(days=start_offset)).date(),
            evenement_fin=(NOW + timedelta(days=end_offset)).date(),
            montant=montant, current_step=step, head_marketing=head_marketing,
            requires_payment=requires_payment, payment_received=requires_payment and step != 'DISCUSSIONS',
            convention_status='SIGNEE' if step in ('DEPLOIEMENT', 'CLOTURE') else ('ENVOYEE' if step == 'PREPARATION_CONVENTION' else 'NON_DEMARREE'),
            bilan_valide=(step == 'CLOTURE'), created_by=created_by, urgent=(index == 0),
        )
        dossier.reference = f'PART-{dossier.created_at.year}-{dossier.id:03d}'
        dossier.save(update_fields=['reference'])
        PartnershipTimelineEntry.objects.create(dossier=dossier, author=created_by, label='Dossier partenariat créé.', kind='SYSTEM')
        if step != 'DISCUSSIONS':
            PartnershipTimelineEntry.objects.create(dossier=dossier, author=head_marketing, label='Réunion de qualification tenue avec le partenaire.', kind='ACTION')
            PartnershipTask.objects.create(dossier=dossier, label='Préparer la fiche signalétique du partenaire', done=True)
        if step in ('PREPARATION_CONVENTION', 'DEPLOIEMENT', 'CLOTURE'):
            PartnershipTask.objects.create(dossier=dossier, label='Rédiger la convention de partenariat', done=True)
        if step in ('DEPLOIEMENT', 'CLOTURE'):
            PartnershipTask.objects.create(dossier=dossier, label='Installation sur site', done=(step == 'CLOTURE'))
            PartnershipTask.objects.create(dossier=dossier, label='Suivi terrain le jour J', done=(step == 'CLOTURE'))
        print(f'  {dossier.reference}: {partner.company} — {title} ({step})')


# ---------------------------------------------------------------------------
# Prospects (historique d'interactions, relances)
# ---------------------------------------------------------------------------

def add_interaction_history(contact, commercial, count):
    types = ['CALL', 'EMAIL', 'MEETING', 'MESSAGE']
    events_created = []
    for i in range(count):
        itype = types[i % len(types)]
        occurred_at = rand_past(90, days_min=(count - i) * 4)
        interaction = Interaction.objects.create(
            contact=contact, interaction_type=itype, stage=contact.stage,
            title=random.choice(INTERACTION_TITLES[itype]),
            description=f'Échange avec {contact.name} au sujet de son besoin en communication.',
            occurred_at=occurred_at, created_by=commercial,
        )
        events_created.append(interaction)
    return events_created


def seed_prospects(commercials, pool):
    print('\nProspects (historique en cours) :')
    stages_cycle = ['PRISE_DE_CONTACT', 'QUALIFICATION', 'ECHANGES', 'CHIFFRAGE_OFFRE']
    created = []
    for index in range(6):
        name, company, sector = pool.pop()
        commercial = commercials[index % len(commercials)]
        stage = stages_cycle[index % len(stages_cycle)]
        contact = Contact.objects.create(
            contact_type='PROSPECT', entity_type=random.choice(['PME', 'GRANDE_ENTREPRISE', 'INSTITUTION']),
            name=name, company=company, sector=sector,
            email=f"contact@{company.lower().replace(' ', '').replace(chr(39), '')[:20]}.ne",
            phone=f'+227 9{random.randint(0,6)} {random.randint(10,99)} {random.randint(10,99)} {random.randint(10,99)}',
            address=random.choice(NIAMEY_ADDRESSES), source=random.choice(SOURCES),
            notes='', stage=stage, assigned_to=commercial, created_by=commercial,
        )
        add_interaction_history(contact, commercial, random.randint(2, 5))
        if stage in ('QUALIFICATION', 'ECHANGES', 'CHIFFRAGE_OFFRE'):
            contact.next_followup_at = rand_future(10)
            contact.save(update_fields=['next_followup_at'])
            Task.objects.create(
                task_type='CONTACT', contact=contact, label=f'Relancer {contact.name} ({contact.company})',
                due_at=contact.next_followup_at, priority='MEDIUM', assignee=commercial, created_by=commercial,
            )
        # Rendez-vous à l'agenda pour une partie des prospects.
        if index % 2 == 0:
            Event.objects.create(
                contact=contact, event_type=random.choice(['CALL', 'MEETING']),
                title=random.choice(EVENT_TITLES_CALL + EVENT_TITLES_MEETING),
                starts_at=rand_future(14), location='' if random.random() < 0.5 else "Bureaux de l'agence, Niamey",
                created_by=commercial,
            )
        created.append(contact)
        print(f'  #{contact.id}: {contact.name} ({contact.company}) — {stage} — {commercial.first_name}')
    return created


# ---------------------------------------------------------------------------
# Clients — cycle de vie complet du projet
# ---------------------------------------------------------------------------

def build_won_project(contact, commercial, budget, deadline_days, requires_deposit):
    """Crée le Project (kind=PROJET) déjà 'gagné' avec au moins une prestation,
    reproduisant ce que fait le vrai parcours (opportunité -> devis validé ->
    gagnée -> acompte -> démarrage), sans repasser par les endpoints DRF."""
    deadline = NOW + timedelta(days=deadline_days)
    project = Project.objects.create(
        kind='PROJET', client=contact, name=f'{random.choice(PRESTATION_LABELS)} — {contact.company}',
        description=f'Besoin exprimé par {contact.name} : renforcer la présence de {contact.company}.',
        deadline=deadline, priority=random.choice(['HIGH', 'MEDIUM', 'MEDIUM', 'LOW']), budget=budget,
        requires_deposit=requires_deposit, deposit_amount=(round(budget * 0.3, -3) if requires_deposit else None),
        deposit_decided=True, status='NOUVEAU', created_by=commercial, converted_at=NOW - timedelta(days=random.randint(20, 120)),
    )
    return project


def attach_devis(project, contact, validator, commercial, decided=True):
    devis = Document.objects.create(
        owner_type='PROJECT', project=project, document_type='DEVIS', status=('VALIDE' if decided else 'A_VALIDER'),
        link=f'https://exemple.iman.ne/devis/{project.id}.pdf', label=f'Devis — {project.name}',
        uploaded_by=commercial,
    )
    DocumentReview.objects.create(document=devis, author=commercial, decision='SOUMIS')
    if decided:
        DocumentReview.objects.create(document=devis, author=validator, decision='VALIDE', comment='Devis conforme, à envoyer au client.')
    devis.validators.add(validator)
    return devis


def assign_prestation(project, division, label, commercial, chief, note, deadline_days, workers, done_ratio):
    prestation = Prestation.objects.create(
        project=project, division=division, label=label, deadline=NOW + timedelta(days=deadline_days), note=note,
    )
    if workers:
        task_labels = ['Brief créatif', 'Première maquette', 'Retouches client', 'Version finale', 'Livraison des fichiers sources']
        n_tasks = random.randint(3, 5)
        for i in range(n_tasks):
            done = i < round(n_tasks * done_ratio)
            Task.objects.create(
                task_type='PRESTATION', prestation=prestation, label=task_labels[i % len(task_labels)],
                due_at=NOW + timedelta(days=random.randint(-10, deadline_days)), priority=random.choice(['HIGH', 'MEDIUM', 'LOW']),
                done=done, status=('DONE' if done else random.choice(['TODO', 'IN_PROGRESS'])),
                assignee=random.choice(workers), created_by=commercial,
            )
    brief = Document.objects.create(
        owner_type='PROJECT', project=project, prestation=prestation, document_type='BRIEF', status='PIECE_JOINTE',
        label=f'Brief — {label}', uploaded_by=commercial,
    )
    brief.file = placeholder_file('brief.txt', f'Consignes pour {label} : {note}')
    brief.save(update_fields=['file'])
    DocumentVersion.objects.create(document=brief, file=brief.file, uploaded_by=commercial)
    Notification.objects.create(recipient=chief, message=f'La prestation « {label} » du projet « {project.name} » a été affectée à votre division.'[:255])
    return prestation


def record_payments(project, comptable, schedule):
    """schedule: liste de fractions du budget, ex [0.3, 0.4, 0.3]."""
    total = float(project.budget)
    paid_so_far = 0
    for i, fraction in enumerate(schedule):
        amount = round(total * fraction, -2)
        paid_so_far += amount
        ProjectPayment.objects.create(
            project=project, amount=amount, method=random.choice(['VIREMENT', 'MOBILE_MONEY', 'CHEQUE']),
            note=('Acompte' if i == 0 and project.requires_deposit else f'{i + 1}e versement'),
            recorded_by=comptable, paid_at=NOW - timedelta(days=(len(schedule) - i) * 12),
        )
    if project.requires_deposit and paid_so_far >= float(project.deposit_amount or 0):
        project.deposit_received = True
    if paid_so_far >= total:
        project.final_payment_received = True
    project.save(update_fields=['deposit_received', 'final_payment_received'])


def seed_clients(pool, commercials, chiefs, divisions):
    """chiefs: dict role->User (cdm, cdn, vip). Retourne les statuts couverts,
    du tout début de production jusqu'à la clôture complète."""
    print('\nClients (projet complet) :')
    developers = list(User.objects.filter(role='DEVELOPPEUR'))
    graphistes = list(User.objects.filter(role='GRAPHISTE'))
    vip_workers = list(User.objects.filter(role='VIP'))
    comptable = User.objects.filter(role='COMPTABLE_GENERAL').first()
    cdv = User.objects.filter(role='CDV').first()

    plans = [
        # (status, requires_deposit, deposit_paid, prestation faite avec quelle division, fiche BAT validée, paiements)
        dict(status='EN_COURS', requires_deposit=True, prestation_done=0.1, bat=False, payments=[]),  # acompte en attente
        dict(status='EN_COURS', requires_deposit=True, prestation_done=0.3, bat=False, payments=[0.4]),
        dict(status='EN_COURS', requires_deposit=False, prestation_done=0.5, bat=False, payments=[]),
        dict(status='EN_VALIDATION_CLIENT', requires_deposit=True, prestation_done=0.8, bat=False, payments=[0.3]),
        dict(status='EN_CORRECTION', requires_deposit=True, prestation_done=0.7, bat=False, payments=[0.3]),
        dict(status='PRET_POUR_EXECUTION', requires_deposit=True, prestation_done=1.0, bat=True, payments=[0.3]),
        dict(status='PRET_POUR_LIVRAISON', requires_deposit=True, prestation_done=1.0, bat=True, payments=[0.3, 0.3]),
        dict(status='LIVRE', requires_deposit=True, prestation_done=1.0, bat=True, payments=[0.3, 0.3], final_paid=False),
        dict(status='LIVRE', requires_deposit=False, prestation_done=1.0, bat=True, payments=[1.0], final_paid=True, cloture=True),
        dict(status='CLOTURE', requires_deposit=True, prestation_done=1.0, bat=True, payments=[0.3, 0.3, 0.4], final_paid=True, cloture=True),
    ]
    created = []
    for index, plan in enumerate(plans):
        name, company, sector = pool.pop()
        commercial = commercials[index % len(commercials)]
        budget = random.choice([1_500_000, 2_000_000, 2_500_000, 3_000_000, 4_500_000, 6_000_000])
        contact = Contact.objects.create(
            contact_type='CLIENT', entity_type=random.choice(['PME', 'GRANDE_ENTREPRISE', 'INSTITUTION']),
            name=name, company=company, sector=sector,
            email=f"direction@{company.lower().replace(' ', '').replace(chr(39), '')[:20]}.ne",
            phone=f'+227 9{random.randint(0,6)} {random.randint(10,99)} {random.randint(10,99)} {random.randint(10,99)}',
            address=random.choice(NIAMEY_ADDRESSES), source=random.choice(SOURCES), notes='',
            stage='CONVERSION_CLIENT', assigned_to=commercial, created_by=commercial,
            converted_at=NOW - timedelta(days=random.randint(30, 150)),
        )
        add_interaction_history(contact, commercial, random.randint(4, 7))
        Note.objects.create(contact=contact, text=f'{contact.company} est un compte prioritaire, exigeant sur les délais.', created_by=commercial)
        Note.objects.create(contact=contact, text='Préfère être contacté en fin de journée.', created_by=commercial)

        project = build_won_project(contact, commercial, budget, deadline_days=random.randint(-10, 45), requires_deposit=plan['requires_deposit'])
        attach_devis(project, contact, cdv or commercial, commercial)

        division_name, workers, chief = random.choice([
            ('Marketing', graphistes, chiefs.get('CDM')),
            ('Numérique', developers, chiefs.get('CDN')),
        ])
        prestation = assign_prestation(
            project, divisions[division_name], random.choice(PRESTATION_LABELS), commercial, chief,
            note='Merci de respecter la charte graphique transmise en pièce jointe.',
            deadline_days=random.randint(5, 30), workers=workers, done_ratio=plan['prestation_done'],
        )
        if plan['bat']:
            # Le tout premier BAT du lot reste volontairement en attente de
            # validation — pour peupler "Validations en attente" côté chef de
            # division (voir DashboardCdvPage.tsx / centre de validation).
            bat_decided = index != 5
            fiche = Document.objects.create(
                owner_type='PROJECT', project=project, prestation=prestation, document_type='FICHE_BAT',
                status=('VALIDE' if bat_decided else 'A_VALIDER'),
                link=f'https://exemple.iman.ne/bat/{project.id}.pdf', label=f'Fiche BAT — {project.name}', uploaded_by=commercial,
            )
            DocumentReview.objects.create(document=fiche, author=commercial, decision='SOUMIS')
            if bat_decided:
                DocumentReview.objects.create(document=fiche, author=contact.assigned_to, decision='VALIDE', comment='Bon à tirer.')
            fiche.validators.add(chief or cdv or commercial)

        project.status = plan['status']
        if plan['status'] in ('PRET_POUR_EXECUTION', 'PRET_POUR_LIVRAISON', 'LIVRE', 'CLOTURE'):
            # Une exécution transmise à la production a toujours une division
            # responsable — VIP par défaut, comme dans le vrai flux.
            assign_prestation(
                project, divisions['Visibilité, Infrastructure et Production'], 'Impression / production finale', commercial,
                chiefs.get('VIP'), note='Livraison sur site à coordonner avec le client.', deadline_days=random.randint(1, 10),
                workers=vip_workers, done_ratio=1.0 if plan['status'] != 'PRET_POUR_EXECUTION' else 0.2,
            )
        project.save(update_fields=['status'])

        if plan['payments']:
            record_payments(project, comptable or commercial, plan['payments'])
        if plan.get('final_paid'):
            project.final_payment_received = True
            project.save(update_fields=['final_payment_received'])
        if plan.get('cloture'):
            project.status = 'CLOTURE'
            project.save(update_fields=['status'])

        if plan['status'] in ('LIVRE', 'CLOTURE'):
            Event.objects.create(
                contact=contact, event_type='LIVRAISON', title=f'Livraison — {project.name}',
                starts_at=NOW - timedelta(days=random.randint(1, 20)), created_by=commercial,
            )
        else:
            Event.objects.create(
                contact=contact, event_type=random.choice(['CALL', 'MEETING']),
                title=random.choice(EVENT_TITLES_MEETING), starts_at=rand_future(21),
                location="Bureaux de l'agence, Niamey", created_by=commercial,
            )

        created.append(contact)
        print(f'  #{contact.id}: {contact.name} ({contact.company}) — projet {project.status} — {commercial.first_name}')
    return created


def seed_pipeline_opportunities(pool, commercials, cdv):
    print('\nOpportunités en pipeline / perdues :')
    for index in range(6):
        name, company, sector = pool.pop()
        commercial = commercials[index % len(commercials)]
        contact = Contact.objects.create(
            contact_type='CLIENT' if index % 2 == 0 else 'PROSPECT', entity_type='PME', name=name, company=company, sector=sector,
            email=f"contact@{company.lower().replace(' ', '').replace(chr(39), '')[:20]}.ne",
            phone=f'+227 9{random.randint(0,6)} {random.randint(10,99)} {random.randint(10,99)} {random.randint(10,99)}',
            address=random.choice(NIAMEY_ADDRESSES), source=random.choice(SOURCES), notes='',
            stage='CHIFFRAGE_OFFRE', assigned_to=commercial, created_by=commercial,
        )
        add_interaction_history(contact, commercial, random.randint(2, 4))
        budget = random.choice([800_000, 1_200_000, 1_800_000, 2_500_000])
        project = Project.objects.create(
            kind='OPPORTUNITE', client=contact, name=f'{random.choice(PRESTATION_LABELS)} — {contact.company}',
            description='Besoin en cours de qualification.', priority=random.choice(['HIGH', 'MEDIUM', 'LOW']),
            created_by=commercial,
        )
        is_lost = index < 3
        if is_lost:
            project.status = 'PERDUE'
            project.description = 'Le client a finalement choisi un prestataire local moins cher.'
            project.save(update_fields=['status', 'description'])
            print(f'  #{contact.id}: {contact.name} ({contact.company}) — opportunité perdue')
        else:
            # Devis encore en attente de validation — alimente le centre de
            # validation / "Validations en attente" du CDV pour la démo.
            attach_devis(project, contact, cdv or commercial, commercial, decided=False)
            if index % 3 == 0:
                project.budget = budget
                project.save(update_fields=['budget'])
            print(f'  #{contact.id}: {contact.name} ({contact.company}) — pipeline ({project.status})')


def seed_today_agenda(contacts, commercials):
    """Quelques rendez-vous à la date du jour — sans ça, "Agenda du jour"
    (DashboardCdvPage.tsx et équivalents) reste toujours vide, puisque tout
    le reste de l'agenda est délibérément réparti dans le passé/futur proche
    plutôt que pile aujourd'hui."""
    print("\nAgenda du jour :")
    if not contacts:
        return
    sample = random.sample(contacts, k=min(4, len(contacts)))
    hours = [9, 11, 14, 16]
    for i, contact in enumerate(sample):
        commercial = contact.assigned_to or commercials[i % len(commercials)]
        event = Event.objects.create(
            contact=contact, event_type=random.choice(['CALL', 'MEETING']),
            title=random.choice(EVENT_TITLES_CALL + EVENT_TITLES_MEETING),
            starts_at=rand_today(hours[i % len(hours)]),
            location='' if random.random() < 0.5 else "Bureaux de l'agence, Niamey",
            created_by=commercial,
        )
        print(f"  {event.get_event_type_display()} à {event.starts_at.strftime('%H:%M')} avec {contact.name} ({contact.company})")


# ---------------------------------------------------------------------------
def main():
    wipe_transactional_data()
    divisions = ensure_divisions()
    ensure_unique_role_holders(divisions)
    ensure_team(divisions)

    commercials = list(User.objects.filter(role='COMMERCIAL').order_by('id'))
    if not commercials:
        raise SystemExit('Aucun commercial disponible — vérifiez ensure_team().')
    chiefs = {
        'CDM': User.objects.filter(role='CDM').first(),
        'CDN': User.objects.filter(role='CDN').first(),
        'VIP': User.objects.filter(role='VIP').first(),
    }
    cdv = User.objects.filter(role='CDV').first()
    cdm = chiefs.get('CDM')

    pool = list(COMPANY_POOL)
    random.shuffle(pool)

    seed_partnership_dossiers(head_marketing=cdm or commercials[0], created_by=cdm or commercials[0])
    prospects = seed_prospects(commercials, pool)
    clients = seed_clients(pool, commercials, chiefs, divisions)
    seed_pipeline_opportunities(pool, commercials, cdv)
    seed_today_agenda(prospects + clients, commercials)

    sync_default_conversations()
    print('\nCanaux de messagerie réamorcés :')
    for conversation in Conversation.objects.filter(kind='GROUP').order_by('name'):
        print(f'  #{conversation.id}: {conversation.name} — {conversation.participants.count()} membre(s)')

    print('\nReset terminé.')
    print(f"Mot de passe des comptes nouvellement créés : {DEMO_PASSWORD}")


if __name__ == '__main__':
    main()
