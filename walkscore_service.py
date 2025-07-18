import requests
import json
from datetime import datetime
from typing import Dict, Optional, Tuple

class WalkScoreService:
    def __init__(self, api_url: str = None, api_key: str = None):
        """
        Initialize WalkScore service
        
        Args:
            api_url: WalkScore API URL (optional, can be set later)
            api_key: WalkScore API key (optional, can be set later)
        """
        self.api_url = api_url or "https://api.walkscore.com/score"
        self.api_key = api_key
        self.session = requests.Session()
    
    def set_credentials(self, api_url: str, api_key: str):
        """Set API credentials"""
        self.api_url = api_url
        self.api_key = api_key
    
    def lookup_walkscore(self, straat: str = None, huisnummer: str = None, huisletter: str = None, postcode: str = None, woonplaats: str = None, lat: float = None, lon: float = None) -> Tuple[Dict, int]:
        """
        Lookup WalkScore for an address
        
        Args:
            straat: Street name
            huisnummer: House number
            huisletter: House letter (optional)
            postcode: Postal code
            woonplaats: City name
            lat: Latitude (required for WalkScore API)
            lon: Longitude (required for WalkScore API)
            
        Returns:
            Tuple of (response_data, status_code)
        """
        if not self.api_key:
            return {
                'error': 'WalkScore API key not configured',
                'success': False
            }, 400
        
        # Check if coordinates are provided (required by WalkScore API)
        if lat is None or lon is None:
            return {
                'error': 'Latitude and longitude are required for WalkScore API',
                'success': False
            }, 400
        
        # Build address string in proper format for WalkScore
        address_parts = []
        
        # Add street and house number (preferred format)
        if straat and huisnummer:
            house_part = str(huisnummer)
            if huisletter:
                house_part += huisletter
            address_parts.append(f"{straat} {house_part}")
        elif huisnummer:
            # Fallback: just house number
            house_part = str(huisnummer)
            if huisletter:
                house_part += huisletter
            address_parts.append(house_part)
        
        # Add postal code and city
        if postcode:
            address_parts.append(postcode)
        if woonplaats:
            address_parts.append(woonplaats)
        elif not straat and postcode:
            # If no city name, add "Netherlands" for better geocoding
            address_parts.append("Netherlands")
        
        # Join address parts
        if address_parts:
            address = " ".join(address_parts)
        else:
            # Ultimate fallback: use coordinates as address
            address = f"{lat},{lon}"
        
        print(f'DEBUG WalkScore: Using address: {address}', flush=True)
        
        try:
            # Prepare API request parameters
            params = {
                'format': 'json',
                'address': address,
                'lat': lat,
                'lon': lon,
                'wsapikey': self.api_key,
                'transit': 1,  # Include transit score
                'bike': 1      # Include bike score
            }
            
            # Make API request
            response = self.session.get(self.api_url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check for API errors in the response
                if data.get('status') == 40:
                    return {
                        'error': 'Invalid WalkScore API key',
                        'success': False
                    }, 400
                elif data.get('status') == 41:
                    return {
                        'error': 'Daily WalkScore API quota exceeded',
                        'success': False
                    }, 429
                elif data.get('status') == 42:
                    return {
                        'error': 'IP address blocked by WalkScore API',
                        'success': False
                    }, 403
                elif data.get('status') == 30:
                    return {
                        'error': 'Invalid latitude/longitude coordinates',
                        'success': False
                    }, 400
                elif data.get('status') == 31:
                    return {
                        'error': 'WalkScore API internal error',
                        'success': False
                    }, 500
                elif data.get('status') == 2:
                    return {
                        'error': 'WalkScore is being calculated and not currently available',
                        'success': False
                    }, 202
                
                # Parse WalkScore response
                parsed_data = self._parse_walkscore_response(data)
                return {
                    'success': True,
                    'data': parsed_data,
                    'raw_response': data
                }, 200
            else:
                return {
                    'error': f'WalkScore API error: {response.status_code}',
                    'success': False,
                    'status_code': response.status_code
                }, response.status_code
                
        except requests.exceptions.RequestException as e:
            return {
                'error': f'Network error: {str(e)}',
                'success': False
            }, 500
        except json.JSONDecodeError as e:
            return {
                'error': f'Invalid JSON response: {str(e)}',
                'success': False
            }, 500
        except Exception as e:
            return {
                'error': f'Unexpected error: {str(e)}',
                'success': False
            }, 500
    
    def _parse_walkscore_response(self, data: Dict) -> Dict:
        """
        Parse WalkScore API response
        
        Args:
            data: Raw API response
            
        Returns:
            Parsed WalkScore data
        """
        try:
            parsed = {
                'walkscore': data.get('walkscore', 0),
                'description': data.get('description', ''),
                'logo_url': data.get('logo_url', ''),
                'more_info_icon': data.get('more_info_icon', ''),
                'more_info_link': data.get('more_info_link', ''),
                'ws_link': data.get('ws_link', ''),
                'help_link': data.get('help_link', ''),
                'snapped_lat': data.get('snapped_lat'),
                'snapped_lon': data.get('snapped_lon'),
                'transit': {},
                'bike': {}
            }
            
            # Parse transit data
            if 'transit' in data and data['transit']:
                transit = data['transit']
                parsed['transit'] = {
                    'score': transit.get('score', 0),
                    'description': transit.get('description', ''),
                    'summary': transit.get('summary', '')
                }
            
            # Parse bike data
            if 'bike' in data and data['bike']:
                bike = data['bike']
                parsed['bike'] = {
                    'score': bike.get('score', 0),
                    'description': bike.get('description', '')
                }
            
            return parsed
            
        except Exception as e:
            return {
                'error': f'Error parsing WalkScore data: {str(e)}',
                'walkscore': 0,
                'description': 'Error parsing data'
            }
    
    def get_walkscore_category(self, score: int) -> str:
        """
        Get WalkScore category based on score
        
        Args:
            score: WalkScore (0-100)
            
        Returns:
            Category string
        """
        if score >= 90:
            return "Walker's Paradise"
        elif score >= 70:
            return "Very Walkable"
        elif score >= 50:
            return "Somewhat Walkable"
        elif score >= 25:
            return "Car-Dependent"
        else:
            return "Car-Dependent"
    
    def get_walkscore_color(self, score: int) -> str:
        """
        Get color for WalkScore display
        
        Args:
            score: WalkScore (0-100)
            
        Returns:
            CSS color class
        """
        if score >= 90:
            return "text-green-600"
        elif score >= 70:
            return "text-green-500"
        elif score >= 50:
            return "text-yellow-600"
        elif score >= 25:
            return "text-orange-500"
        else:
            return "text-red-500" 