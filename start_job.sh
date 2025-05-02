#!/bin/sh
if [[ -z "${VIRTUAL_ENV+x}" ]] ; then
    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
fi
python news_scraper.py --test