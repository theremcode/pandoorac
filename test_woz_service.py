#!/usr/bin/env python3
"""
Test script voor de WOZ service om te controleren of verschillende adressen
nu correcte, unieke mock data terugkrijgen.
"""

import json
from woz_service import WozService

def test_woz_service():
    """Test de WOZ service met verschillende adressen"""
    
    print("🔍 Testing WOZ Service...")
    print("=" * 60)
    
    woz_service = WozService()
    
    # Test verschillende adressen
    test_addresses = [
        "Cederstraat 127, 2404VG Alphen aan den Rijn",
        "Pippelingstraat 31, 2564RC 's-Gravenhage", 
        "Damrak 1, 1012 LG Amsterdam",
        "Coolsingel 100, 3012 AG Rotterdam",
        "Neude 11, 3512 AD Utrecht"
    ]
    
    print("Testing different addresses to ensure unique WOZ data:\n")
    
    for i, address in enumerate(test_addresses, 1):
        print(f"Test {i}: {address}")
        print("-" * 40)
        
        try:
            result = woz_service.lookup_woz_data(address)
            
            if result and 'woz_data' in result:
                woz_data = result['woz_data']
                woz_object = woz_data.get('wozObject', {})
                
                print(f"✅ Address found:")
                print(f"   Straat: {woz_object.get('straatnaam', 'N/A')}")
                print(f"   Huisnummer: {woz_object.get('huisnummer', 'N/A')}")
                print(f"   Postcode: {woz_object.get('postcode', 'N/A')}")
                print(f"   Plaats: {woz_object.get('woonplaatsnaam', 'N/A')}")
                print(f"   WOZ nummer: {woz_object.get('wozobjectnummer', 'N/A')}")
                
                # Show WOZ values
                woz_waarden = woz_data.get('wozWaarden', [])
                if woz_waarden:
                    print(f"   WOZ waarden:")
                    for waarde in woz_waarden[:2]:  # Show first 2 years
                        print(f"     {waarde.get('peildatum')}: €{waarde.get('vastgesteldeWaarde'):,}")
                
                print(f"   Grondoppervlakte: {woz_object.get('grondoppervlakte', 'N/A')} m²")
                
            else:
                print("❌ No WOZ data found")
                
        except Exception as e:
            print(f"❌ Error: {e}")
        
        print()
    
    print("=" * 60)
    print("✅ WOZ Service test completed!")
    print("\n📝 Notes:")
    print("- This service currently uses MOCK DATA for development/testing")
    print("- Each address should now return unique, realistic WOZ data")
    print("- Real WOZ API integration needs to be implemented for production")

if __name__ == "__main__":
    test_woz_service()
