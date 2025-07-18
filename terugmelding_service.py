import requests
from typing import List, Optional

def get_bag_terugmeldingen(adresseerbaarobjectid: str) -> Optional[List[dict]]:
    """
    Haal de laatste 2 terugmeldingen op voor een BAG-adresseerbaarobjectid via de PDOK Terugmelding API.
    Retourneer een lege lijst als er geen meldingen zijn, of None bij een fout.
    """
    url = f"https://api.pdok.nl/bzk/terugmeldingen/v1/terugmeldingen?identificatie={adresseerbaarobjectid}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return None
        data = response.json()
        meldingen = data.get('terugmeldingen', [])
        # Sorteer op datum aflopend (nieuwste eerst), pak de laatste 2
        meldingen_sorted = sorted(meldingen, key=lambda m: m.get('datumTijdRegistratie', ''), reverse=True)
        return meldingen_sorted[:2]
    except Exception:
        return None 