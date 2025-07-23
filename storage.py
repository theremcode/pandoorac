import os
from flask import current_app
import boto3
from werkzeug.utils import secure_filename

try:
    import magic
except ImportError:
    magic = None
    print('Waarschuwing: python-magic/libmagic niet gevonden. Bestandstype-detectie is uitgeschakeld.')

try:
    from azure.storage.blob import BlobServiceClient
    AZURE_AVAILABLE = True
except ImportError:
    AZURE_AVAILABLE = False
    print('Waarschuwing: azure-storage-blob niet gevonden. Azure Blob Storage is uitgeschakeld.')

class StorageService:
    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        # Try to get storage type from database first, then fall back to app config
        try:
            # Import here to avoid circular imports
            from app import get_setting
            storage_type = get_setting('STORAGE_TYPE')
            if storage_type:
                self.storage_type = storage_type
            else:
                self.storage_type = app.config.get('STORAGE_TYPE', 'azure')
        except:
            # If database is not available yet, use app config
            self.storage_type = app.config.get('STORAGE_TYPE', 'azure')
        
        print(f"Storage type: {self.storage_type}")
        
        if self.storage_type == 'local':
            self.upload_folder = app.config.get('UPLOAD_FOLDER', 'uploads')
            print(f"Using local storage in folder: {self.upload_folder}")
            # Create upload folder if it doesn't exist
            os.makedirs(self.upload_folder, exist_ok=True)
        elif self.storage_type == 'azure':
            if not AZURE_AVAILABLE:
                print("Azure Blob Storage libraries not available, falling back to local storage")
                self.storage_type = 'local'
                self.upload_folder = app.config.get('UPLOAD_FOLDER', 'uploads')
                os.makedirs(self.upload_folder, exist_ok=True)
            else:
                try:
                    # Try to get Azure settings from database first
                    try:
                        from app import get_setting
                        azure_account = get_setting('AZURE_STORAGE_ACCOUNT') or app.config.get('AZURE_STORAGE_ACCOUNT')
                        azure_key = get_setting('AZURE_STORAGE_KEY') or app.config.get('AZURE_STORAGE_KEY')
                        azure_container = get_setting('AZURE_CONTAINER_NAME') or app.config.get('AZURE_CONTAINER_NAME', 'pandoorac')
                    except:
                        # Fall back to app config if database not available
                        azure_account = app.config.get('AZURE_STORAGE_ACCOUNT')
                        azure_key = app.config.get('AZURE_STORAGE_KEY')
                        azure_container = app.config.get('AZURE_CONTAINER_NAME', 'pandoorac')
                    
                    if azure_account and azure_key:
                        print(f"Initializing Azure Blob Storage: {azure_account}")
                        account_url = f"https://{azure_account}.blob.core.windows.net"
                        self.blob_service_client = BlobServiceClient(
                            account_url=account_url,
                            credential=azure_key
                        )
                        self.container_name = azure_container
                        
                        # Ensure container exists, create if it doesn't
                        try:
                            container_client = self.blob_service_client.get_container_client(self.container_name)
                            container_client.get_container_properties()
                            print(f"Azure container '{self.container_name}' exists")
                        except Exception as e:
                            print(f"Azure container '{self.container_name}' does not exist, creating it...")
                            try:
                                self.blob_service_client.create_container(self.container_name)
                                print(f"Azure container '{self.container_name}' created successfully")
                            except Exception as create_error:
                                print(f"Failed to create Azure container: {create_error}")
                                raise create_error
                        
                        print("Azure Blob Storage initialized successfully")
                    else:
                        print("Azure Blob Storage configuration incomplete, falling back to local storage")
                        self.storage_type = 'local'
                        self.upload_folder = app.config.get('UPLOAD_FOLDER', 'uploads')
                        os.makedirs(self.upload_folder, exist_ok=True)
                except Exception as e:
                    print(f"Azure Blob Storage initialization failed: {e}, falling back to local storage")
                    self.storage_type = 'local'
                    self.upload_folder = app.config.get('UPLOAD_FOLDER', 'uploads')
                    os.makedirs(self.upload_folder, exist_ok=True)
        elif self.storage_type == 'minio':
            try:
                # Try to get MinIO settings from database first
                try:
                    from app import get_setting
                    minio_endpoint = get_setting('MINIO_ENDPOINT') or app.config.get('MINIO_ENDPOINT')
                    minio_access_key = get_setting('MINIO_ACCESS_KEY') or app.config.get('MINIO_ACCESS_KEY')
                    minio_secret_key = get_setting('MINIO_SECRET_KEY') or app.config.get('MINIO_SECRET_KEY')
                    minio_bucket = get_setting('MINIO_BUCKET') or app.config.get('MINIO_BUCKET', 'pandoorac-local')
                except:
                    # Fall back to app config if database not available
                    minio_endpoint = app.config.get('MINIO_ENDPOINT')
                    minio_access_key = app.config.get('MINIO_ACCESS_KEY')
                    minio_secret_key = app.config.get('MINIO_SECRET_KEY')
                    minio_bucket = app.config.get('MINIO_BUCKET', 'pandoorac-local')
                
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
                    
                    # Ensure bucket exists, create if it doesn't
                    try:
                        self.s3_client.head_bucket(Bucket=self.bucket_name)
                        print(f"MinIO bucket '{self.bucket_name}' exists")
                    except Exception as e:
                        print(f"MinIO bucket '{self.bucket_name}' does not exist, creating it...")
                        try:
                            self.s3_client.create_bucket(Bucket=self.bucket_name)
                            print(f"MinIO bucket '{self.bucket_name}' created successfully")
                        except Exception as create_error:
                            print(f"Failed to create MinIO bucket: {create_error}")
                            raise create_error
                    
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
        elif self.storage_type == 'azure':
            # Upload to Azure Blob Storage
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=filename
            )
            blob_client.upload_blob(file, overwrite=True)
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
        elif self.storage_type == 'azure':
            # Get file from Azure Blob Storage
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=filename
            )
            return blob_client.download_blob().readall()
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
        elif self.storage_type == 'azure':
            # Return Azure Blob Storage URL
            return f"https://{self.blob_service_client.account_name}.blob.core.windows.net/{self.container_name}/{filename}"
        else:  # minio
            return f"{current_app.config['S3_ENDPOINT_URL']}/{self.bucket_name}/{filename}"

    def delete_file(self, filename):
        """Delete a file from storage"""
        if self.storage_type == 'local':
            # Delete file from local filesystem
            file_path = os.path.join(self.upload_folder, filename)
            if os.path.exists(file_path):
                os.remove(file_path)
        elif self.storage_type == 'azure':
            # Delete file from Azure Blob Storage
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=filename
            )
            blob_client.delete_blob()
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
        elif self.storage_type == 'azure':
            # Ensure Azure container exists
            try:
                container_client = self.blob_service_client.get_container_client(self.container_name)
                container_client.get_container_properties()
            except Exception:
                self.blob_service_client.create_container(self.container_name)
        else:  # minio
            try:
                self.s3_client.head_bucket(Bucket=self.bucket_name)
            except Exception:
                self.s3_client.create_bucket(Bucket=self.bucket_name) 