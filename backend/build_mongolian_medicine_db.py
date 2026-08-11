from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


TRIPLE_RE = re.compile(
    r"^(?P<subject>.+?)\s+--\[(?P<predicate>[^\]]+)\]-->\s+"
    r"(?P<object>.*?)\s+\|\s+source_field=(?P<source_field>.*?)"
    r"\s+\|\s+source_row_id=(?P<source_row_id>[^|\s]+)\s*$"
)
NODE_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*:.+$")
MODULE_PREFIX_RE = re.compile(r"^M(?P<number>\d+)_")


TEXT_COLUMNS = {
    "source_description",
    "source_category",
    "usage_dosage",
    "caution",
    "pharmacopoeia_status",
    "pharmacopoeia_matched_name",
    "pharmacopoeia_evidence",
    "theory_basis_flag",
    "clinical_use_flag",
    "locality_evidence",
    "specialty_candidate_status",
    "assessment_conclusion",
    "review_priority",
    "gbif_matched_name",
    "gbif_match_status",
    "national_distribution",
    "inner_mongolia_distribution_flag",
    "inner_mongolia_wide_status",
    "distribution_judgement_basis",
    "distribution_data_source",
}

INTEGER_COLUMNS = {
    "national_province_count",
    "china_record_count",
    "inner_mongolia_record_count",
    "inner_mongolia_place_count",
}

MATERIAL_RELATIONS_FOR_SEARCH = {
    "HAS_SOURCE_CATEGORY",
    "HAS_TASTE",
    "HAS_NATURE",
    "HAS_POTENCY",
    "HAS_FUNCTION",
    "TREATS_INDICATION",
    "RECORDED_IN",
}


@dataclass(frozen=True)
class Triple:
    id: int
    module_code: str
    module_name: str
    source_file: str
    line_no: int
    subject_id: str
    subject_type: str
    predicate: str
    object_kind: str
    object_id: str | None
    object_type: str | None
    object_value: str | None
    source_field: str
    source_row_id: str
    raw_text: str


def split_node_id(node_id: str) -> tuple[str | None, str]:
    if ":" not in node_id:
        return None, node_id
    node_type, local_name = node_id.split(":", 1)
    return node_type, local_name


def parse_object(raw_object: str) -> tuple[str, str | None, str | None, str | None]:
    value = raw_object.strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return "literal", None, None, value[1:-1].replace('\\"', '"')
    if NODE_ID_RE.match(value):
        node_type, _ = split_node_id(value)
        return "node", value, node_type, None
    return "class", None, None, value


def module_sort_key(path: Path) -> tuple[int, str]:
    match = MODULE_PREFIX_RE.match(path.name)
    if not match:
        return (10_000, path.name)
    return (int(match.group("number")), path.name)


def module_info(path: Path) -> tuple[str, str]:
    stem = path.stem
    module_code, module_name = stem.split("_", 1)
    suffix = "_知识图谱基础数据"
    if module_name.endswith(suffix):
        module_name = module_name[: -len(suffix)]
    return module_code, module_name


