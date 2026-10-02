"""Turns the Flask site into plain HTML files in the 'site' folder.
Run:  python build.py
Then upload everything inside 'site' to any static host (GitHub Pages, Netlify, etc.)."""
import os, shutil
from app import app

PAGES = {"/": "index.html", "/about": "about.html", "/testimonials": "testimonials.html",
         "/terms": "terms.html", "/privacy": "privacy.html"}

OUT = "site"
shutil.rmtree(OUT, ignore_errors=True)
shutil.copytree("static", os.path.join(OUT, "static"))

client = app.test_client()
for route, filename in PAGES.items():
    html = client.get(route).get_data(as_text=True)
    html = html.replace("/static/", "static/")
    for r, f in PAGES.items():
        html = html.replace(f'href="{r}#', f'href="{f}#').replace(f'href="{r}"', f'href="{f}"')
    open(os.path.join(OUT, filename), "w", encoding="utf-8").write(html)
    print("built", filename)
