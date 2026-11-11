# ForêtFinance

🇫🇷 **Français** · 🇧🇷 [Português](README.pt-BR.md)

**Diagnostic de financements forestiers pour les propriétaires privés en France.** En quelques questions, l'application
identifie les aides auxquelles une parcelle est éligible, propose la combinaison la plus avantageuse, estime les montants
et le potentiel carbone, puis génère un conseil personnalisé avec Claude.

![Python](https://img.shields.io/badge/Python-3-informational?style=flat-square)
![Flask](https://img.shields.io/badge/Flask-3.x-lightgrey?style=flat-square)
![Folium](https://img.shields.io/badge/Folium-0.16+-77B829?style=flat-square)

---

## Fonctionnalités

- **Formulaire de diagnostic** : durée de propriété, surface, état du peuplement, type de propriétaire, région, terrain
  non boisé depuis 10 ans, zone Natura 2000.
- **Géolocalisation de la parcelle** : à partir d'une adresse (API Adresse de data.gouv.fr) ou de coordonnées `lat, lon`,
  l'application détecte la région et vérifie si le point se trouve en zone Natura 2000 (service WFS de l'INPN).
- **Moteur d'éligibilité** : règles déclaratives dans `data/financements.json` (critères obligatoires et restrictifs,
  avec alternatives) appliquées à 7 mécanismes :

  | Mécanisme | Type |
  |---|---|
  | Label Bas Carbone — Boisement | Crédits carbone |
  | Label Bas Carbone — Reconstitution | Crédits carbone |
  | Label Bas Carbone — Conversion de taillis | Crédits carbone |
  | France Nation Verte — Renouvellement forestier | Subvention |
  | FEADER — Aide au reboisement | Subvention |
  | DEFI Travaux — Crédit d'impôt forestier | Avantage fiscal |
  | Contrats Natura 2000 | Contrat État |

- **Combinaison optimale** : recherche du plus grand ensemble de mécanismes cumulables (ou combinaison recommandée pour les
  peuplements sinistrés / dépérissants détenus depuis 30 ans et plus), avec le financement direct estimé (min – max).
- **Estimateur carbone** : séquestration annuelle et sur 30 ans, revenus potentiels selon une fourchette de prix du crédit.
- **Conseil personnalisé par IA** : trois paragraphes rédigés par Claude (API Anthropic) dans le rôle d'un conseiller
  forestier : pourquoi la parcelle est éligible, quelle combinaison retenir, trois actions prioritaires.
- **Carte des zones Natura 2000** (`/map`) : carte Folium de sites forestiers représentatifs.
- **Formulaire de contact** : les demandes sont enregistrées dans `data/contacts.json`.

## Installation

```bash
git clone https://github.com/joaoalbuquerquef/ForetFinance.git
cd ForetFinance
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Créez un fichier `.env` à la racine avec votre clé API :

```
ANTHROPIC_API_KEY=sk-ant-...
```

Sans clé, le diagnostic fonctionne quand même ; seul le conseil personnalisé affiche un message d'indisponibilité.

## Lancement

```bash
python app.py
```

L'application écoute sur `http://localhost:5000` (ou sur le port défini par la variable `PORT`). Le `Procfile` permet le
déploiement sur Heroku, Railway ou Render.

## Routes

| Route | Méthode | Rôle |
|---|---|---|
| `/` | GET | Formulaire de diagnostic |
| `/diagnose` | POST | Géolocalisation, éligibilité, combinaison optimale, conseil IA |
| `/contact` | POST | Enregistre une demande de contact |
| `/map` | GET | Carte des zones Natura 2000 |

## Structure

```
app.py                  Routes Flask, appel à l'API Anthropic, carte Folium
matching.py             Moteur d'éligibilité, estimation des montants, combinaison optimale, carbone
geo.py                  Géocodage (API Adresse) et test Natura 2000 (WFS INPN)
data/financements.json  Base de règles : mécanismes, cumuls, estimateur carbone, champs du formulaire
data/contacts.json      Demandes de contact reçues
templates/              index.html, result.html, contact_confirmation.html
static/style.css
```

## Mettre à jour les règles

Toute la logique métier est dans `data/financements.json` : pour ajouter un mécanisme, modifier un critère ou un taux,
il suffit d'éditer ce fichier, sans toucher au code. Chaque mécanisme déclare ses `criteres_eligibilite`
(`obligatoires`, `restrictifs`), son `montant` (`variable`, `pourcentage`, `pourcentage_regional`, `credit_impot`) et
la liste des mécanismes avec lesquels il est `cumulable_avec`.

## Limites

- Les montants sont des **estimations indicatives** (coût de référence de 9 000 €/ha de travaux, 5 tCO₂/ha/an pour un
  peuplement mixte) et ne remplacent pas l'instruction d'un dossier par le CNPF ou la DDT.
- Les champs absents du formulaire (essences, plan de gestion, etc.) sont supposés favorables.
- Sources des règles : CNPF, ministère de la Transition écologique, IGN (avril 2026).