def parse_input_files(input_dir: Path) -> tuple[list[Triple], list[dict[str, object]]]:
    files = sorted(input_dir.glob("M*_知识图谱基础数据.txt"), key=module_sort_key)
    if not files:
        raise FileNotFoundError(f"No module text files found in {input_dir}")

    triples: list[Triple] = []
    source_files: list[dict[str, object]] = []
    errors: list[str] = []
    next_id = 1

    for path in files:
        module_code, module_name = module_info(path)
        parsed_count = 0
        with path.open("r", encoding="utf-8-sig") as handle:
            for line_no, raw_line in enumerate(handle, start=1):
                raw_text = raw_line.rstrip("\n")
                stripped = raw_text.strip()
                if not stripped or stripped.startswith("#"):
                    continue

                match = TRIPLE_RE.match(stripped)
                if not match:
                    errors.append(f"{path.name}:{line_no}: {stripped[:160]}")
                    continue

                subject_id = match.group("subject").strip()
                subject_type, _ = split_node_id(subject_id)
                object_kind, object_id, object_type, object_value = parse_object(match.group("object"))

                triples.append(
                    Triple(
                        id=next_id,
                        module_code=module_code,
                        module_name=module_name,
                        source_file=path.name,
                        line_no=line_no,
                        subject_id=subject_id,
                        subject_type=subject_type or "",
                        predicate=match.group("predicate").strip(),
                        object_kind=object_kind,
                        object_id=object_id,
                        object_type=object_type,
                        object_value=object_value,
                        source_field=match.group("source_field").strip(),
                        source_row_id=match.group("source_row_id").strip(),
                        raw_text=stripped,
                    )
                )
                next_id += 1
                parsed_count += 1

        source_files.append(
            {
                "filename": path.name,
                "module_code": module_code,
                "module_name": module_name,
                "triple_count": parsed_count,
            }
        )

    if errors:
        sample = "\n".join(errors[:20])
        raise ValueError(f"Failed to parse {len(errors)} lines. First examples:\n{sample}")

    return triples, source_files


def add_unique(bucket: list[str], value: str | None) -> None:
    if not value:
        return
    clean = value.strip()
    if clean and clean not in bucket:
        bucket.append(clean)


def joined(values: list[str], sep: str = "；") -> str | None:
    clean = [value for value in values if value]
    return sep.join(clean) if clean else None


def parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def first_int(values: list[str]) -> int | None:
    for value in values:
        parsed = parse_int(value)
        if parsed is not None:
            return parsed
    return None


