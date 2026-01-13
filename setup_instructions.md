# YouTube Video Downloader - Setup Instructions

Complete guide for deploying the YouTube downloader on Ubuntu 24.04.

## Prerequisites

### 1. System Dependencies

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install ffmpeg and Python
sudo apt install -y ffmpeg python3 python3-pip python3-venv
```

### 2. Verify ffmpeg Installation

```bash
ffmpeg -version
```

---

## Application Setup

### 1. Navigate to Project Directory

```bash
cd /path/to/yt-downloader
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 4. Create Required Directories

The directories should already exist, but if not:

```bash
mkdir -p downloaded converted templates
```

### 5. Setup cookies.txt (IMPORTANT)

yt-dlp requires YouTube cookies for reliable downloads.

**Option A: Using a Browser Extension**

1. Install "Get cookies.txt LOCALLY" extension for Chrome/Firefox
2. Go to youtube.com and ensure you're logged in
3. Click the extension and export cookies
4. Save as `cookies.txt` in the project root

**Option B: Using yt-dlp directly**

```bash
# Extract cookies from your browser
yt-dlp --cookies-from-browser chrome --cookies cookies.txt "https://www.youtube.com"
```

**Cookie file location:**
```
/path/to/yt-downloader/cookies.txt
```

---

## Running the Application

### Development Mode

```bash
source venv/bin/activate
python app.py
```

Access at: `http://localhost:5000`

### Production Mode (Gunicorn)

```bash
source venv/bin/activate
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

---

## Systemd Service (Production)

### 1. Create Service File

```bash
sudo nano /etc/systemd/system/yt-downloader.service
```

Add the following content:

```ini
[Unit]
Description=YouTube Downloader Flask App
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/path/to/yt-downloader
Environment="PATH=/path/to/yt-downloader/venv/bin"
ExecStart=/path/to/yt-downloader/venv/bin/gunicorn -w 4 -b 127.0.0.1:5000 app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 2. Enable and Start Service

```bash
# Set correct permissions
sudo chown -R www-data:www-data /path/to/yt-downloader

# Reload systemd
sudo systemctl daemon-reload

# Enable and start
sudo systemctl enable yt-downloader
sudo systemctl start yt-downloader

# Check status
sudo systemctl status yt-downloader
```

---

## Nginx Configuration

### 1. Create Nginx Config

```bash
sudo nano /etc/nginx/sites-available/yt-downloader
```

Add:

```nginx
server {
    listen 80;
    server_name your-domain.com;  # Or your IP address

    client_max_body_size 2G;  # For large video downloads

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts for long downloads
        proxy_connect_timeout 300;
        proxy_send_timeout 300;
        proxy_read_timeout 300;
    }

    # Serve converted files directly (optional, for performance)
    location /converted/ {
        alias /path/to/yt-downloader/converted/;
        internal;
    }
}
```

### 2. Enable Site

```bash
sudo ln -s /etc/nginx/sites-available/yt-downloader /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 3. (Optional) SSL with Certbot

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

---

## Cleanup Cron Job

The cleanup script removes expired files based on retention policy.

### 1. Make Script Executable

```bash
chmod +x /path/to/yt-downloader/cleanup.py
```

### 2. Setup Cron Job

```bash
crontab -e
```

Add this line (runs every 10 minutes):

```cron
*/10 * * * * /path/to/yt-downloader/venv/bin/python /path/to/yt-downloader/cleanup.py >> /path/to/yt-downloader/cleanup.log 2>&1
```

### 3. Verify Cron

```bash
# List current cron jobs
crontab -l

# Check cleanup log
tail -f /path/to/yt-downloader/cleanup.log
```

---

## Retention Policy

Files are automatically deleted based on this rule:

```
Retention Time = MAX(2 hours, Video Duration)
```

Examples:
- 5-minute video → Kept for 2 hours
- 1.5-hour video → Kept for 2 hours
- 3-hour video → Kept for 3 hours

---

## Troubleshooting

### yt-dlp Errors

```bash
# Update yt-dlp
pip install -U yt-dlp

# Test with cookies
yt-dlp --cookies cookies.txt "https://www.youtube.com/watch?v=VIDEO_ID" --print title
```

### Permission Issues

```bash
sudo chown -R www-data:www-data /path/to/yt-downloader
sudo chmod -R 755 /path/to/yt-downloader
```

### Check Logs

```bash
# Application logs
sudo journalctl -u yt-downloader -f

# Nginx logs
sudo tail -f /var/log/nginx/error.log

# Cleanup logs
tail -f /path/to/yt-downloader/cleanup.log
```

---

## Quick Start Commands

```bash
# Full setup (run from project directory)
sudo apt install -y ffmpeg python3 python3-pip python3-venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run in development
python app.py

# Access: http://localhost:5000
```
