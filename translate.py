#!/usr/bin/env python3
"""
Translate selected DCS World .miz dictionary entries to Chinese using the OpenAI Responses API.

Key design choices:
- Reads API key from api_key.txt next to this script.
- Uses the current Responses API via openai-python.
- Separates stable instruction, glossary memory, and local candidate context.
- Avoids blindly stuffing recent translations into one flat prompt.
- Handles partially disordered mission text by retrieving semantically similar candidates
  from the whole mission instead of trusting file order alone.
- Adds task-type hints and structure-preservation constraints for DCS mission text.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from openai import OpenAI
from tqdm import tqdm


# =========================
# Prompting / task settings
# =========================

DEFAULT_SYSTEM_PROMPT = """
你是 DCS World 战役文本本地化助手，熟悉空军、联合作战、无线电通话、任务提示、武器与航电术语。

你的唯一任务是：把给定英文条目翻译成中文，用于 DCS 任务文本本地化。

你处理的条目可能属于下列类型：
A1. 对话：通常出现在 DictKey_subtitle 中，包含“人物/说话源 + 语言内容”两部分。
A2. 提示：通常出现在 DictKey_ActionText 中，用于提示玩家操作、状态、结果或任务推进。
A3. 菜单选项：通常出现在 DictKey_ActionRadioText 中，是玩家在菜单中选择的短句或短词。
A4. 游戏内背景介绍：可能出现在 DictKey_ActionText 中，是进入游戏后展示的局势、简报、会议场景描述。
A5. 游戏外背景介绍：通常出现在 DictKey_sortie、DictKey_descriptionBlueTask、DictKey_descriptionNeutralsTask、DictKey_descriptionRedTask、DictKey_descriptionText 中。
A6. 调试信息：通常出现在 DictKey_ActionText 中，是任务作者调试时使用的字符串；若能明确判断是调试信息，则保持原样，不翻译。

关于 A2 / A4 / A6：
- 这三类可能共享相同字段，不能只靠字段名判断。
- 只有在能明确判断条目是调试信息时，才按 A6 处理并保持原样。
- 如果不能明确判断其为调试信息，必须优先按 A2 或 A4 正常翻译，不能因为怀疑是调试信息就拒绝翻译。

硬性要求：
1. 只输出最终结果本身，不要解释，不要加引号，不要加注释。
2. 呼号、人名、机型代号、武器型号、航点代号、频率、激光编码、数字坐标，默认保留原样，除非中文社区已有稳定官方译名。
3. 军事缩写首次出现时，优先译为“中文（英文缩写）”；如果原句极短、属于无线电喊话或 UI 提示，可只保留缩写或使用更短表达。
4. 无线电通话应简洁、口语化、符合战术电台语境；任务说明和字幕则可略完整。
5. 不要擅自补充原文没有的信息。
6. 若上下文不足以确定人称、指代或术语含义，采取最保守、最不易误导的译法。
7. 保持同一任务内术语、呼号、地名译法一致。
8. DCS 官方中文版已有固定译名时，优先与其一致。
9. 若原文包含“说话人/发话源 + 内容”的结构，必须保留该结构，不得省略说话人、发话源、呼号前缀、尖括号包裹的人物标记、冒号等结构元素。
10. 若原文中存在类似 “PLAYER: ...”“OVERLORD: ...”“<PLAYER> ...”“Raven2-1, ...” 等发话头、称呼或呼叫对象，它们属于脚本结构的一部分，默认必须保留，不得因为中文习惯而省略。
11. 你只能翻译可翻译的正文，不得删除原文中可识别的结构性头部。
12. 候选上下文只用于帮助你判断术语、语气、类型和脚本结构；绝不可把别的条目内容拼进当前译文。
13. 菜单选项（A3）要简短、可点击；提示（A2）要清楚直接；背景介绍（A4/A5）可稍完整；对话（A1）要保留人物与发话结构。
14. 如果当前条目被明确标注为“clear_debug_signal=true”，则保持原文不变，原样输出。

你会收到：
- 当前条目
- 条目元数据（字段类型、ID）
- 针对类型和结构的程序分析提示
- 可能相关的候选上下文（它们不保证顺序正确，只能作为参考）
- 已累积的术语/记忆表
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

