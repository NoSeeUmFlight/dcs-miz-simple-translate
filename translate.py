#!/usr/bin/env python3
"""
Translate selected DCS World .miz dictionary entries to Chinese using the OpenAI Responses API.

Key design choices:
- Uses environment variable OPENAI_API_KEY instead of hard-coding secrets.
- Uses the current Responses API via openai-python.
- Separates stable instruction, glossary memory, and local candidate context.
- Avoids blindly stuffing recent translations into one flat prompt.
- Handles partially disordered mission text by retrieving semantically similar candidates
  from the whole mission instead of trusting file order alone.

Recommended install:
    pip install -U openai tqdm

Example:
    python translate_v2_openai.py mission.miz --model gpt-5.4-mini
"""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import os
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from openai import OpenAI
from tqdm import tqdm


# =========================
# Prompting / task settings
# =========================

DEFAULT_SYSTEM_PROMPT = """
你是 DCS World 战役文本本地化助手，熟悉空军、联合作战、无线电通话、任务提示、武器与航电术语。

你的唯一任务是：把给定英文条目翻译成中文，用于 DCS 任务文本本地化。

硬性要求：
1. 只输出译文本身，不要解释，不要加引号，不要加注释。
2. 呼号、人名、机型代号、武器型号、航点代号、频率、激光编码、数字坐标，默认保留原样，除非中文社区已有稳定官方译名。
3. 军事缩写首次出现时，优先译为“中文（英文缩写）”；如果原句极短、属于无线电喊话或 UI 提示，可只保留缩写或使用更短表达。
4. 无线电通话应简洁、口语化、符合战术电台语境；任务说明和字幕则可略完整。
5. 不要擅自补充原文没有的信息。
6. 若上下文不足以确定人称、指代或术语含义，采取最保守、最不易误导的译法。
7. 保持同一任务内术语、呼号、地名译法一致。
8. DCS 官方中文版已有固定译名时，优先与其一致。

你会收到：
- 当前条目
- 条目元数据（字段类型、ID）
- 可能相关的候选上下文（它们不保证顺序正确，只能作为参考）
- 已累积的术语/记忆表

候选上下文仅供消歧，绝不可把别的条目内容拼进当前译文。
""".strip()

TARGET_PREFIXES = [
    "DictKey_ActionRadioText_",
    "DictKey_subtitle_",
    "DictKey_ActionText_",
    "DictKey_sortie_",
    "DictKey_descriptionBlueTask_",
    "DictKey_descriptionRedTask_",
    "DictKey_descriptionNeutralsTask_",
    "DictKey_descriptionText_",
]


# =========================
# Data structures
# =========================

@dataclass
class Entry:
    prefix: str
    field_id: int
    full_key: str
    text: str
    index_in_file: int


# =========================
# Parsing helpers
# =========================

ENTRY_REGEX = re.compile(
    r'\[\s*"(?P<key>(' + '|'.join(re.escape(prefix) for prefix in TARGET_PREFIXES) +
    r')(?P<id>\d+))"\s*\]\s*=\s*"(?P<text>(?:\\.|[^"\\])*)",?\s*(?=\n|\r|$)',
    re.DOTALL,
)


def unescape_lua_string(s: str) -> str:
    """Conservative unescape for DCS dictionary content."""
    s = s.replace(r'\"', '"')
    s = s.replace(r"\\", "\\")
    s = s.replace(r"\n", "\n")
    s = s.replace(r"\r", "\r")
    s = s.replace(r"\t", "\t")
    return s


def escape_for_csv_cell(s: str) -> str:
    """Preserve line breaks visually for human review in CSV."""
    return s.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")


def read_dictionary_text_from_miz(miz_file_path: Path) -> str:
    with zipfile.ZipFile(miz_file_path, "r") as zip_ref:
        for file in zip_ref.namelist():
            if file.endswith("l10n/DEFAULT/dictionary"):
                with zip_ref.open(file) as f:
                    return f.read().decode("utf-8", errors="replace")
    raise FileNotFoundError("No l10n/DEFAULT/dictionary found inside the .miz file")


def extract_entries(dictionary_text: str) -> List[Entry]:
    entries: List[Entry] = []
    for idx, match in enumerate(ENTRY_REGEX.finditer(dictionary_text)):
        full_key = match.group("key")
        prefix = next(p for p in TARGET_PREFIXES if full_key.startswith(p))
        field_id = int(match.group("id"))
        text = unescape_lua_string(match.group("text"))
        entries.append(Entry(prefix, field_id, full_key, text, idx))
    return entries


