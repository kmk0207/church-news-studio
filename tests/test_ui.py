"""실제 Streamlit 위젯으로 로컬 제작 흐름을 검사한다. API는 호출하지 않는다."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from church_studio.studio import Studio


def app(tmp_path):
    script = f'from pathlib import Path\nfrom church_studio.ui import main\nmain(Path({str(tmp_path)!r}))'
    return AppTest.from_string(script, default_timeout=30).run()


def by_label(elements, label):
    return next(element for element in elements if element.label == label)


def start(at):
    by_label(at.button, '새 작업 시작').click().run()
    assert not at.exception


def test_start_edit_save_and_reopen_project(tmp_path):
    at = app(tmp_path)
    assert not at.exception
    start(at)
    by_label(at.button, '텍스트 공지 추가').click().run()
    by_label(at.text_input, '상단 안내').set_value('01 주간 안내')
    by_label(at.text_input, '제목').set_value('테스트 광고')
    by_label(at.text_area, '본문 · 빈 줄로 문단 구분').set_value('가상 안내입니다.')
    by_label(at.checkbox, '내용과 날짜·장소·담당자를 확인했습니다').check()
    by_label(at.button, '변경 사항 저장').click().run()
    assert not at.exception
    records = Studio(tmp_path).projects()
    saved = Studio(tmp_path).get(records[0]['id'])
    assert saved.cards[-1].data['title'] == '테스트 광고'
    assert saved.cards[-1].reviewed is True
    reopened = app(tmp_path)
    assert not reopened.exception
    assert saved.cards[0].data['template'] == 'cover'


def test_local_multiple_input_and_history_copy(tmp_path):
    at = app(tmp_path)
    start(at)
    by_label(at.text_area, '이번 주 광고 원문').set_value('0. 첫 광고\n내용 하나\n1. 둘째 광고\n내용 둘').run()
    by_label(at.button, '번호별 광고 만들기 · 기본 말투').click().run()
    assert not at.exception
    assert len(Studio(tmp_path).get(Studio(tmp_path).projects()[0]['id']).cards) == 3
    by_label(at.radio, '작업 메뉴').set_value('제작 기록').run()
    by_label(at.button, '새 주로 복사').click().run()
    assert not at.exception
    assert len(Studio(tmp_path).projects()) == 2
    assert by_label(at.radio, '작업 메뉴').value == '광고 편집'


def test_cover_editor_keeps_all_service_rows_between_reruns(tmp_path):
    at = app(tmp_path)
    start(at)
    assert len([field for field in at.text_input if field.label.startswith('담당 / 본문')]) == 4
    by_label(at.text_input, '담당 / 본문 1').set_value('가상 인도자').run()
    assert not at.exception
    assert len([field for field in at.text_input if field.label.startswith('담당 / 본문')]) == 4
    by_label(at.radio, '작업 메뉴').set_value('사진 보관함').run()
    by_label(at.radio, '작업 메뉴').set_value('광고 편집').run()
    assert by_label(at.text_input, '담당 / 본문 1').value == '가상 인도자'


def test_cover_fields_are_locked_and_only_one_cover_is_created(tmp_path):
    at = app(tmp_path)
    start(at)
    assert by_label(at.text_input, '제목').disabled
    assert by_label(at.text_input, '상단 안내').disabled
    assert all(field.disabled for field in at.text_input if field.label.startswith('순서 '))
    assert not any(button.label == '예배 표지 추가' for button in at.button)
    saved = Studio(tmp_path).get(Studio(tmp_path).projects()[0]['id'])
    assert len(saved.cards) == 1 and saved.cards[0].enabled


def test_numbered_intake_creates_five_pages_and_exact_photo_assignment(tmp_path):
    from io import BytesIO
    from PIL import Image
    from test_briefs import SOURCE
    image = BytesIO()
    Image.new('RGB', (100, 80), 'blue').save(image, 'PNG')
    asset = Studio(tmp_path).upload('배드민턴 샘플.png', image.getvalue())
    at = app(tmp_path)
    start(at)
    by_label(at.text_area, '이번 주 광고 원문').set_value(SOURCE).run()
    target = next(field for field in at.multiselect if field.label.startswith('4번 사진'))
    target.set_value([asset['path']]).run()
    by_label(at.button, '번호별 광고 만들기 · 기본 말투').click().run()
    assert not at.exception
    saved = Studio(tmp_path).get(Studio(tmp_path).projects()[0]['id'])
    assert len(saved.cards) == 6
    assert [card.number for card in saved.cards[1:]] == [0, 1, 2, 3, 4]
    assert saved.cards[4].data['photos'] == []
    assert saved.cards[5].data['photos'][0]['path'] == asset['path']
