from dotenv import load_dotenv
load_dotenv()

import json
import os
import re
import unicodedata
from datetime import datetime, timezone

from flask import Flask, render_template, request
import anthropic

from matching import diagnose
from geo import get_coordinates, check_natura_2000

app = Flask(__name__)
DATA_PATH = os.path.join(os.path.dirname(__file__), 'data', 'financements.json')


def load_data():
    with open(DATA_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


# ─── Region matching helpers ─────────────────────────────────────────────────

def _norm(s: str) -> str:
    """Lowercase, strip accents and separators for fuzzy region matching."""
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return re.sub(r"[\s\-']+", ' ', s).lower().strip()


def _find_region(detected: str, options: list) -> str:
    """Return the closest region option for a geocoded region name, or 'Autre'."""
    d = _norm(detected)
    for opt in options:
        if _norm(opt) == d:
            return opt
    return 'Autre'


# ─── Template filters ────────────────────────────────────────────────────────

@app.template_filter('type_label')
def type_label(t):
    return {
        'credits_carbone': 'Crédits carbone',
        'subvention': 'Subvention',
        'fiscal': 'Avantage fiscal',
        'contrat_etat': 'Contrat État',
    }.get(t, t)


@app.template_filter('fr_num')
def fr_num(value):
    """Format integer with French thousands separator (space)."""
    try:
        return f'{int(value):,}'.replace(',', ' ')
    except (ValueError, TypeError):
        return value


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    data = load_data()
    return render_template('index.html', data=data)


@app.route('/diagnose', methods=['POST'])
def diagnose_route():
    data = load_data()
    raw = request.form.to_dict()

    geo_detected = False
    geo_natura = False
    geo_adresse = raw.get('adresse', '').strip()

    if geo_adresse:
        coords = get_coordinates(geo_adresse)
        if coords:
            lat, lon, context = coords
            geo_natura = check_natura_2000(lat, lon)
            raw['zone_natura_2000'] = 'true' if geo_natura else 'false'
            geo_detected = True
            if context:
                # context format: "77, Seine-et-Marne, Île-de-France"
                parts = [p.strip() for p in context.split(',')]
                if len(parts) >= 3:
                    region_options = data['champs_formulaire']['region']['options']
                    raw['region'] = _find_region(parts[-1], region_options)

    result = diagnose(raw, data)
    advisory = get_advisory(raw, result)
    return render_template(
        'result.html',
        result=result,
        advisory=advisory,
        form_data=raw,
        geo_detected=geo_detected,
        geo_natura=geo_natura,
        geo_adresse=geo_adresse,
    )


@app.route('/contact', methods=['POST'])
def contact():
    entry = {
        'nom':       request.form.get('nom', '').strip(),
        'email':     request.form.get('email', '').strip(),
        'telephone': request.form.get('telephone', '').strip(),
        'message':   request.form.get('message', '').strip(),
        'timestamp': datetime.now(timezone.utc).isoformat(),
    }

    contacts_path = os.path.join(os.path.dirname(__file__), 'data', 'contacts.json')
    try:
        with open(contacts_path, 'r', encoding='utf-8') as f:
            contacts = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        contacts = []
    contacts.append(entry)
    with open(contacts_path, 'w', encoding='utf-8') as f:
        json.dump(contacts, f, ensure_ascii=False, indent=2)

    prenom = entry['nom'].split()[0] if entry['nom'] else 'vous'
    return render_template('contact_confirmation.html', prenom=prenom)


@app.route('/map')
def map_view():
    try:
        import folium  # noqa: PLC0415
        m = build_natura_map()
        return m.get_root().render()
    except ImportError:
        return (
            '<p style="font-family:sans-serif;padding:2rem;">'
            'Folium non installé. Exécutez : <code>pip install folium</code></p>'
        )


# ─── Anthropic advisory ──────────────────────────────────────────────────────

def get_advisory(form_data, result):
    try:
        client = anthropic.Anthropic()
        eligible_names = ', '.join(m['nom'] for m in result['eligible']) or 'Aucun'
        optimal_names = ', '.join(m['nom'] for m in result['optimal']['details']) or 'Aucun'
        carbon = result['carbon']
        opt = result['optimal']

        context = (
            f"Profil du propriétaire :\n"
            f"- Durée de propriété : {form_data.get('duree_propriete')} ans\n"
            f"- Surface : {form_data.get('surface_ha')} ha\n"
            f"- État du peuplement : {form_data.get('etat_peuplement')}\n"
            f"- Zone Natura 2000 : {'Oui' if form_data.get('zone_natura_2000') == 'true' else 'Non'}\n"
            f"- Terrain non boisé il y a 10 ans : {'Oui' if form_data.get('non_boise_10ans') == 'true' else 'Non'}\n"
            f"- Type de propriétaire : {form_data.get('type_proprietaire')}\n"
            f"- Région : {form_data.get('region')}\n\n"
            f"Mécanismes éligibles : {eligible_names}\n"
            f"Combinaison optimale : {optimal_names}\n"
            f"Financement direct estimé : {opt['total_min']:,}€ – {opt['total_max']:,}€\n"
            f"Séquestration carbone : {carbon['sur_30_ans']} tCO₂ sur 30 ans "
            f"(revenu potentiel : {carbon['revenu_moyen']:,}€)\n\n"
            f"Rédigez exactement 3 paragraphes de conseil personnalisé."
        )

        msg = client.messages.create(
            model='claude-sonnet-4-20250514',
            max_tokens=1024,
            system=(
                'Tu es un conseiller forestier expert du CNPF. Tu parles directement au '
                'propriétaire forestier en français, avec un ton professionnel mais accessible. '
                'Tu expliques pourquoi sa parcelle est éligible, quelle combinaison de financements '
                'maximise son retour, et ses 3 actions prioritaires cette semaine.'
            ),
            messages=[{'role': 'user', 'content': context}],
        )
        text = msg.content[0].text
        text = re.sub(r'^## (.+)$', r'<h5>\1</h5>', text, flags=re.MULTILINE)
        text = re.sub(r'^# (.+)$',  r'<h4>\1</h4>', text, flags=re.MULTILINE)
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        return text
    except Exception as exc:
        return f'(Conseil non disponible pour le moment : {exc})'


# ─── Folium map ──────────────────────────────────────────────────────────────

def build_natura_map():
    import folium  # noqa: PLC0415

    m = folium.Map(location=[46.5, 2.5], zoom_start=6, tiles='CartoDB positron')

    zones = [
        ('Camargue', 43.50, 4.60, 'Zone humide / Deltaïque'),
        ('Forêt de Fontainebleau', 48.40, 2.68, 'Forêt tempérée feuillue'),
        ('Massif des Vosges', 48.10, 7.10, 'Forêt de montagne'),
        ('Pyrénées — Haute-chaîne', 42.70, 0.50, "Montagne / Forêt d'altitude"),
        ('Massif du Jura', 46.70, 5.80, 'Forêt mixte / Tourbières'),
        ('Landes de Gascogne', 44.20, -0.90, 'Forêt de pins / Landes'),
        ('Forêt de Bercé', 47.90, 0.40, 'Vieux chênes'),
        ('Causse du Quercy', 44.60, 1.70, 'Pelouses calcaires / Boisements'),
        ('Massif de la Chartreuse', 45.35, 5.80, 'Forêt de montagne'),
        ('Marais de la Brière', 47.37, -2.17, 'Zone humide / Forêt alluviale'),
        ('Forêt de Compiègne', 49.38, 2.87, 'Forêt feuillue'),
        ('Gorges de l\'Ardèche', 44.37, 4.40, 'Ripisylve / Garrigue'),
        ('Baie du Mont-Saint-Michel', 48.63, -1.51, 'Zone humide côtière'),
        ('Forêt d\'Orléans', 47.90, 2.40, 'Forêt feuillue'),
        ('Calanques — Marseille', 43.21, 5.50, 'Garrigue côtière'),
        ('Forêt des Landes', 44.50, -1.00, 'Pinède côtière'),
        ('Alpes du Nord', 45.80, 6.60, 'Forêt alpine / Sous-alpin'),
        ('Pyrénées-Orientales', 42.50, 2.20, 'Forêt méditerranéenne'),
    ]

    for nom, lat, lon, type_zone in zones:
        folium.CircleMarker(
            location=[lat, lon],
            radius=11,
            color='#1b4332',
            weight=2,
            fill=True,
            fill_color='#52b788',
            fill_opacity=0.65,
            popup=folium.Popup(
                f'<b style="color:#1b4332">{nom}</b><br><small>{type_zone}</small>',
                max_width=220,
            ),
            tooltip=nom,
        ).add_to(m)

    legend = """
    <div style="position:fixed;bottom:30px;left:30px;z-index:1000;
                background:white;padding:14px 18px;border-radius:10px;
                box-shadow:0 2px 12px rgba(0,0,0,.18);font-family:sans-serif;font-size:13px;">
        <div style="color:#1b4332;font-weight:700;margin-bottom:6px;">Zones Natura 2000</div>
        <span style="display:inline-block;width:13px;height:13px;background:#52b788;
                     border-radius:50%;border:2px solid #1b4332;margin-right:7px;"></span>
        Sites forestiers représentatifs
        <br><span style="color:#888;font-size:11px;">Source : INPN / Min. Transition Écologique</span>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend))

    title = """
    <div style="position:fixed;top:15px;left:50%;transform:translateX(-50%);z-index:1000;
                background:#1b4332;color:white;padding:10px 22px;border-radius:8px;
                font-family:sans-serif;font-size:15px;font-weight:600;
                box-shadow:0 2px 8px rgba(0,0,0,.3);">
        🌲 Zones Natura 2000 — Forêts françaises
    </div>
    """
    m.get_root().html.add_child(folium.Element(title))

    return m


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
