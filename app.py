#!/usr/bin/env python3
"""
Flask web interface for YouTube Audio Processing Pipeline
"""
# Suppress warnings first
from src.warning_suppression import *

import os
import sys
import json
import uuid
import threading
import time
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for
from werkzeug.utils import secure_filename
import logging

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from src.simple_pipeline import SimpleDownloadPipeline
from src.config import Config

app = Flask(__name__)
import secrets
app.secret_key = secrets.token_urlsafe(32)

# Global variables for job tracking
active_jobs = {}
job_lock = threading.Lock()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class JobStatus:
    def __init__(self, job_id: str, url: str):
        self.job_id = job_id
        self.url = url
        self.status = "waiting"  # waiting, downloading, segmenting, diarizing, separating, completed, failed
        self.progress = 0  # 0-100
        self.message = "Iniciando processamento..."
        self.start_time = datetime.now()
        self.end_time = None
        self.results = None
        self.error = None
        
    def update(self, status: str, progress: int, message: str):
        self.status = status
        self.progress = progress
        self.message = message
        logger.info(f"Job {self.job_id}: {status} - {progress}% - {message}")
        
    def complete(self, results: dict):
        self.status = "completed"
        self.progress = 100
        self.message = "Processamento concluído com sucesso!"
        self.end_time = datetime.now()
        self.results = results
        
    def fail(self, error: str):
        self.status = "failed"
        self.progress = 0
        self.message = f"Erro: {error}"
        self.end_time = datetime.now()
        self.error = error

def process_youtube_url_background(job_id: str, url: str, options: dict):
    """Background task to process YouTube URL"""
    job = active_jobs[job_id]
    
    try:
        # Create simplified pipeline
        pipeline = SimpleDownloadPipeline(
            output_base_dir=Config.OUTPUT_DIR,
            youtube_api_key=Config.YOUTUBE_API_KEY,
            gcp_bucket_name="dataset_youtube_katube"
        )
        
        # Update job status throughout the process
        job.update("downloading", 10, "Iniciando download...")
        
        # Create session
        session_name = options.get('session_name') or f"web_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        session_dir = pipeline.create_session(session_name)
        
        # Progress callback for downloads
        def progress_callback(video_url, success, total_videos, current_index):
            progress_percent = min(90, int((current_index / total_videos) * 80) + 10)
            video_id = video_url.split('watch?v=')[-1].split('&')[0] if 'watch?v=' in video_url else video_url[-11:]
            
            # Add more detailed status for immediate upload flow
            if success:
                status_msg = f"✅ Vídeo {current_index}/{total_videos} processado e enviado | ID: {video_id}"
            else:
                status_msg = f"⬇️ Baixando vídeo {current_index}/{total_videos} | ID: {video_id}"
                if current_index > 1:  # Add note about long videos after first video
                    status_msg += " (pode demorar para vídeos longos)"
            
            job.update("processing", progress_percent, status_msg)
        
        # Process URL (video or channel)
        result = pipeline.process_url(
            url=url,
            custom_filename=options.get('filename'),
            max_videos=options.get('max_videos', 2500),
            progress_callback=progress_callback
        )
        
        job.update("finalizing", 95, "Finalizando processamento...")
        
        # Get download summary 
        download_summary = pipeline.get_download_summary()
        result['download_summary'] = download_summary
        
        # Check if GCP was available for uploads
        if download_summary.get('gcp_available', False):
            # Count successful uploads from individual video results
            uploaded_count = 0
            total_processed = 0
            
            if result.get('type') == 'video':
                total_processed = 1
                if result.get('uploaded_to_gcp', False):
                    uploaded_count = 1
            else:
                # For channels, count from downloaded_videos
                downloaded_videos = result.get('downloaded_videos', [])
                total_processed = len(downloaded_videos)
                uploaded_count = sum(1 for video in downloaded_videos if video.get('uploaded_to_gcp', False))
            
            if uploaded_count == total_processed:
                job.update("completed", 100, f"✅ Processamento concluído! {uploaded_count} arquivos enviados para GCP.")
            elif uploaded_count > 0:
                job.update("completed", 100, f"⚠️ Processamento concluído! {uploaded_count}/{total_processed} arquivos enviados para GCP.")
            else:
                job.update("completed", 100, f"⚠️ Processamento concluído, mas uploads GCP falharam. Arquivos salvos localmente.")
        else:
            job.update("completed", 100, "Processamento concluído! GCP não configurado - arquivos salvos localmente.")
        
        job.complete(result)
        
    except Exception as e:
        logger.error(f"Background job {job_id} failed: {e}")
        job.fail(str(e))

