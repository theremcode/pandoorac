from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, current_app, send_from_directory, abort, make_response, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os
import time
import logging
from config import config
from storage import StorageService
import io
from functools import wraps
import requests
import secrets
from bag_service import BagService
from woz_service import WozService
from walkscore_service import WalkScoreService
from pdok_service import PDOKService
import json
from terugmelding_service import get_bag_terugmeldingen


# Custom logging filter to suppress health check requests
class HealthCheckFilter(logging.Filter):
    def filter(self, record):
        # Filter out health check requests
        if hasattr(record, 'getMessage'):
            message = record.getMessage()
            if '/health' in message or '/health/startup' in message:
                return False
        return True

try:
    import magic
except ImportError:
    magic = None
    print('Waarschuwing: python-magic/libmagic niet gevonden. Bestandstype-detectie is uitgeschakeld.')

# Initialize Flask extensions
db = SQLAlchemy()
login_manager = LoginManager()
storage = StorageService()

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=True)  # Made nullable for Google auth
    email = db.Column(db.String(120), unique=True, nullable=True)
    full_name = db.Column(db.String(120), nullable=True)
    role = db.Column(db.String(20), nullable=False, default='user')
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    registration_status = db.Column(db.String(20), nullable=False, default='active')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Google OAuth fields
    google_id = db.Column(db.String(100), unique=True, nullable=True)
    google_email = db.Column(db.String(120), nullable=True)
    google_profile_picture = db.Column(db.String(500), nullable=True)
    auth_type = db.Column(db.String(20), nullable=False, default='local')  # 'local' or 'google'
    
    # StreetSmart account credentials
    streetsmart_username = db.Column(db.String(120), nullable=True)
    streetsmart_password_hash = db.Column(db.String(255), nullable=True)
    
    dossiers = db.relationship('Dossier', backref='user', lazy=True)
    logs = db.relationship('UserLog', backref='user', lazy=True)

    def set_password(self, password):
        if password:
            self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if self.password_hash:
            return check_password_hash(self.password_hash, password)
        return False
    
    def set_streetsmart_password(self, password):
        """Set StreetSmart password with encryption"""
        if password:
            self.streetsmart_password_hash = generate_password_hash(password)
        else:
            self.streetsmart_password_hash = None
    
    def check_streetsmart_password(self, password):
        """Check StreetSmart password"""
        if self.streetsmart_password_hash:
            return check_password_hash(self.streetsmart_password_hash, password)
        return False
    
    def get_streetsmart_credentials(self):
        """Get StreetSmart credentials for API use (returns None if not set)"""
        if self.streetsmart_username and self.streetsmart_password_hash:
            return {
                'username': self.streetsmart_username,
                'password_hash': self.streetsmart_password_hash
            }
        return None
    
    def is_google_user(self):
        """Check if user is authenticated via Google"""
        return self.auth_type == 'google' and self.google_id is not None

class Dossier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    naam = db.Column(db.String(100), nullable=False)
    adres = db.Column(db.String(200), nullable=False)
    postcode = db.Column(db.String(10), nullable=False)
    plaats = db.Column(db.String(100), nullable=False)
    bouwjaar = db.Column(db.String(10))
    oppervlakte = db.Column(db.String(20))
    inhoud = db.Column(db.String(20))
    hoogte = db.Column(db.String(20))
    aantal_bouwlagen = db.Column(db.String(10))
    gebruiksdoel = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    taxaties = db.relationship('Taxatie', backref='dossier', lazy=True)
    documents = db.relationship('Document', backref='dossier', lazy=True)
    woz_data = db.relationship('WozData', lazy=True)
    bag_data = db.relationship('BagData', lazy=True)
    walkscore_data = db.relationship('WalkScoreData', lazy=True)
    pdok_data = db.relationship('PDOKData', lazy=True)

class Taxatie(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    datum = db.Column(db.Date, nullable=False)
    taxateur = db.Column(db.String(100), nullable=False)
    waarde = db.Column(db.Float, nullable=False)
    opmerkingen = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default='concept')
    # New fields for automatic calculation
    hoogte_meters = db.Column(db.Float, nullable=True)
    prijs_per_m2 = db.Column(db.Float, nullable=True)
    prijs_per_m3 = db.Column(db.Float, nullable=True)
    berekening_methode = db.Column(db.String(20), nullable=True)  # 'm2' or 'm3'
    dossier_id = db.Column(db.Integer, db.ForeignKey('dossier.id'), nullable=False)
    photos = db.relationship('Photo', backref='taxatie', lazy=True)
    status_history = db.relationship('TaxatieStatusHistory', backref='taxatie', lazy=True, order_by='TaxatieStatusHistory.timestamp.desc()')
    
    def can_edit(self):
        """Check if the taxatie can be edited based on its status"""
        return self.status != 'definitief'
    
    def calculate_value(self, oppervlakte=None, hoogte=None, prijs_per_m2=None, prijs_per_m3=None):
        """Calculate the property value based on function and dimensions"""
        if not oppervlakte:
            return None
            
        # Determine calculation method based on property function
        if self.dossier.gebruiksdoel and 'woonfunctie' in self.dossier.gebruiksdoel.lower():
            # Residential property: use m³ calculation
            if not hoogte:
                hoogte = 2.6  # Default height for residential
            if not prijs_per_m3:
                return None
            volume = float(oppervlakte) * hoogte
            return volume * prijs_per_m3
        else:
            # Non-residential property: use m² calculation
            if not prijs_per_m2:
                return None
            return float(oppervlakte) * prijs_per_m2
    
    def change_status(self, new_status, user_id):
        """Change the status and log the change"""
        if new_status not in ['concept', 'definitief', 'gearchiveerd']:
            raise ValueError("Invalid status")
        
        old_status = self.status
        self.status = new_status
        
        # Log the status change
        status_log = TaxatieStatusHistory(
            taxatie_id=self.id,
            old_status=old_status,
            new_status=new_status,
            user_id=user_id
        )
        db.session.add(status_log)
        db.session.commit()

class TaxatieStatusHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    taxatie_id = db.Column(db.Integer, db.ForeignKey('taxatie.id'), nullable=False)
    old_status = db.Column(db.String(20), nullable=False)
    new_status = db.Column(db.String(20), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user = db.relationship('User', backref='status_changes')

class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(100), nullable=False)
    uploaded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    dossier_id = db.Column(db.Integer, db.ForeignKey('dossier.id'), nullable=False)

class Photo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    taxatie_id = db.Column(db.Integer, db.ForeignKey('taxatie.id'), nullable=False)

class UserLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action = db.Column(db.String(50), nullable=False)
    details = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=True)

class AllowedUser(db.Model):
    """Whitelist model for allowed users to register"""
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    full_name = db.Column(db.String(120), nullable=True)
    role = db.Column(db.String(20), nullable=False, default='user')
    added_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    added_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    is_registered = db.Column(db.Boolean, nullable=False, default=False)
    registered_at = db.Column(db.DateTime, nullable=True)
    registered_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    
    # Relationships
    added_by_user = db.relationship('User', foreign_keys=[added_by], backref='added_users')
    registered_user = db.relationship('User', foreign_keys=[registered_user_id], backref='whitelist_entry', uselist=False)

class WozData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # WOZ Object information
    wozobjectnummer = db.Column(db.String(50), nullable=False)
    woonplaatsnaam = db.Column(db.String(100), nullable=True)
    openbareruimtenaam = db.Column(db.String(200), nullable=True)
    openbareruimtetype = db.Column(db.String(50), nullable=True)
    straatnaam = db.Column(db.String(200), nullable=True)
    postcode = db.Column(db.String(10), nullable=True)
    huisnummer = db.Column(db.Integer, nullable=True)
    huisletter = db.Column(db.String(10), nullable=True)
    huisnummertoevoeging = db.Column(db.String(10), nullable=True)
    gemeentecode = db.Column(db.String(10), nullable=True)
    grondoppervlakte = db.Column(db.Integer, nullable=True)
    adresseerbaarobjectid = db.Column(db.String(50), nullable=True)
    nummeraanduidingid = db.Column(db.String(50), nullable=True)
    
    # Kadastrale objecten
    kadastrale_gemeente_code = db.Column(db.String(10), nullable=True)
    kadastrale_sectie = db.Column(db.String(10), nullable=True)
    kadastraal_perceel_nummer = db.Column(db.String(20), nullable=True)
    
    # Metadata
    last_updated = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    api_response_data = db.Column(db.Text, nullable=True)  # Store full JSON response
    
    # Relationships
    dossier_id = db.Column(db.Integer, db.ForeignKey('dossier.id'), nullable=True)
    # WOZ Values history (one-to-many relationship)
    woz_values = db.relationship('WozValue', backref='woz_data', lazy=True, cascade='all, delete-orphan')