def create_schema(conn: sqlite3.Connection) -> str:
    conn.executescript(
        """
        PRAGMA foreign_keys = OFF;

        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE source_files (
            filename TEXT PRIMARY KEY,
            module_code TEXT NOT NULL,
            module_name TEXT NOT NULL,
            triple_count INTEGER NOT NULL
        );

        CREATE TABLE triples (
            id INTEGER PRIMARY KEY,
            module_code TEXT NOT NULL,
            module_name TEXT NOT NULL,
            source_file TEXT NOT NULL,
            line_no INTEGER NOT NULL,
            subject_id TEXT NOT NULL,
            subject_type TEXT,
            predicate TEXT NOT NULL,
            object_kind TEXT NOT NULL CHECK (object_kind IN ('node', 'literal', 'class')),
            object_id TEXT,
            object_type TEXT,
            object_value TEXT,
            source_field TEXT NOT NULL,
            source_row_id TEXT NOT NULL,
            raw_text TEXT NOT NULL
        );

        CREATE TABLE entities (
            entity_id TEXT PRIMARY KEY,
            entity_type TEXT,
            local_name TEXT,
            label TEXT,
            module_codes_json TEXT NOT NULL,
            source_row_ids_json TEXT NOT NULL,
            search_text TEXT
        );

        CREATE TABLE kg_edges (
            id INTEGER PRIMARY KEY,
            triple_id INTEGER NOT NULL,
            module_code TEXT NOT NULL,
            module_name TEXT NOT NULL,
            subject_id TEXT NOT NULL,
            subject_type TEXT,
            predicate TEXT NOT NULL,
            object_id TEXT NOT NULL,
            object_type TEXT,
            source_field TEXT NOT NULL,
            source_row_id TEXT NOT NULL
        );

        CREATE TABLE literal_properties (
            id INTEGER PRIMARY KEY,
            triple_id INTEGER NOT NULL,
            module_code TEXT NOT NULL,
            module_name TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            entity_type TEXT,
            predicate TEXT NOT NULL,
            value TEXT,
            source_field TEXT NOT NULL,
            source_row_id TEXT NOT NULL
        );

        CREATE TABLE materials (
            material_id TEXT PRIMARY KEY,
            label TEXT,
            source_description TEXT,
            source_category TEXT,
            usage_dosage TEXT,
            caution TEXT,
            pharmacopoeia_status TEXT,
            pharmacopoeia_matched_name TEXT,
            pharmacopoeia_evidence TEXT,
            theory_basis_flag TEXT,
            clinical_use_flag TEXT,
            locality_evidence TEXT,
            specialty_candidate_status TEXT,
            assessment_conclusion TEXT,
            review_priority TEXT,
            gbif_matched_name TEXT,
            gbif_match_status TEXT,
            national_distribution TEXT,
            national_province_count INTEGER,
            china_record_count INTEGER,
            inner_mongolia_record_count INTEGER,
            inner_mongolia_place_count INTEGER,
            inner_mongolia_distribution_flag TEXT,
            inner_mongolia_wide_status TEXT,
            distribution_judgement_basis TEXT,
            distribution_data_source TEXT,
            terms_text TEXT,
            search_text TEXT
        );

        CREATE TABLE material_terms (
            id INTEGER PRIMARY KEY,
            material_id TEXT NOT NULL,
            relation TEXT NOT NULL,
            term_id TEXT NOT NULL,
            term_type TEXT,
            term_label TEXT,
            source_field TEXT NOT NULL,
            module_code TEXT NOT NULL
        );

        CREATE TABLE distribution_regions (
            id INTEGER PRIMARY KEY,
            material_id TEXT NOT NULL,
            region TEXT NOT NULL,
            record_count INTEGER,
            source_field TEXT NOT NULL,
            module_code TEXT NOT NULL
        );

        CREATE TABLE search_documents (
            id INTEGER PRIMARY KEY,
            doc_type TEXT NOT NULL,
            ref_id TEXT NOT NULL,
            title TEXT,
            body TEXT,
            tags TEXT
        );
        """
    )

    tokenizer = "trigram"
    try:
        conn.executescript(
            """
            CREATE VIRTUAL TABLE material_fts USING fts5(
                material_id UNINDEXED,
                label,
                source_description,
                source_category,
                terms,
                evidence,
                tokenize='trigram'
            );
            CREATE VIRTUAL TABLE entity_fts USING fts5(
                entity_id UNINDEXED,
                entity_type,
                label,
                search_text,
                tokenize='trigram'
            );
            CREATE VIRTUAL TABLE triple_fts USING fts5(
                triple_id UNINDEXED,
                subject_id,
                predicate,
                object_text,
                source_field,
                source_row_id,
                raw_text,
                tokenize='trigram'
            );
            CREATE VIRTUAL TABLE search_documents_fts USING fts5(
                doc_type UNINDEXED,
                ref_id UNINDEXED,
                title,
                body,
                tags,
                tokenize='trigram'
            );
            """
        )
    except sqlite3.OperationalError:
        tokenizer = "unicode61"
        conn.executescript(
            """
            CREATE VIRTUAL TABLE material_fts USING fts5(
                material_id UNINDEXED,
                label,
                source_description,
                source_category,
                terms,
                evidence
            );
            CREATE VIRTUAL TABLE entity_fts USING fts5(
                entity_id UNINDEXED,
                entity_type,
                label,
                search_text
            );
            CREATE VIRTUAL TABLE triple_fts USING fts5(
                triple_id UNINDEXED,
                subject_id,
                predicate,
                object_text,
                source_field,
                source_row_id,
                raw_text
            );
            CREATE VIRTUAL TABLE search_documents_fts USING fts5(
                doc_type UNINDEXED,
                ref_id UNINDEXED,
                title,
                body,
                tags
            );
            """
        )

    conn.executescript(
        """
        CREATE INDEX idx_triples_subject ON triples(subject_id);
        CREATE INDEX idx_triples_object ON triples(object_id);
        CREATE INDEX idx_triples_predicate ON triples(predicate);
        CREATE INDEX idx_triples_source_row ON triples(source_row_id);
        CREATE INDEX idx_entities_type ON entities(entity_type);
        CREATE INDEX idx_edges_subject ON kg_edges(subject_id);
        CREATE INDEX idx_edges_object ON kg_edges(object_id);
        CREATE INDEX idx_edges_predicate ON kg_edges(predicate);
        CREATE INDEX idx_properties_entity ON literal_properties(entity_id);
        CREATE INDEX idx_properties_predicate ON literal_properties(predicate);
        CREATE INDEX idx_material_terms_material ON material_terms(material_id);
        CREATE INDEX idx_material_terms_relation ON material_terms(relation);
        CREATE INDEX idx_distribution_regions_material ON distribution_regions(material_id);
        CREATE INDEX idx_distribution_regions_region ON distribution_regions(region);

        CREATE VIEW v_kg_edges_labeled AS
        SELECT
            e.id,
            e.triple_id,
            e.module_code,
            e.module_name,
            e.source_row_id,
            e.source_field,
            e.subject_id,
            subj.label AS subject_label,
            e.subject_type,
            e.predicate,
            e.object_id,
            obj.label AS object_label,
            e.object_type
        FROM kg_edges e
        LEFT JOIN entities subj ON subj.entity_id = e.subject_id
        LEFT JOIN entities obj ON obj.entity_id = e.object_id;

        CREATE VIEW v_material_relation_summary AS
        SELECT
            material_id,
            relation,
            group_concat(term_label, '；') AS terms
        FROM (
            SELECT DISTINCT material_id, relation, term_label
            FROM material_terms
            WHERE term_label IS NOT NULL AND term_label <> ''
            ORDER BY material_id, relation, term_label
        )
        GROUP BY material_id, relation;
        """
    )
    return tokenizer


