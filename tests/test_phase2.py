"""네트워크 없이 승인 경계·원문 근거·SQLite 검색·표지 정보를 검증한다."""

from datetime import date
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from church_studio.ai_models import StructureResult, StyleProfile, validate_evidence
from church_studio.gemini import execute_plan, make_plan
from church_studio.library import LocalNgramEncoder, StyleLibrary, recommend_template
from church_studio.models import Announcement, RenderOptions
from church_studio.render import build_html, render_announcement


def cover_data():
    return {'service_date': '2026-11-15', 'service_time': '13:20:00', 'church': '샘플 교회',
            'location': '샘플 예배실', 'welcome': '여러분을 환영합니다 :)', 'confirmed': True,
            'service_order': [{'label': '인도자', 'value': '가상 인도자'}, {'label': '기도', 'value': '가상 기도자'},
                              {'label': '성경봉독', 'value': '가상 본문'}, {'label': '설교자', 'value': '가상 설교자'}]}


def test_cover_date_order_and_missing_values(tmp_path):
    ad = Announcement(template='cover', heading='예배', title='예배 안내', worship=cover_data())
    assert ad.worship.date_label == '11월 15일'
    assert ad.worship.time_label == '1:20PM'
    assert ad.worship.missing_items() == ['Song List 곡명']
    ad.worship.service_date = date(2026, 11, 22)
    assert ad.worship.date_label == '11월 22일'
    with pytest.raises(ValueError, match='Song List'):
        render_announcement(ad, tmp_path, tmp_path / 'outputs/check')
    html, _ = build_html(ad, tmp_path, RenderOptions(draft=True))
    assert '11월 22일' in html and '11월 15일' not in html
    assert '교회 사진 등록 대기' in html and '당일 곡명 입력 대기' in html


def result_data():
    return StructureResult(announcements=[{'title': '나눔 모임', 'category': '모임',
        'source_quote': '나눔 모임은 11월 22일 샘플홀에서 열립니다.',
        'paragraphs': ['나눔 모임은 11월 22일 샘플홀에서 열립니다.'],
        'facts': [{'label': '장소', 'value': '샘플홀', 'source_quote': '샘플홀에서 열립니다.'}]}])


def test_unsupported_facts_and_photo_ids_are_rejected():
    result = result_data()
    source = result.announcements[0].source_quote
    assert validate_evidence(result, source, [])
    result.announcements[0].facts[0].value = '과거 장소'
    with pytest.raises(ValueError, match='근거'):
        validate_evidence(result, source, [])
    result = result_data()
    result.announcements[0].photo_ids = ['unknown']
    with pytest.raises(ValueError, match='사진 ID'):
        validate_evidence(result, source, [])


def test_ai_rewritten_body_and_title_rejected():
    result = result_data()
    source = result.announcements[0].source_quote
    result.announcements[0].paragraphs = ['지난주 장소로 오세요.']
    with pytest.raises(ValueError, match='원문'):
        validate_evidence(result, source, [])
    result = result_data()
    result.announcements[0].title = '다른 행사'
    with pytest.raises(ValueError, match='제목'):
        validate_evidence(result, source, [])


def test_transfer_must_be_approved_before_client_use(tmp_path):
    plan = make_plan('structure', 'test-model', '가상 안내', [], tmp_path)
    class NeverClient:
        @property
        def models(self):
            pytest.fail('동의 전 클라이언트 접근')
    with pytest.raises(PermissionError):
        execute_plan(plan, '', client=NeverClient())
    digest = plan.digest()
    plan.text = '변경한 안내'
    with pytest.raises(PermissionError):
        execute_plan(plan, digest, client=NeverClient())


def test_changed_photo_after_approval_blocks_transmission(tmp_path):
    path = tmp_path / 'photo.png'
    Image.new('RGB', (20, 20), 'blue').save(path)
    plan = make_plan('style', 'test-model', '', [path], tmp_path)
    digest = plan.digest()
    Image.new('RGB', (20, 20), 'red').save(path)
    with pytest.raises(PermissionError, match='변경'):
        execute_plan(plan, digest, client=object())


def test_structure_does_not_send_photos(tmp_path):
    with pytest.raises(ValueError, match='사진 파일'):
        make_plan('structure', 'test-model', '안내', [tmp_path / 'not-existing.png'], tmp_path)


