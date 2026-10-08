"""
Centralized constants for TwinScope.

This module stores all global, application-level, file extension,
I/O, search, merge, and UI constants used across the application.
"""

from __future__ import annotations
import re
from typing import List, Set, Tuple

# =============================================================================
# Repository & Release Details
# =============================================================================
REPO_OWNER: str = "dipta-roy"
REPO_NAME: str = "TwinScope"
GITHUB_API_URL: str = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"

# =============================================================================
# Application Metadata
# =============================================================================
APP_NAME: str = "TwinScope"
APP_DISPLAY_NAME: str = "TwinScope"
APP_VERSION: str = "1.2.1"
APP_ORGANIZATION: str = "TwinScope"
APP_DOMAIN: str = "dipta-roy.github.io/TwinScope"
APP_DESCRIPTION: str = "Professional File Comparison Tool"
APP_AUTHOR: str = "Dipta Roy"
UPGRADE_CODE: str = "{A8271C53-96B3-4197-8CFD-ACAEB2460786}"

APP_ABOUT_DESCRIPTION: str = (
    f"**{APP_NAME}** is a cross-platform file and folder comparison tool inspired by Beyond Compare. "
    "Built with Python, it provides a clean, responsive interface for comparing text files, binary files, images, and entire directory trees."
)

# Directory Names
RESOURCES_DIR_NAME: str = "resources"
ICONS_DIR_NAME: str = "icons"
THEMES_DIR_NAME: str = "themes"
LOGS_DIR_NAME: str = "logs"

# =============================================================================
# File Extensions
# =============================================================================
TEXT_EXTENSIONS: Set[str] = {
    '.txt', '.md', '.rst', '.json', '.xml', '.html', '.htm',
    '.css', '.js', '.ts', '.py', '.rb', '.java', '.c', '.cpp',
    '.h', '.hpp', '.cs', '.go', '.rs', '.swift', '.kt', '.scala',
    '.sh', '.bash', '.zsh', '.fish', '.ps1', '.bat', '.cmd',
    '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf',
    '.sql', '.graphql', '.proto',
    '.vue', '.jsx', '.tsx', '.svelte',
    '.r', '.R', '.jl', '.m', '.matlab',
    '.tex', '.bib', '.sty',
    '.csv', '.tsv',
    '.log', '.diff', '.patch',
}

IMAGE_EXTENSIONS: Set[str] = {
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.tif',
    '.webp', '.ico', '.svg',
}

BINARY_EXTENSIONS: Set[str] = {
    '.exe', '.dll', '.so', '.dylib', '.bin', '.dat',
    '.zip', '.tar', '.gz', '.bz2', '.xz', '.7z', '.rar',
    '.mp3', '.mp4', '.avi', '.mkv', '.mov', '.wav', '.flac',
    '.ttf', '.otf', '.woff', '.woff2',
}

DOC_EXTENSIONS: Set[str] = {
    '.pdf', '.docx', '.xlsx', '.pptx',
}

# =============================================================================
# File I/O & Encodings
# =============================================================================
DEFAULT_ENCODINGS: List[str] = [
    'utf-8', 'utf-8-sig', 'utf-16', 'utf-16-le', 'utf-16-be',
    'ascii', 'iso-8859-1', 'cp1252', 'latin-1',
]

BINARY_SIGNATURES: List[bytes] = [
    b'\x00',           # Null byte (strong indicator)
    b'\x89PNG',        # PNG
    b'\xff\xd8\xff',   # JPEG
    b'GIF8',           # GIF
    b'PK\x03\x04',     # ZIP
    b'\x1f\x8b',       # GZIP
    b'%PDF',           # PDF
    b'\x7fELF',        # ELF
    b'MZ',             # Windows executable
]

DEFAULT_BINARY_CHECK_SIZE: int = 8192

COMMON_ENCODINGS: List[Tuple[str, str]] = [
    ("UTF-8", "utf-8"),
    ("UTF-16", "utf-16"),
    ("ASCII", "ascii"),
    ("Latin-1", "iso-8859-1"),
    ("Windows-1252", "cp1252"),
    ("UTF-8 BOM", "utf-8-sig"),
    ("UTF-16 LE", "utf-16-le"),
    ("UTF-16 BE", "utf-16-be"),
]

LINE_ENDINGS: List[Tuple[str, str]] = [
    ("LF (Unix)", "lf"),
    ("CRLF (Windows)", "crlf"),
    ("CR (Mac)", "cr"),
    ("Auto", "auto"),
]

# =============================================================================
# Limits & UI History
# =============================================================================
MAX_PATH_HISTORY: int = 10
MAX_SEARCH_HISTORY: int = 20
MAX_SEARCH_MATCHES: int = 10000

# =============================================================================
# Merge Conflict Markers
# =============================================================================
CONFLICT_MARKER_START_PATTERN: re.Pattern = re.compile(r'^<{7}\s*(.*)$')
CONFLICT_MARKER_BASE_PATTERN: re.Pattern = re.compile(r'^\|{7}\s*(.*)$')
CONFLICT_MARKER_SEP_PATTERN: re.Pattern = re.compile(r'^={7}\s*$')
CONFLICT_MARKER_END_PATTERN: re.Pattern = re.compile(r'^>{7}\s*(.*)$')

# =============================================================================
# Binary Patch
# =============================================================================
BINARY_PATCH_MAGIC: bytes = b'BPATCH01'

# =============================================================================
# UI View & Tree Columns
# =============================================================================
FILE_TREE_COLUMNS: List[str] = [
    'Name', 'Status', '% Match', 'Left Size', 'Right Size', 'Left Modified', 'Right Modified',
]

# =============================================================================
# Folder Scanner & Comparison Defaults
# =============================================================================
DEFAULT_EXCLUDE_PATTERNS: List[str] = [
    '.git', '.svn', '.hg', '.bzr',
    '__pycache__', '*.pyc', '*.pyo',
    'node_modules', '.npm',
    '.DS_Store', 'Thumbs.db', 'desktop.ini',
    '*.swp', '*.swo', '*~',
    '.idea', '.vscode', '*.suo', '*.user',
]