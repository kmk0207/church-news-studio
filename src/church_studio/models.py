"""사용자가 제공한 사실과 디자인 설정을 분리하여 검증한다."""

from pathlib import Path
from datetime import date, time
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
BodyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class Fact(StrictModel):
    label: Annotated[str, StringConstraints(min_length=1, max_length=16)]
    value: Annotated[str, StringConstraints(min_length=1, max_length=160)]
    accent: bool = False


class Photo(StrictModel):
    path: Path
    caption: Annotated[str, StringConstraints(max_length=80)] = ""
    focal_x: float = Field(default=0.5, ge=0, le=1)
    focal_y: float = Field(default=0.5, ge=0, le=1)
    zoom: float = Field(default=1, ge=1, le=3)


class WorshipCover(StrictModel):
    """표지 전용 예배 정보. 주간 날짜·담당자·곡을 자동으로 재사용하지 않는다."""

    service_date: date
    service_time: time
    church: ShortText
    location: ShortText
    welcome: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    song_list: list[ShortText] = Field(default_factory=list, max_length=10)
    service_order: list[Fact] = Field(default_factory=list, max_length=6)
    brand: ShortText = 'YES!'
    motto: ShortText = 'Ethos Spirit'
    confirmed: bool = False

    @property
    def date_label(self) -> str:
        return f'{self.service_date.month}월 {self.service_date.day}일'

    @property
    def time_label(self) -> str:
        hour = self.service_time.hour
        return f'{hour % 12 or 12}:{self.service_time.minute:02d}{"PM" if hour >= 12 else "AM"}'

    def missing_items(self) -> list[str]:
        missing = []
        if not self.song_list:
            missing.append('Song List 곡명')
        if not self.service_order:
            missing.append('예배 순서')
        if not self.confirmed:
            missing.append('날짜·예배 순서 최종 확인')
        return missing


class Announcement(StrictModel):
    template: Literal["notice", "photo", "cover"] = "notice"
    heading: ShortText
    title: ShortText
    paragraphs: list[BodyText] = Field(default_factory=list, max_length=6)
    facts: list[Fact] = Field(default_factory=list, max_length=5)
    photos: list[Photo] = Field(default_factory=list, max_length=3)
    footer: Annotated[str, StringConstraints(max_length=120)] = ""
    highlight_title: bool = True
    logo: Path | None = None
    background: Path | None = None
    worship: WorshipCover | None = None

    @model_validator(mode="after")
    def check_layout(self):
        if self.worship and self.template != 'cover':
            raise ValueError('예배 정보는 cover 템플릿에서만 사용하세요.')
        if self.worship and (self.paragraphs or self.facts):
            raise ValueError('예배 표지는 본문 대신 worship.welcome, 예배 순서는 worship.service_order에 입력하세요.')
        if self.template in {"photo", "cover"} and not self.photos and not self.worship:
            raise ValueError("사진형·표지형에는 사진을 하나 이상 지정하세요.")
        if self.template == "notice" and self.photos:
            raise ValueError("사진을 표시하려면 photo 또는 cover 템플릿을 선택하세요.")
        if self.template == "cover" and len(self.photos) > 1:
            raise ValueError("표지형은 대표 사진 한 장을 사용합니다.")
        return self


class RenderOptions(StrictModel):
    scale: Literal[1, 2] = 1
    font: Path | None = None
    bold_font: Path | None = None
    draft: bool = False
