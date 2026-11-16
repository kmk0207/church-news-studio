# Phase 1 사용 안내

## 제작 순서

1. README의 설치 명령을 실행한다. Python 3.11 이상과 Playwright Chromium이 필요하다.
2. `python -m church_studio demo`로 가상 광고를 확인한다.
3. 새 JSON 파일을 `examples/notice.json` 또는 생성된 `*-input.json`에서 복사한다.
4. heading(상단 안내), title(큰 제목), paragraphs(문단 목록), facts(일시·장소 등)를 직접 입력한다.
5. PNG를 생성하고 날짜·장소·맞춤법·사진 크롭을 확인한다. 변경할 때는 입력 JSON을 수정하고 새 이름으로 다시 생성한다.

이 단계는 명령행 기반이다. 미리보기는 생성된 PNG 또는 HTML을 열어 확인한다. HTML은 입력 요소 복원이 아니라 Jinja2에서 생성한 새 편집형 템플릿의 결과이다. 사용자는 JSON 문구·사진 설정과 HTML/CSS 원본을 편집할 수 있고, 드래그 편집 UI는 Phase 3에서 구현한다.

## 사진형 입력 예시

아래 파일 경로에 실제로 존재하고 사용 권한이 있는 사진을 넣은 뒤 실행한다. 경로는 프로젝트 루트 기준이며 Windows에서도 `/`를 사용하면 된다.

```json
{
  "template": "photo",
  "heading": "01  가상 샘플",
  "title": "함께하는 나눔",
  "paragraphs": ["가상 광고입니다. 실제 정보로 바꾸어 주세요."],
  "facts": [{"label": "장소", "value": "확정한 장소를 입력"}],
  "photos": [
    {"path": "data/samples/photos/photo.jpg", "caption": "사진 설명", "focal_x": 0.5, "focal_y": 0.5, "zoom": 1.0}
  ],
  "footer": "가상 광고 · 실제 일정이 아닙니다"
}
```

`focal_x`, `focal_y`는 0~1 사이의 크롭 창 위치이다. 0은 왼쪽/위, 1은 오른쪽/아래, 0.5는 중앙이다. `zoom`은 1~3 사이의 확대율이다. EXIF 회전을 적용하고 비율을 유지하여 채우므로 사진 가장자리가 잘릴 수 있다. 인물 얼굴과 중요한 정보가 크롭되지 않았는지 확인한다. `photo`는 사진 1~3장, `cover`는 1장만 받는다. `notice`에는 사진을 넣을 수 없다.

## 로고·배경·글꼴

JSON 최상위에 `"logo": "data/assets/logos/logo.png"`, `"background": "data/assets/backgrounds/background.png"`를 선택적으로 넣을 수 있다. 로고는 비율을 유지해 하단에 넣고 배경은 16:9로 크롭한다. 메모 프레임은 가독성을 위해 거의 불투명한 흰색이다. 사진·로고·배경은 Pillow가 읽을 수 있는 PNG/JPG 등의 래스터 형식을 사용한다. SVG 직접 렌더링은 지원하지 않는다.

`--font`와 `--bold-font`로 글꼴을 지정한다. 둘 다 없으면 Windows 맑은 고딕, Linux Noto Sans CJK, macOS 시스템 한글 글꼴의 알려진 경로를 찾는다. 자동 검색 실패 시 한글을 지원하는 TTF/OTF를 직접 지정한다. 지정 글꼴의 모든 문자 지원 여부를 자동 증명하지 않으므로 PNG로 한글과 특수문자를 확인한다.

HTML은 사진과 글꼴을 포함하므로 용량이 크다. 특히 OS 글꼴이 포함된 HTML은 글꼴 재배포 권한 확인 없이 공유하지 말고, 교회 배포용으로는 생성된 PNG를 사용한다. 원본 자료·로고·사진·글꼴 라이선스는 관리자가 확인해야 한다.

## 오류와 제한

- '글자가 영역을 넘칩니다': 문단을 줄이거나 광고를 여러 장으로 나눈다. 코드는 내용을 생략하거나 말줄임표로 숨기지 않는다. 기본 글자 크기를 65%까지 낮추고도 들어가지 않으면 PNG를 만들지 않는다.
- '같은 이름의 결과물이 있습니다': `--name` 또는 `--output`을 바꾼다. 원본과 이전 결과물은 자동 덮어쓰지 않는다. 실패한 데모 실행에 입력 파일이 남았어도 새 출력 폴더로 다시 실행한다.
- '자료 파일을 찾을 수 없습니다': JSON의 경로와 `--root`를 확인한다. 열려 있지만 저장되지 않은 IDE 탭은 읽을 수 없다.
- 'Chromium 미설치': 가상환경 Python으로 `python -m playwright install chromium`을 실행한다. 보안 도구나 에이전트 실행 제한이 Node/Chromium 프로세스를 차단하는 경우 허용된 로컬 터미널에서 실행해야 한다.
- Windows 터미널 글자가 깨지면 실행 전에 `$env:PYTHONUTF8='1'`을 설정한다. JSON 파일은 UTF-8로 저장한다.
- 매우 긴 글·이모지·복잡한 특수문자는 글꼴과 실제 송출 화면에서 확인한다. 날짜·요일 일치, 장소 존재, 내용 누락은 Phase 1에서 의미 검증하지 않는다.
- PNG만 구현했다. JPG/ZIP/PPTX, 자연어 파싱, AI 추천, UI와 제작 이력 DB는 아직 구현하지 않았다.

## 테스트

`python -m pytest -q`는 실제 Chromium으로 렌더링까지 검사한다. 브라우저가 없는 환경의 로직 검사만 하려면 `python -m pytest -q -m "not integration"`을 사용한다. 모든 임시 광고는 테스트 임시 폴더에 생성한다. 원본 data/ 자료를 테스트에 요구하거나 수정하지 않는다.
