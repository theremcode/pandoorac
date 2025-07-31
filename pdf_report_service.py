"""
PDF Report Service voor Pandoorac
Genereert professionele taxatierapporten in PDF formaat
"""

import os
import json
from datetime import datetime
from weasyprint import HTML, CSS
from flask import render_template, current_app
from jinja2 import Environment, FileSystemLoader
import requests
from io import BytesIO
import base64
from urllib.parse import urlencode
import math


class PDFReportService:
    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize the PDF service with Flask app"""
        self.app = app
        # Ensure templates directory exists
        self.template_dir = os.path.join(app.root_path, 'templates', 'pdf_reports')
        os.makedirs(self.template_dir, exist_ok=True)
    
    def generate_taxatie_rapport(self, dossier, taxatie=None):
        """
        Genereer een PDF rapport voor een dossier en optionele taxatie
        
        Args:
            dossier: Dossier object
            taxatie: Taxatie object (optioneel, gebruikt laatste als None)
        
        Returns:
            tuple: (pdf_bytes, filename)
        """
        # Gebruik laatste taxatie als geen specifieke taxatie is gegeven
        if taxatie is None and dossier.taxaties:
            taxatie = max(dossier.taxaties, key=lambda t: t.datum)
        
        # Bepaal of het een woonfunctie is
        is_woonfunctie = (dossier.gebruiksdoel and 
                         'woonfunctie' in dossier.gebruiksdoel.lower())
        
        # Verzamel alle benodigde data
        rapport_data = self._collect_rapport_data(dossier, taxatie, is_woonfunctie)
        
        # Genereer HTML van template
        html_content = self._generate_html(rapport_data, is_woonfunctie)
        
        # Converteer naar PDF
        pdf_bytes = self._html_to_pdf(html_content)
        
        # Genereer filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"taxatierapport_{dossier.id}_{timestamp}.pdf"
        
        return pdf_bytes, filename
    
    def _collect_rapport_data(self, dossier, taxatie, is_woonfunctie):
        """Verzamel alle data voor het rapport"""
        data = {
            'dossier': dossier,
            'taxatie': taxatie,
            'is_woonfunctie': is_woonfunctie,
            'generatie_datum': datetime.now(),
            'bag_data': None,
            'woz_data': None,
            'kaart_url': None
        }
        
        # BAG data ophalen
        try:
            data['bag_data'] = self._get_bag_data(dossier)
        except Exception as e:
            current_app.logger.warning(f"Kon BAG data niet ophalen: {e}")
        
        # WOZ data ophalen (alleen voor woonfuncties)
        if is_woonfunctie:
            try:
                data['woz_data'] = self._get_woz_data(dossier)
            except Exception as e:
                current_app.logger.warning(f"Kon WOZ data niet ophalen: {e}")
        
        # Kaart snapshot genereren
        try:
            data['kaart_snapshot'] = self._generate_map_snapshot(dossier)
        except Exception as e:
            current_app.logger.warning(f"Kon kaart snapshot niet genereren: {e}")
            data['kaart_snapshot'] = None
        
        return data
    
    def _get_bag_data(self, dossier):
        """Haal BAG data direct uit de database"""
        try:
            # Haal BAG data direct uit de database via de relationship
            if dossier.bag_data:
                bag = dossier.bag_data[0]  # Neem de eerste BAG entry
                
                # Structureer de data zoals verwacht door het template
                bag_data = {
                    'adresseerbaarobjectid': bag.adresseerbaarobjectid,
                    'nummeraanduidingid': bag.nummeraanduidingid,
                    'pand_id': bag.pand_id,
                    'straatnaam': bag.straatnaam,
                    'huisnummer': bag.huisnummer,
                    'huisletter': bag.huisletter,
                    'postcode': bag.postcode,
                    'woonplaats': bag.woonplaats,
                    'bouwjaar': bag.bouwjaar,
                    'oppervlakte': bag.oppervlakte,
                    'inhoud': bag.inhoud,
                    'hoogte': bag.hoogte,
                    'aantal_bouwlagen': bag.aantal_bouwlagen,
                    'gebruiksdoel': bag.gebruiksdoel,
                    'centroide_ll': bag.centroide_ll,
                    'centroide_rd': bag.centroide_rd,
                    'geometrie': bag.geometrie,
                    'latitude': bag.latitude,
                    'longitude': bag.longitude,
                    'x_coord': bag.x_coord,
                    'y_coord': bag.y_coord,
                    'google_maps_url': bag.google_maps_url,
                    'last_updated': bag.last_updated.isoformat() if bag.last_updated else None
                }
                
                current_app.logger.info(f"BAG data uit database gehaald voor dossier {dossier.id}")
                return bag_data
            else:
                current_app.logger.info(f"Geen BAG data gevonden voor dossier {dossier.id}")
                return None
                
        except Exception as e:
            current_app.logger.error(f"BAG data uit database halen mislukt: {e}")
            return None
    
    def _get_woz_data(self, dossier):
        """Haal WOZ data direct uit de database"""
        try:
            # Haal WOZ data direct uit de database via de relationship
            if dossier.woz_data:
                woz = dossier.woz_data[0]  # Neem de eerste WOZ entry
                
                # Structureer de data zoals verwacht door het template
                woz_data = {
                    'woz_data': {
                        'wozobjectnummer': woz.wozobjectnummer,
                        'woonplaatsnaam': woz.woonplaatsnaam,
                        'openbareruimtenaam': woz.openbareruimtenaam,
                        'openbareruimtetype': woz.openbareruimtetype,
                        'straatnaam': woz.straatnaam,
                        'postcode': woz.postcode,
                        'huisnummer': woz.huisnummer,
                        'huisletter': woz.huisletter,
                        'huisnummertoevoeging': woz.huisnummertoevoeging,
                        'gemeentecode': woz.gemeentecode,
                        'grondoppervlakte': woz.grondoppervlakte,
                        'adresseerbaarobjectid': woz.adresseerbaarobjectid,
                        'nummeraanduidingid': woz.nummeraanduidingid,
                        'kadastrale_gemeente_code': woz.kadastrale_gemeente_code,
                        'kadastrale_sectie': woz.kadastrale_sectie,
                        'kadastraal_perceel_nummer': woz.kadastraal_perceel_nummer
                    },
                    'woz_values': []
                }
                
                # Voeg WOZ waarden toe
                for woz_value in woz.woz_values:
                    woz_data['woz_values'].append({
                        'peildatum': woz_value.peildatum.strftime('%Y-%m-%d') if woz_value.peildatum else None,
                        'vastgestelde_waarde': woz_value.vastgestelde_waarde
                    })
                
                # Sorteer WOZ waarden op peildatum (nieuwste eerst)
                woz_data['woz_values'].sort(key=lambda x: x['peildatum'] if x['peildatum'] else '', reverse=True)
                
                current_app.logger.info(f"WOZ data uit database gehaald voor dossier {dossier.id}")
                return woz_data
            else:
                current_app.logger.info(f"Geen WOZ data gevonden voor dossier {dossier.id}")
                return None
                
        except Exception as e:
            current_app.logger.error(f"WOZ data uit database halen mislukt: {e}")
            return None
    
    def _generate_map_snapshot(self, dossier):
        """Genereer een kaart snapshot voor het rapport"""
        try:
            # Probeer eerst PDOK data (nauwkeuriger)
            if dossier.pdok_data:
                pdok = dossier.pdok_data[0]
                if pdok.latitude and pdok.longitude:
                    lat, lon = float(pdok.latitude), float(pdok.longitude)
                    current_app.logger.info(f"PDOK coördinaten gevonden: {lat}, {lon}")
                    return self._create_static_map(lat, lon, dossier.adres, "PDOK")
            
            # Probeer dan BAG data
            if dossier.bag_data:
                bag = dossier.bag_data[0]
                if bag.latitude and bag.longitude:
                    lat, lon = float(bag.latitude), float(bag.longitude)
                    current_app.logger.info(f"BAG coördinaten gevonden: {lat}, {lon}")
                    return self._create_static_map(lat, lon, dossier.adres, "BAG")
            
            current_app.logger.warning(f"Geen coördinaten beschikbaar voor dossier {dossier.id}")
            return None
            
        except Exception as e:
            current_app.logger.error(f"Fout bij genereren kaart snapshot: {e}")
            return None
    
    def _create_static_map(self, lat, lon, address, source):
        """Maak een statische kaart image voor PDF embedding"""
        try:
            # Gebruik OpenStreetMap tiles via een statische map service
            # We gebruiken de OSM Static Maps API
            width, height = 600, 400
            zoom = 16
            
            # Probeer verschillende static map services
            image_data = None
            
            # 1. Probeer eerst OpenTopoMap (gratis, geen API key nodig)
            try:
                # OpenTopoMap static map service
                map_url = f"https://tile.opentopomap.org/{zoom}/{self._deg2num(lat, lon, zoom)[0]}/{self._deg2num(lat, lon, zoom)[1]}.png"
                current_app.logger.info(f"Proberen OpenTopoMap: {map_url}")
                
                response = requests.get(map_url, timeout=10)
                if response.status_code == 200 and len(response.content) > 1000:
                    image_data = base64.b64encode(response.content).decode('utf-8')
                    current_app.logger.info("OpenTopoMap kaart succesvol gedownload")
            except Exception as e:
                current_app.logger.warning(f"OpenTopoMap mislukt: {e}")
            
            # 2. Als OpenTopoMap niet werkt, probeer een eenvoudige tile combinatie
            if not image_data:
                try:
                    # Gebruik OSM tiles direct
                    tile_x, tile_y = self._deg2num(lat, lon, zoom)
                    map_url = f"https://tile.openstreetmap.org/{zoom}/{tile_x}/{tile_y}.png"
                    
                    current_app.logger.info(f"Proberen OSM tile: {map_url}")
                    
                    response = requests.get(map_url, timeout=10, headers={
                        'User-Agent': 'PandooracTaxatieApp/1.0'
                    })
                    
                    if response.status_code == 200 and len(response.content) > 1000:
                        image_data = base64.b64encode(response.content).decode('utf-8')
                        current_app.logger.info("OSM tile succesvol gedownload")
                except Exception as e:
                    current_app.logger.warning(f"OSM tile mislukt: {e}")
            
            # 3. Als alle opties mislukken, maak een eenvoudige placeholder
            if not image_data:
                current_app.logger.warning("Alle kaart services mislukt, gebruik placeholder")
                return {
                    'coordinates': {'lat': lat, 'lon': lon},
                    'center_address': address,
                    'source': source,
                    'map_reference': f"Locatie: {lat:.6f}, {lon:.6f}",
                    'zoom': zoom
                }
            
            return {
                'image_data': image_data,
                'coordinates': {'lat': lat, 'lon': lon},
                'center_address': address,
                'source': source,
                'zoom': zoom
            }
            
        except Exception as e:
            current_app.logger.error(f"Fout bij maken statische kaart: {e}")
            return None
    
    def _deg2num(self, lat_deg, lon_deg, zoom):
        """Converteer lat/lon naar tile nummers voor OSM tiles"""
        import math
        lat_rad = math.radians(lat_deg)
        n = 2.0 ** zoom
        x = int((lon_deg + 180.0) / 360.0 * n)
        y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
        return (x, y)
    
    def _generate_html(self, data, is_woonfunctie):
        """Genereer HTML content voor het rapport"""
        template_name = 'taxatie_rapport_woonfunctie.html' if is_woonfunctie else 'taxatie_rapport_algemeen.html'
        
        # Gebruik Jinja2 om template te renderen
        env = Environment(loader=FileSystemLoader(self.template_dir))
        
        # Voeg custom filters toe
        env.filters['currency'] = self._format_currency
        env.filters['date'] = self._format_date
        env.filters['percentage'] = self._format_percentage
        
        try:
            template = env.get_template(template_name)
            html_content = template.render(**data)
            return html_content
        except Exception as e:
            current_app.logger.error(f"Template rendering mislukt: {e}")
            # Fallback naar basis template
            return self._generate_fallback_html(data)
    
    def _generate_fallback_html(self, data):
        """Genereer een basis HTML rapport als fallback"""
        dossier = data['dossier']
        taxatie = data['taxatie']
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Taxatierapport - {dossier.naam}</title>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                .header {{ text-align: center; border-bottom: 2px solid #333; padding-bottom: 20px; }}
                .section {{ margin: 20px 0; }}
                table {{ width: 100%; border-collapse: collapse; }}
                th, td {{ padding: 8px; text-align: left; border-bottom: 1px solid #ddd; }}
                th {{ background-color: #f2f2f2; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Taxatierapport</h1>
                <p>{dossier.naam}</p>
                <p>{dossier.adres}, {dossier.postcode} {dossier.plaats}</p>
            </div>
            
            <div class="section">
                <h2>Pandgegevens</h2>
                <table>
                    <tr><th>Adres</th><td>{dossier.adres}</td></tr>
                    <tr><th>Postcode</th><td>{dossier.postcode}</td></tr>
                    <tr><th>Plaats</th><td>{dossier.plaats}</td></tr>
                    <tr><th>Bouwjaar</th><td>{dossier.bouwjaar or '-'}</td></tr>
                    <tr><th>Oppervlakte</th><td>{dossier.oppervlakte or '-'} m²</td></tr>
                    <tr><th>Gebruiksdoel</th><td>{dossier.gebruiksdoel or '-'}</td></tr>
                </table>
            </div>
            
            {f'''
            <div class="section">
                <h2>Taxatiegegevens</h2>
                <table>
                    <tr><th>Datum</th><td>{taxatie.datum}</td></tr>
                    <tr><th>Taxateur</th><td>{taxatie.taxateur}</td></tr>
                    <tr><th>Waarde</th><td>€ {taxatie.waarde:,.2f}</td></tr>
                    <tr><th>Oppervlakte</th><td>{taxatie.oppervlakte or '-'} m²</td></tr>
                    <tr><th>Opmerkingen</th><td>{taxatie.opmerkingen or '-'}</td></tr>
                </table>
            </div>
            ''' if taxatie else '<p>Geen taxatiegegevens beschikbaar</p>'}
            
            <div class="section">
                <p><small>Gegenereerd op: {data['generatie_datum'].strftime('%d-%m-%Y %H:%M')}</small></p>
            </div>
        </body>
        </html>
        """
        return html
    
    def _html_to_pdf(self, html_content):
        """Converteer HTML naar PDF bytes"""
        try:
            # CSS voor PDF styling
            css_string = """
            @page {
                size: A4;
                margin: 2cm;
            }
            body {
                font-family: 'Arial', sans-serif;
                font-size: 12pt;
                line-height: 1.5;
            }
            .page-break {
                page-break-before: always;
            }
            """
            
            # Genereer PDF
            html = HTML(string=html_content)
            css = CSS(string=css_string)
            pdf_bytes = html.write_pdf(stylesheets=[css])
            
            return pdf_bytes
        except Exception as e:
            current_app.logger.error(f"PDF generatie mislukt: {e}")
            raise
    
    @staticmethod
    def _format_currency(value):
        """Format currency for templates"""
        if value is None:
            return "-"
        return f"€ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    
    @staticmethod
    def _format_date(value):
        """Format date for templates"""
        if value is None:
            return "-"
        if isinstance(value, str):
            return value
        return value.strftime('%d-%m-%Y')
    
    @staticmethod
    def _format_percentage(value):
        """Format percentage for templates"""
        if value is None:
            return "-"
        return f"{value:,.2f}%".replace(",", "X").replace(".", ",").replace("X", ".")


# Service instance
pdf_service = PDFReportService()
