---
title: Narrate
emoji: 🎧
colorFrom: indigo
colorTo: green
sdk: gradio
sdk_version: 5.49.1
app_file: app.py
pinned: false
license: apache-2.0
---

# Narrate

Explore cached English and Hindi audio-description runs at zero cost. The
Samples tab is the default and makes no model API calls.

Live uploads are hidden unless the host sets `NARRATE_LIVE=1` and provides a
supported provider credential in the server environment. Hosted limits are
read from `config.yaml`: $3 per day, clips up to 60 seconds, and 24 agent turns.
Credentials are never accepted from or shown to visitors.
