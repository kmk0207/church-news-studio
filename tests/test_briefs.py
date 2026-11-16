"""번호 분할·사실 보존·말투·사진 연결·고정 표지 흐름을 검증한다."""

import json
from datetime import date
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image

from church_studio.briefs import CopyResult, cards_from_copy, local_copy, parse_numbered, validate_copy
from church_studio.gemini import execute_plan, make_plan
from church_studio.studio import Studio

SOURCE = '''0. 새신자 환영
1. 10월 생일축하
2. 추수감사 특새 광고 (복장 ,모임시간)
3. 광고 이후 추수감사 특송 연습
4. 배트민턴 광고 (우천시 취소)'''


def result_for(source=SOURCE):
    return CopyResult(pages=[local_copy(item) for item in parse_numbered(source)])


def test_five_numbered_items_are_five_pages_including_zero(tmp_path):
    items = parse_numbered(SOURCE)
    result = result_for()
    cards = cards_from_copy(items, result, {}, tmp_path)
    assert [card.number for card in cards] == [0, 1, 2, 3, 4]
    assert '연습이 있습니다~' in cards[3].data['paragraphs'][0]
    assert '우천시 취소' in cards[4].data['paragraphs'][0]
    assert cards[2].review_notes == ['복장을 알려주세요.', '모임 시간을 알려주세요.']
    assert all(not card.reviewed for card in cards)


def test_continuation_and_blank_lines_stay_on_same_number():
    items = parse_numbered('0. 새신자 환영\n안내 첫 줄\n\n안내 둘째 줄\n1. 생일 축하')
    assert len(items) == 2
    assert '안내 둘째 줄' in items[0].text
    for source in ['내용만 입력', '0. 첫 안내\n0. 중복 번호', '머리말\n0. 안내']:
        with pytest.raises(ValueError):
            parse_numbered(source)


def test_rewrite_can_change_wording_but_not_dates_counts_or_conditions():
    items = parse_numbered(SOURCE)
    result = result_for()
    result.pages[3].title = '추수감사 특송 연습 안내'
    validate_copy(result, items)
    result.pages[4].paragraphs = ['비가 와도 모입니다.']
    with pytest.raises(ValueError, match='취소'):
        validate_copy(result, items)
    result = result_for()
    result.pages[0].paragraphs = ['11월 22일 새가족을 환영합니다.']
    with pytest.raises(ValueError, match='숫자'):
        validate_copy(result, items)
    result = result_for()
    result.pages.pop()
    with pytest.raises(ValueError, match='페이지 수'):
        validate_copy(result, items)


def test_fixed_values_and_number_photo_assignment_are_preserved(tmp_path):
    service = Studio(tmp_path)
    service.save_cover_settings({'church': '가상 교회', 'location': '가상 홀', 'welcome': '환영합니다 :)', 'brand': 'YES!', 'motto': 'Ethos Spirit'})
    project = service.new_project('이번 주', date(2026, 11, 15))
    assert len(project.cards) == 1 and project.cards[0].data['worship']['church'] == '가상 교회'
    image = BytesIO()
    Image.new('RGB', (20, 20)).save(image, 'PNG')
    photo = service.upload('photo.png', image.getvalue())
    cards = cards_from_copy(parse_numbered(SOURCE), result_for(), {4: [photo['path']]}, tmp_path)
    saved = service.apply_numbered(project, cards)
    assert len(saved.cards) == 6
    assert saved.cards[0].id == project.cards[0].id
    assert saved.cards[-1].data['template'] == 'photo'
    assert saved.cards[-1].data['photos'][0]['path'] == photo['path']
    assert saved.cards[1].data['photos'] == []
    updated = service.apply_numbered(saved, cards[:2])
    assert len(updated.cards) == 3
    with service.connect() as db:
        previous = db.execute('SELECT payload FROM project_revisions WHERE project_id=? AND version=?', (saved.id, saved.version)).fetchone()
    assert len(json.loads(previous[0])['cards']) == 6


def test_explicit_fact_value_may_not_be_rewritten():
    items = parse_numbered('0. 모임 안내\n장소: 샘플홀\n시간: 오후 2시')
    result = CopyResult(pages=[{'number': 0, 'title': '모임', 'paragraphs': ['오후 2시에 다른홀에서 만나요.']}])
    with pytest.raises(ValueError, match='사실 정보'):
        validate_copy(result, items)


def test_mocked_gemini_copy_uses_style_examples_and_keeps_page_numbers(tmp_path):
    plan = make_plan('copy', 'test-model', SOURCE, [], tmp_path)
    calls = []
    def generate_content(**kwargs):
        calls.append(kwargs)
        assert kwargs['config'].response_schema is CopyResult
        assert '연습이 있습니다~' in kwargs['config'].system_instruction
        assert len(kwargs['contents']) == 1
        return SimpleNamespace(text=result_for().model_dump_json(), usage_metadata=None)
    response = execute_plan(plan, plan.digest(), client=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))
    assert response['needs_review'] and len(calls) == 1
    assert len(response['result']['pages']) == 5