def build_entity_records(triples: list[Triple]) -> tuple[list[tuple], dict[str, str], dict[str, str]]:
    entity_types: dict[str, str] = {}
    entity_labels: dict[str, str] = {}
    entity_modules: dict[str, set[str]] = defaultdict(set)
    entity_rows: dict[str, set[str]] = defaultdict(set)
    entity_search_values: dict[str, list[str]] = defaultdict(list)

    def ensure_entity(entity_id: str, entity_type: str | None, triple: Triple) -> None:
        inferred_type, local_name = split_node_id(entity_id)
        final_type = entity_type or inferred_type or ""
        if final_type and not entity_types.get(entity_id):
            entity_types[entity_id] = final_type
        entity_modules[entity_id].add(triple.module_code)
        entity_rows[entity_id].add(triple.source_row_id)
        add_unique(entity_search_values[entity_id], entity_id)
        add_unique(entity_search_values[entity_id], local_name)

    for triple in triples:
        ensure_entity(triple.subject_id, triple.subject_type, triple)
        if triple.object_kind == "node" and triple.object_id:
            ensure_entity(triple.object_id, triple.object_type, triple)

        if triple.predicate == "rdf:type" and triple.object_value:
            entity_types[triple.subject_id] = entity_types.get(triple.subject_id) or triple.object_value
        elif triple.predicate == "rdfs:label" and triple.object_value:
            entity_labels.setdefault(triple.subject_id, triple.object_value)
            add_unique(entity_search_values[triple.subject_id], triple.object_value)
        elif triple.object_kind != "node" and triple.object_value:
            add_unique(entity_search_values[triple.subject_id], triple.object_value)

    records: list[tuple] = []
    for entity_id in sorted(entity_modules):
        entity_type, local_name = split_node_id(entity_id)
        final_type = entity_types.get(entity_id) or entity_type or ""
        label = entity_labels.get(entity_id) or local_name
        add_unique(entity_search_values[entity_id], final_type)
        add_unique(entity_search_values[entity_id], label)
        records.append(
            (
                entity_id,
                final_type,
                local_name,
                label,
                json.dumps(sorted(entity_modules[entity_id]), ensure_ascii=False),
                json.dumps(sorted(entity_rows[entity_id]), ensure_ascii=False),
                " ".join(entity_search_values[entity_id]),
            )
        )

    return records, entity_labels, entity_types


