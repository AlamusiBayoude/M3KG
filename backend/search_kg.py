from __future__ import annotations

import argparse
import hashlib
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path


DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "mongolian_medicine_kg.sqlite"


def connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    try:
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.OperationalError:
        digest = hashlib.sha1(str(db_path.resolve()).encode("utf-8")).hexdigest()[:12]
        shadow_path = Path(tempfile.gettempdir()) / f"mongolian_medicine_kg_search_{digest}.sqlite"
        if not shadow_path.exists() or shadow_path.stat().st_mtime < db_path.stat().st_mtime:
            shutil.copy2(db_path, shadow_path)
        conn = sqlite3.connect(f"file:{shadow_path.as_posix()}?mode=ro&immutable=1", uri=True)
        conn.row_factory = sqlite3.Row
        return conn


def like_pattern(query: str) -> str:
    return f"%{query}%"


def quote_fts(query: str) -> str:
    return '"' + query.replace('"', '""') + '"'


def print_rows(rows: list[sqlite3.Row], empty_message: str = "未找到匹配记录。") -> None:
    if not rows:
        print(empty_message)
        return
    for idx, row in enumerate(rows, start=1):
        print(f"\n[{idx}]")
        for key in row.keys():
            value = row[key]
            if value is not None and value != "":
                print(f"{key}: {value}")


def show_stats(conn: sqlite3.Connection) -> None:
    print("数据库统计")
    for row in conn.execute("SELECT key, value FROM metadata ORDER BY key"):
        print(f"- {row['key']}: {row['value']}")

    print("\n模块文件")
    for row in conn.execute("SELECT module_code, module_name, triple_count FROM source_files ORDER BY module_code"):
        print(f"- {row['module_code']} {row['module_name']}: {row['triple_count']}")

    print("\n实体类型")
    for row in conn.execute(
        "SELECT entity_type, COUNT(*) AS count FROM entities GROUP BY entity_type ORDER BY count DESC, entity_type"
    ):
        print(f"- {row['entity_type']}: {row['count']}")


def find_material(conn: sqlite3.Connection, material_query: str) -> sqlite3.Row | None:
    row = conn.execute(
        """
        SELECT * FROM materials
        WHERE material_id = ? OR label = ?
        LIMIT 1
        """,
        (material_query, material_query),
    ).fetchone()
    if row:
        return row

    return conn.execute(
        """
        SELECT * FROM materials
        WHERE material_id LIKE ? OR label LIKE ? OR search_text LIKE ?
        ORDER BY material_id
        LIMIT 1
        """,
        (like_pattern(material_query), like_pattern(material_query), like_pattern(material_query)),
    ).fetchone()


def show_material(conn: sqlite3.Connection, material_query: str) -> None:
    material = find_material(conn, material_query)
    if not material:
        print("未找到该药材。")
        return

    fields = [
        ("药材编号", "material_id"),
        ("药材名称", "label"),
        ("基源分类", "source_category"),
        ("基源", "source_description"),
        ("味性/功效/主治等聚合词", "terms_text"),
        ("用法用量", "usage_dosage"),
        ("注意事项", "caution"),
        ("药典比对状态", "pharmacopoeia_status"),
        ("药典命中名", "pharmacopoeia_matched_name"),
        ("特色蒙药候选", "specialty_candidate_status"),
        ("综合判定", "assessment_conclusion"),
        ("复核优先级", "review_priority"),
        ("GBIF匹配状态", "gbif_match_status"),
        ("GBIF匹配学名", "gbif_matched_name"),
        ("全国分布", "national_distribution"),
        ("中国记录数", "china_record_count"),
        ("内蒙古记录数", "inner_mongolia_record_count"),
        ("内蒙古分布标记", "inner_mongolia_distribution_flag"),
    ]

    print("药材档案")
    for label, key in fields:
        value = material[key]
        if value is not None and value != "":
            print(f"- {label}: {value}")

    relation_rows = conn.execute(
        """
        SELECT relation, terms
        FROM v_material_relation_summary
        WHERE material_id = ?
        ORDER BY relation
        """,
        (material["material_id"],),
    ).fetchall()
    if relation_rows:
        print("\n图谱关系聚合")
        for row in relation_rows:
            print(f"- {row['relation']}: {row['terms']}")

    region_rows = conn.execute(
        """
        SELECT region, record_count
        FROM distribution_regions
        WHERE material_id = ?
        ORDER BY COALESCE(record_count, 0) DESC, region
        LIMIT 20
        """,
        (material["material_id"],),
    ).fetchall()
    if region_rows:
        print("\nGBIF省级分布")
        for row in region_rows:
            print(f"- {row['region']}: {row['record_count']}")


