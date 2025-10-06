"""
Warning suppression configuration for YouTube downloader
"""
import warnings
import logging

# Suppress general warnings
warnings.filterwarnings("ignore", message=".*pkg_resources is deprecated.*")

# Suppress YouTube-dl/yt-dlp warnings
warnings.filterwarnings("ignore", category=UserWarning, module="yt_dlp")

# Set logging level for specific modules
logging.getLogger("yt_dlp").setLevel(logging.WARNING)
logging.getLogger("googleapiclient").setLevel(logging.WARNING)