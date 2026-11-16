"""Phase 2 하위 명령. 전송 계획 생성은 로컬 작업이며 실행과 분리한다."""

import json
from pathlib import Path

from .ai_models import StyleProfile
from .gemini import TransferPlan, execute_plan, make_plan
from .library import SentenceEncoder, StyleLibrary
from .paths import output_directory


def add_commands(sub):
    plan = sub.add_parser('ai-plan', help='Gemini 전송 대상 검토용 계획 생성 (전송 안 함)')
    plan.add_argument('--operation', choices=['structure', 'style', 'copy'], required=True)
    plan.add_argument('--model', required=True, help='사용할 Gemini 모델 ID를 명시')
    plan.add_argument('--text', type=Path)
    plan.add_argument('--images', type=Path, nargs='*', default=[])
    plan.add_argument('--photo-ids', nargs='*', default=[])
    plan.add_argument('--output', type=Path, required=True, help='outputs/ 내부의 새 JSON 경로')
    run = sub.add_parser('ai-run', help='검토 후 정확한 SHA-256을 승인한 계획만 외부 전송')
    run.add_argument('--plan', type=Path, required=True)
    run.add_argument('--approve-sha256', required=True)
    run.add_argument('--output', type=Path, required=True)
    add = sub.add_parser('style-add', help='검토한 스타일 프로필과 원본 참조를 로컬 DB에 등록')
    add.add_argument('--image', type=Path, required=True)
    add.add_argument('--profile', type=Path, required=True)
    add.add_argument('--reviewed', action='store_true')
    search = sub.add_parser('recommend', help='로컬 스타일 유사도 검색')
    search.add_argument('query')
    search.add_argument('--limit', type=int, default=3)
    drafts = sub.add_parser('ai-drafts', help='검토용 구조화 응답을 광고 JSON으로 변환 (API 호출 안 함)')
    drafts.add_argument('--plan', type=Path, required=True)
    drafts.add_argument('--response', type=Path, required=True)
    drafts.add_argument('--photo-map', type=Path, help='사진 ID를 로컬 파일 경로에 연결한 JSON 객체')
    drafts.add_argument('--output', type=Path, required=True, help='outputs/ 내부 새 폴더')
    for parser in [add, search]:
        parser.add_argument('--db', type=Path, default=Path('outputs/library/styles.sqlite3'))
        parser.add_argument('--embedding-model', type=Path, help='선택: 다운로드가 완료된 로컬 Sentence Transformers 폴더')


def run_command(args, root: Path):
    def resolve(path):
        return (root / path).resolve() if not path.is_absolute() else path.resolve()

    def save(path, data):
        path = resolve(path)
        output_directory(path.parent, root)
        # 최종 파일이 원본을 가리키는 링크인 경우도 거부한다.
        if not path.is_relative_to((root / 'outputs').resolve()):
            raise ValueError('결과는 outputs/ 내부에 저장하세요.')
        with path.open('x', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)

    if args.command == 'ai-plan':
        text = resolve(args.text).read_text(encoding='utf-8-sig') if args.text else ''
        plan = make_plan(args.operation, args.model, text, args.images, root, args.photo_ids)
        save(args.output, {'plan': plan.model_dump(mode='json'), 'sha256': plan.digest(),
                           'notice': '이 파일의 텍스트·이미지 목록·모델을 검토하세요. 아직 전송하지 않았습니다.'})
        return {'plan': str(args.output), 'sha256': plan.digest(), 'sent': False}
    if args.command == 'ai-run':
        output = resolve(args.output)
        output_directory(output.parent, root)
        if output.exists():
            raise FileExistsError('기존 결과가 있습니다. 새 출력 파일을 지정하세요.')
        raw = json.loads(resolve(args.plan).read_text(encoding='utf-8-sig'))
        plan = TransferPlan.model_validate(raw['plan'])
        result = execute_plan(plan, args.approve_sha256)
        save(args.output, result)
        return {'output': str(args.output), 'needs_review': True, 'usage': result['usage']}
    if args.command == 'ai-drafts':
        from .ai_models import StructureResult
        from .workflow import prepare_drafts
        plan = TransferPlan.model_validate(json.loads(resolve(args.plan).read_text(encoding='utf-8-sig'))['plan'])
        if plan.operation != 'structure':
            raise ValueError('광고 구조화 계획을 지정하세요.')
        raw = json.loads(resolve(args.response).read_text(encoding='utf-8-sig'))
        if raw.get('transfer_sha256') != plan.digest():
            raise ValueError('구조화 응답과 입력 계획이 일치하지 않습니다.')
        photos = json.loads(resolve(args.photo_map).read_text(encoding='utf-8-sig')) if args.photo_map else {}
        if not isinstance(photos, dict) or not set(photos).issubset(plan.photo_ids):
            raise ValueError('사진 연결은 계획에 등록한 ID와 경로의 객체여야 합니다.')
        result = StructureResult.model_validate(raw['result'])
        review = prepare_drafts(result, plan.text, photos, root)
        output = resolve(args.output)
        output_directory(output, root)
        targets = [output / (item['name'] + '.json') for item in review['drafts']] + [output / 'review.json']
        if any(path.exists() for path in targets):
            raise FileExistsError('새 출력 폴더를 사용하세요.')
        for item, path in zip(review['drafts'], targets):
            save(path, item['input'])
        save(targets[-1], review)
        return {'output': str(args.output), 'count': len(review['drafts']), 'needs_review': True}
    encoder = SentenceEncoder(resolve(args.embedding_model)) if args.embedding_model else None
    library = StyleLibrary(root, resolve(args.db), encoder=encoder)
    if args.command == 'style-add':
        profile = StyleProfile.model_validate_json(resolve(args.profile).read_text(encoding='utf-8-sig'))
        return {'image_hash': library.add(args.image, profile, reviewed=args.reviewed)}
    return {'results': library.search(args.query, limit=args.limit), 'note': '과거 사실을 복사하지 않고 디자인만 참고하세요.'}