class WozValue(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    woz_data_id = db.Column(db.Integer, db.ForeignKey('woz_data.id'), nullable=False)
    peildatum = db.Column(db.Date, nullable=False)
    vastgestelde_waarde = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

class BagData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # BAG Object information
    adresseerbaarobjectid = db.Column(db.String(50), nullable=True)
    nummeraanduidingid = db.Column(db.String(50), nullable=True)
    pand_id = db.Column(db.String(50), nullable=True)
    
    # Adresgegevens
    straatnaam = db.Column(db.String(200), nullable=True)
    huisnummer = db.Column(db.String(20), nullable=True)
    huisletter = db.Column(db.String(10), nullable=True)
    postcode = db.Column(db.String(10), nullable=True)
    woonplaats = db.Column(db.String(100), nullable=True)
    
    # Pandgegevens
    bouwjaar = db.Column(db.String(10), nullable=True)
    oppervlakte = db.Column(db.String(20), nullable=True)
    inhoud = db.Column(db.String(20), nullable=True)
    hoogte = db.Column(db.String(20), nullable=True)
    aantal_bouwlagen = db.Column(db.String(10), nullable=True)
    gebruiksdoel = db.Column(db.String(200), nullable=True)
    
    # Geodata fields
    centroide_ll = db.Column(db.String(100), nullable=True)  # Latitude,Longitude
    centroide_rd = db.Column(db.String(100), nullable=True)  # X,Y coordinates (Dutch RD)
    geometrie = db.Column(db.Text, nullable=True)  # Full geometry JSON
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    x_coord = db.Column(db.Float, nullable=True)  # Dutch RD X coordinate
    y_coord = db.Column(db.Float, nullable=True)  # Dutch RD Y coordinate
    google_maps_url = db.Column(db.String(500), nullable=True)  # Google Maps URL based on address
    
    # Metadata
    last_updated = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    api_response_data = db.Column(db.Text, nullable=True)  # Store full JSON response
    
    # Relationships
    dossier_id = db.Column(db.Integer, db.ForeignKey('dossier.id'), nullable=True)

class WalkScoreData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    
    # WalkScore information
    walkscore = db.Column(db.Integer, nullable=True)
    description = db.Column(db.String(500), nullable=True)
    logo_url = db.Column(db.String(500), nullable=True)
    more_info_icon = db.Column(db.String(500), nullable=True)
    more_info_link = db.Column(db.String(500), nullable=True)
    ws_link = db.Column(db.String(500), nullable=True)
    help_link = db.Column(db.String(500), nullable=True)
    
    # Location data
    snapped_lat = db.Column(db.Float, nullable=True)
    snapped_lon = db.Column(db.Float, nullable=True)
    
    # Transit score
    transit_score = db.Column(db.Integer, nullable=True)
    transit_description = db.Column(db.String(500), nullable=True)
    transit_summary = db.Column(db.String(500), nullable=True)
    
    # Bike score
    bike_score = db.Column(db.Integer, nullable=True)
    bike_description = db.Column(db.String(500), nullable=True)
    
    # Metadata
    last_updated = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    api_response_data = db.Column(db.Text, nullable=True)  # Store full JSON response
    
    # Relationships
    dossier_id = db.Column(db.Integer, db.ForeignKey('dossier.id'), nullable=True)

class PDOKData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    
    # Address and identification
    bag_id = db.Column(db.String(50), nullable=True)
    search_successful = db.Column(db.Boolean, nullable=True)
    address = db.Column(db.String(200), nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    
    # Basic property information
    status = db.Column(db.String(50), nullable=True)
    bouwjaar = db.Column(db.String(10), nullable=True)
    oppervlakte = db.Column(db.String(20), nullable=True)
    property_type = db.Column(db.String(100), nullable=True)
    
    # 3D Data
    building_height = db.Column(db.Float, nullable=True)
    roof_height = db.Column(db.Float, nullable=True)
    ground_height = db.Column(db.Float, nullable=True)
    building_volume = db.Column(db.Float, nullable=True)
    roof_type = db.Column(db.String(100), nullable=True)
    model_3d_available = db.Column(db.Boolean, nullable=True)
    
    # Kadastrale Data
    perceel_id = db.Column(db.String(50), nullable=True)
    kadastrale_gemeente = db.Column(db.String(100), nullable=True)
    sectie = db.Column(db.String(10), nullable=True)
    perceelnummer = db.Column(db.String(20), nullable=True)
    perceel_oppervlakte = db.Column(db.Float, nullable=True)
    eigenaar_type = db.Column(db.String(100), nullable=True)
    perceel_gebruik = db.Column(db.String(100), nullable=True)
    
    # Topographic Context
    surrounding_buildings = db.Column(db.Integer, nullable=True)
    land_use = db.Column(db.Text, nullable=True)  # JSON array
    infrastructure = db.Column(db.Text, nullable=True)  # JSON array
    water_features = db.Column(db.Text, nullable=True)  # JSON array
    
    # Data quality indicators
    has_basic_info = db.Column(db.Boolean, nullable=True)
    has_3d_data = db.Column(db.Boolean, nullable=True)
    has_kadastrale_data = db.Column(db.Boolean, nullable=True)
    has_topographic_data = db.Column(db.Boolean, nullable=True)
    data_sources = db.Column(db.Text, nullable=True)  # JSON array
    
    # Property type categorization
    property_type_category = db.Column(db.String(50), nullable=True)
    taxatie_relevance_score = db.Column(db.Integer, nullable=True)
    
    # Metadata
    last_updated = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    api_response_data = db.Column(db.Text, nullable=True)  # Store full JSON response
    
    # Relationships
    dossier_id = db.Column(db.Integer, db.ForeignKey('dossier.id'), nullable=True)

def get_setting(key, default=None):
    setting = Setting.query.filter_by(key=key).first()
    return setting.value if setting else default

def set_setting(key, value):
    setting = Setting.query.filter_by(key=key).first()
    if setting:
        setting.value = value
    else:
        setting = Setting(key=key, value=value)
        db.session.add(setting)
    db.session.commit()

def is_app_configured():
    """Check if the app has been configured (setup wizard completed)"""
    return get_setting('APP_CONFIGURED', 'false') == 'true'

def complete_app_setup():
    """Mark the app as configured"""
    set_setting('APP_CONFIGURED', 'true')

def lookup_and_save_woz_data(address, dossier_id):
    """Helper function to lookup and save WOZ data for a dossier"""
    try:
        # Check if WOZ data already exists for this dossier
        existing_woz = WozData.query.filter_by(dossier_id=dossier_id).first()
        
        woz_service = WozService()
        woz_response = woz_service.lookup_woz_data(address)
        
        if woz_response:
            parsed_data = woz_service.parse_woz_data(woz_response)
            
            if existing_woz:
                # Update existing WOZ data
                woz_data = existing_woz
            else:
                # Create new WOZ data
                woz_data = WozData(dossier_id=dossier_id)
            
            # Update WOZ data fields
            woz_data.wozobjectnummer = parsed_data['woz_data']['wozobjectnummer']
            woz_data.woonplaatsnaam = parsed_data['woz_data']['woonplaatsnaam']
            woz_data.openbareruimtenaam = parsed_data['woz_data']['openbareruimtenaam']
            woz_data.openbareruimtetype = parsed_data['woz_data']['openbareruimtetype']
            woz_data.straatnaam = parsed_data['woz_data']['straatnaam']
            woz_data.postcode = parsed_data['woz_data']['postcode']
            woz_data.huisnummer = safe_int(parsed_data['woz_data']['huisnummer'])
            woz_data.huisletter = parsed_data['woz_data']['huisletter']
            woz_data.huisnummertoevoeging = parsed_data['woz_data']['huisnummertoevoeging']
            woz_data.gemeentecode = parsed_data['woz_data']['gemeentecode']
            woz_data.grondoppervlakte = safe_int(parsed_data['woz_data']['grondoppervlakte'])
            woz_data.adresseerbaarobjectid = parsed_data['woz_data']['adresseerbaarobjectid']
            woz_data.nummeraanduidingid = parsed_data['woz_data']['nummeraanduidingid']
            woz_data.kadastrale_gemeente_code = parsed_data['woz_data']['kadastrale_gemeente_code']
            woz_data.kadastrale_sectie = parsed_data['woz_data']['kadastrale_sectie']
            woz_data.kadastraal_perceel_nummer = parsed_data['woz_data']['kadastraal_perceel_nummer']
            woz_data.api_response_data = json.dumps(woz_response)
            woz_data.last_updated = datetime.utcnow()
            
            if not existing_woz:
                db.session.add(woz_data)
            db.session.flush()  # Zorg dat woz_data.id beschikbaar is
            
            # Clear existing WOZ values and add new ones
            if existing_woz:
                WozValue.query.filter_by(woz_data_id=existing_woz.id).delete()
            
            # Add WOZ values
            for value_data in parsed_data['woz_values']:
                woz_value = WozValue(
                    woz_data_id=woz_data.id,
                    peildatum=datetime.strptime(value_data['peildatum'], '%Y-%m-%d').date(),
                    vastgestelde_waarde=value_data['vastgestelde_waarde']
                )
                db.session.add(woz_value)
            
            db.session.commit()
            return True
        else:
            return False
            
    except Exception as e:
        db.session.rollback()
        print(f"Fout bij WOZ lookup en opslag: {str(e)}", flush=True)
        return False

def lookup_and_save_walkscore_data(postcode, huisnummer, huisletter, dossier_id):
    """Helper function to lookup and save WalkScore data for a dossier"""
    try:
        api_url = get_setting('WALKSCORE_API_URL')
        api_key = get_setting('WALKSCORE_API_KEY')
        if not api_url or not api_key:
            return False
        
        walkscore_service = WalkScoreService(api_url, api_key)
        
        # Get coordinates from BAG data or PDOK data
        lat = None
        lon = None
        straat = None
        woonplaats = None
        
        # First try to get coordinates from BAG data
        bag_data = BagData.query.filter_by(dossier_id=dossier_id).first()
        if bag_data and bag_data.latitude and bag_data.longitude:
            lat = bag_data.latitude
            lon = bag_data.longitude
            straat = bag_data.straatnaam
            woonplaats = bag_data.woonplaats
        else:
            # Try to get coordinates from PDOK data
            pdok_data = PDOKData.query.filter_by(dossier_id=dossier_id).first()
            if pdok_data and pdok_data.latitude and pdok_data.longitude:
                lat = pdok_data.latitude
                lon = pdok_data.longitude
        
        if not lat or not lon:
            return False
        
        result, status = walkscore_service.lookup_walkscore(
            straat=straat,
            huisnummer=huisnummer, 
            huisletter=huisletter,
            postcode=postcode,
            woonplaats=woonplaats,
            lat=lat, 
            lon=lon
        )
        
        if status == 200 and result.get('success'):
            # Check if WalkScore data already exists for this dossier
            existing_walkscore = WalkScoreData.query.filter_by(dossier_id=dossier_id).first()
            
            if existing_walkscore:
                # Update existing WalkScore data
                walkscore_data = existing_walkscore
            else:
                # Create new WalkScore data
                walkscore_data = WalkScoreData(dossier_id=dossier_id)
            
            # Update WalkScore data fields
            data = result['data']
            walkscore_data.walkscore = data.get('walkscore')
            walkscore_data.description = data.get('description')
            walkscore_data.logo_url = data.get('logo_url')
            walkscore_data.more_info_icon = data.get('more_info_icon')
            walkscore_data.more_info_link = data.get('more_info_link')
            walkscore_data.ws_link = data.get('ws_link')
            walkscore_data.help_link = data.get('help_link')
            walkscore_data.snapped_lat = data.get('snapped_lat')
            walkscore_data.snapped_lon = data.get('snapped_lon')
            
            # Update transit data
            if 'transit' in data and data['transit']:
                transit = data['transit']
                walkscore_data.transit_score = transit.get('score')
                walkscore_data.transit_description = transit.get('description')
                walkscore_data.transit_summary = transit.get('summary')
            
            # Update bike data
            if 'bike' in data and data['bike']:
                bike = data['bike']
                walkscore_data.bike_score = bike.get('score')
                walkscore_data.bike_description = bike.get('description')
            
            walkscore_data.api_response_data = json.dumps(result.get('raw_response', {}))
            walkscore_data.last_updated = datetime.utcnow()
            
            if not existing_walkscore:
                db.session.add(walkscore_data)
            
            db.session.commit()
            return True
        else:
            return False
            
    except Exception as e:
        db.session.rollback()
        print(f"Fout bij WalkScore lookup en opslag: {str(e)}", flush=True)
        return False

def lookup_and_save_pdok_data(postcode, huisnummer, huisletter, dossier_id):
    """Helper function to lookup and save PDOK data for a dossier"""
    try:
        # Get address information from dossier
        dossier = Dossier.query.get(dossier_id)
        if not dossier:
            return False

        # Use hardcoded PDOK API URL (open data, no key required)
        pdok_api_url = 'https://geodata.nationaalgeoregister.nl/locatieserver/v3/'
        
        # Initialize PDOK service (no API key needed for open data)
        pdok_service = PDOKService(pdok_api_url)
        
        # Lookup PDOK data
        response_data, status_code = pdok_service.lookup_pdok_data(
            postcode, 
            huisnummer, 
            huisletter
        )
        
        if status_code != 200:
            return False
        
        # Extract data for database storage
        pdok_data_dict = response_data.get('data', {})
        address_info = pdok_data_dict.get('address_info', {})
        property_data = pdok_data_dict.get('property_data', {})
        data_quality = pdok_data_dict.get('data_quality', {})
        
        # Calculate property type and relevance score
        property_type_category = pdok_service.get_property_type_category(
            property_data.get('basic_info', {}).get('property_type', '')
        )
        taxatie_relevance_score = pdok_service.get_taxatie_relevance_score(property_data)
        
        # Save to database
        existing_data = PDOKData.query.filter_by(dossier_id=dossier_id).first()
        if existing_data:
            # Update existing record
            existing_data.bag_id = address_info.get('bag_id')
            existing_data.search_successful = address_info.get('search_successful')
            existing_data.address = address_info.get('address')
            
            # Coordinates
            coordinates = address_info.get('coordinates', {})
            existing_data.latitude = coordinates.get('latitude')
            existing_data.longitude = coordinates.get('longitude')
            
            # Basic property information
            basic_info = property_data.get('basic_info', {})
            existing_data.status = basic_info.get('status')
            existing_data.bouwjaar = basic_info.get('bouwjaar')
            existing_data.oppervlakte = basic_info.get('oppervlakte')
            existing_data.property_type = basic_info.get('property_type')
            
            # 3D Data
            three_d_data = property_data.get('3d_data', {})
            existing_data.building_height = three_d_data.get('height')
            existing_data.roof_height = three_d_data.get('roof_height')
            existing_data.ground_height = three_d_data.get('ground_height')
            existing_data.building_volume = three_d_data.get('building_volume')
            existing_data.roof_type = three_d_data.get('roof_type')
            existing_data.model_3d_available = three_d_data.get('3d_model_available')
            
            # Kadastrale Data
            kadastrale_data = property_data.get('kadastrale_data', {})
            existing_data.perceel_id = kadastrale_data.get('perceel_id')
            existing_data.kadastrale_gemeente = kadastrale_data.get('kadastrale_gemeente')
            existing_data.sectie = kadastrale_data.get('sectie')
            existing_data.perceelnummer = kadastrale_data.get('perceelnummer')
            existing_data.perceel_oppervlakte = kadastrale_data.get('oppervlakte')
            existing_data.eigenaar_type = kadastrale_data.get('eigenaar_type')
            existing_data.perceel_gebruik = kadastrale_data.get('gebruik')
            
            # Topographic Context
            topographic_context = property_data.get('topographic_context', {})
            existing_data.surrounding_buildings = topographic_context.get('surrounding_buildings')
            existing_data.land_use = json.dumps(topographic_context.get('land_use', []))
            existing_data.infrastructure = json.dumps(topographic_context.get('infrastructure', []))
            existing_data.water_features = json.dumps(topographic_context.get('water_features', []))
            
            # Data quality indicators
            existing_data.has_basic_info = data_quality.get('has_basic_info')
            existing_data.has_3d_data = data_quality.get('has_3d_data')
            existing_data.has_kadastrale_data = data_quality.get('has_kadastrale_data')
            existing_data.has_topographic_data = data_quality.get('has_topographic_data')
            existing_data.data_sources = json.dumps(data_quality.get('data_sources', []))
            
            # Property categorization
            existing_data.property_type_category = property_type_category
            existing_data.taxatie_relevance_score = taxatie_relevance_score
            
            # Store raw API response for debugging
            existing_data.api_response_data = json.dumps(response_data)
            existing_data.last_updated = datetime.utcnow()
            
            db.session.commit()
            
        else:
            # Create new record
            new_data = PDOKData(
                dossier_id=dossier_id,
                bag_id=address_info.get('bag_id'),
                search_successful=address_info.get('search_successful'),
                address=address_info.get('address'),
                latitude=address_info.get('coordinates', {}).get('latitude'),
                longitude=address_info.get('coordinates', {}).get('longitude'),
                
                # Basic property information
                status=property_data.get('basic_info', {}).get('status'),
                bouwjaar=property_data.get('basic_info', {}).get('bouwjaar'),
                oppervlakte=property_data.get('basic_info', {}).get('oppervlakte'),
                property_type=property_data.get('basic_info', {}).get('property_type'),
                
                # 3D Data
                building_height=property_data.get('3d_data', {}).get('height'),
                roof_height=property_data.get('3d_data', {}).get('roof_height'),
                ground_height=property_data.get('3d_data', {}).get('ground_height'),
                building_volume=property_data.get('3d_data', {}).get('building_volume'),
                roof_type=property_data.get('3d_data', {}).get('roof_type'),
                model_3d_available=property_data.get('3d_data', {}).get('3d_model_available'),
                
                # Kadastrale Data
                perceel_id=property_data.get('kadastrale_data', {}).get('perceel_id'),
                kadastrale_gemeente=property_data.get('kadastrale_data', {}).get('kadastrale_gemeente'),
                sectie=property_data.get('kadastrale_data', {}).get('sectie'),
                perceelnummer=property_data.get('kadastrale_data', {}).get('perceelnummer'),
                perceel_oppervlakte=property_data.get('kadastrale_data', {}).get('oppervlakte'),
                eigenaar_type=property_data.get('kadastrale_data', {}).get('eigenaar_type'),
                perceel_gebruik=property_data.get('kadastrale_data', {}).get('gebruik'),
                
                # Topographic Context
                surrounding_buildings=property_data.get('topographic_context', {}).get('surrounding_buildings'),
                land_use=json.dumps(property_data.get('topographic_context', {}).get('land_use', [])),
                infrastructure=json.dumps(property_data.get('topographic_context', {}).get('infrastructure', [])),
                water_features=json.dumps(property_data.get('topographic_context', {}).get('water_features', [])),
                
                # Data quality indicators
                has_basic_info=data_quality.get('has_basic_info'),
                has_3d_data=data_quality.get('has_3d_data'),
                has_kadastrale_data=data_quality.get('has_kadastrale_data'),
                has_topographic_data=data_quality.get('has_topographic_data'),
                data_sources=json.dumps(data_quality.get('data_sources', [])),
                
                # Property categorization
                property_type_category=property_type_category,
                taxatie_relevance_score=taxatie_relevance_score,
                
                # Store raw API response for debugging
                api_response_data=json.dumps(response_data),
                last_updated=datetime.utcnow()
            )
            
            db.session.add(new_data)
            db.session.commit()
        
        print(f"PDOK data succesvol opgeslagen voor dossier {dossier_id}", flush=True)
        return True
        
    except Exception as e:
        db.session.rollback()
        print(f"Fout bij PDOK lookup en opslag: {str(e)}", flush=True)
        return False

def create_app(config_name='development'):
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object(config[config_name])
    
    # Force local storage for development
    if config_name == 'development':
        app.config['STORAGE_TYPE'] = 'local'
        app.config['UPLOAD_FOLDER'] = 'uploads'
    
    # Configure logging to suppress health check requests
    logging.basicConfig(level=logging.INFO)
    werkzeug_logger = logging.getLogger('werkzeug')
    health_filter = HealthCheckFilter()
    werkzeug_logger.addFilter(health_filter)
    
    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    storage.init_app(app)
    
    # Set up login manager
    login_manager.login_view = 'login'
    login_manager.login_message = 'Je moet ingelogd zijn om deze pagina te bekijken.'
    login_manager.login_message_category = 'info'
    
    # Register blueprints and routes
    with app.app_context():
        # Initialize database with retry mechanism
        max_db_retries = 10
        db_retry_delay = 2
        
        for db_attempt in range(max_db_retries):
            try:
                print(f"Attempting database initialization (attempt {db_attempt + 1}/{max_db_retries})")
                
                # Test database connection first
                db.session.execute('SELECT 1')
                print("Database connection successful")
                
                # Initialize database
                db.create_all()
                print("Database tables created successfully")
                
                # Initialize storage
                storage.ensure_container_exists()
                
                # Zet default API urls in de database als ze nog niet bestaan
                if get_setting('BAG_API_URL') is None:
                    set_setting('BAG_API_URL', 'https://api.bag.kadaster.nl/lvbag/individuelebevragingen/v2')
                if get_setting('BAG_PDOK_API_URL') is None:
                    set_setting('BAG_PDOK_API_URL', 'https://data.pdok.nl/bag/api/v1/')
                if get_setting('STREETSMART_API_URL') is None:
                    set_setting('STREETSMART_API_URL', 'https://developer.cyclomedia.com/our-apis/street-smart/')
                if get_setting('WALKSCORE_API_URL') is None:
                    set_setting('WALKSCORE_API_URL', 'https://api.walkscore.com/score')
                
                print("Database initialization completed successfully")
                break
                
            except Exception as e:
                print(f"Database initialization failed on attempt {db_attempt + 1}: {e}")
                if db_attempt < max_db_retries - 1:
                    print(f"Retrying database initialization in {db_retry_delay} seconds...")
                    time.sleep(db_retry_delay)
                    db_retry_delay *= 1.5  # Gradual backoff
                else:
                    print("Max database retries reached. App will start but database operations may fail.")
                    # Don't fail the app startup, just log the error
                    # The app can still start and handle requests
    
    return app

# Initialize app with retry mechanism
def initialize_app_with_retry():
    max_retries = 5
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            app = create_app(os.getenv('FLASK_ENV', 'development'))
            print(f"App initialized successfully on attempt {attempt + 1}")
            return app
        except Exception as e:
            print(f"App initialization failed on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                print(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                print("Max retries reached. Starting app anyway...")
                return create_app(os.getenv('FLASK_ENV', 'development'))

app = initialize_app_with_retry()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def allowed_file(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

@app.before_request
def check_setup():
    """Redirect to setup wizard if app is not configured"""
    # Skip setup check for setup routes and static files
    if request.endpoint in ['setup_wizard', 'complete_setup', 'static'] or request.path.startswith('/static/'):
        return
    
    # Check if app is configured
    if not is_app_configured():
        return redirect(url_for('setup_wizard'))

# Routes
@app.route('/setup', methods=['GET', 'POST'])
def setup_wizard():
    """Setup wizard for initial app configuration"""
    # If app is already configured, redirect to main page
    if is_app_configured():
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        try:
            # Create admin user
            admin_username = request.form.get('admin_username')
            admin_email = request.form.get('admin_email')
            admin_password = request.form.get('admin_password')
            admin_full_name = request.form.get('admin_full_name')
            
            # Validate required fields
            if not admin_username or not admin_password or not admin_email:
                flash('Alle velden voor de admin gebruiker zijn verplicht', 'error')
                return render_template('setup_wizard.html')
            
            # Check if username/email already exists
            if User.query.filter_by(username=admin_username).first():
                flash('Gebruikersnaam bestaat al', 'error')
                return render_template('setup_wizard.html')
            
            if User.query.filter_by(email=admin_email).first():
                flash('Email adres bestaat al', 'error')
                return render_template('setup_wizard.html')
            
            # Create admin user
            admin_user = User(
                username=admin_username,
                email=admin_email,
                full_name=admin_full_name or admin_username,
                role='admin',
                auth_type='local'
            )
            admin_user.set_password(admin_password)
            db.session.add(admin_user)
            
            # Configure Google OAuth (optional)
            google_client_id = request.form.get('google_client_id', '').strip()
            google_client_secret = request.form.get('google_client_secret', '').strip()
            
            if google_client_id and google_client_secret:
                set_setting('GOOGLE_CLIENT_ID', google_client_id)
                set_setting('GOOGLE_CLIENT_SECRET', google_client_secret)
                flash('Google OAuth geconfigureerd', 'success')
            
            # Mark app as configured
            complete_app_setup()
            
            db.session.commit()
            
            flash('Setup voltooid! Je kunt nu inloggen met je admin account.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Fout tijdens setup: {str(e)}', 'error')
            return render_template('setup_wizard.html')
    
    return render_template('setup_wizard.html')

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dossiers'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('dossiers'))
        flash('Ongeldige gebruikersnaam of wachtwoord', 'error')
    
    # Check if Google OAuth is enabled
    google_oauth_enabled = bool(get_setting('GOOGLE_CLIENT_ID'))
    
    return render_template('login.html', google_oauth_enabled=google_oauth_enabled)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        email = request.form.get('email')
        
        # Basic validation
        if not username or not password:
            flash('Gebruikersnaam en wachtwoord zijn verplicht', 'error')
            return redirect(url_for('register'))
        
        if User.query.filter_by(username=username).first():
            flash('Gebruikersnaam bestaat al', 'error')
            return redirect(url_for('register'))
        
        if email and User.query.filter_by(email=email).first():
            flash('Email adres bestaat al', 'error')
            return redirect(url_for('register'))
        
        user = User(username=username, email=email, auth_type='local')
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        login_user(user)
        flash('Account succesvol aangemaakt', 'success')
        return redirect(url_for('dossiers'))
    
    # Check if Google OAuth is enabled
    google_oauth_enabled = bool(get_setting('GOOGLE_CLIENT_ID'))
    
    return render_template('register.html', google_oauth_enabled=google_oauth_enabled)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/auth/google')
def google_auth():
    """Redirect to Google OAuth"""
    google_client_id = get_setting('GOOGLE_CLIENT_ID')
    if not google_client_id:
        flash('Google OAuth is niet geconfigureerd. Neem contact op met een administrator.', 'error')
        return redirect(url_for('login'))
    
    # Generate state for security
    state = secrets.token_urlsafe(32)
    session['oauth_state'] = state
    
    # Google OAuth URL
    google_oauth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={google_client_id}"
        f"&redirect_uri={url_for('google_callback', _external=True)}"
        f"&scope=openid email profile"
        f"&response_type=code"
        f"&state={state}"
    )
    
    return redirect(google_oauth_url)

@app.route('/auth/google/callback')
def google_callback():
    """Handle Google OAuth callback"""
    try:
        # Verify state
        if request.args.get('state') != session.get('oauth_state'):
            flash('Invalid state parameter', 'error')
            return redirect(url_for('login'))
        
        # Get authorization code
        code = request.args.get('code')
        if not code:
            flash('Authorization code not received', 'error')
            return redirect(url_for('login'))
        
        # Exchange code for token
        google_client_id = get_setting('GOOGLE_CLIENT_ID')
        google_client_secret = get_setting('GOOGLE_CLIENT_SECRET')
        
        token_data = {
            'code': code,
            'client_id': google_client_id,
            'client_secret': google_client_secret,
            'redirect_uri': url_for('google_callback', _external=True),
            'grant_type': 'authorization_code'
        }
        
        token_response = requests.post('https://oauth2.googleapis.com/token', data=token_data)
        token_json = token_response.json()
        
        if 'access_token' not in token_json:
            flash('Failed to get access token', 'error')
            return redirect(url_for('login'))
        
        # Get user info
        user_response = requests.get(
            'https://www.googleapis.com/oauth2/v2/userinfo',
            headers={'Authorization': f'Bearer {token_json["access_token"]}'}
        )
        user_data = user_response.json()
        
        # Check if user is allowed to register (only if whitelist is enabled)
        allowed_users_exist = AllowedUser.query.count() > 0
        if allowed_users_exist:
            allowed_user = AllowedUser.query.filter_by(email=user_data['email']).first()
            if not allowed_user:
                flash('Je email adres is niet geautoriseerd voor toegang tot dit systeem. Neem contact op met een administrator.', 'error')
                return redirect(url_for('login'))
        else:
            # No whitelist configured, allow anyone to register
            allowed_user = None
        
        # Check if user already exists
        user = User.query.filter_by(google_id=user_data['id']).first()
        if not user:
            user = User.query.filter_by(email=user_data['email']).first()
        
        if user:
            # Update existing user with Google info
            user.google_id = user_data['id']
            user.google_email = user_data['email']
            user.google_profile_picture = user_data.get('picture')
            user.auth_type = 'google'
            if not user.email:
                user.email = user_data['email']
            if not user.full_name:
                user.full_name = user_data.get('name', '')
        else:
            # Create new user
            username = user_data['email'].split('@')[0]
            # Make sure username is unique
            counter = 1
            original_username = username
            while User.query.filter_by(username=username).first():
                username = f"{original_username}{counter}"
                counter += 1
            
            user = User(
                username=username,
                email=user_data['email'],
                full_name=user_data.get('name', ''),
                google_id=user_data['id'],
                google_email=user_data['email'],
                google_profile_picture=user_data.get('picture'),
                auth_type='google',
                role=allowed_user.role if allowed_user else 'user'
            )
            db.session.add(user)
            
            # Mark as registered in whitelist if it exists
            if allowed_user:
                allowed_user.is_registered = True
                allowed_user.registered_at = datetime.utcnow()
                allowed_user.registered_user_id = user.id
        
        db.session.commit()
        login_user(user)
        
        # Clear state
        session.pop('oauth_state', None)
        
        flash('Successfully logged in with Google', 'success')
        return redirect(url_for('dossiers'))
        
    except Exception as e:
        flash(f'Error during Google authentication: {str(e)}', 'error')
        return redirect(url_for('login'))

@app.route('/dossiers')
@login_required
def dossiers():
    user_dossiers = Dossier.query.filter_by(user_id=current_user.id).all()
    return render_template('dossiers.html', dossiers=user_dossiers)

@app.route('/dossier/nieuw', methods=['GET', 'POST'])
@login_required
def nieuw_dossier():
    if request.method == 'POST':
        # Check for duplicate before creating
        postcode = request.form.get('postcode')
        huisnummer = request.form.get('huisnummer')
        huisletter = request.form.get('huisletter')
        
        # Check for duplicate
        duplicate = check_duplicate_dossier(postcode, huisnummer, huisletter)
        if duplicate:
            flash(f'Er bestaat al een dossier voor dit adres: {duplicate.naam} ({duplicate.adres})', 'warning')
            return redirect(url_for('dossier_detail', dossier_id=duplicate.id))
        
        dossier = Dossier(
            naam=request.form.get('naam'),
            adres=request.form.get('adres'),
            postcode=request.form.get('postcode'),
            plaats=request.form.get('plaats'),
            bouwjaar=request.form.get('bouwjaar'),
            oppervlakte=request.form.get('oppervlakte'),
            inhoud=request.form.get('inhoud'),
            hoogte=request.form.get('hoogte'),
            aantal_bouwlagen=request.form.get('aantal_bouwlagen'),
            gebruiksdoel=request.form.get('gebruiksdoel'),
            user_id=current_user.id
        )
        db.session.add(dossier)
        db.session.commit()
        
        # Haal BAG data op na het aanmaken van het dossier
        try:
            from bag_service import BagService
            import json
            
            api_url = get_setting('BAG_API_URL')
            api_key = get_setting('BAG_API_KEY')
            
            if api_url and api_key:
                bag_service = BagService(api_url, api_key)
                postcode = request.form.get('postcode', '').replace(' ', '').upper()
                huisnummer = request.form.get('huisnummer', '')
                huisletter = request.form.get('huisletter', '')
                
                result, status = bag_service.lookup_address(postcode, huisnummer, huisletter)
                
                if status == 200:
                    # Maak BAG data record aan
                    bag_data = BagData(dossier_id=dossier.id)
                    
                    # Update BAG data fields
                    if 'adres' in result:
                        adres_data = result['adres']
                        bag_data.straatnaam = adres_data.get('straat', '')
                        bag_data.huisnummer = adres_data.get('huisnummer', '')
                        bag_data.huisletter = adres_data.get('huisletter', '')
                        bag_data.postcode = adres_data.get('postcode', '')
                        bag_data.woonplaats = adres_data.get('woonplaats', '')
                    
                    bag_data.bouwjaar = str(result['bouwjaar']) if result.get('bouwjaar') else None
                    bag_data.oppervlakte = str(result['oppervlakte']) if result.get('oppervlakte') else None
                    bag_data.inhoud = str(result['inhoud']) if result.get('inhoud') else None
                    bag_data.hoogte = str(result['hoogte']) if result.get('hoogte') else None
                    bag_data.aantal_bouwlagen = str(result['aantal_bouwlagen']) if result.get('aantal_bouwlagen') else None
                    
                    # Process gebruiksdoel
                    if 'gebruiksdoel' in result:
                        if isinstance(result['gebruiksdoel'], list):
                            gebruiksdoelen = result['gebruiksdoel']
                            if not gebruiksdoelen:
                                bag_data.gebruiksdoel = None
                            else:
                                bag_data.gebruiksdoel = ', '.join(gebruiksdoelen)
                        else:
                            bag_data.gebruiksdoel = str(result['gebruiksdoel']) if result['gebruiksdoel'] else None
                    
                    # Store geodata if available
                    if 'geodata' in result:
                        geodata = result['geodata']
                        bag_data.centroide_ll = geodata.get('centroide_ll')
                        bag_data.centroide_rd = geodata.get('centroide_rd')
                        bag_data.geometrie = json.dumps(geodata.get('geometrie')) if geodata.get('geometrie') else None
                        bag_data.latitude = geodata.get('latitude')
                        bag_data.longitude = geodata.get('longitude')
                        bag_data.x_coord = geodata.get('x_coord')
                        bag_data.y_coord = geodata.get('y_coord')
                        bag_data.google_maps_url = geodata.get('google_maps_url')
                    
                    # Store the full API response
                    bag_data.api_response_data = json.dumps(result)
                    bag_data.last_updated = datetime.utcnow()
                    
                    db.session.add(bag_data)
                    db.session.commit()
                    
                    flash('Dossier succesvol aangemaakt met BAG data', 'success')
                else:
                    flash('Dossier succesvol aangemaakt (BAG data kon niet worden opgehaald)', 'warning')
            else:
                flash('Dossier succesvol aangemaakt (BAG API niet geconfigureerd)', 'warning')
        except Exception as e:
            print(f"BAG data ophalen bij dossier aanmaken mislukt: {e}", flush=True)
            flash('Dossier succesvol aangemaakt (BAG data kon niet worden opgehaald)', 'warning')
        
        return redirect(url_for('dossiers'))
    return render_template('nieuw_dossier.html')

@app.route('/dossier/<int:dossier_id>')
@login_required
def dossier_detail(dossier_id):
    dossier = Dossier.query.get_or_404(dossier_id)
    if dossier.user_id != current_user.id:
        return redirect(url_for('dossiers'))
    # Haal eerste bag_data record op
    bag = dossier.bag_data[0] if dossier.bag_data else None
    bag_terugmeldingen = []
    if bag and bag.adresseerbaarobjectid:
        meldingen = get_bag_terugmeldingen(bag.adresseerbaarobjectid)
        if meldingen is not None:
            bag_terugmeldingen = meldingen

    # Initieel WOZ-data ophalen als nodig (en van toepassing)
    woz = dossier.woz_data[0] if dossier.woz_data else None
    if not woz and bag and bag.straatnaam and bag.huisnummer and 'woonfunctie' in (bag.gebruiksdoel or '').lower():
        try:
            address = f"{bag.straatnaam} {bag.huisnummer}{bag.huisletter or ''}, {bag.postcode} {bag.woonplaats}"
            lookup_and_save_woz_data(address, dossier.id)
            # Herlaad woz_data
            dossier = Dossier.query.get_or_404(dossier_id)
        except Exception as e:
            print(f"WOZ initieel ophalen mislukt: {e}", flush=True)
    
    # Initieel WalkScore ophalen als nodig
    walkscore = dossier.walkscore_data[0] if dossier.walkscore_data else None
    if not walkscore and bag and bag.latitude and bag.longitude:
        try:
            lookup_and_save_walkscore_data(bag.postcode, bag.huisnummer, bag.huisletter, dossier.id)
            dossier = Dossier.query.get_or_404(dossier_id)
        except Exception as e:
            print(f"WalkScore initieel ophalen mislukt: {e}", flush=True)

    # PDOK data wordt nu asynchroon geladen via JavaScript voor betere performance
    # Geen automatische refresh hier meer - dit gebeurt nu in de frontend

    # Convert bag object to dictionary for template
    bag_dict = None
    if bag:
        print(f"DEBUG BAG DB: x_coord={bag.x_coord}, y_coord={bag.y_coord}, lat={bag.latitude}, lng={bag.longitude}", flush=True)
        bag_dict = {
            'latitude': bag.latitude,
            'longitude': bag.longitude,
            'x_coord': bag.x_coord,
            'y_coord': bag.y_coord,
            'postcode': bag.postcode,
            'huisnummer': bag.huisnummer,
            'huisletter': bag.huisletter,
            'straatnaam': bag.straatnaam,
            'woonplaats': bag.woonplaats
        }

    # Also get PDOK data for more accurate coordinates
    pdok_dict = None
    pdok = dossier.pdok_data[0] if dossier.pdok_data else None
    if pdok:
        print(f"DEBUG PDOK DB: lat={pdok.latitude}, lng={pdok.longitude}", flush=True)
        pdok_dict = {
            'latitude': pdok.latitude,
            'longitude': pdok.longitude,
            'x_coord': None,  # PDOK model doesn't have RD coordinates
            'y_coord': None,  # PDOK model doesn't have RD coordinates
            'postcode': None,  # PDOK model doesn't store address components
            'huisnummer': None,
            'huisletter': None,
            'straatnaam': None,
            'woonplaats': None,
            'address': pdok.address  # Use the full address field instead
        }

    return render_template('dossier_detail.html', dossier=dossier, bag=bag_dict, pdok=pdok_dict, bag_terugmeldingen=bag_terugmeldingen)

@app.route('/dossier/<int:dossier_id>/taxatie/nieuw', methods=['GET', 'POST'])
@login_required
def nieuwe_taxatie(dossier_id):
    dossier = Dossier.query.get_or_404(dossier_id)
    if dossier.user_id != current_user.id:
        return redirect(url_for('dossiers'))
    
    if request.method == 'POST':
        # Get calculation fields
        hoogte_meters = request.form.get('hoogte_meters')
        prijs_per_m2 = request.form.get('prijs_per_m2')
        prijs_per_m3 = request.form.get('prijs_per_m3')
        berekening_methode = request.form.get('berekening_methode')
        
        taxatie = Taxatie(
            datum=datetime.strptime(request.form.get('datum'), '%Y-%m-%d').date(),
            taxateur=request.form.get('taxateur'),
            waarde=float(request.form.get('waarde')),
            opmerkingen=request.form.get('opmerkingen'),
            hoogte_meters=float(hoogte_meters) if hoogte_meters else None,
            prijs_per_m2=float(prijs_per_m2) if prijs_per_m2 else None,
            prijs_per_m3=float(prijs_per_m3) if prijs_per_m3 else None,
            berekening_methode=berekening_methode,
            dossier_id=dossier_id
        )
        db.session.add(taxatie)
        db.session.commit()
        
        # Handle photo uploads
        if 'photos' in request.files:
            photos = request.files.getlist('photos')
            for photo in photos:
                if photo and allowed_file(photo.filename, app.config['ALLOWED_EXTENSIONS']['images']):
                    filename = storage.upload_file(photo, folder=f'taxaties/{taxatie.id}')
                    photo_record = Photo(
                        filename=filename,
                        original_filename=photo.filename,
                        taxatie_id=taxatie.id
                    )
                    db.session.add(photo_record)
        
        db.session.commit()
        
        flash('Taxatie succesvol aangemaakt', 'success')
        return redirect(url_for('dossier_detail', dossier_id=dossier_id))
    
    return render_template('nieuwe_taxatie.html', dossier=dossier)

@app.route('/dossier/<int:dossier_id>/taxatie/<int:taxatie_id>/bewerken', methods=['GET', 'POST'])
@login_required
def bewerk_taxatie(dossier_id, taxatie_id):
    dossier = Dossier.query.get_or_404(dossier_id)
    if dossier.user_id != current_user.id:
        return redirect(url_for('dossiers'))
    
    taxatie = Taxatie.query.get_or_404(taxatie_id)
    if taxatie.dossier_id != dossier_id:
        return redirect(url_for('dossiers'))
    
    if request.method == 'POST':
        # Check if taxatie can be edited
        if not taxatie.can_edit():
            flash('Deze taxatie kan niet bewerkt worden omdat de status "definitief" is.', 'error')
            return redirect(url_for('dossier_detail', dossier_id=dossier_id))
        
        # Update taxatie data
        taxatie.datum = datetime.strptime(request.form.get('datum'), '%Y-%m-%d').date()
        taxatie.taxateur = request.form.get('taxateur')
        taxatie.waarde = float(request.form.get('waarde'))
        taxatie.opmerkingen = request.form.get('opmerkingen')
        
        # Update calculation fields
        hoogte_meters = request.form.get('hoogte_meters')
        prijs_per_m2 = request.form.get('prijs_per_m2')
        prijs_per_m3 = request.form.get('prijs_per_m3')
        berekening_methode = request.form.get('berekening_methode')
        
        taxatie.hoogte_meters = float(hoogte_meters) if hoogte_meters else None
        taxatie.prijs_per_m2 = float(prijs_per_m2) if prijs_per_m2 else None
        taxatie.prijs_per_m3 = float(prijs_per_m3) if prijs_per_m3 else None
        taxatie.berekening_methode = berekening_methode
        
        # Handle photo uploads
        if 'photos' in request.files:
            photos = request.files.getlist('photos')
            for photo in photos:
                if photo and allowed_file(photo.filename, app.config['ALLOWED_EXTENSIONS']['images']):
                    filename = storage.upload_file(photo, folder=f'taxaties/{taxatie.id}')
                    photo_record = Photo(
                        filename=filename,
                        original_filename=photo.filename,
                        taxatie_id=taxatie.id
                    )
                    db.session.add(photo_record)
        
        db.session.commit()
        flash('Taxatie succesvol bijgewerkt', 'success')
        return redirect(url_for('dossier_detail', dossier_id=dossier_id))
    
    return render_template('bewerk_taxatie.html', dossier=dossier, taxatie=taxatie)

@app.route('/dossier/<int:dossier_id>/taxatie/<int:taxatie_id>/status', methods=['POST'])
@login_required
def wijzig_taxatie_status(dossier_id, taxatie_id):
    dossier = Dossier.query.get_or_404(dossier_id)
    if dossier.user_id != current_user.id:
        return redirect(url_for('dossiers'))
    
    taxatie = Taxatie.query.get_or_404(taxatie_id)
    if taxatie.dossier_id != dossier_id:
        return redirect(url_for('dossiers'))
    
    new_status = request.form.get('status')
    if new_status not in ['concept', 'definitief', 'gearchiveerd']:
        flash('Ongeldige status', 'error')
        return redirect(url_for('dossier_detail', dossier_id=dossier_id))
    
    try:
        taxatie.change_status(new_status, current_user.id)
        flash(f'Status van taxatie gewijzigd naar "{new_status}"', 'success')
    except ValueError as e:
        flash(str(e), 'error')
    
    return redirect(url_for('dossier_detail', dossier_id=dossier_id))

@app.route('/dossier/<int:dossier_id>/document/upload', methods=['POST'])
@login_required
def upload_document(dossier_id):
    dossier = Dossier.query.get_or_404(dossier_id)
    if dossier.user_id != current_user.id:
        return redirect(url_for('dossiers'))
    
    if 'document' not in request.files:
        flash('No file part')
        return redirect(url_for('dossier_detail', dossier_id=dossier_id))
    
    file = request.files['document']
    if file.filename == '':
        flash('No selected file')
        return redirect(url_for('dossier_detail', dossier_id=dossier_id))
    
    if file and allowed_file(file.filename, app.config['ALLOWED_EXTENSIONS']['documents']):
        filename = storage.upload_file(file, folder=f'dossiers/{dossier_id}')
        document = Document(
            filename=filename,
            original_filename=file.filename,
            file_type=file.content_type,
            dossier_id=dossier_id
        )
        db.session.add(document)
        db.session.commit()
        flash('Document uploaded successfully')
    else:
        flash('Invalid file type')
    
    return redirect(url_for('dossier_detail', dossier_id=dossier_id))

@app.route('/document/<int:document_id>')
@login_required
def get_document(document_id):
    document = Document.query.get_or_404(document_id)
    dossier = Dossier.query.get_or_404(document.dossier_id)
    
    if dossier.user_id != current_user.id:
        return redirect(url_for('dossiers'))
    
    try:
        file_data = storage.get_file(document.filename)
        return send_file(
            io.BytesIO(file_data),
            mimetype=document.file_type,
            as_attachment=True,
            download_name=document.original_filename
        )
    except Exception as e:
        flash('Error retrieving document')
        return redirect(url_for('dossier_detail', dossier_id=document.dossier_id))

@app.route('/photo/<int:photo_id>')
@login_required
def get_photo(photo_id):
    photo = Photo.query.get_or_404(photo_id)
    taxatie = Taxatie.query.get_or_404(photo.taxatie_id)
    dossier = Dossier.query.get_or_404(taxatie.dossier_id)
    
    if dossier.user_id != current_user.id:
        return redirect(url_for('dossiers'))
    
    try:
        file_data = storage.get_file(photo.filename)
        return send_file(
            io.BytesIO(file_data),
            mimetype='image/jpeg',
            as_attachment=False
        )
    except Exception as e:
        flash('Error retrieving photo')
        return redirect(url_for('dossier_detail', dossier_id=dossier.id))

@app.route('/profiel', methods=['GET', 'POST'])
@login_required
def profiel():
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'update_profile':
            current_user.email = request.form.get('email')
            current_user.full_name = request.form.get('full_name')
            
            # Update StreetSmart credentials
            streetsmart_username = request.form.get('streetsmart_username')
            streetsmart_password = request.form.get('streetsmart_password')
            
            if streetsmart_username:
                current_user.streetsmart_username = streetsmart_username
            else:
                current_user.streetsmart_username = None
            
            if streetsmart_password:
                current_user.set_streetsmart_password(streetsmart_password)
            elif not streetsmart_username:
                # If no username is provided, also clear the password
                current_user.streetsmart_password_hash = None
            
            # Update password if provided
            new_password = request.form.get('new_password')
            if new_password:
                if not current_user.check_password(request.form.get('current_password')):
                    flash('Huidig wachtwoord is onjuist', 'error')
                    return redirect(url_for('profiel'))
                current_user.set_password(new_password)
            
            db.session.commit()
            flash('Profiel succesvol bijgewerkt', 'success')
            
    return render_template('profiel.html', user=current_user)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Je hebt geen toegang tot deze pagina.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin', methods=['GET', 'POST'])
@login_required
@admin_required
def admin():
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'update_user_status':
            user_id = request.form.get('user_id')
            new_status = request.form.get('status')
            user = User.query.get_or_404(user_id)
            old_status = user.registration_status
            user.registration_status = new_status
            # Log de statuswijziging
            log = UserLog(
                user_id=current_user.id,
                action='update_user_status',
                details=f'Changed status of user {user.username} from {old_status} to {new_status}'
            )
            db.session.add(log)
            db.session.commit()
            flash(f'Status van gebruiker {user.username} bijgewerkt naar {new_status}', 'success')
        elif action == 'delete_user':
            user_id = request.form.get('user_id')
            user = User.query.get_or_404(user_id)
            if user.id != current_user.id:
                log = UserLog(
                    user_id=current_user.id,
                    action='delete_user',
                    details=f'Deleted user {user.username}'
                )
                db.session.add(log)
                db.session.delete(user)
                db.session.commit()
                flash(f'Gebruiker {user.username} verwijderd', 'success')
            else:
                flash('Je kunt je eigen account niet verwijderen', 'error')
        elif action == 'add_allowed_user':
            email = request.form.get('email')
            full_name = request.form.get('full_name')
            role = request.form.get('role', 'user')
            
            if not email:
                flash('Email adres is verplicht', 'error')
            elif AllowedUser.query.filter_by(email=email).first():
                flash('Deze email is al toegevoegd', 'error')
            else:
                allowed_user = AllowedUser(
                    email=email,
                    full_name=full_name,
                    role=role,
                    added_by=current_user.id
                )
                db.session.add(allowed_user)
                db.session.commit()
                flash(f'Gebruiker {email} toegevoegd aan whitelist', 'success')
        elif action == 'remove_allowed_user':
            allowed_user_id = request.form.get('allowed_user_id')
            allowed_user = AllowedUser.query.get_or_404(allowed_user_id)
            email = allowed_user.email
            db.session.delete(allowed_user)
            db.session.commit()
            flash(f'Gebruiker {email} verwijderd uit whitelist', 'success')
        elif action == 'update_google_oauth':
            set_setting('GOOGLE_CLIENT_ID', request.form.get('google_client_id'))
            set_setting('GOOGLE_CLIENT_SECRET', request.form.get('google_client_secret'))
            log = UserLog(
                user_id=current_user.id,
                action='update_google_oauth',
                details='Updated Google OAuth settings'
            )
            db.session.add(log)
            db.session.commit()
            flash('Google OAuth instellingen bijgewerkt', 'success')
        elif action == 'update_storage':
            storage_type = request.form.get('storage_type')
            if storage_type == 'minio':
                set_setting('STORAGE_TYPE', 'minio')
                set_setting('MINIO_ENDPOINT', request.form.get('minio_endpoint'))
                set_setting('MINIO_ACCESS_KEY', request.form.get('minio_access_key'))
                set_setting('MINIO_SECRET_KEY', request.form.get('minio_secret_key'))
                set_setting('MINIO_BUCKET', request.form.get('minio_bucket'))
            else:
                set_setting('STORAGE_TYPE', 'local')
            log = UserLog(
                user_id=current_user.id,
                action='update_storage_settings',
                details=f'Updated storage settings to {storage_type}'
            )
            db.session.add(log)
            db.session.commit()
            flash('Opslaginstellingen succesvol bijgewerkt', 'success')
        elif action == 'update_api_config':
            set_setting('BAG_API_URL', request.form.get('bag_api_url'))
            set_setting('BAG_API_KEY', request.form.get('bag_api_key'))
            set_setting('BAG_PDOK_API_URL', request.form.get('bag_pdok_api_url'))
            set_setting('BAG_PDOK_API_KEY', request.form.get('bag_pdok_api_key'))
            set_setting('STREETSMART_API_URL', request.form.get('streetsmart_api_url'))
            set_setting('STREETSMART_API_KEY', request.form.get('streetsmart_api_key'))
            set_setting('WALKSCORE_API_URL', request.form.get('walkscore_api_url'))
            set_setting('WALKSCORE_API_KEY', request.form.get('walkscore_api_key'))
            set_setting('pdok_api_url', request.form.get('pdok_api_url'))
            log = UserLog(
                user_id=current_user.id,
                action='update_api_config',
                details='Updated API configurations'
            )
            db.session.add(log)
            db.session.commit()
            flash('API configuraties bijgewerkt', 'success')
        elif action == 'update_system_settings':
            set_setting('ALLOW_REGISTRATION', str(request.form.get('allow_registration') == 'true'))
            set_setting('REQUIRE_EMAIL_VERIFICATION', str(request.form.get('require_email_verification') == 'true'))
            set_setting('MAX_FILE_SIZE', str(int(request.form.get('max_file_size', 10)) * 1024 * 1024))
            log = UserLog(
                user_id=current_user.id,
                action='update_system_settings',
                details='Updated system settings'
            )
            db.session.add(log)
            db.session.commit()
            flash('Systeeminstellingen bijgewerkt', 'success')
    users = User.query.filter(User.id != current_user.id).all()
    total_users = User.query.count()
    active_users = User.query.filter_by(is_active=True).count()
    pending_users = User.query.filter_by(registration_status='pending').count()
    total_dossiers = Dossier.query.count()
    total_taxaties = Taxatie.query.count()
    recent_logs = UserLog.query.order_by(UserLog.timestamp.desc()).limit(10).all()
    allowed_users = AllowedUser.query.all()
    
    return render_template('admin.html',
                         users=users,
                         recent_logs=recent_logs,
                         allowed_users=allowed_users,
                         statistics={
                             'total_users': total_users,
                             'active_users': active_users,
                             'pending_users': pending_users,
                             'total_dossiers': total_dossiers,
                             'total_taxaties': total_taxaties
                         },
                         system_settings={
                             'allow_registration': get_setting('ALLOW_REGISTRATION', 'True') == 'True',
                             'require_email_verification': get_setting('REQUIRE_EMAIL_VERIFICATION', 'False') == 'True',
                             'max_file_size': int(get_setting('MAX_FILE_SIZE', str(10 * 1024 * 1024))) // (1024 * 1024)
                         },
                         storage_type=get_setting('STORAGE_TYPE', 'local'),
                         minio_endpoint=get_setting('MINIO_ENDPOINT', ''),
                         minio_access_key=get_setting('MINIO_ACCESS_KEY', ''),
                         minio_secret_key=get_setting('MINIO_SECRET_KEY', ''),
                         minio_bucket=get_setting('MINIO_BUCKET', ''),
                         bag_api_url=get_setting('BAG_API_URL', ''),
                         bag_api_key=get_setting('BAG_API_KEY', ''),
                         bag_pdok_api_url=get_setting('BAG_PDOK_API_URL', ''),
                         bag_pdok_api_key=get_setting('BAG_PDOK_API_KEY', ''),
                         streetsmart_api_url=get_setting('STREETSMART_API_URL', ''),
                         streetsmart_api_key=get_setting('STREETSMART_API_KEY', ''),
                         walkscore_api_url=get_setting('WALKSCORE_API_URL', ''),
                         walkscore_api_key=get_setting('WALKSCORE_API_KEY', ''),
                         pdok_api_url=get_setting('pdok_api_url', ''),
                         google_client_id=get_setting('GOOGLE_CLIENT_ID', ''),
                         google_client_secret=get_setting('GOOGLE_CLIENT_SECRET', ''))

@app.route('/api/bag_lookup', methods=['GET'])
@login_required
def bag_lookup():
    postcode = request.args.get('postcode', '').replace(' ', '').upper()
    huisnummer = request.args.get('huisnummer', '')
    huisletter = request.args.get('huisletter', '')

    if not postcode or not huisnummer:
        return jsonify({'error': 'Postcode en huisnummer zijn verplicht'}), 400

    api_url = get_setting('BAG_API_URL')
    api_key = get_setting('BAG_API_KEY')
    if not api_url or not api_key:
        return jsonify({'error': 'BAG API URL of API key ontbreekt!'}), 400

    bag_service = BagService(api_url, api_key)
    result, status = bag_service.lookup_address(postcode, huisnummer, huisletter)
    return jsonify(result), status

@app.route('/api/bag_lookup_and_save', methods=['POST'])
@login_required
def bag_lookup_and_save():
    """Lookup BAG data and save to database for a dossier"""
    data = request.get_json()
    postcode = data.get('postcode', '').replace(' ', '').upper()
    huisnummer = data.get('huisnummer', '')
    huisletter = data.get('huisletter', '')
    dossier_id = data.get('dossier_id')
    
    # Debug logging
    print(f"DEBUG BAG API: Received data: {data}")
    print(f"DEBUG BAG API: postcode='{postcode}', huisnummer='{huisnummer}', huisletter='{huisletter}', dossier_id='{dossier_id}'")
    
    if not postcode or not huisnummer:
        print(f"DEBUG BAG API: Validation failed - postcode empty: {not postcode}, huisnummer empty: {not huisnummer}")
        return jsonify({'error': 'Postcode en huisnummer zijn verplicht'}), 400
    
    if not dossier_id:
        return jsonify({'error': 'Dossier ID is verplicht'}), 400
    
    try:
        # Check if dossier exists and user has access
        dossier = Dossier.query.get_or_404(dossier_id)
        if dossier.user_id != current_user.id:
            return jsonify({'error': 'Geen toegang tot dit dossier'}), 403
        
        api_url = get_setting('BAG_API_URL')
        api_key = get_setting('BAG_API_KEY')
        if not api_url or not api_key:
            return jsonify({'error': 'BAG API URL of API key ontbreekt!'}), 400

        bag_service = BagService(api_url, api_key)
        result, status = bag_service.lookup_address(postcode, huisnummer, huisletter)
        
        if status == 200:
            # Check if BAG data already exists for this dossier
            existing_bag = BagData.query.filter_by(dossier_id=dossier_id).first()
            
            if existing_bag:
                # Update existing BAG data
                bag_data = existing_bag
            else:
                # Create new BAG data
                bag_data = BagData(dossier_id=dossier_id)
            
            # Update BAG data fields
            if 'adres' in result:
                adres_data = result['adres']
                bag_data.straatnaam = adres_data.get('straat', '')
                bag_data.huisnummer = adres_data.get('huisnummer', '')
                bag_data.huisletter = adres_data.get('huisletter', '')
                bag_data.postcode = adres_data.get('postcode', '')
                bag_data.woonplaats = adres_data.get('woonplaats', '')
            
            bag_data.bouwjaar = str(result['bouwjaar']) if result.get('bouwjaar') else None
            bag_data.oppervlakte = str(result['oppervlakte']) if result.get('oppervlakte') else None
            bag_data.inhoud = str(result['inhoud']) if result.get('inhoud') else None
            bag_data.hoogte = str(result['hoogte']) if result.get('hoogte') else None
            bag_data.aantal_bouwlagen = str(result['aantal_bouwlagen']) if result.get('aantal_bouwlagen') else None
            
            # Process gebruiksdoel with priority logic
            if 'gebruiksdoel' in result:
                if isinstance(result['gebruiksdoel'], list):
                    # Store all gebruiksdoelen as a comma-separated string
                    gebruiksdoelen = result['gebruiksdoel']
                    if not gebruiksdoelen:
                        bag_data.gebruiksdoel = None
                    else:
                        bag_data.gebruiksdoel = ', '.join(gebruiksdoelen)
                else:
                    bag_data.gebruiksdoel = str(result['gebruiksdoel']) if result['gebruiksdoel'] else None
            
            # Store geodata if available
            if 'geodata' in result:
                geodata = result['geodata']
                bag_data.centroide_ll = geodata.get('centroide_ll')
                bag_data.centroide_rd = geodata.get('centroide_rd')
                bag_data.geometrie = json.dumps(geodata.get('geometrie')) if geodata.get('geometrie') else None
                bag_data.latitude = geodata.get('latitude')
                bag_data.longitude = geodata.get('longitude')
                bag_data.x_coord = geodata.get('x_coord')
                bag_data.y_coord = geodata.get('y_coord')
                bag_data.google_maps_url = geodata.get('google_maps_url')
            
            # Store the full API response
            bag_data.api_response_data = json.dumps(result)
            bag_data.last_updated = datetime.utcnow()
            
            if not existing_bag:
                db.session.add(bag_data)
            
            # Also update the dossier with the processed data for backward compatibility
            if 'bouwjaar' in result:
                dossier.bouwjaar = str(result['bouwjaar']) if result['bouwjaar'] else None
            if 'oppervlakte' in result:
                dossier.oppervlakte = str(result['oppervlakte']) if result['oppervlakte'] else None
            if 'inhoud' in result:
                dossier.inhoud = str(result['inhoud']) if result['inhoud'] else None
            if 'hoogte' in result:
                dossier.hoogte = str(result['hoogte']) if result['hoogte'] else None
            if 'aantal_bouwlagen' in result:
                dossier.aantal_bouwlagen = str(result['aantal_bouwlagen']) if result['aantal_bouwlagen'] else None
            if 'gebruiksdoel' in result:
                if isinstance(result['gebruiksdoel'], list):
                    # Store all gebruiksdoelen as a comma-separated string
                    gebruiksdoelen = result['gebruiksdoel']
                    if not gebruiksdoelen:
                        dossier.gebruiksdoel = None
                    else:
                        dossier.gebruiksdoel = ', '.join(gebruiksdoelen)
                else:
                    dossier.gebruiksdoel = str(result['gebruiksdoel']) if result['gebruiksdoel'] else None
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'BAG data succesvol opgeslagen',
                'data': result
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', 'Onbekende fout bij BAG lookup')
            }), status
            
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'Fout bij BAG lookup en opslag: {str(e)}'
        }), 500

