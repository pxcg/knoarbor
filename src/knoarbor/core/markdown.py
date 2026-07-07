from __future__ import annotations

import re
from typing import Any

from knoarbor.core.errors import PolicyRejection


MAX_INDEX_SUMMARY_LENGTH = 180


def inline_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def compact_inline_text(value: str, max_length: int = MAX_INDEX_SUMMARY_LENGTH) -> str:
    compacted = inline_text(value)
    if len(compacted) <= max_length:
        return compacted
    return compacted[: max_length - 1].rstrip() + "..."


def parse_frontmatter(content: str) -> dict[str, str]:
    match = re.search(r"^---\s*$\n(?P<body>.*?)(?=^---\s*$)", content, flags=re.MULTILINE | re.DOTALL)
    if not match:
        return {}

    metadata: dict[str, str] = {}
    for line in match.group("body").splitlines():
        if ":" not in line or line.startswith(" "):
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip()
    return metadata


def extract_heading(content: str, fallback: str) -> str:
    match = re.search(r"^#\s+(.+)$", content, flags=re.MULTILINE)
    return compact_inline_text(match.group(1), 80) if match else fallback


def update_heading(content: str, title: str) -> str:
    replacement = f"# {title.strip()}"
    if re.search(r"^#\s+.+$", content, flags=re.MULTILINE):
        return re.sub(r"^#\s+.+$", lambda _match: replacement, content, count=1, flags=re.MULTILINE)
    return replacement + "\n\n" + content.lstrip()


def extract_section(content: str, heading: str) -> str:
    pattern = rf"^##\s+{re.escape(heading)}\s*$\n(?P<body>.*?)(?=^##\s+|\Z)"
    match = re.search(pattern, content, flags=re.MULTILINE | re.DOTALL)
    return match.group("body").strip() if match else ""


def replace_section(content: str, heading: str, body: str) -> str:
    section = f"## {heading}\n\n{body.strip()}\n"
    pattern = rf"^##\s+{re.escape(heading)}\s*$\n.*?(?=^##\s+|\Z)"
    if re.search(pattern, content, flags=re.MULTILINE | re.DOTALL):
        return re.sub(pattern, lambda _match: section, content, count=1, flags=re.MULTILINE | re.DOTALL)
    return content.rstrip() + "\n\n" + section


def update_frontmatter_value(content: str, key: str, value: str) -> str:
    frontmatter_match = re.search(r"^---\s*\n(?P<body>.*?)(?P<closing>^---\s*$)", content, flags=re.MULTILINE | re.DOTALL)
    if not frontmatter_match:
        return content
    pattern = rf"^({re.escape(key)}:\s*).*$"
    body = frontmatter_match.group("body")
    if re.search(pattern, body, flags=re.MULTILINE):
        updated_body = re.sub(pattern, lambda match: f"{match.group(1)}{value}", body, count=1, flags=re.MULTILINE)
    else:
        updated_body = body.rstrip() + f"\n{key}: {value}\n"
    return content[: frontmatter_match.start("body")] + updated_body + content[frontmatter_match.start("closing") :]


def extract_list_items(section_body: str) -> list[str]:
    items: list[str] = []
    for line in section_body.splitlines():
        if not line.startswith("- "):
            continue
        item = line[2:].strip()
        if item and not item.startswith("暂无"):
            items.append(item)
    return items


def normalize_list_item(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def wiki_target_key(value: str) -> str:
    target = value.strip()
    if "|" in target:
        target = target.split("|", 1)[0].strip()
    target = target.split("#", 1)[0].strip()
    if target.endswith(".md"):
        target = target[:-3]
    return target.casefold()


def format_wikilink(target: str, alias: str | None = None) -> str:
    clean_target = target.strip()
    clean_alias = (alias or "").strip()
    return f"[[{clean_target}|{clean_alias}]]" if clean_alias else f"[[{clean_target}]]"


def render_list_section(items: list[str], empty_text: str) -> str:
    return "\n".join(f"- {item}" for item in items) if items else f"- {empty_text}"


def append_to_section(content: str, heading: str, body: str, subsection_heading: str | None = None) -> str:
    existing = extract_section(content, heading)
    incoming = body.strip()
    if not incoming:
        return content
    if incoming in existing:
        return content
    if subsection_heading:
        incoming = f"### {subsection_heading.strip()}\n\n{incoming}"
    section_body = (existing.rstrip() + "\n\n" + incoming).strip() if existing else incoming
    return replace_section(content, heading, section_body)


def validate_body_markdown(markdown: str, field_name: str) -> str:
    body = markdown.strip()
    if re.search(r"^#{1,2}\s+\S+", body, flags=re.MULTILINE):
        raise PolicyRejection(f"{field_name} must not contain H1/H2 headings")
    if has_unclosed_fenced_code_blocks(body):
        raise PolicyRejection(f"{field_name} contains an unclosed fenced code block")
    return body


def normalize_embedded_body_markdown(markdown: str, field_name: str) -> str:
    body = markdown.strip()
    return re.sub(r"^#{1,2}(\s+\S+)", r"###\1", body, flags=re.MULTILINE)


def has_unclosed_fenced_code_blocks(markdown: str) -> bool:
    fence_stack: list[str] = []
    for line in markdown.splitlines():
        match = re.match(r"^\s*(```+|~~~+)", line)
        if not match:
            continue
        fence = match.group(1)
        marker = fence[0]
        if fence_stack and fence_stack[-1][0] == marker and len(fence) >= len(fence_stack[-1]):
            fence_stack.pop()
        else:
            fence_stack.append(fence)
    return bool(fence_stack)


def adjacent_duplicate_headings(content: str) -> list[dict[str, Any]]:
    duplicates: list[dict[str, Any]] = []
    lines = content.splitlines()
    for index, line in enumerate(lines):
        current = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if not current:
            continue
        next_index = index + 1
        while next_index < len(lines) and not lines[next_index].strip():
            next_index += 1
        if next_index >= len(lines):
            continue
        following = re.match(r"^(#{1,6})\s+(.+?)\s*$", lines[next_index])
        if (
            following
            and current.group(1) == following.group(1)
            and normalize_heading_text(current.group(2)) == normalize_heading_text(following.group(2))
        ):
            duplicates.append(
                {
                    "heading": current.group(2).strip(),
                    "level": len(current.group(1)),
                    "first_line": index + 1,
                    "second_line": next_index + 1,
                }
            )
    return duplicates


def remove_adjacent_duplicate_headings(content: str) -> tuple[str, list[dict[str, Any]]]:
    lines = content.splitlines()
    output: list[str] = []
    removed: list[dict[str, Any]] = []
    index = 0
    while index < len(lines):
        current = re.match(r"^(#{1,6})\s+(.+?)\s*$", lines[index])
        if current:
            next_index = index + 1
            while next_index < len(lines) and not lines[next_index].strip():
                next_index += 1
            if next_index < len(lines):
                following = re.match(r"^(#{1,6})\s+(.+?)\s*$", lines[next_index])
                if (
                    following
                    and current.group(1) == following.group(1)
                    and normalize_heading_text(current.group(2)) == normalize_heading_text(following.group(2))
                ):
                    removed.append(
                        {
                            "heading": current.group(2).strip(),
                            "level": len(current.group(1)),
                            "first_line": index + 1,
                            "kept_line": next_index + 1,
                        }
                    )
                    index = next_index
                    continue
        output.append(lines[index])
        index += 1
    return "\n".join(output).rstrip() + "\n", removed


def normalize_heading_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()
