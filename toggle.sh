#!/bin/bash
# Toggle the Investment Dashboard: start if stopped, stop if running.

NOTIFY() {
    osascript -e "display notification \"$1\" with title \"Investment Dashboard\""
}

if pgrep -f "streamlit run" > /dev/null 2>&1; then
    pkill -f "streamlit run"
    NOTIFY "Investment Dashboard stopped"
else
    source "/Users/vivekb2017/opt/anaconda3/etc/profile.d/conda.sh"
    conda activate investment-dashboard
    cd "/Users/vivekb2017/Desktop/Apps/investment-panel-dashboard-2026"
    streamlit run app/main.py &> /tmp/streamlit-dashboard.log &
    sleep 2
    open "http://localhost:8501"
    NOTIFY "Investment Dashboard started"
fi
