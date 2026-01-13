#!/usr/bin/env python3
"""
YouTube Downloader - Cleanup Script
Run via cron every 10 minutes: */10 * * * * /path/to/cleanup.py

Removes expired downloads based on retention policy:
Retention = MAX(2 hours, video_duration)
"""

import logging
import sqlite3
import time
from pathlib import Path

# =============================================================================
# Configuration
# =============================================================================

BASE_DIR = Path(__file__).parent.resolve()
DOWNLOADED_DIR = BASE_DIR / "downloaded"
CONVERTED_DIR = BASE_DIR / "converted"
DATABASE_PATH = BASE_DIR / "downloads.db"
LOG_FILE = BASE_DIR / "cleanup.log"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# =============================================================================
# Cleanup Functions
# =============================================================================

def get_expired_records():
    """Get all records where expiry_timestamp < current time."""
    if not DATABASE_PATH.exists():
        return []
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    current_time = time.time()
    cursor.execute('''
        SELECT id, filepath, title, expiry_timestamp 
        FROM downloads 
        WHERE expiry_timestamp < ?
    ''', (current_time,))
    
    records = cursor.fetchall()
    conn.close()
    
    return [
        {'id': r[0], 'filepath': r[1], 'title': r[2], 'expiry': r[3]}
        for r in records
    ]

def delete_file_safely(filepath):
    """Delete a file if it exists, return success status."""
    path = Path(filepath)
    if path.exists():
        try:
            path.unlink()
            return True
        except Exception as e:
            logger.error(f"Failed to delete {filepath}: {e}")
            return False
    return True  # File already doesn't exist

def remove_db_record(record_id):
    """Remove a record from the database."""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM downloads WHERE id = ?', (record_id,))
    conn.commit()
    conn.close()

def cleanup_expired():
    """Main cleanup routine for expired files."""
    logger.info("Starting cleanup...")
    
    expired = get_expired_records()
    
    if not expired:
        logger.info("No expired files found.")
        return 0
    
    deleted_count = 0
    for record in expired:
        logger.info(f"Processing expired: {record['title']} (ID: {record['id']})")
        
        # Delete the file
        if delete_file_safely(record['filepath']):
            # Remove from database
            remove_db_record(record['id'])
            deleted_count += 1
            logger.info(f"Deleted: {record['filepath']}")
        else:
            logger.warning(f"Could not delete: {record['filepath']}")
    
    logger.info(f"Cleanup complete. Deleted {deleted_count} files.")
    return deleted_count

def cleanup_orphaned_files():
    """
    Clean up files in downloaded folder that don't have matching tasks.
    These are leftover intermediate files from failed downloads.
    """
    logger.info("Checking for orphaned files in downloaded folder...")
    
    orphaned_count = 0
    for filepath in DOWNLOADED_DIR.glob("*"):
        if filepath.is_file():
            # Check if file is older than 1 hour (likely orphaned)
            age = time.time() - filepath.stat().st_mtime
            if age > 3600:  # 1 hour
                try:
                    filepath.unlink()
                    orphaned_count += 1
                    logger.info(f"Deleted orphaned: {filepath.name}")
                except Exception as e:
                    logger.error(f"Failed to delete orphaned {filepath}: {e}")
    
    if orphaned_count:
        logger.info(f"Deleted {orphaned_count} orphaned files.")
    
    return orphaned_count

def test_cleanup():
    """Test mode: Create a test file and expired record, then clean it up."""
    import uuid
    
    logger.info("=== RUNNING CLEANUP TEST ===")
    
    # Create test file
    test_id = f"test_{uuid.uuid4().hex[:8]}"
    test_file = CONVERTED_DIR / f"{test_id}_test_video.mp4"
    test_file.write_text("test content")
    
    # Create expired DB record
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
    cursor.execute('''
        INSERT INTO downloads 
        (id, video_id, title, filepath, duration_seconds, expiry_timestamp, format_info, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (test_id, 'test123', 'Test Video', str(test_file), 60, time.time() - 100, 'test', 'ready', time.time()))
    conn.commit()
    conn.close()
    
    logger.info(f"Created test file: {test_file}")
    
    # Run cleanup
    deleted = cleanup_expired()
    
    # Verify
    if not test_file.exists():
        logger.info("✓ TEST PASSED: Test file was deleted successfully")
    else:
        logger.error("✗ TEST FAILED: Test file still exists")
        test_file.unlink()  # Clean up anyway
    
    logger.info("=== TEST COMPLETE ===")

# =============================================================================
# Main
# =============================================================================

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == '--test':
        test_cleanup()
    else:
        cleanup_expired()
        cleanup_orphaned_files()
