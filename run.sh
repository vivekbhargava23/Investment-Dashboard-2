#!/bin/bash
# Activate conda environment and launch the Investment Dashboard in the browser.

source "/Users/vivekb2017/opt/anaconda3/etc/profile.d/conda.sh"
conda activate investment-dashboard

cd "/Users/vivekb2017/Desktop/Apps/investment-panel-dashboard-2026"
streamlit run app/main.py
