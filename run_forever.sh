#!/bin/bash

LOGFILE="logs/nota-bot.log"
ERRFILE="logs/nota-bot.err"

while true; do
  echo "[run_forever.sh] Запуск бота: $(date)" >> "$LOGFILE"
  python3 bot.py >> "$LOGFILE" 2>> "$ERRFILE"
  echo "[run_forever.sh] Бот завершился! Перезапуск через 5 секунд..." >> "$LOGFILE"
  sleep 5
done 