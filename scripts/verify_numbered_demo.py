"""번호별 제작 흐름을 외부 API 없이 실제 PNG로 검증한다. 원본·제작 DB는 변경하지 않는다."""

import json
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageDraw

from church_studio.briefs import CopyResult, cards_from_copy, local_copy, parse_numbered
from church_studio.models import Announcement, RenderOptions
from church_studio.render import render_announcement


def main():
    root = Path(__file__).resolve().parents[1]
    output = root / 'outputs' / ('numbered-demo-' + uuid4().hex[:8])
    output.mkdir(parents=True)
    image = Image.new('RGB', (1200, 800), '#eaf4f1')
    draw = ImageDraw.Draw(image)
    draw.rectangle((80, 160, 1120, 650), outline='#147d84', width=8)
    draw.line((600, 160, 600, 650), fill='#147d84', width=8)
    draw.text((80, 710), 'SYNTHETIC PHOTO - LOCAL TEST', fill='#147d84')
    photo = output / 'sample-photo.png'
    image.save(photo)
    source = (root / 'examples/numbered-announcements.txt').read_text(encoding='utf-8')
    briefs = parse_numbered(source)
    cards = cards_from_copy(briefs, CopyResult(pages=[local_copy(item) for item in briefs]), {4: [str(photo)]}, root)
    results = []
    cover_path = root / 'outputs/phase2-cover/cover-input.json'
    if cover_path.is_file():
        cover = Announcement.model_validate_json(cover_path.read_text(encoding='utf-8'))
        cover.photos = []
        results.append(render_announcement(cover, root, output, name='cover-draft', options=RenderOptions(draft=True)))
    for card in cards:
        ad = Announcement.model_validate(card.data)
        results.append(render_announcement(ad, root, output, name=f'notice-{card.number:02d}'))
    (output / 'review-notes.json').write_text(json.dumps([
        {'number': card.number, 'source': card.source_text, 'notes': card.review_notes} for card in cards], ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(output), 'pages': len(results), 'api_calls': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
