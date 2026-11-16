"""로컬 이미지의 기술 정보와 중복을 분석한다. OCR/AI 분석은 하지 않는다."""

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError

from .paths import output_directory

EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def inspect_archive(archive: Path, root: Path, output: Path) -> dict:
    if not archive.is_dir():
        raise ValueError(f"기존 자료 폴더가 없습니다: {archive}")
    output = output_directory(output, root)
    records, errors, thumbnails = [], [], []
    hashes = defaultdict(list)
    for path in sorted(archive.rglob("*")):
        if path.suffix.lower() not in EXTENSIONS or not path.is_file():
            continue
        name = path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            with Image.open(path) as source:
                source.load()
                image = ImageOps.exif_transpose(source).convert("RGB")
                colors = image.resize((160, 90)).quantize(colors=5).convert("RGB").getcolors(14400)
                palette = ["#%02x%02x%02x" % rgb for count, rgb in sorted(colors, reverse=True)]
                records.append({"path": name, "width": image.width, "height": image.height,
                                "aspect_ratio": round(image.width / image.height, 6),
                                "mode": source.mode, "bytes": path.stat().st_size,
                                "sha256": digest, "palette": palette})
                if digest not in hashes:
                    thumbnails.append((name, ImageOps.contain(image, (480, 270))))
                hashes[digest].append(name)
        except (OSError, ValueError, UnidentifiedImageError) as exc:
            errors.append({"path": name, "error": str(exc)})
    report = {"file_count": len(records), "unique_count": len(hashes),
              "duplicate_groups": [paths for paths in hashes.values() if len(paths) > 1],
              "resolutions": dict(Counter(f'{r["width"]}x{r["height"]}' for r in records)),
              "images": records, "errors": errors,
              "note": "색상은 로컬 픽셀 집계이며 템플릿 의미 분류는 관리자의 육안 검토가 필요합니다."}
    (output / "archive-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if thumbnails:
        sheet = Image.new("RGB", (1500, ((len(thumbnails) + 2) // 3) * 330), "#eeeeee")
        draw = ImageDraw.Draw(sheet)
        for i, (name, thumb) in enumerate(thumbnails):
            x, y = i % 3 * 500, i // 3 * 330
            sheet.paste(thumb, (x + 10, y + 10))
            draw.text((x + 10, y + 286), f'{i + 1:02} {Path(name).parent.name}', fill="black")
            draw.text((x + 10, y + 306), Path(name).stem, fill="black")
        sheet.save(output / "contact-sheet.jpg")
    return report
