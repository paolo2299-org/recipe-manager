"""Fetch webpage content as clean markdown via Jina Reader."""

import requests


def fetch_via_jina(url: str) -> str:
    """Fetch webpage content as clean markdown via Jina Reader."""
    jina_url = f"https://r.jina.ai/{url}"
    headers = {
        "Accept": "text/plain",
        "X-Return-Format": "markdown",
    }
    response = requests.get(jina_url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text
