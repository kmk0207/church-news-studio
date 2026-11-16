"""실제 브라우저에서 한글·사진·로고·배경·넘침을 검사한다."""

import hashlib
import json

import pytest
from PIL import Image
from playwright.sync_api import sync_playwright

from church_studio.demo import create_demo_inputs
from church_studio.models import Announcement, RenderOptions
from church_studio.render import LayoutOverflowError, render_announcement

pytestmark = pytest.mark.integration


@pytest.mark.parametrize('template', ['notice', 'photo', 'cover'])
def test_templates_render_real_png_with_exact_text_and_no_network(tmp_path, template):
    folder = tmp_path / 'outputs/demo'
    paths = create_demo_inputs(folder, tmp_path)
    ad = Announcement.model_validate_json(next(p for p in paths if p.name == template + '-input.json').read_text(encoding='utf-8'))
    result = render_announcement(ad, tmp_path, folder, name=template)
    with Image.open(result['png']) as image:
        assert image.size == (1920, 1080)
        assert image.convert('L').getextrema()[0] < 80
    assert result['overflow'] == []
    assert result['input'] == ad.model_dump(mode='json')
    assert result['external_requests_allowed'] is False
    # 저장된 HTML이 열리는지와 사용자가 입력한 문자열이 바뀌지 않는지 확인한다.
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        requests = []
        page.on('request', lambda request: requests.append(request.url))
        page.set_content(open(result['html'], encoding='utf-8').read())
        page.evaluate('document.fonts.ready')
        assert page.locator('h1').inner_text() == ad.title
        assert all(url.startswith('data:') for url in requests)
        browser.close()


def test_4k_logo_background_and_source_unchanged(tmp_path):
    asset = tmp_path / 'data/assets'
    asset.mkdir(parents=True)
    Image.new('RGB', (600, 100), '#0077bb').save(asset / 'logo.png')
    Image.new('RGB', (1920, 1080), '#eef5ff').save(asset / 'background.png')
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in asset.iterdir()}
    ad = Announcement(heading='고해상도 검증', title='한글 글꼴과 로고', logo='data/assets/logo.png', background='data/assets/background.png')
    result = render_announcement(ad, tmp_path, tmp_path / 'outputs/4k', options=RenderOptions(scale=2))
    with Image.open(result['png']) as image:
        assert image.size == (3840, 2160)
        assert image.convert('RGB').getpixel((0, 0)) == (238, 245, 255)
    assert before == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in asset.iterdir()}


def test_overflow_rejected_instead_of_silent_clipping(tmp_path):
    ad = Announcement(heading='넘침 테스트', title='너무 긴 광고는 나누어 주세요',
                      paragraphs=['한글 본문이 너무 길어 광고 영역을 넘치는 경우를 검사합니다. ' * 15] * 6)
    output = tmp_path / 'outputs/overflow'
    with pytest.raises(LayoutOverflowError, match='글자가 영역을 넘칩니다'):
        render_announcement(ad, tmp_path, output)
    assert not list(output.glob('*.png'))
