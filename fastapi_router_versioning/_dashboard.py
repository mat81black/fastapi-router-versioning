import html

from typing import Any


def render_versions_dashboard(versions: list[dict[str, Any]], title: str, version: str) -> str:
    """Default renderer for the versions dashboard: a self-contained HTML page, no external
    assets. Replaced wholesale by versions_dashboard_hook when one is given. title and version
    are the FastAPI app's own app.title / app.version.
    """
    esc_title = html.escape(title)
    esc_version = html.escape(version)
    items: list[str] = []
    for model in versions:
        label = html.escape(str(model["version"]))
        links = [
            f'<a href="{html.escape(model[key])}">{text}</a>'
            for key, text in (
                ("swagger_url", "Swagger"),
                ("redoc_url", "ReDoc"),
                ("openapi_url", "OpenAPI"),
                ("guide_url", "Guide"),
            )
            if key in model
        ]
        docs = f'<span class="links">{"".join(links)}</span>' if links else '<span class="none">no docs</span>'
        items.append(f'      <li><span class="v">{label}</span>{docs}</li>')
    count = len(versions)
    list_html = "\n".join(items)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{esc_title} &middot; API versions</title>
    <style>
      :root {{
        color-scheme: light dark;
        --bg: #f6f7f9; --card: #ffffff; --fg: #1c1e21; --muted: #6b7280;
        --border: #e5e7eb; --accent: #0d9488;
      }}
      @media (prefers-color-scheme: dark) {{
        :root {{
          --bg: #16181d; --card: #1f2229; --fg: #e6e7ea; --muted: #9aa0aa;
          --border: #2c2f38; --accent: #2dd4bf;
        }}
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0; padding: 3rem 1rem; background: var(--bg); color: var(--fg);
        font: 16px/1.6 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
      }}
      main {{ max-width: 42rem; margin: 0 auto; }}
      h1 {{ margin: 0 0 .25rem; font-size: 1.5rem; }}
      h1 .ver {{
        font-size: .8rem; font-weight: 500; color: var(--muted);
        border: 1px solid var(--border); border-radius: 999px;
        padding: .1rem .5rem; vertical-align: middle;
      }}
      p.sub {{ margin: 0 0 2rem; color: var(--muted); }}
      ul {{ list-style: none; margin: 0; padding: 0; display: grid; gap: .75rem; }}
      li {{
        display: flex; flex-wrap: wrap; align-items: center; gap: .75rem;
        background: var(--card); border: 1px solid var(--border);
        border-radius: .75rem; padding: .9rem 1.1rem;
      }}
      .v {{ font-weight: 600; font-size: 1.05rem; margin-right: auto; }}
      .links {{ display: flex; flex-wrap: wrap; gap: .4rem; }}
      .links a {{
        text-decoration: none; font-size: .875rem; padding: .3rem .7rem;
        border: 1px solid var(--border); border-radius: 999px; color: var(--fg);
      }}
      .links a:hover {{ border-color: var(--accent); color: var(--accent); }}
      .none {{ color: var(--muted); font-size: .875rem; }}
    </style>
  </head>
  <body>
    <main>
      <h1>{esc_title} <span class="ver">{esc_version}</span></h1>
      <p class="sub">{count} active API version{"" if count == 1 else "s"}</p>
      <ul>
{list_html}
      </ul>
    </main>
  </body>
</html>
"""