@app.route('/api/woz_lookup', methods=['GET'])
@login_required
def woz_lookup():
    """Lookup WOZ data for an address"""
    address = request.args.get('address', '')
    
    if not address:
        return jsonify({'error': 'Adres is verplicht'}), 400
    
    try:
        woz_service = WozService()
        woz_response = woz_service.lookup_woz_data(address)
        
        if woz_response:
            parsed_data = woz_service.parse_woz_data(woz_response)
            return jsonify({
                'success': True,
                'data': parsed_data
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Geen WOZ data gevonden voor dit adres'
            }), 404
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Fout bij WOZ lookup: {str(e)}'
        }), 500

@app.route('/api/woz_lookup_and_save', methods=['POST'])
@login_required
def woz_lookup_and_save():
    """Lookup WOZ data and save to database for a dossier"""
    data = request.get_json()
    address = data.get('address', '')
    dossier_id = data.get('dossier_id')
    
    if not address:
        return jsonify({'error': 'Adres is verplicht'}), 400
    
    if not dossier_id:
        return jsonify({'error': 'Dossier ID is verplicht'}), 400
    
    try:
        # Check if dossier exists and user has access
        dossier = Dossier.query.get_or_404(dossier_id)
        if dossier.user_id != current_user.id:
            return jsonify({'error': 'Geen toegang tot dit dossier'}), 403
        
        # Check if WOZ data already exists for this dossier
        existing_woz = WozData.query.filter_by(dossier_id=dossier_id).first()
        
        woz_service = WozService()
        woz_response = woz_service.lookup_woz_data(address)
        
        if woz_response:
            parsed_data = woz_service.parse_woz_data(woz_response)
            
            if existing_woz:
                # Update existing WOZ data
                woz_data = existing_woz
            else:
                # Create new WOZ data
                woz_data = WozData(dossier_id=dossier_id)
            
            # Update WOZ data fields
            woz_data.wozobjectnummer = parsed_data['woz_data']['wozobjectnummer']
            woz_data.woonplaatsnaam = parsed_data['woz_data']['woonplaatsnaam']
            woz_data.openbareruimtenaam = parsed_data['woz_data']['openbareruimtenaam']
            woz_data.openbareruimtetype = parsed_data['woz_data']['openbareruimtetype']
            woz_data.straatnaam = parsed_data['woz_data']['straatnaam']
            woz_data.postcode = parsed_data['woz_data']['postcode']
            woz_data.huisnummer = safe_int(parsed_data['woz_data']['huisnummer'])
            woz_data.huisletter = parsed_data['woz_data']['huisletter']
            woz_data.huisnummertoevoeging = parsed_data['woz_data']['huisnummertoevoeging']
            woz_data.gemeentecode = parsed_data['woz_data']['gemeentecode']
            woz_data.grondoppervlakte = safe_int(parsed_data['woz_data']['grondoppervlakte'])
            woz_data.adresseerbaarobjectid = parsed_data['woz_data']['adresseerbaarobjectid']
            woz_data.nummeraanduidingid = parsed_data['woz_data']['nummeraanduidingid']
            woz_data.kadastrale_gemeente_code = parsed_data['woz_data']['kadastrale_gemeente_code']
            woz_data.kadastrale_sectie = parsed_data['woz_data']['kadastrale_sectie']
            woz_data.kadastraal_perceel_nummer = parsed_data['woz_data']['kadastraal_perceel_nummer']
            woz_data.api_response_data = json.dumps(woz_response)
            woz_data.last_updated = datetime.utcnow()
            
            if not existing_woz:
                db.session.add(woz_data)
            db.session.flush()  # Zorg dat woz_data.id beschikbaar is
            
            # Clear existing WOZ values and add new ones
            if existing_woz:
                WozValue.query.filter_by(woz_data_id=existing_woz.id).delete()
            
            # Add WOZ values
            for value_data in parsed_data['woz_values']:
                woz_value = WozValue(
                    woz_data_id=woz_data.id,
                    peildatum=datetime.strptime(value_data['peildatum'], '%Y-%m-%d').date(),
                    vastgestelde_waarde=value_data['vastgestelde_waarde']
                )
                db.session.add(woz_value)
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'WOZ data succesvol opgeslagen',
                'data': parsed_data
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Geen WOZ data gevonden voor dit adres'
            }), 404
            
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'Fout bij WOZ lookup en opslag: {str(e)}'
        }), 500

