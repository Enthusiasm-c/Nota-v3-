#!/usr/bin/env python3
"""
Watch bot activity in real-time
"""

import os
import time
import subprocess
from datetime import datetime

# ANSI colors
RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
CYAN = '\033[96m'
RESET = '\033[0m'
BOLD = '\033[1m'

def get_bot_pid():
    """Get bot process PID"""
    try:
        result = subprocess.run(['pgrep', '-f', 'python.*bot.py'], 
                               capture_output=True, text=True)
        if result.stdout:
            return result.stdout.strip()
    except:
        pass
    return None

def tail_log(log_file, last_position=0):
    """Read new lines from log file"""
    if not os.path.exists(log_file):
        return last_position, []
    
    new_lines = []
    with open(log_file, 'r') as f:
        f.seek(last_position)
        new_lines = f.readlines()
        last_position = f.tell()
    
    return last_position, new_lines

def format_line(line):
    """Format log line with colors"""
    # Errors
    if any(word in line for word in ['ERROR', 'CRITICAL', 'Exception', 'Traceback']):
        return f"{RED}{line}{RESET}"
    
    # Warnings
    if 'WARNING' in line:
        return f"{YELLOW}{line}{RESET}"
    
    # User actions
    if any(word in line for word in ['message from', 'callback from', 'photo from']):
        return f"{CYAN}{line}{RESET}"
    
    # Success
    if any(word in line for word in ['✅', 'SUCCESS', 'completed']):
        return f"{GREEN}{line}{RESET}"
    
    # Info
    if 'INFO' in line:
        return f"{BLUE}{line}{RESET}"
    
    return line

def main():
    """Main monitoring loop"""
    print(f"{BOLD}=== Bot Activity Monitor ==={RESET}")
    print(f"Time: {datetime.now()}")
    
    # Check if bot is running
    pid = get_bot_pid()
    if pid:
        print(f"{GREEN}✅ Bot is running (PID: {pid}){RESET}")
    else:
        print(f"{RED}❌ Bot is not running{RESET}")
        return
    
    print(f"\nMonitoring logs...")
    print("-" * 60)
    
    # Log files to monitor
    log_files = {
        'logs/bot_live.log': 0,
        'logs/bot.log': 0,
        'logs/nota.log': 0,
        'logs/errors.log': 0
    }
    
    try:
        while True:
            for log_file, position in log_files.items():
                new_position, new_lines = tail_log(log_file, position)
                log_files[log_file] = new_position
                
                for line in new_lines:
                    line = line.rstrip()
                    if line:  # Skip empty lines
                        # Add log file prefix
                        prefix = f"[{os.path.basename(log_file).replace('.log', '')}]"
                        formatted = format_line(f"{prefix} {line}")
                        print(formatted)
            
            # Check if bot is still running
            if not get_bot_pid():
                print(f"\n{RED}⚠️  Bot stopped!{RESET}")
                break
            
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Monitoring stopped{RESET}")

if __name__ == "__main__":
    main()