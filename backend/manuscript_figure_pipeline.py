from __future__ import annotations

import argparse
import collections
import csv
import dataclasses
import importlib.util
import json
import math
import pickle
import platform
import random
import shutil
import sqlite3
import sys
import textwrap
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import matplotlib
    import matplotlib.pyplot as plt
    from matplotlib import gridspec
    from matplotlib.colors import LinearSegmentedColormap
    from matplotlib.patches import Circle, Ellipse, FancyArrowPatch, FancyBboxPatch, Rectangle
except ImportError:  # The lightweight audit mode works in the bundled PDF runtime.
    matplotlib = None
    plt = None
    gridspec = None
    LinearSegmentedColormap = None
    Circle = Ellipse = FancyArrowPatch = FancyBboxPatch = Rectangle = None


ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "curated_tsv_dataset_20260623"
DB_PATH = ROOT / "data" / "m3kg_curated_20260623.sqlite"
OUTPUT_ROOT = ROOT / "output" / "manuscript_figures"
FIGURE_DIR = OUTPUT_ROOT / "figures"
FIGURE_DATA_DIR = OUTPUT_ROOT / "source_data"
ASSET_DIR = OUTPUT_ROOT / "assets"
SNAPSHOT_DIR = OUTPUT_ROOT / "source_snapshot"
ANALYSIS_CACHE = OUTPUT_ROOT / "analysis_cache.pkl"

RANDOM_SEED = 20260623
N_MATERIALS = 558

COLORS = {
    # Reference-derived editorial palette: navy and indigo carry the main
    # structure; cyan, magenta and coral are reserved for sparse emphasis.
    "green": "#263963",
    "green_light": "#E5E9F1",
    "blue": "#384F8E",
    "blue_light": "#E6EAF3",
    "orange": "#53ABBC",
    "orange_light": "#E3F1F4",
    "purple": "#675A8E",
    "purple_light": "#EAE8F0",
    "magenta": "#913176",
    "magenta_light": "#F1E4ED",
    "yellow": "#AF7AA2",
    "gray": "#737A86",
    "gray_light": "#ECEDEF",
    "ink": "#292B30",
    "grid": "#D9DBDF",
    "red": "#D68779",
    "red_light": "#F5E6E2",
}

SEQUENTIAL_COLORS = ["#FAFAFA", "#E8EFF5", "#B8D5E3", "#72B1CC", "#2C4C79", "#1F244C"]
DIVERGING_COLORS = ["#913176", "#C497BA", "#F8F7F8", "#B7CDDF", "#263963"]

SOURCE_COLORS = {
    "植物": COLORS["green"],
    "动物": COLORS["blue"],
    "矿物": COLORS["orange"],
    "真菌": COLORS["purple"],
}

SOURCE_ENGLISH = {"植物": "Plant", "动物": "Animal", "矿物": "Mineral", "真菌": "Fungus"}

TASTE_CANONICAL = {
    "苦": "Bitter",
    "微苦": "Bitter",
    "甘": "Sweet",
    "微甘": "Sweet",
    "辛": "Pungent",
    "微辛": "Pungent",
    "涩": "Astringent",
    "咸": "Salty",
    "微咸": "Salty",
    "酸": "Sour",
    "微酸": "Sour",
    "淡": "Bland",
}

NATURE_CANONICAL = {
    "寒": "Cold",
    "微寒": "Cold",
    "凉": "Cool",
    "平": "Neutral",
    "温": "Warm",
    "微温": "Warm",
    "热": "Hot",
}

POTENCY_ENGLISH = {
    "轻": "Light",
    "糙": "Rough",
    "钝": "Dull",
    "燥": "Dry",
    "柔": "Soft-flexible",
    "腻": "Oily",
    "重": "Heavy",
    "稀": "Thin",
    "锐": "Sharp",
    "软": "Soft",
    "淡": "Bland",
    "浮": "Floating",
    "动": "Mobile",
    "固": "Stable",
    "涩": "Astringent",
    "和": "Harmonious",
    "润": "Moistening",
    "粘": "Viscous",
}

TERM_ENGLISH = {
    "清热": "Heat-clearing",
    "解毒": "Detoxifying",
    "消肿": "Reducing swelling",
    "愈伤": "Wound healing",
    "止痛": "Analgesia",
    "消食": "Promoting digestion",
    "止血": "Hemostasis",
    "止泻": "Antidiarrheal",
    "杀虫": "Antiparasitic",
    "温胃": "Warming the stomach",
    "滋补": "Tonic action",
    "利尿": "Diuresis",
    "开胃": "Improving appetite",
    "止咳": "Antitussive",
    "祛痰": "Expectorant",
    "活血": "Promoting circulation",
    "强壮": "Strengthening",
    "消化不良": "Indigestion",
    "毒热": "Toxic-heat syndrome",
    "水肿": "Edema",
    "肺脓肿": "Lung abscess",
    "肝热": "Liver-heat syndrome",
    "黄疸": "Jaundice",
    "疮疡": "Sores and ulcers",
    "皮肤瘙痒": "Pruritus",
    "肺热": "Lung-heat syndrome",
    "阳痿": "Erectile dysfunction",
    "腮腺炎": "Parotitis",
    "结膜炎": "Conjunctivitis",
    "乳腺炎": "Mastitis",
    "肺炎": "Pneumonia",
    "支气管炎": "Bronchitis",
    "咽炎": "Pharyngitis",
    "胃热": "Stomach heat",
    "腹胀": "Abdominal distension",
    "胃寒": "Stomach cold",
    "牙痛": "Toothache",
    "烧伤": "Burn injury",
    "扁桃体炎": "Tonsillitis",
    "鼻炎": "Rhinitis",
}

PREDICATE_LABELS = {
    "HAS_TASTE": "Taste",
    "HAS_NATURE": "Nature",
    "HAS_POTENCY": "Potency",
    "HAS_FUNCTION": "Function",
    "TREATS_INDICATION": "Indication",
    "HAS_PHARMACOGNOSTIC_ORIGIN": "Origin",
}


def audit_environment() -> dict[str, object]:
    packages = [
        "numpy",
        "pandas",
        "matplotlib",
        "seaborn",
        "scipy",
        "sklearn",
        "networkx",
        "umap",
        "mlxtend",
        "torch",
        "pykeen",
        "reportlab",
        "pypdf",
        "pdfplumber",
    ]
    available = {name: importlib.util.find_spec(name) is not None for name in packages}

    with sqlite3.connect(DB_PATH) as conn:
        tables = {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT name, sql FROM sqlite_master WHERE type = 'table' ORDER BY name"
            )
        }
        counts = {
            table: conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in tables
            if not table.startswith("search_documents_fts")
        }

    return {
        "python": sys.version,
        "platform": platform.platform(),
        "packages": available,
        "database": str(DB_PATH),
        "tables": counts,
        "schemas": tables,
        "dataset_files": sorted(path.name for path in DATASET_DIR.glob("*")),
    }


def profile_data() -> dict[str, object]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row

        def rows(sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
            return [dict(row) for row in conn.execute(sql, params)]

        property_counts = rows(
            """
            SELECT property_class, property_label, COUNT(DISTINCT material_id) AS material_count
            FROM medicinal_properties
            GROUP BY property_class, property_label
            ORDER BY property_class, material_count DESC, property_label
            """
        )
        relation_counts = rows(
            """
            SELECT predicate, COUNT(*) AS edge_count, COUNT(DISTINCT subject_id) AS material_count,
                   COUNT(DISTINCT object_id) AS object_count
            FROM kg_edges
            GROUP BY predicate
            ORDER BY edge_count DESC
            """
        )
        source_counts = rows(
            """
            SELECT source_type, COUNT(DISTINCT material_id) AS material_count
            FROM material_origins
            GROUP BY source_type
            ORDER BY material_count DESC
            """
        )
        kingdom_counts = rows(
            """
            SELECT p.kingdom_name, COUNT(DISTINCT m.material_id) AS material_count,
                   COUNT(DISTINCT m.species_id) AS species_count
            FROM mmp_po AS m
            JOIN pharmacognostic_origins AS p ON p.species_id = m.species_id
            GROUP BY p.kingdom_name
            ORDER BY material_count DESC
            """
        )
        top_families = rows(
            """
            SELECT p.family_name, COUNT(DISTINCT m.material_id) AS material_count,
                   COUNT(DISTINCT m.species_id) AS species_count
            FROM mmp_po AS m
            JOIN pharmacognostic_origins AS p ON p.species_id = m.species_id
            GROUP BY p.family_name
            ORDER BY material_count DESC, p.family_name
            LIMIT 15
            """
        )
        top_genera = rows(
            """
            SELECT p.genus_name, COUNT(DISTINCT m.material_id) AS material_count,
                   COUNT(DISTINCT m.species_id) AS species_count
            FROM mmp_po AS m
            JOIN pharmacognostic_origins AS p ON p.species_id = m.species_id
            GROUP BY p.genus_name
            ORDER BY material_count DESC, p.genus_name
            LIMIT 15
            """
        )
        multi_origin = rows(
            """
            SELECT m.material_id, m.label, COUNT(DISTINCT o.species_id) AS species_count,
                   GROUP_CONCAT(DISTINCT o.species_name) AS species_names
            FROM materials AS m
            JOIN material_origins AS o ON o.material_id = m.material_id
            WHERE COALESCE(o.species_id, '') <> ''
            GROUP BY m.material_id, m.label
            HAVING COUNT(DISTINCT o.species_id) > 1
            ORDER BY species_count DESC, m.material_id
            """
        )
        named_examples = rows(
            """
            SELECT m.material_id, m.label, COUNT(DISTINCT o.species_id) AS species_count,
                   GROUP_CONCAT(DISTINCT o.species_name) AS species_names
            FROM materials AS m
            LEFT JOIN material_origins AS o ON o.material_id = m.material_id
            WHERE m.label IN ('川贝母', '海马', '石决明', '钩藤')
            GROUP BY m.material_id, m.label
            ORDER BY m.label
            """
        )
        missing_nature = rows(
            """
            SELECT material_id, label FROM materials
            WHERE material_id NOT IN (
                SELECT DISTINCT material_id FROM medicinal_properties
                WHERE property_class = 'Medicinal nature'
            )
            ORDER BY material_id
            """
        )
        without_species = rows(
            """
            SELECT material_id, label, source_type_text
            FROM materials
            WHERE material_id NOT IN (
                SELECT DISTINCT material_id FROM material_origins
                WHERE COALESCE(species_id, '') <> ''
            )
            ORDER BY material_id
            """
        )
        suspicious_labels = rows(
            """
            SELECT material_id, label, source_type_text, species_text
            FROM materials
            WHERE label IN ('紫丁香', '苏木', '尖叶假龙胆')
            ORDER BY material_id
            """
        )
        top_terms = rows(
            """
            SELECT relation, term_label, COUNT(DISTINCT material_id) AS material_count
            FROM material_terms
            WHERE relation IN ('HAS_FUNCTION', 'TREATS_INDICATION')
            GROUP BY relation, term_label
            ORDER BY relation, material_count DESC, term_label
            """
        )
        selected_terms = rows(
            """
            SELECT relation, term_label, COUNT(DISTINCT material_id) AS material_count
            FROM material_terms
            WHERE relation IN ('HAS_FUNCTION', 'TREATS_INDICATION')
              AND (
                term_label LIKE '%清热%' OR term_label LIKE '%解毒%'
                OR term_label LIKE '%温胃%' OR term_label LIKE '%消食%'
                OR term_label LIKE '%消化不良%' OR term_label LIKE '%炎%'
              )
            GROUP BY relation, term_label
            ORDER BY relation, material_count DESC, term_label
            """
        )

    prop_by_class: dict[str, list[dict[str, object]]] = collections.defaultdict(list)
    for row in property_counts:
        prop_by_class[str(row["property_class"])].append(row)

    return {
        "relations": relation_counts,
        "properties": dict(prop_by_class),
        "source_types": source_counts,
        "kingdoms": kingdom_counts,
        "top_families": top_families,
        "top_genera": top_genera,
        "multi_origin_count": len(multi_origin),
        "multi_origin_top": multi_origin[:30],
        "requested_multi_origin_examples": named_examples,
        "missing_nature": missing_nature,
        "materials_without_species_id_count": len(without_species),
        "materials_without_species_id_preview": without_species[:20],
        "suspicious_source_labels": suspicious_labels,
        "top_functions": [row for row in top_terms if row["relation"] == "HAS_FUNCTION"][:30],
        "top_indications": [row for row in top_terms if row["relation"] == "TREATS_INDICATION"][:30],
        "selected_rule_terms": selected_terms,
    }


def configure_matplotlib() -> None:
    if matplotlib is None:
        raise RuntimeError(
            "Matplotlib is required for figure generation. Run this script with D:\\Program Files\\Python311\\python.exe."
        )
    matplotlib.use("Agg")
    matplotlib.rcParams.update(
        {
            "font.family": "Arial",
            "font.size": 6,
            "axes.titlesize": 7,
            "axes.labelsize": 6,
            "xtick.labelsize": 5.5,
            "ytick.labelsize": 5.5,
            "legend.fontsize": 5.3,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
            "axes.linewidth": 0.55,
            "xtick.major.width": 0.5,
            "ytick.major.width": 0.5,
            "xtick.major.size": 2.5,
            "ytick.major.size": 2.5,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "text.color": COLORS["ink"],
            "axes.labelcolor": COLORS["ink"],
            "axes.edgecolor": COLORS["ink"],
            "xtick.color": COLORS["ink"],
            "ytick.color": COLORS["ink"],
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
        }
    )


def ensure_output_dirs() -> None:
    for path in (FIGURE_DIR, FIGURE_DATA_DIR, ASSET_DIR, SNAPSHOT_DIR):
        path.mkdir(parents=True, exist_ok=True)


def load_data() -> dict[str, pd.DataFrame]:
    queries = {
        "materials": "SELECT * FROM materials ORDER BY material_id",
        "terminology": "SELECT * FROM terminology ORDER BY mmt_id",
        "mmp_mmt": "SELECT * FROM mmp_mmt ORDER BY material_id, mmt_id",
        "properties": "SELECT * FROM medicinal_properties ORDER BY material_id, property_class, property_label",
        "taxonomy": "SELECT * FROM pharmacognostic_origins ORDER BY species_id",
        "mmp_po": "SELECT * FROM mmp_po ORDER BY material_id, species_id",
        "material_terms": "SELECT * FROM material_terms ORDER BY material_id, relation, term_id",
        "material_origins": "SELECT * FROM material_origins ORDER BY material_id, species_id",
        "kg_edges": "SELECT * FROM kg_edges ORDER BY id",
        "entities": "SELECT * FROM entities ORDER BY entity_id",
        "source_files": "SELECT * FROM source_files ORDER BY module_code",
    }
    with sqlite3.connect(DB_PATH) as conn:
        return {name: pd.read_sql_query(sql, conn) for name, sql in queries.items()}


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def copy_source_snapshot() -> None:
    for path in sorted(DATASET_DIR.glob("D*.tsv")):
        shutil.copy2(path, SNAPSHOT_DIR / path.name)
    restored = DATASET_DIR / "Mongolian_medicinal_pieces_restored_table.xlsx"
    if restored.exists():
        shutil.copy2(restored, SNAPSHOT_DIR / restored.name)


def clean_axis(ax: object, grid: str | None = None) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if grid == "x":
        ax.grid(axis="x", color=COLORS["grid"], linewidth=0.45, alpha=0.7, zorder=0)
    elif grid == "y":
        ax.grid(axis="y", color=COLORS["grid"], linewidth=0.45, alpha=0.7, zorder=0)


def panel_label(ax: object, label: str, x: float = -0.08, y: float = 1.04) -> None:
    ax.text(x, y, label, transform=ax.transAxes, fontsize=8, fontweight="bold", va="bottom", ha="left")


def panel_title(ax: object, title: str) -> None:
    ax.set_title(title, loc="left", pad=3, fontweight="bold", color=COLORS["ink"])


def add_box(
    ax: object,
    xy: tuple[float, float],
    width: float,
    height: float,
    text: str,
    facecolor: str = "white",
    edgecolor: str = COLORS["grid"],
    textcolor: str = COLORS["ink"],
    fontsize: float = 5.5,
    weight: str = "normal",
    radius: float = 0.03,
) -> FancyBboxPatch:
    x, y = xy
    patch = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle=f"round,pad=0.008,rounding_size={radius}",
        transform=ax.transAxes,
        linewidth=0.65,
        facecolor=facecolor,
        edgecolor=edgecolor,
        clip_on=False,
    )
    ax.add_patch(patch)
    ax.text(
        x + width / 2,
        y + height / 2,
        text,
        transform=ax.transAxes,
        ha="center",
        va="center",
        fontsize=fontsize,
        color=textcolor,
        fontweight=weight,
        linespacing=1.15,
    )
    return patch


def add_arrow(
    ax: object,
    start: tuple[float, float],
    end: tuple[float, float],
    color: str = COLORS["gray"],
    width: float = 0.8,
    connectionstyle: str = "arc3,rad=0",
    dashed: bool = False,
) -> None:
    arrow = FancyArrowPatch(
        start,
        end,
        transform=ax.transAxes,
        arrowstyle="-|>",
        mutation_scale=6,
        linewidth=width,
        linestyle="--" if dashed else "-",
        color=color,
        connectionstyle=connectionstyle,
        clip_on=False,
    )
    ax.add_patch(arrow)


