import json


def normalize_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).lower() in ('true', 'oui', 'yes', '1', 'on')


def check_condition(form_value, condition, expected):
    if form_value is None:
        return True  # unknown field — assume favorable
    if condition == 'gte':
        try:
            return float(form_value) >= float(expected)
        except (ValueError, TypeError):
            return False
    elif condition == 'lte':
        try:
            return float(form_value) <= float(expected)
        except (ValueError, TypeError):
            return False
    elif condition == 'eq':
        if isinstance(expected, bool):
            return normalize_bool(form_value) == expected
        return str(form_value) == str(expected)
    elif condition == 'in':
        return str(form_value) in [str(v) for v in expected]
    return False


def build_form_context(raw):
    """Normalize raw form data and fill defaults for fields not in the basic form."""
    surface = float(raw.get('surface_ha') or 0)
    in_natura = normalize_bool(raw.get('zone_natura_2000', False))
    return {
        # Fields from the form
        'duree_propriete': int(raw.get('duree_propriete') or 0),
        'surface_ha': surface,
        'etat_peuplement': raw.get('etat_peuplement', ''),
        'zone_natura_2000': in_natura,
        'non_boise_10ans': normalize_bool(raw.get('non_boise_10ans', False)),
        'type_proprietaire': raw.get('type_proprietaire', ''),
        'region': raw.get('region', ''),
        # Assumed favorable defaults for fields not in the form
        'essences_mfr': True,
        'accepte_plan_gestion': True,
        'pct_essences_experimentales': 0,
        'travaux_deja_commences': False,
        'type_peuplement': 'mixte',
        'qualite_station': None,        # lbc_taillis requires 'bonne' — never matches without explicit input
        'enrichissement_2000_plants': False,
        'action_preservation': in_natura,  # if in Natura 2000, assume restoration intent
        'diagnostic_realise': True,
        'valeur_bois_inferieure': True,
        'annee_travaux': 2026,
        'nb_essences': 2,
        'essences_adaptees_climat': True,
        'certification_pefc': False,
    }


def evaluate_mechanism(mec, ctx):
    """Return (eligible: bool, criteria_met: list, criteria_failed: list)."""
    crit = mec.get('criteres_eligibilite', {})
    met, failed = [], []

    for c in crit.get('obligatoires', []):
        ok = check_condition(ctx.get(c['champ_formulaire']), c['condition'], c['valeur'])
        if not ok and 'alternative' in c:
            alt = c['alternative']
            ok = check_condition(ctx.get(alt['champ']), alt['condition'], alt['valeur'])
        (met if ok else failed).append(c['label'])
        if not ok:
            return False, met, failed

    for c in crit.get('restrictifs', []):
        ok = check_condition(ctx.get(c['champ_formulaire']), c['condition'], c['valeur'])
        (met if ok else failed).append(c['label'])
        if not ok:
            return False, met, failed

    return True, met, failed


def estimate_amount(mec, ctx):
    """Return {min, max, note} or None."""
    m = mec['montant']
    surface = ctx['surface_ha']
    region = ctx['region']
    cout_ha = 9000  # baseline cost per ha for reforestation work

    if m['type'] == 'variable':
        duree = mec.get('duree_engagement', 30)
        rate = 5.0  # tCO2/ha/year (mixed forest default)
        return {
            'min': int(surface * rate * 15 * duree),
            'max': int(surface * rate * 30 * duree),
            'note': m.get('estimation_tonne_co2', m['description']),
            'long_terme': True,
        }
    elif m['type'] == 'pourcentage':
        base = surface * cout_ha
        return {
            'min': int(base * m['min_pct'] / 100),
            'max': int(base * m['max_pct'] / 100),
            'note': m['description'],
            'long_terme': False,
        }
    elif m['type'] == 'pourcentage_regional':
        regions = m['par_region']
        r = regions.get(region, regions['default'])
        base = surface * cout_ha
        plafond = m.get('plafond_eur', 999_999)
        return {
            'min': min(int(base * r['min_pct'] / 100), plafond),
            'max': min(int(base * r['max_pct'] / 100), plafond),
            'note': r.get('detail', m.get('description', '')),
            'long_terme': False,
        }
    elif m['type'] == 'credit_impot':
        # Applied on the share not covered by grants (~35% residual)
        base = surface * cout_ha * 0.35
        credit = int(base * m['pct'] / 100)
        return {
            'min': credit,
            'max': credit,
            'note': m['description'],
            'long_terme': False,
        }
    return None


