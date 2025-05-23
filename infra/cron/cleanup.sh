#!/bin/bash
# Cleanup script for Nota AI temporary files

# 1. Cleanup files older than 1 day in /tmp/nota directory
find /tmp/nota -type f -mtime +1 -delete

# Log cleanup completion
echo "[$(date +%Y-%m-%d\ %H:%M:%S)] Cleaned up files older than 1 day in /tmp/nota" >> /var/log/nota_cleanup.log

# Exit successfully
exit 0
