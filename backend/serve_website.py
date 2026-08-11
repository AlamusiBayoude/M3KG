from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import re
import shutil
import sqlite3
import tempfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
CURATED_INPUT_DIR = ROOT / "curated_tsv_dataset_20260623"
DEFAULT_DB = Path(tempfile.gettempdir()) / "m3kg_curated_20260623.sqlite"
DEFAULT_WEB_DIR = ROOT / "web"
SOURCE_DESCRIPTION_DIR = ROOT.parent / "outputs" / "kg_triples_by_module"


def row_to_dict(row: sqlite3.Row) -> dict[str, object]:
    return {key: row[key] for key in row.keys()}


def clamp_int(value: str | None, default: int, minimum: int, maximum: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return max(minimum, min(maximum, parsed))


def like_pattern(value: str) -> str:
    return f"%{value}%"


def quote_fts(query: str) -> str:
    return '"' + query.replace('"', '""') + '"'


def material_id_from_mm_id(mm_id: str) -> str:
    match = re.fullmatch(r"MM(\d+)", mm_id.strip())
    if not match:
        return mm_id
    return f"MMP{int(match.group(1)):04d}"


def load_source_descriptions() -> dict[str, str]:
    descriptions: dict[str, str] = {}
    if not SOURCE_DESCRIPTION_DIR.exists():
        return descriptions
    direct_pattern = re.compile(
        r'MongolianMedicinalMaterial:(MM\d+)\s+--\[source_description_text\]-->\s+"(.*?)"\s+\|'
    )
    fallback_pattern = re.compile(r'SourceDescription:(MM\d+)\s+--\[rdfs:label\]-->\s+"(.*?)"\s+\|')
    for path in SOURCE_DESCRIPTION_DIR.glob("*.txt"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in direct_pattern.finditer(text):
            descriptions[material_id_from_mm_id(match.group(1))] = match.group(2)
        for match in fallback_pattern.finditer(text):
            descriptions.setdefault(material_id_from_mm_id(match.group(1)), match.group(2))
    return descriptions


SOURCE_DESCRIPTIONS = load_source_descriptions()


def ensure_curated_database(db_path: Path) -> None:
    curated_files = list(CURATED_INPUT_DIR.glob("D*.tsv"))
    restored_workbook = CURATED_INPUT_DIR / "Mongolian_medicinal_pieces_restored_table.xlsx"
    if restored_workbook.exists():
        curated_files.append(restored_workbook)
    if SOURCE_DESCRIPTION_DIR.exists():
        curated_files.extend(SOURCE_DESCRIPTION_DIR.glob("*.txt"))
    if not curated_files:
        return
    newest_source = max(path.stat().st_mtime for path in curated_files)
    if db_path.exists() and db_path.stat().st_mtime >= newest_source:
        return
    from build_curated_tsv_db import build_database

    build_database(CURATED_INPUT_DIR, db_path)


class Database:
    def __init__(self, db_path: Path) -> None:
        if not db_path.exists():
            raise FileNotFoundError(f"Database not found: {db_path}")
        self.db_path = db_path
        self.shadow_path: Path | None = None

    def connect(self) -> sqlite3.Connection:
        try:
            conn = sqlite3.connect(f"file:{self.db_path.as_posix()}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.OperationalError:
            shadow_path = self._shadow_copy()
            conn = sqlite3.connect(f"file:{shadow_path.as_posix()}?mode=ro&immutable=1", uri=True)
            conn.row_factory = sqlite3.Row
            return conn

    def _shadow_copy(self) -> Path:
        digest = hashlib.sha1(str(self.db_path.resolve()).encode("utf-8")).hexdigest()[:12]
        shadow_path = Path(tempfile.gettempdir()) / f"mongolian_medicine_kg_web_{digest}.sqlite"
        if not shadow_path.exists() or shadow_path.stat().st_mtime < self.db_path.stat().st_mtime:
            shutil.copy2(self.db_path, shadow_path)
        self.shadow_path = shadow_path
        return shadow_path


class WebsiteHandler(BaseHTTPRequestHandler):
    database: Database
    web_dir: Path

    server_version = "MongolianMedicineKG/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        params = parse_qs(parsed.query)

        try:
            if path == "/api/stats":
                self.send_json(self.api_stats())
            elif path == "/api/compare":
                self.send_json(self.api_compare(params))
            elif path == "/api/materials":
                self.send_json(self.api_materials(params))
            elif path.startswith("/api/materials/"):
                material_id = path.rsplit("/", 1)[-1]
                payload = self.api_material_detail(material_id)
                if payload is not None:
                    self.send_json(payload)
            elif path == "/api/search":
                self.send_json(self.api_search(params))
            elif path == "/api/triples":
                self.send_json(self.api_triples(params))
            elif path.startswith("/api/graph/"):
                material_id = path.rsplit("/", 1)[-1]
                self.send_json(self.api_graph(material_id, params))
            elif path.startswith("/api/"):
                self.send_error_json(HTTPStatus.NOT_FOUND, "API endpoint not found")
            else:
                self.serve_static(path)
        except Exception as exc:  # noqa: BLE001 - return useful local diagnostics.
            self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def log_message(self, format: str, *args: object) -> None:
        return

    def send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status: HTTPStatus, message: str) -> None:
        self.send_json({"error": message, "status": int(status)}, status)

    def serve_static(self, path: str) -> None:
        if path in ("", "/"):
            path = "/index.html"
        target = (self.web_dir / path.lstrip("/")).resolve()
        web_root = self.web_dir.resolve()
        if not str(target).startswith(str(web_root)) or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        content_type, _ = mimetypes.guess_type(target.name)
        content_type = content_type or "application/octet-stream"
        if content_type.startswith("text/") or content_type in ("application/javascript", "application/json"):
            content_type = f"{content_type}; charset=utf-8"
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def api_stats(self) -> dict[str, object]:
        with self.database.connect() as conn:
            metadata = {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM metadata ORDER BY key")}
            modules = [
                row_to_dict(row)
                for row in conn.execute(
                    """
                    SELECT module_code, module_name, row_count AS triple_count
                    FROM source_files
                    ORDER BY module_code
                    """
                )
            ]
            entity_types = [
                row_to_dict(row)
                for row in conn.execute(
                    """
                    SELECT entity_type, COUNT(*) AS count
                    FROM entities
                    GROUP BY entity_type
                    ORDER BY count DESC, entity_type
                    """
                )
            ]
            facets = {
                "term_category": self.distinct_sql(conn, "SELECT DISTINCT term_category AS value FROM terminology ORDER BY value"),
                "property_class": self.distinct_sql(
                    conn, "SELECT DISTINCT property_class AS value FROM medicinal_properties ORDER BY value"
                ),
                "source_type": self.distinct_sql(
                    conn,
                    """
                    SELECT DISTINCT source_type AS value
                    FROM material_origins
                    WHERE source_type IS NOT NULL AND source_type <> ''
                    ORDER BY value
                    """,
                ),
                "kingdom": self.distinct_sql(
                    conn,
                    """
                    SELECT DISTINCT kingdom_name AS value
                    FROM material_origins
                    WHERE kingdom_name IS NOT NULL AND kingdom_name <> ''
                    ORDER BY value
                    """,
                ),
            }
        return {"metadata": metadata, "modules": modules, "entity_types": entity_types, "facets": facets}

    @staticmethod
    def distinct_sql(conn: sqlite3.Connection, sql: str) -> list[str]:
        return [row["value"] for row in conn.execute(sql)]

    def api_materials(self, params: dict[str, list[str]]) -> dict[str, object]:
        query = self.param(params, "query")
        limit = clamp_int(self.param(params, "limit"), 24, 1, 100)
        offset = clamp_int(self.param(params, "offset"), 0, 0, 100_000)
        filters = {
            "term_category": self.param(params, "term_category"),
            "property_class": self.param(params, "property_class"),
            "source_type": self.param(params, "source_type"),
            "kingdom": self.param(params, "kingdom"),
        }

        where: list[str] = []
        sql_params: list[object] = []
        if query:
            where.append("(material_id LIKE ? OR label LIKE ? OR search_text LIKE ?)")
            pattern = like_pattern(query)
            sql_params.extend([pattern, pattern, pattern])
        if filters["term_category"]:
            where.append(
                """
                EXISTS (
                    SELECT 1
                    FROM mmp_mmt mm
                    JOIN terminology t ON t.mmt_id = mm.mmt_id
                    WHERE mm.material_id = materials.material_id
                      AND t.term_category LIKE ?
                )
                """
            )
            sql_params.append(like_pattern(filters["term_category"] or ""))
        if filters["property_class"]:
            where.append(
                """
                EXISTS (
                    SELECT 1
                    FROM medicinal_properties mp
                    WHERE mp.material_id = materials.material_id
                      AND mp.property_class = ?
                )
                """
            )
            sql_params.append(filters["property_class"])
        if filters["source_type"]:
            where.append(
                """
                EXISTS (
                    SELECT 1
                    FROM material_origins mo
                    WHERE mo.material_id = materials.material_id
                      AND mo.source_type = ?
                )
                """
            )
            sql_params.append(filters["source_type"])
        if filters["kingdom"]:
            where.append(
                """
                EXISTS (
                    SELECT 1
                    FROM material_origins mo
                    WHERE mo.material_id = materials.material_id
                      AND mo.kingdom_name = ?
                )
                """
            )
            sql_params.append(filters["kingdom"])
        where_clause = "WHERE " + " AND ".join(where) if where else ""

        with self.database.connect() as conn:
            total = conn.execute(f"SELECT COUNT(*) AS count FROM materials {where_clause}", sql_params).fetchone()["count"]
            rows = [
                row_to_dict(row)
                for row in conn.execute(
                    f"""
                    SELECT
                        material_id,
                        label,
                        functions_text,
                        indications_text,
                        flavors_text,
                        natures_text,
                        potencies_text,
                        terms_text,
                        properties_text,
                        families_text,
                        genera_text,
                        species_text,
                        source_type_text,
                        origins_text,
                        term_count,
                        property_count,
                        species_count
                    FROM materials
                    {where_clause}
                    ORDER BY material_id
                    LIMIT ? OFFSET ?
                    """,
                    [*sql_params, limit, offset],
                )
            ]
        for row in rows:
            row["source_description_text"] = SOURCE_DESCRIPTIONS.get(str(row["material_id"]), "")
        return {"total": total, "limit": limit, "offset": offset, "items": rows}

    def material_detail_payload(self, conn: sqlite3.Connection, material_id: str) -> dict[str, object] | None:
        material = conn.execute(
            "SELECT * FROM materials WHERE material_id = ? OR label = ? LIMIT 1",
            (material_id, material_id),
        ).fetchone()
        if material is None:
            return None
        resolved_id = material["material_id"]
        relation_summary = [
            row_to_dict(row)
            for row in conn.execute(
                """
                SELECT relation, group_concat(term_label, '；') AS terms
                FROM (
                    SELECT relation, term_label
                    FROM material_terms
                    WHERE material_id = ?
                    GROUP BY relation, term_label
                    ORDER BY
                        CASE relation
                            WHEN 'HAS_TASTE' THEN 1
                            WHEN 'HAS_NATURE' THEN 2
                            WHEN 'HAS_POTENCY' THEN 3
                            WHEN 'HAS_FUNCTION' THEN 4
                            WHEN 'TREATS_INDICATION' THEN 5
                            ELSE 99
                        END,
                        term_label
                )
                GROUP BY relation
                ORDER BY
                    CASE relation
                        WHEN 'HAS_TASTE' THEN 1
                        WHEN 'HAS_NATURE' THEN 2
                        WHEN 'HAS_POTENCY' THEN 3
                        WHEN 'HAS_FUNCTION' THEN 4
                        WHEN 'TREATS_INDICATION' THEN 5
                        ELSE 99
                    END
                """,
                (resolved_id,),
            )
        ]
        origins = [
            row_to_dict(row)
            for row in conn.execute(
                """
                SELECT
                    species_id,
                    species_name,
                    source_type,
                    genus_name,
                    family_name,
                    order_name,
                    class_name,
                    phylum_name,
                    kingdom_name
                FROM material_origins
                WHERE material_id = ?
                ORDER BY kingdom_name, species_name, species_id
                """,
                (resolved_id,),
            )
        ]
        terms = [
            row_to_dict(row)
            for row in conn.execute(
                """
                SELECT relation, term_id, term_type, term_label, source_field, module_code
                FROM material_terms
                WHERE material_id = ?
                ORDER BY
                    CASE relation
                        WHEN 'HAS_TASTE' THEN 1
                        WHEN 'HAS_NATURE' THEN 2
                        WHEN 'HAS_POTENCY' THEN 3
                        WHEN 'HAS_FUNCTION' THEN 4
                        WHEN 'TREATS_INDICATION' THEN 5
                        ELSE 99
                    END,
                    term_label
                """,
                (resolved_id,),
            )
        ]
        material_dict = row_to_dict(material)
        material_dict["source_description_text"] = SOURCE_DESCRIPTIONS.get(resolved_id, "")
        return {
            "material": material_dict,
            "relation_summary": relation_summary,
            "terms": terms,
            "origins": origins,
        }

    def api_material_detail(self, material_id: str) -> dict[str, object] | None:
        with self.database.connect() as conn:
            payload = self.material_detail_payload(conn, material_id)
        if payload is None:
            self.send_error_json(HTTPStatus.NOT_FOUND, f"Material not found: {material_id}")
        return payload

    def api_compare(self, params: dict[str, list[str]]) -> dict[str, object]:
        raw_ids: list[str] = []
        ids_param = self.param(params, "ids")
        if ids_param:
            raw_ids.extend(ids_param.split(","))
        raw_ids.extend(params.get("id", []))

        ids: list[str] = []
        seen: set[str] = set()
        for raw_id in raw_ids:
            material_id = raw_id.strip()
            if not material_id or material_id in seen:
                continue
            seen.add(material_id)
            ids.append(material_id)
            if len(ids) >= 30:
                break

        if not ids:
            return {"limit": 30, "items": [], "missing": []}

        items: list[dict[str, object]] = []
        missing: list[str] = []
        with self.database.connect() as conn:
            for material_id in ids:
                payload = self.material_detail_payload(conn, material_id)
                if payload is None:
                    missing.append(material_id)
                else:
                    items.append(payload)
        return {"limit": 30, "items": items, "missing": missing}

    def api_search(self, params: dict[str, list[str]]) -> dict[str, object]:
        query = self.param(params, "query")
        doc_type = self.param(params, "type")
        limit = clamp_int(self.param(params, "limit"), 20, 1, 100)
        if not query:
            return {"items": []}

        with self.database.connect() as conn:
            rows: list[sqlite3.Row] = []
            try:
                if doc_type and doc_type != "all":
                    type_filter = "AND d.doc_type = ?"
                else:
                    type_filter = "AND d.doc_type IN ('material', 'terminology', 'origin')"
                sql_params: list[object] = [quote_fts(query)]
                if doc_type and doc_type != "all":
                    sql_params.append(doc_type)
                sql_params.append(limit)
                rows = conn.execute(
                    f"""
                    SELECT
                        d.doc_type,
                        d.ref_id,
                        d.title,
                        snippet(search_documents_fts, 1, '[', ']', '...', 22) AS snippet,
                        d.tags
                    FROM search_documents_fts
                    JOIN search_documents d ON d.id = search_documents_fts.rowid
                    WHERE search_documents_fts MATCH ?
                    {type_filter}
                    LIMIT ?
                    """,
                    sql_params,
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []

            if not rows:
                pattern = like_pattern(query)
                where = "(title LIKE ? OR body LIKE ? OR tags LIKE ?)"
                sql_params = [pattern, pattern, pattern]
                if doc_type and doc_type != "all":
                    where += " AND doc_type = ?"
                    sql_params.append(doc_type)
                else:
                    where += " AND doc_type IN ('material', 'terminology', 'origin')"
                sql_params.append(limit)
                rows = conn.execute(
                    f"""
                    SELECT doc_type, ref_id, title, substr(body, 1, 260) AS snippet, tags
                    FROM search_documents
                    WHERE {where}
                    ORDER BY CASE doc_type WHEN 'material' THEN 1 WHEN 'entity' THEN 2 ELSE 3 END, id
                    LIMIT ?
                    """,
                    sql_params,
                ).fetchall()

        return {"items": [row_to_dict(row) for row in rows]}

    def api_triples(self, params: dict[str, list[str]]) -> dict[str, object]:
        query = self.param(params, "query")
        predicate = self.param(params, "predicate")
        material_id = self.param(params, "material_id")
        limit = clamp_int(self.param(params, "limit"), 50, 1, 200)

        where: list[str] = []
        sql_params: list[object] = []
        if query:
            pattern = like_pattern(query)
            where.append(
                """
                (
                    subject_id LIKE ?
                    OR subject_id LIKE ?
                    OR predicate LIKE ?
                    OR object_id LIKE ?
                    OR object_label LIKE ?
                    OR source_field LIKE ?
                    OR source_row_id LIKE ?
                )
                """
            )
            sql_params.extend([pattern, pattern, pattern, pattern, pattern, pattern, pattern])
        if predicate:
            where.append("predicate = ?")
            sql_params.append(predicate)
        if material_id:
            where.append("source_row_id = ?")
            sql_params.append(material_id)
        where_clause = "WHERE " + " AND ".join(where) if where else ""

        with self.database.connect() as conn:
            rows = [
                row_to_dict(row)
                for row in conn.execute(
                    f"""
                    SELECT
                        id,
                        module_code,
                        module_code AS module_name,
                        source_row_id,
                        subject_id,
                        predicate,
                        object_label AS object,
                        object_type AS object_kind,
                        source_field,
                        id AS line_no
                    FROM kg_edges
                    {where_clause}
                    ORDER BY id
                    LIMIT ?
                    """,
                    [*sql_params, limit],
                )
            ]
        return {"items": rows}

    def api_graph(self, material_id: str, params: dict[str, list[str]]) -> dict[str, object]:
        limit = clamp_int(self.param(params, "limit"), 140, 20, 300)
        with self.database.connect() as conn:
            material = conn.execute(
                "SELECT material_id, label FROM materials WHERE material_id = ? OR label = ? LIMIT 1",
                (material_id, material_id),
            ).fetchone()
            if material is None:
                self.send_error_json(HTTPStatus.NOT_FOUND, f"Material not found: {material_id}")
                return {}
            resolved_id = material["material_id"]
            graph_predicates = (
                "HAS_TASTE",
                "HAS_NATURE",
                "HAS_POTENCY",
                "HAS_FUNCTION",
                "TREATS_INDICATION",
            )
            rows = conn.execute(
                """
                SELECT
                    subject_id,
                    subject_label,
                    subject_type,
                    predicate,
                    object_id,
                    object_label,
                    object_type,
                    module_code,
                    source_field
                FROM kg_edges
                WHERE source_row_id = ?
                  AND predicate IN (?, ?, ?, ?, ?)
                ORDER BY
                    CASE
                        WHEN subject_type = 'MongolianMedicinalMaterial' THEN 0
                        ELSE 1
                    END,
                    CASE predicate
                        WHEN 'HAS_TASTE' THEN 1
                        WHEN 'HAS_NATURE' THEN 2
                        WHEN 'HAS_POTENCY' THEN 3
                        WHEN 'HAS_FUNCTION' THEN 4
                        WHEN 'TREATS_INDICATION' THEN 5
                        ELSE 99
                    END,
                    object_label
                LIMIT ?
                """,
                (resolved_id, *graph_predicates, limit),
            ).fetchall()

        nodes: dict[str, dict[str, object]] = {}
        edges: list[dict[str, object]] = []

        def add_node(node_id: str, label: str | None, node_type: str | None) -> None:
            if node_id not in nodes:
                if node_type == "DistributionEvidence":
                    label = "GBIF分布证据"
                elif node_type == "PharmacopoeiaComparison":
                    label = "药典比对"
                elif node_type == "SpecialtyAssessment":
                    label = "特色评估"
                nodes[node_id] = {
                    "id": node_id,
                    "label": label or node_id.split(":", 1)[-1],
                    "type": node_type or "",
                }

        center_id = f"MongolianMedicinalPiece:{resolved_id}"
        add_node(center_id, material["label"], "MongolianMedicinalPiece")
        for row in rows:
            add_node(row["subject_id"], row["subject_label"], row["subject_type"])
            add_node(row["object_id"], row["object_label"], row["object_type"])
            edges.append(
                {
                    "source": row["subject_id"],
                    "target": row["object_id"],
                    "predicate": row["predicate"],
                    "module_code": row["module_code"],
                    "source_field": row["source_field"],
                }
            )

        return {
            "material_id": resolved_id,
            "label": material["label"],
            "center_id": center_id,
            "nodes": list(nodes.values()),
            "edges": edges,
        }

    @staticmethod
    def param(params: dict[str, list[str]], key: str) -> str | None:
        values = params.get(key)
        if not values:
            return None
        value = values[0].strip()
        return value or None


def make_handler(database: Database, web_dir: Path) -> type[WebsiteHandler]:
    class BoundWebsiteHandler(WebsiteHandler):
        pass

    BoundWebsiteHandler.database = database
    BoundWebsiteHandler.web_dir = web_dir
    return BoundWebsiteHandler


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the Mongolian medicine database website.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind.")
    parser.add_argument("--port", type=int, default=8765, help="Port to bind.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite database path.")
    parser.add_argument("--web-dir", type=Path, default=DEFAULT_WEB_DIR, help="Static web directory.")
    args = parser.parse_args()

    ensure_curated_database(args.db)
    database = Database(args.db)
    handler = make_handler(database, args.web_dir)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving Mongolian medicine KG website at http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
