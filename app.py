"""
YouTube Video Downloader - Flask Backend
Features: Multi-quality download, video preview, dynamic retention policy
"""

import os
import re
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import yt_dlp
from flask import Flask, jsonify, render_template, request, send_file

# =============================================================================
# Configuration
# =============================================================================

BASE_DIR = Path(__file__).parent.resolve()
DOWNLOADED_DIR = BASE_DIR / "downloaded"
CONVERTED_DIR = BASE_DIR / "converted"
DATABASE_PATH = BASE_DIR / "downloads.db"
COOKIES_PATH = BASE_DIR / "cookies.txt"

# Ensure directories exist
DOWNLOADED_DIR.mkdir(exist_ok=True)
CONVERTED_DIR.mkdir(exist_ok=True)

# Thread pool for background downloads
executor = ThreadPoolExecutor(max_workers=3)

# In-memory task status tracking
tasks = {}

# =============================================================================
# Flask App
# =============================================================================

app = Flask(__name__)

# =============================================================================
# Database Functions
# =============================================================================

def init_db():
    """Initialize SQLite database with downloads table."""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS downloads (
            id TEXT PRIMARY KEY,
            video_id TEXT,
            title TEXT,
            filepath TEXT,
            duration_seconds INTEGER,
            expiry_timestamp REAL,
            format_info TEXT,
            status TEXT,
            created_at REAL
        )
    ''')
    conn.commit()
    conn.close()

def save_download_record(task_id, video_id, title, filepath, duration_seconds, format_info):
    """Save download record with calculated expiry."""
    expiry_seconds = calculate_expiry(duration_seconds)
    expiry_timestamp = time.time() + expiry_seconds
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO downloads 
        (id, video_id, title, filepath, duration_seconds, expiry_timestamp, format_info, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (task_id, video_id, title, filepath, duration_seconds, expiry_timestamp, format_info, 'ready', time.time()))
    conn.commit()
    conn.close()
    
    return expiry_timestamp

def get_download_record(task_id):
    """Get download record by task ID."""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM downloads WHERE id = ?', (task_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            'id': row[0],
            'video_id': row[1],
            'title': row[2],
            'filepath': row[3],
            'duration_seconds': row[4],
            'expiry_timestamp': row[5],
            'format_info': row[6],
            'status': row[7],
            'created_at': row[8]
        }
    return None

# =============================================================================
# Utility Functions
# =============================================================================

def calculate_expiry(duration_seconds):
    """
    Calculate retention time: MAX(2 hours, video duration)
    Returns expiry in seconds.
    """
    two_hours = 2 * 60 * 60  # 7200 seconds
    return max(two_hours, duration_seconds)

def extract_video_id(url):
    """Extract YouTube video ID from various URL formats."""
    patterns = [
        r'(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'(?:embed/)([a-zA-Z0-9_-]{11})',
        r'(?:shorts/)([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def get_yt_dlp_opts(cookies=True):
    """Get base yt-dlp options."""
    opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'noplaylist': True,  # Only download single video, not playlist
        'ffmpeg_location': '/usr/bin',  # Explicit path to ffmpeg/ffprobe
    }
    if cookies and COOKIES_PATH.exists():
        opts['cookiefile'] = str(COOKIES_PATH)
    return opts

def clean_youtube_url(url):
    """Clean YouTube URL by removing playlist and extra parameters."""
    video_id = extract_video_id(url)
    if video_id:
        return f'https://www.youtube.com/watch?v={video_id}'
    return url

def format_duration(seconds):
    """Format duration in human-readable format."""
    if not seconds:
        return "Unknown"
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"

# =============================================================================
# Video Info & Format Extraction
# =============================================================================

def fetch_video_info(url):
    """Fetch video info and available formats from YouTube."""
    opts = get_yt_dlp_opts()
    opts['skip_download'] = True
    
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    
    # Extract available video qualities
    formats = info.get('formats', [])
    
    # Group formats by resolution
    video_formats = {}
    audio_formats = []
    
    for fmt in formats:
        # Skip formats without proper info
        if not fmt.get('format_id'):
            continue
        
        height = fmt.get('height')
        vcodec = fmt.get('vcodec', 'none')
        acodec = fmt.get('acodec', 'none')
        ext = fmt.get('ext', 'unknown')
        filesize = fmt.get('filesize') or fmt.get('filesize_approx') or 0
        
        # Video formats (with video codec)
        if height and vcodec != 'none':
            quality_label = f"{height}p"
            if quality_label not in video_formats:
                video_formats[quality_label] = {
                    'height': height,
                    'formats': []
                }
            video_formats[quality_label]['formats'].append({
                'format_id': fmt.get('format_id'),
                'ext': ext,
                'vcodec': vcodec,
                'acodec': acodec,
                'filesize': filesize,
                'fps': fmt.get('fps', 30),
                'tbr': fmt.get('tbr', 0),  # Total bitrate
            })
        
        # Audio-only formats
        elif acodec != 'none' and vcodec == 'none':
            audio_formats.append({
                'format_id': fmt.get('format_id'),
                'ext': ext,
                'acodec': acodec,
                'abr': fmt.get('abr', 0),  # Audio bitrate
                'filesize': filesize,
            })
    
    # Sort video qualities by height (descending)
    sorted_qualities = sorted(video_formats.keys(), key=lambda x: int(x.replace('p', '')), reverse=True)
    
    # Sort audio by bitrate (descending)
    audio_formats.sort(key=lambda x: x.get('abr', 0), reverse=True)
    
    return {
        'video_id': info.get('id'),
        'title': info.get('title'),
        'thumbnail': info.get('thumbnail'),
        'duration': info.get('duration'),
        'duration_formatted': format_duration(info.get('duration')),
        'channel': info.get('channel') or info.get('uploader'),
        'view_count': info.get('view_count'),
        'qualities': sorted_qualities,
        'video_formats': video_formats,
        'audio_formats': audio_formats[:5],  # Top 5 audio formats
    }

# =============================================================================
# Download Functions
# =============================================================================

def download_video(task_id, url, quality, format_type):
    """
    Background download task.
    quality: e.g., "720p", "1080p", "best"
    format_type: "video+audio", "video", "audio_mp3", "audio_m4a"
    """
    try:
        tasks[task_id]['status'] = 'downloading'
        tasks[task_id]['progress'] = 0
        
        # Parse quality
        height = None
        if quality and quality != 'best':
            height = int(quality.replace('p', ''))
        
        # Prepare output template
        output_template = str(DOWNLOADED_DIR / f"{task_id}_%(title)s.%(ext)s")
        final_output = str(CONVERTED_DIR / f"{task_id}.%(ext)s")
        
        # Build format selector based on format_type
        if format_type == 'audio_mp3':
            format_selector = 'bestaudio/best'
            postprocessors = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            }]
            final_ext = 'mp3'
        elif format_type == 'audio_m4a':
            format_selector = 'bestaudio[ext=m4a]/bestaudio/best'
            postprocessors = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'm4a',
                'preferredquality': '256',
            }]
            final_ext = 'm4a'
        elif format_type == 'video':
            # Video only, no audio
            if height:
                format_selector = f'bestvideo[height<={height}]/bestvideo/best'
            else:
                format_selector = 'bestvideo/best'
            postprocessors = []
            final_ext = 'mp4'
        else:
            # video+audio (default)
            if height:
                format_selector = f'bestvideo[height<={height}]+bestaudio/best[height<={height}]/best'
            else:
                format_selector = 'bestvideo+bestaudio/best'
            postprocessors = [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }]
            final_ext = 'mp4'
        
        # Progress hook
        def progress_hook(d):
            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                downloaded = d.get('downloaded_bytes', 0)
                if total > 0:
                    tasks[task_id]['progress'] = int((downloaded / total) * 100)
            elif d['status'] == 'finished':
                tasks[task_id]['status'] = 'converting'
                tasks[task_id]['progress'] = 100
        
        # yt-dlp options
        ydl_opts = get_yt_dlp_opts()
        ydl_opts.update({
            'format': format_selector,
            'outtmpl': output_template,
            'progress_hooks': [progress_hook],
            'postprocessors': postprocessors,
            'merge_output_format': 'mp4' if format_type in ['video+audio', 'video'] else None,
            'keepvideo': False,
        })
        
        # Download
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
        
        # Find the downloaded file and move to converted
        tasks[task_id]['status'] = 'converting'
        
        # Look for the output file
        downloaded_files = list(DOWNLOADED_DIR.glob(f"{task_id}_*"))
        if not downloaded_files:
            raise Exception("Downloaded file not found")
        
        source_file = downloaded_files[0]
        
        # Determine final filename
        safe_title = re.sub(r'[^\w\s-]', '', info.get('title', 'video'))[:50]
        final_filename = f"{task_id}_{safe_title}.{final_ext}"
        final_path = CONVERTED_DIR / final_filename
        
        # Move file to converted directory
        import shutil
        shutil.move(str(source_file), str(final_path))
        
        # Clean up any remaining files in downloaded
        for f in DOWNLOADED_DIR.glob(f"{task_id}_*"):
            f.unlink()
        
        # Save to database
        duration = info.get('duration', 0)
        expiry_timestamp = save_download_record(
            task_id=task_id,
            video_id=info.get('id'),
            title=info.get('title'),
            filepath=str(final_path),
            duration_seconds=duration,
            format_info=f"{quality}_{format_type}"
        )
        
        # Update task status
        tasks[task_id]['status'] = 'ready'
        tasks[task_id]['filepath'] = str(final_path)
        tasks[task_id]['filename'] = final_filename
        tasks[task_id]['expiry'] = expiry_timestamp
        tasks[task_id]['title'] = info.get('title')
        
    except Exception as e:
        tasks[task_id]['status'] = 'error'
        tasks[task_id]['error'] = str(e)

# =============================================================================
# Routes
# =============================================================================

@app.route('/')
def index():
    """Render the main page."""
    return render_template('index.html')

@app.route('/info', methods=['POST'])
def get_video_info():
    """Fetch video information and available formats."""
    data = request.get_json()
    url = data.get('url', '').strip()
    
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    
    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({'error': 'Invalid YouTube URL'}), 400
    
    # Clean URL to remove playlist parameters
    clean_url = clean_youtube_url(url)
    
    try:
        info = fetch_video_info(clean_url)
        return jsonify(info)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download', methods=['POST'])
def start_download():
    """Start a download task."""
    data = request.get_json()
    url = data.get('url', '').strip()
    quality = data.get('quality', 'best')
    format_type = data.get('format_type', 'video+audio')
    
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    
    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({'error': 'Invalid YouTube URL'}), 400
    
    # Clean URL to remove playlist parameters
    clean_url = clean_youtube_url(url)
    
    # Create task
    task_id = str(uuid.uuid4())[:8]
    tasks[task_id] = {
        'status': 'queued',
        'progress': 0,
        'url': clean_url,
        'quality': quality,
        'format_type': format_type,
        'video_id': video_id,
    }
    
    # Submit to executor
    executor.submit(download_video, task_id, clean_url, quality, format_type)
    
    return jsonify({'task_id': task_id})

@app.route('/status/<task_id>')
def get_status(task_id):
    """Get download status."""
    if task_id not in tasks:
        # Check database for completed download
        record = get_download_record(task_id)
        if record:
            return jsonify({
                'status': 'ready',
                'title': record['title'],
                'expiry': record['expiry_timestamp'],
            })
        return jsonify({'error': 'Task not found'}), 404
    
    task = tasks[task_id]
    response = {
        'status': task['status'],
        'progress': task.get('progress', 0),
    }
    
    if task['status'] == 'ready':
        response['title'] = task.get('title')
        response['filename'] = task.get('filename')
        response['expiry'] = task.get('expiry')
    elif task['status'] == 'error':
        response['error'] = task.get('error')
    
    return jsonify(response)

@app.route('/file/<task_id>')
def download_file(task_id):
    """Serve the downloaded file."""
    # Check in-memory tasks first
    if task_id in tasks and tasks[task_id].get('filepath'):
        filepath = tasks[task_id]['filepath']
        filename = tasks[task_id].get('filename', 'download')
    else:
        # Check database
        record = get_download_record(task_id)
        if not record:
            return jsonify({'error': 'File not found'}), 404
        filepath = record['filepath']
        filename = Path(filepath).name
    
    if not Path(filepath).exists():
        return jsonify({'error': 'File no longer exists'}), 404
    
    return send_file(
        filepath,
        as_attachment=True,
        download_name=filename
    )

# =============================================================================
# Main
# =============================================================================

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
