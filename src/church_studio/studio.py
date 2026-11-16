"""UI와 분리된 주간 프로젝트·업로드·생성·다운로드 서비스."""

import hashlib
import copy
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import date
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image
from pydantic import Field

from .models import Announcement, RenderOptions, StrictModel
from .paths import output_directory


def uid() -> str:
    return uuid4().hex


class Card(StrictModel):
    id: str = Field(default_factory=uid)
    data: dict
    enabled: bool = True
    reviewed: bool = False
    artifact: dict | None = None
    number: int | None = None
    source_text: str = ''
    review_notes: list[str] = Field(default_factory=list)


class Project(StrictModel):
    id: str = Field(default_factory=uid)
    name: str = Field(min_length=1, max_length=100)
    week: date
    cards: list[Card] = Field(default_factory=list)
    version: int = 0
    copied_from: str | None = None


class ProjectConflict(ValueError):
    pass


def empty_card(template='notice', week: date | None = None) -> Card:
    data = {'template': template, 'heading': '', 'title': '', 'paragraphs': [], 'facts': [], 'photos': [], 'footer': ''}
    if template == 'cover':
        data['worship'] = {'service_date': str(week or date.today()), 'service_time': '13:20:00',
            'church': '', 'location': '', 'welcome': '예배 자리에 오신 여러분을\n환영하고 축복합니다 :)',
            'song_list': [], 'service_order': [{'label': label, 'value': ''} for label in ['인도자', '기도', '성경봉독', '설교자']],
            'brand': 'YES!', 'motto': 'Ethos Spirit', 'confirmed': False}
    return Card(data=data)


def split_local_text(text: str) -> list[Card]:
    """빈 줄 또는 --- 단위로 사용자가 구분한 광고를 보존해서 가져온다. AI 분석이 아니다."""
    cards = []
    for block in re.split(r'\n\s*---\s*\n|\n\s*\n', text.strip()):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        card = empty_card()
        card.data.update(heading=lines[0], title=lines[0], paragraphs=['\n'.join(lines[1:])] if len(lines) > 1 else [])
        Announcement.model_validate(card.data)
        cards.append(card)
    if not cards:
        raise ValueError('광고 내용을 입력하세요.')
    if len(cards) > 30:
        raise ValueError('한 번에 30개 이하의 광고를 입력하세요.')
    return cards


def render_worker(ad: Announcement, root: Path, output: Path, options: RenderOptions) -> dict:
    """Streamlit의 Windows 이벤트 루프와 Chromium을 별도 프로세스로 격리한다."""
    source = output / 'source.json'
    source.write_text(ad.model_dump_json(indent=2), encoding='utf-8')
    command = [sys.executable, '-m', 'church_studio', '--root', str(root), 'render', str(source),
               '--output', str(output), '--name', 'slide', '--scale', str(options.scale)]
    if options.draft:
        command.append('--draft')
    for flag, value in [('--font', options.font), ('--bold-font', options.bold_font)]:
        if value:
            command.extend([flag, str(value)])
    result = subprocess.run(command, cwd=root, env={**os.environ, 'PYTHONUTF8': '1'},
                            capture_output=True, text=True, encoding='utf-8', timeout=180)
    if result.returncode:
        message = next((line for line in result.stderr.splitlines() if line.startswith('오류:')), '')
        raise ValueError(message or '이미지 생성에 실패했습니다. Chromium 설치와 글꼴을 확인하세요.')
    manifest = json.loads((output / 'slide.json').read_text(encoding='utf-8'))
    return {**manifest, 'png': str(output / 'slide.png')}


