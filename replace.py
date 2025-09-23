#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import zipfile
import csv
import re
import shutil
import os
import tempfile
import argparse
from pathlib import Path


def inject_translations(miz_path: str) -> None:
    miz_path = Path(miz_path).resolve()
    if not miz_path.exists():
        raise FileNotFoundError(miz_path)

    base_stem = miz_path.stem
    csv_path = miz_path.with_suffix(".csv")

    if not csv_path.exists():
        raise FileNotFoundError(csv_path)

    translation_map: dict[str, str] = {}
    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = row.get("Field Name", "").strip()
            val = row.get("Translated Text", "").strip()
            if key and val:
                translation_map[key] = val
    if not translation_map:
        raise ValueError("CSV contains no translations.")

    temp_dir = Path(tempfile.mkdtemp(prefix="miz_"))
    with zipfile.ZipFile(miz_path, "r") as zf:
        zf.extractall(temp_dir)

    dict_path = temp_dir / "l10n" / "DEFAULT" / "dictionary"
    if not dict_path.exists():
        shutil.rmtree(temp_dir)
        raise FileNotFoundError("dictionary file not found inside .miz")

    with dict_path.open("r", encoding="utf-8") as f:
        original_dict = f.read()

    entry_regex = re.compile(
        r'\[\s*"(?P<key>DictKey_[^"]+)"\s*\]\s*=\s*"(?P<text>(?:\\.|[^"\\])*)"',
        re.DOTALL,
    )

    def repl(match: re.Match) -> str:
        key = match.group("key")
        if key not in translation_map:
            return match.group(0)

        txt = translation_map[key]

        txt = txt.replace("\\", "")
        txt = txt.replace("\n", "\\\n")
        txt = txt.replace('"', r"\"")

        return f'["{key}"] = "{txt}"'

    modified_dict = entry_regex.sub(repl, original_dict)

    with dict_path.open("w", encoding="utf-8") as f:
        f.write(modified_dict)

    output_dir = miz_path.parent / "translated"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_miz = output_dir / miz_path.name

    with zipfile.ZipFile(output_miz, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for file in temp_dir.rglob("*"):
            arc = file.relative_to(temp_dir).as_posix()
            zout.write(file, arc)

    shutil.rmtree(temp_dir)
    print("Translated mission saved as:", output_miz)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract and translate DCS .miz dictionary entries.")
    parser.add_argument("miz_file", help="Path to the .miz file")
    args = parser.parse_args()
    miz_file_path = args.miz_file
    inject_translations(miz_file_path)
