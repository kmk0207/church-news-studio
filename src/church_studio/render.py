"""Jinja2 → 격리된 Chromium → 고해상도 PNG. 외부 요청은 모두 차단한다."""

import base64
import hashlib
import json
import re
import time
from importlib.resources import files
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from playwright.sync_api import sync_playwright

from .images import image_data
from .models import Announcement, RenderOptions
from .paths import asset_path, output_directory


class LayoutOverflowError(ValueError):
    """최소 글자 크기로 줄여도 레이아웃을 벗어나면 생성을 거부한다."""


def select_fonts(root: Path, options: RenderOptions) -> tuple[Path, Path]:
    if options.bold_font and not options.font:
        raise ValueError("bold_font와 함께 font도 지정하세요.")
    if options.font:
        regular = asset_path(options.font, root)
        bold = asset_path(options.bold_font, root) if options.bold_font else regular
        return regular, bold
    # 자동 선택은 한글 글꼴로 알려진 경로만 사용한다. 원본 자산을 복사하지 않는다.
    candidates = [
        (Path('C:/Windows/Fonts/malgun.ttf'), Path('C:/Windows/Fonts/malgunbd.ttf')),
        (Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'),
         Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc')),
        (Path('/System/Library/Fonts/AppleSDGothicNeo.ttc'),
         Path('/System/Library/Fonts/AppleSDGothicNeo.ttc')),
    ]
    for regular, bold in candidates:
        if regular.is_file() and bold.is_file():
            return regular, bold
    raise ValueError("한글 글꼴이 없습니다. --font로 사용 권한이 있는 TTF/OTF 글꼴을 지정하세요.")


def font_uri(path: Path) -> str:
    return 'data:font/ttf;base64,' + base64.b64encode(path.read_bytes()).decode('ascii')


def build_html(ad: Announcement, root: Path, options: RenderOptions) -> tuple[str, dict]:
    regular, bold = select_fonts(root, options)
    template_dir = files('church_studio').joinpath('templates')
    env = Environment(loader=FileSystemLoader(str(template_dir)),
                      autoescape=select_autoescape(['html']), undefined=StrictUndefined)
    photos = []
    photo_width = round((1328 - 24 * (len(ad.photos) - 1)) / max(1, len(ad.photos)))
    size = ((650, 460) if ad.worship else (1050, 500)) if ad.template == 'cover' else (photo_width, 320)
    for photo in ad.photos:
        photos.append({"caption": photo.caption, "uri": image_data(
            asset_path(photo.path, root), tuple(v * options.scale for v in size),
            focal_x=photo.focal_x, focal_y=photo.focal_y, zoom=photo.zoom)})
    logo = image_data(asset_path(ad.logo, root), (320, 100), contain=True) if ad.logo else None
    background = image_data(asset_path(ad.background, root), (1920 * options.scale, 1080 * options.scale)) if ad.background else None
    template = 'worship.html' if ad.worship else ('cover.html' if ad.template == 'cover' else 'notice.html')
    html = env.get_template(template).render(
        ad=ad, photos=photos, logo=logo, background=background, draft=options.draft,
        font_regular=font_uri(regular), font_bold=font_uri(bold),
        stylesheet=template_dir.joinpath('style.css').read_text(encoding='utf-8'))
    return html, {"regular": str(regular), "bold": str(bold)}


# 스크롤 크기와 실제 좌표를 함께 검사하여 flex 중앙 정렬의 넘침도 탐지한다.
OVERFLOW_SCRIPT = """() => {
  const slide = document.querySelector('#slide').getBoundingClientRect();
  return [...document.querySelectorAll('[data-fit]')].filter(el => {
    const r = el.getBoundingClientRect();
    if (el.scrollWidth > el.clientWidth + 2 || el.scrollHeight > el.clientHeight + 2) return true;
    if (r.left < slide.left - 1 || r.right > slide.right + 1 || r.top < slide.top - 1 || r.bottom > slide.bottom + 1) return true;
    const range = document.createRange(); range.selectNodeContents(el);
    return [...range.getClientRects()].some(c => c.left < r.left - 2 || c.right > r.right + 2 || c.top < r.top - 2 || c.bottom > r.bottom + 2);
  }).map(el => ({tag: el.tagName, text: el.textContent.trim().slice(0, 100)}));
}"""


def render_announcement(ad: Announcement, root: Path, output: Path, *, name='announcement',
                        options: RenderOptions | None = None) -> dict:
    """같은 이름을 덮어쓰지 않고 HTML·입력 JSON·렌더링 기록을 함께 저장한다."""
    root = root.resolve()
    options = options or RenderOptions()
    warnings = ad.worship.missing_items() if ad.worship else []
    if ad.worship and not ad.photos:
        warnings.append('중앙 교회 사진')
    if warnings and not options.draft:
        raise ValueError('표지 정보 확인 필요: ' + ', '.join(warnings) + '. 미완성 미리보기는 --draft를 사용하세요.')
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', name):
        raise ValueError("파일 이름은 영문·숫자·밑줄·하이픈만 사용하세요.")
    output = output_directory(output, root)
    targets = {ext: output / f'{name}.{ext}' for ext in ['png', 'html', 'json']}
    if any(path.exists() for path in targets.values()):
        raise FileExistsError("같은 이름의 결과물이 있습니다. 새 이름 또는 새 출력 폴더를 사용하세요.")
    started = time.perf_counter()
    html, fonts = build_html(ad, root, options)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(viewport={"width": 1920, "height": 1080},
                                          device_scale_factor=options.scale, locale='ko-KR',
                                          timezone_id='Asia/Seoul', service_workers='block')
            # 템플릿/사용자 내용은 어떤 외부 주소도 불러올 수 없다.
            context.route('**/*', lambda route: route.abort())
            page = context.new_page()
            page.set_content(html, wait_until='load')
            page.evaluate('document.fonts.ready')
            page.evaluate("""async () => {
              await document.fonts.load('400 40px Studio', '한글');
              await document.fonts.load('700 40px Studio', '한글');
              await Promise.all([...document.images].map(img => img.decode()));
              if (![...document.fonts].every(f => f.status === 'loaded')) throw new Error('글꼴 로딩 실패');
            }""")
            issues = []
            shrink = 1.0
            for percent in [100, 95, 90, 85, 80, 75, 70, 65]:
                shrink = percent / 100
                page.eval_on_selector('#slide', '(el, v) => el.style.setProperty("--shrink", v)', str(shrink))
                issues = page.evaluate(OVERFLOW_SCRIPT)
                if not issues:
                    break
            if issues:
                raise LayoutOverflowError('글자가 영역을 넘칩니다. 광고를 나누거나 문구를 줄이세요: ' + json.dumps(issues, ensure_ascii=False))
            png = page.locator('#slide').screenshot(type='png', animations='disabled')
            browser_version = browser.version
        finally:
            browser.close()
    # 미리보기 HTML도 실제 PNG와 같은 축소 비율을 사용한다.
    html = html.replace('--shrink: 1;', f'--shrink: {shrink};')
    manifest = {"input": ad.model_dump(mode='json'), "options": options.model_dump(mode='json'),
                "width": 1920 * options.scale, "height": 1080 * options.scale,
                "font_scale": shrink, "fonts": fonts, "chromium": browser_version,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "png_sha256": hashlib.sha256(png).hexdigest(), "overflow": [],
                "external_requests_allowed": False}
    manifest['warnings'] = warnings
    manifest['draft'] = options.draft
    # 독점 생성 모드로 실수로 기존 결과물을 덮어쓰지 않는다.
    with targets['png'].open('xb') as stream:
        stream.write(png)
    with targets['html'].open('x', encoding='utf-8') as stream:
        stream.write(html)
    with targets['json'].open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
    return {**manifest, "png": str(targets['png']), "html": str(targets['html']), "manifest": str(targets['json'])}