@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')

@app.route('/process_channel', methods=['POST'])
def process_channel():
    """Process entire YouTube channel."""
    try:
        data = request.get_json()
        channel_url = data.get('channelUrl') or data.get('channel_url')
        
        # Validate URL (accept both channel and video URLs)
        if not channel_url:
            return jsonify({'error': 'URL is required'}), 400
        
        # Check if it's a channel URL or video URL
        is_channel = any(pattern in channel_url.lower() for pattern in [
            '/channel/', '/c/', '/user/', '/@', '/playlist?'
        ])
        
        if not is_channel and 'youtube.com/watch' not in channel_url.lower() and 'youtu.be/' not in channel_url.lower():
            return jsonify({'error': 'Please provide a valid YouTube channel or video URL'}), 400
        
        # Generate job ID
        job_id = str(uuid.uuid4())
        
        # Start background job using threading
        job_thread = threading.Thread(
            target=process_channel_background,
            args=(job_id, channel_url)
        )
        job_thread.daemon = True
        job_thread.start()
        
        # Store job status
        with job_lock:
            active_jobs[job_id] = JobStatus(job_id, channel_url)
        
        return jsonify({
            'job_id': job_id,
            'status': 'started',
            'message': 'Channel processing started'
        })
        
    except Exception as e:
        logger.error(f"Error starting channel processing: {e}")
        return jsonify({'error': str(e)}), 500

def process_channel_background(job_id, url):
    """Background job to process YouTube channel or single video."""
    try:
        logger.info(f"🔄 Starting processing: {url}")
        
        # Check if it's a channel URL or video URL
        is_channel = any(pattern in url.lower() for pattern in [
            '/channel/', '/c/', '/user/', '/@', '/playlist?'
        ])
        
        # Update job status
        with job_lock:
            if job_id in active_jobs:
                if is_channel:
                    active_jobs[job_id].update('downloading', 10, 'Iniciando processamento do canal...')
                else:
                    active_jobs[job_id].update('downloading', 10, 'Iniciando processamento do vídeo...')
        
        # Initialize simplified pipeline
        pipeline = SimpleDownloadPipeline(
            output_base_dir=Config.OUTPUT_DIR,
            youtube_api_key=Config.YOUTUBE_API_KEY,
            gcp_bucket_name="dataset_youtube_katube"
        )
        
        processed_count = 0
        failed_count = 0
        
        def progress_callback(video_url, success, total_videos, current_index):
            """Update progress for each video processed."""
            nonlocal processed_count, failed_count
            
            with job_lock:
                if job_id in active_jobs:
                    job = active_jobs[job_id]
                    
                    # Always count as processed (success) since we're processing all videos
                    processed_count += 1
                    
                    # Extract video ID for display
                    video_id = video_url.split('watch?v=')[-1].split('&')[0] if 'watch?v=' in video_url else video_url[-11:]
                    
                    # Show progress as "Video X of Y" format
                    status = f"📹 Vídeo {current_index}/{total_videos} processado"
                    
                    # Calculate progress percentage based on actual total
                    progress_percent = min(90, int((current_index / total_videos) * 90))
                    
                    job.update('processing', progress_percent, 
                             f'Processando canal... {status} | ID: {video_id}')
        
        # Process URL (video or channel)
        result = pipeline.process_url(
            url=url,
            max_videos=2500,
            progress_callback=progress_callback
        )
        
        # Check final upload status (uploads already happened individually)
        if result.get('success', False):
            download_summary = pipeline.get_download_summary()
            
            if download_summary.get('gcp_available', False):
                with job_lock:
                    if job_id in active_jobs:
                        active_jobs[job_id].update('finalizing', 95, 'Finalizando uploads para GCP...')
                
                # Count successful uploads from individual results
                downloaded_videos = result.get('downloaded_videos', [])
                uploaded_count = sum(1 for video in downloaded_videos if video.get('uploaded_to_gcp', False))
                total_count = len(downloaded_videos)
                
                # Create upload summary for compatibility
                upload_result = {
                    'success': uploaded_count > 0,
                    'uploaded_count': uploaded_count,
                    'total_files': total_count,
                    'failed_count': total_count - uploaded_count
                }
                result['gcp_upload'] = upload_result
            
            # Update final job status
            with job_lock:
                if job_id in active_jobs:
                    if result.get('success', False):
                        gcp_upload = result.get('gcp_upload', {})
                        
                        if result.get('type') == 'channel':
                            total_videos = result.get('total_videos', 0)
                            downloaded = result.get('downloaded_count', 0)
                            
                            if gcp_upload.get('success', False):
                                active_jobs[job_id].update('completed', 100, f'✅ Canal processado e enviado para GCP! {downloaded}/{total_videos} vídeos')
                            else:
                                active_jobs[job_id].update('completed', 100, f'✅ Canal processado! {downloaded}/{total_videos} vídeos (GCP: {gcp_upload.get("error", "não configurado")})')
                        else:
                            if gcp_upload.get('success', False):
                                active_jobs[job_id].update('completed', 100, f'✅ Vídeo baixado e enviado para GCP!')
                            else:
                                active_jobs[job_id].update('completed', 100, f'✅ Vídeo baixado! (GCP: {gcp_upload.get("error", "não configurado")})')
                    else:
                        active_jobs[job_id].update('failed', 0, f'❌ Erro: {result.get("error", "Erro desconhecido")}')
                    active_jobs[job_id].results = result
            
        logger.info(f"✅ Processing complete: {result}")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Channel processing failed: {e}")
        
        # Update job status with error
        with job_lock:
            if job_id in active_jobs:
                active_jobs[job_id].update('failed', 0, f'Erro: {str(e)}')
                active_jobs[job_id].error = str(e)
        
        return {'success': False, 'error': str(e)}

