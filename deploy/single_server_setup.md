# Single Server Setup Guide for Nota-AI "Walking Skeleton"

This guide explains how to deploy the Nota-AI bot on a minimal VPS (1 vCPU, 1 GB RAM) such as a DigitalOcean Droplet.

## Prerequisites

- Ubuntu 22.04 LTS
- SSH access to your server
- Domain name (optional)

## Step 1: Initial Server Setup

```bash
# Update the system
sudo apt update && sudo apt upgrade -y

# Install required dependencies
sudo apt install -y python3 python3-pip python3-venv git redis-server logrotate

# Enable and start Redis
sudo systemctl enable redis-server
sudo systemctl start redis-server

# Check Redis status
sudo systemctl status redis-server
```

## Step 2: Clone the Repository

```bash
# Create directory for application
mkdir -p /opt/nota-ai
cd /opt/nota-ai

# Clone the repository
git clone https://github.com/your-organization/nota-optimized.git .

# Alternative: Upload code via SCP
# On your local machine:
# scp -r /path/to/local/nota-optimized/* user@your-server:/opt/nota-ai/
```

## Step 3: Set Up Python Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install requirements
pip install -r requirements.txt

# Verify dependencies
pip list
```

## Step 4: Configure Environment

```bash
# Create and edit .env file
cp .env.example .env
nano .env
```

Add your API keys and Telegram Bot token:

```
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
OPENAI_API_KEY=your_openai_api_key
ADMIN_CHAT_ID=your_telegram_chat_id
```

## Step 5: Set Up Logging

```bash
# Create logs directory
mkdir -p logs

# Configure logrotate
sudo cp deploy/nota-logs.logrotate /etc/logrotate.d/nota-logs
sudo chmod 644 /etc/logrotate.d/nota-logs
sudo logrotate --force /etc/logrotate.d/nota-logs
```

## Step 6: Install Systemd Service

```bash
# Copy the systemd service file
sudo cp deploy/nota.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable the service to start on boot
sudo systemctl enable nota.service

# Start the service
sudo systemctl start nota.service

# Check service status
sudo systemctl status nota.service
```

## Step 7: Verify Bot Operation

```bash
# Check logs
journalctl -u nota.service -f

# Check if bot process is running
ps aux | grep bot.py

# Test Redis connection
redis-cli ping
```

## Step 8: Monitoring and Maintenance

### View Real-time Logs

```bash
journalctl -u nota.service -f
```

### Restart the Bot

```bash
sudo systemctl restart nota.service
```

### Check for Errors

```bash
# View error logs
tail -f logs/nota.log

# Run error report script
./scripts/send_test_invoices.sh
```

## Troubleshooting

### Bot Not Starting
- Check logs: `journalctl -u nota.service -e`
- Verify your `.env` file contains the correct API keys
- Ensure Redis is running: `systemctl status redis-server`

### Memory Issues
- Check memory usage: `free -m`
- Consider adding swap: 
  ```bash
  sudo fallocate -l 1G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
  ```

### Connection Issues
- Verify internet connection: `ping -c 4 google.com`
- Check Telegram API connectivity: `curl -s https://api.telegram.org`
- Check OpenAI API connectivity: `curl -s https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY"`