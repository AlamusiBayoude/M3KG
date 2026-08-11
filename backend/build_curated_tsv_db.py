from __future__ import annotations

import argparse
import csv
import re
import sqlite3
import zipfile
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = ROOT / "curated_tsv_dataset_20260623"
DEFAULT_OUTPUT_DB = ROOT / "data" / "m3kg_curated_20260623.sqlite"
RESTORED_WORKBOOK = "Mongolian_medicinal_pieces_restored_table.xlsx"
SOURCE_DESCRIPTION_DIR = ROOT.parent / "outputs" / "kg_triples_by_module"

MODULES = [
    ("D1", "Mongolian medicine terminology", "D1_Mongolian_medicine_terminology.tsv"),
    ("D2", "Mongolian medicinal pieces", "D2_Mongolian_medicinal_pieces.tsv"),
    ("D3", "MMP-MMT associations", "D3_MMP_MMT.tsv"),
    ("D4", "MMP medicinal properties", "D4_MMP_Medicinal_properties.tsv"),
    ("D5", "Pharmacognostic origin taxonomy", "D5_Pharmacognostic_origin.tsv"),
    ("D6", "MMP-PO associations", "D6_MMP_PO.tsv"),
]

TERM_CATEGORY_MAP = {
    "Therapeutic function": ("HAS_FUNCTION", "FunctionTerm", "功能"),
    "Clinical indication": ("TREATS_INDICATION", "IndicationTerm", "主治"),
}

PROPERTY_CLASS_MAP = {
    "Medicinal flavor": ("HAS_TASTE", "Taste", "味"),
    "Medicinal nature": ("HAS_NATURE", "Nature", "性"),
    "Medicinal potency feature": ("HAS_POTENCY", "PotencyFeature", "效能"),
}


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle, delimiter="\t")]


def compact(values: list[str], sep: str = "；") -> str:
    seen: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.append(text)
    return sep.join(seen)


def split_term_categories(value: str) -> list[str]:
    return [part.strip() for part in str(value or "").split("|") if part.strip()]


def split_semicolon(value: object) -> list[str]:
    return [part.strip() for part in re.split(r"[；;]", str(value or "")) if part.strip()]


def excel_col_index(cell_ref: str) -> int:
    letters = re.match(r"[A-Z]+", cell_ref.upper())
    if not letters:
        return 0
    index = 0
    for char in letters.group(0):
        index = index * 26 + ord(char) - ord("A") + 1
    return index - 1


def cell_text(cell: ET.Element, shared_strings: list[str], namespace: dict[str, str]) -> str:
    cell_type = cell.attrib.get("t", "")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//main:t", namespace)).strip()
    value = cell.find("main:v", namespace)
    if value is None or value.text is None:
        return ""
    text = value.text.strip()
    if cell_type == "s":
        try:
            return shared_strings[int(text)].strip()
        except (IndexError, ValueError):
            return ""
    return text


def read_xlsx_table(path: Path, sheet_name: str) -> list[dict[str, str]]:
    namespace = {
        "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "pkg": "http://schemas.openxmlformats.org/package/2006/relationships",
    }
    with zipfile.ZipFile(path) as archive:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in shared_root.findall("main:si", namespace):
                shared_strings.append("".join(node.text or "" for node in item.findall(".//main:t", namespace)))

        workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
        sheet_rel_id = ""
        for sheet in workbook_root.findall(".//main:sheet", namespace):
            if sheet.attrib.get("name") == sheet_name:
                sheet_rel_id = sheet.attrib.get(f"{{{namespace['rel']}}}id", "")
                break
        if not sheet_rel_id:
            first_sheet = workbook_root.find(".//main:sheet", namespace)
            if first_sheet is None:
                return []
            sheet_rel_id = first_sheet.attrib.get(f"{{{namespace['rel']}}}id", "")

        rels_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        sheet_target = ""
        for relationship in rels_root.findall("pkg:Relationship", namespace):
            if relationship.attrib.get("Id") == sheet_rel_id:
                sheet_target = relationship.attrib.get("Target", "")
                break
        if not sheet_target:
            return []
        normalized_target = sheet_target.lstrip("/")
        sheet_path = normalized_target if normalized_target.startswith("xl/") else f"xl/{normalized_target}"
        sheet_root = ET.fromstring(archive.read(sheet_path))

    rows: list[list[str]] = []
    for row in sheet_root.findall(".//main:sheetData/main:row", namespace):
        values: dict[int, str] = {}
        max_index = -1
        for cell in row.findall("main:c", namespace):
            ref = cell.attrib.get("r", "")
            index = excel_col_index(ref)
            max_index = max(max_index, index)
            values[index] = cell_text(cell, shared_strings, namespace)
        if max_index >= 0:
            rows.append([values.get(index, "") for index in range(max_index + 1)])
    if not rows:
        return []
    headers = [value.strip() for value in rows[0]]
    return [
        {headers[index]: row[index] if index < len(row) else "" for index in range(len(headers))}
        for row in rows[1:]
        if any(str(value or "").strip() for value in row)
    ]


