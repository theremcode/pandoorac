import requests
import json
from datetime import datetime
import time
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WozService:
    def __init__(self):
        # PDOK API URLs voor adres lookup
        self.suggest_url = "https://api.pdok.nl/bzk/locatieserver/search/v3_1/suggest"
        self.lookup_url = "https://api.pdok.nl/bzk/locatieserver/search/v3_1/lookup"
        
        # WOZ waardeloket API
        self.woz_base_url = "https://www.wozwaardeloket.nl"
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Pandoorac/1.0 (WOZ Service)'
        })
    
    def get_address_id(self, address):
        """Get address ID from PDOK Locatieserver using new API"""
        try:
            params = {
                'q': address
            }
            
            logger.info(f"Looking up address ID for: {address}")
            response = self.session.get(self.suggest_url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            logger.info(f"PDOK suggest response: {data}")
            
            if 'response' in data and 'docs' in data['response'] and data['response']['docs']:
                # Return the first matching address ID
                address_id = data['response']['docs'][0]['id']
                logger.info(f"Found address ID: {address_id}")
                return address_id
            
            logger.warning(f"No address ID found for: {address}")
            return None
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting address ID: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting address ID: {e}")
            return None
    
    def get_address_details(self, address_id):
        """Get address details from PDOK Locatieserver"""
        try:
            params = {
                'id': address_id
            }
            
            logger.info(f"Looking up details for address ID: {address_id}")
            response = self.session.get(self.lookup_url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            logger.info(f"PDOK lookup response: {data}")
            
            if 'response' in data and 'docs' in data['response'] and data['response']['docs']:
                address_data = data['response']['docs'][0]
                logger.info(f"Found address data: {address_data}")
                return address_data
            
            logger.warning(f"No address details found for ID: {address_id}")
            return None
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting address details: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting address details: {e}")
            return None
    
    def get_woz_data(self, nummeraanduiding_id, address_details=None):
        """Get WOZ data - for now using mock data since WOZ waardeloket API is not directly accessible"""
        try:
            logger.info(f"Getting WOZ data for nummeraanduiding: {nummeraanduiding_id}")
            
            # IMPORTANT WARNING: This is mock data for development/testing purposes
            logger.warning("⚠️  USING MOCK WOZ DATA - Real WOZ API integration not implemented yet")
            
            # For now, return mock WOZ data since the WOZ waardeloket API is not directly accessible
            # In a real implementation, this would call the WOZ API
            
            # Use actual address details if provided, otherwise use defaults
            if address_details:
                woonplaats = address_details.get('woonplaatsnaam', 'Onbekende plaats')
                straatnaam = address_details.get('straatnaam', 'Onbekende straat')
                postcode = address_details.get('postcode', '0000XX')
                huisnummer = address_details.get('huisnummer', 1)
                huisletter = address_details.get('huis_nlt', '') if address_details.get('huis_nlt', '').isalpha() else ''
                gemeentecode = address_details.get('gemeentecode', '0000')
                adresseerbaarobject_id = address_details.get('adresseerbaarobject_id', f"0000010000{nummeraanduiding_id[-8:]}")
            else:
                # Fallback defaults
                woonplaats = "Onbekende plaats"
                straatnaam = "Onbekende straat"
                postcode = "0000XX"
                huisnummer = 1
                huisletter = ""
                gemeentecode = "0000"
                adresseerbaarobject_id = f"0000010000{nummeraanduiding_id[-8:]}"
            
            # Generate realistic WOZ values based on location
            base_value = 350000  # Base WOZ value
            
            # Adjust base value based on postcode (rough estimation)
            if postcode.startswith('1'):  # Amsterdam area
                base_value = 500000
            elif postcode.startswith('2'):  # Rotterdam/Den Haag area
                base_value = 400000
            elif postcode.startswith('3'):  # Utrecht area
                base_value = 450000
            elif postcode.startswith('4'):  # Zuid-Holland
                base_value = 380000
            elif postcode.startswith('5'):  # Noord-Brabant
                base_value = 320000
            
            # Generate some variation based on address
            hash_value = hash(f"{straatnaam}{huisnummer}{postcode}") % 100000
            value_variation = hash_value - 50000  # -50k to +50k variation
            
            current_year = datetime.now().year
            woz_waarden = []
            
            for year_offset in range(3):  # Current year and 2 previous years
                year = current_year - year_offset
                # Add slight year-over-year growth (roughly 3-5% per year)
                yearly_value = int(base_value + value_variation * (1 + (year_offset * 0.04)))
                
                woz_waarden.append({
                    "peildatum": f"{year}-01-01",
                    "vastgesteldeWaarde": yearly_value
                })
            
            mock_woz_data = {
                "wozObject": {
                    "wozobjectnummer": f"WOZ-{nummeraanduiding_id[-8:]}",
                    "woonplaatsnaam": woonplaats,
                    "openbareruimtenaam": straatnaam,
                    "straatnaam": straatnaam,
                    "postcode": postcode,
                    "huisnummer": huisnummer,
                    "huisletter": huisletter,
                    "huisnummertoevoeging": "",
                    "gemeentecode": gemeentecode,
                    "grondoppervlakte": 120 + (hash_value % 200),  # 120-320 m²
                    "adresseerbaarobjectid": adresseerbaarobject_id,
                    "nummeraanduidingid": nummeraanduiding_id,
                    "kadastrale_gemeente_code": gemeentecode,
                    "kadastrale_sectie": chr(65 + (hash_value % 26)),  # A-Z
                    "kadastraal_perceel_nummer": str(1000 + (hash_value % 9000))  # 1000-9999
                },
                "wozWaarden": woz_waarden
            }
            
            logger.info(f"Returning realistic mock WOZ data for {straatnaam} {huisnummer}, {postcode} {woonplaats}")
            return mock_woz_data
                
        except Exception as e:
            logger.error(f"Error getting WOZ data: {e}")
            return None
    
    def lookup_woz_data(self, address):
        """Lookup WOZ data for an address"""
        try:
            logger.info(f"Starting WOZ lookup for address: {address}")
            
            # Step 1: Get address ID from PDOK
            address_id = self.get_address_id(address)
            if not address_id:
                logger.error(f"No address ID found for: {address}")
                return None
            
            # Step 2: Get address details from PDOK
            address_details = self.get_address_details(address_id)
            if not address_details:
                logger.error(f"No address details found for ID: {address_id}")
                return None
            
            # Step 3: Get WOZ data using nummeraanduiding ID
            nummeraanduiding_id = address_details.get('nummeraanduiding_id')
            if not nummeraanduiding_id:
                logger.error("No nummeraanduiding ID found in address details")
                return None
            
            logger.info(f"Getting WOZ data for nummeraanduiding: {nummeraanduiding_id}")
            woz_data = self.get_woz_data(nummeraanduiding_id, address_details)
            
            if woz_data:
                # Combine address details with WOZ data
                combined_data = {
                    **address_details,
                    'woz_data': woz_data
                }
                return combined_data
            else:
                logger.warning("No WOZ data found")
                return None
            
        except Exception as e:
            logger.error(f"Error in WOZ lookup: {e}")
            return None
    
    def parse_woz_data(self, woz_response):
        """Parse WOZ response data into structured format"""
        try:
            # Extract basic address information from PDOK data
            woz_data = {
                'wozobjectnummer': woz_response.get('wozobjectnummer', ''),
                'woonplaatsnaam': woz_response.get('woonplaatsnaam', ''),
                'openbareruimtenaam': woz_response.get('straatnaam', ''),
                'openbareruimtetype': woz_response.get('openbareruimtetype', ''),
                'straatnaam': woz_response.get('straatnaam', ''),
                'postcode': woz_response.get('postcode', ''),
                'huisnummer': woz_response.get('huisnummer', ''),
                'huisletter': woz_response.get('huisletter', ''),
                'huisnummertoevoeging': woz_response.get('huisnummertoevoeging', ''),
                'gemeentecode': woz_response.get('gemeentecode', ''),
                'grondoppervlakte': woz_response.get('grondoppervlakte', ''),
                'adresseerbaarobjectid': woz_response.get('adresseerbaarobject_id', ''),
                'nummeraanduidingid': woz_response.get('nummeraanduiding_id', ''),
                'kadastrale_gemeente_code': woz_response.get('kadastrale_gemeente_code', ''),
                'kadastrale_sectie': woz_response.get('kadastrale_sectie', ''),
                'kadastraal_perceel_nummer': woz_response.get('kadastraal_perceel_nummer', '')
            }
            
            # Extract WOZ values from WOZ data
            woz_values = []
            woz_waardeloket_data = woz_response.get('woz_data', {})
            
            if woz_waardeloket_data and 'wozWaarden' in woz_waardeloket_data:
                for woz_waarde in woz_waardeloket_data['wozWaarden']:
                    woz_values.append({
                        'peildatum': woz_waarde.get('peildatum', ''),
                        'vastgestelde_waarde': woz_waarde.get('vastgesteldeWaarde', 0)
                    })
            
            # Also check if WOZ data is directly in the response (for mock data)
            if 'wozWaarden' in woz_response:
                for woz_waarde in woz_response['wozWaarden']:
                    woz_values.append({
                        'peildatum': woz_waarde.get('peildatum', ''),
                        'vastgestelde_waarde': woz_waarde.get('vastgesteldeWaarde', 0)
                    })
            
            return {
                'woz_data': woz_data,
                'woz_values': woz_values
            }
            
        except Exception as e:
            logger.error(f"Error parsing WOZ data: {e}")
            return None 