import requests
import re
import json

class BagService:
    def __init__(self, api_url, api_key):
        self.api_url = api_url
        self.api_key = api_key

    def lookup_address(self, postcode, huisnummer, huisletter=None):
        # Normaliseer postcode: hoofdletters, geen spaties
        postcode = re.sub(r'\s+', '', postcode).upper()
        # Normaliseer huisnummer: alleen cijfers
        original_huisnummer = huisnummer
        huisnummer = re.sub(r'\D', '', str(huisnummer))
        # Normaliseer huisletter: één hoofdletter, geen spaties of cijfers
        huisletter = (huisletter or '').strip().upper()
        huisletter = huisletter[0] if huisletter else None

        print(f'DEBUG BAG: Original huisnummer: {original_huisnummer}, Normalized: {huisnummer}', flush=True)

        headers = {
            'X-Api-Key': self.api_key,
            'Accept': 'application/hal+json',
            'Accept-Crs': 'EPSG:28992'  # Nederlands coördinatenstelsel
        }

        try:
            # 1. Zoek eerst het adres op
            zoekterm = f"{postcode} {huisnummer}"
            if huisletter:
                zoekterm += f" {huisletter}"

            print(f'DEBUG BAG: Zoeken adres met term: {zoekterm}', flush=True)
            adres_resp = requests.get(
                f"{self.api_url}/adressen/zoek",
                headers=headers,
                params={'zoek': zoekterm},
                timeout=10
            )
            adres_resp.raise_for_status()
            adres_data = adres_resp.json()
            print('DEBUG BAG API /adressen/zoek response:', adres_data, flush=True)

            zoekresultaten = adres_data.get('_embedded', {}).get('zoekresultaten', [])
            if not zoekresultaten:
                return {'error': f'Geen adres gevonden voor {zoekterm}'}, 404

            # 2. Haal het adres op via de link
            adres_link = zoekresultaten[0].get('_links', {}).get('adres', {}).get('href')
            if not adres_link:
                return {'error': 'Geen adreslink gevonden in zoekresultaat'}, 404

            print(f'DEBUG: Adres link gevonden: {adres_link}', flush=True)
            adres_detail_resp = requests.get(adres_link, headers=headers, timeout=10)
            adres_detail_resp.raise_for_status()
            adres_detail = adres_detail_resp.json()
            print('DEBUG BAG API adres detail response:', adres_detail, flush=True)

            # 3. Haal verblijfsobject ID op uit adres
            adressen = adres_detail.get('_embedded', {}).get('adressen', [])
            if not adressen:
                return {'error': 'Geen adres details gevonden'}, 404

            adres = adressen[0]
            vbo_link = adres.get('_links', {}).get('adresseerbaarObject', {}).get('href')
            if not vbo_link:
                return {'error': 'Geen verblijfsobject link gevonden in adres'}, 404

            print(f'DEBUG: Verblijfsobject link gevonden: {vbo_link}', flush=True)
            vbo_resp = requests.get(vbo_link, headers=headers, timeout=10)
            vbo_resp.raise_for_status()
            verblijfsobject = vbo_resp.json().get('verblijfsobject', {})
            print('DEBUG: Verblijfsobject gevonden:', verblijfsobject, flush=True)

            # 4. Haal pand-id op uit verblijfsobject
            pand_ids = verblijfsobject.get('maaktDeelUitVan', [])
            if not pand_ids:
                return {'error': 'Geen pand-relaties gevonden bij verblijfsobject'}, 404

            pand_id = pand_ids[0]
            if not pand_id:
                return {'error': 'Geen pand ID gevonden in verblijfsobject'}, 404

            print(f'DEBUG: Pand ID gevonden: {pand_id}', flush=True)
            pand_resp = requests.get(f"{self.api_url}/panden/{pand_id}", headers=headers, timeout=10)
            pand_resp.raise_for_status()
            pand = pand_resp.json().get('pand', {})
            print('DEBUG BAG API pand response:', pand, flush=True)

            if not pand:
                return {'error': 'Geen pand details gevonden'}, 404

            # 5. Verzamel alle gevraagde data
            bouwjaar = pand.get('oorspronkelijkBouwjaar') or pand.get('bouwjaar')
            oppervlakte = verblijfsobject.get('oppervlakte')
            inhoud = verblijfsobject.get('inhoud')
            hoogte = pand.get('hoogte')
            aantal_bouwlagen = pand.get('aantalBouwlagen')
            gebruiksdoel = verblijfsobject.get('gebruiksdoelen', [])

            # Verzamel adresgegevens
            straat = adres.get('openbareRuimteNaam', '')
            huisnummer = adres.get('huisnummer', '')
            postcode = adres.get('postcode', '')
            woonplaats = adres.get('woonplaatsNaam', '')
            huisletter = adres.get('huisletter', '')

            print(f'DEBUG BAG: API returned huisnummer: {huisnummer}', flush=True)

            # 6. Verzamel geodata
            geodata = self._extract_geodata(verblijfsobject, pand)

            # Maak volledig adres
            volledig_adres = f"{straat} {huisnummer}"
            if huisletter:
                volledig_adres += f" {huisletter}"
            volledig_adres += f", {postcode} {woonplaats}"

            return {
                'bouwjaar': bouwjaar,
                'oppervlakte': oppervlakte,
                'inhoud': inhoud,
                'hoogte': hoogte,
                'aantal_bouwlagen': aantal_bouwlagen,
                'gebruiksdoel': gebruiksdoel,
                'adres': {
                    'straat': straat,
                    'huisnummer': huisnummer,
                    'huisletter': huisletter,
                    'postcode': postcode,
                    'woonplaats': woonplaats,
                    'volledig': volledig_adres
                },
                'geodata': geodata
            }, 200

        except requests.HTTPError as e:
            if e.response.status_code == 401:
                return {'error': 'Ongeldige of ontbrekende BAG API key'}, 401
            if e.response.status_code == 404:
                return {'error': 'Adres of object niet gevonden'}, 404
            return {'error': f'BAG API error: {e.response.text}'}, e.response.status_code
        except Exception as e:
            return {'error': f'BAG API request failed: {str(e)}'}, 500 

    def _extract_geodata(self, verblijfsobject, pand):
        """Extract geodata from BAG API responses"""
        geodata = {
            'centroide_ll': None,  # Latitude/Longitude
            'centroide_rd': None,  # Dutch RD coordinates
            'geometrie': None,     # Building geometry/polygon
            'latitude': None,
            'longitude': None,
            'x_coord': None,
            'y_coord': None
        }

        # Extract centroide from verblijfsobject (preferred)
        if verblijfsobject:
            # Try to get centroide from verblijfsobject
            geometrie = verblijfsobject.get('geometrie', {})
            if geometrie:
                # Extract centroide_ll (WGS84)
                centroide_ll = geometrie.get('centroide_ll')
                if centroide_ll:
                    geodata['centroide_ll'] = centroide_ll
                    # Parse latitude and longitude
                    try:
                        coords = centroide_ll.split(',')
                        if len(coords) == 2:
                            geodata['latitude'] = float(coords[0].strip())
                            geodata['longitude'] = float(coords[1].strip())
                    except (ValueError, AttributeError):
                        pass

                # Extract centroide_rd (Dutch RD)
                centroide_rd = geometrie.get('centroide_rd')
                if centroide_rd:
                    geodata['centroide_rd'] = centroide_rd
                    # Parse X and Y coordinates
                    try:
                        coords = centroide_rd.split(',')
                        if len(coords) == 2:
                            geodata['x_coord'] = float(coords[0].strip())
                            geodata['y_coord'] = float(coords[1].strip())
                    except (ValueError, AttributeError):
                        pass

                # Extract full geometry
                geodata['geometrie'] = geometrie

        # If no centroide from verblijfsobject, try pand
        if not geodata['centroide_ll'] and pand:
            geometrie = pand.get('geometrie', {})
            if geometrie:
                # Extract centroide_ll (WGS84)
                centroide_ll = geometrie.get('centroide_ll')
                if centroide_ll:
                    geodata['centroide_ll'] = centroide_ll
                    # Parse latitude and longitude
                    try:
                        coords = centroide_ll.split(',')
                        if len(coords) == 2:
                            geodata['latitude'] = float(coords[0].strip())
                            geodata['longitude'] = float(coords[1].strip())
                    except (ValueError, AttributeError):
                        pass

                # Extract centroide_rd (Dutch RD)
                centroide_rd = geometrie.get('centroide_rd')
                if centroide_rd:
                    geodata['centroide_rd'] = centroide_rd
                    # Parse X and Y coordinates
                    try:
                        coords = centroide_rd.split(',')
                        if len(coords) == 2:
                            geodata['x_coord'] = float(coords[0].strip())
                            geodata['y_coord'] = float(coords[1].strip())
                    except (ValueError, AttributeError):
                        pass

                # Extract full geometry if not already set
                if not geodata['geometrie']:
                    geodata['geometrie'] = geometrie

        print(f'DEBUG BAG: Extracted geodata: {geodata}', flush=True)
        return geodata 