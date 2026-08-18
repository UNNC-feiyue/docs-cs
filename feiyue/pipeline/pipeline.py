#!/usr/bin/env python3
"""Generate one application-handbook PDF per SeaTable student.

The API token is read from SEATABLE_API_TOKEN, including from a local .env file.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)
from pypdf import PdfReader


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


REQUIRED_COLUMNS: dict[str, set[str]] = {
    "Student": {
        "s_id",
        "name",
        "term",
        "major",
        "apply_degree",
        "prefer_field",
        "program_choice",
        "gpa",
        "lang",
        "gre",
        "experience",
        "sharing",
        "applications",
    },
    "Application": {"a_id", "student", "program", "result", "submit_date", "result_date"},
    "Program": {"p_id", "university", "level", "name", "abbrv"},
    "University": {"u_id", "region", "abbrv", "name"},
}

CONTACT_CANDIDATES = (
    "contact",
    "contact_info",
    "contact information",
    "联系方式",
    "email",
    "邮箱",
    "wechat",
    "微信",
)

MAJOR_DISPLAY = {
    "CS (4+0)": "BSc Computer Science (4+0)",
    "CS (2+2)": "BSc Computer Science (2+2)",
    "CSAI (4+0)": "BSc Computer Science with Artificial Intelligence (4+0)",
    "CSAI (2+2)": "BSc Computer Science with Artificial Intelligence (2+2)",
}

RESULT_GROUPS = (
    ("Admission", {"Admit", "Chosen"}),
    ("Waitlist", {"Waitlist"}),
    ("Rejection", {"Reject"}),
)


class PipelineError(RuntimeError):
    pass


def clean_text(value: Any, *, empty: str = "") -> str:
    if value is None:
        return empty
    text = html.unescape(str(value))
    text = text.replace("\u200b", "").replace("\ufeff", "")
    for dash in ("\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2212"):
        text = text.replace(dash, "-")
    # Color emoji are not supported by the selected PDF font. Keep BMP text intact.
    text = "".join(ch for ch in text if ord(ch) <= 0xFFFF and ord(ch) not in (0xFE0E, 0xFE0F))
    return text.strip()


def is_blank(value: Any) -> bool:
    text = clean_text(value).strip().lower()
    return text in {"", "none", "n/a", "na", "/", "-"}


def format_program(level: Any, name: Any) -> str:
    """Join a program level and name without repeating an existing prefix."""
    level_text = clean_text(level)
    name_text = clean_text(name)
    if not level_text:
        return name_text
    if not name_text:
        return level_text
    if name_text.casefold() == level_text.casefold() or name_text.casefold().startswith(
        level_text.casefold() + " "
    ):
        return name_text
    return f"{level_text} {name_text}"


def link_first(value: Any) -> dict[str, Any] | None:
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    return None


def numeric_suffix(value: str) -> int:
    match = re.search(r"(\d+)$", value or "")
    return int(match.group(1)) if match else 10**12


def safe_filename(value: Any, fallback: str) -> str:
    """Return a Windows-safe filename stem while preserving Chinese characters."""
    name = clean_text(value)
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).rstrip(" .")
    if not name:
        name = fallback
    if name.casefold() in {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{i}" for i in range(1, 10)),
        *(f"lpt{i}" for i in range(1, 10)),
    }:
        name = f"_{name}"
    return name[:120].rstrip(" .") or fallback


def latex_escape(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(ch, ch) for ch in clean_text(value))


def term_sort_key(value: str) -> tuple[int, str]:
    """Sort intake terms newest first while keeping unknown labels deterministic."""
    text = clean_text(value)
    match = re.search(r"\b(\d{4})\b", text)
    return (int(match.group(1)) if match else -1, text.casefold())


def term_display(value: str) -> str:
    """Use a compact cohort label such as 2026届 in statistics tables."""
    text = clean_text(value)
    match = re.search(r"\b(\d{4})\b", text)
    return f"{match.group(1)}届" if match else text


def build_offer_statistics(
    students: list[dict[str, Any]],
    applications: list[dict[str, Any]],
    programs: list[dict[str, Any]],
    universities: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, dict[str, int]]], list[str]]:
    """Count Admit/Chosen application rows by region, university, and term."""
    student_term = {
        row["_id"]: clean_text(row.get("term"))
        for row in students
        if clean_text(row.get("term"))
    }
    program_by_id = {row["_id"]: row for row in programs}
    university_by_id = {row["_id"]: row for row in universities}
    counts: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(int))
    )
    terms = set(student_term.values())

    for application in applications:
        if clean_text(application.get("result")) not in {"Admit", "Chosen"}:
            continue
        student_link = link_first(application.get("student"))
        program_link = link_first(application.get("program"))
        term = student_term.get(student_link["row_id"], "") if student_link else ""
        program = program_by_id.get(program_link["row_id"]) if program_link else None
        university_link = link_first(program.get("university")) if program else None
        university = (
            university_by_id.get(university_link["row_id"])
            if university_link
            else None
        )
        if not term or not university:
            continue

        region = clean_text(university.get("region"))
        university_name = clean_text(university.get("name"))
        if not region or not university_name:
            continue
        counts[region][university_name][term] += 1

    ordered_terms = sorted(terms, key=term_sort_key, reverse=True)
    normalized = {
        region: {
            university: dict(term_counts)
            for university, term_counts in universities_by_name.items()
        }
        for region, universities_by_name in counts.items()
    }
    return normalized, ordered_terms


def offer_table_tex(
    region: str,
    university_counts: dict[str, dict[str, int]],
    terms: list[str],
) -> list[str]:
    """Return a bordered, page-breaking Offer table below a region title."""
    if not university_counts or not terms:
        return []

    column_count = len(terms) + 1
    name_width = max(4.0, 14.70 - 1.45 * column_count)
    name_column = (
        rf">{{\centering\arraybackslash}}p{{{name_width:.2f}cm}}|"
    )
    year_columns = "".join(
        r">{\centering\arraybackslash}p{1.45cm}|" for _ in range(column_count)
    )
    cohort_years: list[str] = []
    for term in reversed(terms):
        match = re.search(r"\b(\d{4})\b", term)
        if match:
            cohort_years.append(match.group(1))
    cohort_span = "--".join(cohort_years)
    table_title = (
        f"{cohort_span} 届各校 Offer 数量统计"
        if cohort_span
        else "各校 Offer 数量统计"
    )

    header_lines = [
        r"\hline",
        rf"\multirow{{2}}{{*}}{{\textbf{{学校名称}}}} & \multicolumn{{{column_count}}}{{c|}}{{\textbf{{各届 Offer 数量}}}} \\",
        rf"\cline{{2-{column_count + 1}}}",
        " & " + " & ".join(
            [rf"\textbf{{{latex_escape(term_display(term))}}}" for term in terms]
            + [r"\textbf{合计}"]
        )
        + r" \\",
        r"\hline",
    ]
    lines = [
        r"\begingroup",
        r"\small",
        r"\setlength{\tabcolsep}{4pt}",
        r"\renewcommand{\arraystretch}{1.15}",
        rf"\noindent\begin{{center}}\large\bfseries {latex_escape(table_title)}\end{{center}}",
        r"\vspace{-0.4em}",
        rf"\begin{{longtable}}{{|{name_column}{year_columns}}}",
        *header_lines,
        r"\endfirsthead",
        *header_lines,
        r"\endhead",
    ]

    rows = sorted(
        university_counts.items(),
        key=lambda item: (
            -sum(item[1].get(term, 0) for term in terms),
            item[0].casefold(),
        ),
    )
    totals = {term: 0 for term in terms}
    grand_total = 0
    for university, counts_by_term in rows:
        values = [counts_by_term.get(term, 0) for term in terms]
        total = sum(values)
        for term, value in zip(terms, values):
            totals[term] += value
        grand_total += total
        cells = [latex_escape(university)] + [str(value) if value else "" for value in values]
        cells.append(str(total))
        lines.extend([" & ".join(cells) + r" \\", r"\hline"])

    total_cells = [r"\textbf{合计}"] + [
        rf"\textbf{{{totals[term]}}}" for term in terms
    ]
    total_cells.append(rf"\textbf{{{grand_total}}}")
    lines.extend(
        [
            " & ".join(total_cells) + r" \\",
            r"\hline",
            r"\end{longtable}",
            r"\endgroup",
            r"\par\medskip",
        ]
    )
    return lines


@dataclass
class PipelineConfig:
    server: str
    term: str
    output_dir: Path
    font_regular: Path
    font_bold: Path
    contact_candidates: tuple[str, ...]
    timeout_seconds: int = 45

    @classmethod
    def load(cls, path: Path, term_override: str | None = None) -> "PipelineConfig":
        raw = json.loads(path.read_text(encoding="utf-8"))
        base_dir = path.parent

        def resolve(value: str) -> Path:
            expanded = Path(os.path.expandvars(os.path.expanduser(value)))
            return expanded if expanded.is_absolute() else (base_dir / expanded).resolve()

        return cls(
            server=raw.get("server", "https://cloud.seatable.io").rstrip("/"),
            term=term_override or raw.get("term", "2026 Fall"),
            output_dir=resolve(raw.get("output_dir", "generated")),
            font_regular=resolve(raw.get("font_regular", "C:/Windows/Fonts/msyh.ttc")),
            font_bold=resolve(raw.get("font_bold", "C:/Windows/Fonts/msyhbd.ttc")),
            contact_candidates=tuple(raw.get("contact_candidates", CONTACT_CANDIDATES)),
            timeout_seconds=int(raw.get("timeout_seconds", 45)),
        )


class SeaTableClient:
    def __init__(self, server: str, api_token: str, timeout: int = 45):
        self.server = server.rstrip("/")
        self.api_token = api_token
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "seatable-pdf-pipeline/1.0"})
        self.access_token = ""
        self.base_uuid = ""
        self.workspace_id = ""
        self.base_name = ""

    def _json(self, method: str, url: str, *, token: str, **kwargs: Any) -> Any:
        response = self.session.request(
            method,
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
            **kwargs,
        )
        if response.status_code >= 400:
            body = response.text[:500].replace("\n", " ")
            raise PipelineError(f"SeaTable API {response.status_code} for {url}: {body}")
        return response.json()

    def authenticate(self) -> None:
        payload = self._json(
            "GET",
            f"{self.server}/api/v2.1/dtable/app-access-token/",
            token=self.api_token,
            params={"exp": "2h"},
        )
        self.access_token = payload["access_token"]
        self.base_uuid = payload["dtable_uuid"]
        self.workspace_id = str(payload["workspace_id"])
        self.base_name = payload["dtable_name"]

    @property
    def base_api(self) -> str:
        if not self.base_uuid:
            raise PipelineError("Client is not authenticated")
        return f"{self.server}/api-gateway/api/v2/dtables/{self.base_uuid}"

    def metadata(self) -> dict[str, Any]:
        return self._json(
            "GET", f"{self.base_api}/metadata/", token=self.access_token
        )["metadata"]

    def rows(self, table: str, page_size: int = 1000) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        start = 0
        while True:
            payload = self._json(
                "GET",
                f"{self.base_api}/rows/",
                token=self.access_token,
                params={
                    "table_name": table,
                    "start": start,
                    "limit": page_size,
                    "convert_keys": "true",
                },
            )
            batch = payload.get("rows", [])
            rows.extend(batch)
            if len(batch) < page_size:
                break
            start += len(batch)
        return rows

    def download_asset(self, source_url: str, target: Path) -> Path:
        parsed = urlparse(source_url)
        if parsed.netloc.lower() != urlparse(self.server).netloc.lower():
            raise PipelineError(f"Refusing to download non-SeaTable asset: {source_url}")

        marker = f"/workspace/{self.workspace_id}/asset/{self.base_uuid}"
        if marker not in parsed.path:
            raise PipelineError(f"Unrecognized SeaTable asset URL: {source_url}")
        asset_path = parsed.path.split(marker, 1)[1]
        if not asset_path.startswith(("/images/", "/files/")):
            raise PipelineError(f"Unsupported SeaTable asset path: {asset_path}")

        payload = self._json(
            "GET",
            f"{self.server}/api/v2.1/dtable/app-download-link/",
            token=self.api_token,
            params={"path": asset_path},
        )
        download_url = payload["download_link"]
        response = self.session.get(download_url, timeout=self.timeout)
        if response.status_code >= 400:
            raise PipelineError(
                f"Asset download failed with HTTP {response.status_code}: {source_url}"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(response.content)
        return target


def validate_schema(metadata: dict[str, Any]) -> tuple[dict[str, set[str]], list[str]]:
    table_columns: dict[str, set[str]] = {}
    for table in metadata.get("tables", []):
        table_columns[table["name"]] = {column["name"] for column in table.get("columns", [])}

    errors: list[str] = []
    for table, required in REQUIRED_COLUMNS.items():
        if table not in table_columns:
            errors.append(f"Missing table: {table}")
            continue
        missing = sorted(required - table_columns[table])
        if missing:
            errors.append(f"{table} missing columns: {', '.join(missing)}")
    return table_columns, errors


def choose_contact_column(columns: set[str], candidates: Iterable[str]) -> str | None:
    by_lower = {name.casefold(): name for name in columns}
    for candidate in candidates:
        if candidate.casefold() in by_lower:
            return by_lower[candidate.casefold()]
    return None


def application_date_text(application: dict[str, Any]) -> str:
    submitted = clean_text(application.get("submit_date"))
    result_date = clean_text(application.get("result_date"))
    status = clean_text(application.get("result"))
    if submitted and result_date:
        return f"({submitted} - {result_date})"
    if submitted and status == "Waitlist":
        return f"({submitted} - now)"
    if submitted:
        return f"(submitted {submitted})"
    if result_date:
        return f"(result {result_date})"
    return ""


def build_student_records(
    students: list[dict[str, Any]],
    applications: list[dict[str, Any]],
    programs: list[dict[str, Any]],
    universities: list[dict[str, Any]],
    *,
    term: str,
    contact_column: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    program_by_id = {row["_id"]: row for row in programs}
    university_by_id = {row["_id"]: row for row in universities}
    apps_by_student: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in applications:
        student_link = link_first(row.get("student"))
        if student_link:
            apps_by_student[student_link["row_id"]].append(row)

    records: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for student in students:
        if clean_text(student.get("term")) != term:
            continue

        student_issues: list[str] = []
        choice_links = student.get("program_choice") or []
        if len(choice_links) != 1:
            student_issues.append(f"program_choice count is {len(choice_links)}; expected 1")
        choice = link_first(choice_links)
        program = program_by_id.get(choice["row_id"]) if choice else None
        if not program:
            student_issues.append("chosen program cannot be resolved")

        university_link = link_first(program.get("university")) if program else None
        university = university_by_id.get(university_link["row_id"]) if university_link else None
        if not university:
            student_issues.append("chosen university cannot be resolved")

        resolved_apps: list[dict[str, Any]] = []
        for app in sorted(
            apps_by_student.get(student["_id"], []),
            key=lambda row: numeric_suffix(clean_text(row.get("a_id"))),
        ):
            app_program_link = link_first(app.get("program"))
            app_program = (
                program_by_id.get(app_program_link["row_id"]) if app_program_link else None
            )
            app_university_link = link_first(app_program.get("university")) if app_program else None
            app_university = (
                university_by_id.get(app_university_link["row_id"])
                if app_university_link
                else None
            )
            if not app_program or not app_university:
                student_issues.append(
                    f"{clean_text(app.get('a_id'))}: program/university link cannot be resolved"
                )
                continue
            resolved_apps.append(
                {
                    "a_id": clean_text(app.get("a_id")),
                    "result": clean_text(app.get("result")),
                    "submit_date": clean_text(app.get("submit_date")),
                    "result_date": clean_text(app.get("result_date")),
                    "date_text": application_date_text(app),
                    "program_abbrv": clean_text(app_program.get("abbrv")),
                    "program_level": clean_text(app_program.get("level")),
                    "program_name": clean_text(app_program.get("name")),
                    "university_name": clean_text(app_university.get("name")),
                    "region": clean_text(app_university.get("region")),
                }
            )

        if not resolved_apps:
            student_issues.append("no application rows resolved")

        chosen_apps = [app for app in resolved_apps if app["result"] == "Chosen"]
        if len(chosen_apps) != 1:
            student_issues.append(
                f"Chosen application count is {len(chosen_apps)}; program_choice remains authoritative"
            )

        contact = clean_text(student.get(contact_column)) if contact_column else ""
        record = {
            "s_id": clean_text(student.get("s_id")),
            "row_id": student.get("_id"),
            "name": clean_text(student.get("name"), empty="Unnamed student"),
            "term": clean_text(student.get("term")),
            "major": clean_text(student.get("major")),
            "major_display": MAJOR_DISPLAY.get(
                clean_text(student.get("major")), clean_text(student.get("major"))
            ),
            "apply_degree": clean_text(student.get("apply_degree")),
            "prefer_field": clean_text(student.get("prefer_field")),
            "gpa": clean_text(student.get("gpa")),
            "lang": clean_text(student.get("lang")),
            "gre": clean_text(student.get("gre")),
            "experience": clean_text(student.get("experience")),
            "sharing": clean_text(student.get("sharing")),
            "contact": contact,
            "chosen_program_abbrv": clean_text(program.get("abbrv")) if program else "",
            "chosen_program_level": clean_text(program.get("level")) if program else "",
            "chosen_program_name": clean_text(program.get("name")) if program else "",
            "chosen_university_name": clean_text(university.get("name")) if university else "",
            "region": clean_text(university.get("region")) if university else "UNRESOLVED",
            "applications": resolved_apps,
        }

        for field in ("name", "major", "apply_degree", "prefer_field", "gpa"):
            if is_blank(record[field]):
                student_issues.append(f"missing {field}")
        for field in ("lang", "gre", "experience", "sharing"):
            if is_blank(record[field]):
                student_issues.append(f"empty or placeholder {field}")

        if student_issues:
            issues.append({"s_id": record["s_id"], "name": record["name"], "issues": student_issues})
        records.append(record)

    records.sort(
        key=lambda row: (
            row["region"],
            row["chosen_university_name"].casefold(),
            row["chosen_program_name"].casefold(),
            row["name"].casefold(),
            row["s_id"],
        )
    )
    return records, issues


def register_fonts(regular: Path, bold: Path) -> tuple[str, str]:
    if regular.exists() and bold.exists():
        try:
            pdfmetrics.registerFont(TTFont("HandbookRegular", str(regular), subfontIndex=0))
            pdfmetrics.registerFont(TTFont("HandbookBold", str(bold), subfontIndex=0))
            pdfmetrics.registerFontFamily(
                "HandbookRegular",
                normal="HandbookRegular",
                bold="HandbookBold",
                italic="HandbookRegular",
                boldItalic="HandbookBold",
            )
            return "HandbookRegular", "HandbookBold"
        except Exception as exc:
            print(f"Warning: failed to load configured fonts: {exc}", file=sys.stderr)

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    return "STSong-Light", "STSong-Light"


def make_styles(regular_font: str, bold_font: str) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "HandbookTitle",
            parent=base["Title"],
            fontName=bold_font,
            fontSize=25,
            leading=31,
            alignment=TA_LEFT,
            textColor=colors.black,
            spaceAfter=18,
            keepWithNext=True,
        ),
        "h2": ParagraphStyle(
            "HandbookH2",
            parent=base["Heading2"],
            fontName=bold_font,
            fontSize=15.5,
            leading=22,
            textColor=colors.black,
            spaceBefore=16,
            spaceAfter=8,
            keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "HandbookH3",
            parent=base["Heading3"],
            fontName=bold_font,
            fontSize=12.5,
            leading=18,
            textColor=colors.black,
            spaceBefore=8,
            spaceAfter=5,
            keepWithNext=True,
        ),
        "h4": ParagraphStyle(
            "HandbookH4",
            parent=base["Heading4"],
            fontName=bold_font,
            fontSize=11.2,
            leading=17,
            textColor=colors.black,
            spaceBefore=6,
            spaceAfter=3,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "HandbookBody",
            parent=base["BodyText"],
            fontName=regular_font,
            fontSize=10.8,
            leading=19.5,
            textColor=colors.black,
            spaceAfter=6,
            allowWidows=0,
            allowOrphans=0,
        ),
        "field": ParagraphStyle(
            "HandbookField",
            parent=base["BodyText"],
            fontName=regular_font,
            fontSize=10.8,
            leading=19,
            textColor=colors.black,
            spaceAfter=8,
        ),
        "list": ParagraphStyle(
            "HandbookList",
            parent=base["BodyText"],
            fontName=regular_font,
            fontSize=10.6,
            leading=19,
            leftIndent=0,
            firstLineIndent=0,
            spaceAfter=5,
        ),
        "numbered": ParagraphStyle(
            "HandbookNumbered",
            parent=base["BodyText"],
            fontName=regular_font,
            fontSize=10.6,
            leading=19,
            leftIndent=9 * mm,
            firstLineIndent=0,
            bulletIndent=0,
            bulletFontName=regular_font,
            bulletFontSize=10.6,
            bulletOffsetY=0,
            textColor=colors.black,
            spaceAfter=6,
            allowWidows=0,
            allowOrphans=0,
        ),
        "quote": ParagraphStyle(
            "HandbookQuote",
            parent=base["BodyText"],
            fontName=regular_font,
            fontSize=10.3,
            leading=19,
            leftIndent=10 * mm,
            rightIndent=5 * mm,
            textColor=colors.HexColor("#444444"),
            borderColor=colors.HexColor("#B8B8B8"),
            borderWidth=0.8,
            borderPadding=(0, 0, 0, 6),
            spaceAfter=6,
        ),
    }


def inline_markup(value: str) -> str:
    text = clean_text(value)
    placeholders: list[str] = []

    def save_link(match: re.Match[str]) -> str:
        label = html.escape(clean_text(match.group(1)), quote=False)
        href = html.escape(clean_text(match.group(2)), quote=True)
        placeholders.append(f'<link href="{href}" color="#2468A2">{label}</link>')
        return f"@@LINK{len(placeholders) - 1}@@"

    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", save_link, text)
    text = html.escape(text, quote=False)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__([^_]+)__", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"`([^`]+)`", r'<font face="Courier">\1</font>', text)
    for index, replacement in enumerate(placeholders):
        text = text.replace(f"@@LINK{index}@@", replacement)
    return text


IMG_TAG_RE = re.compile(r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"'][^>]*>", re.I)
HEADING_RE = re.compile(r"^(#{2,4})\s*(.*?)\s*$")
ORDERED_RE = re.compile(r"^\s*(\d+)[.)]\s+(.*)$")
UNORDERED_RE = re.compile(r"^\s*[-+*]\s+(.*)$")


def image_flowable(path: Path, max_width: float) -> Image:
    with PILImage.open(path) as source:
        width_px, height_px = source.size
    width = min(max_width, width_px * 0.75)
    height = height_px * (width / width_px)
    return Image(str(path), width=width, height=height)


def markdown_flowables(
    value: str,
    *,
    styles: dict[str, ParagraphStyle],
    client: SeaTableClient,
    asset_dir: Path,
    max_width: float,
    fallback_heading: str,
) -> tuple[list[Any], list[str]]:
    text = clean_text(value)
    warnings: list[str] = []
    if is_blank(text):
        return [Paragraph(inline_markup(fallback_heading), styles["h2"]), Paragraph("未提供", styles["body"])], warnings

    lines = text.splitlines()
    flowables: list[Any] = []
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        if paragraph_lines:
            paragraph_text = "<br/>".join(inline_markup(line) for line in paragraph_lines if line.strip())
            if paragraph_text:
                flowables.append(Paragraph(paragraph_text, styles["body"]))
            paragraph_lines = []

    index = 0
    while index < len(lines):
        raw = lines[index].strip()
        if not raw:
            flush_paragraph()
            index += 1
            continue

        image_match = IMG_TAG_RE.search(raw)
        if image_match:
            flush_paragraph()
            source_url = html.unescape(image_match.group(1))
            suffix = Path(urlparse(source_url).path).suffix or ".img"
            target = asset_dir / f"image-{len(list(asset_dir.glob('*'))) + 1:02d}{suffix}"
            try:
                if not target.exists():
                    client.download_asset(source_url, target)
                flowables.append(Spacer(1, 4))
                flowables.append(image_flowable(target, max_width=max_width))
                flowables.append(Spacer(1, 7))
            except Exception as exc:
                warnings.append(f"Could not render image {source_url}: {exc}")
                flowables.append(Paragraph("[图片无法读取]", styles["body"]))
            index += 1
            continue

        heading_match = HEADING_RE.match(raw)
        if heading_match:
            flush_paragraph()
            level = min(len(heading_match.group(1)), 4)
            flowables.append(Paragraph(inline_markup(heading_match.group(2)), styles[f"h{level}"]))
            index += 1
            continue

        ordered_match = ORDERED_RE.match(raw)
        unordered_match = UNORDERED_RE.match(raw)
        if ordered_match:
            flush_paragraph()
            number = ordered_match.group(1)
            item_lines = [ordered_match.group(2)]
            index += 1
            while index < len(lines):
                candidate = lines[index].strip()
                if ORDERED_RE.match(candidate) or HEADING_RE.match(candidate):
                    break
                if UNORDERED_RE.match(candidate) or IMG_TAG_RE.search(candidate) or candidate.startswith(">"):
                    break
                if not candidate:
                    next_index = index + 1
                    while next_index < len(lines) and not lines[next_index].strip():
                        next_index += 1
                    if next_index >= len(lines):
                        index = next_index
                        break
                    next_text = lines[next_index].strip()
                    if (
                        ORDERED_RE.match(next_text)
                        or HEADING_RE.match(next_text)
                        or UNORDERED_RE.match(next_text)
                        or IMG_TAG_RE.search(next_text)
                        or next_text.startswith(">")
                    ):
                        index = next_index
                        break
                    item_lines.append("")
                    index += 1
                    continue
                item_lines.append(re.sub(r"</?[^>]+>", "", candidate))
                index += 1
            item_markup = "<br/>".join(
                inline_markup(line) if line else "" for line in item_lines
            )
            flowables.append(
                Paragraph(item_markup, styles["numbered"], bulletText=f"{number}.")
            )
            continue

        if unordered_match:
            flush_paragraph()
            items: list[ListItem] = []
            while index < len(lines):
                candidate = lines[index].strip()
                match = UNORDERED_RE.match(candidate)
                if not match:
                    break
                items.append(
                    ListItem(
                        Paragraph(inline_markup(match.group(1)), styles["list"]),
                        leftIndent=10,
                    )
                )
                index += 1
            flowables.append(
                ListFlowable(
                    items,
                    bulletType="bullet",
                    leftIndent=16,
                    bulletFontName=styles["body"].fontName,
                    bulletFontSize=10.6,
                    spaceAfter=7,
                )
            )
            continue

        if raw.startswith(">"):
            flush_paragraph()
            quote_lines: list[str] = []
            while index < len(lines) and lines[index].lstrip().startswith(">"):
                quote_lines.append(lines[index].lstrip()[1:].strip())
                index += 1
            flowables.append(
                Paragraph("<br/>".join(inline_markup(line) for line in quote_lines), styles["quote"])
            )
            continue

        # Strip unsupported raw HTML while keeping its readable text.
        raw = re.sub(r"</?[^>]+>", "", raw)
        paragraph_lines.append(raw)
        index += 1

    flush_paragraph()
    if not any(isinstance(item, Paragraph) and item.style.name == "HandbookH2" for item in flowables):
        flowables.insert(0, Paragraph(inline_markup(fallback_heading), styles["h2"]))
    return flowables, warnings


def add_field(story: list[Any], label: str, value: str, styles: dict[str, ParagraphStyle]) -> None:
    display = clean_text(value) or "未提供"
    story.append(
        Paragraph(
            f"<b>{html.escape(clean_text(label), quote=False)}：</b> {inline_markup(display)}",
            styles["field"],
        )
    )


def render_student_pdf(
    record: dict[str, Any],
    target: Path,
    *,
    styles: dict[str, ParagraphStyle],
    client: SeaTableClient,
    asset_root: Path,
) -> list[str]:
    target.parent.mkdir(parents=True, exist_ok=True)
    page_width, _ = A4
    left_margin = 24 * mm
    right_margin = 24 * mm
    content_width = page_width - left_margin - right_margin
    doc = SimpleDocTemplate(
        str(target),
        pagesize=A4,
        leftMargin=left_margin,
        rightMargin=right_margin,
        topMargin=19 * mm,
        bottomMargin=19 * mm,
        title=f"{record['chosen_program_abbrv']} - {record['name']}",
        author="SeaTable PDF Pipeline",
        creator="SeaTable PDF Pipeline",
    )
    story: list[Any] = []
    warnings: list[str] = []

    title = f"{record['chosen_program_abbrv']} - {record['name']}"
    story.append(Paragraph(inline_markup(title), styles["title"]))
    story.append(Paragraph("基本信息 Basic Information", styles["h2"]))
    add_field(story, "本科专业", record["major_display"], styles)
    add_field(story, "申请学位", record["apply_degree"], styles)
    add_field(story, "领域偏好", record["prefer_field"], styles)
    destination = " - ".join(
        part
        for part in (
            record["chosen_university_name"],
            format_program(record["chosen_program_level"], record["chosen_program_name"]),
        )
        if part
    )
    add_field(story, "最终去向", destination, styles)
    if not is_blank(record.get("contact")):
        add_field(story, "联系方式", record["contact"], styles)

    story.append(Paragraph("申请三维 Application Information", styles["h2"]))
    add_field(story, "均分（大一/大二/大三）", record["gpa"], styles)
    add_field(story, "语言成绩", record["lang"], styles)
    add_field(story, "GRE", record["gre"] or "无", styles)

    experience_flowables, experience_warnings = markdown_flowables(
        record["experience"],
        styles=styles,
        client=client,
        asset_dir=asset_root / record["s_id"] / "experience",
        max_width=content_width,
        fallback_heading="个人经历 Personal Academic Experiences",
    )
    story.extend(experience_flowables)
    warnings.extend(experience_warnings)

    story.append(Paragraph("申请结果 Application Results", styles["h2"]))
    for heading, statuses in RESULT_GROUPS:
        grouped = [app for app in record["applications"] if app["result"] in statuses]
        if not grouped:
            continue
        story.append(Paragraph(f"{heading}:", styles["h3"]))
        for app_index, app in enumerate(grouped, start=1):
            program_text = format_program(app["program_level"], app["program_name"])
            line = f"{app['university_name']} - {program_text}"
            if app["date_text"]:
                line += f" {app['date_text']}"
            story.append(
                Paragraph(
                    inline_markup(line),
                    styles["numbered"],
                    bulletText=f"{app_index}.",
                )
            )

    sharing_flowables, sharing_warnings = markdown_flowables(
        record["sharing"],
        styles=styles,
        client=client,
        asset_dir=asset_root / record["s_id"] / "sharing",
        max_width=content_width,
        fallback_heading="申请经验 Application Experience Sharing",
    )
    story.extend(sharing_flowables)
    warnings.extend(sharing_warnings)

    doc.build(story)
    return warnings


def build_main_tex(
    manifest: list[dict[str, Any]],
    target: Path,
    offer_statistics: dict[str, dict[str, dict[str, int]]],
    statistics_terms: list[str],
) -> None:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in manifest:
        grouped[row["region"]].append(row)

    preferred_region_order = ("US", "UK", "HK", "SG", "CN", "EU", "JP")
    region_order = [region for region in preferred_region_order if region in grouped]
    region_order.extend(sorted(region for region in grouped if region not in region_order))

    lines = [
        r"\documentclass{article}",
        r"\usepackage{graphicx}",
        r"\usepackage{pdfpages}",
        r"\usepackage[UTF8]{ctex}",
        r"\usepackage{titlesec}",
        r"\usepackage{titletoc}",
        r"\usepackage[hidelinks]{hyperref}",
        r"\usepackage{xstring}",
        r"\usepackage[a4paper, margin=2.54cm]{geometry}",
        r"\usepackage{fancyhdr}",
        r"\usepackage{tocloft}",
        r"\usepackage{array}",
        r"\usepackage{multirow}",
        r"\usepackage{longtable}",
        "",
        "",
        r"% ---------- 目录开始 --------------",
        r"\renewcommand{\contentsname}{%",
        r"  \centering\Huge 目录\\[0.1ex]",
        r"  \makebox[\textwidth][c]{\normalfont\small （以下按字母顺序排列）}%",
        r"}",
        "",
        r"% 格式设置",
        r"\setlength{\cftsecnumwidth}{1em}",
        r"\setlength{\cftsecindent}{0em}",
        r"\renewcommand{\cftsecleader}{\cftdotfill{\cftdotsep}}",
        r"\renewcommand{\cftsecfont}{\normalfont}",
        "",
        r"% 自定义命令以在带编号的 section 后添加点",
        r"\makeatletter",
        r"\renewcommand{\numberline}[1]{\ifx\@empty#1\@empty\else\textbf{#1.}\fi\hskip 1em\relax}",
        r"\makeatother",
        "",
        r"% ------------- 目录结束 ----------------",
        "",
        r"% 页眉页脚",
        r"\fancypagestyle{plain}{",
        r"  \fancyhead[R]{\thepage\ \hyperlink{toc}{返回目录}}",
        r"}",
        "",
        r"\pagestyle{fancy}",
        r"\fancyhf{}",
        r"\fancyhead[R]{\hyperlink{toc}{\textcolor{blue}{返回目录}}}",
        r"\fancyfoot[C]{\thepage}",
        r"% \renewcommand{\footrulewidth}{0.4pt} % 添加页脚横线",
        "",
        r"% 重新定义includepdffile",
        r"\newcommand{\includepdffile}[3]{%",
        r"  \clearpage",
        r"  \phantomsection",
        r"  \StrBefore{#1}{.pdf}[\filename]",
        r"  \edef\displaytitle{#3}",
        r"  \addcontentsline{toc}{section}{\protect\numberline{}{\displaytitle}}",
        r"  \label{toc\filename}",
        r"  \includepdf[",
        r"    pages=-,",
        r"    pagecommand={%",
        r"      \fancyhf{}%",
        r"      \fancyhead[L]{#2}%",
        r"      \fancyhead[R]{\hyperlink{toc}{\textcolor{blue}{返回目录}}}%",
        r"      \fancyfoot[C]{\thepage}%",
        r"      \thispagestyle{fancy}%",
        r"    }",
        r"  ]{#1}",
        r"}",
        "",
        r"\title{飞跃手册}",
        "",
        r"\begin{document}",
        "",
        r"% \includepdf[pages=-, fitpaper=true]{covers/covers.pdf}",
        "",
        r"% \clearpage",
        r"% \phantomsection",
        r"\hypertarget{toc}{}",
        "",
        r"\tableofcontents % 生成目录",
        r"\newpage",
        "",
        r"\newpage",
        "",
        r"\titleformat{\section}{\fontsize{48}{28}\selectfont\bfseries}{\thesection\quad}{0pt}{}",
        r"\titlespacing*{\section}{0pt}{\baselineskip}{\baselineskip}",
        "",
        r"%% 收纳盒",
        r"{",
        "",
    ]
    for region in region_order:
        lines.append(f"\\section{{\\textbf{{{latex_escape(region)}}} }}")
        lines.extend(
            offer_table_tex(
                region,
                offer_statistics.get(region, {}),
                statistics_terms,
            )
        )
        rows = sorted(
            grouped[region],
            key=lambda row: (
                row["university"].casefold(),
                row["program"].casefold(),
                row["student"].casefold(),
            ),
        )
        for row in rows:
            header = f"{row['university']} - {row['program']}/{row['student']}"
            path = "./" + row["pdf_path"].replace("\\", "/")
            lines.append(
                "\\includepdffile"
                f"{{{path}}}"
                f"{{{latex_escape(header)}}}"
                f"{{{latex_escape(header)}}}"
            )
        lines.append("")
    lines.extend([r"}", "", r"\end{document}", ""])
    target.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(
    config: PipelineConfig,
    client: SeaTableClient,
    records: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    contact_column: str | None,
    offer_statistics: dict[str, dict[str, dict[str, int]]],
    statistics_terms: list[str],
) -> dict[str, Any]:
    output_dir = config.output_dir
    individual_dir = output_dir / "individual"
    asset_dir = output_dir / "assets"
    individual_dir.mkdir(parents=True, exist_ok=True)
    asset_dir.mkdir(parents=True, exist_ok=True)

    # This directory is fully managed by the pipeline. Clear prior named outputs so
    # switching naming schemes does not leave obsolete student-id PDFs behind.
    for old_pdf in individual_dir.glob("*.pdf"):
        old_pdf.unlink()

    regular_font, bold_font = register_fonts(config.font_regular, config.font_bold)
    styles = make_styles(regular_font, bold_font)
    render_warnings: list[dict[str, Any]] = []
    manifest: list[dict[str, Any]] = []
    used_filenames: set[str] = set()

    for index, record in enumerate(records, start=1):
        stem = safe_filename(record["name"], record["s_id"])
        filename = f"{stem}.pdf"
        duplicate_index = 2
        while filename.casefold() in used_filenames:
            filename = f"{stem} ({duplicate_index}).pdf"
            duplicate_index += 1
        used_filenames.add(filename.casefold())
        target = individual_dir / filename
        print(f"[{index:02d}/{len(records):02d}] {record['name']} -> {target.name}")
        warnings = render_student_pdf(
            record,
            target,
            styles=styles,
            client=client,
            asset_root=asset_dir,
        )
        if warnings:
            render_warnings.append(
                {"s_id": record["s_id"], "name": record["name"], "warnings": warnings}
            )
        page_count = len(PdfReader(str(target)).pages)
        manifest.append(
            {
                "s_id": record["s_id"],
                "student": record["name"],
                "term": record["term"],
                "region": record["region"],
                "university": record["chosen_university_name"],
                "program": format_program(
                    record["chosen_program_level"], record["chosen_program_name"]
                ),
                "program_abbrv": record["chosen_program_abbrv"],
                "pdf_path": f"individual/{filename}",
                "pages": page_count,
            }
        )

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    build_main_tex(
        manifest,
        output_dir / "main.tex",
        offer_statistics,
        statistics_terms,
    )

    missing_application_dates = {
        "submit_date": sum(
            1 for record in records for app in record["applications"] if not app["submit_date"]
        ),
        "result_date": sum(
            1 for record in records for app in record["applications"] if not app["result_date"]
        ),
    }
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_name": client.base_name,
        "base_uuid": client.base_uuid,
        "term": config.term,
        "student_count": len(records),
        "pdf_count": len(manifest),
        "total_pages": sum(row["pages"] for row in manifest),
        "contact_column": contact_column,
        "statistics_terms": statistics_terms,
        "schema_notes": [
            "No contact column was found; the contact line is omitted."
            if contact_column is None
            else f"Contact values are read from Student.{contact_column}."
        ],
        "data_issues": issues,
        "render_warnings": render_warnings,
        "missing_application_dates": missing_application_dates,
    }
    (output_dir / "quality_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).with_name("config.json"),
        help="Path to the JSON config file",
    )
    parser.add_argument("--term", help="Override the configured intake term")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Read and validate SeaTable data without generating PDFs",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
    if not args.config.exists():
        raise PipelineError(
            f"Config file not found: {args.config}. Copy config.example.json to config.json."
        )
    config = PipelineConfig.load(args.config, term_override=args.term)
    api_token = os.environ.get("SEATABLE_API_TOKEN", "").strip()
    if not api_token:
        raise PipelineError(
            "Set SEATABLE_API_TOKEN in the pipeline's .env file or environment."
        )

    client = SeaTableClient(config.server, api_token, timeout=config.timeout_seconds)
    client.authenticate()
    metadata = client.metadata()
    table_columns, schema_errors = validate_schema(metadata)
    if schema_errors:
        raise PipelineError("; ".join(schema_errors))

    contact_column = choose_contact_column(
        table_columns.get("Student", set()), config.contact_candidates
    )
    students = client.rows("Student")
    applications = client.rows("Application")
    programs = client.rows("Program")
    universities = client.rows("University")
    records, issues = build_student_records(
        students,
        applications,
        programs,
        universities,
        term=config.term,
        contact_column=contact_column,
    )
    if not records:
        raise PipelineError(f"No students found for term: {config.term}")
    offer_statistics, statistics_terms = build_offer_statistics(
        students,
        applications,
        programs,
        universities,
    )

    print(
        json.dumps(
            {
                "base": client.base_name,
                "term": config.term,
                "students": len(records),
                "contact_column": contact_column,
                "students_with_data_notes": len(issues),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if args.validate_only:
        return 0

    report = write_outputs(
        config,
        client,
        records,
        issues,
        contact_column,
        offer_statistics,
        statistics_terms,
    )
    print(
        json.dumps(
            {
                "output_dir": str(config.output_dir),
                "pdf_count": report["pdf_count"],
                "total_pages": report["total_pages"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PipelineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