@app.route('/api/walkscore_lookup', methods=['GET'])
@login_required
def walkscore_lookup():
    """Lookup WalkScore data for an address"""
    postcode = request.args.get('postcode', '').replace(' ', '').upper()
    huisnummer = request.args.get('huisnummer', '')
    huisletter = request.args.get('huisletter', '')
    lat = request.args.get('lat', type=float)
    lon = request.args.get('lon', type=float)
    
    if not postcode or not huisnummer:
        return jsonify({'error': 'Postcode en huisnummer zijn verplicht'}), 400
    
    if not lat or not lon:
        return jsonify({'error': 'Latitude en longitude zijn verplicht voor WalkScore API'}), 400
    
    api_url = get_setting('WALKSCORE_API_URL')
    api_key = get_setting('WALKSCORE_API_KEY')
    if not api_url or not api_key:
        return jsonify({'error': 'WalkScore API URL of API key ontbreekt!'}), 400
    
    walkscore_service = WalkScoreService(api_url, api_key)
    result, status = walkscore_service.lookup_walkscore(
        straat=None,  # Not available in simple lookup
        huisnummer=huisnummer,
        huisletter=huisletter,
        postcode=postcode,
        woonplaats=None,  # Not available in simple lookup
        lat=lat,
        lon=lon
    )
    return jsonify(result), status

