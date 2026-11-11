"""Bounded calls to configured internal backend services."""
import json
import os
from urllib.request import Request, urlopen
from urllib.error import URLError


def post(url, path, payload, timeout=120):
    token = os.environ.get("INTERNAL_SERVICE_TOKEN", "")
    if not token:
        raise RuntimeError("INTERNAL_SERVICE_TOKEN is required")
    request = Request(url.rstrip("/") + path, data=json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json", "Authorization": "Bearer " + token})
    try:
        with urlopen(request, timeout=timeout) as response:
            content = response.read(64 * 1024 * 1024 + 1)
        if len(content) > 64 * 1024 * 1024:
            raise RuntimeError("Internal service response exceeds limit")
        return json.loads(content)
    except (URLError, TimeoutError, ValueError) as error:
        raise RuntimeError("Internal backend service unavailable or invalid response") from error
