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
    
    def get_woz_data(self, nummeraanduiding_id):
        """Get WOZ data - for now using mock data since WOZ waardeloket API is not directly accessible"""
        try:
            logger.info(f"Getting WOZ data for nummeraanduiding: {nummeraanduiding_id}")
            
            # For now, return mock WOZ data since the WOZ waardeloket API is not directly accessible
            # In a real implementation, this would call the WOZ API
            mock_woz_data = {
                "wozObject": {
                    "wozobjectnummer": f"WOZ-{nummeraanduiding_id[-8:]}",
                    "woonplaatsnaam": "'s-Gravenhage",
                    "openbareruimtenaam": "Pippelingstraat",
                    "straatnaam": "Pippelingstraat",
                    "postcode": "2564RC",
                    "huisnummer": 31,
                    "huisletter": "",
                    "huisnummertoevoeging": "",
                    "gemeentecode": "0518",
                    "grondoppervlakte": 120,
                    "adresseerbaarobjectid": f"0518010000{nummeraanduiding_id[-8:]}",
                    "nummeraanduidingid": nummeraanduiding_id,
                    "kadastrale_gemeente_code": "0518",
                    "kadastrale_sectie": "A",
                    "kadastraal_perceel_nummer": "1234"
                },
                "wozWaarden": [
                    {
                        "peildatum": "2025-01-01",
                        "vastgesteldeWaarde": 450000
                    },
                    {
                        "peildatum": "2024-01-01", 
                        "vastgesteldeWaarde": 425000
                    },
                    {
                        "peildatum": "2023-01-01",
                        "vastgesteldeWaarde": 400000
                    }
                ]
            }
            
            logger.info(f"Returning mock WOZ data: {mock_woz_data}")
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
            woz_data = self.get_woz_data(nummeraanduiding_id)
            
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