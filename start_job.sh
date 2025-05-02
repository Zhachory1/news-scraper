#!/bin/sh
if [[ -z "${VIRTUAL_ENV+x}" ]] ; then
    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
fi

# View news_scaper.py to see all arguments
if [[ $# -eq 0 ]] ; then
    python news_scraper.py 
else
    python news_scraper.py $@
fi