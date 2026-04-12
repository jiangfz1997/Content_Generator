from app.core.workflow import global_graph
print(global_graph.get_graph().draw_mermaid())
png_bytes = global_graph.get_graph().draw_mermaid_png()
with open("graph.png", "wb") as f:
    f.write(png_bytes)