def save_figure(fig: object, number: int, slug: str) -> dict[str, str]:
    stem = f"Figure_{number}_{slug}"
    outputs = {
        "pdf": str(FIGURE_DIR / f"{stem}.pdf"),
        "svg": str(FIGURE_DIR / f"{stem}.svg"),
        "png": str(FIGURE_DIR / f"{stem}.png"),
    }
    fig.savefig(outputs["pdf"], bbox_inches="tight", pad_inches=0.02)
    fig.savefig(outputs["svg"], bbox_inches="tight", pad_inches=0.02)
    fig.savefig(outputs["png"], dpi=300, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    return outputs


def log_comb(n: int, k: int) -> float:
    if k < 0 or k > n:
        return float("-inf")
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def logsumexp(values: list[float]) -> float:
    if not values:
        return float("-inf")
    maximum = max(values)
    return maximum + math.log(sum(math.exp(value - maximum) for value in values))


def fisher_enrichment_p(n_total: int, n_a: int, n_b: int, n_ab: int) -> float:
    upper = min(n_a, n_b)
    lower = max(0, n_a - (n_total - n_b))
    if n_ab < lower or n_ab > upper:
        return 1.0
    denominator = log_comb(n_total, n_a)
    log_probabilities = [
        log_comb(n_b, value) + log_comb(n_total - n_b, n_a - value) - denominator
        for value in range(n_ab, upper + 1)
    ]
    return min(1.0, math.exp(logsumexp(log_probabilities)))


def benjamini_hochberg(p_values: np.ndarray) -> np.ndarray:
    p_values = np.asarray(p_values, dtype=float)
    order = np.argsort(p_values)
    ranked = p_values[order]
    adjusted = ranked * len(ranked) / np.arange(1, len(ranked) + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    output = np.empty_like(adjusted)
    output[order] = np.minimum(adjusted, 1.0)
    return output


def rule_label(antecedent: str, consequent: str) -> str:
    parts = []
    for item in antecedent.split(" + "):
        if item.startswith("Taste:"):
            parts.append(TASTE_CANONICAL.get(item.split(":", 1)[1], item.split(":", 1)[1]))
        elif item.startswith("Nature:"):
            parts.append(NATURE_CANONICAL.get(item.split(":", 1)[1], item.split(":", 1)[1]))
        else:
            parts.append(item)
    return " + ".join(parts) + " -> " + TERM_ENGLISH.get(consequent, consequent)


def build_transactions(data: dict[str, pd.DataFrame]) -> dict[str, object]:
    materials = data["materials"][["material_id", "label", "source_type_text"]].copy()
    material_ids = materials["material_id"].tolist()
    index = {material_id: position for position, material_id in enumerate(material_ids)}

    properties = data["properties"].copy()
    tastes: dict[str, set[str]] = collections.defaultdict(set)
    natures: dict[str, set[str]] = collections.defaultdict(set)
    potencies: dict[str, set[str]] = collections.defaultdict(set)
    for row in properties.itertuples(index=False):
        if row.property_class == "Medicinal flavor" and row.property_label in TASTE_CANONICAL:
            tastes[row.material_id].add(row.property_label)
        elif row.property_class == "Medicinal nature" and row.property_label in NATURE_CANONICAL:
            natures[row.material_id].add(row.property_label)
        elif row.property_class == "Medicinal potency feature":
            potencies[row.material_id].add(row.property_label)

    functions: dict[str, set[str]] = collections.defaultdict(set)
    indications: dict[str, set[str]] = collections.defaultdict(set)
    term_ids_by_label: dict[tuple[str, str], str] = {}
    for row in data["material_terms"].itertuples(index=False):
        if row.relation == "HAS_FUNCTION":
            functions[row.material_id].add(row.term_label)
            term_ids_by_label[(row.relation, row.term_label)] = row.term_id
        elif row.relation == "TREATS_INDICATION":
            indications[row.material_id].add(row.term_label)
            term_ids_by_label[(row.relation, row.term_label)] = row.term_id

    return {
        "materials": materials,
        "material_ids": material_ids,
        "index": index,
        "tastes": tastes,
        "natures": natures,
        "potencies": potencies,
        "functions": functions,
        "indications": indications,
        "term_ids_by_label": term_ids_by_label,
    }


def mine_association_rules(transactions: dict[str, object]) -> pd.DataFrame:
    material_ids: list[str] = transactions["material_ids"]
    n_total = len(material_ids)
    antecedent_sets: dict[str, set[str]] = {}

    taste_labels = sorted({label for values in transactions["tastes"].values() for label in values})
    nature_labels = sorted({label for values in transactions["natures"].values() for label in values})
    for label in taste_labels:
        antecedent_sets[f"Taste:{label}"] = {m for m in material_ids if label in transactions["tastes"].get(m, set())}
    for label in nature_labels:
        antecedent_sets[f"Nature:{label}"] = {m for m in material_ids if label in transactions["natures"].get(m, set())}
    for taste in taste_labels:
        for nature in nature_labels:
            members = {
                m
                for m in material_ids
                if taste in transactions["tastes"].get(m, set()) and nature in transactions["natures"].get(m, set())
            }
            if len(members) >= 5:
                antecedent_sets[f"Taste:{taste} + Nature:{nature}"] = members

    outcomes: list[tuple[str, str, set[str]]] = []
    for relation, key in (("HAS_FUNCTION", "functions"), ("TREATS_INDICATION", "indications")):
        labels = sorted({label for values in transactions[key].values() for label in values})
        for label in labels:
            members = {m for m in material_ids if label in transactions[key].get(m, set())}
            outcomes.append((relation, label, members))

    records: list[dict[str, object]] = []
    for antecedent, a_members in antecedent_sets.items():
        n_a = len(a_members)
        for relation, consequent, b_members in outcomes:
            n_b = len(b_members)
            n_ab = len(a_members & b_members)
            if n_ab < 5:
                continue
            support = n_ab / n_total
            confidence = n_ab / n_a
            prevalence = n_b / n_total
            lift = confidence / prevalence if prevalence else float("nan")
            p_value = fisher_enrichment_p(n_total, n_a, n_b, n_ab)
            se_log_lift = math.sqrt(max(0.0, 1 / n_ab - 1 / n_a + 1 / n_b - 1 / n_total))
            ci_low = math.exp(math.log(lift) - 1.96 * se_log_lift)
            ci_high = math.exp(math.log(lift) + 1.96 * se_log_lift)
            records.append(
                {
                    "antecedent": antecedent,
                    "consequent": consequent,
                    "consequent_relation": relation,
                    "n_total": n_total,
                    "antecedent_count": n_a,
                    "consequent_count": n_b,
                    "joint_count": n_ab,
                    "support": support,
                    "confidence": confidence,
                    "lift": lift,
                    "lift_ci_low": ci_low,
                    "lift_ci_high": ci_high,
                    "p_value": p_value,
                }
            )
    rules = pd.DataFrame.from_records(records)
    if rules.empty:
        return rules
    rules["q_value"] = benjamini_hochberg(rules["p_value"].to_numpy())
    rules["rule_label_en"] = [
        rule_label(antecedent, consequent)
        for antecedent, consequent in zip(rules["antecedent"], rules["consequent"])
    ]
    rules = rules.sort_values(["q_value", "lift", "support"], ascending=[True, False, False]).reset_index(drop=True)
    return rules


def permutation_stability(
    transactions: dict[str, object],
    rules: pd.DataFrame,
    selections: list[tuple[str, str, str]],
    n_permutations: int = 1000,
) -> pd.DataFrame:
    rng = np.random.default_rng(RANDOM_SEED)
    material_ids: list[str] = transactions["material_ids"]
    output: list[dict[str, object]] = []
    for antecedent, consequent, relation in selections:
        match = rules[
            (rules["antecedent"] == antecedent)
            & (rules["consequent"] == consequent)
            & (rules["consequent_relation"] == relation)
        ]
        if match.empty:
            continue
        observed = float(match.iloc[0]["lift"])
        a = np.array(
            [
                all(
                    (
                        token.split(":", 1)[1] in transactions["tastes"].get(material_id, set())
                        if token.startswith("Taste:")
                        else token.split(":", 1)[1] in transactions["natures"].get(material_id, set())
                    )
                    for token in antecedent.split(" + ")
                )
                for material_id in material_ids
            ],
            dtype=bool,
        )
        outcome_key = "functions" if relation == "HAS_FUNCTION" else "indications"
        b = np.array([consequent in transactions[outcome_key].get(m, set()) for m in material_ids], dtype=bool)
        null_values = []
        for permutation in range(n_permutations):
            shuffled = rng.permutation(b)
            joint = int(np.sum(a & shuffled))
            confidence = joint / max(int(np.sum(a)), 1)
            prevalence = max(float(np.mean(shuffled)), 1e-12)
            null_lift = confidence / prevalence
            null_values.append(null_lift)
            output.append(
                {
                    "rule_label_en": rule_label(antecedent, consequent),
                    "permutation": permutation + 1,
                    "null_lift": null_lift,
                    "observed_lift": observed,
                }
            )
        p_permutation = (1 + sum(value >= observed for value in null_values)) / (n_permutations + 1)
        for record in output[-n_permutations:]:
            record["permutation_p_value"] = p_permutation
    return pd.DataFrame.from_records(output)


def build_coverage_table(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    materials = data["materials"][["material_id", "label", "source_type_text"]].copy()
    presence: dict[str, set[str]] = {
        "Taste": set(
            data["properties"].loc[
                data["properties"]["property_class"] == "Medicinal flavor", "material_id"
            ]
        ),
        "Nature": set(
            data["properties"].loc[
                data["properties"]["property_class"] == "Medicinal nature", "material_id"
            ]
        ),
        "Potency": set(
            data["properties"].loc[
                data["properties"]["property_class"] == "Medicinal potency feature", "material_id"
            ]
        ),
        "Function": set(
            data["material_terms"].loc[data["material_terms"]["relation"] == "HAS_FUNCTION", "material_id"]
        ),
        "Indication": set(
            data["material_terms"].loc[
                data["material_terms"]["relation"] == "TREATS_INDICATION", "material_id"
            ]
        ),
        "Origin": set(data["material_origins"]["material_id"]),
        "Species_ID": set(
            data["material_origins"].loc[
                data["material_origins"]["species_id"].fillna("").astype(str).str.strip() != "", "material_id"
            ]
        ),
    }
    for column, members in presence.items():
        materials[column] = materials["material_id"].isin(members).astype(int)
    materials["source_type_en"] = materials["source_type_text"].map(SOURCE_ENGLISH).fillna("Unresolved")
    materials = materials.sort_values(["source_type_en", "material_id"]).reset_index(drop=True)
    return materials


def source_type_summary(coverage: pd.DataFrame) -> pd.DataFrame:
    order = ["植物", "动物", "矿物", "真菌"]
    summary = (
        coverage.groupby("source_type_text", dropna=False)["material_id"]
        .nunique()
        .reindex(order)
        .fillna(0)
        .astype(int)
        .rename("material_count")
        .reset_index()
    )
    summary["source_type_en"] = summary["source_type_text"].map(SOURCE_ENGLISH)
    summary["percent"] = summary["material_count"] / len(coverage) * 100
    return summary


def taxonomy_summaries(data: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    linked = data["mmp_po"].merge(data["taxonomy"], on="species_id", how="left")
    kingdom = (
        linked.groupby("kingdom_name", dropna=False)
        .agg(material_count=("material_id", "nunique"), species_count=("species_id", "nunique"))
        .reset_index()
        .sort_values("material_count", ascending=False)
    )
    family = (
        linked.groupby("family_name", dropna=False)
        .agg(material_count=("material_id", "nunique"), species_count=("species_id", "nunique"))
        .reset_index()
        .sort_values(["material_count", "family_name"], ascending=[False, True])
    )
    genus = (
        linked.groupby("genus_name", dropna=False)
        .agg(material_count=("material_id", "nunique"), species_count=("species_id", "nunique"))
        .reset_index()
        .sort_values(["material_count", "genus_name"], ascending=[False, True])
    )
    multi = (
        linked.groupby("material_id")
        .agg(
            species_count=("species_id", "nunique"),
            species_names=("species_name", lambda values: "; ".join(sorted(set(values.dropna())))),
            families=("family_name", lambda values: "; ".join(sorted(set(values.dropna())))),
        )
        .reset_index()
        .merge(data["materials"][["material_id", "label"]], on="material_id", how="left")
    )
    multi = multi[multi["species_count"] > 1].sort_values(["species_count", "material_id"], ascending=[False, True])
    return {"linked": linked, "kingdom": kingdom, "family": family, "genus": genus, "multi": multi}


def build_qc_flags(data: dict[str, pd.DataFrame], coverage: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    missing_nature = coverage[coverage["Nature"] == 0]
    for row in missing_nature.itertuples(index=False):
        records.append(
            {
                "flag_type": "Missing medicinal nature",
                "material_id": row.material_id,
                "material_label": row.label,
                "observed_value": "",
                "expected_or_action": "Predictive hypothesis followed by expert review",
                "severity": "High",
            }
        )
    for label in ("尖叶假龙胆", "苏木", "紫丁香"):
        match = coverage[coverage["label"] == label]
        if match.empty:
            continue
        row = match.iloc[0]
        records.append(
            {
                "flag_type": "Source type requires manual review",
                "material_id": row["material_id"],
                "material_label": row["label"],
                "observed_value": row["source_type_text"],
                "expected_or_action": "Reconcile source description and taxonomy before submission",
                "severity": "High",
            }
        )
    class_conflicts = data["properties"][
        (data["properties"]["property_class"] == "Medicinal flavor")
        & (data["properties"]["property_label"].isin(["寒", "凉", "热", "温", "平"]))
    ]
    labels = data["materials"].set_index("material_id")["label"].to_dict()
    for row in class_conflicts.itertuples(index=False):
        records.append(
            {
                "flag_type": "Property class-label conflict",
                "material_id": row.material_id,
                "material_label": labels.get(row.material_id, ""),
                "observed_value": f"{row.property_label} in {row.property_class}",
                "expected_or_action": "Verify whether the record belongs to Medicinal nature",
                "severity": "Medium",
            }
        )
    no_species = coverage[coverage["Species_ID"] == 0]
    for row in no_species.itertuples(index=False):
        records.append(
            {
                "flag_type": "Missing species_ID",
                "material_id": row.material_id,
                "material_label": row.label,
                "observed_value": row.source_type_text,
                "expected_or_action": "Retain as non-species origin or curate a taxonomy identifier",
                "severity": "Medium" if row.source_type_text != "矿物" else "Expected",
            }
        )
    return pd.DataFrame.from_records(records)


def canonical_property_tables(
    data: dict[str, pd.DataFrame], transactions: dict[str, object]
) -> dict[str, pd.DataFrame | np.ndarray | list[str]]:
    material_ids: list[str] = transactions["material_ids"]
    taste_order = ["Bitter", "Sweet", "Pungent", "Astringent", "Salty", "Sour", "Bland"]
    nature_order = ["Cold", "Cool", "Neutral", "Warm", "Hot"]
    potency_order = [
        POTENCY_ENGLISH[label]
        for label in sorted(POTENCY_ENGLISH, key=lambda item: item)
        if any(label in values for values in transactions["potencies"].values())
    ]

    taste_matrix = pd.DataFrame(0, index=material_ids, columns=taste_order, dtype=int)
    nature_matrix = pd.DataFrame(0, index=material_ids, columns=nature_order, dtype=int)
    potency_matrix = pd.DataFrame(0, index=material_ids, columns=potency_order, dtype=int)
    for material_id in material_ids:
        for label in transactions["tastes"].get(material_id, set()):
            canonical = TASTE_CANONICAL.get(label)
            if canonical:
                taste_matrix.loc[material_id, canonical] = 1
        for label in transactions["natures"].get(material_id, set()):
            canonical = NATURE_CANONICAL.get(label)
            if canonical:
                nature_matrix.loc[material_id, canonical] = 1
        for label in transactions["potencies"].get(material_id, set()):
            translated = POTENCY_ENGLISH.get(label)
            if translated:
                potency_matrix.loc[material_id, translated] = 1

    taste_counts = taste_matrix.sum(axis=0).rename("material_count").rename_axis("taste").reset_index()
    nature_counts = nature_matrix.sum(axis=0).rename("material_count").rename_axis("nature").reset_index()
    combination = pd.DataFrame(0, index=taste_order, columns=nature_order, dtype=int)
    for taste in taste_order:
        for nature in nature_order:
            combination.loc[taste, nature] = int(np.sum((taste_matrix[taste] == 1) & (nature_matrix[nature] == 1)))

    feature_matrix = pd.concat(
        [
            taste_matrix.add_prefix("Taste:"),
            nature_matrix.add_prefix("Nature:"),
            potency_matrix.add_prefix("Potency:"),
        ],
        axis=1,
    )
    centered = feature_matrix.to_numpy(dtype=float) - feature_matrix.to_numpy(dtype=float).mean(axis=0, keepdims=True)
    u, singular_values, _ = np.linalg.svd(centered, full_matrices=False)
    coordinates = u[:, :2] * singular_values[:2]
    variance = singular_values**2
    explained = variance[:2] / variance.sum()
    pca = pd.DataFrame(
        {
            "material_id": material_ids,
            "PC1": coordinates[:, 0],
            "PC2": coordinates[:, 1],
            "PC1_explained_variance": explained[0],
            "PC2_explained_variance": explained[1],
        }
    ).merge(data["materials"][["material_id", "label", "source_type_text"]], on="material_id", how="left")

    top_features = (
        feature_matrix.sum(axis=0).sort_values(ascending=False).head(14).index.tolist()
    )
    source = data["materials"].set_index("material_id")["source_type_text"].reindex(material_ids)
    source_prevalence_records: list[dict[str, object]] = []
    for source_type in ["植物", "动物", "矿物", "真菌"]:
        mask = source == source_type
        for feature in top_features:
            source_prevalence_records.append(
                {
                    "source_type": source_type,
                    "source_type_en": SOURCE_ENGLISH[source_type],
                    "feature": feature,
                    "feature_en": feature,
                    "prevalence": float(feature_matrix.loc[mask, feature].mean()) if mask.any() else float("nan"),
                    "n_materials": int(mask.sum()),
                }
            )
    source_prevalence = pd.DataFrame.from_records(source_prevalence_records)
    pivot = source_prevalence.pivot(index="source_type_en", columns="feature_en", values="prevalence")
    zscore = (pivot - pivot.mean(axis=0)) / pivot.std(axis=0, ddof=0).replace(0, np.nan)
    zscore = zscore.fillna(0)

    potency_counts = potency_matrix.sum(axis=0)
    cooccurrence = potency_matrix.T.dot(potency_matrix)
    potency_edges: list[dict[str, object]] = []
    for left_index, left in enumerate(potency_matrix.columns):
        for right_index in range(left_index + 1, len(potency_matrix.columns)):
            right = potency_matrix.columns[right_index]
            count = int(cooccurrence.loc[left, right])
            if count >= 5:
                potency_edges.append({"source": left, "target": right, "cooccurrence": count})
    potency_edges_df = pd.DataFrame.from_records(potency_edges).sort_values("cooccurrence", ascending=False)
    potency_nodes = potency_counts.rename("material_count").rename_axis("potency").reset_index()

    return {
        "taste_matrix": taste_matrix,
        "nature_matrix": nature_matrix,
        "potency_matrix": potency_matrix,
        "taste_counts": taste_counts,
        "nature_counts": nature_counts,
        "taste_nature_combination": combination,
        "feature_matrix": feature_matrix,
        "pca": pca,
        "source_prevalence": source_prevalence,
        "source_prevalence_zscore": zscore,
        "potency_nodes": potency_nodes,
        "potency_edges": potency_edges_df,
    }


def deterministic_spring_layout(
    nodes: list[str], edges: list[tuple[str, str, float]], iterations: int = 350
) -> dict[str, np.ndarray]:
    if not nodes:
        return {}
    rng = np.random.default_rng(RANDOM_SEED)
    positions = rng.normal(0, 0.4, size=(len(nodes), 2))
    node_index = {node: index for index, node in enumerate(nodes)}
    area = 4.0
    k = math.sqrt(area / max(len(nodes), 1))
    temperature = 0.18
    for iteration in range(iterations):
        displacement = np.zeros_like(positions)
        for left in range(len(nodes)):
            delta = positions[left] - positions
            distance = np.sqrt(np.sum(delta**2, axis=1)) + 1e-6
            force = (k * k / distance**2)[:, None] * delta
            force[left] = 0
            displacement[left] += force.sum(axis=0)
        for source, target, weight in edges:
            left, right = node_index[source], node_index[target]
            delta = positions[left] - positions[right]
            distance = max(float(np.linalg.norm(delta)), 1e-6)
            attraction = (distance * distance / k) * (0.35 + math.log1p(weight) / 5.0)
            vector = delta / distance * attraction
            displacement[left] -= vector
            displacement[right] += vector
        norms = np.linalg.norm(displacement, axis=1)
        scale = np.minimum(norms, temperature) / np.maximum(norms, 1e-9)
        positions += displacement * scale[:, None]
        positions -= positions.mean(axis=0, keepdims=True)
        temperature *= 0.992
    maximum = np.abs(positions).max()
    if maximum > 0:
        positions /= maximum
    return {node: positions[index] for node, index in node_index.items()}


def rank_phytomedicine_candidates(
    data: dict[str, pd.DataFrame], transactions: dict[str, object]
) -> pd.DataFrame:
    origin_species = (
        data["material_origins"]
        .sort_values(["material_id", "species_name"])
        .groupby("material_id")
        .agg(
            species_name=("species_name", lambda values: next((str(v) for v in values if pd.notna(v) and str(v)), "")),
            species_id=("species_id", lambda values: next((str(v) for v in values if pd.notna(v) and str(v)), "")),
        )
    )
    materials = data["materials"].set_index("material_id")
    records: list[dict[str, object]] = []
    inflammatory_terms = ("炎", "热", "肿", "疮", "痛")
    for material_id in transactions["material_ids"]:
        source_type = str(materials.loc[material_id, "source_type_text"])
        if source_type != "植物":
            continue
        tastes = transactions["tastes"].get(material_id, set())
        natures = transactions["natures"].get(material_id, set())
        functions = transactions["functions"].get(material_id, set())
        indications = transactions["indications"].get(material_id, set())
        evidence = {
            "Bitter": any(TASTE_CANONICAL.get(value) == "Bitter" for value in tastes),
            "Cold_or_cool": any(NATURE_CANONICAL.get(value) in {"Cold", "Cool"} for value in natures),
            "Heat_clearing": "清热" in functions,
            "Detoxifying": "解毒" in functions,
        }
        indication_hits = sorted(term for term in indications if any(token in term for token in inflammatory_terms))
        therapeutic_edge_count = len(functions) + len(indications)
        evidence_breadth_bonus = 0.12 * math.log1p(therapeutic_edge_count)
        score = (
            1.0 * evidence["Bitter"]
            + 1.0 * evidence["Cold_or_cool"]
            + 2.0 * evidence["Heat_clearing"]
            + 2.0 * evidence["Detoxifying"]
            + min(len(indication_hits), 3) * 0.35
            + (0.5 if material_id in origin_species.index and origin_species.loc[material_id, "species_id"] else 0.0)
            + evidence_breadth_bonus
        )
        species_name = origin_species.loc[material_id, "species_name"] if material_id in origin_species.index else ""
        species_id = origin_species.loc[material_id, "species_id"] if material_id in origin_species.index else ""
        records.append(
            {
                "material_id": material_id,
                "material_label_original": materials.loc[material_id, "label"],
                "display_name": species_name or material_id,
                "species_name": species_name,
                "species_id": species_id,
                "score": score,
                **{key: int(value) for key, value in evidence.items()},
                "inflammation_related_indication_count": len(indication_hits),
                "inflammation_related_indications_original": "; ".join(indication_hits),
                "therapeutic_edge_count": therapeutic_edge_count,
                "evidence_breadth_bonus": evidence_breadth_bonus,
            }
        )
    candidates = pd.DataFrame.from_records(records)
    return candidates.sort_values(
        ["score", "Heat_clearing", "Detoxifying", "material_id"], ascending=[False, False, False, True]
    ).reset_index(drop=True)


@dataclasses.dataclass
class KGSplit:
    entities: list[str]
    relations: list[str]
    triples: np.ndarray
    train: np.ndarray
    validation: np.ndarray
    test: np.ndarray
    entity_to_index: dict[str, int]
    relation_to_index: dict[str, int]
    candidate_tails: dict[int, np.ndarray]
    all_true_tails: dict[tuple[int, int], set[int]]
    edge_lookup: pd.DataFrame


def stratified_kg_split(data: dict[str, pd.DataFrame]) -> KGSplit:
    edges = data["kg_edges"].copy()
    edges = edges[edges["predicate"].isin(PREDICATE_LABELS)].reset_index(drop=True)
    entities = sorted(set(edges["subject_id"]) | set(edges["object_id"]))
    relations = sorted(edges["predicate"].unique())
    entity_to_index = {value: index for index, value in enumerate(entities)}
    relation_to_index = {value: index for index, value in enumerate(relations)}
    triples = np.column_stack(
        [
            edges["subject_id"].map(entity_to_index).to_numpy(dtype=int),
            edges["predicate"].map(relation_to_index).to_numpy(dtype=int),
            edges["object_id"].map(entity_to_index).to_numpy(dtype=int),
        ]
    )
    rng = np.random.default_rng(RANDOM_SEED)
    train_indices: list[int] = []
    validation_indices: list[int] = []
    test_indices: list[int] = []
    for relation_name in relations:
        relation_index = relation_to_index[relation_name]
        indices = np.flatnonzero(triples[:, 1] == relation_index)
        shuffled = rng.permutation(indices)
        n_test = max(1, int(round(len(indices) * 0.10)))
        n_validation = max(1, int(round(len(indices) * 0.10)))
        test_indices.extend(shuffled[:n_test].tolist())
        validation_indices.extend(shuffled[n_test : n_test + n_validation].tolist())
        train_indices.extend(shuffled[n_test + n_validation :].tolist())
    train = triples[np.array(sorted(train_indices), dtype=int)]
    validation = triples[np.array(sorted(validation_indices), dtype=int)]
    test = triples[np.array(sorted(test_indices), dtype=int)]

    candidate_tails = {
        relation_to_index[name]: np.array(
            sorted(set(triples[triples[:, 1] == relation_to_index[name], 2].tolist())), dtype=int
        )
        for name in relations
    }
    all_true_tails: dict[tuple[int, int], set[int]] = collections.defaultdict(set)
    for head, relation, tail in triples:
        all_true_tails[(int(head), int(relation))].add(int(tail))
    return KGSplit(
        entities=entities,
        relations=relations,
        triples=triples,
        train=train,
        validation=validation,
        test=test,
        entity_to_index=entity_to_index,
        relation_to_index=relation_to_index,
        candidate_tails=candidate_tails,
        all_true_tails=dict(all_true_tails),
        edge_lookup=edges,
    )


def relation_negative_tails(
    triples: np.ndarray, candidate_tails: dict[int, np.ndarray], rng: np.random.Generator
) -> np.ndarray:
    negatives = np.empty(len(triples), dtype=int)
    for relation in np.unique(triples[:, 1]):
        mask = triples[:, 1] == relation
        candidates = candidate_tails[int(relation)]
        sampled = rng.choice(candidates, size=int(mask.sum()), replace=True)
        positive = triples[mask, 2]
        collision = sampled == positive
        while collision.any() and len(candidates) > 1:
            sampled[collision] = rng.choice(candidates, size=int(collision.sum()), replace=True)
            collision = sampled == positive
        negatives[mask] = sampled
    return negatives


class TransEModel:
    name = "TransE"

    def __init__(self, n_entities: int, n_relations: int, dimension: int, rng: np.random.Generator):
        scale = 0.6 / math.sqrt(dimension)
        self.entity = rng.normal(0, scale, size=(n_entities, dimension))
        self.relation = rng.normal(0, scale, size=(n_relations, dimension))

    def train(
        self,
        triples: np.ndarray,
        candidate_tails: dict[int, np.ndarray],
        epochs: int = 60,
        batch_size: int = 512,
        learning_rate: float = 0.08,
        margin: float = 1.0,
        seed: int = RANDOM_SEED,
    ) -> None:
        rng = np.random.default_rng(seed)
        for epoch in range(epochs):
            for selection in np.array_split(rng.permutation(len(triples)), math.ceil(len(triples) / batch_size)):
                batch = triples[selection]
                negative_tails = relation_negative_tails(batch, candidate_tails, rng)
                heads, relations, tails = batch.T
                positive_residual = self.entity[heads] + self.relation[relations] - self.entity[tails]
                negative_residual = self.entity[heads] + self.relation[relations] - self.entity[negative_tails]
                positive_distance = np.sum(positive_residual**2, axis=1)
                negative_distance = np.sum(negative_residual**2, axis=1)
                active = margin + positive_distance - negative_distance > 0
                if not active.any():
                    continue
                h, r, t, nt = heads[active], relations[active], tails[active], negative_tails[active]
                pos, neg = positive_residual[active], negative_residual[active]
                factor = learning_rate / max(len(h), 1)
                entity_gradient = np.zeros_like(self.entity)
                relation_gradient = np.zeros_like(self.relation)
                np.add.at(entity_gradient, h, 2 * pos - 2 * neg)
                np.add.at(relation_gradient, r, 2 * pos - 2 * neg)
                np.add.at(entity_gradient, t, -2 * pos)
                np.add.at(entity_gradient, nt, 2 * neg)
                self.entity -= factor * entity_gradient
                self.relation -= factor * relation_gradient
                norms = np.linalg.norm(self.entity, axis=1, keepdims=True)
                self.entity /= np.maximum(norms, 1.0)

    def score_candidates(self, head: int, relation: int, candidates: np.ndarray) -> np.ndarray:
        residual = self.entity[head] + self.relation[relation] - self.entity[candidates]
        return -np.sum(residual**2, axis=1)


class ComplExModel:
    name = "ComplEx"

    def __init__(self, n_entities: int, n_relations: int, dimension: int, rng: np.random.Generator):
        scale = 0.4 / math.sqrt(dimension)
        self.er = rng.normal(0, scale, size=(n_entities, dimension))
        self.ei = rng.normal(0, scale, size=(n_entities, dimension))
        self.rr = rng.normal(0, scale, size=(n_relations, dimension))
        self.ri = rng.normal(0, scale, size=(n_relations, dimension))

    @staticmethod
    def gradient_components(
        hr: np.ndarray,
        hi: np.ndarray,
        rr: np.ndarray,
        ri: np.ndarray,
        tr: np.ndarray,
        ti: np.ndarray,
    ) -> tuple[np.ndarray, ...]:
        gh_r = rr * tr + ri * ti
        gh_i = rr * ti - ri * tr
        gr_r = hr * tr + hi * ti
        gr_i = hr * ti - hi * tr
        gt_r = hr * rr - hi * ri
        gt_i = hr * ri + hi * rr
        return gh_r, gh_i, gr_r, gr_i, gt_r, gt_i

    def score_triples(self, heads: np.ndarray, relations: np.ndarray, tails: np.ndarray) -> np.ndarray:
        hr, hi = self.er[heads], self.ei[heads]
        rr, ri = self.rr[relations], self.ri[relations]
        tr, ti = self.er[tails], self.ei[tails]
        return np.sum(hr * rr * tr + hr * ri * ti + hi * rr * ti - hi * ri * tr, axis=1)

    def train(
        self,
        triples: np.ndarray,
        candidate_tails: dict[int, np.ndarray],
        epochs: int = 70,
        batch_size: int = 512,
        learning_rate: float = 0.12,
        seed: int = RANDOM_SEED + 1,
    ) -> None:
        rng = np.random.default_rng(seed)
        for epoch in range(epochs):
            for selection in np.array_split(rng.permutation(len(triples)), math.ceil(len(triples) / batch_size)):
                batch = triples[selection]
                negative_tails = relation_negative_tails(batch, candidate_tails, rng)
                heads, relations, tails = batch.T
                positive_score = self.score_triples(heads, relations, tails)
                negative_score = self.score_triples(heads, relations, negative_tails)
                coefficient = 1.0 / (1.0 + np.exp(np.clip(positive_score - negative_score, -30, 30)))
                coefficient = coefficient[:, None]
                hr, hi = self.er[heads], self.ei[heads]
                rr, ri = self.rr[relations], self.ri[relations]
                tr, ti = self.er[tails], self.ei[tails]
                nr, ni = self.er[negative_tails], self.ei[negative_tails]
                positive_grad = self.gradient_components(hr, hi, rr, ri, tr, ti)
                negative_grad = self.gradient_components(hr, hi, rr, ri, nr, ni)
                gradients = [np.zeros_like(array) for array in (self.er, self.ei, self.rr, self.ri)]
                factor = learning_rate / max(len(batch), 1)
                np.add.at(gradients[0], heads, coefficient * (positive_grad[0] - negative_grad[0]))
                np.add.at(gradients[1], heads, coefficient * (positive_grad[1] - negative_grad[1]))
                np.add.at(gradients[2], relations, coefficient * (positive_grad[2] - negative_grad[2]))
                np.add.at(gradients[3], relations, coefficient * (positive_grad[3] - negative_grad[3]))
                np.add.at(gradients[0], tails, coefficient * positive_grad[4])
                np.add.at(gradients[1], tails, coefficient * positive_grad[5])
                np.add.at(gradients[0], negative_tails, -coefficient * negative_grad[4])
                np.add.at(gradients[1], negative_tails, -coefficient * negative_grad[5])
                self.er += factor * gradients[0]
                self.ei += factor * gradients[1]
                self.rr += factor * gradients[2]
                self.ri += factor * gradients[3]
                entity_norm = np.sqrt(np.sum(self.er**2 + self.ei**2, axis=1, keepdims=True))
                scale = np.maximum(entity_norm, 1.0)
                self.er /= scale
                self.ei /= scale

    def score_candidates(self, head: int, relation: int, candidates: np.ndarray) -> np.ndarray:
        heads = np.full(len(candidates), head, dtype=int)
        relations = np.full(len(candidates), relation, dtype=int)
        return self.score_triples(heads, relations, candidates)


class RotatEModel:
    name = "RotatE"

    def __init__(self, n_entities: int, n_relations: int, dimension: int, rng: np.random.Generator):
        scale = 0.5 / math.sqrt(dimension)
        self.er = rng.normal(0, scale, size=(n_entities, dimension))
        self.ei = rng.normal(0, scale, size=(n_entities, dimension))
        self.phase = rng.uniform(-math.pi, math.pi, size=(n_relations, dimension))

    def distance_components(
        self, heads: np.ndarray, relations: np.ndarray, tails: np.ndarray
    ) -> tuple[np.ndarray, ...]:
        hr, hi = self.er[heads], self.ei[heads]
        cosine, sine = np.cos(self.phase[relations]), np.sin(self.phase[relations])
        zr = hr * cosine - hi * sine
        zi = hr * sine + hi * cosine
        residual_r = zr - self.er[tails]
        residual_i = zi - self.ei[tails]
        return hr, hi, cosine, sine, zr, zi, residual_r, residual_i

    def train(
        self,
        triples: np.ndarray,
        candidate_tails: dict[int, np.ndarray],
        epochs: int = 65,
        batch_size: int = 512,
        learning_rate: float = 0.055,
        margin: float = 1.0,
        seed: int = RANDOM_SEED + 2,
    ) -> None:
        rng = np.random.default_rng(seed)
        for epoch in range(epochs):
            for selection in np.array_split(rng.permutation(len(triples)), math.ceil(len(triples) / batch_size)):
                batch = triples[selection]
                negative_tails = relation_negative_tails(batch, candidate_tails, rng)
                heads, relations, tails = batch.T
                positive = self.distance_components(heads, relations, tails)
                negative = self.distance_components(heads, relations, negative_tails)
                positive_distance = np.sum(positive[6] ** 2 + positive[7] ** 2, axis=1)
                negative_distance = np.sum(negative[6] ** 2 + negative[7] ** 2, axis=1)
                active = margin + positive_distance - negative_distance > 0
                if not active.any():
                    continue
                h, r, t, nt = heads[active], relations[active], tails[active], negative_tails[active]
                pos = tuple(value[active] for value in positive)
                neg = tuple(value[active] for value in negative)
                entity_grad_r = np.zeros_like(self.er)
                entity_grad_i = np.zeros_like(self.ei)
                phase_grad = np.zeros_like(self.phase)

                pos_h_r = 2 * (pos[2] * pos[6] + pos[3] * pos[7])
                pos_h_i = 2 * (-pos[3] * pos[6] + pos[2] * pos[7])
                neg_h_r = 2 * (neg[2] * neg[6] + neg[3] * neg[7])
                neg_h_i = 2 * (-neg[3] * neg[6] + neg[2] * neg[7])
                pos_phase = 2 * (-pos[5] * pos[6] + pos[4] * pos[7])
                neg_phase = 2 * (-neg[5] * neg[6] + neg[4] * neg[7])
                np.add.at(entity_grad_r, h, pos_h_r - neg_h_r)
                np.add.at(entity_grad_i, h, pos_h_i - neg_h_i)
                np.add.at(phase_grad, r, pos_phase - neg_phase)
                np.add.at(entity_grad_r, t, -2 * pos[6])
                np.add.at(entity_grad_i, t, -2 * pos[7])
                np.add.at(entity_grad_r, nt, 2 * neg[6])
                np.add.at(entity_grad_i, nt, 2 * neg[7])
                factor = learning_rate / max(len(h), 1)
                self.er -= factor * entity_grad_r
                self.ei -= factor * entity_grad_i
                self.phase -= factor * phase_grad
                self.phase = (self.phase + math.pi) % (2 * math.pi) - math.pi
                entity_norm = np.sqrt(np.sum(self.er**2 + self.ei**2, axis=1, keepdims=True))
                scale = np.maximum(entity_norm, 1.0)
                self.er /= scale
                self.ei /= scale

    def score_candidates(self, head: int, relation: int, candidates: np.ndarray) -> np.ndarray:
        heads = np.full(len(candidates), head, dtype=int)
        relations = np.full(len(candidates), relation, dtype=int)
        values = self.distance_components(heads, relations, candidates)
        return -np.sum(values[6] ** 2 + values[7] ** 2, axis=1)


def filtered_rank(
    scores: np.ndarray,
    candidates: np.ndarray,
    target: int,
    filtered: set[int],
) -> int:
    target_position = int(np.flatnonzero(candidates == target)[0])
    masked = scores.copy()
    for known_tail in filtered:
        if known_tail == target:
            continue
        positions = np.flatnonzero(candidates == known_tail)
        if len(positions):
            masked[int(positions[0])] = -np.inf
    target_score = masked[target_position]
    return 1 + int(np.sum(masked > target_score))


def rule_prior_score(
    split: KGSplit,
    transactions: dict[str, object],
    rules: pd.DataFrame,
    head_index: int,
    relation_index: int,
    candidates: np.ndarray,
) -> np.ndarray:
    relation_name = split.relations[relation_index]
    if relation_name not in {"HAS_FUNCTION", "TREATS_INDICATION"}:
        return np.zeros(len(candidates), dtype=float)
    head_entity = split.entities[head_index]
    material_id = head_entity.split(":", 1)[1] if ":" in head_entity else head_entity
    active_antecedents = set()
    for taste in transactions["tastes"].get(material_id, set()):
        active_antecedents.add(f"Taste:{taste}")
    for nature in transactions["natures"].get(material_id, set()):
        active_antecedents.add(f"Nature:{nature}")
    for taste in transactions["tastes"].get(material_id, set()):
        for nature in transactions["natures"].get(material_id, set()):
            active_antecedents.add(f"Taste:{taste} + Nature:{nature}")
    relevant = rules[
        (rules["consequent_relation"] == relation_name)
        & (rules["antecedent"].isin(active_antecedents))
        & (rules["joint_count"] >= 5)
        & (rules["lift"] > 1)
    ]
    lookup: dict[str, float] = {}
    for row in relevant.itertuples(index=False):
        term_id = transactions["term_ids_by_label"].get((relation_name, row.consequent))
        if term_id:
            lookup[term_id] = max(lookup.get(term_id, 0.0), math.log(max(float(row.lift), 1.0)))
    return np.array([lookup.get(split.entities[int(candidate)], 0.0) for candidate in candidates], dtype=float)


def evaluate_model(
    model: object,
    split: KGSplit,
    evaluation_triples: np.ndarray,
    therapeutic_only: bool = True,
    prior_rules: pd.DataFrame | None = None,
    transactions: dict[str, object] | None = None,
    alpha: float = 0.0,
) -> tuple[dict[str, float], pd.DataFrame]:
    therapeutic_indices = {
        split.relation_to_index[relation]
        for relation in ("HAS_FUNCTION", "TREATS_INDICATION")
        if relation in split.relation_to_index
    }
    ranks: list[int] = []
    records: list[dict[str, object]] = []
    for head, relation, tail in evaluation_triples:
        head, relation, tail = int(head), int(relation), int(tail)
        if therapeutic_only and relation not in therapeutic_indices:
            continue
        candidates = split.candidate_tails[relation]
        scores = model.score_candidates(head, relation, candidates).astype(float)
        if prior_rules is not None and transactions is not None and alpha > 0:
            standard = float(np.std(scores))
            normalized = (scores - float(np.mean(scores))) / (standard if standard > 1e-9 else 1.0)
            prior = rule_prior_score(split, transactions, prior_rules, head, relation, candidates)
            scores = normalized + alpha * prior
        rank = filtered_rank(scores, candidates, tail, split.all_true_tails.get((head, relation), set()))
        ranks.append(rank)
        records.append(
            {
                "head_entity": split.entities[head],
                "relation": split.relations[relation],
                "tail_entity": split.entities[tail],
                "rank": rank,
                "candidate_count": len(candidates),
            }
        )
    rank_array = np.asarray(ranks, dtype=float)
    metrics = {
        "MRR": float(np.mean(1.0 / rank_array)),
        "Hits@1": float(np.mean(rank_array <= 1)),
        "Hits@3": float(np.mean(rank_array <= 3)),
        "Hits@10": float(np.mean(rank_array <= 10)),
        "MeanRank": float(np.mean(rank_array)),
        "n_test_edges": int(len(rank_array)),
    }
    return metrics, pd.DataFrame.from_records(records)


def nature_prediction_for_shajie(
    data: dict[str, pd.DataFrame],
    transactions: dict[str, object],
    property_tables: dict[str, object],
) -> pd.DataFrame:
    target_id = "MMP0361"
    feature_matrix: pd.DataFrame = property_tables["feature_matrix"]
    nature_columns = [column for column in feature_matrix.columns if column.startswith("Nature:")]
    predictors = feature_matrix.drop(columns=nature_columns)
    target_vector = predictors.loc[target_id].to_numpy(dtype=float)
    known_ids = [
        material_id
        for material_id in predictors.index
        if len(transactions["natures"].get(material_id, set())) > 0 and material_id != target_id
    ]
    matrix = predictors.loc[known_ids].to_numpy(dtype=float)
    numerator = matrix @ target_vector
    denominator = np.linalg.norm(matrix, axis=1) * max(np.linalg.norm(target_vector), 1e-9)
    similarities = numerator / np.maximum(denominator, 1e-9)
    nearest_positions = np.argsort(similarities)[::-1][:30]
    votes = collections.defaultdict(float)
    neighbour_records: list[tuple[str, float, set[str]]] = []
    for position in nearest_positions:
        material_id = known_ids[int(position)]
        similarity = max(float(similarities[int(position)]), 0.0)
        neighbour_records.append((material_id, similarity, transactions["natures"].get(material_id, set())))
        for label in transactions["natures"].get(material_id, set()):
            canonical = NATURE_CANONICAL.get(label)
            if canonical:
                votes[canonical] += similarity
    total = sum(votes.values()) or 1.0
    labels = data["materials"].set_index("material_id")["label"].to_dict()
    records = []
    for rank, (nature, vote) in enumerate(sorted(votes.items(), key=lambda item: item[1], reverse=True), start=1):
        support_neighbours = [
            f"{material_id} ({labels.get(material_id, '')})"
            for material_id, similarity, values in neighbour_records
            if any(NATURE_CANONICAL.get(value) == nature for value in values)
        ][:5]
        records.append(
            {
                "material_id": target_id,
                "material_label_original": labels.get(target_id, "沙芥"),
                "predicted_nature": nature,
                "rank": rank,
                "weighted_vote_probability": vote / total,
                "supporting_neighbours": "; ".join(support_neighbours),
                "status": "Prediction for expert review; no ground truth in D4",
            }
        )
    return pd.DataFrame.from_records(records)


def run_kg_benchmark(
    data: dict[str, pd.DataFrame],
    transactions: dict[str, object],
    rules: pd.DataFrame,
    property_tables: dict[str, object],
) -> dict[str, object]:
    split = stratified_kg_split(data)
    rng = np.random.default_rng(RANDOM_SEED)
    models = [
        TransEModel(len(split.entities), len(split.relations), 32, rng),
        RotatEModel(len(split.entities), len(split.relations), 32, rng),
        ComplExModel(len(split.entities), len(split.relations), 32, rng),
    ]
    metric_records: list[dict[str, object]] = []
    rank_tables: dict[str, pd.DataFrame] = {}
    validation_mrr: dict[str, float] = {}
    for model in models:
        model.train(split.train, split.candidate_tails)
        validation_metrics, _ = evaluate_model(model, split, split.validation)
        metrics, ranks = evaluate_model(model, split, split.test)
        validation_mrr[model.name] = validation_metrics["MRR"]
        metric_records.append({"model": model.name, "prior_guided": 0, **metrics})
        rank_tables[model.name] = ranks

    best_model = max(models, key=lambda model: validation_mrr[model.name])
    alpha_results = []
    for alpha in (0.25, 0.5, 1.0, 1.5, 2.0):
        metrics, _ = evaluate_model(
            best_model,
            split,
            split.validation,
            prior_rules=rules,
            transactions=transactions,
            alpha=alpha,
        )
        alpha_results.append((alpha, metrics["MRR"]))
    best_alpha = max(alpha_results, key=lambda item: item[1])[0]
    prior_metrics, prior_ranks = evaluate_model(
        best_model,
        split,
        split.test,
        prior_rules=rules,
        transactions=transactions,
        alpha=best_alpha,
    )
    metric_records.append(
        {
            "model": "Rule-enhanced KG",
            "prior_guided": 1,
            "base_embedding_model": best_model.name,
            "prior_alpha": best_alpha,
            **prior_metrics,
        }
    )
    rank_tables["Rule-enhanced KG"] = prior_ranks
    metrics_df = pd.DataFrame.from_records(metric_records)

    merged = rank_tables[best_model.name].merge(
        prior_ranks,
        on=["head_entity", "relation", "tail_entity", "candidate_count"],
        suffixes=("_base", "_prior"),
    )
    merged["rank_improvement"] = merged["rank_base"] - merged["rank_prior"]
    explainable = merged.sort_values(["rank_improvement", "rank_prior"], ascending=[False, True]).head(20)

    split_rows = []
    for name, triples in (("Train", split.train), ("Validation", split.validation), ("Test", split.test)):
        for relation_index, relation_name in enumerate(split.relations):
            split_rows.append(
                {
                    "split": name,
                    "relation": relation_name,
                    "edge_count": int(np.sum(triples[:, 1] == relation_index)),
                }
            )
    split_counts = pd.DataFrame.from_records(split_rows)
    nature_predictions = nature_prediction_for_shajie(data, transactions, property_tables)
    return {
        "split": split,
        "models": models,
        "metrics": metrics_df,
        "rank_tables": rank_tables,
        "best_model_name": best_model.name,
        "best_alpha": best_alpha,
        "explainable": explainable,
        "split_counts": split_counts,
        "nature_predictions": nature_predictions,
    }


def export_analysis_tables(
    data: dict[str, pd.DataFrame],
    transactions: dict[str, object],
    coverage: pd.DataFrame,
    source_summary: pd.DataFrame,
    taxonomy: dict[str, pd.DataFrame],
    qc_flags: pd.DataFrame,
    property_tables: dict[str, object],
    rules: pd.DataFrame,
    permutations: pd.DataFrame,
    benchmark: dict[str, object],
    candidates: pd.DataFrame,
) -> None:
    module_counts = data["source_files"].copy()
    entity_counts = (
        data["entities"].groupby("entity_type")["entity_id"].nunique().rename("entity_count").reset_index()
    )
    relation_counts = (
        data["kg_edges"]
        .groupby("predicate")
        .agg(edge_count=("id", "count"), subject_count=("subject_id", "nunique"), object_count=("object_id", "nunique"))
        .reset_index()
        .sort_values("edge_count", ascending=False)
    )
    write_csv(module_counts, FIGURE_DATA_DIR / "figure1" / "Fig1A_module_counts.csv")
    write_csv(entity_counts, FIGURE_DATA_DIR / "figure1" / "Fig1B_entity_counts.csv")
    write_csv(relation_counts, FIGURE_DATA_DIR / "figure1" / "Fig1D_relation_counts.csv")

    write_csv(coverage, FIGURE_DATA_DIR / "figure2" / "Fig2A_material_coverage_matrix.csv")
    write_csv(source_summary, FIGURE_DATA_DIR / "figure2" / "Fig2B_source_type_counts.csv")
    write_csv(taxonomy["kingdom"], FIGURE_DATA_DIR / "figure2" / "Fig2C_species_taxonomy_coverage.csv")
    write_csv(taxonomy["family"], FIGURE_DATA_DIR / "figure2" / "Fig2D_family_counts.csv")
    write_csv(taxonomy["genus"], FIGURE_DATA_DIR / "figure2" / "Fig2D_genus_counts.csv")
    write_csv(taxonomy["multi"], FIGURE_DATA_DIR / "figure2" / "Fig2E_multi_origin_materials.csv")
    write_csv(qc_flags, FIGURE_DATA_DIR / "figure2" / "Fig2F_qc_flags.csv")

    write_csv(property_tables["taste_counts"], FIGURE_DATA_DIR / "figure3" / "Fig3A_taste_counts.csv")
    write_csv(property_tables["nature_counts"], FIGURE_DATA_DIR / "figure3" / "Fig3B_nature_counts.csv")
    combination = property_tables["taste_nature_combination"].rename_axis("taste").reset_index()
    write_csv(combination, FIGURE_DATA_DIR / "figure3" / "Fig3C_taste_nature_matrix.csv")
    write_csv(property_tables["potency_nodes"], FIGURE_DATA_DIR / "figure3" / "Fig3D_potency_nodes.csv")
    write_csv(property_tables["potency_edges"], FIGURE_DATA_DIR / "figure3" / "Fig3D_potency_edges.csv")
    write_csv(property_tables["source_prevalence"], FIGURE_DATA_DIR / "figure3" / "Fig3E_source_property_prevalence.csv")
    write_csv(
        property_tables["source_prevalence_zscore"].reset_index(),
        FIGURE_DATA_DIR / "figure3" / "Fig3E_source_property_zscores.csv",
    )
    write_csv(property_tables["pca"], FIGURE_DATA_DIR / "figure3" / "Fig3F_property_PCA_coordinates.csv")

    write_csv(rules, FIGURE_DATA_DIR / "figure4" / "Fig4_association_rules_all.csv")
    display_rules = rules[
        rules["consequent"].isin(TERM_ENGLISH)
        & (rules["lift"] > 1)
        & (rules["q_value"] < 0.05)
    ].sort_values(["lift", "support"], ascending=[False, False])
    write_csv(display_rules.head(30), FIGURE_DATA_DIR / "figure4" / "Fig4C_top_rules.csv")
    write_csv(permutations, FIGURE_DATA_DIR / "figure4" / "Fig4F_permutation_test.csv")

    write_csv(benchmark["split_counts"], FIGURE_DATA_DIR / "figure5" / "Fig5A_edge_split_counts.csv")
    write_csv(benchmark["metrics"], FIGURE_DATA_DIR / "figure5" / "Fig5C_link_prediction_metrics.csv")
    for model_name, table in benchmark["rank_tables"].items():
        write_csv(table, FIGURE_DATA_DIR / "figure5" / f"Fig5C_ranks_{model_name.replace(' ', '_')}.csv")
    write_csv(benchmark["explainable"], FIGURE_DATA_DIR / "figure5" / "Fig5D_explainable_rank_improvements.csv")
    write_csv(benchmark["nature_predictions"], FIGURE_DATA_DIR / "figure5" / "Fig5E_Shajie_nature_prediction.csv")

    write_csv(candidates, FIGURE_DATA_DIR / "figure6" / "Fig6A_candidate_prioritization.csv")
    prospective = pd.DataFrame(
        [
            {
                "panel": "B",
                "required_data": "Curated compound identities and compound-material links",
                "planned_method": "Compound-target-disease network integration",
                "current_status": "Not available in D1-D6",
            },
            {
                "panel": "C",
                "required_data": "Experimentally supported or predicted target list",
                "planned_method": "GO/KEGG over-representation analysis with FDR control",
                "current_status": "Not computed",
            },
            {
                "panel": "D",
                "required_data": "Compound structures, target structures or transcriptomic signatures",
                "planned_method": "Molecular docking or transcriptomic reversal",
                "current_status": "Not performed",
            },
            {
                "panel": "E",
                "required_data": "Independent biological replicates for NO, TNF-alpha, IL-6 and IL-1beta",
                "planned_method": "Prospective LPS-stimulated macrophage validation",
                "current_status": "Not performed",
            },
        ]
    )
    write_csv(prospective, FIGURE_DATA_DIR / "figure6" / "Fig6B-E_prospective_data_requirements.csv")


def run_analysis(export_tables: bool = True) -> dict[str, object]:
    ensure_output_dirs()
    data = load_data()
    transactions = build_transactions(data)
    coverage = build_coverage_table(data)
    source_summary = source_type_summary(coverage)
    taxonomy = taxonomy_summaries(data)
    qc_flags = build_qc_flags(data, coverage)
    property_tables = canonical_property_tables(data, transactions)
    rules = mine_association_rules(transactions)
    selected_permutation_rules = [
        ("Taste:苦 + Nature:寒", "清热", "HAS_FUNCTION"),
        ("Taste:辛 + Nature:热", "温胃", "HAS_FUNCTION"),
    ]
    permutations = permutation_stability(
        transactions,
        rules,
        selected_permutation_rules,
        n_permutations=1000,
    )
    benchmark = run_kg_benchmark(data, transactions, rules, property_tables)
    candidates = rank_phytomedicine_candidates(data, transactions)
    if export_tables:
        copy_source_snapshot()
        export_analysis_tables(
            data,
            transactions,
            coverage,
            source_summary,
            taxonomy,
            qc_flags,
            property_tables,
            rules,
            permutations,
            benchmark,
            candidates,
        )
    results = {
        "data": data,
        "transactions": transactions,
        "coverage": coverage,
        "source_summary": source_summary,
        "taxonomy": taxonomy,
        "qc_flags": qc_flags,
        "property_tables": property_tables,
        "rules": rules,
        "permutations": permutations,
        "benchmark": benchmark,
        "candidates": candidates,
    }
    if export_tables:
        cache_results = dict(results)
        cache_benchmark = dict(benchmark)
        cache_benchmark.pop("models", None)
        cache_benchmark.pop("split", None)
        cache_results["benchmark"] = cache_benchmark
        with ANALYSIS_CACHE.open("wb") as handle:
            pickle.dump(cache_results, handle, protocol=pickle.HIGHEST_PROTOCOL)
    return results


def figure1_overall_design(results: dict[str, object]) -> dict[str, str]:
    data = results["data"]
    fig = plt.figure(figsize=(183 / 25.4, 142 / 25.4))
    outer = gridspec.GridSpec(2, 12, figure=fig, height_ratios=[1.02, 1.0], hspace=0.34, wspace=0.78)

    ax_a = fig.add_subplot(outer[0, 0:5])
    ax_a.set_axis_off()
    panel_label(ax_a, "a", -0.04, 1.02)
    panel_title(ax_a, "D1-D6 curated data modules")
    modules = [
        ("D1", "Terminology", 1132, COLORS["blue_light"], COLORS["blue"]),
        ("D2", "Medicinal pieces", 558, COLORS["green_light"], COLORS["green"]),
        ("D3", "MMP-MMT", 5679, COLORS["purple_light"], COLORS["purple"]),
        ("D4", "Medicinal properties", 2362, COLORS["orange_light"], COLORS["orange"]),
        ("D5", "Origins", 390, COLORS["gray_light"], COLORS["gray"]),
        ("D6", "MMP-PO", 468, COLORS["magenta_light"], COLORS["magenta"]),
    ]
    positions = [(0.02, 0.62), (0.36, 0.62), (0.70, 0.62), (0.02, 0.20), (0.36, 0.20), (0.70, 0.20)]
    for (code, label, count, fill, edge), position in zip(modules, positions):
        add_box(ax_a, position, 0.27, 0.24, f"{code}\n{label}\n{count:,} records", fill, edge, fontsize=5.4, weight="bold")
    add_arrow(ax_a, (0.29, 0.74), (0.36, 0.74), COLORS["gray"])
    add_arrow(ax_a, (0.63, 0.74), (0.70, 0.74), COLORS["gray"])
    add_arrow(ax_a, (0.29, 0.32), (0.36, 0.32), COLORS["gray"])
    add_arrow(ax_a, (0.63, 0.32), (0.70, 0.32), COLORS["gray"])
    add_arrow(ax_a, (0.49, 0.60), (0.49, 0.46), COLORS["green"], width=1.0)

    ax_b = fig.add_subplot(outer[0, 5:9])
    ax_b.set_axis_off()
    panel_label(ax_b, "b", -0.08, 1.02)
    panel_title(ax_b, "M3KG entity schema")
    center = (0.5, 0.5)
    ax_b.add_patch(Circle(center, 0.12, transform=ax_b.transAxes, facecolor=COLORS["green"], edgecolor="none"))
    ax_b.text(*center, "MMP", transform=ax_b.transAxes, ha="center", va="center", color="white", fontsize=7, fontweight="bold")
    entities = [
        ("Taste", (0.18, 0.78), COLORS["orange"]),
        ("Nature", (0.50, 0.84), COLORS["magenta"]),
        ("Potency", (0.82, 0.76), COLORS["blue"]),
        ("Function", (0.82, 0.28), COLORS["green"]),
        ("Indication", (0.50, 0.15), COLORS["purple"]),
        ("Origin", (0.17, 0.28), COLORS["gray"]),
    ]
    for label, position, color in entities:
        ax_b.plot([center[0], position[0]], [center[1], position[1]], transform=ax_b.transAxes, color=COLORS["grid"], lw=1.0, zorder=0)
        ax_b.add_patch(Circle(position, 0.095, transform=ax_b.transAxes, facecolor=color, edgecolor="white", linewidth=0.8))
        ax_b.text(*position, label, transform=ax_b.transAxes, ha="center", va="center", color="white", fontsize=5.3, fontweight="bold")

    ax_c = fig.add_subplot(outer[0, 9:12])
    ax_c.set_axis_off()
    panel_label(ax_c, "c", -0.12, 1.02)
    panel_title(ax_c, "Prior knowledge-guided workflow")
    workflow = [
        ("Curation", "Traceable tables"),
        ("Ontology", "Typed entities"),
        ("Knowledge graph", "Evidence edges"),
        ("Explainable discovery", "Rules + paths"),
    ]
    y_values = [0.75, 0.54, 0.33, 0.12]
    fills = [COLORS["blue_light"], COLORS["purple_light"], COLORS["green_light"], COLORS["orange_light"]]
    edges = [COLORS["blue"], COLORS["purple"], COLORS["green"], COLORS["orange"]]
    for index, ((title, subtitle), y, fill, edge) in enumerate(zip(workflow, y_values, fills, edges)):
        add_box(ax_c, (0.08, y), 0.83, 0.14, f"{title}\n{subtitle}", fill, edge, fontsize=5.4, weight="bold")
        if index < len(workflow) - 1:
            add_arrow(ax_c, (0.50, y - 0.01), (0.50, y_values[index + 1] + 0.15), COLORS["gray"], width=0.8)

    ax_d = fig.add_subplot(outer[1, 0:5])
    panel_label(ax_d, "d", -0.10, 1.04)
    panel_title(ax_d, "Graph scale")
    relation_counts = (
        data["kg_edges"].groupby("predicate").size().reindex(PREDICATE_LABELS).fillna(0).astype(int)
    )
    labels = [PREDICATE_LABELS[value] for value in relation_counts.index]
    y = np.arange(len(labels))[::-1]
    bar_colors = [COLORS["orange"], COLORS["magenta"], COLORS["blue"], COLORS["green"], COLORS["purple"], COLORS["gray"]]
    ax_d.barh(y, relation_counts.values, color=bar_colors, height=0.62, zorder=2)
    ax_d.set_yticks(y, labels)
    ax_d.set_xlabel("Number of edges")
    clean_axis(ax_d, "x")
    for position, value in zip(y, relation_counts.values):
        ax_d.text(value + max(relation_counts.values) * 0.015, position, f"{value:,}", va="center", fontsize=5.2)
    ax_d.text(0.98, 0.98, "2,133 entities\n8,805 typed edges", transform=ax_d.transAxes, ha="right", va="top", fontsize=6, fontweight="bold", color=COLORS["ink"])

    ax_e = fig.add_subplot(outer[1, 5:12])
    ax_e.set_axis_off()
    panel_label(ax_e, "e", -0.04, 1.04)
    panel_title(ax_e, "Search and visualization web explorer")
    screenshot_path = ASSET_DIR / "website_overview_en.png"
    if screenshot_path.exists():
        image = plt.imread(screenshot_path)
        ax_e.imshow(image)
        ax_e.add_patch(Rectangle((0, 0), image.shape[1] - 1, image.shape[0] - 1, fill=False, edgecolor=COLORS["grid"], linewidth=0.8))
    else:
        add_box(ax_e, (0.08, 0.20), 0.84, 0.60, "M3KG web explorer\nSearch | filtering | graph visualization", COLORS["green_light"], COLORS["green"], fontsize=7, weight="bold")
    ax_e.set_xlim(0, image.shape[1] if screenshot_path.exists() else 1)
    ax_e.set_ylim(image.shape[0] if screenshot_path.exists() else 0, 0 if screenshot_path.exists() else 1)

    return save_figure(fig, 1, "Overall_design")


def _donut(ax: object, labels: list[str], values: list[float], title: str, colors: list[str]) -> None:
    wedges, _ = ax.pie(
        values,
        startangle=90,
        counterclock=False,
        colors=colors,
        wedgeprops={"width": 0.38, "edgecolor": "white", "linewidth": 0.7},
    )
    ax.text(0, 0.04, f"{int(sum(values))}", ha="center", va="center", fontsize=7, fontweight="bold")
    ax.text(0, -0.18, title, ha="center", va="center", fontsize=5.2, color=COLORS["gray"])
    ax.set_aspect("equal")


def figure2_data_landscape(results: dict[str, object]) -> dict[str, str]:
    coverage: pd.DataFrame = results["coverage"]
    source_summary: pd.DataFrame = results["source_summary"]
    taxonomy: dict[str, pd.DataFrame] = results["taxonomy"]
    qc_flags: pd.DataFrame = results["qc_flags"]
    fig = plt.figure(figsize=(183 / 25.4, 168 / 25.4))
    outer = gridspec.GridSpec(2, 12, figure=fig, hspace=0.46, wspace=1.32, height_ratios=[1, 1])

    ax_a = fig.add_subplot(outer[0, 0:6])
    panel_label(ax_a, "a", -0.08, 1.05)
    panel_title(ax_a, "Coverage across 558 medicinal pieces")
    columns = ["Taste", "Nature", "Potency", "Function", "Indication", "Origin"]
    matrix = coverage[columns].to_numpy(dtype=int)
    cmap = LinearSegmentedColormap.from_list("coverage", ["#F7F8FA", COLORS["green"]])
    ax_a.imshow(matrix, aspect="auto", interpolation="nearest", cmap=cmap, vmin=0, vmax=1)
    ax_a.set_xticks(np.arange(len(columns)), columns, rotation=35, ha="right")
    ax_a.set_yticks([])
    ax_a.set_ylabel("Medicinal pieces")
    for index, column in enumerate(columns):
        percent = coverage[column].mean() * 100
        ax_a.text(
            index,
            0.985,
            f"{percent:.1f}%",
            transform=ax_a.get_xaxis_transform(),
            ha="center",
            va="top",
            fontsize=4.7,
            fontweight="bold",
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.78, "pad": 0.7},
        )
    for spine in ax_a.spines.values():
        spine.set_visible(True)
        spine.set_linewidth(0.5)
        spine.set_color(COLORS["grid"])

    ax_b = fig.add_subplot(outer[0, 6:9])
    panel_label(ax_b, "b", -0.17, 1.05)
    panel_title(ax_b, "Source types")
    summary = source_summary.iloc[::-1]
    y = np.arange(len(summary))
    colors = [SOURCE_COLORS[value] for value in summary["source_type_text"]]
    ax_b.barh(y, summary["material_count"], color=colors, height=0.62, zorder=2)
    ax_b.set_yticks(y, summary["source_type_en"])
    ax_b.set_xlabel("Medicinal pieces")
    clean_axis(ax_b, "x")
    for position, value in zip(y, summary["material_count"]):
        ax_b.text(value + 6, position, str(int(value)), va="center", fontsize=5.3, fontweight="bold")
    ax_b.set_xlim(0, max(summary["material_count"]) * 1.18)

    ax_c = fig.add_subplot(outer[0, 9:12])
    panel_label(ax_c, "c", -0.17, 1.05)
    panel_title(ax_c, "Species-level taxonomy")
    kingdom = taxonomy["kingdom"].copy()
    kingdom["kingdom_short"] = kingdom["kingdom_name"].replace(
        {"Viridiplantae": "Plants", "Metazoa": "Animals", "Fungi": "Fungi"}
    )
    x = np.arange(len(kingdom))
    ax_c.bar(x - 0.17, kingdom["material_count"], width=0.34, color=COLORS["green"], label="MMPs")
    ax_c.bar(x + 0.17, kingdom["species_count"], width=0.34, color=COLORS["blue"], label="Species IDs")
    ax_c.set_xticks(x, kingdom["kingdom_short"], rotation=25, ha="right")
    ax_c.set_ylabel("Count")
    clean_axis(ax_c, "y")
    ax_c.legend(frameon=False, loc="upper right")
    ax_c.text(0.98, 0.82, "396/558 MMPs\nwith species IDs", transform=ax_c.transAxes, ha="right", fontsize=5.4, fontweight="bold")

    ax_d = fig.add_subplot(outer[1, 0:4])
    panel_label(ax_d, "d", -0.12, 1.05)
    panel_title(ax_d, "Dominant families and genera")
    family = taxonomy["family"].head(5)
    genus = taxonomy["genus"].head(5)
    family_values = family["material_count"].tolist() + [int(taxonomy["family"].iloc[5:]["material_count"].sum())]
    genus_values = genus["material_count"].tolist() + [int(taxonomy["genus"].iloc[5:]["material_count"].sum())]
    palette = [COLORS["green"], COLORS["blue"], COLORS["orange"], COLORS["purple"], COLORS["magenta"], COLORS["gray_light"]]
    inset_family = ax_d.inset_axes([0.00, 0.24, 0.53, 0.62])
    inset_genus = ax_d.inset_axes([0.47, 0.24, 0.53, 0.62])
    _donut(inset_family, [], family_values, "MMP-family links", palette)
    _donut(inset_genus, [], genus_values, "MMP-genus links", palette)
    ax_d.set_axis_off()
    family_text = "Families: " + ", ".join(f"{row.family_name} ({row.material_count})" for row in family.itertuples())
    genus_text = "Genera: " + ", ".join(f"{row.genus_name} ({row.material_count})" for row in genus.itertuples())
    ax_d.text(0.02, 0.12, textwrap.fill(family_text, 58), transform=ax_d.transAxes, fontsize=4.7, va="top")
    ax_d.text(0.02, -0.01, textwrap.fill(genus_text, 58), transform=ax_d.transAxes, fontsize=4.7, va="top")

    ax_e = fig.add_subplot(outer[1, 4:9])
    panel_label(ax_e, "e", -0.10, 1.05)
    panel_title(ax_e, "Multi-origin examples")
    examples = taxonomy["multi"][taxonomy["multi"]["label"].isin(["川贝母", "海马", "石决明", "钩藤"])].copy()
    display_names = {
        "川贝母": "Fritillaria bulb",
        "海马": "Seahorse",
        "石决明": "Abalone shell",
        "钩藤": "Uncaria hook",
    }
    examples["display"] = examples["label"].map(display_names)
    y = np.arange(len(examples))[::-1]
    ax_e.hlines(y, 0, examples["species_count"], color=COLORS["grid"], lw=2)
    ax_e.scatter(examples["species_count"], y, s=45, color=COLORS["green"], edgecolor="white", linewidth=0.6, zorder=3)
    ax_e.set_yticks(y, examples["display"])
    ax_e.set_xlabel("Accepted species-level origins")
    ax_e.set_xlim(0, 5.8)
    ax_e.set_ylim(-0.55, max(y) + 0.45)
    ax_e.set_xticks(range(0, 6))
    clean_axis(ax_e, "x")
    for position, row in zip(y, examples.itertuples()):
        species = ", ".join(name.split()[0] + " " + name.split()[1][0] + "." for name in row.species_names.split("; ") if len(name.split()) >= 2)
        ax_e.text(0.1, position - 0.30, species, fontsize=4.2, color=COLORS["gray"], va="top")

    ax_f = fig.add_subplot(outer[1, 9:12])
    panel_label(ax_f, "f", -0.17, 1.05)
    panel_title(ax_f, "Quality-control boundaries")
    qc_summary = (
        qc_flags.groupby("flag_type").size().reindex(
            [
                "Missing medicinal nature",
                "Source type requires manual review",
                "Property class-label conflict",
                "Missing species_ID",
            ]
        )
    )
    labels = ["Missing nature", "Source-type review", "Class-label conflict", "Missing species ID"]
    y = np.arange(len(labels))[::-1]
    values = qc_summary.to_numpy(dtype=int)
    ax_f.barh(y, values, color=[COLORS["red"], COLORS["red"], COLORS["magenta"], COLORS["gray"]], height=0.6)
    ax_f.set_yticks(y, labels)
    ax_f.set_xlabel("Flagged records/materials")
    ax_f.set_xscale("symlog", linthresh=2)
    ax_f.set_xticks([0, 1, 3, 10, 100], ["0", "1", "3", "10", "100"])
    clean_axis(ax_f, "x")
    for position, value in zip(y, values):
        ax_f.text(value * 1.14 if value else 0.1, position, str(value), va="center", fontsize=5.4, fontweight="bold")
    ax_f.text(0.02, 0.015, "Flags identify curation needs; no value was imputed.", transform=ax_f.transAxes, fontsize=4.2, color=COLORS["gray"], va="bottom")

    return save_figure(fig, 2, "Data_landscape_and_QC")


def confidence_ellipse(ax: object, x: np.ndarray, y: np.ndarray, color: str) -> None:
    if len(x) < 3:
        return
    covariance = np.cov(np.column_stack([x, y]), rowvar=False)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    order = np.argsort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[order]
    eigenvectors = eigenvectors[:, order]
    angle = math.degrees(math.atan2(eigenvectors[1, 0], eigenvectors[0, 0]))
    width, height = 2 * 1.65 * np.sqrt(np.maximum(eigenvalues, 0))
    ellipse = Ellipse(
        (float(np.mean(x)), float(np.mean(y))),
        width,
        height,
        angle=angle,
        facecolor=color,
        edgecolor=color,
        alpha=0.10,
        linewidth=0.8,
    )
    ax.add_patch(ellipse)


def figure3_property_space(results: dict[str, object]) -> dict[str, str]:
    tables: dict[str, object] = results["property_tables"]
    fig = plt.figure(figsize=(183 / 25.4, 168 / 25.4))
    outer = gridspec.GridSpec(2, 12, figure=fig, hspace=0.48, wspace=1.48)

    ax_a = fig.add_subplot(outer[0, 0:4])
    panel_label(ax_a, "a", -0.14, 1.05)
    panel_title(ax_a, "Taste distribution")
    taste_counts = tables["taste_counts"].sort_values("material_count")
    y = np.arange(len(taste_counts))
    ax_a.barh(y, taste_counts["material_count"], color=COLORS["orange"], height=0.65)
    ax_a.set_yticks(y, taste_counts["taste"])
    ax_a.set_xlabel("Medicinal pieces")
    clean_axis(ax_a, "x")
    for position, value in zip(y, taste_counts["material_count"]):
        ax_a.text(value + 4, position, str(int(value)), va="center", fontsize=4.8)
    ax_a.set_xlim(0, max(taste_counts["material_count"]) * 1.17)

    ax_b = fig.add_subplot(outer[0, 4:7])
    panel_label(ax_b, "b", -0.18, 1.05)
    panel_title(ax_b, "Thermal nature distribution")
    nature_counts = tables["nature_counts"].sort_values("material_count")
    nature_colors = {
        "Cold": COLORS["blue"],
        "Cool": "#80A4C0",
        "Neutral": COLORS["gray"],
        "Warm": "#EDB6A5",
        "Hot": COLORS["red"],
    }
    y = np.arange(len(nature_counts))
    ax_b.barh(y, nature_counts["material_count"], color=[nature_colors[value] for value in nature_counts["nature"]], height=0.64)
    ax_b.set_yticks(y, nature_counts["nature"])
    ax_b.set_xlabel("Medicinal pieces")
    clean_axis(ax_b, "x")
    for position, value in zip(y, nature_counts["material_count"]):
        ax_b.text(value + 4, position, str(int(value)), va="center", fontsize=4.8)

    ax_c = fig.add_subplot(outer[0, 7:12])
    panel_label(ax_c, "c", -0.11, 1.05)
    panel_title(ax_c, "Taste-nature combinations")
    combination: pd.DataFrame = tables["taste_nature_combination"]
    combination_cmap = LinearSegmentedColormap.from_list("taste_nature", SEQUENTIAL_COLORS)
    image = ax_c.imshow(combination.to_numpy(), cmap=combination_cmap, aspect="auto")
    ax_c.set_xticks(np.arange(len(combination.columns)), combination.columns, rotation=32, ha="right")
    ax_c.set_yticks(np.arange(len(combination.index)), combination.index)
    for row in range(combination.shape[0]):
        for column in range(combination.shape[1]):
            value = int(combination.iloc[row, column])
            if value >= 15:
                ax_c.text(column, row, str(value), ha="center", va="center", fontsize=4.5, color="white" if value > 65 else COLORS["ink"])
    colorbar = fig.colorbar(image, ax=ax_c, fraction=0.03, pad=0.02)
    colorbar.set_label("Co-occurring MMPs", fontsize=5.2)
    colorbar.ax.tick_params(labelsize=4.8)

    ax_d = fig.add_subplot(outer[1, 0:4])
    panel_label(ax_d, "d", -0.14, 1.05)
    panel_title(ax_d, "Potency co-occurrence")
    nodes_df: pd.DataFrame = tables["potency_nodes"]
    nodes_df = nodes_df.sort_values("material_count", ascending=False).head(10)
    nodes = nodes_df["potency"].tolist()
    edges_df: pd.DataFrame = tables["potency_edges"]
    edges_df = edges_df[edges_df["source"].isin(nodes) & edges_df["target"].isin(nodes)].head(30)
    edges = [(row.source, row.target, float(row.cooccurrence)) for row in edges_df.itertuples()]
    angles = np.linspace(math.pi / 2, math.pi / 2 + 2 * math.pi, len(nodes), endpoint=False)
    positions = {node: np.array([math.cos(angle), math.sin(angle)]) for node, angle in zip(nodes, angles)}
    max_edge = max([weight for _, _, weight in edges], default=1)
    for source, target, weight in edges:
        left, right = positions[source], positions[target]
        ax_d.plot([left[0], right[0]], [left[1], right[1]], color=COLORS["grid"], lw=0.35 + 1.2 * weight / max_edge, alpha=0.7, zorder=1)
    count_lookup = nodes_df.set_index("potency")["material_count"].to_dict()
    max_count = max(count_lookup.values())
    for node in nodes:
        position = positions[node]
        count = count_lookup[node]
        ax_d.scatter(position[0], position[1], s=10 + 75 * count / max_count, color=COLORS["blue"], edgecolor="white", linewidth=0.45, zorder=2)
        horizontal = "left" if position[0] >= 0 else "right"
        ax_d.text(position[0] * 1.10, position[1] * 1.10, node, ha=horizontal, va="center", fontsize=4.2, zorder=3)
    ax_d.set_xlim(-1.18, 1.18)
    ax_d.set_ylim(-1.18, 1.18)
    ax_d.set_axis_off()
    ax_d.text(0.02, -0.07, "Node size: prevalence; edge width: co-occurrence", transform=ax_d.transAxes, fontsize=4.5, color=COLORS["gray"])

    ax_e = fig.add_subplot(outer[1, 4:8])
    panel_label(ax_e, "e", -0.14, 1.05)
    panel_title(ax_e, "Source-specific properties")
    zscore: pd.DataFrame = tables["source_prevalence_zscore"].reindex(["Plant", "Animal", "Mineral", "Fungus"])
    source_cmap = LinearSegmentedColormap.from_list("source_property", DIVERGING_COLORS)
    heat = ax_e.imshow(zscore.to_numpy(), cmap=source_cmap, vmin=-2.2, vmax=2.2, aspect="auto")
    short_columns = [value.replace("Taste:", "T:").replace("Nature:", "N:").replace("Potency:", "P:") for value in zscore.columns]
    ax_e.set_xticks(np.arange(len(short_columns)), short_columns, rotation=58, ha="right")
    ax_e.set_yticks(np.arange(len(zscore.index)), zscore.index)
    ax_e.text(
        0.0,
        -0.34,
        "T, taste; N, nature; P, potency. z: -2 orange, +2 purple.",
        transform=ax_e.transAxes,
        fontsize=4.2,
        color=COLORS["gray"],
    )

    ax_f = fig.add_subplot(outer[1, 8:12])
    panel_label(ax_f, "f", -0.14, 1.05)
    pca: pd.DataFrame = tables["pca"]
    pc1 = float(pca["PC1_explained_variance"].iloc[0]) * 100
    pc2 = float(pca["PC2_explained_variance"].iloc[0]) * 100
    panel_title(ax_f, "Property-profile PCA")
    for source_type in ["植物", "动物", "矿物", "真菌"]:
        subset = pca[pca["source_type_text"] == source_type]
        color = SOURCE_COLORS[source_type]
        ax_f.scatter(subset["PC1"], subset["PC2"], s=7, color=color, alpha=0.55, edgecolor="none", label=SOURCE_ENGLISH[source_type])
        confidence_ellipse(ax_f, subset["PC1"].to_numpy(), subset["PC2"].to_numpy(), color)
    ax_f.set_xlabel(f"PC1 ({pc1:.1f}% variance)")
    ax_f.set_ylabel(f"PC2 ({pc2:.1f}% variance)", labelpad=1)
    clean_axis(ax_f, "both")
    ax_f.axhline(0, color=COLORS["grid"], lw=0.45, zorder=0)
    ax_f.axvline(0, color=COLORS["grid"], lw=0.45, zorder=0)
    ax_f.legend(frameon=False, ncol=2, loc="best", handletextpad=0.3, columnspacing=0.8)

    return save_figure(fig, 3, "Medicinal_property_space")


def find_rule(
    rules: pd.DataFrame, antecedent: str, consequent: str, relation: str
) -> pd.Series | None:
    match = rules[
        (rules["antecedent"] == antecedent)
        & (rules["consequent"] == consequent)
        & (rules["consequent_relation"] == relation)
    ]
    return None if match.empty else match.iloc[0]


def draw_rule_path(
    ax: object,
    nodes: list[tuple[str, str]],
    rule: pd.Series | None,
    subtitle: str,
) -> None:
    ax.set_axis_off()
    x_values = np.linspace(0.08, 0.92, len(nodes))
    for index, ((label, kind), x) in enumerate(zip(nodes, x_values)):
        color = {
            "taste": COLORS["orange"],
            "nature": COLORS["magenta"],
            "function": COLORS["green"],
            "indication": COLORS["purple"],
        }[kind]
        add_box(ax, (x - 0.105, 0.45), 0.21, 0.22, textwrap.fill(label, 15), "white", color, fontsize=4.6, weight="bold", radius=0.025)
        if index < len(nodes) - 1:
            add_arrow(ax, (x + 0.105, 0.56), (x_values[index + 1] - 0.105, 0.56), COLORS["gray"], width=0.8)
    ax.text(0.5, 0.29, subtitle, transform=ax.transAxes, ha="center", fontsize=5.0, color=COLORS["gray"])
    if rule is not None:
        ax.text(
            0.5,
            0.12,
            f"n={int(rule['joint_count'])}; support={rule['support']:.3f}\nconfidence={rule['confidence']:.3f}; lift={rule['lift']:.2f}",
            transform=ax.transAxes,
            ha="center",
            fontsize=4.8,
            fontweight="bold",
        )


def figure4_explainable_rules(results: dict[str, object]) -> dict[str, str]:
    rules: pd.DataFrame = results["rules"]
    permutations: pd.DataFrame = results["permutations"]
    fig = plt.figure(figsize=(183 / 25.4, 168 / 25.4))
    outer = gridspec.GridSpec(2, 12, figure=fig, hspace=0.47, wspace=1.28)

    ax_a = fig.add_subplot(outer[0, 0:5])
    panel_label(ax_a, "a", -0.10, 1.05)
    panel_title(ax_a, "Taste-nature-function-indication network")
    ax_a.set_axis_off()
    layers = {
        "Taste": (0.09, [("Bitter", COLORS["orange"]), ("Pungent", COLORS["orange"])]),
        "Nature": (0.34, [("Cold", COLORS["magenta"]), ("Hot", COLORS["magenta"])]),
        "Function": (
            0.64,
            [
                ("Heat-clearing", COLORS["green"]),
                ("Detoxifying", COLORS["green"]),
                ("Warming stomach", COLORS["green"]),
                ("Promoting digestion", COLORS["green"]),
            ],
        ),
        "Indication": (0.92, [("Toxic-heat syndrome", COLORS["purple"]), ("Indigestion", COLORS["purple"])]),
    }
    positions: dict[str, tuple[float, float]] = {}
    for layer, (x, items) in layers.items():
        y_values = np.linspace(0.74, 0.22, len(items))
        ax_a.text(x, 0.93, layer, transform=ax_a.transAxes, ha="center", va="bottom", fontsize=5.3, fontweight="bold")
        for (label, color), y in zip(items, y_values):
            positions[label] = (x, float(y))
            ax_a.add_patch(Circle((x, y), 0.048, transform=ax_a.transAxes, facecolor=color, edgecolor="white", linewidth=0.6, zorder=3))
            ax_a.text(x, y - 0.075, textwrap.fill(label, 14), transform=ax_a.transAxes, ha="center", va="top", fontsize=4.2)
    connections = [
        ("Bitter", "Cold", 46),
        ("Cold", "Heat-clearing", 37),
        ("Cold", "Detoxifying", 26),
        ("Heat-clearing", "Toxic-heat syndrome", 24),
        ("Detoxifying", "Toxic-heat syndrome", 21),
        ("Pungent", "Hot", 19),
        ("Hot", "Warming stomach", 15),
        ("Hot", "Promoting digestion", 7),
        ("Warming stomach", "Indigestion", 14),
        ("Promoting digestion", "Indigestion", 12),
    ]
    max_weight = max(weight for _, _, weight in connections)
    for source, target, weight in connections:
        start, end = positions[source], positions[target]
        ax_a.add_patch(
            FancyArrowPatch(
                start,
                end,
                transform=ax_a.transAxes,
                arrowstyle="-|>",
                mutation_scale=5,
                linewidth=0.45 + 1.5 * weight / max_weight,
                color=COLORS["grid"],
                connectionstyle="arc3,rad=0.02",
                zorder=1,
            )
        )
    ax_a.text(0.50, 0.02, "Edge width represents the number of supporting MMPs.", transform=ax_a.transAxes, ha="center", fontsize=4.4, color=COLORS["gray"])

    ax_b = fig.add_subplot(outer[0, 5:9])
    panel_label(ax_b, "b", -0.14, 1.05)
    panel_title(ax_b, "Association-rule landscape")
    plot_rules = rules[(rules["lift"] > 0) & np.isfinite(rules["lift"])].copy()
    plot_rules["x"] = np.log2(plot_rules["lift"])
    plot_rules["y"] = -np.log10(plot_rules["q_value"].clip(lower=1e-30))
    for relation, color, label in [
        ("HAS_FUNCTION", COLORS["green"], "Function"),
        ("TREATS_INDICATION", COLORS["purple"], "Indication"),
    ]:
        subset = plot_rules[plot_rules["consequent_relation"] == relation]
        ax_b.scatter(subset["x"], subset["y"], s=3 + 90 * subset["support"], color=color, alpha=0.35, edgecolor="none", label=label)
    ax_b.axvline(0, color=COLORS["gray"], lw=0.55)
    ax_b.axhline(-math.log10(0.05), color=COLORS["gray"], lw=0.55, linestyle="--")
    ax_b.set_xlabel("log2(lift)")
    ax_b.set_ylabel("-log10(FDR q-value)")
    clean_axis(ax_b, "both")
    ax_b.legend(frameon=False, loc="upper left")
    highlighted = plot_rules[
        ((plot_rules["antecedent"] == "Taste:苦 + Nature:寒") & (plot_rules["consequent"].isin(["清热", "解毒"])))
        | ((plot_rules["antecedent"] == "Taste:辛 + Nature:热") & (plot_rules["consequent"].isin(["温胃", "消化不良"])))
    ]
    short_annotations = {
        "清热": "Bitter+Cold -> Heat-clearing",
        "解毒": "Bitter+Cold -> Detoxifying",
        "温胃": "Pungent+Hot -> Warming stomach",
        "消化不良": "Pungent+Hot -> Indigestion",
    }
    for row in highlighted.itertuples():
        label = short_annotations.get(row.consequent, TERM_ENGLISH.get(row.consequent, row.consequent))
        align = "right" if row.x > 3 else "left"
        offset = (-3, 3) if align == "right" else (3, 3)
        ax_b.annotate(label, (row.x, row.y), xytext=offset, textcoords="offset points", fontsize=3.8, ha=align)

    ax_c = fig.add_subplot(outer[0, 9:12])
    panel_label(ax_c, "c", -0.17, 1.05)
    panel_title(ax_c, "Top interpretable rules")
    display = rules[
        rules["consequent"].isin(TERM_ENGLISH)
        & (rules["q_value"] < 0.05)
        & (rules["lift"] > 1)
        & (rules["joint_count"] >= 7)
    ].sort_values(["lift", "support"], ascending=[False, False]).drop_duplicates("rule_label_en").head(8).copy()
    display = display.sort_values("lift")
    y = np.arange(len(display))
    colors = [COLORS["green"] if value == "HAS_FUNCTION" else COLORS["purple"] for value in display["consequent_relation"]]
    ax_c.hlines(y, display["lift_ci_low"], display["lift_ci_high"], color=colors, lw=1.1)
    ax_c.scatter(display["lift"], y, s=16, color=colors, edgecolor="white", linewidth=0.45, zorder=3)
    labels = [
        value.replace("Pungent + Hot", "Pungent+Hot")
        .replace("Astringent + Cold", "Astringent+Cold")
        .replace("Sweet + Warm", "Sweet+Warm")
        .replace(" -> ", " -> ")
        for value in display["rule_label_en"]
    ]
    ax_c.set_yticks([])
    ax_c.set_xlabel("Lift (95% CI)")
    ax_c.axvline(1, color=COLORS["gray"], linestyle="--", lw=0.55)
    clean_axis(ax_c, "x")
    left_margin = -8.4
    right_limit = max(float(display["lift_ci_high"].max()) + 2.0, 12.0)
    ax_c.set_xlim(left_margin, right_limit)
    for position, (row, label) in enumerate(zip(display.itertuples(), labels)):
        ax_c.text(left_margin + 0.15, position, textwrap.fill(label, 25), ha="left", va="center", fontsize=3.8)
        ax_c.text(row.lift_ci_high + 0.15, position, f"c={row.confidence:.2f}\ns={row.support:.2f}", va="center", fontsize=4.0)

    ax_d = fig.add_subplot(outer[1, 0:4])
    panel_label(ax_d, "d", -0.14, 1.05)
    panel_title(ax_d, "Bitter-cold pathway")
    cold_heat = find_rule(rules, "Taste:苦 + Nature:寒", "清热", "HAS_FUNCTION")
    draw_rule_path(ax_d, [("Bitter", "taste"), ("Cold", "nature"), ("Heat-clearing", "function")], cold_heat, "A prior-knowledge path supported by co-occurrence")

    ax_e = fig.add_subplot(outer[1, 4:8])
    panel_label(ax_e, "e", -0.14, 1.05)
    panel_title(ax_e, "Pungent-hot pathway")
    hot_warm = find_rule(rules, "Taste:辛 + Nature:热", "温胃", "HAS_FUNCTION")
    draw_rule_path(ax_e, [("Pungent", "taste"), ("Hot", "nature"), ("Warming the stomach", "function")], hot_warm, "A high-lift gastrointestinal rule")

    ax_f = fig.add_subplot(outer[1, 8:12])
    panel_label(ax_f, "f", -0.14, 1.05)
    panel_title(ax_f, "Permutation-based robustness")
    if not permutations.empty:
        for label, color in zip(permutations["rule_label_en"].unique(), [COLORS["green"], COLORS["orange"]]):
            subset = permutations[permutations["rule_label_en"] == label]
            ax_f.hist(subset["null_lift"], bins=28, density=True, alpha=0.38, color=color, label=textwrap.fill(label, 28))
            observed = float(subset["observed_lift"].iloc[0])
            p_value = float(subset["permutation_p_value"].iloc[0])
            ax_f.axvline(observed, color=color, lw=1.4)
            ax_f.text(observed, ax_f.get_ylim()[1] * 0.78, f"Observed {observed:.2f}\nPperm={p_value:.3g}", color=COLORS["ink"], fontsize=4.5, rotation=90, va="top", ha="right")
    ax_f.set_xlabel("Lift after outcome-label permutation")
    ax_f.set_ylabel("Density")
    clean_axis(ax_f, "y")
    ax_f.legend(frameon=False, loc="upper right", fontsize=4.3)

    return save_figure(fig, 4, "Explainable_rules")


def figure5_graph_completion(results: dict[str, object]) -> dict[str, str]:
    benchmark: dict[str, object] = results["benchmark"]
    data: dict[str, pd.DataFrame] = results["data"]
    transactions: dict[str, object] = results["transactions"]
    rules: pd.DataFrame = results["rules"]
    metrics: pd.DataFrame = benchmark["metrics"]
    fig = plt.figure(figsize=(183 / 25.4, 166 / 25.4))
    outer = gridspec.GridSpec(2, 12, figure=fig, hspace=0.44, wspace=1.0)

    ax_a = fig.add_subplot(outer[0, 0:4])
    panel_label(ax_a, "a", -0.14, 1.05)
    panel_title(ax_a, "Stratified edge masking")
    ax_a.set_axis_off()
    split_totals = benchmark["split_counts"].groupby("split")["edge_count"].sum().reindex(["Train", "Validation", "Test"])
    total = int(split_totals.sum())
    labels = ["Train", "Validation", "Test"]
    colors = [COLORS["green"], COLORS["blue"], COLORS["orange"]]
    start = 0.04
    usable = 0.92
    for label, color in zip(labels, colors):
        width = usable * int(split_totals[label]) / total
        ax_a.add_patch(Rectangle((start, 0.56), width, 0.18, transform=ax_a.transAxes, facecolor=color, edgecolor="white", linewidth=0.8))
        if width > 0.1:
            ax_a.text(start + width / 2, 0.65, f"{label}\n{int(split_totals[label]):,}", transform=ax_a.transAxes, ha="center", va="center", color="white", fontsize=5.1, fontweight="bold")
        start += width
    add_box(ax_a, (0.10, 0.18), 0.80, 0.20, "Filtered tail ranking\nrelation-specific candidates", COLORS["gray_light"], COLORS["gray"], fontsize=5.4, weight="bold")
    add_arrow(ax_a, (0.50, 0.54), (0.50, 0.39), COLORS["gray"])
    ax_a.text(0.5, 0.03, "Split was stratified by relation type using seed 20260623.", transform=ax_a.transAxes, ha="center", fontsize=4.4, color=COLORS["gray"])

    ax_b = fig.add_subplot(outer[0, 4:8])
    panel_label(ax_b, "b", -0.14, 1.05)
    panel_title(ax_b, "Embedding and prior-guided models")
    ax_b.set_axis_off()
    models = [
        ("TransE", "-||h + r - t||2", COLORS["blue_light"], COLORS["blue"]),
        ("RotatE", "-||h o r - t||2", COLORS["purple_light"], COLORS["purple"]),
        ("ComplEx", "Re(<h, r, conj(t)>)", COLORS["orange_light"], COLORS["orange"]),
        ("Rule-enhanced KG", "z(KGE score) + alpha log(lift)", COLORS["green_light"], COLORS["green"]),
    ]
    y_values = [0.73, 0.51, 0.29, 0.07]
    for (name, formula, fill, edge), y in zip(models, y_values):
        add_box(ax_b, (0.07, y), 0.86, 0.16, f"{name}\n{formula}", fill, edge, fontsize=5.3, weight="bold")
    ax_b.text(0.5, -0.06, f"Prior model used {benchmark['best_model_name']} with alpha={benchmark['best_alpha']:.2f} selected on validation MRR.", transform=ax_b.transAxes, ha="center", fontsize=4.3, color=COLORS["gray"])

    ax_c = fig.add_subplot(outer[0, 8:12])
    panel_label(ax_c, "c", -0.14, 1.05)
    panel_title(ax_c, "Therapeutic-edge link prediction")
    metric_names = ["MRR", "Hits@1", "Hits@3", "Hits@10"]
    x = np.arange(len(metric_names))
    width = 0.18
    model_colors = [COLORS["blue"], COLORS["purple"], COLORS["orange"], COLORS["green"]]
    for index, row in enumerate(metrics.itertuples()):
        # itertuples renames Hits@ columns; positional access is stable in the exported metric table.
        values = [float(row[3]), float(row[4]), float(row[5]), float(row[6])]
        ax_c.bar(x + (index - 1.5) * width, values, width=width, color=model_colors[index], label=row.model)
    ax_c.set_xticks(x, metric_names)
    ax_c.set_ylabel("Filtered ranking score")
    ax_c.set_ylim(0, max(metrics[metric_names].to_numpy().max() * 1.25, 0.25))
    clean_axis(ax_c, "y")
    ax_c.legend(frameon=False, ncol=2, loc="upper left", fontsize=4.6, columnspacing=0.7, handlelength=1.1)
    prior_mrr = float(metrics.loc[metrics["model"] == "Rule-enhanced KG", "MRR"].iloc[0])
    base_mrr = float(metrics.loc[metrics["model"] == benchmark["best_model_name"], "MRR"].iloc[0])
    ax_c.text(0.98, 0.98, f"MRR improvement\n{(prior_mrr / base_mrr - 1) * 100:.1f}%", transform=ax_c.transAxes, ha="right", va="top", fontsize=5.2, fontweight="bold", color=COLORS["green"])

    ax_d = fig.add_subplot(outer[1, 0:4])
    panel_label(ax_d, "d", -0.14, 1.05)
    panel_title(ax_d, "Example explainable prediction")
    ax_d.set_axis_off()
    explainable = benchmark["explainable"]
    if not explainable.empty:
        row = explainable.iloc[0]
        for _, candidate_row in explainable.iterrows():
            candidate_tail = str(candidate_row["tail_entity"])
            candidate_match = data["kg_edges"].loc[
                data["kg_edges"]["object_id"] == candidate_tail, "object_label"
            ]
            if not candidate_match.empty and candidate_match.iloc[0] in TERM_ENGLISH:
                row = candidate_row
                break
        material_id = str(row["head_entity"]).split(":", 1)[-1]
        tail_entity = str(row["tail_entity"])
        tail_match = data["kg_edges"].loc[data["kg_edges"]["object_id"] == tail_entity, "object_label"]
        tail_label_original = tail_match.iloc[0] if not tail_match.empty else tail_entity
        tail_label = TERM_ENGLISH.get(tail_label_original, tail_entity.split(":", 1)[0])
        active_rules = rules[
            (rules["consequent"] == tail_label_original)
            & (rules["antecedent"].isin(
                [
                    *(f"Taste:{value}" for value in transactions["tastes"].get(material_id, set())),
                    *(f"Nature:{value}" for value in transactions["natures"].get(material_id, set())),
                    *(
                        f"Taste:{taste} + Nature:{nature}"
                        for taste in transactions["tastes"].get(material_id, set())
                        for nature in transactions["natures"].get(material_id, set())
                    ),
                ]
            ))
        ].sort_values("lift", ascending=False)
        antecedent = active_rules.iloc[0]["antecedent"] if not active_rules.empty else "Known properties"
        antecedent_en = rule_label(antecedent, tail_label_original).split(" -> ")[0]
        display_material = material_id
        draw_rule_path(
            ax_d,
            [(display_material, "taste"), (antecedent_en, "nature"), (tail_label, "function")],
            active_rules.iloc[0] if not active_rules.empty else None,
            f"Filtered rank: {int(row['rank_base'])} -> {int(row['rank_prior'])}",
        )
    else:
        add_box(ax_d, (0.12, 0.35), 0.76, 0.28, "No rank-improvement example available", COLORS["gray_light"], COLORS["gray"])

    ax_e = fig.add_subplot(outer[1, 4:8])
    panel_label(ax_e, "e", -0.14, 1.05)
    panel_title(ax_e, "Predicted nature for MMP0361 (Shajie)")
    predictions = benchmark["nature_predictions"].head(5).sort_values("weighted_vote_probability")
    y = np.arange(len(predictions))
    ax_e.barh(y, predictions["weighted_vote_probability"], color=COLORS["blue"], height=0.6)
    ax_e.set_yticks(y, predictions["predicted_nature"])
    ax_e.set_xlabel("Weighted nearest-neighbour vote")
    ax_e.set_xlim(0, max(predictions["weighted_vote_probability"].max() * 1.25, 0.1))
    clean_axis(ax_e, "x")
    for position, value in zip(y, predictions["weighted_vote_probability"]):
        ax_e.text(value + 0.01, position, f"{value:.2f}", va="center", fontsize=5.0)
    ax_e.text(0.0, 0.015, "Hypothesis only: D4 contains no observed nature for MMP0361.", transform=ax_e.transAxes, fontsize=4.2, color=COLORS["red"], va="bottom")

    ax_f = fig.add_subplot(outer[1, 8:12])
    panel_label(ax_f, "f", -0.14, 1.05)
    panel_title(ax_f, "Expert-review workflow")
    ax_f.set_axis_off()
    steps = [
        ("Masked or missing edge", COLORS["gray_light"], COLORS["gray"]),
        ("Model rank + rule path", COLORS["blue_light"], COLORS["blue"]),
        ("Source-text verification", COLORS["orange_light"], COLORS["orange"]),
        ("Expert decision", COLORS["green_light"], COLORS["green"]),
    ]
    y_values = [0.74, 0.53, 0.32, 0.11]
    for index, ((label, fill, edge), y) in enumerate(zip(steps, y_values)):
        add_box(ax_f, (0.12, y), 0.76, 0.14, label, fill, edge, fontsize=5.4, weight="bold")
        if index < len(steps) - 1:
            add_arrow(ax_f, (0.50, y - 0.01), (0.50, y_values[index + 1] + 0.15), COLORS["gray"])
    ax_f.text(0.5, -0.02, "Predictions are not written back to the curated tables without review.", transform=ax_f.transAxes, ha="center", fontsize=4.4, color=COLORS["gray"])

    return save_figure(fig, 5, "Prior_guided_graph_completion")


def figure6_validation_case_study(results: dict[str, object]) -> dict[str, str]:
    candidates: pd.DataFrame = results["candidates"].head(10).copy()
    fig = plt.figure(figsize=(183 / 25.4, 166 / 25.4))
    outer = gridspec.GridSpec(2, 12, figure=fig, hspace=0.48, wspace=1.05)

    ax_a = fig.add_subplot(outer[0, 0:5])
    panel_label(ax_a, "a", -0.10, 1.05)
    panel_title(ax_a, "Plant-derived candidate prioritization")
    candidates = candidates.sort_values(["score", "material_id"])
    y = np.arange(len(candidates))
    ax_a.barh(y, candidates["score"], color=COLORS["green"], height=0.62)
    labels = [textwrap.shorten(value, width=25, placeholder="...") for value in candidates["display_name"]]
    ax_a.set_yticks(y, labels, style="italic")
    ax_a.set_xlabel("Prior-knowledge score")
    clean_axis(ax_a, "x")
    for position, row in zip(y, candidates.itertuples()):
        ax_a.text(
            row.score + 0.04,
            position,
            f"{row.material_id} · {row.score:.2f}",
            va="center",
            fontsize=4.15,
            color=COLORS["gray"],
        )
    ax_a.set_xlim(0, candidates["score"].max() * 1.22)

    ax_b = fig.add_subplot(outer[0, 5:9])
    panel_label(ax_b, "b", -0.14, 1.05)
    panel_title(ax_b, "Candidate-to-mechanism evidence layer")
    ax_b.set_axis_off()
    chain = [
        ("Prioritized MMPs", COLORS["green"]),
        ("Phytochemicals", COLORS["orange"]),
        ("Targets", COLORS["blue"]),
        ("Inflammatory diseases", COLORS["purple"]),
    ]
    x_values = np.linspace(0.10, 0.90, len(chain))
    for index, ((label, color), x) in enumerate(zip(chain, x_values)):
        ax_b.add_patch(Circle((x, 0.57), 0.075, transform=ax_b.transAxes, facecolor=color, edgecolor="white", linewidth=0.7))
        ax_b.text(x, 0.41, textwrap.fill(label, 15), transform=ax_b.transAxes, ha="center", fontsize=4.7)
        if index < len(chain) - 1:
            add_arrow(ax_b, (x + 0.075, 0.57), (x_values[index + 1] - 0.075, 0.57), COLORS["gray"], dashed=True)
    add_box(ax_b, (0.12, 0.08), 0.76, 0.18, "External compound-target data required\nNo mechanistic edge is claimed", COLORS["gray_light"], COLORS["gray"], fontsize=5.0, weight="bold")

    ax_c = fig.add_subplot(outer[0, 9:12])
    panel_label(ax_c, "c", -0.17, 1.05)
    panel_title(ax_c, "Planned GO/KEGG enrichment")
    ax_c.set_axis_off()
    terms = ["Inflammatory response", "NF-kappa B signalling", "Cytokine signalling", "Oxidative stress"]
    y_values = np.linspace(0.73, 0.28, len(terms))
    for index, (label, y) in enumerate(zip(terms, y_values)):
        ax_c.hlines(y, 0.55, 0.94, transform=ax_c.transAxes, color=COLORS["grid"], lw=0.7)
        ax_c.scatter(0.58 + index * 0.10, y, transform=ax_c.transAxes, s=18 + index * 10, color=COLORS["gray"], alpha=0.45)
        ax_c.text(0.02, y, textwrap.fill(label, 21), transform=ax_c.transAxes, va="center", fontsize=4.4)
    ax_c.text(0.50, 0.08, "Design schematic - target list unavailable", transform=ax_c.transAxes, ha="center", fontsize=5.0, fontweight="bold", color=COLORS["red"])

    ax_d = fig.add_subplot(outer[1, 0:4])
    panel_label(ax_d, "d", -0.14, 1.05)
    panel_title(ax_d, "Mechanistic validation options")
    ax_d.set_axis_off()
    add_box(ax_d, (0.05, 0.54), 0.40, 0.27, "Docking\ncompound-target", COLORS["blue_light"], COLORS["blue"], fontsize=5.0, weight="bold")
    add_box(ax_d, (0.55, 0.54), 0.40, 0.27, "Transcriptomic\nreversal", COLORS["purple_light"], COLORS["purple"], fontsize=5.0, weight="bold")
    add_arrow(ax_d, (0.25, 0.52), (0.50, 0.29), COLORS["gray"])
    add_arrow(ax_d, (0.75, 0.52), (0.50, 0.29), COLORS["gray"])
    add_box(ax_d, (0.25, 0.12), 0.50, 0.16, "Select one preregistered route\nNo result generated", COLORS["gray_light"], COLORS["gray"], fontsize=5.0, weight="bold")

    ax_e = fig.add_subplot(outer[1, 4:8])
    panel_label(ax_e, "e", -0.14, 1.05)
    panel_title(ax_e, "Prospective anti-inflammatory assay")
    ax_e.set_axis_off()
    steps = [
        ("LPS-stimulated macrophages", COLORS["orange_light"], COLORS["orange"]),
        ("Candidate extract or compound", COLORS["green_light"], COLORS["green"]),
        ("Readouts: NO, TNF-alpha, IL-6, IL-1beta", COLORS["blue_light"], COLORS["blue"]),
    ]
    y_values = [0.71, 0.47, 0.23]
    for index, ((label, fill, edge), y) in enumerate(zip(steps, y_values)):
        add_box(ax_e, (0.13, y), 0.74, 0.15, textwrap.fill(label, 34), fill, edge, fontsize=4.8, weight="bold")
        if index < len(steps) - 1:
            add_arrow(ax_e, (0.50, y - 0.01), (0.50, y_values[index + 1] + 0.16), COLORS["gray"])
    ax_e.text(0.50, 0.10, "Replicates, dose-response and positive controls required", transform=ax_e.transAxes, ha="center", fontsize=4.4)
    ax_e.text(0.50, 0.01, "Prospective design - no experimental measurement", transform=ax_e.transAxes, ha="center", fontsize=4.5, fontweight="bold", color=COLORS["red"], va="bottom")

    ax_f = fig.add_subplot(outer[1, 8:12])
    panel_label(ax_f, "f", -0.14, 1.05)
    panel_title(ax_f, "Evidence loop from theory to mechanism")
    ax_f.set_axis_off()
    center = (0.50, 0.50)
    loop_nodes = [
        ("Mongolian theory", (0.50, 0.84), COLORS["orange"]),
        ("M3KG rule", (0.84, 0.57), COLORS["green"]),
        ("Mechanistic hypothesis", (0.69, 0.16), COLORS["blue"]),
        ("Experimental evidence", (0.31, 0.16), COLORS["purple"]),
        ("Curated update", (0.16, 0.57), COLORS["gray"]),
    ]
    for label, position, color in loop_nodes:
        ax_f.add_patch(Circle(position, 0.075, transform=ax_f.transAxes, facecolor=color, edgecolor="white", linewidth=0.7, zorder=3))
        ax_f.text(position[0], position[1] - 0.11, textwrap.fill(label, 16), transform=ax_f.transAxes, ha="center", va="top", fontsize=4.5)
    for index in range(len(loop_nodes)):
        start = loop_nodes[index][1]
        end = loop_nodes[(index + 1) % len(loop_nodes)][1]
        ax_f.add_patch(FancyArrowPatch(start, end, transform=ax_f.transAxes, arrowstyle="-|>", mutation_scale=5, linewidth=0.8, color=COLORS["grid"], connectionstyle="arc3,rad=-0.15"))
    ax_f.text(*center, "Traceable\nevidence", transform=ax_f.transAxes, ha="center", va="center", fontsize=6, fontweight="bold", color=COLORS["ink"])

    return save_figure(fig, 6, "Phytomedicine_validation_design")


def write_manuscript_documentation(
    results: dict[str, object], figure_outputs: dict[int, dict[str, str]]
) -> None:
    metrics = results["benchmark"]["metrics"].set_index("model")
    source_summary = results["source_summary"].set_index("source_type_en")
    qc_summary = results["qc_flags"].groupby("flag_type").size()
    cold_heat = find_rule(results["rules"], "Taste:苦 + Nature:寒", "清热", "HAS_FUNCTION")
    hot_warm = find_rule(results["rules"], "Taste:辛 + Nature:热", "温胃", "HAS_FUNCTION")

    legends = f"""# M3KG Figure Legends

**Figure 1 | Overall design of M3KG.** a, Structure and record counts of the six curated data modules: terminology (D1), Mongolian medicinal pieces (D2), MMP-to-terminology mappings (D3), medicinal properties (D4), pharmacognostic origins (D5) and MMP-to-origin mappings (D6). b, Typed entity schema linking Mongolian medicinal pieces (MMPs) to taste, nature, potency, function, indication and origin entities. c, Prior knowledge-guided workflow from curation and ontology construction to the knowledge graph and explainable discovery. d, Numbers of typed edges by relation; the current graph contains 2,133 entities and 8,805 edges. e, Screenshot of the M3KG web explorer showing search, structured filtering and evidence display. This figure summarizes the construction of M3KG and its prior knowledge-guided discovery workflow for Mongolian medicinal pieces.

**Figure 2 | Data landscape and quality-control boundaries.** a, Binary coverage matrix for taste, nature, potency, function, indication and origin across 558 medicinal pieces; percentages denote field-level completeness. b, Pharmacognostic source types assigned to medicinal pieces: {int(source_summary.loc['Plant', 'material_count'])} plant, {int(source_summary.loc['Animal', 'material_count'])} animal, {int(source_summary.loc['Mineral', 'material_count'])} mineral and {int(source_summary.loc['Fungus', 'material_count'])} fungal materials. c, Species-level taxonomic coverage for plant, animal and fungal origins; 396 of 558 medicinal pieces have at least one species identifier. d, Distribution of the most frequent taxonomic families and genera; the residual category is grouped as other. e, Four multi-origin examples, each linked to five accepted species-level origins: Fritillaria bulb, seahorse, abalone shell and Uncaria hook. f, Quality-control flags comprising {int(qc_summary.get('Missing medicinal nature', 0))} missing nature record, {int(qc_summary.get('Source type requires manual review', 0))} source-type labels requiring review, {int(qc_summary.get('Property class-label conflict', 0))} property class-label conflicts and {int(qc_summary.get('Missing species_ID', 0))} materials without species identifiers. Flags are curation boundaries and were not treated as imputed observations. This figure evaluates completeness, taxonomic coverage and quality-control boundaries of the curated M3KG dataset.

**Figure 3 | Medicinal-property space of Mongolian medicines.** a, Frequency of canonicalized taste categories. Prefixes indicating mild intensity were merged with their parent taste, whereas class-label conflicts were excluded and retained in the quality-control table. b, Distribution of canonicalized thermal nature categories; mild cold and mild warm were merged with cold and warm, respectively. c, Heat map of taste-nature co-occurrence counts. d, Potency-feature co-occurrence network; node area represents the number of medicinal pieces and edge width represents within-piece co-occurrence. e, Source-specific property prevalence expressed as a feature-wise z-score across plant, animal, mineral and fungal materials. f, Principal-component analysis of one-hot encoded taste, nature and potency profiles. Points are medicinal pieces and shaded ellipses summarize approximately 80% covariance regions for each source type. This figure shows how traditional medicinal properties form a structured and quantifiable property space.

**Figure 4 | Explainable links from taste and nature to function and indication.** a, Four-layer network illustrating selected taste-nature-function-indication paths; edge width denotes the number of supporting medicinal pieces. b, Association-rule landscape; the x axis is log2 lift, the y axis is the negative log10 Benjamini-Hochberg-adjusted one-sided Fisher enrichment P value, and point size denotes support. c, Top interpretable rules with lift and approximate 95% confidence intervals; c and s denote confidence and support. d, Bitter plus cold to heat-clearing path ({'n=' + str(int(cold_heat['joint_count'])) + ', confidence=' + format(cold_heat['confidence'], '.3f') + ', lift=' + format(cold_heat['lift'], '.2f') if cold_heat is not None else 'rule unavailable'}). e, Pungent plus hot to warming-the-stomach path ({'n=' + str(int(hot_warm['joint_count'])) + ', confidence=' + format(hot_warm['confidence'], '.3f') + ', lift=' + format(hot_warm['lift'], '.2f') if hot_warm is not None else 'rule unavailable'}). f, Null lift distributions from 1,000 outcome-label permutations; vertical lines indicate observed lifts and Pperm is the empirical permutation P value. This figure demonstrates interpretable prior knowledge rules linking medicinal properties to therapeutic functions and clinical indications.

**Figure 5 | Prior knowledge-guided graph completion and prediction.** a, Relation-stratified 80:10:10 edge split and filtered, relation-specific tail ranking. b, Compared scoring models: TransE, RotatE, ComplEx and a rule-enhanced model combining standardized embedding scores with log lift from applicable taste and nature rules. c, Mean reciprocal rank (MRR) and Hits at 1, 3 and 10 for 598 held-out function and indication edges. The best embedding baseline was {results['benchmark']['best_model_name']} (MRR={metrics.loc[results['benchmark']['best_model_name'], 'MRR']:.3f}); the prior-guided model achieved MRR={metrics.loc['Rule-enhanced KG', 'MRR']:.3f} and Hits@10={metrics.loc['Rule-enhanced KG', 'Hits@10']:.3f}. d, Example in which an applicable medicinal-property rule improves the filtered rank of a held-out therapeutic edge. e, Weighted nearest-neighbour prediction of the missing nature for MMP0361 (Shajie); this is a hypothesis for expert review and is not a ground-truth value. f, Expert-review workflow required before predicted edges can enter the curated tables. This figure evaluates whether prior knowledge constraints improve graph completion and explainable inference.

**Figure 6 | Phytomedicine-oriented validation case-study design.** a, Ranking of plant-derived candidates using a prespecified score integrating bitter taste, cold or cool nature, heat-clearing and detoxifying functions, inflammation-related indications, species-level traceability and a small log-scaled therapeutic-evidence breadth bonus. b, Planned integration of candidates with compounds, targets and inflammatory diseases; these external data are not present in D1-D6 and no mechanistic edge is claimed. c, Prospective GO and KEGG enrichment design requiring a validated target list. d, Alternative prospective routes for molecular docking or transcriptomic reversal. e, Proposed anti-inflammatory validation in lipopolysaccharide-stimulated macrophages with nitric oxide, tumour necrosis factor-alpha, interleukin-6 and interleukin-1beta readouts. f, Evidence loop from Mongolian medicine theory through M3KG rules and mechanistic hypotheses to experimental evidence and curated updates. Panels b-e are study-design schematics rather than experimental results. This figure translates M3KG-derived property rules into experimentally testable phytopharmacological hypotheses.
"""
    (OUTPUT_ROOT / "M3KG_Figure_legends.md").write_text(legends, encoding="utf-8")

    methods = f"""# Reproducible Figure Methods and Data Notes

## Scope

All quantitative panels were generated from the frozen D1-D6 files in `source_snapshot` and `data/m3kg_curated_20260623.sqlite`. The source snapshot contains 558 Mongolian medicinal pieces, 1,132 terminology records, 2,362 medicinal-property records, 390 pharmacognostic-origin units, 468 MMP-origin mappings and 8,805 typed graph edges. Figure 6b-e contains prospective study designs because compound, target, docking, transcriptomic and wet-laboratory data were not available.

## Figure specification

Figures were assembled on 183-mm-wide canvases with heights no greater than 170 mm and exported with tight bounding boxes; every final PDF page remains within the 183 mm × 170 mm limit. Editable PDF and SVG files retain text and vector objects. Fonts are embedded as TrueType Type 42 where supported. Body lettering is 5-7 pt and panel labels are 8 pt bold. A reference-derived editorial palette is used consistently across the figure set: taste, cyan (`#53ABBC`); nature, magenta (`#913176`); potency, indigo (`#384F8E`); function and M3KG, navy (`#263963`); indication, violet (`#675A8E`); and origin, cool slate (`#737A86`). Continuous maps follow navy-blue or magenta-white-navy scales, rainbow scales are avoided, and colour is paired with labels, position or shape. These settings follow the Nature research figure guide: https://research-figure-guide.nature.com/figures/building-and-exporting-figure-panels/

## Property normalization

Mild taste or nature modifiers were collapsed into their parent category (for example, mild bitter to bitter; mild warm to warm). Three records labelled cold or cool within the medicinal-flavour class were excluded from canonical taste summaries and retained in the QC table. PCA was calculated by centring the binary taste-nature-potency matrix and applying singular-value decomposition; no UMAP result is reported because UMAP was not required to answer the panel question.

## Association rules

Antecedents comprised one taste, one nature, or a taste-nature pair. Consequents were therapeutic functions or clinical indications. Rules required at least five joint supporting medicinal pieces. Support, confidence and lift follow the definitions used by mlxtend association rules (https://rasbt.github.io/mlxtend/user_guide/frequent_patterns/association_rules/). Enrichment P values were computed with the upper-tail hypergeometric distribution and adjusted with the Benjamini-Hochberg procedure. The displayed confidence interval is an approximate log-lift interval. Robustness was evaluated with 1,000 outcome-label permutations using seed {RANDOM_SEED}.

## Network layout

The potency co-occurrence network uses a deterministic circular layout for label legibility; display coordinates do not affect statistical results. A deterministic Fruchterman-Reingold-style implementation, cross-checked against the NetworkX spring-layout documentation (https://networkx.org/documentation/stable/reference/generated/networkx.drawing.layout.spring_layout.html), is retained in the reproducible pipeline for exploratory network layouts.

## Knowledge-graph completion

Edges were split 80:10:10 within each relation using seed {RANDOM_SEED}. TransE, RotatE and ComplEx scoring functions were independently implemented in NumPy with 32-dimensional embeddings and relation-specific tail corruption. Model definitions and naming were cross-checked against PyKEEN (https://github.com/pykeen/pykeen); PyKEEN was not a runtime dependency. Evaluation used filtered ranks and relation-specific candidate tails. Reported metrics are restricted to held-out function and indication edges (n=598). A rule-enhanced score combined a standardized score from the validation-selected baseline ({results['benchmark']['best_model_name']}) with applicable rule log-lift; alpha={results['benchmark']['best_alpha']:.2f} was selected on validation MRR.

## Candidate prioritization and experimental boundary

Figure 6a used a transparent heuristic score: bitter taste (1 point), cold or cool nature (1 point), heat-clearing function (2 points), detoxifying function (2 points), up to three inflammation-related indication matches (0.35 points each), a species identifier (0.5 points), and a small therapeutic-evidence breadth bonus calculated as 0.12 × ln(1 + number of function and indication edges). It is a hypothesis-prioritization score, not evidence of efficacy. Figure 6b-e must be replaced or supplemented with independently generated compound, target, enrichment, docking/transcriptomic and biological replicate data before the figure is presented as a validation result.

## Software references

- NumPy and Pandas were used for data transformation and matrix computations.
- Matplotlib generated editable PDF/SVG artwork.
- The UMAP reference repository was reviewed but UMAP was not used: https://github.com/lmcinnes/umap
- scikit-learn's PCA interface was reviewed for naming consistency, although PCA was computed directly by SVD: https://github.com/scikit-learn/scikit-learn
- All generated CSV files use UTF-8 with a byte-order mark for compatibility with Excel and retain original Chinese labels where necessary for auditability.
"""
    (OUTPUT_ROOT / "METHODS_AND_DATA_NOTES.md").write_text(methods, encoding="utf-8")

    readme = """# M3KG manuscript figure package

This directory contains six editable manuscript figures, panel-level source data, a frozen D1-D6 source snapshot, legends and reproducibility notes.

## Submission boundary

Figures 1-5 contain analyses computed from the current dataset. Figure 6a is a transparent candidate-ranking analysis. Figure 6b-e is explicitly prospective and must not be described as experimental evidence until the required external and laboratory data have been generated.

## Directory map

- `figures/`: editable PDF and SVG files plus 300-dpi PNG previews.
- `source_data/figure1` to `source_data/figure6`: panel-specific analysis tables.
- `source_snapshot/`: unmodified D1-D6 TSV files and the restored origin workbook.
- `assets/`: the English web-explorer screenshot used in Figure 1e.
- `scripts/`: the reproducible analysis and figure-generation pipeline.
- `M3KG_Figure_legends.md`: manuscript-ready English legends.
- `METHODS_AND_DATA_NOTES.md`: methods, assumptions, QC boundaries and software references.
"""
    (OUTPUT_ROOT / "README.md").write_text(readme, encoding="utf-8")

    manifest_rows = []
    for number, outputs in sorted(figure_outputs.items()):
        for file_type, path in outputs.items():
            target = Path(path)
            manifest_rows.append(
                {
                    "figure": number,
                    "format": file_type.upper(),
                    "path": str(target.relative_to(OUTPUT_ROOT)),
                    "bytes": target.stat().st_size,
                    "editable_vector": int(file_type in {"pdf", "svg"}),
                }
            )
    write_csv(pd.DataFrame.from_records(manifest_rows), OUTPUT_ROOT / "figure_manifest.csv")
    parameters = {
        "random_seed": RANDOM_SEED,
        "figure_width_mm": 183,
        "maximum_figure_height_mm": 170,
        "association_rule_min_joint_count": 5,
        "permutations": 1000,
        "kg_embedding_dimension": 32,
        "kg_split": {"train": 0.8, "validation": 0.1, "test": 0.1},
        "kg_evaluation_scope": "HAS_FUNCTION and TREATS_INDICATION",
        "figure6_experimental_status": "Not performed; prospective design only",
        "color_palette": {
            "taste": COLORS["orange"],
            "nature": COLORS["magenta"],
            "potency": COLORS["blue"],
            "function_and_m3kg": COLORS["green"],
            "indication": COLORS["purple"],
            "origin": COLORS["gray"],
            "warning": COLORS["red"],
            "sequential": SEQUENTIAL_COLORS,
            "diverging": DIVERGING_COLORS,
        },
    }
    (OUTPUT_ROOT / "analysis_parameters.json").write_text(
        json.dumps(parameters, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUTPUT_ROOT / "software_environment.json").write_text(
        json.dumps(audit_environment(), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def generate_all(use_cache: bool = False) -> dict[int, dict[str, str]]:
    configure_matplotlib()
    if use_cache:
        if not ANALYSIS_CACHE.exists():
            raise FileNotFoundError(f"Analysis cache not found: {ANALYSIS_CACHE}")
        with ANALYSIS_CACHE.open("rb") as handle:
            results = pickle.load(handle)
    else:
        results = run_analysis(export_tables=True)
    outputs = {
        1: figure1_overall_design(results),
        2: figure2_data_landscape(results),
        3: figure3_property_space(results),
        4: figure4_explainable_rules(results),
        5: figure5_graph_completion(results),
        6: figure6_validation_case_study(results),
    }
    write_manuscript_documentation(results, outputs)
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Build manuscript figures and supporting data for M3KG.")
    parser.add_argument("--audit", action="store_true", help="Print the data/software audit and exit.")
    parser.add_argument("--profile", action="store_true", help="Print a compact data profile and exit.")
    parser.add_argument("--analysis-only", action="store_true", help="Run analyses and export panel data, but do not draw figures.")
    parser.add_argument("--render-only", action="store_true", help="Redraw figures from the most recent analysis cache.")
    args = parser.parse_args()

    if args.audit:
        print(json.dumps(audit_environment(), ensure_ascii=False, indent=2))
        return
    if args.profile:
        print(json.dumps(profile_data(), ensure_ascii=False, indent=2))
        return

    if args.analysis_only:
        results = run_analysis(export_tables=True)
        print(results["benchmark"]["metrics"].to_string(index=False))
        print("\nTop candidates:")
        print(results["candidates"].head(10)[["material_id", "display_name", "score"]].to_string(index=False))
        return
    outputs = generate_all(use_cache=args.render_only)
    print(json.dumps(outputs, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
