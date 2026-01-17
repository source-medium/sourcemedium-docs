#!/usr/bin/env python3
"""
Validate table/column references in docs against schema docs (dbt YAML snapshots).

Why this exists:
- Drift is most painful in "how to query" pages (e.g., DDA guides) where examples
  reference columns that may be renamed in dbt (rename_column_map_all).
- The canonical column list is already present in this repo under
  data-activation/data-tables/sm_transformed_v2/*.mdx as a fenced ```yaml block.

This script:
1) Parses those schema pages to build a map of table -> exposed column names.
2) Validates onboarding/data-docs/tables/* Key Columns lists reference real columns.

Usage:
  python3 scripts/docs_column_accuracy.py
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DOCS_DIR = REPO_ROOT / "data-activation" / "data-tables" / "sm_transformed_v2"
DDA_DOCS_DIR = REPO_ROOT / "onboarding" / "data-docs" / "tables"


YAML_BLOCK_RE = re.compile(r"```yaml\s*\n(.*?)\n```", re.DOTALL)
YAML_NAME_RE = re.compile(r"^\s*-\s*name:\s*([A-Za-z0-9_]+)\s*$", re.MULTILINE)
SQL_BLOCK_RE = re.compile(r"```sql\s*\n(.*?)\n```", re.DOTALL | re.IGNORECASE)

# Table refs in example SQL blocks typically look like:
# FROM `your_project.sm_transformed_v2.obt_orders` o
TABLE_REF_RE = re.compile(
    r"`[^`]*?\.sm_transformed_v2\.([A-Za-z0-9_]+)`(?:\s+(?:AS\s+)?([A-Za-z_][A-Za-z0-9_]*))?",
    re.IGNORECASE,
)
QUALIFIED_COL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b")
UNQUALIFIED_IDENT_RE = re.compile(r"\b([a-z][a-z0-9_]{2,})\b")
AS_ALIAS_RE = re.compile(r"\bAS\s+([A-Za-z_][A-Za-z0-9_]*)\b", re.IGNORECASE)
CTE_NAME_RE = re.compile(r"(?:\bWITH\s+|,\s*)([A-Za-z_][A-Za-z0-9_]*)\s+AS\s*\(", re.IGNORECASE)

SQL_IGNORE_WORDS = {
    # keywords
    "select",
    "from",
    "where",
    "group",
    "by",
    "order",
    "limit",
    "join",
    "left",
    "right",
    "inner",
    "outer",
    "full",
    "cross",
    "on",
    "as",
    "with",
    "union",
    "all",
    "distinct",
    "having",
    "over",
    "partition",
    "and",
    "or",
    "not",
    "null",
    "is",
    "in",
    "like",
    "between",
    "case",
    "when",
    "then",
    "else",
    "end",
    "desc",
    "asc",
    "qualify",
    # literals / misc
    "true",
    "false",
    "interval",
    "day",
    "week",
    "month",
    "quarter",
    "year",
}

SQL_IGNORE_FUNCTIONS = {
    "sum",
    "count",
    "countif",
    "avg",
    "min",
    "max",
    "lag",
    "lead",
    "safe_divide",
    "nullif",
    "ifnull",
    "coalesce",
    "current_date",
    "current_timestamp",
    "date_sub",
    "date_add",
    "cast",
}


@dataclass(frozen=True)
class Issue:
    path: Path
    message: str


def iter_mdx_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    return sorted(root.rglob("*.mdx"))


def extract_yaml_block(text: str) -> str | None:
    m = YAML_BLOCK_RE.search(text)
    if not m:
        return None
    return m.group(1)


def build_table_columns_from_schema_docs() -> dict[str, set[str]]:
    table_to_columns: dict[str, set[str]] = {}
    for path in iter_mdx_files(SCHEMA_DOCS_DIR):
        table_name = path.stem
        text = path.read_text(encoding="utf-8", errors="ignore")
        yaml_block = extract_yaml_block(text)
        if not yaml_block:
            continue
        names = YAML_NAME_RE.findall(yaml_block)
        if not names:
            continue
        # First "- name:" is the model name itself; the remainder are column names.
        if names and names[0] == table_name:
            names = names[1:]
        cols = {n for n in names if n != table_name}
        if cols:
            table_to_columns[table_name] = cols
    return table_to_columns


def parse_table_from_frontmatter(text: str) -> str | None:
    # Common pattern: description: 'Working with the `obt_orders` table in BigQuery'
    m = re.search(r"^description:\s*['\"].*?`([A-Za-z0-9_]+)`.*['\"]\s*$", text, flags=re.M)
    if not m:
        return None
    return m.group(1)


def extract_key_columns(text: str) -> list[str]:
    # Extract first-column values from the markdown table under "## Key Columns".
    start = text.find("## Key Columns")
    if start == -1:
        return []
    rest = text[start:]
    next_header = re.search(r"^##\s+", rest[1:], flags=re.M)
    section = rest if not next_header else rest[: next_header.start() + 1]

    cols: list[str] = []
    for line in section.splitlines():
        m = re.match(r"^\|\s*`([A-Za-z0-9_]+)`\s*\|", line)
        if m:
            cols.append(m.group(1))
    return cols


def extract_sql_blocks(text: str) -> list[str]:
    return [m.group(1) for m in SQL_BLOCK_RE.finditer(text)]


def normalize_sql(sql: str) -> str:
    # Strip line comments and collapse whitespace.
    sql = re.sub(r"--.*?$", "", sql, flags=re.M)
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.S)
    # Strip quoted string literals so placeholders don't look like identifiers.
    sql = re.sub(r"'([^'\\]|\\.)*'", "''", sql)
    sql = re.sub(r'"([^"\\]|\\.)*"', '""', sql)
    return sql


def validate_sql_blocks(
    *,
    path: Path,
    text: str,
    table_to_columns: dict[str, set[str]],
) -> list[Issue]:
    issues: list[Issue] = []
    for sql in extract_sql_blocks(text):
        sql_norm = normalize_sql(sql)
        alias_to_table: dict[str, str] = {}
        referenced_tables: set[str] = set()

        for table, alias in TABLE_REF_RE.findall(sql_norm):
            referenced_tables.add(table)
            if alias:
                alias_to_table[alias] = table
            alias_to_table.setdefault(table, table)

        known_tables = {t for t in referenced_tables if t in table_to_columns}

        # 1) Qualified column references: alias.column
        for qualifier, col in QUALIFIED_COL_RE.findall(sql_norm):
            if qualifier not in alias_to_table:
                continue
            table = alias_to_table[qualifier]
            if table not in table_to_columns:
                continue
            if col not in table_to_columns[table]:
                issues.append(Issue(path, f"unknown column `{qualifier}.{col}` for table `{table}` in sql block"))

        # 2) Unqualified identifiers: validate only when the SQL references exactly one known table.
        if len(known_tables) != 1:
            continue
        (single_table,) = tuple(known_tables)
        known_cols = table_to_columns[single_table]

        aliases = set(AS_ALIAS_RE.findall(sql_norm))
        ctes = set(CTE_NAME_RE.findall(sql_norm))
        ignore = SQL_IGNORE_WORDS | SQL_IGNORE_FUNCTIONS | set(alias_to_table.keys()) | aliases | ctes
        ignore |= {single_table, "your_project", "sm_transformed_v2"}

        for ident in UNQUALIFIED_IDENT_RE.findall(sql_norm):
            if ident in ignore:
                continue
            if ident not in known_cols:
                issues.append(Issue(path, f"unknown column `{ident}` for table `{single_table}` in sql block"))

    return issues


def main() -> int:
    table_to_columns = build_table_columns_from_schema_docs()
    if not table_to_columns:
        print(f"[INFO] No schema docs found under {SCHEMA_DOCS_DIR} (skipping accuracy checks).")
        return 0

    issues: list[Issue] = []
    for path in iter_mdx_files(DDA_DOCS_DIR):
        text = path.read_text(encoding="utf-8", errors="ignore")
        table = parse_table_from_frontmatter(text)
        if not table:
            issues.append(Issue(path, "unable to determine table name from frontmatter description"))
            continue
        if table not in table_to_columns:
            issues.append(Issue(path, f"no schema doc found for table `{table}` in {SCHEMA_DOCS_DIR}"))
            continue
        key_cols = extract_key_columns(text)
        if not key_cols:
            issues.append(Issue(path, "missing or unparseable `## Key Columns` table"))
            continue

        known_cols = table_to_columns[table]
        for col in key_cols:
            if col not in known_cols:
                issues.append(Issue(path, f"unknown column `{col}` for table `{table}`"))

        issues.extend(validate_sql_blocks(path=path, text=text, table_to_columns=table_to_columns))

    if issues:
        print(f"[ERROR] Column accuracy check failed with {len(issues)} issue(s):")
        for issue in issues[:100]:
            rel = issue.path.relative_to(REPO_ROOT)
            print(f"  - {rel}: {issue.message}")
        if len(issues) > 100:
            print(f"  ... and {len(issues) - 100} more")
        return 1

    print("[OK] Column accuracy check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