def material_column_for_triple(triple: Triple) -> str | None:
    if triple.subject_type == "MongolianMedicinalMaterial":
        if triple.predicate == "rdfs:label":
            return "label"
        if triple.predicate == "source_description_text":
            return "source_description"
        if triple.predicate == "source_category_text":
            return "source_category"

    if triple.subject_type == "SourceDescription" and triple.predicate == "rdfs:label":
        return "source_description"
    if triple.subject_type == "UsageDosage" and triple.predicate == "rdfs:label":
        return "usage_dosage"
    if triple.subject_type == "Caution" and triple.predicate == "rdfs:label":
        return "caution"

    if triple.subject_type == "PharmacopoeiaComparison":
        return {
            "comparison_status": "pharmacopoeia_status",
            "matched_name": "pharmacopoeia_matched_name",
            "comparison_evidence": "pharmacopoeia_evidence",
        }.get(triple.predicate)

    if triple.subject_type == "SpecialtyAssessment":
        return {
            "theory_basis_flag": "theory_basis_flag",
            "clinical_use_flag": "clinical_use_flag",
            "locality_evidence": "locality_evidence",
            "specialty_candidate_status": "specialty_candidate_status",
            "assessment_conclusion": "assessment_conclusion",
            "review_priority": "review_priority",
        }.get(triple.predicate)

    if triple.subject_type == "DistributionEvidence":
        return {
            "gbif_matched_name": "gbif_matched_name",
            "gbif_match_status": "gbif_match_status",
            "national_distribution": "national_distribution",
            "national_province_count": "national_province_count",
            "china_record_count": "china_record_count",
            "inner_mongolia_record_count": "inner_mongolia_record_count",
            "inner_mongolia_place_count": "inner_mongolia_place_count",
            "inner_mongolia_distribution_flag": "inner_mongolia_distribution_flag",
            "inner_mongolia_wide_status": "inner_mongolia_wide_status",
            "distribution_judgement_basis": "distribution_judgement_basis",
            "distribution_data_source": "distribution_data_source",
        }.get(triple.predicate)

    return None


