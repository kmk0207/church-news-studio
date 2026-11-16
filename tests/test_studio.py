"""주간 저장·복사·다운로드의 실제 사용자 오류를 검사한다."""

from datetime import date
from io import BytesIO
from zipfile import ZipFile

import pytest
from PIL import Image

from church_studio.models import RenderOptions
from church_studio.studio import Card, Project, ProjectConflict, Studio, empty_card, split_local_text


def png_bytes(color='blue'):
    stream = BytesIO()
    Image.new('RGB', (160, 90), color).save(stream, 'PNG')
    return stream.getvalue()


def notice():
    card = empty_card()
    card.data.update(heading='주간 안내', title='가상 광고', paragraphs=['가상 안내 본문'])
    card.reviewed = True
    return card


def fake_renderer(ad, root, output, options):
    path = output / 'slide.png'
    path.write_bytes(png_bytes())
    return {'png': str(path), 'warnings': []}


def test_project_survives_restart_and_detects_concurrent_edits(tmp_path):
    service = Studio(tmp_path)
    project = service.save(Project(name='이번 주', week=date(2026, 11, 15), cards=[notice()]))
    stale = project.model_copy(deep=True)
    project.name = '새 이름'
    saved = service.save(project)
    assert Studio(tmp_path).get(saved.id).name == '새 이름'
    with pytest.raises(ProjectConflict):
        service.save(stale)


def test_upload_validates_bytes_deduplicates_and_ignores_traversal_name(tmp_path):
    service = Studio(tmp_path)
    first = service.upload('../../secret.png', png_bytes())
    second = service.upload('different.png', png_bytes())
    assert first['path'] == second['path']
    assert len(service.uploads()) == 1
    assert service.result_path(first['path']).is_file()
    with pytest.raises(OSError):
        service.upload('not-a-photo.png', b'not a photo')


def test_copy_keeps_unchanged_images_but_requires_fact_review(tmp_path):
    service = Studio(tmp_path)
    card = service.generate(notice(), RenderOptions(), renderer=fake_renderer)
    source = service.save(Project(name='지난주', week=date(2026, 11, 15), cards=[card]))
    copied = service.clone(source, '이번 주', date(2026, 11, 22))
    assert copied.id != source.id and copied.cards[0].id != source.cards[0].id
    assert service.current(copied.cards[0])
    assert copied.cards[0].artifact == source.cards[0].artifact
    assert not copied.cards[0].reviewed
    with pytest.raises(ValueError, match='검토'):
        service.bundle(copied)
    assert service.get(source.id).cards[0].reviewed is True


def test_copied_worship_date_changes_and_invalidates_output(tmp_path):
    service = Studio(tmp_path)
    card = empty_card('cover', date(2026, 11, 15))
    card.data['worship']['confirmed'] = True
    card.artifact = {'png': 'old-image'}
    source = Project(name='원본', week=date(2026, 11, 15), cards=[card])
    copied = service.clone(source, '새 주', date(2026, 11, 22))
    assert copied.cards[0].data['worship']['service_date'] == '2026-11-22'
    assert copied.cards[0].data['worship']['confirmed'] is False
    assert copied.cards[0].artifact is None
    assert source.cards[0].data['worship']['service_date'] == '2026-11-15'


def test_edited_text_and_replaced_asset_block_stale_downloads(tmp_path):
    service = Studio(tmp_path)
    card = service.generate(notice(), RenderOptions(), renderer=fake_renderer)
    assert service.current(card)
    card.data['title'] = '수정한 제목'
    assert not service.current(card)
    with pytest.raises(ValueError):
        service.download(card)
    photo = service.upload('a.png', png_bytes())
    card = notice()
    card.data.update(template='photo', photos=[{'path': photo['path']}])
    card = service.generate(card, RenderOptions(), renderer=fake_renderer)
    assert service.current(card)
    service.result_path(photo['path']).write_bytes(png_bytes('red'))
    assert not service.current(card)


def test_bundle_order_png_jpg_and_draft_exclusion(tmp_path):
    service = Studio(tmp_path)
    card = service.generate(notice(), RenderOptions(), renderer=fake_renderer)
    disabled = notice()
    disabled.enabled = False
    project = Project(name='가상', week=date(2026, 11, 15), cards=[card, disabled])
    with ZipFile(BytesIO(service.bundle(project, 'JPG'))) as archive:
        assert archive.namelist() == ['01-notice.jpg']
        assert Image.open(BytesIO(archive.read('01-notice.jpg'))).format == 'JPEG'
    card = service.generate(card, RenderOptions(draft=True), renderer=fake_renderer)
    assert service.download(card, allow_draft=True)
    with pytest.raises(ValueError, match='초안'):
        service.bundle(Project(name='가상', week=date(2026, 11, 15), cards=[card]))


def test_manual_split_preserves_text_and_does_not_invent_information():
    cards = split_local_text('첫 광고\n첫 안내문\n\n두 번째 광고\n둘째 안내문')
    assert len(cards) == 2
    assert cards[0].data['paragraphs'] == ['첫 안내문']
    assert cards[1].data['facts'] == []
    assert not cards[0].reviewed


@pytest.mark.integration
def test_real_streamlit_render_worker_creates_images_and_zip(tmp_path):
    # 서비스 루트와 Python 패키지 위치가 달라도 격리 프로세스가 실행되어야 한다.
    service = Studio(tmp_path)
    card = service.generate(notice(), RenderOptions())
    project = Project(name='송출 테스트', week=date(2026, 11, 15), cards=[card])
    with Image.open(service.result_path(card.artifact['png'])) as image:
        assert image.size == (1920, 1080)
    assert service.bundle(project)
