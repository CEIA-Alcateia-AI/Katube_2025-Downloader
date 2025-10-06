"""
Google Cloud Storage uploader for YouTube audio files
"""
import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

try:
    from google.cloud import storage
    from google.oauth2 import service_account
    GCP_AVAILABLE = True
except ImportError:
    storage = None
    service_account = None
    GCP_AVAILABLE = False

logger = logging.getLogger(__name__)

class GCPUploader:
    """
    Google Cloud Storage uploader for audio files and metadata
    """
    
    def __init__(self, 
                 project_id: str = "GCP_PROJECT_ID",
                 bucket_name: str = "GCP_BUCKET_NAME",
                 credentials_path: Optional[str] = None):
        """
        Initialize GCP uploader.
        
        Args:
            project_id: GCP project ID
            bucket_name: GCS bucket name
            credentials_path: Path to service account JSON file
        """
        self.project_id = project_id
        self.bucket_name = bucket_name
        self.credentials_path = credentials_path
        self.client = None
        self.bucket = None
        
        if not GCP_AVAILABLE:
            logger.warning("⚠️ Google Cloud Storage libraries not available. Install with: pip install google-cloud-storage")
            return
        
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize GCS client with credentials."""
        try:
            # Always try to use the credentials file first
            credentials_file = "gcp_credentials.json"
            if Path(credentials_file).exists():
                # Use service account credentials from local file
                credentials = service_account.Credentials.from_service_account_file(
                    credentials_file
                )
                self.client = storage.Client(
                    project=self.project_id,
                    credentials=credentials
                )
                logger.info(f"✅ GCS client initialized with service account: {credentials_file}")
            elif self.credentials_path and Path(self.credentials_path).exists():
                # Use service account file from specified path
                credentials = service_account.Credentials.from_service_account_file(
                    self.credentials_path
                )
                self.client = storage.Client(
                    project=self.project_id,
                    credentials=credentials
                )
                logger.info(f"✅ GCS client initialized with service account: {self.credentials_path}")
            else:
                # Use default credentials (environment variable or gcloud auth)
                self.client = storage.Client(project=self.project_id)
                logger.info(f"✅ GCS client initialized with default credentials")
            
            # Get bucket
            self.bucket = self.client.bucket(self.bucket_name)
            logger.info(f"✅ Connected to bucket: {self.bucket_name}")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize GCS client: {e}")
            self.client = None
            self.bucket = None
    
    def is_available(self) -> bool:
        """Check if GCP uploader is available and configured."""
        return GCP_AVAILABLE and self.client is not None and self.bucket is not None
    
    def upload_file(self, 
                   local_path: Path, 
                   remote_path: str,
                   metadata: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Upload a single file to GCS.
        
        Args:
            local_path: Local file path
            remote_path: Remote path in bucket
            metadata: Optional metadata to attach to file
            
        Returns:
            Dictionary with upload results
        """
        if not self.is_available():
            return {
                'success': False,
                'error': 'GCP uploader not available'
            }
        
        if not local_path.exists():
            return {
                'success': False,
                'error': f'Local file not found: {local_path}'
            }
        
        try:
            # Create blob
            blob = self.bucket.blob(remote_path)
            
            # Set metadata if provided
            if metadata:
                blob.metadata = metadata
            
            # Upload file
            blob.upload_from_filename(str(local_path))
            
            logger.info(f"✅ Uploaded: {local_path.name} → gs://{self.bucket_name}/{remote_path}")
            
            return {
                'success': True,
                'local_path': str(local_path),
                'remote_path': remote_path,
                'bucket': self.bucket_name,
                'size': local_path.stat().st_size,
                'public_url': f"gs://{self.bucket_name}/{remote_path}"
            }
            
        except Exception as e:
            logger.error(f"❌ Upload failed: {local_path.name} - {e}")
            return {
                'success': False,
                'error': str(e),
                'local_path': str(local_path),
                'remote_path': remote_path
            }
    
    def upload_session_files(self, 
                           session_dir: Path,
                           session_name: str,
                           include_patterns: List[str] = None) -> Dict[str, Any]:
        """
        Upload all files from a download session to GCS.
        
        Args:
            session_dir: Local session directory
            session_name: Session name for organizing in bucket
            include_patterns: File patterns to include (default: all)
            
        Returns:
            Dictionary with upload results
        """
        if not self.is_available():
            return {
                'success': False,
                'error': 'GCP uploader not available',
                'uploaded_files': [],
                'failed_files': []
            }
        
        if not session_dir.exists():
            return {
                'success': False,
                'error': f'Session directory not found: {session_dir}',
                'uploaded_files': [],
                'failed_files': []
            }
        
        # Default patterns to include all common files
        if include_patterns is None:
            include_patterns = ['*.flac', '*.json', '*.txt', '*.csv']
        
        uploaded_files = []
        failed_files = []
        
        logger.info(f"🔄 Starting upload of session: {session_name}")
        
        # Create session folder structure in bucket
        session_prefix = f"youtube_downloads/{session_name}"
        
        # Upload files by category
        categories = {
            'downloads': session_dir / 'downloads',
            'metadata': session_dir / 'metadata'
        }
        
        # Also include root files
        root_files = []
        for pattern in include_patterns:
            root_files.extend(session_dir.glob(pattern))
        
        if root_files:
            categories['root'] = session_dir
        
        for category, category_dir in categories.items():
            if not category_dir.exists():
                continue
            
            logger.info(f"📁 Uploading {category} files...")
            
            if category == 'root':
                # Handle root files specially
                files_to_upload = root_files
            else:
                # Get all files matching patterns in subdirectory
                files_to_upload = []
                for pattern in include_patterns:
                    files_to_upload.extend(category_dir.glob(pattern))
            
            for file_path in files_to_upload:
                if file_path.is_file():
                    # Create remote path
                    if category == 'root':
                        remote_path = f"{session_prefix}/{file_path.name}"
                    else:
                        remote_path = f"{session_prefix}/{category}/{file_path.name}"
                    
                    # Create metadata
                    metadata = {
                        'session_name': session_name,
                        'category': category,
                        'upload_time': datetime.now().isoformat(),
                        'original_path': str(file_path.relative_to(session_dir))
                    }
                    
                    # Upload file
                    result = self.upload_file(file_path, remote_path, metadata)
                    
                    if result['success']:
                        uploaded_files.append(result)
                    else:
                        failed_files.append(result)
        
        # Upload summary
        total_files = len(uploaded_files) + len(failed_files)
        success_rate = len(uploaded_files) / total_files if total_files > 0 else 0
        
        # Create upload summary
        upload_summary = {
            'session_name': session_name,
            'upload_time': datetime.now().isoformat(),
            'total_files': total_files,
            'uploaded_count': len(uploaded_files),
            'failed_count': len(failed_files),
            'success_rate': success_rate,
            'bucket': self.bucket_name,
            'session_prefix': session_prefix,
            'uploaded_files': uploaded_files,
            'failed_files': failed_files
        }
        
        # Save upload summary to bucket
        summary_path = f"{session_prefix}/upload_summary.json"
        summary_blob = self.bucket.blob(summary_path)
        summary_blob.upload_from_string(
            json.dumps(upload_summary, indent=2, ensure_ascii=False),
            content_type='application/json'
        )
        
        logger.info(f"✅ Session upload complete: {len(uploaded_files)}/{total_files} files uploaded")
        logger.info(f"📊 Upload summary saved: gs://{self.bucket_name}/{summary_path}")
        
        return {
            'success': len(failed_files) == 0,
            'session_name': session_name,
            'bucket': self.bucket_name,
            'session_prefix': session_prefix,
            'total_files': total_files,
            'uploaded_count': len(uploaded_files),
            'failed_count': len(failed_files),
            'success_rate': success_rate,
            'uploaded_files': uploaded_files,
            'failed_files': failed_files,
            'summary_url': f"gs://{self.bucket_name}/{summary_path}"
        }
    
    def list_session_files(self, session_name: str) -> List[Dict[str, Any]]:
        """
        List files for a specific session in the bucket.
        
        Args:
            session_name: Session name to list files for
            
        Returns:
            List of file information dictionaries
        """
        if not self.is_available():
            return []
        
        session_prefix = f"youtube_downloads/{session_name}/"
        
        try:
            blobs = self.client.list_blobs(self.bucket, prefix=session_prefix)
            
            files = []
            for blob in blobs:
                files.append({
                    'name': blob.name,
                    'size': blob.size,
                    'created': blob.time_created.isoformat() if blob.time_created else None,
                    'updated': blob.updated.isoformat() if blob.updated else None,
                    'content_type': blob.content_type,
                    'metadata': blob.metadata or {},
                    'public_url': f"gs://{self.bucket_name}/{blob.name}"
                })
            
            return files
            
        except Exception as e:
            logger.error(f"❌ Failed to list session files: {e}")
            return []
    
    def get_bucket_info(self) -> Dict[str, Any]:
        """
        Get information about the configured bucket.
        
        Returns:
            Dictionary with bucket information
        """
        if not self.is_available():
            return {
                'available': False,
                'error': 'GCP uploader not available'
            }
        
        try:
            # Refresh bucket info
            self.bucket.reload()
            
            return {
                'available': True,
                'project_id': self.project_id,
                'bucket_name': self.bucket_name,
                'location': self.bucket.location,
                'storage_class': self.bucket.storage_class,
                'created': self.bucket.time_created.isoformat() if self.bucket.time_created else None,
                'public_url': f"gs://{self.bucket_name}/"
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to get bucket info: {e}")
            return {
                'available': False,
                'error': str(e)
            }


# Example usage
if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    
    uploader = GCPUploader()
    
    if uploader.is_available():
        bucket_info = uploader.get_bucket_info()
        print(f"Bucket info: {bucket_info}")
    else:
        print("GCP uploader not available")
