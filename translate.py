import zipfile
import re
import csv
import os
from openai import OpenAI
from tqdm import tqdm
import argparse

client = OpenAI(api_key=open(os.path.join(os.path.dirname(__file__), "api_key.txt"), "r", encoding="utf-8").read().strip())

system_prompt = (
    "你是一个了解军事、空军作战体系和术语的领域专家和专业翻译。"
    "你需要将DCS World游戏的战役中的英文内容翻译成精确、流畅的中文。你仅回复翻译内容，不要包含任何其他内容。"
    "你需要确保正确翻译专业术语、缩写，并保证翻译后的内容符合语境。比如sir需要翻译为长官，而不是先生。"
    "对于无线电通话，翻译要尽可能简短。"
    "对于专业缩写，在翻译的文本中保留缩写本身，如：CAP -> 战斗空中巡逻（CAP）"
    "保留飞行员、指挥官等呼号，不翻译。"
    "所有地名需和DCS World游戏官方中文版中一致，如al Minhad需要被翻译成艾尔明翰，Al Dhafra需要被翻译成迪哈夫拉。"
)

max_context_turns = 16  # number of recent (source, translation) pairs to include as context

translation_cache = {}
recent_pairs = []  # store tuples of (source_text, translated_text)

# === Step 1–3: Read .miz and extract target fields ===
parser = argparse.ArgumentParser(description="Extract and translate DCS .miz dictionary entries.")
parser.add_argument("miz_file", help="Path to the .miz file")
args = parser.parse_args()
miz_file_path = args.miz_file

target_prefixes = [
    "DictKey_ActionRadioText_",
    "DictKey_subtitle_",
    "DictKey_ActionText_",
    "DictKey_sortie_",
    "DictKey_descriptionBlueTask_",
    "DictKey_descriptionRedTask_",
    "DictKey_descriptionNeutralsTask_",
    "DictKey_descriptionText_"
]

entry_regex = re.compile(
    r'\[\s*"(?P<key>(' + '|'.join(re.escape(prefix) for prefix in target_prefixes) +
    r')(?P<id>\d+))"\s*\]\s*=\s*"(?P<text>.*?)",?\s*(?=\n|\r|$)',
    re.DOTALL
)

dictionary_text = ""
with zipfile.ZipFile(miz_file_path, 'r') as zip_ref:
    for file in zip_ref.namelist():
        if file.endswith('l10n/DEFAULT/dictionary'):
            with zip_ref.open(file) as f:
                dictionary_text = f.read().decode('utf-8', errors='replace')
            break

entries = []
for match in entry_regex.finditer(dictionary_text):
    full_key = match.group('key')
    prefix = next(p for p in target_prefixes if full_key.startswith(p))
    field_id = int(match.group('id'))
    text = match.group('text')
    entries.append((prefix, field_id, full_key, text))

entries.sort(key=lambda x: (x[0], x[1]))

# === Step 4: Call GPT-5 Responses API, with context as prior translations ===
translated_rows = []

for prefix, field_id, full_key, original_text in tqdm(entries, desc="Translating", unit="line"):
    src = (original_text or "").strip()

    if not src:
        translated = ""
    elif src in translation_cache:
        translated = translation_cache[src]
    else:
        # Build context as prior translations (not examples, but background info)
        ctx_lines = []
        if recent_pairs:
            ctx_lines.append("Previous translations that may affect style and consistency:")
            for s, t in recent_pairs[-max_context_turns:]:
                if s and t:
                    ctx_lines.append(f"SRC: {s}")
                    ctx_lines.append(f"TGT: {t}")
        ctx_block = "\n".join(ctx_lines) if ctx_lines else ""

        current_block = "Translate the following text:\n" + src

        if ctx_block:
            input_text = ctx_block + "\n\n" + current_block
        else:
            input_text = current_block

        try:
            response = client.responses.create(
                model="gpt-5",
                instructions=system_prompt,
                input=input_text,
                reasoning={"effort": "high"}
            )

            if hasattr(response, "output_text") and isinstance(response.output_text, str) and response.output_text.strip():
                translated = response.output_text.strip()
            else:
                translated = ""
                try:
                    out = getattr(response, "output", None)
                    if isinstance(out, list):
                        for item in out:
                            content = item.get("content") if isinstance(item, dict) else getattr(item, "content", None)
                            if isinstance(content, list):
                                for c in content:
                                    ctype = c.get("type") if isinstance(c, dict) else getattr(c, "type", None)
                                    if ctype == "output_text":
                                        t = c.get("text") if isinstance(c, dict) else getattr(c, "text", None)
                                        if isinstance(t, str) and t.strip():
                                            translated = t.strip()
                                            break
                            if translated:
                                break
                except Exception:
                    translated = str(response).strip()

            translated = translated.replace("\\", "")
            translated = translated.replace("\n", "\\\n")

            translation_cache[src] = translated
            recent_pairs.append((src, translated))
        except Exception as e:
            translated = f"[ERROR: {e}]"

    translated_rows.append([prefix, field_id, full_key, src, translated])

# === Step 5: Write CSV (Original Text preserved) ===
output_csv_path = miz_file_path.removesuffix(".miz") + ".csv"
with open(output_csv_path, mode='w', newline='', encoding='utf-8-sig') as f:
    writer = csv.writer(f)
    writer.writerow(["Field Type", "ID", "Field Name", "Original Text", "Translated Text"])
    for row in translated_rows:
        writer.writerow(row)