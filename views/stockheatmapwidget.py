import panel as pn

pn.extension()

def panel():
    html = (
        '<iframe src="/public/stock_heatmap.html" '
        'style="width:100%;height:700px;border:none;"></iframe>'
    )
    return pn.pane.HTML(html, sizing_mode="stretch_width", height=700)
