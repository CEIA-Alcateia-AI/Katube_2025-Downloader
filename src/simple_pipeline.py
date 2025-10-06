"""
Simplified YouTube Audio Download Pipeline
Downloads YouTube videos/channels and saves to GCP bucket
"""
import os
import time
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging
from datetime import datetime

from .config import Config
from .youtube_downloader import YouTubeDownloader
from .youtube_scanner import YouTubeChannelScanner
from .gcp_uploader import GCPUploader

logger = logging.getLogger(__name__)

class SimpleDownloadPipeline:
    """
    Simplified pipeline for YouTube audio download and GCP bucket storage:
    1. Download audio from YouTube (video or channel)
    2. Save audio files to local storage
    3. Generate list of downloaded files for GCP upload
    4. Create summary text files with video/channel information
    """
    
    def __init__(self, 
                 output_base_dir: Optional[Path] = None,
                 youtube_api_key: Optional[str] = None,
                 gcp_project_id: str = "GCP_PROJECT_ID",
                 gcp_bucket_name: str = "GCP_BUCKET_NAME",
                 gcp_credentials_path: Optional[str] = None):
        
        # Set up directories
        self.output_base_dir = output_base_dir or Config.OUTPUT_DIR
        Config.create_directories()
        
        # Initialize components
        self.downloader = YouTubeDownloader()
        self.youtube_scanner = YouTubeChannelScanner(
            api_key=youtube_api_key or Config.YOUTUBE_API_KEY or '',
            base_dir=self.output_base_dir / "youtube_scans"
        )
        
        # Initialize GCP uploader
        self.gcp_uploader = GCPUploader(
            project_id=gcp_project_id,
            bucket_name=gcp_bucket_name,
            credentials_path=gcp_credentials_path
        )
        
        # Pipeline state
        self.current_session = None
        self.session_dir = None
        
    def create_session(self, session_name: Optional[str] = None) -> Path:
        """Create a new download session directory."""
        if session_name is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            session_name = f"download_session_{timestamp}"
        
        self.current_session = session_name
        self.session_dir = self.output_base_dir / session_name
        self.session_dir.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        subdirs = ['downloads', 'metadata']
        for subdir in subdirs:
            (self.session_dir / subdir).mkdir(exist_ok=True)
        
        logger.info(f"📁 Download session created: {self.current_session}")
        return self.session_dir
    
    def download_single_video(self, url: str, custom_filename: Optional[str] = None, immediate_upload: bool = True) -> Dict[str, Any]:
        """
        Download a single YouTube video with optional immediate upload to GCP.
        
        Args:
            url: YouTube video URL
            custom_filename: Optional custom filename
            immediate_upload: If True, uploads to GCP immediately and cleans up local files
            
        Returns:
            Dictionary with download results
        """
        logger.info(f"🎬 Downloading single video: {url}")
        
        if not self.session_dir:
            raise ValueError("No active session. Call create_session() first.")
        
        try:
            # Set download directory to session downloads folder
            self.downloader.output_dir = self.session_dir / 'downloads'
            
            # Get video info first
            video_info = self.downloader.get_video_info(url)
            video_title = video_info.get('title', 'Unknown')
            video_id = video_info.get('id', 'unknown')
            duration = video_info.get('duration', 0)
            
            logger.info(f"📹 Video: {video_title} (Duration: {duration}s)")
            
            # Download audio
            audio_path = self.downloader.download(url, custom_filename)
            
            # Create metadata file
            metadata = {
                'video_id': video_id,
                'title': video_title,
                'url': url,
                'duration': duration,
                'download_time': datetime.now().isoformat(),
                'audio_file': str(audio_path.name),
                'file_size': audio_path.stat().st_size if audio_path.exists() else 0
            }
            
            metadata_file = self.session_dir / 'metadata' / f"{video_id}_metadata.json"
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            
            result = {
                'success': True,
                'video_id': video_id,
                'title': video_title,
                'url': url,
                'audio_path': str(audio_path),
                'metadata_path': str(metadata_file),
                'file_size': metadata['file_size'],
                'duration': duration,
                'uploaded_to_gcp': False,
                'local_files_cleaned': False
            }
            
            # Immediate upload to GCP if enabled and available
            if immediate_upload and self.gcp_uploader.is_available():
                logger.info(f"⬆️ Uploading {video_title} to GCP...")
                
                # Upload audio file
                session_name = self.current_session or "unknown_session"
                audio_remote_path = f"youtube_downloads/{session_name}/downloads/{audio_path.name}"
                
                upload_result = self.gcp_uploader.upload_file(
                    local_path=audio_path,
                    remote_path=audio_remote_path,
                    metadata={
                        'video_id': video_id,
                        'title': video_title,
                        'duration': str(duration),
                        'session_name': session_name,
                        'upload_time': datetime.now().isoformat()
                    }
                )
                
                if upload_result.get('success', False):
                    # Upload metadata file
                    metadata_remote_path = f"youtube_downloads/{session_name}/metadata/{metadata_file.name}"
                    metadata_upload = self.gcp_uploader.upload_file(
                        local_path=metadata_file,
                        remote_path=metadata_remote_path
                    )
                    
                    if metadata_upload.get('success', False):
                        logger.info(f"✅ Uploaded {video_title} to GCP successfully")
                        result['uploaded_to_gcp'] = True
                        result['gcp_audio_url'] = upload_result.get('public_url')
                        result['gcp_metadata_url'] = metadata_upload.get('public_url')
                        
                        # Clean up local files after successful upload
                        try:
                            if audio_path.exists():
                                audio_path.unlink()
                                logger.info(f"🗑️ Cleaned up local audio: {audio_path.name}")
                            
                            if metadata_file.exists():
                                metadata_file.unlink()
                                logger.info(f"🗑️ Cleaned up local metadata: {metadata_file.name}")
                            
                            result['local_files_cleaned'] = True
                            
                        except Exception as cleanup_error:
                            logger.warning(f"⚠️ Failed to clean up local files: {cleanup_error}")
                    else:
                        logger.warning(f"⚠️ Failed to upload metadata for {video_title}")
                else:
                    logger.warning(f"⚠️ Failed to upload audio for {video_title}: {upload_result.get('error')}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Error downloading video {url}: {e}")
            return {
                'success': False,
                'url': url,
                'error': str(e)
            }
    
    def download_channel_videos(self, channel_url: str, max_videos: int = 2500, progress_callback=None) -> Dict[str, Any]:
        """
        Download all videos from a YouTube channel.
        
        Args:
            channel_url: YouTube channel URL
            max_videos: Maximum number of videos to download
            progress_callback: Optional callback for progress updates
            
        Returns:
            Dictionary with download results
        """
        logger.info(f"🔄 Downloading channel videos: {channel_url}")
        
        if not self.session_dir:
            raise ValueError("No active session. Call create_session() first.")
        
        try:
            # Scan channel for video URLs
            video_list_path = self.youtube_scanner.scan_channel(channel_url)
            if not video_list_path:
                return {
                    'success': False,
                    'error': 'Channel scan failed',
                    'downloaded_count': 0,
                    'failed_count': 0
                }
            
            # Get video URLs
            video_urls = self.youtube_scanner.get_video_urls(video_list_path)
            if not video_urls:
                return {
                    'success': False,
                    'error': 'No videos found in channel',
                    'downloaded_count': 0,
                    'failed_count': 0
                }
            
            # Limit number of videos
            if len(video_urls) > max_videos:
                video_urls = video_urls[:max_videos]
                logger.info(f"⚠️ Limited to first {max_videos} videos")
            
            # Download each video
            downloaded_videos = []
            failed_videos = []
            
            for i, video_url in enumerate(video_urls):
                try:
                    logger.info(f"📹 Downloading video {i+1}/{len(video_urls)}: {video_url}")
                    
                    # Download video with immediate upload
                    result = self.download_single_video(video_url, immediate_upload=True)
                    
                    if result['success']:
                        downloaded_videos.append(result)
                        logger.info(f"✅ Downloaded: {result['title']}")
                    else:
                        failed_videos.append(result)
                        logger.warning(f"❌ Failed: {video_url} - {result.get('error', 'Unknown error')}")
                    
                    # Update progress if callback provided
                    if progress_callback:
                        progress_callback(video_url, result['success'], len(video_urls), i+1)
                        
                except Exception as e:
                    logger.error(f"❌ Error downloading video {video_url}: {e}")
                    failed_videos.append({
                        'success': False,
                        'url': video_url,
                        'error': str(e)
                    })
                    
                    if progress_callback:
                        progress_callback(video_url, False, len(video_urls), i+1)
            
            # Create channel summary
            channel_summary = {
                'channel_url': channel_url,
                'scan_time': datetime.now().isoformat(),
                'total_videos_found': len(video_urls),
                'downloaded_count': len(downloaded_videos),
                'failed_count': len(failed_videos),
                'downloaded_videos': downloaded_videos,
                'failed_videos': failed_videos
            }
            
            summary_file = self.session_dir / 'metadata' / 'channel_summary.json'
            with open(summary_file, 'w', encoding='utf-8') as f:
                json.dump(channel_summary, f, indent=2, ensure_ascii=False)
            
            # Create video list text file
            video_list_file = self.session_dir / 'video_urls.txt'
            with open(video_list_file, 'w', encoding='utf-8') as f:
                f.write(f"Channel: {channel_url}\n")
                f.write(f"Scan Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Total Videos: {len(video_urls)}\n")
                f.write(f"Downloaded: {len(downloaded_videos)}\n")
                f.write(f"Failed: {len(failed_videos)}\n")
                f.write("\n=== DOWNLOADED VIDEOS ===\n")
                for video in downloaded_videos:
                    f.write(f"{video['url']} | {video['title']}\n")
                f.write("\n=== FAILED VIDEOS ===\n")
                for video in failed_videos:
                    f.write(f"{video['url']} | Error: {video.get('error', 'Unknown')}\n")
            
            return {
                'success': True,
                'channel_url': channel_url,
                'total_videos': len(video_urls),
                'downloaded_count': len(downloaded_videos),
                'failed_count': len(failed_videos),
                'summary_file': str(summary_file),
                'video_list_file': str(video_list_file),
                'downloaded_videos': downloaded_videos,
                'failed_videos': failed_videos
            }
            
        except Exception as e:
            logger.error(f"❌ Error downloading channel: {e}")
            return {
                'success': False,
                'error': str(e),
                'downloaded_count': 0,
                'failed_count': 0
            }
    
    def process_url(self, url: str, custom_filename: Optional[str] = None, max_videos: int = 2500, progress_callback=None) -> Dict[str, Any]:
        """
        Process a YouTube URL (video or channel).
        
        Args:
            url: YouTube URL (video or channel)
            custom_filename: Optional custom filename for single videos
            max_videos: Maximum videos to download from channels
            progress_callback: Optional progress callback
            
        Returns:
            Dictionary with processing results
        """
        start_time = time.time()
        
        logger.info("=== STARTING SIMPLE DOWNLOAD PIPELINE ===")
        logger.info(f"URL: {url}")
        
        try:
            # Create session
            session_dir = self.create_session()
            
            # Determine if it's a channel or single video
            is_channel = any(pattern in url.lower() for pattern in [
                '/channel/', '/c/', '/user/', '/@', '/playlist?'
            ])
            
            if is_channel:
                # Process channel
                result = self.download_channel_videos(url, max_videos, progress_callback)
                result['type'] = 'channel'
            else:
                # Process single video with immediate upload
                result = self.download_single_video(url, custom_filename, immediate_upload=True)
                result['type'] = 'video'
                # Wrap single video result in channel-like structure for consistency
                if result['success']:
                    result.update({
                        'downloaded_count': 1,
                        'failed_count': 0,
                        'total_videos': 1
                    })
                else:
                    result.update({
                        'downloaded_count': 0,
                        'failed_count': 1,
                        'total_videos': 1
                    })
            
            # Add session info
            processing_time = time.time() - start_time
            result.update({
                'session_name': self.current_session,
                'session_dir': str(session_dir),
                'processing_time': processing_time
            })
            
            # Save session results
            results_file = session_dir / 'download_results.json'
            with open(results_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False, default=str)
            
            logger.info("=== DOWNLOAD PIPELINE COMPLETED ===")
            logger.info(f"Processing time: {processing_time:.2f}s")
            logger.info(f"Results saved to: {results_file}")
            
            return result
            
        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'type': 'unknown',
                'downloaded_count': 0,
                'failed_count': 0
            }
    
    def get_download_summary(self) -> Dict[str, Any]:
        """
        Get summary of all files ready for GCP upload.
        
        Returns:
            Dictionary with file paths and metadata for GCP upload
        """
        if not self.session_dir:
            return {'error': 'No active session'}
        
        downloads_dir = self.session_dir / 'downloads'
        metadata_dir = self.session_dir / 'metadata'
        
        audio_files = []
        metadata_files = []
        
        # Collect audio files
        if downloads_dir.exists():
            for audio_file in downloads_dir.glob('*.flac'):
                audio_files.append({
                    'path': str(audio_file),
                    'name': audio_file.name,
                    'size': audio_file.stat().st_size,
                    'type': 'audio'
                })
        
        # Collect metadata files
        if metadata_dir.exists():
            for meta_file in metadata_dir.glob('*.json'):
                metadata_files.append({
                    'path': str(meta_file),
                    'name': meta_file.name,
                    'size': meta_file.stat().st_size,
                    'type': 'metadata'
                })
        
        # Include text files
        text_files = []
        for txt_file in self.session_dir.glob('*.txt'):
            text_files.append({
                'path': str(txt_file),
                'name': txt_file.name,
                'size': txt_file.stat().st_size,
                'type': 'text'
            })
        
        return {
            'session_dir': str(self.session_dir),
            'audio_files': audio_files,
            'metadata_files': metadata_files,
            'text_files': text_files,
            'total_files': len(audio_files) + len(metadata_files) + len(text_files),
            'total_audio_size': sum(f['size'] for f in audio_files),
            'ready_for_gcp_upload': True,
            'gcp_available': self.gcp_uploader.is_available()
        }
    
    def upload_to_gcp(self, upload_after_download: bool = True) -> Dict[str, Any]:
        """
        Upload session files to GCP bucket.
        
        Args:
            upload_after_download: Whether to upload immediately after download
            
        Returns:
            Dictionary with upload results
        """
        if not self.session_dir:
            return {'error': 'No active session'}
        
        if not self.gcp_uploader.is_available():
            return {
                'success': False,
                'error': 'GCP uploader not available. Check credentials and dependencies.',
                'uploaded_files': [],
                'failed_files': []
            }
        
        logger.info(f"🔄 Starting GCP upload for session: {self.current_session}")
        
        # Upload session files
        upload_result = self.gcp_uploader.upload_session_files(
            session_dir=self.session_dir,
            session_name=self.current_session,
            include_patterns=['*.flac', '*.json', '*.txt', '*.csv']
        )
        
        if upload_result['success']:
            logger.info(f"✅ GCP upload completed successfully!")
            logger.info(f"📊 Uploaded {upload_result['uploaded_count']}/{upload_result['total_files']} files")
            logger.info(f"🔗 Session URL: {upload_result['summary_url']}")
        else:
            logger.error(f"❌ GCP upload failed: {upload_result.get('error', 'Unknown error')}")
            logger.error(f"📊 Only {upload_result['uploaded_count']}/{upload_result['total_files']} files uploaded")
        
        return upload_result
    
    def get_gcp_bucket_info(self) -> Dict[str, Any]:
        """
        Get information about the GCP bucket.
        
        Returns:
            Dictionary with bucket information
        """
        return self.gcp_uploader.get_bucket_info()


# Example usage
if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    
    pipeline = SimpleDownloadPipeline()
    
    # Example: download a single video
    # result = pipeline.process_url("https://www.youtube.com/watch?v=example")
    
    # Example: download a channel
    # result = pipeline.process_url("https://www.youtube.com/@example")
    
    # print(f"Download results: {result}")
