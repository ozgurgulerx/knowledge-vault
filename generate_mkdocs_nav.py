#!/usr/bin/env python3
"""Generate mkdocs.yml nav from the folder structure of the useful/ directory.

Usage:
    python3 generate_mkdocs_nav.py [--serve] [--port PORT]

Scans all .md files, builds a nav tree grouped by folder, writes mkdocs.yml
to the PARENT directory (so mkdocs.yml is not inside docs_dir), and optionally
starts mkdocs serve.
"""

import re
import sys
import yaml
import subprocess
from pathlib import Path

DOCS_DIR = Path(__file__).parent
# mkdocs.yml lives one level up so it's not inside docs_dir
MKDOCS_YML = DOCS_DIR.parent / "mkdocs.yml"

# Folders to skip
SKIP_DIRS = {".git", "__pycache__", ".claude", "node_modules", "site", "site-preview"}

# Acronyms to fix after .title() (case-insensitive match → replacement)
ACRONYMS = {
    "Ai": "AI",
    "Llm": "LLM",
    "Llms": "LLMs",
    "Gpu": "GPU",
    "Tpu": "TPU",
    "Ux": "UX",
    "Ui": "UI",
    "Rl": "RL",
    "Rag": "RAG",
    "Roi": "ROI",
    "Gpt5": "GPT-5",
    "Gpt": "GPT",
    "Ml": "ML",
    "Mcp": "MCP",
    "Gcp": "GCP",
    "B2C": "B2C",
    "B2B": "B2B",
    "Genai": "GenAI",
    "Evalops": "EvalOps",
}

# Tab grouping: tab name → list of folder name patterns (matched after prefix stripping)
TAB_GROUPS = [
    (
        "Strategy",
        [
            "Market Intelligence",
            "investing",
            "atlas",
            "graph atlas",
        ],
    ),
    (
        "LLMs",
        [
            "LLMs",
            "LLM Landscape and Trends",
            "LLM Architectures",
            "LLM Pre-training",
            "LLM Post-training",
            "Quantization and Distillation",
            "LLM Reasoning",
            "Multimodal LLMs",
            "Multimodal + Real-time",
        ],
    ),
    (
        "RL",
        [
            "RL",
        ],
    ),
    (
        "Data-Patterns",
        [
            "RAG",
            "RAG, Knowledge, Memory",
            "Graph",
            "Data & Knowledge Engineering for GenAI",
        ],
    ),
    (
        "InferenceEng",
        [
            "Systems & Inference Engineering",
            "Hardware",
            "Attention Mechanisms",
            "Inference Engineering Commands",
        ],
    ),
    (
        "LLMOps",
        [
            "AI Evals + GenAI Ops",
        ],
    ),
    (
        "AI Agents",
        [
            "Agents & Copilot Systems",
            "Agents & Tools",
            "Codex",
        ],
    ),
    (
        "AI Products",
        [
            "AI Products + UX UI",
            "AI UX",
        ],
    ),
    (
        "AI Startups",
        [
            "startups",
        ],
    ),
    (
        "AI Safety",
        [
            "AI Security",
            "AI Governance",
            "AI Safety & Alignment Science",
        ],
    ),
]


# Display name overrides for folders that don't clean up well
FOLDER_DISPLAY_OVERRIDES = {
    "research": "Research",
    "investing": "Investing",
    "startups": "Startups",
    "atlas": "Atlas",
    "graph atlas": "Graph Atlas",
    "xxx 00 - General talk points": "Market Intelligence",
    "xxx 03a - Agents & Copilot Systems": "Agents & Tools",
    "inference_engineering_commands": "Inference Engineering Commands",
}


def folder_display_name(name: str) -> str:
    """Clean up folder name for display."""
    if name in FOLDER_DISPLAY_OVERRIDES:
        return FOLDER_DISPLAY_OVERRIDES[name]
    cleaned = re.sub(r"^xxx?\s*\d+[a-z]?(?:-\d+)?\s*-\s*", "", name)
    cleaned = re.sub(r"^xx\s*\d+\s*", "", cleaned)
    return cleaned.strip() or name.strip()


def fix_acronyms(text: str) -> str:
    """Fix common acronyms after .title() mangling."""
    for wrong, right in ACRONYMS.items():
        text = re.sub(r"\b" + re.escape(wrong) + r"\b", right, text)
    return text


def file_display_name(filepath: Path) -> str:
    """Extract a readable title from the filename."""
    name = filepath.stem
    name = re.sub(r"^\d{6}_?", "", name)
    name = name.replace("_", " ").replace("-", " ")
    name = name.strip().title()
    name = fix_acronyms(name)
    return name if name else filepath.stem


