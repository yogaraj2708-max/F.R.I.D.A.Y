with open("friday_ui/core/engine.py", "r", encoding="utf-8") as f:
    for i, line in enumerate(f, 1):
        if "_handle_document_qa" in line:
            print(f"{i}: {line.strip()}")