def material_id_from_mm_id(mm_id: str) -> str:
    match = re.fullmatch(r"MM(\d+)", str(mm_id or "").strip())
    if not match:
        return str(mm_id or "").strip()
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


def source_type_from_kingdom(kingdom_name: str) -> str:
    normalized = str(kingdom_name or "").strip().lower()
    if normalized in {"viridiplantae", "plantae"}:
        return "植物"
    if normalized in {"metazoa", "animalia"}:
        return "动物"
    if normalized in {"fungi", "mycota"}:
        return "真菌"
    return ""


def infer_source_type(kingdom_name: str, description: str, label: str = "", species_name: str = "") -> str:
    by_kingdom = source_type_from_kingdom(kingdom_name)
    if by_kingdom:
        return by_kingdom
    text = " ".join([description or "", label or "", species_name or ""]).lower()
    if re.search(r"真菌|菌核|菌丝|fungi|mycota|poria|cordyceps", text, flags=re.IGNORECASE):
        return "真菌"
    if re.search(
        r"矿物|无机|硫酸盐|卤化物|硅酸盐|碳酸盐|硝酸盐|石灰性|矿石|石盐|明矾|硇砂|石膏|方解石|滑石|磁铁矿|"
        r"四硼酸钠|碳酸钠|碳酸钙|氯化亚汞|硫化汞|氧化汞|硫酸铁|氧化铁|二氧化碳|硼砂|白矾|火硝|光明盐|大青盐|"
        r"黄丹|铁落|铁屑|炼铁|铜绿|铜器|锈衣|香盐|结晶水|金属|cuprum|calcite|gypsum|nacl|na2|hgs|hgo|hg2cl2|caco3",
        text,
        flags=re.IGNORECASE,
    ):
        return "矿物"
    if re.search(
        r"动物|科动物|昆虫|蜜蜂|蟾蜍|蝎|蛇|蛤蚧|蜗牛|海马|"
        r"贝齿|贝壳|骨壳|干燥粪便|粪|胃|肺|心|胆|血|胎盘|麝香|珍珠|珊瑚|鹿茸|犀角|羚羊角|牛角|羊角|水牛角|山羊角",
        text,
    ):
        return "动物"
    if re.search(r"植物|科植物|杂草|庄稼|秸秆|松烟|胶汁|香料|草本|乔木|灌木|全草|地上部分|干燥根|根茎|枝叶|叶|花|果实|种子|树脂|木材|树皮|孢子", text):
        return "植物"
    return "未定"


