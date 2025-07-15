import os
from flask import current_app
import boto3
from werkzeug.utils import secure_filename

try:
    import magic
except ImportError:
    magic = None
    print('Waarschuwing: python-magic/libmagic niet gevonden. Bestandstype-detectie is uitgeschakeld.')

class StorageService:
    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        self.storage_type = app.config.get('STORAGE_TYPE', 'local')
        print(f"Storage type: {self.storage_type}")
        
        if self.storage_type == 'local':
            self.upload_folder = app.config.get('UPLOAD_FOLDER', 'uploads')
            print(f"Using local storage in folder: {self.upload_folder}")
            # Create upload folder if it doesn't exist
            os.makedirs(self.upload_folder, exist_ok=True)
        elif self.storage_type == 'minio':
            try:
                # Try to initialize MinIO
                minio_endpoint = app.config.get('MINIO_ENDPOINT')
                minio_access_key = app.config.get('MINIO_ACCESS_KEY')
                minio_secret_key = app.config.get('MINIO_SECRET_KEY')
                minio_bucket = app.config.get('MINIO_BUCKET', 'pandoorac')
                
                if minio_endpoint and minio_access_key and minio_secret_key:
                    print(f"Initializing MinIO storage: {minio_endpoint}")
                    self.s3_client = boto3.client(
                        's3',
                        endpoint_url=minio_endpoint,
                        aws_access_key_id=minio_access_key,
                        aws_secret_access_key=minio_secret_key,
                        region_name='us-east-1'  # MinIO default
                    )
                    self.bucket_name = minio_bucket
                    # Test connection
                    self.s3_client.head_bucket(Bucket=self.bucket_name)
                    print("MinIO storage initialized successfully")
                else:
                    print("MinIO configuration incomplete, falling back to local storage")
                    self.storage_type = 'local'
                    self.upload_folder = app.config.get('UPLOAD_FOLDER', 'uploads')
                    os.makedirs(self.upload_folder, exist_ok=True)
            except Exception as e:
                print(f"MinIO initialization failed: {e}, falling back to local storage")
                self.storage_type = 'local'
                self.upload_folder = app.config.get('UPLOAD_FOLDER', 'uploads')
                os.makedirs(self.upload_folder, exist_ok=True)
        else:
            print("Unknown storage type, falling back to local storage")
            self.storage_type = 'local'
            self.upload_folder = app.config.get('UPLOAD_FOLDER', 'uploads')
            os.makedirs(self.upload_folder, exist_ok=True)

    def upload_file(self, file, folder=None):
        """Upload a file to storage"""
        filename = secure_filename(file.filename)
        if folder:
            filename = f"{folder}/{filename}"

        if self.storage_type == 'local':
            # Save file to local filesystem
            file_path = os.path.join(self.upload_folder, filename)
            # Create directory structure if it doesn't exist
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            file.save(file_path)
            return filename
        else:  # minio
            self.s3_client.upload_fileobj(
                file,
                self.bucket_name,
                filename
            )
            return filename

    def get_file(self, filename):
        """Get file data from storage"""
        if self.storage_type == 'local':
            # Read file from local filesystem
            file_path = os.path.join(self.upload_folder, filename)
            with open(file_path, 'rb') as f:
                return f.read()
        else:  # minio
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=filename
            )
            return response['Body'].read()

    def get_file_url(self, filename):
        """Get a URL for the file"""
        if self.storage_type == 'local':
            # Return local file path for serving
            return f"/uploads/{filename}"
        else:  # minio
            return f"{current_app.config['S3_ENDPOINT_URL']}/{self.bucket_name}/{filename}"

    def delete_file(self, filename):
        """Delete a file from storage"""
        if self.storage_type == 'local':
            # Delete file from local filesystem
            file_path = os.path.join(self.upload_folder, filename)
            if os.path.exists(file_path):
                os.remove(file_path)
        else:  # minio
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=filename
            )

    def ensure_container_exists(self):
        """Ensure the storage container/bucket exists"""
        if self.storage_type == 'local':
            # Ensure upload folder exists
            os.makedirs(self.upload_folder, exist_ok=True)
        else:  # minio
            try:
                self.s3_client.head_bucket(Bucket=self.bucket_name)
            except Exception:
                self.s3_client.create_bucket(Bucket=self.bucket_name) 