@app.route('/process', methods=['POST'])
def process_url():
    """Start processing a YouTube URL"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        
        if not url:
            return jsonify({'error': 'URL é obrigatória'}), 400
        
        # Validate YouTube URL
        if 'youtube.com/watch' not in url and 'youtu.be/' not in url:
            return jsonify({'error': 'URL inválida. Use uma URL válida do YouTube.'}), 400
        
        # Create job
        job_id = str(uuid.uuid4())
        
        # Get options from request
        options = {
            'filename': data.get('filename'),
            'num_speakers': data.get('num_speakers'),
            'min_duration': data.get('min_duration', 10.0),
            'max_duration': data.get('max_duration', 15.0),
            'enhance_audio': data.get('enhance_audio', True),
            'intelligent_segmentation': data.get('intelligent_segmentation', True),
            'session_name': data.get('session_name')
        }
        
        # Create job status
        with job_lock:
            active_jobs[job_id] = JobStatus(job_id, url)
        
        # Start background processing
        thread = threading.Thread(
            target=process_youtube_url_background,
            args=(job_id, url, options),
            daemon=True
        )
        thread.start()
        
        return jsonify({'job_id': job_id})
        
    except Exception as e:
        logger.error(f"Process URL error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/status/<job_id>')
def get_status(job_id):
    """Get job status"""
    try:
        with job_lock:
            job = active_jobs.get(job_id)
            
            if not job:
                return jsonify({'error': 'Job não encontrado'}), 404
            
            return jsonify({
                'job_id': job.job_id,
                'status': job.status,
                'progress': job.progress,
                'message': job.message,
                'start_time': job.start_time.isoformat(),
                'end_time': job.end_time.isoformat() if job.end_time else None,
                'error': job.error
            })
    except Exception as e:
        logger.error(f"Error getting job status {job_id}: {e}")
        return jsonify({'error': 'Erro interno do servidor'}), 500

@app.route('/result/<job_id>')
def get_result(job_id):
    """Get job results"""
    with job_lock:
        job = active_jobs.get(job_id)
        
        if not job:
            return jsonify({'error': 'Job não encontrado'}), 404
        
        if job.status != 'completed':
            return jsonify({'error': 'Job ainda não foi concluído'}), 400
        
        # Clean results for JSON serialization
        def clean_for_json(obj):
            if isinstance(obj, dict):
                return {k: clean_for_json(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [clean_for_json(item) for item in obj]
            elif hasattr(obj, '__module__') and 'pyannote' in str(obj.__module__):
                return f"pyannote.{obj.__class__.__name__}"  # Handle pyannote objects
            elif hasattr(obj, '__dict__'):
                return str(obj)  # Convert complex objects to string
            elif isinstance(obj, (str, int, float, bool, type(None))):
                return obj
            elif hasattr(obj, '__class__'):
                return f"{obj.__class__.__module__}.{obj.__class__.__name__}"  # Better class representation
            else:
                return str(obj)  # Convert anything else to string
        
        # Extract GCP upload data separately for better frontend handling
        results = clean_for_json(job.results) if job.results else {}
        gcp_upload = results.get('gcp_upload', {})
        
        return jsonify({
            'job_id': job.job_id,
            'status': job.status,
            'results': results,
            'gcp_upload': gcp_upload,
            'processing_time': (job.end_time - job.start_time).total_seconds() if job.end_time and job.start_time else 0
        })

@app.route('/results/<job_id>')
def results_page(job_id):
    """Results page"""
    with job_lock:
        job = active_jobs.get(job_id)
        
        if not job:
            return "Job não encontrado", 404
            
    return render_template('result.html', job_id=job_id)

@app.route('/download/<job_id>/<path:file_type>')
def download_file(job_id, file_type):
    """Download processed files"""
    with job_lock:
        job = active_jobs.get(job_id)
        
        if not job or job.status != 'completed':
            return "Arquivo não disponível", 404
        
        session_dir = Path(job.results['session_dir'])
        
        try:
            if file_type == 'results.json':
                file_path = session_dir / 'pipeline_results.json'
                return send_file(file_path, as_attachment=True, download_name=f'results_{job_id}.json')
            
            elif file_type.startswith('speaker_'):
                # Download specific speaker files as ZIP
                import zipfile
                import tempfile
                
                speaker_id = file_type.replace('speaker_', '')
                speaker_dir = session_dir / 'stt_ready' / f'speaker_{speaker_id}'
                
                if not speaker_dir.exists():
                    return "Speaker não encontrado", 404
                
                # Create temporary ZIP file
                temp_zip = tempfile.mktemp(suffix='.zip')
                
                with zipfile.ZipFile(temp_zip, 'w') as zipf:
                    for file_path in speaker_dir.glob('*'):
                        if file_path.is_file():
                            zipf.write(file_path, file_path.name)
                
                return send_file(temp_zip, as_attachment=True, download_name=f'speaker_{speaker_id}_{job_id}.zip')
            
            else:
                return "Tipo de arquivo inválido", 400
                
        except Exception as e:
            logger.error(f"Download error: {e}")
            return "Erro no download", 500

@app.route('/cleanup/<job_id>', methods=['POST'])
def cleanup_job(job_id):
    """Clean up job data"""
    with job_lock:
        if job_id in active_jobs:
            del active_jobs[job_id]
    
    return jsonify({'message': 'Job removido'})

@app.route('/jobs')
def list_jobs():
    """List all active jobs (for debugging)"""
    with job_lock:
        jobs_info = []
        for job_id, job in active_jobs.items():
            jobs_info.append({
                'job_id': job_id,
                'status': job.status,
                'progress': job.progress,
                'url': job.url,
                'start_time': job.start_time.isoformat()
            })
    
    return jsonify(jobs_info)

if __name__ == '__main__':
    
    # Ensure directories exist
    Config.create_directories()
    
    # Create additional directories
    Config.AUDIOS_BAIXADOS_DIR.mkdir(parents=True, exist_ok=True)
    
    print("🚀 YouTube Audio Downloader - Simplified Pipeline")
    print("============================================================")
    print("📁 Download local - Arquivos prontos para GCP bucket")
    print("🎯 Aceita: Canais YouTube OU vídeos individuais")
    print("🔍 Pipeline Simplificada: Download → Metadata → Lista de URLs")
    print("🌐 Acesse: http://localhost:5000")
    print("============================================================")
    print()
    print("Recursos disponíveis:")
    print("• Download direto do YouTube em FLAC 24kHz Mono")
    print("• Escaneamento completo de canais YouTube")
    print("• Geração de metadata JSON para cada vídeo")
    print("• Lista de URLs em arquivo .txt")
    print("• Arquivos organizados por sessão")
    print("• Prontos para upload no GCP bucket")
    print("• Interface web simples e intuitiva")
    print()
    print("Saídas geradas:")
    print("• /downloads/ - Arquivos de áudio FLAC")
    print("• /metadata/ - Arquivos JSON com informações dos vídeos")
    print("• video_urls.txt - Lista de URLs processadas")
    print("• download_results.json - Resumo da sessão")
    print()
    print("Pressione Ctrl+C para parar o servidor")
    print("============================================================")
    
    # Para desenvolvimento local, descomente a linha abaixo:
    # app.run(debug=False, host='0.0.0.0', port=5000)
    
    # Para produção no Windows, use: waitress-serve --host=0.0.0.0 --port=5000 app:app
    # Para produção no Linux, use: gunicorn -w 1 -b 0.0.0.0:5000 app:app
