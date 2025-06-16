# views/chart.py

import panel as pn

pn.extension()

def panel():
    html = """
    <iframe
      src="/public/lightweight_chart.html"
      sandbox="allow-scripts allow-same-origin"
      width="100%" height="600"
      style="border:none;"
    ></iframe>
    """
    return pn.pane.HTML(html, sizing_mode="stretch_width", height=600)
