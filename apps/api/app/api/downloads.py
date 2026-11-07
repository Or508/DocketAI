from urllib.parse import quote


def content_disposition(filename: str, disposition: str = "attachment") -> str:
    try:
        filename.encode("ascii")
    except UnicodeEncodeError:
        return f"{disposition}; filename*=utf-8''{quote(filename)}"
    cleaned = filename.replace("\\", "\\\\").replace('"', r"\"")
    return f'{disposition}; filename="{cleaned}"'
