from __future__ import annotations

import os
import subprocess
import webbrowser


class BrowserController:
    def open_url(self, url: str) -> str:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        try:
            if os.name == "nt":
                os.startfile(url)
            else:
                webbrowser.open(url, new=2)
            return f"Opened browser page: {url}"
        except Exception as exc:  # pragma: no cover
            return f"Could not open browser: {exc}"
