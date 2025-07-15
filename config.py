import os

class Config:
    # Common settings
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev')
    
    # Database settings - Local SQLite for development
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///pandoorac.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # File storage settings - Local file system storage
    STORAGE_TYPE = os.environ.get('STORAGE_TYPE', 'local')
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'uploads')
    
    # External API settings
    BAG_API_URL = os.environ.get('BAG_API_URL', '')
    BAG_API_KEY = os.environ.get('BAG_API_KEY', '')
    WOZ_API_URL = os.environ.get('WOZ_API_URL', '')
    WOZ_API_KEY = os.environ.get('WOZ_API_KEY', '')
    
    # Application settings
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    ALLOWED_EXTENSIONS = {
        'images': {'png', 'jpg', 'jpeg', 'gif'},
        'documents': {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt'}
    }

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
} 