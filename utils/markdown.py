def markdown_body_without_front_matter(markdown: str) -> str:
    lines = markdown.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return markdown

    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "".join(lines[index + 1:]).lstrip("\r\n")
    return markdown
