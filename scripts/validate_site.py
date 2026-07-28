#!/usr/bin/env python3
"""Validate the deployable site, generated data, and public-release boundaries."""

import csv
import importlib.util
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DIR = REPO_ROOT / "public"
MAX_PUBLIC_BYTES = 25 * 1024 * 1024
ALLOWED_ROOT_ENTRIES = {
    "_headers",
    "404.html",
    "assets",
    "data",
    "favicon.svg",
    "index.html",
    "models.html",
    "og.png",
}
ALLOWED_SUFFIXES = {".css", ".html", ".js", ".json", ".png", ".svg", ".woff2"}
ALLOWED_EXTERNAL_HOSTS = {
    "artificialanalysis.ai",
    "github.com",
    "models.optiqo.dev",
    "www.artificialanalysis.ai",
    "www.github.com",
}


class SiteHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.local_refs = []
        self.external_hosts = set()
        self.errors = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "style":
            self.errors.append("inline <style> is not allowed")
        if any(name.lower().startswith("on") for name, _ in attrs):
            self.errors.append(f"inline event handler on <{tag}> is not allowed")
        if tag == "script" and not values.get("src"):
            self.errors.append("inline <script> is not allowed")
        if "style" in values:
            self.errors.append(f"inline style attribute on <{tag}> is not allowed")
        for attribute in ("href", "src"):
            value = values.get(attribute)
            if not value or value.startswith(("#", "data:", "mailto:")):
                continue
            if value.startswith(("//", "\\")) or "\\" in value:
                self.errors.append(f"ambiguous or protocol-relative URL: {value}")
                continue
            parsed = urlparse(value)
            if parsed.scheme:
                if parsed.scheme != "https":
                    self.errors.append(f"non-HTTPS external URL: {value}")
                if parsed.hostname:
                    self.external_hosts.add(parsed.hostname)
            else:
                self.local_refs.append(value.split("?", 1)[0].split("#", 1)[0])
        if values.get("target") == "_blank":
            rel = set((values.get("rel") or "").split())
            if not {"noopener", "noreferrer"}.issubset(rel):
                self.errors.append("target=_blank link lacks noopener noreferrer")


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def load_fetch_module():
    path = REPO_ROOT / "scripts" / "fetch_aa_models.py"
    spec = importlib.util.spec_from_file_location("fetch_aa_models", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_public_tree():
    errors = []
    entries = {path.name for path in PUBLIC_DIR.iterdir()}
    if entries != ALLOWED_ROOT_ENTRIES:
        errors.append(
            f"public root entries differ from allowlist: "
            f"extra={sorted(entries - ALLOWED_ROOT_ENTRIES)}, "
            f"missing={sorted(ALLOWED_ROOT_ENTRIES - entries)}"
        )

    total = 0
    for path in PUBLIC_DIR.rglob("*"):
        if path.is_symlink():
            errors.append(f"symlink is forbidden in public output: {path.relative_to(PUBLIC_DIR)}")
        if not path.is_file():
            continue
        rel = path.relative_to(PUBLIC_DIR)
        total += path.stat().st_size
        if any(part.startswith(".") for part in rel.parts):
            errors.append(f"hidden file is forbidden in public output: {rel}")
        if path.name != "_headers" and path.suffix not in ALLOWED_SUFFIXES:
            errors.append(f"unexpected public file type: {rel}")
    if total > MAX_PUBLIC_BYTES:
        errors.append(f"public output is too large: {total} bytes")
    return errors


def validate_html():
    errors = []
    for page in PUBLIC_DIR.glob("*.html"):
        parser = SiteHTMLParser()
        parser.feed(page.read_text(encoding="utf-8"))
        errors.extend(f"{page.name}: {error}" for error in parser.errors)
        unexpected = parser.external_hosts - ALLOWED_EXTERNAL_HOSTS
        if unexpected:
            errors.append(f"{page.name}: unexpected external hosts: {sorted(unexpected)}")
        for ref in parser.local_refs:
            target = (page.parent / ref).resolve()
            try:
                target.relative_to(PUBLIC_DIR.resolve())
            except ValueError:
                errors.append(f"{page.name}: local reference escapes public/: {ref}")
                continue
            if not target.exists():
                errors.append(f"{page.name}: missing local asset: {ref}")
    return errors


def validate_headers():
    headers = (PUBLIC_DIR / "_headers").read_text(encoding="utf-8")
    errors = []
    for forbidden in ("'unsafe-inline'", "'unsafe-eval'", "openrouter.ai", "api.groq.com"):
        if forbidden in headers:
            errors.append(f"forbidden CSP value remains: {forbidden}")
    required = (
        "default-src 'none'",
        "script-src 'self'",
        "style-src 'self'",
        "connect-src 'self'",
        "frame-ancestors 'none'",
        "Strict-Transport-Security:",
    )
    for value in required:
        if value not in headers:
            errors.append(f"required security header value is missing: {value}")
    return errors


def validate_fonts():
    css = (PUBLIC_DIR / "assets" / "fonts.css").read_text(encoding="utf-8")
    referenced = set(re.findall(r"fonts/(font_\d+\.woff2)", css))
    present = {path.name for path in (PUBLIC_DIR / "assets" / "fonts").glob("*.woff2")}
    errors = []
    if referenced - present:
        errors.append(f"missing font files: {sorted(referenced - present)}")
    if present - referenced:
        errors.append(f"unreferenced font files: {sorted(present - referenced)}")
    return errors


def validate_data():
    path = PUBLIC_DIR / "data" / "models.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("models"), list):
        return ["models.json does not contain a models list"]
    module = load_fetch_module()
    try:
        module.validate_output_models(data["models"], path)
    except RuntimeError as exc:
        return [str(exc)]
    return []


def validate_history_csv():
    errors = []
    dangerous = ("=", "+", "-", "@", "\t", "\r")
    for path in (REPO_ROOT / "data" / "history").glob("*.csv"):
        with path.open(newline="", encoding="utf-8") as handle:
            rows = csv.reader(handle)
            header = next(rows, [])
            text_columns = {
                index for index, name in enumerate(header)
                if name in {"name", "creator", "release_date", "slug"}
            }
            for row_number, row in enumerate(rows, 2):
                for index in text_columns:
                    if index < len(row) and row[index].startswith(dangerous):
                        errors.append(f"spreadsheet formula prefix in {path.name}:{row_number}")
                        break
    return errors


def main():
    checks = (
        validate_public_tree,
        validate_html,
        validate_headers,
        validate_fonts,
        validate_data,
        validate_history_csv,
    )
    errors = [error for check in checks for error in check()]
    if errors:
        for error in errors:
            fail(error)
        return 1
    model_count = len(json.loads((PUBLIC_DIR / "data" / "models.json").read_text())["models"])
    print(f"Validated secure public output with {model_count} models")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
