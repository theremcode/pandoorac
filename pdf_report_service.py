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
        
        # Kaart URL genereren
        try:
            data['kaart_url'] = self._generate_map_url(dossier)
        except Exception as e:
            current_app.logger.warning(f"Kon kaart URL niet genereren: {e}")
        
        return data
    
    def _get_bag_data(self, dossier):
        """Haal BAG data op via de bestaande service"""
        try:
            from bag_service import BagService
            bag_service = BagService()
            
            # Probeer BAG data op te halen
            full_address = f"{dossier.adres}, {dossier.postcode} {dossier.plaats}"
            bag_data = bag_service.get_bag_info(full_address)
            
            return bag_data
        except Exception as e:
            current_app.logger.error(f"BAG data ophalen mislukt: {e}")
            return None
    
    def _get_woz_data(self, dossier):
        """Haal WOZ data op via de bestaande service"""
        try:
            from woz_service import WozService
            woz_service = WozService()
            
            # Probeer WOZ data op te halen
            full_address = f"{dossier.adres}, {dossier.postcode} {dossier.plaats}"
            woz_data = woz_service.get_woz_data(full_address)
            
            return woz_data
        except Exception as e:
            current_app.logger.error(f"WOZ data ophalen mislukt: {e}")
            return None
    
    def _generate_map_url(self, dossier):
        """Genereer een statische kaart URL"""
        # Gebruik PDOK voor Nederlandse kaarten
        base_url = "https://service.pdok.nl/brt/achtergrondkaart/wmts/v2_0"
        
        # Approximeer coördinaten op basis van postcode (basis implementatie)
        # In productie zou je dit via geocoding services doen
        lat, lon = self._approximate_coordinates(dossier.postcode)
        
        # Genereer eenvoudige kaart URL (dit is een placeholder)
        # In productie zou je een echte mapping service gebruiken
        map_url = f"https://via.placeholder.com/400x300/f0f0f0/333333?text=Kaart+{dossier.postcode}"
        
        return map_url
    
    def _approximate_coordinates(self, postcode):
        """Approximeer coördinaten (placeholder)"""
        # Dit is een zeer simpele implementatie
        # In productie zou je een echte geocoding service gebruiken
        return 52.1326, 5.2913  # Utrecht centrum als fallback
    
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
