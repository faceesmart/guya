"""Safe, platform-independent file operations for the assistant."""

import json
import logging
import os
import re
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

from ..models import ActionOutcome, SearchMatch
from ..normalizer import filename_keys, filename_match_score, normalize


INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
log = logging.getLogger("Guya")
GENERIC_SEARCH_KEYS = {
    "a",
    "an",
    "the",
    "file",
    "folder",
    "document",
    "item",
    "something",
    "فایل",
    "پوشه",
    "سند",
    "چیز",
}
SKIPPED_DIRECTORY_SUFFIXES = (
    ".app",
    ".bundle",
    ".framework",
    ".pkg",
    ".plugin",
)
# Folders that only ever hold tooling output, never the user's own documents.
# Walking them wastes the candidate budget and produces noise such as
# report.go / reporter.tsx next to a real report.docx. Names a person might
# give a real folder (build, out, dist, target, env) are deliberately NOT here.
# A pruned folder is still offered as a folder candidate itself; only its
# contents are skipped.
SKIPPED_DIRECTORY_NAMES = {
    "node_modules", "venv", "__pycache__", "Library", "vendor",
    "site-packages", "Pods", "DerivedData", "bower_components",
}
# Documents live near the top of a user's folders; deep trees are code.
MAX_SEARCH_DEPTH = 6

WEBSITE_ALIASES = {
    "google": "https://www.google.com",
    "گوگل": "https://www.google.com",
    "youtube": "https://www.youtube.com",
    "you tube": "https://www.youtube.com",
    "یوتیوب": "https://www.youtube.com",
    "wikipedia": "https://www.wikipedia.org",
    "wiki pedia": "https://www.wikipedia.org",
    "ویکی پدیا": "https://www.wikipedia.org",
    "ویکیپدیا": "https://www.wikipedia.org",
    "github": "https://github.com",
    "git hub": "https://github.com",
    "گیت هاب": "https://github.com",
    "gmail": "https://mail.google.com",
    "جی میل": "https://mail.google.com",
    "openai": "https://www.openai.com",
    "open ai": "https://www.openai.com",
    "university of tehran": "https://ut.ac.ir",
    "tehran university": "https://ut.ac.ir",
    "دانشگاه تهران": "https://ut.ac.ir",
}
WEBSITE_TLDS = {
    "ai", "app", "biz", "co", "com", "dev", "edu", "gov", "info",
    "io", "ir", "me", "net", "org",
}