@app.route('/api/walkscore_lookup_and_save', methods=['POST'])
@login_required
def walkscore_lookup_and_save():
    """Lookup WalkScore data and save to database for a dossier"""
    data = request.get_json()
    postcode = data.get('postcode', '').replace(' ', '').upper()
    huisnummer = data.get('huisnummer', '')
    huisletter = data.get('huisletter', '')
    dossier_id = data.get('dossier_id')
    
    if not postcode or not huisnummer:
        return jsonify({'error': 'Postcode en huisnummer zijn verplicht'}), 400
    
    if not dossier_id:
        return jsonify({'error': 'Dossier ID is verplicht'}), 400
    
    try:
        # Check if dossier exists and user has access
        dossier = Dossier.query.get_or_404(dossier_id)
        if dossier.user_id != current_user.id:
            return jsonify({'error': 'Geen toegang tot dit dossier'}), 403
        
        api_url = get_setting('WALKSCORE_API_URL')
        api_key = get_setting('WALKSCORE_API_KEY')
        if not api_url or not api_key:
            return jsonify({'error': 'WalkScore API URL of API key ontbreekt!'}), 400
        
        walkscore_service = WalkScoreService(api_url, api_key)
        
        # Get coordinates from BAG data or PDOK data
        lat = None
        lon = None
        straat = None
        woonplaats = None
        
        # First try to get coordinates from BAG data
        bag_data = BagData.query.filter_by(dossier_id=dossier_id).first()
        if bag_data and bag_data.latitude and bag_data.longitude:
            lat = bag_data.latitude
            lon = bag_data.longitude
            straat = bag_data.straatnaam
            woonplaats = bag_data.woonplaats
        else:
            # Try to get coordinates from PDOK data
            pdok_data = PDOKData.query.filter_by(dossier_id=dossier_id).first()
            if pdok_data and pdok_data.latitude and pdok_data.longitude:
                lat = pdok_data.latitude
                lon = pdok_data.longitude
        
        if not lat or not lon:
            return jsonify({
                'success': False,
                'error': 'Geen coördinaten gevonden. Voer eerst BAG of PDOK data in om de locatie te bepalen.'
            }), 400
        
        result, status = walkscore_service.lookup_walkscore(
            straat=straat,
            huisnummer=huisnummer, 
            huisletter=huisletter,
            postcode=postcode,
            woonplaats=woonplaats,
            lat=lat, 
            lon=lon
        )
        
        if status == 200 and result.get('success'):
            # Check if WalkScore data already exists for this dossier
            existing_walkscore = WalkScoreData.query.filter_by(dossier_id=dossier_id).first()
            
            if existing_walkscore:
                # Update existing WalkScore data
                walkscore_data = existing_walkscore
            else:
                # Create new WalkScore data
                walkscore_data = WalkScoreData(dossier_id=dossier_id)
            
            # Update WalkScore data fields
            data = result['data']
            walkscore_data.walkscore = data.get('walkscore')
            walkscore_data.description = data.get('description')
            walkscore_data.logo_url = data.get('logo_url')
            walkscore_data.more_info_icon = data.get('more_info_icon')
            walkscore_data.more_info_link = data.get('more_info_link')
            walkscore_data.ws_link = data.get('ws_link')
            walkscore_data.help_link = data.get('help_link')
            walkscore_data.snapped_lat = data.get('snapped_lat')
            walkscore_data.snapped_lon = data.get('snapped_lon')
            
            # Update transit data
            if 'transit' in data and data['transit']:
                transit = data['transit']
                walkscore_data.transit_score = transit.get('score')
                walkscore_data.transit_description = transit.get('description')
                walkscore_data.transit_summary = transit.get('summary')
            
            # Update bike data
            if 'bike' in data and data['bike']:
                bike = data['bike']
                walkscore_data.bike_score = bike.get('score')
                walkscore_data.bike_description = bike.get('description')
            
            walkscore_data.api_response_data = json.dumps(result.get('raw_response', {}))
            walkscore_data.last_updated = datetime.utcnow()
            
            if not existing_walkscore:
                db.session.add(walkscore_data)
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'WalkScore data succesvol opgeslagen',
                'data': data
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', 'Onbekende fout bij WalkScore lookup')
            }), status
            
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'Fout bij WalkScore lookup en opslag: {str(e)}'
        }), 500

