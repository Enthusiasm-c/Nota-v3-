#!/usr/bin/env python3
"""Simple log monitoring script"""

import os
import time
from datetime import datetime
from pathlib import Path

# ANSI color codes
RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
MAGENTA = '\033[95m'
CYAN = '\033[96m'
WHITE = '\033[97m'
RESET = '\033[0m'
BOLD = '\033[1m'

def tail_file(file_path, n=10):
    """Read last n lines from file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            return lines[-n:] if len(lines) >= n else lines
    except Exception:
        return []

def monitor_logs():
    """Monitor all log files"""
    log_dir = Path("logs")
    
    print(f"{BOLD}=== Log Monitor ==={RESET}")
    print(f"Time: {datetime.now()}")
    print(f"Watching directory: {log_dir}")
    
    # Check if logs directory exists
    if not log_dir.exists():
        print(f"{RED}❌ Logs directory not found{RESET}")
        return
    
    # Monitor all log files
    log_files = list(log_dir.glob("*.log"))
    
    if not log_files:
        print(f"{YELLOW}⚠️ No log files found{RESET}")
        return
    
    print(f"\n{GREEN}Found {len(log_files)} log files:{RESET}")
    
    # Track file sizes
    file_sizes = {}
    for log_file in log_files:
        try:
            size = log_file.stat().st_size
            file_sizes[log_file] = size
            print(f"  • {log_file.name}: {size:,} bytes")
        except Exception as e:
            print(f"  • {log_file.name}: {RED}Error: {e}{RESET}")
    
    print(f"\n{BOLD}Monitoring logs... (Press Ctrl+C to stop){RESET}\n")
    
    while True:
        try:
            for log_file in log_files:
                try:
                    new_size = log_file.stat().st_size
                    old_size = file_sizes.get(log_file, 0)
                    
                    if new_size > old_size:
                        # File has grown, read new content
                        with open(log_file, 'r', encoding='utf-8') as f:
                            f.seek(old_size)
                            new_content = f.read()
                            
                            if new_content.strip():
                                print(f"\n{CYAN}[{datetime.now().strftime('%H:%M:%S')}] {log_file.name}:{RESET}")
                                
                                for line in new_content.strip().split('\n'):
                                    # Color code based on content
                                    if 'ERROR' in line or 'CRITICAL' in line:
                                        print(f"{RED}{line}{RESET}")
                                    elif 'WARNING' in line:
                                        print(f"{YELLOW}{line}{RESET}")
                                    elif 'INFO' in line:
                                        print(f"{GREEN}{line}{RESET}")
                                    elif 'DEBUG' in line:
                                        print(f"{BLUE}{line}{RESET}")
                                    else:
                                        print(line)
                        
                        file_sizes[log_file] = new_size
                        
                except Exception as e:
                    print(f"{RED}Error reading {log_file.name}: {e}{RESET}")
            
            time.sleep(0.5)  # Check every 500ms
            
        except KeyboardInterrupt:
            print(f"\n{YELLOW}Monitoring stopped.{RESET}")
            break

if __name__ == "__main__":
    monitor_logs()