class SafeDesktopActions:
    """File actions restricted to user-approved roots.

    Search reads the filesystem each time, so a newly added file is immediately
    available without an index or background watcher.
    """

    APP_CANDIDATES = {}

    def __init__(self, roots=None, default_directory=None):
        home = Path.home()
        requested = roots or [home / "Desktop", home / "Documents", home / "Downloads"]
        self.roots = [Path(item).expanduser().resolve() for item in requested]
        # Keep every configured root. A folder that does not exist at startup
        # may be created later and must become searchable immediately.
        self.search_roots = self.roots

        default = Path(default_directory).expanduser() if default_directory else home / "Documents"
        self.default_directory = default.resolve()
        if not self._is_allowed(self.default_directory):
            self.default_directory = self.search_roots[0]
        # Search the creation/default folder first. This keeps common
        # create→close→reopen flows fast even when Desktop contains projects
        # with many files.
        self.search_roots = [self.default_directory] + [
            root for root in self.roots if root != self.default_directory
        ]
        self.target_app = None

    def set_target_app(self, target_app) -> None:
        """Remember the application active when the assistant hotkey was pressed."""
        self.target_app = target_app

    def create_word_document(self, name: Optional[str]) -> ActionOutcome:
        try:
            safe_name = self._safe_name(name or self._timestamped_name("Guya document"))
        except ValueError:
            return self._invalid_name()
        if not safe_name.lower().endswith(".docx"):
            safe_name += ".docx"
        path = self.default_directory / safe_name
        if path.exists():
            return self._failure(
                f"A file named {path.name} already exists.",
                f"فایلی با نام {path.name} از قبل وجود دارد.",
            )
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._write_minimal_docx(path)
            return self._success(
                f"Created {path.name}.",
                f"فایل {path.name} ساخته شد.",
                path,
            )
        except Exception as exc:
            return self._failure(
                f"Could not create the Word file: {exc}",
                f"ساخت فایل ورد ممکن نشد: {exc}",
            )

    def create_text_file(self, name: Optional[str]) -> ActionOutcome:
        try:
            safe_name = self._safe_name(name or self._timestamped_name("Guya note"))
        except ValueError:
            return self._invalid_name()
        if not Path(safe_name).suffix:
            safe_name += ".txt"
        path = self.default_directory / safe_name
        if path.exists():
            return self._failure(
                f"A file named {path.name} already exists.",
                f"فایلی با نام {path.name} از قبل وجود دارد.",
            )
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch(exist_ok=False)
            return self._success(
                f"Created {path.name}.",
                f"فایل {path.name} ساخته شد.",
                path,
            )
        except Exception as exc:
            return self._failure(
                f"Could not create the file: {exc}",
                f"ساخت فایل ممکن نشد: {exc}",
            )

    def create_folder(self, name: Optional[str]) -> ActionOutcome:
        try:
            safe_name = self._safe_name(name or self._timestamped_name("Guya folder"))
        except ValueError:
            return self._invalid_name()
        path = self.default_directory / safe_name
        if path.exists():
            return self._failure(
                f"{path.name} already exists.",
                f"{path.name} از قبل وجود دارد.",
            )
        try:
            path.mkdir(parents=False)
            return self._success(
                f"Created the folder {path.name}.",
                f"پوشه {path.name} ساخته شد.",
                path,
            )
        except Exception as exc:
            return self._failure(
                f"Could not create the folder: {exc}",
                f"ساخت پوشه ممکن نشد: {exc}",
            )

    def search_matches(
        self,
        query: str,
        kind: Optional[str] = None,
        limit: int = 20,
    ) -> List[SearchMatch]:
        """Search live folders and return deterministic, ranked fuzzy matches."""
        query = (query or "").strip()
        if not query:
            return []
        started_at = time.perf_counter()
        full_key, stem_key, extension = filename_keys(query)
        if len(stem_key) < 2 or stem_key in GENERIC_SEARCH_KEYS:
            log.info(
                "Assistant file search rejected: query=%r canonical=%r reason=too_generic",
                query,
                full_key,
            )
            return []
        matches = []
        total_inspected = 0
        limited_roots = []
        max_candidates_per_root = 20_000
        for root in self.search_roots:
            if not root.exists():
                continue
            inspected = 0
            root_limit_reached = False
            try:
                root_depth = len(Path(root).parts)
                for current, dirs, files in os.walk(root):
                    depth = len(Path(current).parts) - root_depth
                    visible_dirs = [
                        directory
                        for directory in dirs
                        if not directory.startswith(".")
                        and not directory.casefold().endswith(SKIPPED_DIRECTORY_SUFFIXES)
                    ]
                    # Descend only into folders that can hold documents.
                    if depth >= MAX_SEARCH_DEPTH:
                        dirs[:] = []
                    else:
                        dirs[:] = [d for d in visible_dirs if d not in SKIPPED_DIRECTORY_NAMES]
                    candidates: Iterable[str]
                    if kind == "folder":
                        candidates = visible_dirs
                    elif kind == "file":
                        candidates = files
                    else:
                        candidates = list(visible_dirs) + list(files)
                    for name in candidates:
                        inspected += 1
                        total_inspected += 1
                        if inspected > max_candidates_per_root:
                            root_limit_reached = True
                            limited_roots.append(str(root))
                            break
                        score, exact = filename_match_score(query, name)
                        if score >= 0.58:
                            path = Path(current) / name
                            if self._is_allowed(path):
                                matches.append(SearchMatch(path, score, exact))
                    if root_limit_reached:
                        break
            except OSError:
                continue
        ranked = self._rank_matches(matches, limit)
        diagnostic = {
            "query": query,
            "canonical": full_key,
            "stem": stem_key,
            "extension": extension,
            "kind": kind or "any",
            "inspected": total_inspected,
            "elapsed_ms": round((time.perf_counter() - started_at) * 1000),
            "limited_roots": limited_roots,
            "top": [
                {
                    "path": str(match.path),
                    "score": round(match.score, 3),
                    "exact": match.exact,
                }
                for match in ranked[:5]
            ],
        }
        log.info(
            "Assistant file search: %s",
            json.dumps(diagnostic, ensure_ascii=False),
        )
        return ranked

    def search(self, query: str, kind: Optional[str] = None, limit: int = 20) -> List[Path]:
        return [
            match.path
            for match in self.search_matches(query, kind=kind, limit=limit)
        ]

    def find_one(self, query: str, kind: Optional[str] = None) -> Optional[Path]:
        matches = self.search(query, kind=kind, limit=20)
        return matches[0] if matches else None

    def open_named(self, query: str, kind: Optional[str] = None) -> ActionOutcome:
        path = self.find_one(query, kind=kind)
        if path is None:
            return self._failure(
                f"I could not find {query}.",
                f"{query} پیدا نشد.",
            )
        return self.open_path(path)

    def rename(self, path: Path, new_name: str) -> ActionOutcome:
        try:
            path = Path(path).expanduser().resolve()
        except (OSError, RuntimeError):
            return self._failure(
                "That item is outside Guya's allowed folders or no longer exists.",
                "این مورد خارج از پوشه‌های مجاز گویا است یا دیگر وجود ندارد.",
            )
        if not self._is_allowed(path) or not path.exists():
            return self._failure(
                "That item is outside Guya's allowed folders or no longer exists.",
                "این مورد خارج از پوشه‌های مجاز گویا است یا دیگر وجود ندارد.",
            )
        try:
            safe_name = self._safe_name(new_name)
        except ValueError:
            return self._invalid_name()
        if path.is_file() and path.suffix and not Path(safe_name).suffix:
            safe_name += path.suffix
        destination = path.with_name(safe_name)
        if not self._is_allowed(destination):
            return self._failure(
                "That new name is not allowed.",
                "این نام جدید مجاز نیست.",
            )
        if destination.exists():
            return self._failure(
                f"{destination.name} already exists. Nothing was changed.",
                f"{destination.name} از قبل وجود دارد و تغییری انجام نشد.",
            )
        try:
            renamed = path.rename(destination)
            return self._success(
                f"Renamed it to {renamed.name}.",
                f"نام به {renamed.name} تغییر کرد.",
                renamed,
            )
        except Exception as exc:
            return self._failure(
                f"Could not rename it: {exc}",
                f"تغییر نام ممکن نشد: {exc}",
            )

    def open_path(self, path: Path) -> ActionOutcome:
        raise NotImplementedError

    def open_app(self, app: str) -> ActionOutcome:
        raise NotImplementedError

    def save_current(self) -> ActionOutcome:
        """Ask the active application to save using its standard shortcut."""
        raise NotImplementedError

    def close_current(self) -> ActionOutcome:
        """Close the active window, allowing the application to show save prompts."""
        raise NotImplementedError

    def search_web(self, query: str, app: Optional[str] = None) -> ActionOutcome:
        """Open a safe HTTPS search URL; never execute page content or scripts."""
        raise NotImplementedError

    def open_website(self, target: str, app: Optional[str] = None) -> ActionOutcome:
        """Open a known website or validated HTTPS domain."""
        raise NotImplementedError

    def browser_control(self, action: str) -> ActionOutcome:
        """Move an already-focused browser without inspecting page content."""
        raise NotImplementedError

    def speak(self, text: str, language: str = "en") -> None:
        """Speak feedback if the OS provides a free built-in voice."""

    def stop_speaking(self) -> None:
        """Stop assistant feedback immediately, when supported."""

    def _is_allowed(self, path: Path) -> bool:
        try:
            candidate = Path(path).expanduser().resolve()
        except (OSError, RuntimeError):
            # A symlink loop raises RuntimeError on Python 3.11; anything that
            # cannot be resolved is treated as outside the boundary.
            return False
        for root in self.roots:
            try:
                candidate.relative_to(root)
                return True
            except ValueError:
                continue
        return False

    @staticmethod
    def safe_website_url(target: str) -> Optional[str]:
        """Resolve a spoken site name/domain to an HTTPS-only URL.

        This intentionally accepts no paths, query strings, ports, schemes,
        JavaScript, or numbered-result requests. Arbitrary page interaction is
        outside Guya V1's safety boundary.
        """
        value = normalize(target)
        value = re.sub(
            r"^(?:https?|www|website|site|وب سایت|سایت)\s+",
            "",
            value,
        ).strip()
        value = re.sub(r"\s+(?:dot|دات|نقطه)\s+", " ", value)
        if not value:
            return None

        aliased = WEBSITE_ALIASES.get(value)
        if aliased:
            return aliased

        tokens = value.split()
        if (
            len(tokens) < 2
            or tokens[-1] not in WEBSITE_TLDS
            or not all(re.fullmatch(r"[a-z0-9-]+", token) for token in tokens)
        ):
            return None
        if any(
            not token
            or len(token) > 63
            or token.startswith("-")
            or token.endswith("-")
            for token in tokens
        ):
            return None

        host = ".".join(tokens)
        if len(host) > 253:
            return None
        return f"https://{host}"

    @staticmethod
    def _safe_name(name: str) -> str:
        result = INVALID_FILENAME.sub("", (name or "")).strip().strip(".")
        if not result or result in (".", ".."):
            raise ValueError("The name is empty or invalid")
        return result[:180]

    @staticmethod
    def _timestamped_name(prefix: str) -> str:
        return f"{prefix} {datetime.now().strftime('%Y-%m-%d %H-%M-%S')}"

    @staticmethod
    def _rank_matches(
        matches: List[SearchMatch],
        limit: int,
    ) -> List[SearchMatch]:
        unique = {}
        for match in matches:
            previous = unique.get(match.path)
            if previous is None or match.score > previous.score:
                unique[match.path] = match
        return sorted(
            unique.values(),
            key=lambda match: (
                -match.score,
                not match.exact,
                len(match.path.name),
                str(match.path).casefold(),
            ),
        )[:limit]

    @staticmethod
    def _write_minimal_docx(path: Path) -> None:
        """Create a valid empty DOCX using only Python's standard library."""
        files = {
            "[Content_Types].xml": (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/word/document.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                "</Types>"
            ),
            "_rels/.rels": (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                'Target="word/document.xml"/>'
                "</Relationships>"
            ),
            "word/document.xml": (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body><w:p/><w:sectPr/></w:body></w:document>"
            ),
        }
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for filename, content in files.items():
                archive.writestr(filename, content)

    @staticmethod
    def _success(message_en: str, message_fa: str, path: Optional[Path] = None) -> ActionOutcome:
        return ActionOutcome(True, message_en, message_fa, path)

    @staticmethod
    def _failure(message_en: str, message_fa: str) -> ActionOutcome:
        return ActionOutcome(False, message_en, message_fa)

    @staticmethod
    def _invalid_name() -> ActionOutcome:
        return ActionOutcome(
            False,
            "That name is empty or invalid.",
            "این نام خالی یا نامعتبر است.",
        )