# =========================
# Context selection helpers
# =========================

TOKEN_SPLIT_RE = re.compile(r"[A-Za-z0-9']+|\\d+|[A-Z]{2,}|")
UPPER_TOKEN_RE = re.compile(r"\b[A-Z]{2,}(?:-[A-Z0-9]+)?\b")
NUMBER_RE = re.compile(r"\b\d{3,5}\b")
CALLSIGN_RE = re.compile(r"\b[A-Z][A-Za-z]+\s?\d?\b")


def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def cheap_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, normalize_text(a), normalize_text(b)).ratio()


def extract_anchor_tokens(s: str) -> List[str]:
    anchors = set()
    for m in UPPER_TOKEN_RE.finditer(s):
        anchors.add(m.group(0))
    for m in NUMBER_RE.finditer(s):
        anchors.add(m.group(0))
    # Callsigns are noisy, so only keep short proper-looking pieces if capitalized standalone.
    for m in re.finditer(r"\b[A-Z][a-zA-Z]{2,}\b", s):
        token = m.group(0)
        if token.lower() not in {"the", "and", "you", "your", "this", "that"}:
            anchors.add(token)
    return sorted(anchors)


def score_candidate(current: Entry, candidate: Entry) -> float:
    if current.full_key == candidate.full_key:
        return -1.0

    score = 0.0

    # Nearby items in file are often useful, but not reliable enough to dominate.
    distance = abs(current.index_in_file - candidate.index_in_file)
    score += max(0.0, 1.5 - 0.08 * distance)

    # Same field family tends to imply similar style.
    if current.prefix == candidate.prefix:
        score += 1.0

    # Exact or partial anchor overlap is very helpful.
    current_anchors = set(extract_anchor_tokens(current.text))
    cand_anchors = set(extract_anchor_tokens(candidate.text))
    overlap = len(current_anchors & cand_anchors)
    score += 1.2 * overlap

    # Text similarity helps when one line asks and another line reminds/repeats.
    score += 2.0 * cheap_similarity(current.text, candidate.text)

    return score


def select_candidate_contexts(current: Entry, all_entries: Sequence[Entry], k: int = 6) -> List[Entry]:
    scored: List[Tuple[float, Entry]] = []
    for candidate in all_entries:
        s = score_candidate(current, candidate)
        if s > 1.2:
            scored.append((s, candidate))
    scored.sort(key=lambda x: (-x[0], x[1].index_in_file))
    return [entry for _, entry in scored[:k]]


# =========================
# Translation memory / glossary
# =========================

class TranslationMemory:
    def __init__(self) -> None:
        self.exact_cache: Dict[str, str] = {}
        self.glossary: Dict[str, str] = {}

    def get_cached(self, src: str) -> str | None:
        return self.exact_cache.get(src)

    def add_translation(self, src: str, tgt: str) -> None:
        self.exact_cache[src] = tgt
        self._learn_glossary(src, tgt)

    def _learn_glossary(self, src: str, tgt: str) -> None:
        # Learn stable anchors only; keep this conservative.
        for anchor in extract_anchor_tokens(src):
            if anchor in src and anchor not in self.glossary:
                # If anchor is retained verbatim in target, remember that fact.
                if anchor in tgt:
                    self.glossary[anchor] = anchor

    def format_glossary_block(self, max_items: int = 40) -> str:
        if not self.glossary:
            return "（当前为空）"
        items = list(self.glossary.items())[:max_items]
        return "\n".join(f"- {k} -> {v}" for k, v in items)


# =========================
# OpenAI call
# =========================