def read_restored_material_origins(input_dir: Path, descriptions: dict[str, str]) -> dict[str, list[dict[str, str]]]:
    workbook_path = input_dir / RESTORED_WORKBOOK
    if not workbook_path.exists():
        return {}
    rows = read_xlsx_table(workbook_path, "MMP_restored")
    restored: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        material_id = str(row.get("MMP_ID") or "").strip()
        if not material_id:
            continue
        label = str(row.get("Mongolian_medicinal_pieces") or "").strip()
        kingdoms = split_semicolon(row.get("kingdom_Name"))
        species_names = split_semicolon(row.get("species_name"))
        species_ids = split_semicolon(row.get("species_ID"))
        record_count = max(len(kingdoms), len(species_names), len(species_ids), 1)
        material_records: list[dict[str, str]] = []
        for index in range(record_count):
            kingdom_name = kingdoms[index] if index < len(kingdoms) else (kingdoms[0] if len(kingdoms) == 1 else "")
            species_name = species_names[index] if index < len(species_names) else ""
            species_id = species_ids[index] if index < len(species_ids) else ""
            source_type = infer_source_type(kingdom_name, descriptions.get(material_id, ""), label, species_name)
            material_records.append(
                {
                    "material_id": material_id,
                    "species_id": species_id,
                    "species_name": species_name,
                    "kingdom_name": kingdom_name,
                    "source_type": source_type,
                }
            )
        restored[material_id] = material_records
    return restored


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA foreign_keys = OFF;

        DROP TABLE IF EXISTS metadata;
        DROP TABLE IF EXISTS source_files;
        DROP TABLE IF EXISTS materials;
        DROP TABLE IF EXISTS terminology;
        DROP TABLE IF EXISTS mmp_mmt;
        DROP TABLE IF EXISTS medicinal_properties;
        DROP TABLE IF EXISTS pharmacognostic_origins;
        DROP TABLE IF EXISTS mmp_po;
        DROP TABLE IF EXISTS material_terms;
        DROP TABLE IF EXISTS material_origins;
        DROP TABLE IF EXISTS kg_edges;
        DROP TABLE IF EXISTS entities;
        DROP TABLE IF EXISTS search_documents;
        DROP TABLE IF EXISTS search_documents_fts;

        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE source_files (
            module_code TEXT PRIMARY KEY,
            module_name TEXT NOT NULL,
            filename TEXT NOT NULL,
            row_count INTEGER NOT NULL
        );

        CREATE TABLE materials (
            material_id TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            functions_text TEXT,
            indications_text TEXT,
            flavors_text TEXT,
            natures_text TEXT,
            potencies_text TEXT,
            terms_text TEXT,
            properties_text TEXT,
            families_text TEXT,
            genera_text TEXT,
            species_text TEXT,
            source_type_text TEXT,
            origins_text TEXT,
            search_text TEXT,
            term_count INTEGER NOT NULL DEFAULT 0,
            property_count INTEGER NOT NULL DEFAULT 0,
            species_count INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE terminology (
            mmt_id TEXT PRIMARY KEY,
            chinese_term TEXT NOT NULL,
            term_category TEXT NOT NULL
        );

        CREATE TABLE mmp_mmt (
            id INTEGER PRIMARY KEY,
            material_id TEXT NOT NULL,
            mmt_id TEXT NOT NULL
        );

        CREATE TABLE medicinal_properties (
            id INTEGER PRIMARY KEY,
            material_id TEXT NOT NULL,
            property_label TEXT NOT NULL,
            property_class TEXT NOT NULL
        );

        CREATE TABLE pharmacognostic_origins (
            species_id TEXT PRIMARY KEY,
            species_name TEXT NOT NULL,
            genus_name TEXT,
            genus_id TEXT,
            family_name TEXT,
            family_id TEXT,
            order_name TEXT,
            order_id TEXT,
            class_name TEXT,
            class_id TEXT,
            phylum_name TEXT,
            phylum_id TEXT,
            kingdom_name TEXT,
            kingdom_id TEXT
        );

        CREATE TABLE mmp_po (
            id INTEGER PRIMARY KEY,
            material_id TEXT NOT NULL,
            species_id TEXT NOT NULL
        );

        CREATE TABLE material_terms (
            id INTEGER PRIMARY KEY,
            material_id TEXT NOT NULL,
            relation TEXT NOT NULL,
            term_id TEXT NOT NULL,
            term_type TEXT NOT NULL,
            term_label TEXT NOT NULL,
            source_field TEXT NOT NULL,
            module_code TEXT NOT NULL
        );

        CREATE TABLE material_origins (
            id INTEGER PRIMARY KEY,
            material_id TEXT NOT NULL,
            species_id TEXT,
            species_name TEXT,
            source_type TEXT,
            genus_name TEXT,
            family_name TEXT,
            order_name TEXT,
            class_name TEXT,
            phylum_name TEXT,
            kingdom_name TEXT
        );

        CREATE TABLE kg_edges (
            id INTEGER PRIMARY KEY,
            source_row_id TEXT NOT NULL,
            subject_id TEXT NOT NULL,
            subject_label TEXT NOT NULL,
            subject_type TEXT NOT NULL,
            predicate TEXT NOT NULL,
            object_id TEXT NOT NULL,
            object_label TEXT NOT NULL,
            object_type TEXT NOT NULL,
            module_code TEXT NOT NULL,
            source_field TEXT NOT NULL
        );

        CREATE TABLE entities (
            entity_id TEXT PRIMARY KEY,
            entity_type TEXT NOT NULL,
            label TEXT NOT NULL,
            description TEXT
        );

        CREATE TABLE search_documents (
            id INTEGER PRIMARY KEY,
            doc_type TEXT NOT NULL,
            ref_id TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            tags TEXT
        );

        CREATE INDEX idx_material_terms_material ON material_terms(material_id);
        CREATE INDEX idx_material_terms_relation ON material_terms(relation);
        CREATE INDEX idx_material_origins_material ON material_origins(material_id);
        CREATE INDEX idx_kg_edges_source ON kg_edges(source_row_id);
        CREATE INDEX idx_kg_edges_predicate ON kg_edges(predicate);
        CREATE INDEX idx_search_documents_type ON search_documents(doc_type);
        """
    )
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE search_documents_fts USING fts5(title, body, tags, content='search_documents', content_rowid='id')"
        )
    except sqlite3.OperationalError:
        pass


def build_database(input_dir: Path, output_db: Path) -> None:
    paths = {code: input_dir / filename for code, _, filename in MODULES}
    restored_workbook = input_dir / RESTORED_WORKBOOK
    missing = [str(path) for path in paths.values() if not path.exists()]
    if not restored_workbook.exists():
        missing.append(str(restored_workbook))
    if missing:
        raise FileNotFoundError("Missing curated input files:\n" + "\n".join(missing))

    d1 = read_tsv(paths["D1"])
    d2 = read_tsv(paths["D2"])
    d3 = read_tsv(paths["D3"])
    d4 = read_tsv(paths["D4"])
    d5 = read_tsv(paths["D5"])
    d6 = read_tsv(paths["D6"])
    source_descriptions = load_source_descriptions()
    restored_origins = read_restored_material_origins(input_dir, source_descriptions)

    output_db.parent.mkdir(parents=True, exist_ok=True)
    if output_db.exists():
        output_db.unlink()

    conn = sqlite3.connect(output_db)
    try:
        create_schema(conn)
        source_file_rows = [
            (code, name, filename, len({"D1": d1, "D2": d2, "D3": d3, "D4": d4, "D5": d5, "D6": d6}[code]))
            for code, name, filename in MODULES
        ]
        source_file_rows.append(("RESTORED", "Restored MMP origin table", RESTORED_WORKBOOK, len(restored_origins)))
        conn.executemany(
            "INSERT INTO source_files(module_code, module_name, filename, row_count) VALUES (?, ?, ?, ?)",
            source_file_rows,
        )

        terms = {row["MMT_ID"]: row for row in d1}
        pieces = {row["MMP_ID"]: row for row in d2}
        origins = {row["species_ID"]: row for row in d5}

        conn.executemany(
            "INSERT INTO terminology(mmt_id, chinese_term, term_category) VALUES (?, ?, ?)",
            [(row["MMT_ID"], row["Chinese_term"], row["Term_category"]) for row in d1],
        )
        conn.executemany(
            "INSERT INTO mmp_mmt(material_id, mmt_id) VALUES (?, ?)",
            [(row["MMP_ID"], row["MMT_ID"]) for row in d3],
        )
        conn.executemany(
            "INSERT INTO medicinal_properties(material_id, property_label, property_class) VALUES (?, ?, ?)",
            [(row["MMP_ID"], row["Medicinal_properties"], row["Class"]) for row in d4],
        )
        conn.executemany(
            """
            INSERT INTO pharmacognostic_origins(
                species_id, species_name, genus_name, genus_id, family_name, family_id,
                order_name, order_id, class_name, class_id, phylum_name, phylum_id,
                kingdom_name, kingdom_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["species_ID"],
                    row["species_name"],
                    row["genus_Name"],
                    row["genus_ID"],
                    row["family_Name"],
                    row["family_ID"],
                    row["order_Name"],
                    row["order_ID"],
                    row["class_Name"],
                    row["class_ID"],
                    row["phylum_Name"],
                    row["phylum_ID"],
                    row["kingdom_Name"],
                    row["kingdom_ID"],
                )
                for row in d5
            ],
        )
        conn.executemany(
            "INSERT INTO mmp_po(material_id, species_id) VALUES (?, ?)",
            [(row["MMP_ID"], row["species_ID"]) for row in d6],
        )

        relation_terms: list[tuple[str, str, str, str, str, str, str]] = []
        edges: list[tuple[str, str, str, str, str, str, str, str, str, str]] = []
        entities: dict[str, tuple[str, str, str]] = {}

        for row in d2:
            material_id = row["MMP_ID"]
            label = row["Mongolian_medicinal_pieces"]
            entities[f"MongolianMedicinalPiece:{material_id}"] = (
                "MongolianMedicinalPiece",
                label,
                "D2 Mongolian medicinal pieces",
            )

        for row in d1:
            for category in split_term_categories(row["Term_category"]):
                mapped = TERM_CATEGORY_MAP.get(category)
                if not mapped:
                    continue
                _, term_type, label_cn = mapped
                entities[f"{term_type}:{row['MMT_ID']}"] = (
                    term_type,
                    row["Chinese_term"],
                    f"D1 {label_cn}术语；MMT_ID={row['MMT_ID']}",
                )

        for row in d3:
            term = terms.get(row["MMT_ID"])
            piece = pieces.get(row["MMP_ID"])
            if not term or not piece:
                continue
            for category in split_term_categories(term["Term_category"]):
                mapped = TERM_CATEGORY_MAP.get(category)
                if not mapped:
                    continue
                relation, term_type, label_cn = mapped
                term_id = f"{term_type}:{term['MMT_ID']}"
                relation_terms.append(
                    (
                        row["MMP_ID"],
                        relation,
                        term_id,
                        term_type,
                        term["Chinese_term"],
                        f"D1 {label_cn}术语 / D3 MMP-MMT",
                        "D3",
                    )
                )
                edges.append(
                    (
                        row["MMP_ID"],
                        f"MongolianMedicinalPiece:{row['MMP_ID']}",
                        piece["Mongolian_medicinal_pieces"],
                        "MongolianMedicinalPiece",
                        relation,
                        term_id,
                        term["Chinese_term"],
                        term_type,
                        "D3",
                        f"D1 {label_cn}术语 / D3 MMP-MMT",
                    )
                )

        for row in d4:
            piece = pieces.get(row["MMP_ID"])
            mapped = PROPERTY_CLASS_MAP.get(row["Class"])
            if not piece or not mapped:
                continue
            relation, term_type, label_cn = mapped
            term_id = f"{term_type}:{row['Medicinal_properties']}"
            entities[term_id] = (
                term_type,
                row["Medicinal_properties"],
                f"D4 {label_cn}；Class={row['Class']}",
            )
            relation_terms.append(
                (
                    row["MMP_ID"],
                    relation,
                    term_id,
                    term_type,
                    row["Medicinal_properties"],
                    f"D4 {label_cn}",
                    "D4",
                )
            )
            edges.append(
                (
                    row["MMP_ID"],
                    f"MongolianMedicinalPiece:{row['MMP_ID']}",
                    piece["Mongolian_medicinal_pieces"],
                    "MongolianMedicinalPiece",
                    relation,
                    term_id,
                    row["Medicinal_properties"],
                    term_type,
                    "D4",
                    f"D4 {label_cn}",
                )
            )

        material_origins: list[tuple[str, str, str, str, str, str, str, str, str, str]] = []
        for material_id, piece in sorted(pieces.items()):
            origin_records = restored_origins.get(material_id)
            if not origin_records:
                origin_records = [
                    {
                        "material_id": material_id,
                        "species_id": "",
                        "species_name": "",
                        "kingdom_name": "",
                        "source_type": infer_source_type(
                            "",
                            source_descriptions.get(material_id, ""),
                            piece["Mongolian_medicinal_pieces"],
                        ),
                    }
                ]
            for index, origin in enumerate(origin_records, start=1):
                species_id_value = origin.get("species_id", "")
                species_name = origin.get("species_name", "")
                kingdom_name = origin.get("kingdom_name", "")
                source_type = origin.get("source_type", "") or infer_source_type(
                    kingdom_name,
                    source_descriptions.get(material_id, ""),
                    piece["Mongolian_medicinal_pieces"],
                    species_name,
                )
                material_origins.append(
                    (
                        material_id,
                        species_id_value,
                        species_name,
                        source_type,
                        "",
                        "",
                        "",
                        "",
                        "",
                        kingdom_name,
                    )
                )
                if not (species_id_value or species_name):
                    continue
                entity_id = f"Species:{species_id_value or f'{material_id}:{index}'}"
                entity_label = species_name or species_id_value
                entities[entity_id] = (
                    "Species",
                    entity_label,
                    compact(
                        [
                            f"{RESTORED_WORKBOOK}",
                            f"kingdom_Name={kingdom_name}" if kingdom_name else "",
                            f"species_ID={species_id_value}" if species_id_value else "",
                            f"source_type={source_type}" if source_type else "",
                        ],
                        "；",
                    ),
                )
                edges.append(
                    (
                        material_id,
                        f"MongolianMedicinalPiece:{material_id}",
                        piece["Mongolian_medicinal_pieces"],
                        "MongolianMedicinalPiece",
                        "HAS_PHARMACOGNOSTIC_ORIGIN",
                        entity_id,
                        entity_label,
                        "Species",
                        "RESTORED",
                        f"{RESTORED_WORKBOOK} kingdom_Name/species_name/species_ID",
                    )
                )

        conn.executemany(
            """
            INSERT INTO material_terms(material_id, relation, term_id, term_type, term_label, source_field, module_code)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            relation_terms,
        )
        conn.executemany(
            """
            INSERT INTO material_origins(
                material_id, species_id, species_name, source_type, genus_name, family_name,
                order_name, class_name, phylum_name, kingdom_name
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            material_origins,
        )
        conn.executemany(
            """
            INSERT INTO kg_edges(
                source_row_id, subject_id, subject_label, subject_type, predicate,
                object_id, object_label, object_type, module_code, source_field
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            edges,
        )
        conn.executemany(
            "INSERT INTO entities(entity_id, entity_type, label, description) VALUES (?, ?, ?, ?)",
            [(entity_id, *payload) for entity_id, payload in sorted(entities.items())],
        )

        grouped_terms: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        for material_id, relation, _, _, term_label, _, _ in relation_terms:
            grouped_terms[material_id][relation].append(term_label)

        grouped_origins: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        for (
            material_id,
            species_id_value,
            species_name,
            source_type,
            genus_name,
            family_name,
            order_name,
            class_name,
            phylum_name,
            kingdom_name,
        ) in material_origins:
            grouped_origins[material_id]["species_id"].append(species_id_value)
            grouped_origins[material_id]["species"].append(species_name)
            grouped_origins[material_id]["source_type"].append(source_type)
            grouped_origins[material_id]["genus"].append(genus_name)
            grouped_origins[material_id]["family"].append(family_name)
            grouped_origins[material_id]["order"].append(order_name)
            grouped_origins[material_id]["class"].append(class_name)
            grouped_origins[material_id]["phylum"].append(phylum_name)
            grouped_origins[material_id]["kingdom"].append(kingdom_name)

        material_rows: list[tuple[object, ...]] = []
        for material_id, piece in sorted(pieces.items()):
            terms_by_relation = grouped_terms[material_id]
            origins_by_level = grouped_origins[material_id]
            functions = compact(terms_by_relation["HAS_FUNCTION"])
            indications = compact(terms_by_relation["TREATS_INDICATION"])
            flavors = compact(terms_by_relation["HAS_TASTE"])
            natures = compact(terms_by_relation["HAS_NATURE"])
            potencies = compact(terms_by_relation["HAS_POTENCY"])
            families = compact(origins_by_level["family"])
            genera = compact(origins_by_level["genus"])
            species = compact(origins_by_level["species"])
            species_ids = compact(origins_by_level["species_id"])
            kingdoms = compact(origins_by_level["kingdom"])
            source_types = compact(origins_by_level["source_type"], "、")
            species_pairs = {
                (species_name, species_id_value)
                for species_name, species_id_value in zip(
                    origins_by_level["species"],
                    origins_by_level["species_id"],
                )
                if species_name or species_id_value
            }
            terms_text = compact([functions, indications])
            properties_text = compact([flavors, natures, potencies])
            origins_text = compact([kingdoms, species, species_ids])
            search_text = compact(
                [
                    piece["Mongolian_medicinal_pieces"],
                    material_id,
                    terms_text,
                    properties_text,
                    source_types,
                    origins_text,
                ],
                " ",
            )
            material_rows.append(
                (
                    material_id,
                    piece["Mongolian_medicinal_pieces"],
                    functions,
                    indications,
                    flavors,
                    natures,
                    potencies,
                    terms_text,
                    properties_text,
                    families,
                    genera,
                    species,
                    source_types,
                    origins_text,
                    search_text,
                    len(set(terms_by_relation["HAS_FUNCTION"] + terms_by_relation["TREATS_INDICATION"])),
                    len(
                        set(
                            terms_by_relation["HAS_TASTE"]
                            + terms_by_relation["HAS_NATURE"]
                            + terms_by_relation["HAS_POTENCY"]
                        )
                    ),
                    len(species_pairs),
                )
            )

        conn.executemany(
            """
            INSERT INTO materials(
                material_id, label, functions_text, indications_text, flavors_text, natures_text,
                potencies_text, terms_text, properties_text, families_text, genera_text,
                species_text, source_type_text, origins_text, search_text, term_count, property_count, species_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            material_rows,
        )

        search_docs: list[tuple[str, str, str, str, str]] = []
        for row in material_rows:
            material_id, label = str(row[0]), str(row[1])
            search_docs.append(
                (
                    "material",
                    material_id,
                    label,
                    str(row[14] or ""),
                    compact(["Mongolian medicinal pieces", str(row[12] or ""), str(row[11] or "")], "；"),
                )
            )
        for row in d1:
            search_docs.append(
                (
                    "terminology",
                    row["MMT_ID"],
                    row["Chinese_term"],
                    f"{row['Chinese_term']} {row['Term_category']}",
                    row["Term_category"],
                )
            )
        seen_origin_docs: set[str] = set()
        for (
            material_id,
            species_id_value,
            species_name,
            source_type,
            _genus_name,
            _family_name,
            _order_name,
            _class_name,
            _phylum_name,
            kingdom_name,
        ) in material_origins:
            ref_id = species_id_value or f"{material_id}:origin"
            if ref_id in seen_origin_docs:
                continue
            seen_origin_docs.add(ref_id)
            title = species_name or compact([source_type, kingdom_name]) or "未记录基源"
            search_docs.append(
                (
                    "origin",
                    ref_id,
                    title,
                    compact(
                        [
                            species_name,
                            species_id_value,
                            kingdom_name,
                            source_type,
                        ],
                        " ",
                    ),
                    compact([source_type, kingdom_name, "Restored pharmacognostic origin"], "；"),
                )
            )
        conn.executemany(
            "INSERT INTO search_documents(doc_type, ref_id, title, body, tags) VALUES (?, ?, ?, ?, ?)",
            search_docs,
        )
        try:
            conn.execute(
                """
                INSERT INTO search_documents_fts(rowid, title, body, tags)
                SELECT id, title, body, tags FROM search_documents
                """
            )
        except sqlite3.OperationalError:
            pass

        origin_taxon_ids = {row[1] for row in material_origins if row[1]}
        mapped_origin_rows = [row for row in material_origins if row[1] or row[2] or row[9]]
        metadata = {
            "dataset_id": input_dir.name,
            "material_count": str(len(d2)),
            "terminology_count": str(len(d1)),
            "mmp_mmt_count": str(len(d3)),
            "medicinal_property_count": str(len(d4)),
            "origin_taxon_count": str(len(origin_taxon_ids)),
            "mmp_po_count": str(len(mapped_origin_rows)),
            "entity_count": str(len(entities)),
            "edge_count": str(len(edges)),
            "fts_tokenizer": "unicode61" if has_fts(conn) else "unavailable",
        }
        conn.executemany("INSERT INTO metadata(key, value) VALUES (?, ?)", sorted(metadata.items()))
        conn.commit()
    finally:
        conn.close()


def has_fts(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='search_documents_fts'"
    ).fetchone()
    return row is not None


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the M3KG SQLite database from curated D1-D6 TSV files.")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-db", type=Path, default=DEFAULT_OUTPUT_DB)
    args = parser.parse_args()
    build_database(args.input_dir, args.output_db)
    print(f"Built {args.output_db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
