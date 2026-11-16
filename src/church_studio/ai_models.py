"""AI 응답 전용 구조. 원문 근거와 검토 상태를 렌더링 입력과 분리한다."""

from typing import Literal

from pydantic import Field

from .models import BodyText, ShortText, StrictModel


class SupportedFact(StrictModel):
    label: ShortText
    value: ShortText
    source_quote: BodyText


class StructuredAd(StrictModel):
    title: ShortText
    category: Literal['예배', '모임', '행사', '안내', '기타']
    source_quote: BodyText
    paragraphs: list[BodyText] = Field(default_factory=list, max_length=6)
    facts: list[SupportedFact] = Field(default_factory=list, max_length=8)
    photo_ids: list[ShortText] = Field(default_factory=list, max_length=3)
    suggested_template: Literal['notice', 'photo', 'cover'] = 'notice'
    missing_information: list[ShortText] = Field(default_factory=list, max_length=12)


class StructureResult(StrictModel):
    announcements: list[StructuredAd] = Field(min_length=1, max_length=30)
    warnings: list[ShortText] = Field(default_factory=list, max_length=20)


class StyleProfile(StrictModel):
    """스타일 정보만 저장한다. 광고 내용 필드는 의도적으로 제공하지 않는다."""

    template: Literal['notice', 'photo', 'cover']
    colors: list[ShortText] = Field(min_length=1, max_length=8)
    layout: BodyText
    typography: BodyText
    tone: BodyText
    limitations: list[ShortText] = Field(default_factory=list, max_length=12)


def validate_evidence(result: StructureResult, source: str, photo_ids: list[str]) -> list[str]:
    """근거 없는 사실과 사진 ID를 거부하고 나머지 검토 항목을 반환한다."""
    warnings = list(result.warnings)
    for i, ad in enumerate(result.announcements, 1):
        if ad.source_quote not in source:
            raise ValueError(f'{i}번 광고의 원문 근거가 입력에 없습니다.')
        if ad.title not in ad.source_quote:
            raise ValueError('제목도 원문에서 발췌하세요. 새 문구 작성은 사람이 검토한 후 진행합니다.')
        for fact in ad.facts:
            if fact.source_quote not in ad.source_quote or fact.value not in fact.source_quote:
                raise ValueError(f'{i}번 광고의 {fact.label} 사실에 원문 근거가 없습니다.')
        if not set(ad.photo_ids).issubset(photo_ids):
            raise ValueError('등록되지 않은 사진 ID를 AI가 지정했습니다.')
        # 본문 속에 은밀히 추가된 날짜/이름을 놓치지 않도록 원문 그대로만 허용한다.
        for paragraph in ad.paragraphs:
            if paragraph not in ad.source_quote:
                raise ValueError('AI 본문은 원문에서 그대로 발췌해야 합니다. 문구 변경은 검토 후 편집하세요.')
        warnings.extend(f'{i}번: {item}' for item in ad.missing_information)
    warnings.append('제목·분류·누락 여부·날짜·장소·사진 연결은 사람이 최종 확인해야 합니다.')
    return warnings