def test_real_sdk_config_and_mock_response_without_network(tmp_path):
    result = result_data()
    plan = make_plan('structure', 'test-model', result.announcements[0].source_quote, [], tmp_path)
    calls = []
    def generate_content(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(text=result.model_dump_json(), usage_metadata=None)
    client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    response = execute_plan(plan, plan.digest(), client=client)
    assert response['needs_review'] is True and len(calls) == 1
    assert calls[0]['config'].response_schema is StructureResult
    assert len(calls[0]['contents']) == 1


def test_multimodal_sdk_parts_are_only_approved_images(tmp_path):
    path = tmp_path / 'test.png'
    Image.new('RGB', (10, 10), 'white').save(path)
    profile = StyleProfile(template='photo', colors=['흰색'], layout='사진 중심', typography='굵은 제목', tone='정중한 안내')
    plan = make_plan('style', 'test-model', '', [path], tmp_path)
    def generate_content(**kwargs):
        assert kwargs['contents'][1].inline_data.data == path.read_bytes()
        return SimpleNamespace(text=profile.model_dump_json(), usage_metadata=None)
    response = execute_plan(plan, plan.digest(), client=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))
    assert response['result']['template'] == 'photo'


def test_api_error_does_not_expose_payload_or_key(tmp_path):
    plan = make_plan('structure', 'test-model', '가상 안내', [], tmp_path)
    def generate_content(**kwargs):
        raise RuntimeError('API_KEY=SECRET 개인정보 원문')
    with pytest.raises(ValueError) as exc:
        execute_plan(plan, plan.digest(), client=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))
    assert 'SECRET' not in str(exc.value) and '개인정보 원문' not in str(exc.value)


def test_sqlite_deduplication_and_local_ranking(tmp_path):
    library = StyleLibrary(tmp_path)
    for template, color, layout in [('cover', 'blue', '오른쪽 Song List 중앙 예배 사진'), ('notice', 'white', '노란 강조 글자 중심 일정 안내')]:
        path = tmp_path / f'{template}.png'
        Image.new('RGB', (10, 10), color).save(path)
        profile = StyleProfile(template=template, colors=[color], layout=layout, typography='굵은 제목', tone='안내')
        with pytest.raises(ValueError, match='검토'):
            library.add(path, profile, reviewed=False)
        library.add(path, profile, reviewed=True)
        library.add(path, profile, reviewed=True)
    found = library.search('오른쪽 Song List 중앙 예배 사진')
    assert found[0]['template'] == 'cover'
    assert len(found) == 2
    with library.connect() as connection:
        assert connection.execute('SELECT COUNT(*) FROM styles').fetchone()[0] == 2
    assert StyleLibrary(tmp_path).search('Song List')[0]['template'] == 'cover'
    assert recommend_template(category='행사', photo_count=2)['template'] == 'photo'


def test_ngram_vector_is_deterministic_and_nonsemantic():
    encoder = LocalNgramEncoder()
    assert np.array_equal(encoder.encode(['교회 안내']), encoder.encode(['교회 안내']))
    assert np.isfinite(encoder.encode([''])).all()


def test_ai_result_connects_to_render_input_without_old_facts(tmp_path):
    from church_studio.workflow import prepare_drafts
    result = result_data()
    review = prepare_drafts(result, result.announcements[0].source_quote, {}, tmp_path)
    ad = Announcement.model_validate(review['drafts'][0]['input'])
    assert review['needs_review'] is True
    assert ad.template == 'notice'
    assert ad.facts[0].value == '샘플홀'
    assert ad.worship is None


@pytest.mark.integration
def test_new_worship_cover_renders_song_order_and_service_information(tmp_path):
    from playwright.sync_api import sync_playwright
    path = tmp_path / 'photo.png'
    Image.new('RGB', (900, 1200), '#718eaf').save(path)
    worship = {**cover_data(), 'song_list': ['가상 찬양 A', '가상 찬양 B', '가상 찬양 C', '가상 찬양 D']}
    ad = Announcement(template='cover', heading='예배', title='예배 안내', worship=worship, photos=[{'path': str(path)}])
    result = render_announcement(ad, tmp_path, tmp_path / 'outputs/worship')
    assert result['warnings'] == [] and result['draft'] is False
    with Image.open(result['png']) as image:
        assert image.size == (1920, 1080)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.set_content(__import__('pathlib').Path(result['html']).read_text(encoding='utf-8'))
        assert page.locator('.song-panel li').all_inner_texts() == worship['song_list']
        assert page.locator('.order-row strong').all_inner_texts() == [f['value'] for f in worship['service_order']]
        assert '11월 15일' in page.locator('.worship-date').inner_text()
        assert page.locator('.worship-photo img').count() == 1
        assert page.locator('.draft-label').count() == 0
        browser.close()