def are_cumulable(id1, id2, mec_map):
    m1 = mec_map.get(id1, {})
    m2 = mec_map.get(id2, {})
    return id2 in m1.get('cumulable_avec', []) or id1 in m2.get('cumulable_avec', [])


def build_optimal_set(eligible_ids, mec_map):
    """Greedy: find the largest mutually cumulable subset."""
    best = []
    for start in eligible_ids:
        current = [start]
        for mid in eligible_ids:
            if mid in current:
                continue
            if all(are_cumulable(mid, sel, mec_map) for sel in current):
                current.append(mid)
        if len(current) > len(best):
            best = current
    return best


def diagnose(raw_form, data):
    ctx = build_form_context(raw_form)
    mec_map = {m['id']: m for m in data['mecanismes']}

    eligible = []
    for mec in data['mecanismes']:
        ok, met, failed = evaluate_mechanism(mec, ctx)
        if ok:
            eligible.append({
                'id': mec['id'],
                'nom': mec['nom'],
                'type': mec['type'],
                'description': mec['description'],
                'amount': estimate_amount(mec, ctx),
                'etapes': mec.get('etapes_candidature', []),
                'contact': mec.get('contact', ''),
                'duree': mec.get('duree_engagement'),
                'tags': mec.get('tags', []),
                'criteria_met': met,
            })

    # Choose optimal combination
    regles = data.get('regles_cumul', {})
    combo = regles.get('combinaison_optimale', {})
    etat = ctx['etat_peuplement']
    duree_prop = ctx['duree_propriete']
    eligible_ids_set = {m['id'] for m in eligible}

    if etat in ('sinistre', 'depérissant') and duree_prop >= 30:
        optimal_ids = [mid for mid in combo.get('mecanismes', []) if mid in eligible_ids_set]
        combo_desc = combo.get('description', '')
    else:
        optimal_ids = build_optimal_set(list(eligible_ids_set), mec_map)
        combo_desc = 'Combinaison optimale des mécanismes disponibles'

    optimal_details = [m for m in eligible if m['id'] in optimal_ids]

    # Sum only upfront amounts (not long-term carbon revenues) for the headline figure
    total_min = sum(
        m['amount']['min'] for m in optimal_details
        if m['amount'] and not m['amount'].get('long_terme')
    )
    total_max = sum(
        m['amount']['max'] for m in optimal_details
        if m['amount'] and not m['amount'].get('long_terme')
    )

    # Carbon estimate
    est = data['estimateur_carbone']
    rate = est['tonne_co2_par_ha_par_an']['mixte']
    prix = est['prix_credit_carbone_eur']
    surface = ctx['surface_ha']
    carbon = {
        'par_an': round(surface * rate, 1),
        'sur_30_ans': round(surface * rate * 30, 1),
        'revenu_min': int(surface * rate * 30 * prix['min']),
        'revenu_max': int(surface * rate * 30 * prix['max']),
        'revenu_moyen': int(surface * rate * 30 * prix['moyen']),
    }

    return {
        'eligible': eligible,
        'optimal': {
            'ids': optimal_ids,
            'details': optimal_details,
            'total_min': total_min,
            'total_max': total_max,
            'description': combo_desc,
        },
        'carbon': carbon,
        'ctx': ctx,
    }
