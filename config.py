import os
from datetime import timedelta

class Config:
    # Common settings
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev')
    
    # URL scheme configuration for HTTPS proxy
    PREFERRED_URL_SCHEME = os.environ.get('PREFERRED_URL_SCHEME', 'http')
    SERVER_NAME = os.environ.get('SERVER_NAME', None)

    # Session configuration for HTTPS proxy
    SESSION_COOKIE_SECURE = PREFERRED_URL_SCHEME == 'https'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_PERMANENT = False
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    
    # Proxy configuration
    FORCE_HTTPS = True
    
    # Database settings - Local SQLite for development
    def get_database_url():
        # Check if individual PostgreSQL environment variables are set
        if all(os.environ.get(var) for var in ['POSTGRES_HOST', 'POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_DB']):
            host = os.environ.get('POSTGRES_HOST')
            port = os.environ.get('POSTGRES_PORT', '5432')
            user = os.environ.get('POSTGRES_USER')
            password = os.environ.get('POSTGRES_PASSWORD')
            database = os.environ.get('POSTGRES_DB')
            return f'postgresql://{user}:{password}@{host}:{port}/{database}'
        else:
            # Fallback to DATABASE_URL or SQLite
            return os.environ.get('DATABASE_URL', 'sqlite:///pandoorac.db')
    
    SQLALCHEMY_DATABASE_URI = get_database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # File storage settings - MinIO as default
    STORAGE_TYPE = os.environ.get('STORAGE_TYPE', 'minio')
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'uploads')
    
    # MinIO settings
    MINIO_ENDPOINT = os.environ.get('MINIO_ENDPOINT', 'http://localhost:9000')
    MINIO_ACCESS_KEY = os.environ.get('MINIO_ACCESS_KEY', 'minioadmin')
    MINIO_SECRET_KEY = os.environ.get('MINIO_SECRET_KEY', 'minioadmin')
    MINIO_BUCKET = os.environ.get('MINIO_BUCKET', 'pandoorac-local')
    
    # Application settings
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    ALLOWED_EXTENSIONS = {
        'images': {'png', 'jpg', 'jpeg', 'gif'},
        'documents': {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt'}
    }
    
    def __init__(self):
        # Debug: print storage type to verify it's being set correctly
        print(f"Config STORAGE_TYPE: {self.STORAGE_TYPE}")
        print(f"Config MINIO_ENDPOINT: {self.MINIO_ENDPOINT}")
        print(f"Config MINIO_SECRET_KEY: {self.MINIO_SECRET_KEY[:5]}...")

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