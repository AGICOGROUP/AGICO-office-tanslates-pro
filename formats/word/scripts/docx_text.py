"""Paragraph text with immutable dynamic Word fields."""
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
FIELD_TAGS = {W + "fldChar", W + "fldSimple"}

def content_nodes(paragraph):
    allowed = {W + "t", W + "tab", W + "br", W + "cr"}
    if paragraph.find(".//" + W + "fldChar") is None and paragraph.find(".//" + W + "fldSimple") is None:
        return [node for node in paragraph.iter() if node.tag in allowed
                and next((a for a in node.iterancestors() if a.tag == W + "p"), None) is paragraph]
    nodes = []
    depth = 0
    for node in paragraph.iter():
        if node.tag not in allowed and node.tag not in FIELD_TAGS:
            continue
        if next((a for a in node.iterancestors() if a.tag == W + "p"), None) is not paragraph:
            continue
        if any(a.tag == W + "fldSimple" for a in node.iterancestors()):
            continue
        if node.tag == W + "fldSimple":
            if not depth:
                nodes.append(node)
        elif node.tag == W + "fldChar":
            kind = node.get(W + "fldCharType")
            if kind == "begin":
                if not depth:
                    nodes.append(node)
                depth += 1
            elif kind == "end":
                depth = max(0, depth - 1)
        elif not depth and node.tag in allowed:
            nodes.append(node)
    return nodes

def node_texts(nodes):
    fields = 0
    values = []
    for node in nodes:
        if node.tag in FIELD_TAGS:
            fields += 1
            values.append("{{FIELD" + str(fields) + "}}")
        elif node.tag == W + "t":
            values.append(node.text or "")
        else:
            values.append("\t" if node.tag == W + "tab" else "\n")
    return values

def paragraph_text(paragraph):
    if paragraph.tag == W + "lvlText":
        return paragraph.get(W + "val", "")
    return "".join(node_texts(content_nodes(paragraph))).strip()
