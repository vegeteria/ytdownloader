# YouTube Downloader - VPS Deployment with Caddy

Deploy guide for Ubuntu 24.04 VPS with Caddy reverse proxy.

---

## 1. System Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y ffmpeg python3 python3-pip python3-venv git
```

---

## 2. Install Caddy

```bash
# Install Caddy
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy
```

---

## 3. Deploy Application

```bash
# Create app directory
sudo mkdir -p /opt/yt-downloader
sudo chown $USER:$USER /opt/yt-downloader

# Copy your project files (from local machine)
# scp -r /home/muntahi/Downloads/try/yt-downloader/* user@your-vps:/opt/yt-downloader/

# Or clone from git if you push to a repo
cd /opt/yt-downloader

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create directories
mkdir -p downloaded converted templates
```

---

## 4. Add cookies.txt

```bash
# Copy your cookies.txt to the server
# scp cookies.txt user@your-vps:/opt/yt-downloader/cookies.txt
```

---

## 5. Systemd Service

```bash
sudo nano /etc/systemd/system/yt-downloader.service
```

Paste this:

```ini
[Unit]
Description=YouTube Downloader Flask App
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/yt-downloader
Environment="PATH=/opt/yt-downloader/venv/bin"
ExecStart=/opt/yt-downloader/venv/bin/gunicorn -w 4 -b 127.0.0.1:5000 app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
# Set permissions
sudo chown -R www-data:www-data /opt/yt-downloader

# Enable service
sudo systemctl daemon-reload
sudo systemctl enable yt-downloader
sudo systemctl start yt-downloader
sudo systemctl status yt-downloader
```

---

## 6. Caddy Configuration

### Option A: Custom Port (e.g., 8080)

```bash
sudo nano /etc/caddy/Caddyfile
```

```caddyfile
:8080 {
    reverse_proxy localhost:5000
    
    # Increase timeouts for large downloads
    request_body {
        max_size 2GB
    }
}
```

Access via: `http://your-vps-ip:8080`

---

### Option B: Domain with HTTPS (Recommended)

```caddyfile
yourdomain.com {
    reverse_proxy localhost:5000
    
    request_body {
        max_size 2GB
    }
}
```

Caddy will automatically get SSL certificates!

---

### Option C: Subdirectory on Existing Server

```caddyfile
yourdomain.com {
    handle /yt-downloader/* {
        uri strip_prefix /yt-downloader
        reverse_proxy localhost:5000
    }
    
    # Your other routes...
}
```

---

## 7. Apply Caddy Config

```bash
sudo systemctl reload caddy
sudo systemctl status caddy
```

---

## 8. Firewall (if using UFW)

```bash
# For custom port
sudo ufw allow 8080/tcp

# For domain (HTTPS)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

sudo ufw reload
```

---

## 9. Setup Cleanup Cron

```bash
# Make script executable
sudo chmod +x /opt/yt-downloader/cleanup.py

# Add cron job (as www-data user)
sudo crontab -u www-data -e
```

Add:

```cron
*/10 * * * * /opt/yt-downloader/venv/bin/python /opt/yt-downloader/cleanup.py >> /opt/yt-downloader/cleanup.log 2>&1
```

---

## 10. Verify Deployment

```bash
# Check services
sudo systemctl status yt-downloader
sudo systemctl status caddy

# Test locally
curl http://localhost:5000

# Check logs
sudo journalctl -u yt-downloader -f
tail -f /opt/yt-downloader/cleanup.log
```

---

## Quick Commands Reference

```bash
# Restart app
sudo systemctl restart yt-downloader

# Restart Caddy
sudo systemctl reload caddy

# View app logs
sudo journalctl -u yt-downloader -f

# Update app (after uploading new files)
sudo systemctl restart yt-downloader
```

---

## Troubleshooting

```bash
# Permission issues
sudo chown -R www-data:www-data /opt/yt-downloader

# Check if port is in use
sudo lsof -i :5000

# Test Gunicorn directly
cd /opt/yt-downloader
source venv/bin/activate
gunicorn -w 1 -b 0.0.0.0:5000 app:app
```