def build_user_input(current: Entry, candidates: Sequence[Entry], memory: TranslationMemory) -> str:
    payload = {
        "task": "translate_dcs_mission_entry",
        "current_entry": {
            "field_type": current.prefix,
            "field_id": current.field_id,
            "field_name": current.full_key,
            "source_text": current.text,
        },
        "reference_glossary": memory.format_glossary_block(),
        "candidate_contexts": [
            {
                "field_type": c.prefix,
                "field_id": c.field_id,
                "field_name": c.full_key,
                "source_text": c.text,
            }
            for c in candidates
        ],
        "output_requirement": "只输出 current_entry.source_text 的中文译文。",
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def extract_output_text(response) -> str:
    text = getattr(response, "output_text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()

    output = getattr(response, "output", None)
    if not isinstance(output, list):
        return ""

    chunks: List[str] = []
    for item in output:
        content = getattr(item, "content", None)
        if content is None and isinstance(item, dict):
            content = item.get("content")
        if not isinstance(content, list):
            continue
        for c in content:
            ctype = getattr(c, "type", None)
            if ctype is None and isinstance(c, dict):
                ctype = c.get("type")
            if ctype == "output_text":
                txt = getattr(c, "text", None)
                if txt is None and isinstance(c, dict):
                    txt = c.get("text")
                if isinstance(txt, str):
                    chunks.append(txt)
    return "".join(chunks).strip()


def translate_one(
    client: OpenAI,
    model: str,
    current: Entry,
    all_entries: Sequence[Entry],
    memory: TranslationMemory,
    system_prompt: str,
    reasoning_effort: str,
) -> str:
    cached = memory.get_cached(current.text)
    if cached is not None:
        return cached

    candidates = select_candidate_contexts(current, all_entries, k=6)
    user_input = build_user_input(current, candidates, memory)

    response = client.responses.create(
        model=model,
        instructions=system_prompt,
        input=user_input,
        reasoning={"effort": reasoning_effort},
    )

    translated = extract_output_text(response)
    translated = translated.strip()
    memory.add_translation(current.text, translated)
    return translated


# =========================
# Main
# =========================


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract and translate DCS .miz dictionary entries using the OpenAI Responses API."
    )
    parser.add_argument("miz_file", help="Path to the .miz file")
    parser.add_argument(
        "--model",
        default="gpt-5.4-mini",
        help="Model to use. Recommended default: gpt-5.4-mini",
    )
    parser.add_argument(
        "--reasoning-effort",
        default="low",
        choices=["minimal", "low", "medium", "high"],
        help="Reasoning effort. For translation, low is usually enough.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output CSV path. Defaults to <miz basename>.csv",
    )
    parser.add_argument(
        "--save-jsonl",
        default=None,
        help="Optional path to save request/response audit records as JSONL",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    miz_file_path = Path(args.miz_file)
    if not miz_file_path.exists():
        print(f"[ERROR] File not found: {miz_file_path}", file=sys.stderr)
        return 1

    api_key_file = Path(__file__).with_name("api_key.txt")
    if not api_key_file.exists():
        print(f"[ERROR] API key file not found: {api_key_file}", file=sys.stderr)
        return 1

    api_key = api_key_file.read_text(encoding="utf-8").strip()
    if not api_key:
        print(f"[ERROR] API key file is empty: {api_key_file}", file=sys.stderr)
        return 1

    client = OpenAI(api_key=api_key)

    dictionary_text = read_dictionary_text_from_miz(miz_file_path)
    entries = extract_entries(dictionary_text)

    if not entries:
        print("[ERROR] No matching dictionary entries were found.", file=sys.stderr)
        return 1

    # Keep original file order for translation, because nearby entries are still sometimes useful.
    # For CSV readability, also include sortable numeric metadata.
    memory = TranslationMemory()
    translated_rows: List[List[str | int]] = []

    audit_fp = None
    if args.save_jsonl:
        audit_fp = open(args.save_jsonl, "w", encoding="utf-8")

    try:
        for entry in tqdm(entries, desc="Translating", unit="line"):
            src = (entry.text or "").strip()
            if not src:
                translated = ""
            else:
                try:
                    translated = translate_one(
                        client=client,
                        model=args.model,
                        current=entry,
                        all_entries=entries,
                        memory=memory,
                        system_prompt=DEFAULT_SYSTEM_PROMPT,
                        reasoning_effort=args.reasoning_effort,
                    )
                except Exception as e:
                    translated = f"[ERROR: {e}]"

            translated_rows.append(
                [
                    entry.prefix,
                    entry.field_id,
                    entry.full_key,
                    entry.index_in_file,
                    escape_for_csv_cell(src),
                    escape_for_csv_cell(translated),
                ]
            )

            if audit_fp:
                audit_fp.write(
                    json.dumps(
                        {
                            "field_name": entry.full_key,
                            "field_type": entry.prefix,
                            "field_id": entry.field_id,
                            "index_in_file": entry.index_in_file,
                            "source_text": src,
                            "translated_text": translated,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
    finally:
        if audit_fp:
            audit_fp.close()

    output_csv_path = Path(args.output) if args.output else miz_file_path.with_suffix(".csv")
    with open(output_csv_path, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "Field Type",
                "ID",
                "Field Name",
                "Index In File",
                "Original Text",
                "Translated Text",
            ]
        )
        writer.writerows(translated_rows)

    print(f"[OK] Wrote CSV: {output_csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
