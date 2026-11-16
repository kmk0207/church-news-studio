"""번호당 한 장의 광고와 교회 문체 초안. 페이지 분할과 사진 연결은 코드가 결정한다."""

import re
from pathlib import Path

from pydantic import Field

from .models import Announcement, BodyText, ShortText, StrictModel

NUMBER = re.compile(r'^\s*(\d{1,2})[.)．]\s+(.+)', re.MULTILINE)


class Brief(StrictModel):
    number: int = Field(ge=0, le=99)
    text: BodyText


class CopyPage(StrictModel):
    number: int = Field(ge=0, le=99)
    title: ShortText
    paragraphs: list[BodyText] = Field(min_length=1, max_length=6)
    missing_information: list[ShortText] = Field(default_factory=list, max_length=10)


class CopyResult(StrictModel):
    pages: list[CopyPage] = Field(min_length=1, max_length=30)


def parse_numbered(text: str) -> list[Brief]:
    text = text.strip()
    matches = list(NUMBER.finditer(text))
    if not matches or text[:matches[0].start()].strip():
        raise ValueError('각 광고를 "0. 새신자 환영"처럼 번호로 시작해 주세요.')
    items = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        content = text[match.start(2):end].strip()
        items.append(Brief(number=int(match[1]), text=content))
    if len(items) > 30 or len({item.number for item in items}) != len(items):
        raise ValueError('광고 번호는 중복 없이 최대 30개까지 입력하세요.')
    return items


def missing_details(text: str) -> list[str]:
    missing = []
    # 값이 아니라 항목명만 주어진 경우 임의로 복장이나 시간을 만들어 내지 않는다.
    if '복장' in text and not re.search(r'복장\s*[:：]\s*\S+', text):
        missing.append('복장을 알려주세요.')
    if re.search(r'모임\s*시간', text) and not re.search(r'모임\s*시간\s*[:：]\s*\S+|\d+\s*시|\d+:\d+', text):
        missing.append('모임 시간을 알려주세요.')
    return missing


def local_copy(brief: Brief) -> CopyPage:
    """무료 로컬 문체 규칙. 자유로운 AI 작성과 구분하며, 모르는 내용은 보존한다."""
    text = brief.text
    title = text.splitlines()[0].split('(')[0].strip()
    if len(title) > 100:
        raise ValueError(f'{brief.number}번 광고 제목을 100자 이하로 줄여 주세요.')
    if re.search(r'새신자|새가족', text) and '환영' in text:
        body = '예배 자리에 오신 새신자 여러분을 환영하고 축복합니다 :)'
    elif '생일' in text and '축하' in text:
        month = re.search(r'\d+\s*월', text)
        body = (month[0] + '에 ' if month else '') + '생일을 맞으신 모든 분들을 축하하고 축복합니다~'
    elif '특송' in text and '연습' in text:
        body = ('광고 이후 ' if re.search(r'광고\s*(이후|후)', text) else '') + '추수감사 특송 연습이 있습니다~\n함께 참여해 주세요.' if '추수감사' in text else '특송 연습이 있습니다~\n함께 참여해 주세요.'
    elif '특새' in text:
        body = ('추수감사 ' if '추수감사' in text else '') + '특별새벽기도회가 있습니다~\n함께 참여해 주세요.'
    elif re.search(r'배[드트]민턴', text):
        body = '배드민턴 모임이 있습니다~\n함께 참여해 주세요.'
    else:
        body = text + ('\n함께 확인해 주세요.' if not text.endswith(('요.', '요~', '다.')) else '')
    # 정형 규칙에 없는 실제 정보와 조건은 덜어내지 않고 원문 그대로 함께 표시한다.
    if body != text and text not in body:
        details = []
        if re.search(r'우천\s*시\s*취소', text):
            details.append('우천시 취소')
        for line in text.splitlines()[1:]:
            if line.strip():
                details.append(line.strip())
        # 제목 한 줄의 괄호 안에 있는 실제 조건도 보존한다.
        for note in re.findall(r'[(（]([^()（）]+)[)）]', text):
            if note.replace(' ', '') not in {'복장,모임시간', '복장,모임시간안내'} and note not in details:
                details.append(note)
        # 한 줄에 적은 시간·장소 등의 정보가 규칙 문장에 사라지지 않게 원문을 보존한다.
        if re.search(r'\d+\s*(일|시|분)|\d+:\d+|장소|문의|신청|복장\s*[:：]', text.splitlines()[0]):
            details.append('안내: ' + text.splitlines()[0])
        if details:
            body += '\n' + '\n'.join(dict.fromkeys(details))
    return CopyPage(number=brief.number, title=title, paragraphs=[body], missing_information=missing_details(text))


def validate_copy(result: CopyResult, briefs: list[Brief]):
    if [page.number for page in result.pages] != [item.number for item in briefs]:
        raise ValueError('AI가 광고 번호·순서·페이지 수를 바꿨습니다. 원문 번호대로 다시 작성해야 합니다.')
    for item, page in zip(briefs, result.pages):
        output = page.title + '\n' + '\n'.join(page.paragraphs)
        # 숫자 추가·변경을 차단한다. 인명·의미의 진위까지 증명하는 검사는 아니다.
        source_numbers = set(re.findall(r'\d+(?::\d+)?', item.text))
        result_numbers = set(re.findall(r'\d+(?::\d+)?', output))
        if result_numbers != source_numbers:
            raise ValueError(f'{item.number}번의 날짜·시간·숫자가 추가되거나 누락됐습니다.')
        compact = re.sub(r'\s+', '', output)
        if re.search(r'우천\s*시\s*취소', item.text) and '우천시취소' not in compact:
            raise ValueError(f'{item.number}번의 우천시 취소 조건이 누락됐습니다.')
        # 명시한 사실 정보는 문장 어미를 바꿔도 값 자체를 유지해야 한다.
        for value in re.findall(r'(?:일시|날짜|시간|장소|복장|문의|신청)\s*[:：]\s*([^\n,;]+)', item.text):
            if re.sub(r'\s+', '', value.strip()) not in compact:
                raise ValueError(f'{item.number}번의 명시한 사실 정보가 변경됐습니다: {value.strip()}')


def cards_from_copy(briefs: list[Brief], result: CopyResult, assignments: dict[int, list[str]], root: Path):
    from .studio import Card
    validate_copy(result, briefs)
    if set(assignments) - {item.number for item in briefs}:
        raise ValueError('원문에 없는 광고 번호에 사진을 연결했습니다.')
    cards = []
    for brief, page in zip(briefs, result.pages):
        paths = assignments.get(brief.number, [])
        if len(paths) > 3:
            raise ValueError('광고 한 장에는 사진을 3개까지 연결할 수 있습니다.')
        photos = []
        for raw in paths:
            path = (root / raw).resolve()
            if not any(path.is_relative_to((root / area).resolve()) for area in ['data', 'outputs']) or not path.is_file():
                raise ValueError('사진 보관함에서 사용할 사진을 선택하세요.')
            photos.append({'path': str(path)})
        ad = Announcement(template='photo' if photos else 'notice', heading=f'{brief.number}. {page.title}',
                          title=page.title, paragraphs=page.paragraphs, photos=photos)
        cards.append(Card(data=ad.model_dump(mode='json'), number=brief.number, source_text=brief.text,
                          review_notes=list(dict.fromkeys([*missing_details(brief.text), *page.missing_information]))))
    return cards
