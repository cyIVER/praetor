#!/bin/bash
# Waybar custom/praetor-driving: visible whenever the agent has the desktop.
if [[ -f "$HOME/.local/state/praetor/hands.driving" ]]; then
  echo '{"text": "󰭹 PRAETOR DRIVING", "tooltip": "The agent is controlling the desktop. Super+Escape stops it.", "class": "active"}'
else
  echo '{"text": ""}'
fi