class Studio:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.folder = output_directory(self.root / 'outputs/studio', self.root)
        self.db = self.folder / 'studio.sqlite3'
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY, name TEXT, week TEXT, version INTEGER, payload TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
            db.execute('''CREATE TABLE IF NOT EXISTS uploads (
                id TEXT PRIMARY KEY, name TEXT, path TEXT, width INTEGER, height INTEGER)''')
            db.execute('''CREATE TABLE IF NOT EXISTS project_revisions (
                project_id TEXT, version INTEGER, payload TEXT,
                PRIMARY KEY(project_id,version))''')

    def connect(self):
        return sqlite3.connect(self.db, timeout=15)

    def cover_settings(self) -> dict:
        path = self.folder / 'cover-settings.json'
        if path.is_file():
            return json.loads(path.read_text(encoding='utf-8'))
        source = self.root / 'outputs/phase2-cover/cover-input.json'
        if source.is_file():
            data = json.loads(source.read_text(encoding='utf-8'))
            worship = data['worship']
            return {key: worship[key] for key in ['church', 'location', 'welcome', 'brand', 'motto']}
        return {'church': '', 'location': '', 'welcome': '예배 자리에 오신 여러분을\n환영하고 축복합니다 :)',
                'brand': 'YES!', 'motto': 'Ethos Spirit'}

    def save_cover_settings(self, settings: dict):
        from .models import ShortText
        from pydantic import TypeAdapter
        expected = {'church', 'location', 'welcome', 'brand', 'motto'}
        if set(settings) != expected or not all(isinstance(v, str) and v.strip() for v in settings.values()):
            raise ValueError('교회·장소·환영 문구·브랜드·슬로건을 모두 입력하세요.')
        for key in expected - {'welcome'}:
            TypeAdapter(ShortText).validate_python(settings[key])
        if len(settings['welcome']) > 200:
            raise ValueError('환영 문구는 200자 이하로 입력하세요.')
        path = self.folder / 'cover-settings.json'
        path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding='utf-8')

    def fixed_cover(self, week: date) -> Card:
        card = empty_card('cover', week)
        card.data.update(heading='YOUTH WORSHIP', title='청년 예배')
        card.data['worship'].update(self.cover_settings())
        return card

    def new_project(self, name: str, week: date) -> Project:
        return self.save(Project(name=name, week=week, cards=[self.fixed_cover(week)]))

    def apply_numbered(self, project: Project, cards: list[Card]) -> Project:
        """번호 목록을 교체한다. 이전 저장본과 표지·수동 광고는 보존한다."""
        numbers = [card.number for card in cards]
        if None in numbers or len(numbers) != len(set(numbers)):
            raise ValueError('광고 번호를 중복 없이 지정하세요.')
        updated = project.model_copy(deep=True)
        old_by_number = {card.number: card for card in updated.cards if card.number is not None}
        updated.cards = [card for card in updated.cards if card.number is None]
        first_cover = next((card for card in updated.cards if card.data.get('worship')), None)
        if first_cover is None:
            first_cover = self.fixed_cover(project.week)
            updated.cards.insert(0, first_cover)
        for incoming in cards:
            old = old_by_number.get(incoming.number)
            if old:
                incoming.id = old.id
            updated.cards.append(incoming)
        updated.cards = [first_cover, *[c for c in updated.cards if c.id != first_cover.id and c.number is None],
                         *sorted([c for c in updated.cards if c.number is not None], key=lambda c: c.number)]
        return self.save(updated)

    def save(self, project: Project) -> Project:
        updated = project.model_copy(deep=True)
        updated.version += 1
        with self.connect() as db:
            if project.version == 0:
                db.execute('INSERT INTO projects(id,name,week,version,payload) VALUES(?,?,?,?,?)',
                    (updated.id, updated.name, str(updated.week), updated.version, updated.model_dump_json()))
            else:
                db.execute('''INSERT OR IGNORE INTO project_revisions
                    SELECT id,version,payload FROM projects WHERE id=? AND version=?''', (project.id, project.version))
                cursor = db.execute('''UPDATE projects SET name=?,week=?,version=?,payload=?,updated_at=CURRENT_TIMESTAMP
                    WHERE id=? AND version=?''', (updated.name, str(updated.week), updated.version,
                                                updated.model_dump_json(), updated.id, project.version))
                if cursor.rowcount != 1:
                    raise ProjectConflict('다른 창에서 제작 내용이 바뀌었습니다. 제작 기록에서 최신 내용을 다시 여세요.')
        return updated

    def get(self, project_id: str) -> Project:
        with self.connect() as db:
            row = db.execute('SELECT payload FROM projects WHERE id=?', (project_id,)).fetchone()
        if row is None:
            raise ValueError('제작 기록을 찾을 수 없습니다.')
        return Project.model_validate_json(row[0])

    def projects(self) -> list[dict]:
        with self.connect() as db:
            return [dict(zip(['id', 'name', 'week', 'version', 'updated_at'], row)) for row in
                db.execute('SELECT id,name,week,version,updated_at FROM projects ORDER BY week DESC,updated_at DESC,id')]

    def clone(self, project: Project, name: str, week: date) -> Project:
        copied = Project(name=name, week=week, copied_from=project.id)
        for source in project.cards:
            card = source.model_copy(deep=True)
            card.id, card.reviewed = uid(), False
            if card.data.get('worship'):
                card.data['worship']['service_date'] = str(week)
                card.data['worship']['confirmed'] = False
                card.artifact = None
            copied.cards.append(card)
        return self.save(copied)

    def upload(self, name: str, content: bytes) -> dict:
        if not content or len(content) > 20 * 1024 * 1024:
            raise ValueError('사진은 비어 있지 않은 20 MB 이하 파일이어야 합니다.')
        with Image.open(BytesIO(content)) as image:
            image.verify()
        with Image.open(BytesIO(content)) as image:
            if image.width * image.height > 40_000_000:
                raise ValueError('사진은 4천만 화소 이하로 준비하세요.')
            extension = {'PNG': '.png', 'JPEG': '.jpg', 'WEBP': '.webp'}.get(image.format)
            if not extension:
                raise ValueError('PNG/JPG/WebP 사진을 사용하세요.')
            width, height = image.size
        digest = hashlib.sha256(content).hexdigest()
        path = output_directory(self.folder / 'uploads', self.root) / (digest + extension)
        if not path.exists():
            with path.open('xb') as stream:
                stream.write(content)
        # 파일 이름은 표시용으로만 저장한다. 저장 경로에는 업로드 이름을 쓰지 않는다.
        name = name.replace('\\', '/').split('/')[-1][:160]
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO uploads VALUES(?,?,?,?,?)', (digest, name, str(path), width, height))
        return {'id': digest, 'name': name, 'path': str(path), 'width': width, 'height': height}

    def uploads(self) -> list[dict]:
        with self.connect() as db:
            return [dict(zip(['id', 'name', 'path', 'width', 'height'], row)) for row in
                    db.execute('SELECT id,name,path,width,height FROM uploads ORDER BY rowid DESC')]

    def validate_paths(self, ad: Announcement):
        for path in [*(photo.path for photo in ad.photos), ad.logo, ad.background]:
            if not path:
                continue
            absolute = (self.root / path).resolve() if not path.is_absolute() else path.resolve()
            if not any(absolute.is_relative_to((self.root / area).resolve()) for area in ['data', 'outputs']):
                raise ValueError('사진·로고·배경은 프로젝트 사진 보관함 또는 data 자료를 사용하세요.')
            if not absolute.is_file():
                raise ValueError(f'사진·로고·배경 파일이 없습니다: {path.name}')

    def fingerprint(self, data: dict, options: dict) -> str:
        ad = Announcement.model_validate(data)
        self.validate_paths(ad)
        content = {'input': ad.model_dump(mode='json'), 'options': options, 'assets': {}}
        for path in [*(photo.path for photo in ad.photos), ad.logo, ad.background]:
            if path:
                full = (self.root / path).resolve()
                content['assets'][str(path)] = hashlib.sha256(full.read_bytes()).hexdigest()
        return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()

    def fixed_data(self, data: dict) -> dict:
        data = copy.deepcopy(data)
        if data.get('worship'):
            data.update(template='cover', heading='YOUTH WORSHIP', title='청년 예배', paragraphs=[], facts=[], footer='')
            data['worship'].update(self.cover_settings())
            values = {item['label']: item['value'] for item in data['worship']['service_order']}
            data['worship']['service_order'] = [{'label': label, 'value': values.get(label, '')}
                for label in ['인도자', '기도', '성경봉독', '설교자']]
        return data

    def current(self, card: Card) -> bool:
        if not card.artifact:
            return False
        try:
            if self.fixed_data(card.data) != card.data:
                return False
            return (card.artifact['fingerprint'] == self.fingerprint(card.data, card.artifact['options'])
                    and self.result_path(card.artifact['png']).is_file())
        except (ValueError, OSError, KeyError):
            return False

    def result_path(self, raw: str) -> Path:
        path = Path(raw).resolve()
        if not path.is_relative_to((self.root / 'outputs').resolve()):
            raise ValueError('생성 이미지 경로가 잘못되었습니다.')
        return path

    def generate(self, card: Card, options: RenderOptions, *, renderer=render_worker) -> Card:
        data = self.fixed_data(card.data)
        ad = Announcement.model_validate(data)
        self.validate_paths(ad)
        output = output_directory(self.folder / 'renders' / uid(), self.root)
        manifest = renderer(ad, self.root, output, options)
        png = self.result_path(manifest['png'])
        jpg = png.with_suffix('.jpg')
        with Image.open(png) as image:
            image.convert('RGB').save(jpg, 'JPEG', quality=95, subsampling=0)
        result = card.model_copy(deep=True)
        result.data = data
        opts = options.model_dump(mode='json')
        result.artifact = {'png': str(png), 'jpg': str(jpg), 'options': opts,
                           'fingerprint': self.fingerprint(data, opts),
                           'draft': options.draft, 'warnings': manifest.get('warnings', [])}
        return result

    def download(self, card: Card, kind='PNG', *, allow_draft=False) -> bytes:
        if kind not in {'PNG', 'JPG'}:
            raise ValueError('PNG 또는 JPG를 선택하세요.')
        if not card.reviewed or not self.current(card):
            raise ValueError('검토를 완료하고 현재 내용으로 이미지를 생성하세요.')
        if card.artifact['draft'] and not allow_draft:
            raise ValueError('초안은 송출본 전체 다운로드에 포함할 수 없습니다.')
        return self.result_path(card.artifact[kind.lower()]).read_bytes()

    def bundle(self, project: Project, kind='PNG') -> bytes:
        cards = [card for card in project.cards if card.enabled]
        if not cards:
            raise ValueError('출력할 광고가 없습니다.')
        buffer = BytesIO()
        with ZipFile(buffer, 'w', ZIP_DEFLATED) as archive:
            for index, card in enumerate(cards, 1):
                content = self.download(card, kind)
                archive.writestr(f'{index:02d}-{card.data.get("template", "notice")}.{kind.lower()}', content)
        return buffer.getvalue()
