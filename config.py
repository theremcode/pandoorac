import os

class Config:
    # Common settings
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev')
    
    # Database settings - Local SQLite for development
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///pandoorac.db')
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