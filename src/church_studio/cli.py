"""로컬 제작 및 승인된 AI 작업용 명령행 도구. 자료 경로는 --root 기준이다."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from playwright.sync_api import Error as PlaywrightError

from .analysis import inspect_archive
from .demo import run_demo
from .models import Announcement, RenderOptions
from .render import render_announcement


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Church Studio - 로컬 광고 PNG 제작')
    parser.add_argument('--root', type=Path, default=Path.cwd(), help='프로젝트 루트 (기본: 현재 폴더)')
    sub = parser.add_subparsers(dest='command', required=True)
    from .phase2_cli import add_commands
    add_commands(sub)
    analyze = sub.add_parser('analyze', help='이미지 해상도·색상·중복과 연락시트 생성')
    analyze.add_argument('--archive', type=Path, default=Path('data/archive'))
    analyze.add_argument('--output', type=Path, default=Path('outputs/analysis'))
    render = sub.add_parser('render', help='JSON 광고 → PNG/HTML/기록')
    render.add_argument('input', type=Path)
    render.add_argument('--name', default='announcement')
    demo = sub.add_parser('demo', help='가상 광고 3종과 테스트 사진 생성')
    for command in [render, demo]:
        command.add_argument('--draft', action='store_true', help='미입력 사진·곡명이 있는 표지를 초안으로 출력')
        command.add_argument('--output', type=Path, help='outputs/ 내부 결과 폴더 (기본: 새 실행 폴더)')
        command.add_argument('--font', type=Path, help='사용 권한을 확인한 한글 TTF/OTF')
        command.add_argument('--bold-font', type=Path)
        command.add_argument('--scale', type=int, choices=[1, 2], default=1, help='1: 1920×1080, 2: 3840×2160')
    args = parser.parse_args(argv)
    root = args.root.resolve()

    def resolve(path):
        return (root / path).resolve() if not path.is_absolute() else path.resolve()

    try:
        if args.command in {'ai-plan', 'ai-run', 'ai-drafts', 'style-add', 'recommend'}:
            from .phase2_cli import run_command
            print(json.dumps(run_command(args, root), ensure_ascii=False, indent=2))
            return 0
        if args.command == 'analyze':
            report = inspect_archive(resolve(args.archive), root, resolve(args.output))
            print(json.dumps({key: report[key] for key in ['file_count', 'unique_count', 'resolutions', 'errors']}, ensure_ascii=False, indent=2))
            return 1 if report['errors'] else 0
        options = RenderOptions(scale=args.scale, font=args.font, bold_font=args.bold_font, draft=args.draft)
        # 날짜가 광고 본문으로 유입되지 않도록 실행 폴더 이름에만 사용한다.
        try:
            now = datetime.now(ZoneInfo('Asia/Seoul'))
        except ZoneInfoNotFoundError:
            from datetime import timedelta, timezone
            now = datetime.now(timezone(timedelta(hours=9)))
        output = resolve(args.output or Path('outputs') / now.strftime('%Y%m%d-%H%M%S-%f'))
        if args.command == 'demo':
            results = run_demo(root, output, options)
        else:
            ad = Announcement.model_validate_json(resolve(args.input).read_text(encoding='utf-8-sig'))
            results = [render_announcement(ad, root, output, name=args.name, options=options)]
        for result in results:
            print(json.dumps({key: result[key] for key in ['png', 'width', 'height', 'font_scale', 'elapsed_seconds']}, ensure_ascii=False))
        return 0
    except (ValueError, OSError, PlaywrightError) as exc:
        print(f'오류: {exc}', file=sys.stderr)
        if isinstance(exc, PlaywrightError):
            print('Chromium 미설치라면 python -m playwright install chromium을 실행하세요.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