@app.route('/api/pdok_lookup', methods=['GET'])
@login_required
def pdok_lookup():
    try:
        postcode = request.args.get('postcode')
        huisnummer = request.args.get('huisnummer')
        huisletter = request.args.get('huisletter')
        
        if not postcode or not huisnummer:
            return jsonify({'error': 'Postcode and huisnummer are required'}), 400
        
        # Use hardcoded PDOK API URL (open data, no key required)
        pdok_api_url = 'https://data.pdok.nl/bag/api/v1/'
        
        if not pdok_api_url:
            return jsonify({'error': 'BAG PDOK API URL not configured'}), 400
        
        # Initialize PDOK service (no API key needed for open data)
        pdok_service = PDOKService(pdok_api_url)
        
        # Lookup PDOK data
        response_data, status_code = pdok_service.lookup_pdok_data(
            postcode, huisnummer, huisletter
        )
        
        return jsonify(response_data), status_code
        
    except Exception as e:
        app.logger.error(f"Error in PDOK lookup: {e}")
        return jsonify({'error': f'Error in PDOK lookup: {str(e)}'}), 500

@app.route('/api/pdok_lookup_and_save', methods=['POST'])
@login_required
def pdok_lookup_and_save():
    try:
        data = request.get_json()
        dossier_id = data.get('dossier_id')
        
        if not dossier_id:
            return jsonify({'error': 'Dossier ID is required'}), 400
        
        dossier = Dossier.query.get(dossier_id)
        if not dossier:
            return jsonify({'error': 'Dossier not found'}), 404
        
        # Get address information from dossier
        postcode = dossier.postcode
        # Extract huisnummer from dossier.adres (e.g., "Pippelingstraat 31" -> "31")
        adres_parts = dossier.adres.split(',')[0].split(' ')
        huisnummer = None
        huisletter = None
        
        # Find huisnummer in address parts
        for part in adres_parts:
            # Remove common suffixes and check if it's a number
            import re
            clean_part = re.sub(r'[-ABab]', '', part)
            try:
                int(clean_part)  # Check if it's a number
                huisnummer = clean_part
                # Check if there's a letter after the number
                if len(part) > len(clean_part):
                    huisletter = part[len(clean_part):]
                break
            except ValueError:
                continue
        
        if not postcode or not huisnummer:
            return jsonify({'error': 'Postcode and huisnummer could not be extracted from dossier data'}), 400
        
        # Use hardcoded PDOK API URL (open data, no key required)
        pdok_api_url = 'https://geodata.nationaalgeoregister.nl/locatieserver/v3/'
        
        # Initialize PDOK service (no API key needed for open data)
        pdok_service = PDOKService(pdok_api_url)
        
        # Lookup PDOK data
        response_data, status_code = pdok_service.lookup_pdok_data(
            postcode, 
            huisnummer, 
            huisletter
        )
        
        if status_code != 200:
            return jsonify(response_data), status_code
        
        # Extract data for database storage
        pdok_data_dict = response_data.get('data', {})
        address_info = pdok_data_dict.get('address_info', {})
        property_data = pdok_data_dict.get('property_data', {})
        data_quality = pdok_data_dict.get('data_quality', {})
        
        # Calculate property type and relevance score
        property_type_category = pdok_service.get_property_type_category(
            property_data.get('basic_info', {}).get('property_type', '')
        )
        taxatie_relevance_score = pdok_service.get_taxatie_relevance_score(property_data)
        
        # Extract data quality indicators
        data_quality = pdok_data_dict.get('data_quality', {})
        
        # Save to database
        existing_data = PDOKData.query.filter_by(dossier_id=dossier_id).first()
        if existing_data:
            # Update existing record
            existing_data.bag_id = address_info.get('bag_id')
            existing_data.search_successful = address_info.get('search_successful')
            existing_data.address = address_info.get('address')
            
            # Coordinates
            coordinates = address_info.get('coordinates', {})
            existing_data.latitude = coordinates.get('latitude')
            existing_data.longitude = coordinates.get('longitude')
            
            # Basic property information
            basic_info = property_data.get('basic_info', {})
            existing_data.status = basic_info.get('status')
            existing_data.bouwjaar = basic_info.get('bouwjaar')
            existing_data.oppervlakte = basic_info.get('oppervlakte')
            existing_data.property_type = basic_info.get('property_type')
            
            # 3D Data
            three_d_data = property_data.get('3d_data', {})
            existing_data.building_height = three_d_data.get('height')
            existing_data.roof_height = three_d_data.get('roof_height')
            existing_data.ground_height = three_d_data.get('ground_height')
            existing_data.building_volume = three_d_data.get('building_volume')
            existing_data.roof_type = three_d_data.get('roof_type')
            existing_data.model_3d_available = three_d_data.get('3d_model_available')
            
            # Kadastrale Data
            kadastrale_data = property_data.get('kadastrale_data', {})
            existing_data.perceel_id = kadastrale_data.get('perceel_id')
            existing_data.kadastrale_gemeente = kadastrale_data.get('kadastrale_gemeente')
            existing_data.sectie = kadastrale_data.get('sectie')
            existing_data.perceelnummer = kadastrale_data.get('perceelnummer')
            existing_data.perceel_oppervlakte = kadastrale_data.get('oppervlakte')
            existing_data.eigenaar_type = kadastrale_data.get('eigenaar_type')
            existing_data.perceel_gebruik = kadastrale_data.get('gebruik')
            
            # Topographic Context
            topographic_context = property_data.get('topographic_context', {})
            existing_data.surrounding_buildings = topographic_context.get('surrounding_buildings')
            existing_data.land_use = json.dumps(topographic_context.get('land_use', []))
            existing_data.infrastructure = json.dumps(topographic_context.get('infrastructure', []))
            existing_data.water_features = json.dumps(topographic_context.get('water_features', []))
            
            # Data quality indicators
            existing_data.has_basic_info = data_quality.get('has_basic_info')
            existing_data.has_3d_data = data_quality.get('has_3d_data')
            existing_data.has_kadastrale_data = data_quality.get('has_kadastrale_data')
            existing_data.has_topographic_data = data_quality.get('has_topographic_data')
            existing_data.data_sources = json.dumps(data_quality.get('data_sources', []))
            
            # Property categorization
            existing_data.property_type_category = property_type_category
            existing_data.taxatie_relevance_score = taxatie_relevance_score
            
            existing_data.last_updated = datetime.utcnow()
            existing_data.api_response_data = json.dumps(response_data)
            pdok_data = existing_data
        else:
            # Create new record
            coordinates = address_info.get('coordinates', {})
            basic_info = property_data.get('basic_info', {})
            three_d_data = property_data.get('3d_data', {})
            kadastrale_data = property_data.get('kadastrale_data', {})
            topographic_context = property_data.get('topographic_context', {})
            
            pdok_data = PDOKData(
                dossier_id=dossier_id,
                bag_id=address_info.get('bag_id'),
                search_successful=address_info.get('search_successful'),
                address=address_info.get('address'),
                latitude=coordinates.get('latitude'),
                longitude=coordinates.get('longitude'),
                
                # Basic property information
                status=basic_info.get('status'),
                bouwjaar=basic_info.get('bouwjaar'),
                oppervlakte=basic_info.get('oppervlakte'),
                property_type=basic_info.get('property_type'),
                
                # 3D Data
                building_height=three_d_data.get('height'),
                roof_height=three_d_data.get('roof_height'),
                ground_height=three_d_data.get('ground_height'),
                building_volume=three_d_data.get('building_volume'),
                roof_type=three_d_data.get('roof_type'),
                model_3d_available=three_d_data.get('3d_model_available'),
                
                # Kadastrale Data
                perceel_id=kadastrale_data.get('perceel_id'),
                kadastrale_gemeente=kadastrale_data.get('kadastrale_gemeente'),
                sectie=kadastrale_data.get('sectie'),
                perceelnummer=kadastrale_data.get('perceelnummer'),
                perceel_oppervlakte=kadastrale_data.get('oppervlakte'),
                eigenaar_type=kadastrale_data.get('eigenaar_type'),
                perceel_gebruik=kadastrale_data.get('gebruik'),
                
                # Topographic Context
                surrounding_buildings=topographic_context.get('surrounding_buildings'),
                land_use=json.dumps(topographic_context.get('land_use', [])),
                infrastructure=json.dumps(topographic_context.get('infrastructure', [])),
                water_features=json.dumps(topographic_context.get('water_features', [])),
                
                # Data quality indicators
                has_basic_info=data_quality.get('has_basic_info'),
                has_3d_data=data_quality.get('has_3d_data'),
                has_kadastrale_data=data_quality.get('has_kadastrale_data'),
                has_topographic_data=data_quality.get('has_topographic_data'),
                data_sources=json.dumps(data_quality.get('data_sources', [])),
                
                # Property categorization
                property_type_category=property_type_category,
                taxatie_relevance_score=taxatie_relevance_score,
                
                api_response_data=json.dumps(response_data)
            )
            db.session.add(pdok_data)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'PDOK data saved successfully',
            'data': response_data
        }), 200
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error saving PDOK data: {e}")
        return jsonify({'error': f'Error saving PDOK data: {str(e)}'}), 500