DESCRIPTION_PREFIXES = {
    "DictKey_sortie_",
    "DictKey_descriptionBlueTask_",
    "DictKey_descriptionRedTask_",
    "DictKey_descriptionNeutralsTask_",
    "DictKey_descriptionText_",
}


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
    s = s.replace(r'\"', '"')
    s = s.replace(r"\\", "\\")
    s = s.replace(r"\n", "\n")
    s = s.replace(r"\r", "\r")
    s = s.replace(r"\t", "\t")
    return s


def escape_for_csv_cell(s: str) -> str:
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

UPPER_TOKEN_RE = re.compile(r"\b[A-Z]{2,}(?:-[A-Z0-9]+)?\b")
NUMBER_RE = re.compile(r"\b\d{2,5}\b")
PROPER_TOKEN_RE = re.compile(r"\b[A-Z][a-zA-Z]{2,}\b")


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
    for m in PROPER_TOKEN_RE.finditer(s):
        token = m.group(0)
        if token.lower() not in {"the", "and", "you", "your", "this", "that", "with", "from"}:
            anchors.add(token)
    return sorted(anchors)


def score_candidate(current: Entry, candidate: Entry) -> float:
    if current.full_key == candidate.full_key:
        return -1.0

    score = 0.0
    distance = abs(current.index_in_file - candidate.index_in_file)
    score += max(0.0, 1.5 - 0.08 * distance)

    if current.prefix == candidate.prefix:
        score += 1.0

    current_anchors = set(extract_anchor_tokens(current.text))
    cand_anchors = set(extract_anchor_tokens(candidate.text))
    overlap = len(current_anchors & cand_anchors)
    score += 1.2 * overlap

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
# Type / structure hints
# =========================

COLON_SPEAKER_RE = re.compile(r"^\s*([^:\n<>]{1,40}):\s+(.+)$", re.DOTALL)
ANGLE_SPEAKER_RE = re.compile(r"^\s*(<[^>]{1,40}>)(\s+.+)$", re.DOTALL)
CALLSIGN_HEAD_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9-]*(?:\s?[0-9]-[0-9])?),\s+(.+)$", re.DOTALL)

DEBUG_PATTERNS = [
    re.compile(r"\bdebug\b", re.IGNORECASE),
    re.compile(r"\btest\b", re.IGNORECASE),
    re.compile(r"\btodo\b", re.IGNORECASE),
    re.compile(r"\bfixme\b", re.IGNORECASE),
    re.compile(r"\btemp\b", re.IGNORECASE),
    re.compile(r"\bdummy\b", re.IGNORECASE),
    re.compile(r"\btrace\b", re.IGNORECASE),
    re.compile(r"\blog\b", re.IGNORECASE),
    re.compile(r"\bflag\s*[:=_-]?\s*\d+\b", re.IGNORECASE),
    re.compile(r"\btrigger\s*[:=_-]?\s*\d+\b", re.IGNORECASE),
    re.compile(r"\bstage\s*[:=_-]?\s*\d+\b", re.IGNORECASE),
    re.compile(r"\bbranch\s*[:=_-]?\s*\d+\b", re.IGNORECASE),
    re.compile(r"\bcase\s*[:=_-]?\s*\d+\b", re.IGNORECASE),
    re.compile(r"\bmsg\s*[:=_-]?\s*\d+\b", re.IGNORECASE),
    re.compile(r"^[A-Z0-9_\- ]{3,}$"),
]


