#!/bin/bash

# === Config ===
TOKEN="YZPSAAbXvIw1586HKdZy7qeqt6wh"
OUTPUT="/root/qqq-trading/qqq_intraday_data.csv"
SYMBOL="QQQ"
INTERVAL="5min"
START=$(date -d "today 09:30" +"%Y-%m-%dT%H:%M")
END=$(date -d "now" +"%Y-%m-%dT%H:%M")

# === Fetch Data ===
curl -s "https://api.tradier.com/v1/markets/timesales?symbol=$SYMBOL&interval=$INTERVAL&start=$START&end=$END&session_filter=open" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/json" |
  jq -r '.series.data[] | [.timestamp, .open, .high, .low, .close, .volume] | @csv' > "$OUTPUT"

# === Add Header ===
sed -i '1i datetime,open,high,low,close,volume' "$OUTPUT"

echo "✅ Intraday QQQ data saved to $OUTPUT"

