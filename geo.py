from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request


def get_coordinates(adresse: str) -> tuple | None:
    """
    If adresse looks like 'lat,lon' (e.g. '48.4074, 2.5958'), parse directly.
    Otherwise, call https://api-adresse.data.gouv.fr/search/?q=<adresse>&limit=1
    Returns (lat, lon, context) tuple where context is properties.context from
    the API (e.g. '77, Seine-et-Marne, Île-de-France') or None for direct input.
    Returns None on failure.
    """
    adresse = adresse.strip()
    if not adresse:
        return None

    # Direct lat,lon input — accepts optional spaces around the comma
    m = re.match(r'^(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)$', adresse)
    if m:
        return float(m.group(1)), float(m.group(2)), None

    try:
        params = urllib.parse.urlencode({'q': adresse, 'limit': 1})
        url = f'https://api-adresse.data.gouv.fr/search/?{params}'
        req = urllib.request.Request(url, headers={'User-Agent': 'ForetFinance/1.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.load(resp)
        features = data.get('features', [])
        if not features:
            return None
        feat = features[0]
        lon, lat = feat['geometry']['coordinates']   # GeoJSON order: [lon, lat]
        context = feat['properties'].get('context', '')
        return lat, lon, context
    except Exception:
        return None


def check_natura_2000(lat: float, lon: float) -> bool:
    """
    Call INPN WFS API to check if point falls in a Natura 2000 zone:
    GET https://ws.carmencarto.fr/WS/119/fxx_inpn/ows?SERVICE=WFS&VERSION=2.0.0
        &REQUEST=GetFeature&typeName=N2000_ENP&outputFormat=application/json
        &CQL_FILTER=INTERSECTS(the_geom,POINT(<lon> <lat>))&count=1
    Returns True if any feature found, False otherwise. Fails silently.
    """
    try:
        # WKT POINT uses longitude then latitude
        cql = f'INTERSECTS(the_geom,POINT({lon} {lat}))'
        params = urllib.parse.urlencode({
            'SERVICE': 'WFS',
            'VERSION': '2.0.0',
            'REQUEST': 'GetFeature',
            'typeName': 'N2000_ENP',
            'outputFormat': 'application/json',
            'CQL_FILTER': cql,
            'count': 1,
        })
        url = f'https://ws.carmencarto.fr/WS/119/fxx_inpn/ows?{params}'
        req = urllib.request.Request(url, headers={'User-Agent': 'ForetFinance/1.0'})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.load(resp)
        return len(data.get('features', [])) > 0
    except Exception:
        return False
