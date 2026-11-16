"""개인정보나 기존 광고 사실 정보를 사용하지 않는 로컬 데모."""

import json
from pathlib import Path

from PIL import Image, ImageDraw

from .models import Announcement, RenderOptions
from .paths import output_directory
from .render import render_announcement


def create_demo_inputs(output: Path, root: Path) -> list[Path]:
    output = output_directory(output, root)
    for name, color in [('scene-a', '#cadfce'), ('scene-b', '#e3d5c2')]:
        path = output / f'{name}.png'
        if path.exists():
            raise FileExistsError(f'데모 파일이 이미 있습니다: {path}')
        # 직접 그린 테스트 이미지. 실제 교회 사진이나 외부 이미지가 아니다.
        image = Image.new('RGB', (1400, 900), color)
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 600, 1400, 900), fill='#536d66')
        draw.ellipse((1050, 90, 1250, 290), fill='#fff1b9')
        draw.polygon([(100, 600), (450, 210), (800, 600)], fill='#7b9a86')
        draw.polygon([(630, 600), (930, 300), (1230, 600)], fill='#a4b7a5')
        draw.text((40, 840), 'CHURCH STUDIO - SYNTHETIC TEST IMAGE', fill='white')
        image.save(path)
    common = {"footer": "가상 광고 · 디자인 검증용 · 실제 일정이 아닙니다"}
    ads = [
        {**common, "template": "notice", "heading": "01  주간 모임 안내 · 가상 샘플",
         "title": "함께하는 감사 나눔 모임", "paragraphs": ["한 주의 감사한 순간을 함께 나눕니다.", "처음 오시는 분도 편안하게 참여해 주세요."],
         "facts": [{"label": "일시", "value": "가상 일정 · 확정 후 입력", "accent": True},
                   {"label": "장소", "value": "샘플 공간 A (가상)"}]},
        {**common, "template": "photo", "heading": "02  사진이 있는 공지 · 가상 샘플",
         "title": "이웃과 함께하는 작은 나눔", "paragraphs": ["사진과 안내 문구를 자유롭게 교체할 수 있습니다."],
         "facts": [{"label": "참여", "value": "가상 모집 안내 · 담당자 확인 필요"}],
         "photos": [{"path": str(output / 'scene-a.png'), "caption": "직접 만든 테스트 이미지 A"},
                    {"path": str(output / 'scene-b.png'), "caption": "직접 만든 테스트 이미지 B", "zoom": 1.15}]},
        {**common, "template": "cover", "heading": "CHURCH STUDIO · 가상 샘플",
         "title": "함께 나누는\n이번 주 이야기", "paragraphs": ["주간 안내", "만남과 나눔을\n준비합니다"],
         "facts": [{"label": "안내", "value": "실제 일정은 확인 후 입력"}],
         "photos": [{"path": str(output / 'scene-a.png'), "caption": "직접 만든 가상 풍경"}]},
    ]
    paths = []
    for ad in ads:
        path = output / f'{ad["template"]}-input.json'
        with path.open('x', encoding='utf-8') as stream:
            json.dump(ad, stream, ensure_ascii=False, indent=2)
        paths.append(path)
    return paths


def run_demo(root: Path, output: Path, options: RenderOptions) -> list[dict]:
    inputs = create_demo_inputs(output, root)
    results = []
    for path in inputs:
        ad = Announcement.model_validate_json(path.read_text(encoding='utf-8'))
        results.append(render_announcement(ad, root, output, name=ad.template, options=options))
    return results