def build_material_records(
    triples: list[Triple],
    entity_labels: dict[str, str],
) -> tuple[list[tuple], list[tuple], list[tuple]]:
    material_ids = sorted({triple.source_row_id for triple in triples if triple.source_row_id.startswith("MM")})
    text_values: dict[str, dict[str, list[str]]] = {
        material_id: defaultdict(list) for material_id in material_ids
    }
    int_values: dict[str, dict[str, list[str]]] = {
        material_id: defaultdict(list) for material_id in material_ids
    }
    material_terms: list[tuple] = []
    material_term_seen: set[tuple[str, str, str, str]] = set()
    distribution_regions: list[tuple] = []
    distribution_seen: set[tuple[str, str, str]] = set()
    term_text_values: dict[str, list[str]] = defaultdict(list)

    for triple in triples:
        material_id = triple.source_row_id
        if material_id not in text_values:
            continue

        if triple.object_kind != "node" and triple.object_value is not None:
            column = material_column_for_triple(triple)
            if column in TEXT_COLUMNS or column == "label":
                add_unique(text_values[material_id][column], triple.object_value)
            elif column in INTEGER_COLUMNS:
                add_unique(int_values[material_id][column], triple.object_value)

        if (
            triple.subject_type == "MongolianMedicinalMaterial"
            and triple.object_kind == "node"
            and triple.object_id
        ):
            term_label = entity_labels.get(triple.object_id) or split_node_id(triple.object_id)[1]
            key = (material_id, triple.predicate, triple.object_id, triple.source_field)
            if key not in material_term_seen:
                material_term_seen.add(key)
                material_terms.append(
                    (
                        material_id,
                        triple.predicate,
                        triple.object_id,
                        triple.object_type,
                        term_label,
                        triple.source_field,
                        triple.module_code,
                    )
                )
            if triple.predicate in MATERIAL_RELATIONS_FOR_SEARCH:
                add_unique(term_text_values[material_id], term_label)

        if (
            triple.subject_type == "DistributionEvidence"
            and triple.predicate.startswith("region_record:")
            and triple.object_value is not None
        ):
            region = triple.predicate.split(":", 1)[1]
            key = (material_id, region, triple.object_value)
            if key not in distribution_seen:
                distribution_seen.add(key)
                distribution_regions.append(
                    (
                        material_id,
                        region,
                        parse_int(triple.object_value),
                        triple.source_field,
                        triple.module_code,
                    )
                )

    material_records: list[tuple] = []
    for material_id in material_ids:
        values = text_values[material_id]
        ints = int_values[material_id]
        terms_text = joined(term_text_values[material_id])
        search_parts = [
            material_id,
            joined(values.get("label", [])),
            joined(values.get("source_description", [])),
            joined(values.get("source_category", [])),
            joined(values.get("usage_dosage", [])),
            joined(values.get("caution", [])),
            joined(values.get("pharmacopoeia_status", [])),
            joined(values.get("pharmacopoeia_matched_name", [])),
            joined(values.get("pharmacopoeia_evidence", [])),
            joined(values.get("specialty_candidate_status", [])),
            joined(values.get("assessment_conclusion", [])),
            joined(values.get("review_priority", [])),
            joined(values.get("gbif_matched_name", [])),
            joined(values.get("gbif_match_status", [])),
            joined(values.get("national_distribution", [])),
            joined(values.get("inner_mongolia_distribution_flag", [])),
            joined(values.get("inner_mongolia_wide_status", [])),
            terms_text,
        ]
        search_text = " ".join(part for part in search_parts if part)

        material_records.append(
            (
                material_id,
                joined(values.get("label", [])),
                joined(values.get("source_description", [])),
                joined(values.get("source_category", [])),
                joined(values.get("usage_dosage", [])),
                joined(values.get("caution", [])),
                joined(values.get("pharmacopoeia_status", [])),
                joined(values.get("pharmacopoeia_matched_name", [])),
                joined(values.get("pharmacopoeia_evidence", [])),
                joined(values.get("theory_basis_flag", [])),
                joined(values.get("clinical_use_flag", [])),
                joined(values.get("locality_evidence", [])),
                joined(values.get("specialty_candidate_status", [])),
                joined(values.get("assessment_conclusion", [])),
                joined(values.get("review_priority", [])),
                joined(values.get("gbif_matched_name", [])),
                joined(values.get("gbif_match_status", [])),
                joined(values.get("national_distribution", [])),
                first_int(ints.get("national_province_count", [])),
                first_int(ints.get("china_record_count", [])),
                first_int(ints.get("inner_mongolia_record_count", [])),
                first_int(ints.get("inner_mongolia_place_count", [])),
                joined(values.get("inner_mongolia_distribution_flag", [])),
                joined(values.get("inner_mongolia_wide_status", [])),
                joined(values.get("distribution_judgement_basis", [])),
                joined(values.get("distribution_data_source", [])),
                terms_text,
                search_text,
            )
        )

    return material_records, material_terms, distribution_regions