@app.route('/api/streetsmart_credentials', methods=['GET'])
@login_required
def get_streetsmart_credentials():
    """Get current user's StreetSmart credentials status"""
    try:
        has_credentials = bool(current_user.streetsmart_username and current_user.streetsmart_password_hash)
        
        if has_credentials:
            return jsonify({
                'success': True,
                'has_credentials': True,
                'username': current_user.streetsmart_username
            })
        else:
            return jsonify({
                'success': True,
                'has_credentials': False,
                'message': 'Geen StreetSmart credentials gevonden. Voeg ze toe in je profiel.'
            })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Fout bij ophalen StreetSmart credentials: {str(e)}'
        }), 500

def safe_int(val):
    """Safely convert value to integer"""
    try:
        return int(val)
    except (ValueError, TypeError):
        return None

def normalize_postcode(postcode):
    """Normalize postcode format (remove spaces, uppercase)"""
    if not postcode:
        return None
    return postcode.replace(' ', '').upper()

def normalize_huisnummer(huisnummer):
    """Normalize house number (remove leading zeros, handle ranges)"""
    if not huisnummer:
        return None
    # Convert to string and remove leading zeros
    huisnummer_str = str(huisnummer).strip()
    # Handle ranges like "1-3" by taking the first number
    if '-' in huisnummer_str:
        huisnummer_str = huisnummer_str.split('-')[0]
    return huisnummer_str.lstrip('0') or '0'

def normalize_huisletter(huisletter):
    """Normalize house letter (uppercase, handle special characters)"""
    if not huisletter:
        return None
    return huisletter.strip().upper()

def check_duplicate_dossier(postcode, huisnummer, huisletter=None, exclude_id=None):
    """Check if a dossier already exists with the same address"""
    normalized_postcode = normalize_postcode(postcode)
    normalized_huisnummer = normalize_huisnummer(huisnummer)
    normalized_huisletter = normalize_huisletter(huisletter)
    
    if not normalized_postcode or not normalized_huisnummer:
        return None
    
    # Build query
    query = Dossier.query.filter(
        Dossier.postcode == normalized_postcode,
        Dossier.user_id == current_user.id
    )
    
    # Extract house number from address field
    # This is a simplified approach - in a real implementation you might want to store house number separately
    query = query.filter(Dossier.adres.contains(normalized_huisnummer))
    
    if exclude_id:
        query = query.filter(Dossier.id != exclude_id)
    
    return query.first()

@app.route('/api/dossiers/search', methods=['GET'])
@login_required
def search_dossiers():
    """Search dossiers with various criteria"""
    query = request.args.get('q', '').strip()
    filter_type = request.args.get('filter', 'all')
    sort_by = request.args.get('sort', 'created_date_desc')
    
    # Base query - only user's dossiers
    dossiers_query = Dossier.query.filter_by(user_id=current_user.id)
    
    # Apply search filter
    if query:
        if filter_type == 'naam':
            dossiers_query = dossiers_query.filter(Dossier.naam.ilike(f'%{query}%'))
        elif filter_type == 'adres':
            dossiers_query = dossiers_query.filter(Dossier.adres.ilike(f'%{query}%'))
        elif filter_type == 'postcode':
            dossiers_query = dossiers_query.filter(Dossier.postcode.ilike(f'%{query}%'))
        elif filter_type == 'plaats':
            dossiers_query = dossiers_query.filter(Dossier.plaats.ilike(f'%{query}%'))
        elif filter_type == 'bouwjaar':
            dossiers_query = dossiers_query.filter(Dossier.bouwjaar.ilike(f'%{query}%'))
        elif filter_type == 'gebruiksdoel':
            dossiers_query = dossiers_query.filter(Dossier.gebruiksdoel.ilike(f'%{query}%'))
        else:
            # Full text search across multiple fields
            dossiers_query = dossiers_query.filter(
                db.or_(
                    Dossier.naam.ilike(f'%{query}%'),
                    Dossier.adres.ilike(f'%{query}%'),
                    Dossier.postcode.ilike(f'%{query}%'),
                    Dossier.plaats.ilike(f'%{query}%'),
                    Dossier.bouwjaar.ilike(f'%{query}%'),
                    Dossier.gebruiksdoel.ilike(f'%{query}%')
                )
            )
    
    # Apply sorting
    if sort_by == 'naam_asc':
        dossiers_query = dossiers_query.order_by(Dossier.naam.asc())
    elif sort_by == 'naam_desc':
        dossiers_query = dossiers_query.order_by(Dossier.naam.desc())
    elif sort_by == 'adres_asc':
        dossiers_query = dossiers_query.order_by(Dossier.adres.asc())
    elif sort_by == 'adres_desc':
        dossiers_query = dossiers_query.order_by(Dossier.adres.desc())
    elif sort_by == 'created_date_asc':
        dossiers_query = dossiers_query.order_by(Dossier.created_at.asc())
    else:  # created_date_desc (default)
        dossiers_query = dossiers_query.order_by(Dossier.created_at.desc())
    
    # Execute query
    dossiers = dossiers_query.all()
    
    # Format results
    results = []
    for dossier in dossiers:
        results.append({
            'id': dossier.id,
            'naam': dossier.naam,
            'adres': dossier.adres,
            'postcode': dossier.postcode,
            'plaats': dossier.plaats,
            'bouwjaar': dossier.bouwjaar,
            'gebruiksdoel': dossier.gebruiksdoel,
            'created_at': dossier.created_at.strftime('%d-%m-%Y'),
            'taxatie_count': len(dossier.taxaties),
            'document_count': len(dossier.documents),
            'detail_url': url_for('dossier_detail', dossier_id=dossier.id)
        })
        
        return jsonify({
        'success': True,
        'results': results,
        'count': len(results),
        'query': query,
        'filter': filter_type,
        'sort': sort_by
    })

