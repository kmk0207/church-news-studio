"""원본 보존, 입력 오류, 비율과 이스케이프를 검증한다."""

import base64
import hashlib
import json
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from church_studio.analysis import inspect_archive
from church_studio.cli import main
from church_studio.images import image_data
from church_studio.models import Announcement, RenderOptions
from church_studio.paths import output_directory
from church_studio.render import build_html, render_announcement


def announcement(**overrides):
    return Announcement(heading='가상 샘플', title='한글 광고', **overrides)


def test_input_validation_and_no_historical_defaults():
    ad = announcement()
    assert ad.facts == [] and ad.photos == [] and ad.footer == ''
    with pytest.raises(ValidationError):
        Announcement(heading=' ', title='비어 있는 제목')
    with pytest.raises(ValidationError):
        announcement(template='photo')
    with pytest.raises(ValidationError):
        announcement(unknown='입력 오타')
    with pytest.raises(ValidationError):
        announcement(photos=[{'path': 'photo.png'}])
    with pytest.raises(ValidationError):
        announcement(template='photo', photos=[{'path': 'photo.png', 'zoom': float('nan')}])


def test_output_protects_data_and_path_traversal(tmp_path):
    for path in [tmp_path / 'data/archive', tmp_path / 'outputs/../../elsewhere']:
        with pytest.raises(ValueError):
            output_directory(path, tmp_path)
    assert output_directory(tmp_path / 'outputs/demo', tmp_path).is_dir()
    with pytest.raises(ValueError):
        render_announcement(announcement(), tmp_path, tmp_path / 'outputs', name='../data')


def test_analyzer_handles_duplicates_corrupt_files_and_preserves_originals(tmp_path):
    archive = tmp_path / 'data/archive/week01'
    archive.mkdir(parents=True)
    Image.new('RGB', (192, 108), '#ffffff').save(archive / 'a.png')
    (archive / 'b.png').write_bytes((archive / 'a.png').read_bytes())
    (archive / 'broken.png').write_bytes(b'')
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in archive.iterdir()}
    report = inspect_archive(archive.parent, tmp_path, tmp_path / 'outputs/analysis')
    assert report['file_count'] == 2
    assert report['unique_count'] == 1
    assert len(report['errors']) == 1
    assert report['resolutions'] == {'192x108': 2}
    assert before == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in archive.iterdir()}
    assert (tmp_path / 'outputs/analysis/contact-sheet.jpg').is_file()


def test_crop_focus_preserves_aspect_and_original(tmp_path):
    path = tmp_path / 'photo.png'
    image = Image.new('RGB', (300, 100), 'red')
    image.paste(Image.new('RGB', (100, 100), 'blue'), (200, 0))
    image.save(path)
    before = path.read_bytes()
    uri = image_data(path, (100, 100), focal_x=1)
    result = Image.open(BytesIO(base64.b64decode(uri.split(',')[1]))).convert('RGB')
    assert result.size == (100, 100)
    assert result.getpixel((50, 50)) == (0, 0, 255)
    assert path.read_bytes() == before


def test_exif_orientation_is_applied(tmp_path):
    path = tmp_path / 'rotated.jpg'
    image = Image.new('RGB', (120, 60), 'red')
    exif = Image.Exif()
    exif[274] = 6
    image.save(path, exif=exif)
    uri = image_data(path, (120, 120), contain=True)
    result = Image.open(BytesIO(base64.b64decode(uri.split(',')[1])))
    assert result.size == (60, 120)


def test_html_escapes_content_and_retains_literal_text(tmp_path):
    html, fonts = build_html(announcement(paragraphs=['<script>alert(1)</script>', '정확한 문구 & 날짜 미정']), tmp_path, RenderOptions())
    assert '<script>alert' not in html
    assert '&lt;script&gt;' in html and '정확한 문구 &amp; 날짜 미정' in html
    assert 'http://' not in html and 'https://' not in html
    assert fonts['regular']


def test_cli_bad_json_and_missing_archive_return_failure(tmp_path, capsys):
    (tmp_path / 'bad.json').write_text('{"title":"필수 heading 누락"}', encoding='utf-8')
    assert main(['--root', str(tmp_path), 'render', 'bad.json']) == 1
    assert '오류:' in capsys.readouterr().err
    assert main(['--root', str(tmp_path), 'analyze']) == 1


def test_cli_help_is_compatible_with_windows_console(capsys):
    with pytest.raises(SystemExit) as exc:
        main(['--help'])
    assert exc.value.code == 0
    text = capsys.readouterr().out
    assert 'Church Studio' in text
    # Windows 기본 cp949 콘솔에서 도움말이 인코딩 오류 없이 출력되어야 한다.
    text.encode('cp949')


def test_existing_output_refused_before_render(tmp_path):
    output = tmp_path / 'outputs/test'
    output.mkdir(parents=True)
    existing = output / 'announcement.png'
    existing.write_bytes('보존'.encode('utf-8'))
    with pytest.raises(FileExistsError):
        render_announcement(announcement(), tmp_path, output)
    assert existing.read_bytes() == '보존'.encode('utf-8')