def build_section(folder: Path) -> tuple:
    """Build a nav section for a folder. Returns (display_name, items) or None."""
    md_files = sorted(folder.glob("*.md"))
    sub_dirs = sorted(
        [d for d in folder.iterdir() if d.is_dir() and d.name not in SKIP_DIRS]
    )

    if not md_files and not sub_dirs:
        return None

    section_name = folder_display_name(folder.name)
    section_name = fix_acronyms(section_name)
    items = []

    # Add direct .md files first
    for f in md_files:
        rel_path = f.relative_to(DOCS_DIR)
        items.append({file_display_name(f): str(rel_path)})

    # Add subdirectories as nested sections
    for sub in sub_dirs:
        sub_md_files = sorted(sub.glob("*.md"))
        if not sub_md_files:
            continue
        sub_name = folder_display_name(sub.name)
        sub_name = fix_acronyms(sub_name)
        sub_items = []
        for f in sub_md_files:
            rel_path = f.relative_to(DOCS_DIR)
            sub_items.append({file_display_name(f): str(rel_path)})
        items.append({sub_name: sub_items})

    if not items:
        return None

    return (section_name, items)


def build_nav() -> list:
    """Walk the docs directory and build mkdocs nav structure with tabs."""
    nav = [{"Home": "index.md"}]

    # Collect all folders
    folders = sorted(
        [
            d
            for d in DOCS_DIR.iterdir()
            if d.is_dir() and d.name not in SKIP_DIRS and not d.name.startswith(".")
        ],
        key=lambda d: d.name.lower(),
    )

    # Build sections keyed by display name
    sections = {}
    for folder in folders:
        if folder.name == "site":
            continue
        result = build_section(folder)
        if result:
            display_name, items = result
            sections[display_name] = items
            # Also store under raw folder name for matching
            sections[folder.name] = items

    # Root .md files (non-index) go under Notes
    root_files = sorted(DOCS_DIR.glob("*.md"))
    root_items = []
    for f in root_files:
        if f.name == "index.md":
            continue
        root_items.append({file_display_name(f): f.name})

    # Build tabbed nav
    placed = set()
    for tab_name, folder_patterns in TAB_GROUPS:
        tab_sections = []
        for pattern in folder_patterns:
            # Try matching against display names, raw folder names, and overrides
            for folder in folders:
                display = folder_display_name(folder.name)
                display_fixed = fix_acronyms(display)
                raw = folder.name
                if pattern in (display, display_fixed, raw):
                    key = (
                        display_fixed
                        if display_fixed in sections
                        else (display if display in sections else raw)
                    )
                    if key in sections and key not in placed:
                        tab_sections.append({display_fixed: sections[key]})
                        placed.add(key)
                        placed.add(raw)
                        placed.add(display)
                        placed.add(display_fixed)
                        break
        if tab_sections:
            nav.append({tab_name: tab_sections})

    # Any unplaced sections go under "Other"
    other = []
    for folder in folders:
        display = folder_display_name(folder.name)
        display = fix_acronyms(display)
        if display not in placed and folder.name not in placed:
            result = build_section(folder)
            if result:
                other.append({result[0]: result[1]})
    if root_items:
        other.insert(0, {"Notes": root_items})
    if other:
        nav.append({"Research & Others": other})

    return nav


def generate_config(nav: list) -> dict:
    """Build full mkdocs.yml config."""
    return {
        "site_name": "Knowledge Base",
        "site_description": "Personal knowledge base - distilled notes",
        "docs_dir": str(DOCS_DIR),
        "site_dir": str(DOCS_DIR / "site"),
        "theme": {
            "name": "material",
            "custom_dir": str(DOCS_DIR.parent / "overrides"),
            "palette": [
                {
                    "scheme": "slate",
                    "primary": "indigo",
                    "accent": "cyan",
                    "toggle": {"icon": "material/brightness-7", "name": "Light mode"},
                },
                {
                    "scheme": "default",
                    "primary": "indigo",
                    "accent": "cyan",
                    "toggle": {"icon": "material/brightness-4", "name": "Dark mode"},
                },
            ],
            "features": [
                "navigation.instant",
                "navigation.tabs",
                "navigation.tabs.sticky",
                "navigation.top",
                "navigation.indexes",
                "search.suggest",
                "search.highlight",
                "content.code.copy",
            ],
        },
        "plugins": ["search"],
        "markdown_extensions": [
            "tables",
            "admonition",
            "pymdownx.details",
            {
                "pymdownx.superfences": {
                    "custom_fences": [
                        {
                            "name": "mermaid",
                            "class": "mermaid",
                            "format": "!!python/name:pymdownx.superfences.fence_code_format",
                        }
                    ]
                }
            },
            "pymdownx.highlight",
            "pymdownx.inlinehilite",
            "attr_list",
            "md_in_html",
            {"toc": {"permalink": True}},
        ],
        "nav": nav,
    }


def write_config():
    """Generate and write mkdocs.yml."""
    nav = build_nav()
    config = generate_config(nav)

    with open(MKDOCS_YML, "w") as f:
        yaml.dump(
            config, f, default_flow_style=False, sort_keys=False, allow_unicode=True
        )

    print(f"Generated {MKDOCS_YML} with {len(nav)} sections")
    return config


def main():
    config = write_config()

    if "--serve" in sys.argv:
        port = "8000"
        if "--port" in sys.argv:
            idx = sys.argv.index("--port")
            port = sys.argv[idx + 1]
        print(f"\nStarting mkdocs serve on http://localhost:{port}")
        subprocess.run(
            ["mkdocs", "serve", "-f", str(MKDOCS_YML), "-a", f"localhost:{port}"],
        )


if __name__ == "__main__":
    main()