@app.route('/api/dossiers/check_duplicate', methods=['POST'])
@login_required
def check_duplicate_dossier_api():
    """Check for duplicate dossiers based on address"""
    data = request.get_json()
    postcode = data.get('postcode', '').replace(' ', '').upper()
    huisnummer = data.get('huisnummer', '')
    huisletter = data.get('huisletter', '')
    exclude_id = data.get('exclude_id')
    
    if not postcode or not huisnummer:
        return jsonify({'error': 'Postcode en huisnummer zijn verplicht'}), 400
    
    try:
        duplicates = check_duplicate_dossier(postcode, huisnummer, huisletter, exclude_id)
        
        if duplicates:
            return jsonify({
                'has_duplicates': True,
                'duplicates': [{
                    'id': d.id,
                    'naam': d.naam,
                    'adres': d.adres,
                    'postcode': d.postcode,
                    'plaats': d.plaats,
                    'created_at': d.created_at.strftime('%d-%m-%Y %H:%M')
                } for d in duplicates]
            }), 200
        else:
            return jsonify({
                'has_duplicates': False,
                'duplicates': []
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': f'Fout bij duplicate check: {str(e)}'
        }), 500

@app.route('/api/dossier/<int:dossier_id>/map_data', methods=['GET'])
@login_required
def get_dossier_map_data(dossier_id):
    """Get map data for a dossier based on BAG geodata"""
    try:
        # Check if dossier exists and user has access
        dossier = Dossier.query.get_or_404(dossier_id)
        if dossier.user_id != current_user.id:
            return jsonify({'error': 'Geen toegang tot dit dossier'}), 403
        
        # Get BAG data for this dossier
        bag_data = BagData.query.filter_by(dossier_id=dossier_id).first()
        
        if not bag_data:
            return jsonify({
                'error': 'Geen BAG data beschikbaar voor dit dossier'
            }), 404
        
        # Check if we have geodata
        if not bag_data.latitude or not bag_data.longitude:
            return jsonify({
                'error': 'Geen geodata beschikbaar voor dit dossier'
            }), 404
        
        # Prepare map data
        map_data = {
            'dossier_id': dossier_id,
            'address': f"{bag_data.straatnaam} {bag_data.huisnummer}{bag_data.huisletter or ''}, {bag_data.postcode} {bag_data.woonplaats}",
            'coordinates': {
                'latitude': bag_data.latitude,
                'longitude': bag_data.longitude,
                'centroide_ll': bag_data.centroide_ll,
                'centroide_rd': bag_data.centroide_rd,
                'x_coord': bag_data.x_coord,
                'y_coord': bag_data.y_coord
            },
            'property_info': {
                'bouwjaar': bag_data.bouwjaar,
                'oppervlakte': bag_data.oppervlakte,
                'gebruiksdoel': bag_data.gebruiksdoel,
                'aantal_bouwlagen': bag_data.aantal_bouwlagen
            }
        }
        
        # Add geometry if available
        if bag_data.geometrie:
            try:
                map_data['geometry'] = json.loads(bag_data.geometrie)
            except json.JSONDecodeError:
                pass
        
        return jsonify({
            'success': True,
            'map_data': map_data
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Fout bij ophalen map data: {str(e)}'
        }), 500

@app.route('/uploads/<path:filename>')
@login_required
def serve_upload(filename):
    """Serve uploaded files from local storage"""
    upload_folder = app.config.get('UPLOAD_FOLDER', 'uploads')
    file_path = os.path.join(upload_folder, filename)
    
    if not os.path.exists(file_path):
        abort(404)
    
    return send_from_directory(upload_folder, filename)

@app.route('/dossier/<int:dossier_id>/verwijderen', methods=['POST'])
@login_required
def verwijder_dossier(dossier_id):
    """Delete a dossier if it has no taxaties"""
    dossier = Dossier.query.get_or_404(dossier_id)
    if dossier.user_id != current_user.id:
        flash('Je hebt geen toegang tot dit dossier', 'error')
        return redirect(url_for('dossiers'))
    
    # Check if dossier has taxaties
    if dossier.taxaties:
        flash('Dossier kan niet worden verwijderd omdat er nog taxaties aan gekoppeld zijn', 'error')
        return redirect(url_for('dossier_detail', dossier_id=dossier_id))
    
    try:
        # Delete related documents
        for document in dossier.documents:
            try:
                storage.delete_file(document.filename)
            except Exception as e:
                print(f"Error deleting document file: {e}")
        
        # Delete WOZ data
        for woz_data in dossier.woz_data:
            db.session.delete(woz_data)
        
        # Delete the dossier
        db.session.delete(dossier)
        db.session.commit()
        
        flash('Dossier succesvol verwijderd', 'success')
        return redirect(url_for('dossiers'))
        
    except Exception as e:
        db.session.rollback()
        flash('Fout bij verwijderen dossier', 'error')
        return redirect(url_for('dossier_detail', dossier_id=dossier_id))

@app.route('/dossier/<int:dossier_id>/taxatie/<int:taxatie_id>/verwijderen', methods=['POST'])
@login_required
def verwijder_taxatie(dossier_id, taxatie_id):
    """Delete a taxatie"""
    dossier = Dossier.query.get_or_404(dossier_id)
    if dossier.user_id != current_user.id:
        flash('Je hebt geen toegang tot dit dossier', 'error')
        return redirect(url_for('dossiers'))
    
    taxatie = Taxatie.query.get_or_404(taxatie_id)
    if taxatie.dossier_id != dossier_id:
        flash('Taxatie hoort niet bij dit dossier', 'error')
        return redirect(url_for('dossiers'))
    
    # Alleen huidige status controleren
    if taxatie.status == 'definitief':
        flash('Definitieve taxaties kunnen niet worden verwijderd', 'error')
        return redirect(url_for('dossier_detail', dossier_id=dossier_id))
    
    try:
        # Delete related photos
        for photo in taxatie.photos:
            try:
                storage.delete_file(photo.filename)
            except Exception as e:
                print(f"Error deleting photo file: {e}")
        
        # Delete status history
        for status_log in taxatie.status_history:
            db.session.delete(status_log)
        
        # Delete the taxatie
        db.session.delete(taxatie)
        db.session.commit()
        
        flash('Taxatie succesvol verwijderd', 'success')
        return redirect(url_for('dossier_detail', dossier_id=dossier_id))
        
    except Exception as e:
        import traceback
        print('Fout bij verwijderen taxatie:', e)
        traceback.print_exc()
        db.session.rollback()
        flash('Fout bij verwijderen taxatie', 'error')
        return redirect(url_for('dossier_detail', dossier_id=dossier_id))

@app.template_filter('fromjson')
def fromjson_filter(s):
    import json
    if not s:
        return {}
    return json.loads(s)

@app.template_filter('isdigit')
def isdigit_filter(s):
    """Check if a string contains only digits"""
    if not s:
        return False
    return str(s).isdigit()

@app.template_filter('walkscore_color')
def walkscore_color_filter(score):
    """Get color class for WalkScore display"""
    try:
        score_int = int(score)
        if score_int >= 90:
            return "text-green-600"
        elif score_int >= 70:
            return "text-green-500"
        elif score_int >= 50:
            return "text-yellow-600"
        elif score_int >= 25:
            return "text-orange-500"
        else:
            return "text-red-500"
    except (ValueError, TypeError):
        return "text-muted"

@app.route('/dossier/<int:dossier_id>/taxatie/bereken', methods=['POST', 'OPTIONS'])
def bereken_taxatie(dossier_id):
    # Handle CORS preflight request
    if request.method == 'OPTIONS':
        response = make_response()
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response
    
    # Temporarily disable authentication for debugging
    # if not current_user.is_authenticated:
    #     return jsonify({'error': 'Niet ingelogd'}), 401
    
    # Temporarily disable user authorization check
    # if dossier.user_id != current_user.id:
    #     return jsonify({'error': 'Geen toegang tot dit dossier'}), 403
    
    try:
        # Get dossier for property function check (needed for calculation)
        dossier = Dossier.query.get_or_404(dossier_id)
        
        oppervlakte = request.form.get('oppervlakte')
        hoogte = request.form.get('hoogte', 2.6)
        prijs_per_m2 = request.form.get('prijs_per_m2')
        prijs_per_m3 = request.form.get('prijs_per_m3')
        
        if not oppervlakte:
            return jsonify({'error': 'Oppervlakte is verplicht'}), 400
        
        # Create temporary taxatie object for calculation
        temp_taxatie = Taxatie(dossier_id=dossier_id)
        
        # Determine calculation method
        if dossier.gebruiksdoel and 'woonfunctie' in dossier.gebruiksdoel.lower():
            # Residential property: m³ calculation
            if not prijs_per_m3:
                return jsonify({'error': 'Prijs per m³ is verplicht voor woonfunctie'}), 400
            
            volume = float(oppervlakte) * float(hoogte)
            waarde = volume * float(prijs_per_m3)
            berekening_methode = 'm3'
            berekening_details = f"{oppervlakte} m² × {hoogte} m = {volume:.2f} m³ × €{prijs_per_m3} = €{waarde:,.2f}"
        else:
            # Non-residential property: m² calculation
            if not prijs_per_m2:
                return jsonify({'error': 'Prijs per m² is verplicht voor niet-woonfunctie'}), 400
            
            waarde = float(oppervlakte) * float(prijs_per_m2)
            berekening_methode = 'm2'
            berekening_details = f"{oppervlakte} m² × €{prijs_per_m2} = €{waarde:,.2f}"
        
        return jsonify({
            'waarde': waarde,
            'waarde_formatted': f"€{waarde:,.2f}",
            'berekening_methode': berekening_methode,
            'berekening_details': berekening_details,
            'is_woonfunctie': 'woonfunctie' in dossier.gebruiksdoel.lower() if dossier.gebruiksdoel else False
        }), 200
        
    except ValueError as e:
        return jsonify({'error': 'Ongeldige numerieke waarden'}), 400
    except Exception as e:
        return jsonify({'error': 'Berekening mislukt'}), 500

@app.route('/health')
def health_check():
    """Health check endpoint for container monitoring"""
    try:
        # Check database connection
        db.session.execute('SELECT 1')
        db_status = 'healthy'
    except Exception as e:
        db_status = f'unhealthy: {str(e)}'
    
    # Check storage connection - make it more robust
    try:
        # Just check if storage service is initialized, don't test actual operations
        if hasattr(storage, 'storage_type'):
            storage_status = 'healthy'
        else:
            storage_status = 'unhealthy: not initialized'
    except Exception as e:
        storage_status = f'unhealthy: {str(e)}'
    
    # For Kubernetes probes, we want to return healthy if the app is running
    # even if external services are not ready yet
    health_status = {
        'status': 'healthy',  # Always return healthy for basic app functionality
        'timestamp': datetime.utcnow().isoformat(),
        'services': {
            'database': db_status,
            'storage': storage_status
        }
    }
    
    # Return 200 for basic health, 503 only if app itself is broken
    status_code = 200
    return jsonify(health_status), status_code

@app.route('/health/startup')
def startup_health_check():
    """Simple startup health check that doesn't depend on external services"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'message': 'Application is starting up'
    }), 200

@app.route('/dossier/<int:dossier_id>/naam_wijzigen', methods=['POST'])
@login_required
def wijzig_dossier_naam(dossier_id):
    dossier = Dossier.query.get_or_404(dossier_id)
    if dossier.user_id != current_user.id:
        flash('Geen toegang tot dit dossier', 'danger')
        return redirect(url_for('dossier_detail', dossier_id=dossier_id))
    nieuwe_naam = request.form.get('nieuwe_naam', '').strip()
    if not nieuwe_naam:
        flash('Naam mag niet leeg zijn', 'danger')
        return redirect(url_for('dossier_detail', dossier_id=dossier_id))
    dossier.naam = nieuwe_naam
    db.session.commit()
    flash('Dossiernaam succesvol gewijzigd', 'success')
    return redirect(url_for('dossier_detail', dossier_id=dossier_id))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True) 