def detect_dialogue_structure(text: str) -> Dict[str, object]:
    info: Dict[str, object] = {
        "has_explicit_speaker_structure": False,
        "structure_kind": "none",
        "protected_head": "",
        "translatable_body": text,
    }

    m = COLON_SPEAKER_RE.match(text)
    if m:
        head = m.group(1).strip() + ":"
        body = m.group(2)
        info.update(
            {
                "has_explicit_speaker_structure": True,
                "structure_kind": "speaker_colon",
                "protected_head": head,
                "translatable_body": body,
            }
        )
        return info

    m = ANGLE_SPEAKER_RE.match(text)
    if m:
        head = m.group(1).strip()
        body = m.group(2).lstrip()
        info.update(
            {
                "has_explicit_speaker_structure": True,
                "structure_kind": "speaker_angle_brackets",
                "protected_head": head,
                "translatable_body": body,
            }
        )
        return info

    m = CALLSIGN_HEAD_RE.match(text)
    if m:
        head = m.group(1).strip() + ","
        body = m.group(2)
        info.update(
            {
                "has_explicit_speaker_structure": True,
                "structure_kind": "callsign_head",
                "protected_head": head,
                "translatable_body": body,
            }
        )
        return info

    return info


def is_clearly_debug_actiontext(entry: Entry) -> bool:
    if entry.prefix != "DictKey_ActionText_":
        return False

    text = entry.text.strip()
    if not text:
        return False

    hits = 0
    for pat in DEBUG_PATTERNS:
        if pat.search(text):
            hits += 1

    if text.startswith("[") and text.endswith("]"):
        hits += 1
    if text.startswith("(") and text.endswith(")"):
        hits += 1
    if "::" in text or "=>" in text or "==" in text:
        hits += 1

    return hits >= 2


def infer_type_hints(entry: Entry) -> Dict[str, object]:
    structure = detect_dialogue_structure(entry.text)

    if entry.prefix == "DictKey_subtitle_":
        return {
            "possible_types": ["A1"],
            "recommended_type": "A1",
            "clear_debug_signal": False,
            "structure_analysis": structure,
            "translation_style_hint": "对话字幕；保留人物/发话结构，只翻译正文。",
        }

    if entry.prefix == "DictKey_ActionRadioText_":
        return {
            "possible_types": ["A3"],
            "recommended_type": "A3",
            "clear_debug_signal": False,
            "structure_analysis": structure,
            "translation_style_hint": "菜单选项；简短、清楚、可点击。",
        }

    if entry.prefix in DESCRIPTION_PREFIXES:
        return {
            "possible_types": ["A5"],
            "recommended_type": "A5",
            "clear_debug_signal": False,
            "structure_analysis": structure,
            "translation_style_hint": "游戏外背景介绍；可稍完整，偏简报/说明文风格。",
        }

    clear_debug = is_clearly_debug_actiontext(entry)
    if clear_debug:
        return {
            "possible_types": ["A2", "A4", "A6"],
            "recommended_type": "A6",
            "clear_debug_signal": True,
            "structure_analysis": structure,
            "translation_style_hint": "已被程序判定为明确调试信息；保持原样输出。",
        }

    # ActionText 默认不轻易判定为调试信息。
    longish = len(entry.text.strip()) >= 120 or entry.text.count("\n") >= 2
    return {
        "possible_types": ["A2", "A4", "A6"],
        "recommended_type": "A4" if longish else "A2",
        "clear_debug_signal": False,
        "structure_analysis": structure,
        "translation_style_hint": "ActionText 非明确调试信息；优先按提示或游戏内背景介绍处理。",
    }


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
        for anchor in extract_anchor_tokens(src):
            if anchor in src and anchor not in self.glossary:
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
        "program_analysis": infer_type_hints(current),
        "reference_glossary": memory.format_glossary_block(),
        "candidate_contexts": [
            {
                "field_type": c.prefix,
                "field_id": c.field_id,
                "field_name": c.full_key,
                "source_text": c.text,
                "program_analysis": infer_type_hints(c),
            }
            for c in candidates
        ],
        "output_requirement": "只输出 current_entry.source_text 的最终结果；若 clear_debug_signal=true，则原样输出 source_text。",
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

    if is_clearly_debug_actiontext(current):
        memory.add_translation(current.text, current.text)
        return current.text

    candidates = select_candidate_contexts(current, all_entries, k=6)
    user_input = build_user_input(current, candidates, memory)

    response = client.responses.create(
        model=model,
        instructions=system_prompt,
        input=user_input,
        reasoning={"effort": reasoning_effort},
    )

    translated = extract_output_text(response).strip()
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
                            "program_analysis": infer_type_hints(entry),
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
