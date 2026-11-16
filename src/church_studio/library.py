"""SQLite 스타일 라이브러리와 로컬 NumPy 유사도 검색. 과거 본문은 추천에 넣지 않는다."""

import hashlib
import json
import re
import sqlite3
from pathlib import Path

import numpy as np

from .ai_models import StyleProfile
from .paths import asset_path, output_directory


class LocalNgramEncoder:
    """모델 없이 쓰는 문자 n-gram 검색. 의미 임베딩이 아닌 명시적 대안이다."""

    identity = 'local-char-ngram-sha256-1024-v1'

    def encode(self, texts: list[str]) -> np.ndarray:
        matrix = np.zeros((len(texts), 1024), dtype=np.float32)
        for i, text in enumerate(texts):
            text = re.sub(r'\s+', '', text.lower())
            for size in [2, 3]:
                for j in range(max(0, len(text) - size + 1)):
                    key = hashlib.sha256(text[j:j + size].encode('utf-8')).digest()
                    matrix[i, int.from_bytes(key[:4], 'big') % 1024] += 1
        return matrix


class SentenceEncoder:
    """이미 내려받은 모델 폴더만 사용한다. 자동 네트워크 다운로드는 없다."""

    def __init__(self, model_path: Path):
        if not model_path.is_dir():
            raise ValueError('로컬 Sentence Transformers 모델 폴더를 지정하세요.')
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(str(model_path.resolve()), local_files_only=True, trust_remote_code=False)
        self.identity = 'sentence-transformers:' + str(model_path.resolve())

    def encode(self, texts: list[str]) -> np.ndarray:
        return np.asarray(self.model.encode(texts, normalize_embeddings=True, convert_to_numpy=True), dtype=np.float32)


class StyleLibrary:
    def __init__(self, root: Path, db: Path | None = None, *, encoder=None):
        self.root = root.resolve()
        self.path = db or self.root / 'outputs/library/styles.sqlite3'
        folder = output_directory(self.path.parent, self.root)
        self.path = folder / self.path.name
        # DB 파일 자체가 원본 영역 등을 가리키는 링크인 경우도 거부한다.
        if not self.path.resolve().is_relative_to((self.root / 'outputs').resolve()):
            raise ValueError('DB는 outputs/ 내부에 저장하세요.')
        self.encoder = encoder or LocalNgramEncoder()
        with self.connect() as connection:
            connection.execute('''CREATE TABLE IF NOT EXISTS styles (
                image_hash TEXT PRIMARY KEY, image_path TEXT NOT NULL,
                profile TEXT NOT NULL, summary TEXT NOT NULL, embedding BLOB NOT NULL,
                dimensions INTEGER NOT NULL, encoder TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')

    def connect(self):
        return sqlite3.connect(self.path)

    def add(self, image: Path, profile: StyleProfile, *, reviewed: bool) -> str:
        if not reviewed:
            raise ValueError('개인정보와 과거 사실이 없는 디자인 프로필을 검토한 뒤 등록하세요.')
        image = asset_path(image, self.root)
        digest = hashlib.sha256(image.read_bytes()).hexdigest()
        summary = ' '.join([profile.template, profile.layout, profile.typography, profile.tone, *profile.colors])
        vector = self.encoder.encode([summary])[0].astype('<f4')
        if not np.isfinite(vector).all() or vector.ndim != 1 or not vector.size:
            raise ValueError('검색 벡터가 올바르지 않습니다.')
        with self.connect() as connection:
            connection.execute('''INSERT INTO styles(image_hash,image_path,profile,summary,embedding,dimensions,encoder)
                VALUES(?,?,?,?,?,?,?) ON CONFLICT(image_hash) DO UPDATE SET
                image_path=excluded.image_path,profile=excluded.profile,summary=excluded.summary,
                embedding=excluded.embedding,dimensions=excluded.dimensions,encoder=excluded.encoder,
                updated_at=CURRENT_TIMESTAMP''',
                (digest, str(image), profile.model_dump_json(), summary, vector.tobytes(), vector.size, self.encoder.identity))
        return digest

    def search(self, query: str, *, limit=3) -> list[dict]:
        if not query.strip() or not 1 <= limit <= 20:
            raise ValueError('검색어와 1~20 사이의 결과 수를 입력하세요.')
        with self.connect() as connection:
            rows = connection.execute('SELECT image_hash,image_path,profile,embedding,dimensions FROM styles WHERE encoder=?', (self.encoder.identity,)).fetchall()
        if not rows:
            return []
        query_vector = self.encoder.encode([query])[0]
        found = []
        for digest, path, raw, blob, size in rows:
            vector = np.frombuffer(blob, dtype='<f4')
            if vector.shape != query_vector.shape:
                raise ValueError('검색 모델 차원이 변경되었습니다. 라이브러리를 재등록하세요.')
            denominator = float(np.linalg.norm(query_vector) * np.linalg.norm(vector))
            score = float(np.dot(query_vector, vector) / denominator) if denominator else 0.0
            if score > 0:
                profile = StyleProfile.model_validate_json(raw)
                found.append({'image_hash': digest, 'reference': path, 'score': round(score, 6),
                              'template': profile.template, 'style': profile.model_dump(),
                              'encoder': self.encoder.identity})
        return sorted(found, key=lambda item: (-item['score'], item['image_hash']))[:limit]


def recommend_template(*, category: str, photo_count: int, worship=False) -> dict:
    """초기 규칙 추천. 라이브러리 검색과 AI 추천보다 렌더링 제약을 우선한다."""
    if not 0 <= photo_count <= 3:
        raise ValueError('사진 수는 0~3 사이여야 합니다.')
    if worship:
        return {'template': 'cover', 'reason': '예배 표지: 중앙 사진 1장과 Song List·예배 순서',
                'needs_review': photo_count != 1}
    template = 'photo' if photo_count else 'notice'
    return {'template': template, 'reason': f'{category}: 사진 {photo_count}장에 맞춘 구성', 'needs_review': False}
