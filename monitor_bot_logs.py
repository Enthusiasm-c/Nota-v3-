#!/usr/bin/env python3
"""
Monitor bot logs in real-time and highlight errors
"""

import os
import time
import sys
from datetime import datetime

# ANSI color codes
RED = '\033[91m'
YELLOW = '\033[93m'
GREEN = '\033[92m'
BLUE = '\033[94m'
RESET = '\033[0m'

def follow_log(log_file, keywords=None):
    """Follow log file like tail -f with keyword highlighting"""
    if not os.path.exists(log_file):
        print(f"Log file {log_file} not found")
        return
    
    # Keywords to highlight
    if keywords is None:
        keywords = {
            'ERROR': RED,
            'CRITICAL': RED,
            'WARNING': YELLOW,
            'INFO': GREEN,
            'DEBUG': BLUE,
            'Exception': RED,
            'Traceback': RED,
            'Failed': RED,
            '❌': RED,
            '✅': GREEN,
            '⚠️': YELLOW
        }
    
    print(f"Monitoring {log_file}")
    print(f"Time: {datetime.now()}")
    print("-" * 60)
    
    with open(log_file, 'r') as f:
        # Go to end of file
        f.seek(0, os.SEEK_END)
        
        try:
            while True:
                line = f.readline()
                if line:
                    # Highlight keywords
                    formatted_line = line.rstrip()
                    for keyword, color in keywords.items():
                        if keyword in formatted_line:
                            formatted_line = formatted_line.replace(
                                keyword, 
                                f"{color}{keyword}{RESET}"
                            )
                            break
                    
                    print(formatted_line)
                else:
                    time.sleep(0.1)
                    
        except KeyboardInterrupt:
            print(f"\n{YELLOW}Monitoring stopped{RESET}")

def main():
    """Main entry point"""
    log_files = [
        'logs/bot.log',
        'logs/errors.log',
        'logs/nota.log'
    ]
    
    print("Available log files:")
    for i, log_file in enumerate(log_files):
        if os.path.exists(log_file):
            size = os.path.getsize(log_file) / 1024  # KB
            print(f"{i+1}. {log_file} ({size:.1f} KB)")
        else:
            print(f"{i+1}. {log_file} (not found)")
    
    try:
        choice = input("\nSelect log file to monitor (1-3): ")
        idx = int(choice) - 1
        if 0 <= idx < len(log_files):
            follow_log(log_files[idx])
        else:
            print("Invalid choice")
    except (ValueError, KeyboardInterrupt):
        print("\nExiting...")

if __name__ == "__main__":
    main()