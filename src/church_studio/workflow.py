"""검토용 AI 결과를 기존 렌더러가 읽는 JSON으로 연결한다."""

from pathlib import Path

from .ai_models import StructureResult, validate_evidence
from .library import recommend_template
from .models import Announcement
from .paths import asset_path


def prepare_drafts(result: StructureResult, source: str, photo_map: dict[str, str], root: Path) -> dict:
    warnings = validate_evidence(result, source, list(photo_map))
    drafts = []
    for index, item in enumerate(result.announcements, 1):
        paths = [asset_path(Path(photo_map[key]), root) for key in item.photo_ids]
        recommendation = recommend_template(category=item.category, photo_count=len(paths))
        # 예배 표지의 날짜·곡·담당자는 별도 명시 입력이 필요하므로 추정해 채우지 않는다.
        if item.suggested_template == 'cover':
            warnings.append(f'{index}번: 예배 표지의 날짜·곡명·예배 순서는 수동 확인 후 입력하세요.')
        ad = Announcement(template=recommendation['template'], heading=item.title, title=item.title,
            paragraphs=item.paragraphs, facts=[{'label': f.label, 'value': f.value} for f in item.facts],
            photos=[{'path': str(path)} for path in paths])
        drafts.append({'name': f'announcement-{index:02d}', 'input': ad.model_dump(mode='json'),
                       'recommendation': recommendation, 'source_quote': item.source_quote})
    return {'needs_review': True, 'warnings': warnings, 'drafts': drafts}
