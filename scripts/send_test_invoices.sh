#!/bin/bash

# send_test_invoices.sh - Script to send test invoices to the bot for smoke testing
# Author: Claude
# Version: 1.0
# Date: 2025-05-14

# Set color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SAMPLE_DIR="data/samples"
LOG_DIR="logs"
ERROR_LOG="$LOG_DIR/nota.log"
TEST_RESULT_FILE="$LOG_DIR/test_results.log"
BOT_TOKEN=""
CHAT_ID=""

# Check if running as root and in the correct directory
check_environment() {
    echo -e "${BLUE}[+] Checking environment...${NC}"
    
    # Check if .env file exists and source it
    if [ -f .env ]; then
        source .env
        BOT_TOKEN=$TELEGRAM_BOT_TOKEN
        CHAT_ID=$ADMIN_CHAT_ID
        echo -e "${GREEN}[+] Loaded configuration from .env file${NC}"
    else
        echo -e "${YELLOW}[!] No .env file found${NC}"
        # Ask for bot token and chat ID if not set
        if [ -z "$BOT_TOKEN" ]; then
            read -p "Enter Telegram Bot Token: " BOT_TOKEN
        fi
        if [ -z "$CHAT_ID" ]; then
            read -p "Enter Chat ID for testing: " CHAT_ID
        fi
    fi
    
    # Verify we have what we need
    if [ -z "$BOT_TOKEN" ] || [ -z "$CHAT_ID" ]; then
        echo -e "${RED}[!] Missing bot token or chat ID${NC}"
        exit 1
    fi
    
    # Check if sample directory exists
    if [ ! -d "$SAMPLE_DIR" ]; then
        echo -e "${RED}[!] Sample directory not found: $SAMPLE_DIR${NC}"
        echo -e "${YELLOW}[*] Creating sample directory...${NC}"
        mkdir -p "$SAMPLE_DIR"
    fi
    
    # Check if we have samples
    SAMPLE_COUNT=$(ls -1 "$SAMPLE_DIR"/*.{jpg,jpeg,png} 2>/dev/null | wc -l)
    if [ "$SAMPLE_COUNT" -eq 0 ]; then
        echo -e "${YELLOW}[!] No sample invoices found in $SAMPLE_DIR${NC}"
        echo -e "${YELLOW}[*] Please add at least one sample invoice image (.jpg, .jpeg, or .png) to $SAMPLE_DIR${NC}"
        exit 1
    fi
    
    # Create log directory if it doesn't exist
    mkdir -p "$LOG_DIR"
    
    echo -e "${GREEN}[+] Environment check passed${NC}"
}

# Send test invoices to the bot
send_test_invoices() {
    echo -e "${BLUE}[+] Starting test: sending $1 sample invoices to the bot...${NC}"
    
    # Create or clear the test results file
    > "$TEST_RESULT_FILE"
    
    # Get a list of sample files
    SAMPLE_FILES=("$SAMPLE_DIR"/*.{jpg,jpeg,png})
    
    # Determine how many samples to send
    COUNT=$1
    if [ $COUNT -gt ${#SAMPLE_FILES[@]} ]; then
        echo -e "${YELLOW}[!] Requested $COUNT samples but only ${#SAMPLE_FILES[@]} available.${NC}"
        COUNT=${#SAMPLE_FILES[@]}
    fi
    
    # Send the samples
    for ((i=0; i<COUNT; i++)); do
        FILE="${SAMPLE_FILES[$i]}"
        if [ -f "$FILE" ]; then
            echo -e "${BLUE}[*] Sending sample ${i+1}/${COUNT}: $(basename "$FILE")${NC}"
            
            # Send file to Telegram
            RESPONSE=$(curl -s -X POST \
                "https://api.telegram.org/bot$BOT_TOKEN/sendPhoto" \
                -F "chat_id=$CHAT_ID" \
                -F "photo=@$FILE" \
                -F "caption=Test invoice ${i+1}/${COUNT}")
            
            # Check if the file was sent successfully
            if [[ "$RESPONSE" == *"\"ok\":true"* ]]; then
                echo -e "${GREEN}[+] Sample sent successfully${NC}"
                echo "$(date '+%Y-%m-%d %H:%M:%S') - Sent test invoice: $(basename "$FILE")" >> "$TEST_RESULT_FILE"
            else
                echo -e "${RED}[!] Failed to send sample${NC}"
                echo "$(date '+%Y-%m-%d %H:%M:%S') - Failed to send test invoice: $(basename "$FILE")" >> "$TEST_RESULT_FILE"
                echo "Response: $RESPONSE" >> "$TEST_RESULT_FILE"
            fi
            
            # Wait a bit to avoid flood limits
            sleep 2
        fi
    done
    
    echo -e "${GREEN}[+] Test completed: sent $COUNT sample invoices${NC}"
}

# Analyze error logs for top errors
analyze_errors() {
    echo -e "${BLUE}[+] Analyzing error logs...${NC}"
    
    # Check if error log exists
    if [ ! -f "$ERROR_LOG" ]; then
        echo -e "${YELLOW}[!] No error log file found at $ERROR_LOG${NC}"
        return
    fi
    
    # Wait a bit for logs to be written
    echo -e "${BLUE}[*] Waiting for processing to complete (15 seconds)...${NC}"
    sleep 15
    
    # Extract and count error messages
    echo -e "${BLUE}[*] Extracting error patterns...${NC}"
    ERROR_REPORT=$(grep -i "error\|exception\|fail" "$ERROR_LOG" | 
                   sed -E 's/^.*ERROR.*: (.*)/\1/' | 
                   sort | 
                   uniq -c | 
                   sort -nr | 
                   head -3)
    
    # Display the results
    echo -e "${YELLOW}=== TOP 3 ERRORS ====${NC}"
    if [ -z "$ERROR_REPORT" ]; then
        echo -e "${GREEN}No errors found in the log!${NC}"
    else
        echo "$ERROR_REPORT"
    fi
}

# Main function
main() {
    echo -e "${BLUE}===============================================${NC}"
    echo -e "${BLUE}= Nota-AI Bot - Smoke Test & Error Reporting =${NC}"
    echo -e "${BLUE}===============================================${NC}"
    
    # Check environment
    check_environment
    
    # Determine number of test invoices to send
    COUNT=10 # Default
    if [ "$1" -gt 0 ] 2>/dev/null; then
        COUNT=$1
    fi
    
    # Send test invoices
    send_test_invoices $COUNT
    
    # Analyze errors
    analyze_errors
    
    echo -e "${BLUE}===============================================${NC}"
    echo -e "${GREEN}Test completed. Results saved to $TEST_RESULT_FILE${NC}"
}

# Run the main function with the first argument as the number of invoices to send
main "$1"