def search_all(conn: sqlite3.Connection, query: str, limit: int) -> None:
    rows: list[sqlite3.Row] = []
    try:
        rows = conn.execute(
            """
            SELECT
                d.doc_type AS 类型,
                d.ref_id AS 引用ID,
                d.title AS 标题,
                snippet(search_documents_fts, 3, '[', ']', '...', 18) AS 摘要,
                d.tags AS 标签
            FROM search_documents_fts
            JOIN search_documents d ON d.id = search_documents_fts.rowid
            WHERE search_documents_fts MATCH ?
            LIMIT ?
            """,
            (quote_fts(query), limit),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []

    if not rows:
        pattern = like_pattern(query)
        rows = conn.execute(
            """
            SELECT
                doc_type AS 类型,
                ref_id AS 引用ID,
                title AS 标题,
                substr(body, 1, 220) AS 摘要,
                tags AS 标签
            FROM search_documents
            WHERE title LIKE ? OR body LIKE ? OR tags LIKE ?
            ORDER BY
                CASE doc_type WHEN 'material' THEN 1 WHEN 'entity' THEN 2 ELSE 3 END,
                id
            LIMIT ?
            """,
            (pattern, pattern, pattern, limit),
        ).fetchall()

    print_rows(rows)


def search_materials(conn: sqlite3.Connection, query: str, limit: int) -> None:
    pattern = like_pattern(query)
    rows = conn.execute(
        """
        SELECT
            material_id AS 药材编号,
            label AS 药材名称,
            source_category AS 基源分类,
            specialty_candidate_status AS 特色蒙药候选,
            review_priority AS 复核优先级,
            inner_mongolia_distribution_flag AS 内蒙古分布标记,
            substr(search_text, 1, 260) AS 摘要
        FROM materials
        WHERE material_id LIKE ? OR label LIKE ? OR search_text LIKE ?
        ORDER BY material_id
        LIMIT ?
        """,
        (pattern, pattern, pattern, limit),
    ).fetchall()
    print_rows(rows)


def search_entities(conn: sqlite3.Connection, query: str, limit: int) -> None:
    pattern = like_pattern(query)
    rows = conn.execute(
        """
        SELECT
            entity_id AS 实体ID,
            entity_type AS 实体类型,
            label AS 标签,
            substr(search_text, 1, 260) AS 摘要
        FROM entities
        WHERE entity_id LIKE ? OR entity_type LIKE ? OR label LIKE ? OR search_text LIKE ?
        ORDER BY entity_type, label
        LIMIT ?
        """,
        (pattern, pattern, pattern, pattern, limit),
    ).fetchall()
    print_rows(rows)


def search_triples(conn: sqlite3.Connection, query: str, limit: int) -> None:
    pattern = like_pattern(query)
    rows = conn.execute(
        """
        SELECT
            id AS 三元组ID,
            module_code AS 模块,
            source_row_id AS 药材编号,
            subject_id AS 主语,
            predicate AS 关系,
            COALESCE(object_id, object_value) AS 宾语,
            source_field AS 来源字段
        FROM triples
        WHERE
            raw_text LIKE ?
            OR subject_id LIKE ?
            OR predicate LIKE ?
            OR object_id LIKE ?
            OR object_value LIKE ?
            OR source_field LIKE ?
            OR source_row_id LIKE ?
        ORDER BY id
        LIMIT ?
        """,
        (pattern, pattern, pattern, pattern, pattern, pattern, pattern, limit),
    ).fetchall()
    print_rows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Search the Mongolian medicine SQLite knowledge graph.")
    parser.add_argument("query", nargs="?", help="Keyword to search.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite database path.")
    parser.add_argument("--limit", type=int, default=10, help="Maximum result count.")
    parser.add_argument("--stats", action="store_true", help="Show database statistics.")
    parser.add_argument("--material", help="Show one material profile by MM id or name.")
    parser.add_argument(
        "--type",
        choices=["all", "material", "entity", "triple"],
        default="all",
        help="Search scope.",
    )
    args = parser.parse_args()

    with connect(args.db.resolve()) as conn:
        if args.stats:
            show_stats(conn)
            return 0
        if args.material:
            show_material(conn, args.material)
            return 0
        if not args.query:
            parser.error("provide a query, --material, or --stats")

        if args.type == "material":
            search_materials(conn, args.query, args.limit)
        elif args.type == "entity":
            search_entities(conn, args.query, args.limit)
        elif args.type == "triple":
            search_triples(conn, args.query, args.limit)
        else:
            search_all(conn, args.query, args.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