def populate_database(
    conn: sqlite3.Connection,
    triples: list[Triple],
    source_files: list[dict[str, object]],
    tokenizer: str,
) -> None:
    conn.executemany(
        """
        INSERT INTO source_files(filename, module_code, module_name, triple_count)
        VALUES(:filename, :module_code, :module_name, :triple_count)
        """,
        source_files,
    )

    conn.executemany(
        """
        INSERT INTO triples(
            id, module_code, module_name, source_file, line_no,
            subject_id, subject_type, predicate, object_kind, object_id,
            object_type, object_value, source_field, source_row_id, raw_text
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                triple.id,
                triple.module_code,
                triple.module_name,
                triple.source_file,
                triple.line_no,
                triple.subject_id,
                triple.subject_type,
                triple.predicate,
                triple.object_kind,
                triple.object_id,
                triple.object_type,
                triple.object_value,
                triple.source_field,
                triple.source_row_id,
                triple.raw_text,
            )
            for triple in triples
        ],
    )

    entity_records, entity_labels, entity_types = build_entity_records(triples)
    conn.executemany(
        """
        INSERT INTO entities(
            entity_id, entity_type, local_name, label,
            module_codes_json, source_row_ids_json, search_text
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        entity_records,
    )

    conn.executemany(
        """
        INSERT INTO kg_edges(
            triple_id, module_code, module_name, subject_id, subject_type,
            predicate, object_id, object_type, source_field, source_row_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                triple.id,
                triple.module_code,
                triple.module_name,
                triple.subject_id,
                triple.subject_type,
                triple.predicate,
                triple.object_id,
                triple.object_type,
                triple.source_field,
                triple.source_row_id,
            )
            for triple in triples
            if triple.object_kind == "node" and triple.object_id
        ],
    )

    conn.executemany(
        """
        INSERT INTO literal_properties(
            triple_id, module_code, module_name, entity_id, entity_type,
            predicate, value, source_field, source_row_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                triple.id,
                triple.module_code,
                triple.module_name,
                triple.subject_id,
                triple.subject_type,
                triple.predicate,
                triple.object_value,
                triple.source_field,
                triple.source_row_id,
            )
            for triple in triples
            if triple.object_kind != "node"
        ],
    )

    material_records, material_terms, distribution_regions = build_material_records(triples, entity_labels)
    conn.executemany(
        """
        INSERT INTO materials(
            material_id, label, source_description, source_category, usage_dosage,
            caution, pharmacopoeia_status, pharmacopoeia_matched_name,
            pharmacopoeia_evidence, theory_basis_flag, clinical_use_flag,
            locality_evidence, specialty_candidate_status, assessment_conclusion,
            review_priority, gbif_matched_name, gbif_match_status,
            national_distribution, national_province_count, china_record_count,
            inner_mongolia_record_count, inner_mongolia_place_count,
            inner_mongolia_distribution_flag, inner_mongolia_wide_status,
            distribution_judgement_basis, distribution_data_source,
            terms_text, search_text
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        material_records,
    )

    conn.executemany(
        """
        INSERT INTO material_terms(
            material_id, relation, term_id, term_type, term_label, source_field, module_code
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        material_terms,
    )

    conn.executemany(
        """
        INSERT INTO distribution_regions(
            material_id, region, record_count, source_field, module_code
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        distribution_regions,
    )

    populate_fts(conn, triples, entity_records, material_records, entity_labels)

    stats = {
        "source_file_count": len(source_files),
        "triple_count": len(triples),
        "entity_count": len(entity_records),
        "edge_count": sum(1 for triple in triples if triple.object_kind == "node"),
        "literal_property_count": sum(1 for triple in triples if triple.object_kind != "node"),
        "material_count": len(material_records),
        "material_term_count": len(material_terms),
        "distribution_region_count": len(distribution_regions),
        "fts_tokenizer": tokenizer,
    }
    conn.executemany(
        "INSERT INTO metadata(key, value) VALUES(?, ?)",
        [(key, str(value)) for key, value in stats.items()],
    )


def populate_fts(
    conn: sqlite3.Connection,
    triples: list[Triple],
    entity_records: list[tuple],
    material_records: list[tuple],
    entity_labels: dict[str, str],
) -> None:
    conn.executemany(
        """
        INSERT INTO material_fts(
            material_id, label, source_description, source_category, terms, evidence
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                record[0],
                record[1],
                record[2],
                record[3],
                record[26],
                " ".join(part for part in (record[6], record[8], record[12], record[13], record[14], record[16], record[17], record[22], record[23]) if part),
            )
            for record in material_records
        ],
    )

    conn.executemany(
        """
        INSERT INTO entity_fts(entity_id, entity_type, label, search_text)
        VALUES (?, ?, ?, ?)
        """,
        [(record[0], record[1], record[3], record[6]) for record in entity_records],
    )

    conn.executemany(
        """
        INSERT INTO triple_fts(
            triple_id, subject_id, predicate, object_text,
            source_field, source_row_id, raw_text
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                triple.id,
                triple.subject_id,
                triple.predicate,
                entity_labels.get(triple.object_id or "") if triple.object_kind == "node" else triple.object_value,
                triple.source_field,
                triple.source_row_id,
                triple.raw_text,
            )
            for triple in triples
        ],
    )

    search_documents: list[tuple] = []
    next_id = 1
    for record in material_records:
        tags = " ".join(part for part in (record[3], record[12], record[14], record[16], record[22], record[23]) if part)
        search_documents.append((next_id, "material", record[0], record[1], record[27], tags))
        next_id += 1
    for record in entity_records:
        search_documents.append((next_id, "entity", record[0], record[3], record[6], record[1]))
        next_id += 1
    for triple in triples:
        object_text = entity_labels.get(triple.object_id or "") if triple.object_kind == "node" else triple.object_value
        title = f"{triple.subject_id} {triple.predicate} {object_text or triple.object_id or ''}".strip()
        tags = f"{triple.module_code} {triple.source_field} {triple.source_row_id}"
        search_documents.append((next_id, "triple", str(triple.id), title, triple.raw_text, tags))
        next_id += 1

    conn.executemany(
        "INSERT INTO search_documents(id, doc_type, ref_id, title, body, tags) VALUES (?, ?, ?, ?, ?, ?)",
        search_documents,
    )
    conn.executemany(
        "INSERT INTO search_documents_fts(rowid, doc_type, ref_id, title, body, tags) VALUES (?, ?, ?, ?, ?, ?)",
        search_documents,
    )


def build_database(input_dir: Path, output_path: Path) -> dict[str, str]:
    triples, source_files = parse_input_files(input_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    for stale_path in (
        output_path.with_name(output_path.name + ".tmp"),
        output_path.with_name(output_path.name + ".tmp-journal"),
        output_path.with_name(output_path.name + ".tmp-wal"),
        output_path.with_name(output_path.name + ".tmp-shm"),
    ):
        if stale_path.exists():
            try:
                stale_path.unlink()
            except PermissionError:
                pass

    with tempfile.TemporaryDirectory(prefix="mongolian_medicine_kg_") as temp_dir:
        build_path = Path(temp_dir) / "mongolian_medicine_kg.sqlite"
        conn = sqlite3.connect(build_path)
        try:
            conn.execute("PRAGMA journal_mode = DELETE")
            conn.execute("PRAGMA synchronous = NORMAL")
            tokenizer = create_schema(conn)
            populate_database(conn, triples, source_files, tokenizer)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        if output_path.exists():
            output_path.unlink()
        shutil.copy2(build_path, output_path)

    return {
        "output": str(output_path),
        "source_file_count": str(len(source_files)),
        "triple_count": str(len(triples)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a SQLite Mongolian medicine database and knowledge-graph search index."
    )
    parser.add_argument("--input-dir", type=Path, default=Path.cwd(), help="Directory containing M1-M10 text files.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data") / "mongolian_medicine_kg.sqlite",
        help="Output SQLite database path.",
    )
    args = parser.parse_args()

    result = build_database(args.input_dir, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
