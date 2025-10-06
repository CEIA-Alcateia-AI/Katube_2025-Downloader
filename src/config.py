"""
Configuration settings for the YouTube audio downloader.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    # Audio settings
    AUDIO_FORMAT = os.getenv('AUDIO_FORMAT', 'flac')
    AUDIO_QUALITY = os.getenv('AUDIO_QUALITY', 'best')
    SAMPLE_RATE = int(os.getenv('SAMPLE_RATE', '24000'))
    
    # YouTube API settings
    YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
    
    # Directories
    BASE_DIR = Path(__file__).parent.parent
    AUDIOS_BAIXADOS_DIR = Path(os.getenv('AUDIOS_BAIXADOS_DIR', r'C:\Users\Usuário\Desktop\katube-novo\audios_baixados'))
    OUTPUT_DIR = AUDIOS_BAIXADOS_DIR / "output"
    TEMP_DIR = AUDIOS_BAIXADOS_DIR / "temp"
    
    # YouTube download settings
    YOUTUBE_FORMAT = "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best/worst"
    
    @classmethod
    def create_directories(cls):
        """Create necessary directories."""
        for dir_path in [cls.OUTPUT_DIR, cls.TEMP_DIR]:
            dir_path.mkdir(parents=True, exist_ok=True)