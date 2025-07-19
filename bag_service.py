import requests
import re
import json
import urllib.parse

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
            # Extra validatie: alleen accepteren als huisnummer en postcode exact overeenkomen met input
            gevonden_huisnummer = str(adres.get('huisnummer', '')).strip()
            gevonden_postcode = str(adres.get('postcode', '')).replace(' ', '').upper()
            if gevonden_huisnummer != str(original_huisnummer).strip() or gevonden_postcode != postcode:
                return {'error': f'Geen exact adres gevonden voor {postcode} {original_huisnummer}'}, 404

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

            # 6. Verzamel geodata - alleen van BAG, geen PDOK
            adres_info = {
                'straat': straat,
                'huisnummer': huisnummer,
                'huisletter': huisletter,
                'postcode': postcode,
                'woonplaats': woonplaats
            }
            geodata = self._extract_geodata_from_bag(verblijfsobject, pand, adres_info)

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
                'adresseerbaarobjectid': verblijfsobject.get('identificatie'),
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


    def rd_to_wgs84_simple(self, x, y):
        """
        Convert RD (EPSG:28992) coordinates to WGS84 (EPSG:4326) using official transformation
        Based on the RDNAPTRANS procedure from Kadaster
        """
        try:
            import math
            
            # Transformation from RD to WGS84 using official parameters
            # This is a simplified but accurate version of the RDNAPTRANS transformation
            
            # Step 1: Transform RD to Bessel coordinates
            # RD projection constants
            X0 = 155000.00  # Reference point X
            Y0 = 463000.00  # Reference point Y
            
            # Calculate normalized coordinates
            dX = (x - X0) * 1e-5
            dY = (y - Y0) * 1e-5
            
            # Coefficients for latitude (phi) transformation
            Kp = [0, 2, 0, 2, 0, 2, 1, 4, 2, 4, 1]
            Kq = [1, 0, 2, 1, 3, 2, 0, 0, 3, 1, 1]
            Kpq = [3235.65389, -32.58297, -0.24750, -0.84978, -0.06550, -0.01709,
                   -0.00738, 0.00530, -0.00039, 0.00033, -0.00012]
            
            # Coefficients for longitude (lambda) transformation  
            Lp = [1, 1, 1, 3, 1, 3, 0, 3, 1, 0, 2, 5]
            Lq = [0, 1, 2, 0, 3, 1, 1, 2, 4, 2, 0, 0]
            Lpq = [5260.52916, 105.94684, 2.45656, -0.81885, 0.05594, -0.05607,
                   0.01199, -0.00256, 0.00128, 0.00022, -0.00022, 0.00026]
            
            # Calculate phi (latitude) on Bessel ellipsoid
            phi = 52.15517440
            for i in range(len(Kpq)):
                phi += (Kpq[i] * (dX ** Kp[i]) * (dY ** Kq[i])) / 3600
            
            # Calculate lambda (longitude) on Bessel ellipsoid
            lambda_val = 5.38720621  
            for i in range(len(Lpq)):
                lambda_val += (Lpq[i] * (dX ** Lp[i]) * (dY ** Lq[i])) / 3600
            
            # Step 2: Transform from Bessel to WGS84 datum
            # These are the official datum shift parameters for Netherlands
            latitude = phi - 0.00033077 + 0.00001763 * (phi - 52) - 0.00000772 * (lambda_val - 5.4)
            longitude = lambda_val + 0.00007371 - 0.00001753 * (phi - 52) - 0.00000039 * (lambda_val - 5.4)
            
            return latitude, longitude
            
        except Exception as e:
            print(f"Error in RD to WGS84 conversion: {e}")
            return None, None

    def _extract_geodata_from_bag(self, verblijfsobject, pand, adres_info=None):
        """Extract geodata from BAG API responses only - no PDOK integration"""
        geodata = {
            'centroide_ll': None,  # Latitude/Longitude
            'centroide_rd': None,  # Dutch RD coordinates
            'geometrie': None,     # Building geometry/polygon
            'latitude': None,
            'longitude': None,
            'x_coord': None,
            'y_coord': None,
            'google_maps_url': None
        }

        # Extract geodata from verblijfsobject (preferred)
        if verblijfsobject:
            geometrie = verblijfsobject.get('geometrie', {})
            if geometrie:
                # Extract coordinates from punt object (RD coordinates)
                punt = geometrie.get('punt')
                if punt and punt.get('type') == 'Point' and isinstance(punt.get('coordinates'), list) and len(punt['coordinates']) >= 2:
                    x, y = punt['coordinates'][0], punt['coordinates'][1]
                    geodata['x_coord'] = x
                    geodata['y_coord'] = y
                    geodata['centroide_rd'] = f"{x},{y}"
                    print(f"DEBUG BAG: Using verblijfsobject coordinates: {x}, {y}", flush=True)
                    
                    # Convert RD to WGS84 for other map layers
                    lat, lon = self.rd_to_wgs84_simple(x, y)
                    if lat and lon:
                        geodata['latitude'] = lat
                        geodata['longitude'] = lon
                        geodata['centroide_ll'] = f"{lat},{lon}"

                # Extract full geometry
                geodata['geometrie'] = geometrie

        # If no coordinates from verblijfsobject, try pand
        if not geodata.get('x_coord') and pand:
            geometrie = pand.get('geometrie', {})
            if geometrie:
                # Try to extract centroid from pand polygon
                if geometrie.get('type') == 'Polygon':
                    coordinates = geometrie.get('coordinates', [])
                    if coordinates and len(coordinates) > 0:
                        # Calculate centroid of polygon
                        polygon_coords = coordinates[0]  # First ring
                        if len(polygon_coords) >= 3:
                            # Simple centroid calculation
                            sum_x = sum(coord[0] for coord in polygon_coords if len(coord) >= 2)
                            sum_y = sum(coord[1] for coord in polygon_coords if len(coord) >= 2)
                            count = len(polygon_coords)
                            
                            if count > 0:
                                x = sum_x / count
                                y = sum_y / count
                                geodata['x_coord'] = x
                                geodata['y_coord'] = y
                                geodata['centroide_rd'] = f"{x},{y}"
                                print(f"DEBUG BAG: Using pand polygon centroid: {x}, {y}", flush=True)
                                
                                # Convert RD to WGS84
                                lat, lon = self.rd_to_wgs84_simple(x, y)
                                if lat and lon:
                                    geodata['latitude'] = lat
                                    geodata['longitude'] = lon
                                    geodata['centroide_ll'] = f"{lat},{lon}"

                # Extract full geometry if not already set
                if not geodata['geometrie']:
                    geodata['geometrie'] = geometrie

        # Add Google Maps URL based on address
        if adres_info:
            google_maps_url = self.create_google_maps_url(
                adres_info.get('straat', ''),
                adres_info.get('huisnummer', ''),
                adres_info.get('huisletter', ''),
                adres_info.get('postcode', ''),
                adres_info.get('woonplaats', '')
            )
            if google_maps_url:
                geodata['google_maps_url'] = google_maps_url

        print(f'DEBUG BAG: Extracted geodata: {geodata}', flush=True)
        return geodata

    def create_google_maps_url(self, straat, huisnummer, huisletter, postcode, woonplaats):
        """
        Create a Google Maps URL using address instead of coordinates for better accuracy
        """
        try:
            import urllib.parse
            
            # Construct the full address
            address_parts = [straat, str(huisnummer)]
            if huisletter:
                address_parts.append(huisletter)
            address_parts.extend([postcode, woonplaats])
            
            full_address = " ".join(address_parts)
            
            # URL encode the address
            encoded_address = urllib.parse.quote_plus(full_address)
            
            # Create Google Maps URL
            google_maps_url = f"https://www.google.com/maps/place/{encoded_address}"
            
            print(f'DEBUG BAG: Generated Google Maps URL: {google_maps_url}', flush=True)
            return google_maps_url
            
        except Exception as e:
            print(f"Error creating Google Maps URL: {e}")
            return None 