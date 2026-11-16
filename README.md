# Church Studio

기존 교회 광고의 시각적 구성을 참고하여 편집 가능한 HTML/CSS 템플릿으로 새 광고를 만드는 프로젝트입니다. 주 1회 로컬 실행과 최소 비용 운영을 목표로 합니다.

현재 **Phase 3 Streamlit UI**를 구현했습니다. 기본 흐름은 고정 표지 1장 + 번호별 광고 각 1장입니다. 사진을 광고 번호에 연결하고 기본 문체 규칙 또는 Gemini로 문장을 다듬습니다. 실제 외부 AI 호출과 배포는 이번 작업에서 하지 않았습니다. 모델 자체를 재학습하는 대신 프롬프트의 문체 지침과 예시를 사용합니다.

## 사용자 화면 실행

`run-studio.cmd`를 실행하거나 프로젝트 루트에서 다음 명령을 실행하세요.

```powershell
./.venv/Scripts/python.exe -m streamlit run app.py
```

브라우저에서 `http://127.0.0.1:8501`을 엽니다. 로컬 주소에만 열리며 공개 배포가 아닙니다. 자세한 순서는 [주간 제작 안내](docs/PHASE3.md)에 있습니다.

1. 새 주간 작업을 시작하면 고정 예배 표지가 첫 장으로 만들어집니다.
2. 표지의 날짜·시간·Song List·예배 담당자·성경 본문·사진을 입력합니다. 교회 고정정보는 별도 기본 설정에서 관리합니다.
3. `0. 새신자 환영`, `1. 10월 생일축하`처럼 번호별 광고 메모를 입력합니다. 줄바꿈·빈 줄과 상관없이 번호 하나당 한 장입니다.
4. 사진을 사용할 번호만 지정합니다. 사진 유무에 따라 텍스트형/사진형을 자동 선택합니다.
5. 무료 기본 말투 또는 전송 동의 후 Gemini로 문장을 작성하고 원문·확인 요청을 검토합니다.
6. 미리보기 생성 후 PNG/JPG, 전체 ZIP으로 내려받습니다. 제작 기록에서 다음 주로 복사할 수 있습니다.

## 새 예배 표지와 Phase 2

중앙 교회 사진, 오른쪽 Song List, 변경 가능한 날짜·시간, 환영 문구, YES! / Ethos Spirit, 하단 예배 순서를 전용 필드로 지원합니다. 확인받은 실제 정보는 Git 제외 대상인 `outputs/phase2-cover/cover-input.json`에 저장했습니다. 미입력 사진·곡명을 표시한 미리보기는 `outputs/phase2-cover/worship-draft.png`입니다.

```powershell
./.venv/Scripts/python.exe -m church_studio render outputs/phase2-cover/cover-input.json --draft --name worship-next
```

실제 사진과 곡명이 준비되면 JSON의 `photos`와 `worship.song_list`를 채우고 `--draft` 없이 생성합니다. 완성되지 않은 예배 표지를 일반 결과로 생성하려 하면 입력을 요청합니다. 날짜는 `worship.service_date`, 시간은 `worship.service_time`을 변경합니다. [Phase 2 안내](docs/PHASE2.md)에 구조와 검색·AI 실행 방법을 설명했습니다.

SQLite 스타일 라이브러리와 NumPy 문자 검색은 로컬에서 검증했습니다. Sentence Transformers 의미 검색 어댑터는 로컬 모델을 준비한 후 별도 검증이 필요합니다. Gemini 실제 품질·비용·사진 의미 분석도 전송 동의 후 검증할 항목입니다.

## 자료와 출력

- `data/archive/`: 원본 주간 광고 (수정 금지)
- `data/assets/`: 권한을 확인한 로고·배경·글꼴
- `data/samples/`: 사용자 샘플
- `outputs/`: 로컬 분석 보고서와 생성 이미지 (Git 제외)
- `docs/ROADMAP.md`: 단계별 개발 계획
- `docs/PROGRESS.md`: 실제 검증 결과와 제한 사항

실제 자료와 키는 Git에서 제외합니다. 외부 AI API에 교회 자료를 전송하기 전 승인이 필요합니다.

## Windows 빠른 시작

프로젝트 루트에서 Python 3.11 이상으로 실행합니다. 이번 검증 환경은 Windows / Python 3.12입니다. PowerShell 가상환경 활성화 없이 실행할 수 있습니다.

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements-lock.txt
./.venv/Scripts/python.exe -m pip install -e . --no-deps
./.venv/Scripts/python.exe -m playwright install chromium
./.venv/Scripts/python.exe -m church_studio analyze
./.venv/Scripts/python.exe -m church_studio demo
```

최초 설치에는 패키지와 브라우저 다운로드가 필요합니다. 설치 후 분석·렌더링은 외부 AI나 네트워크 없이 실행합니다. Chromium은 최초 설치 시 수백 MB의 디스크 공간이 필요합니다. 새 플랫폼에서는 `pip install -e ".[dev]"`로 호환 의존성을 설치할 수 있으며, 테스트한 버전은 `requirements-lock.txt`에 고정했습니다.

`demo`는 `outputs/실행시각/`에 직접 그린 사진 2장과 가상 한국어 광고 3종, 편집할 입력 JSON을 만듭니다. 같은 폴더와 이름으로 덮어쓰지 않습니다. 이번에 확인한 결과물은 `outputs/phase1-preview/`에 있습니다.

## 내 문구로 생성

웹 화면 대신 명령행을 사용하려면 `examples/notice.json`을 복사해서 편집하세요. 기존 JSON 렌더링 명령은 계속 지원합니다.

```powershell
./.venv/Scripts/python.exe -m church_studio render examples/notice.json --name my-notice
./.venv/Scripts/python.exe -m church_studio render examples/notice.json --scale 2 --name my-notice-4k
./.venv/Scripts/python.exe -m pytest -q
```

- `notice`: 텍스트 공지, 노란 제목 강조와 선택적 분홍 사실 강조
- `photo`: 사진 1~3장, 본문, 일정·장소 등의 정보
- `cover`: 대표 사진 1장과 파란 안내 패널
- `--scale 1`: 1920×1080, `--scale 2`: 3840×2160
- `--output outputs/새폴더`: 출력 위치 지정
- `--font data/assets/fonts/글꼴.ttf --bold-font data/assets/fonts/굵은글꼴.ttf`: 한글 글꼴 지정

사용 가능한 OS 한글 글꼴을 자동 선택하며, 이번 환경에서는 맑은 고딕을 사용했습니다. 입력과 자산 경로는 현재 작업 폴더 또는 `--root`로 지정한 프로젝트 루트 기준입니다. `--root`는 하위 명령 앞에 놓습니다. Linux/macOS는 `.venv/bin/python`을 사용하고, Linux Chromium 실행에 필요한 시스템 패키지와 한글 글꼴을 설치해야 합니다. 해당 OS 실행은 이번에 검증하지 않았습니다.

생성물은 PNG, 자체 포함형 HTML, 입력·글꼴·브라우저·축소 비율·소요 시간·PNG 해시를 담은 JSON입니다. 텍스트를 최소 65%까지 줄여도 영역을 넘으면 이미지 생성을 거부합니다. 정확한 사실 여부는 관리자가 확인해야 합니다.

사진·로고·배경 추가, 글꼴 권한 및 CLI 오류 해결은 [사용 안내](docs/USER_GUIDE.md), 실제 자료의 구성과 차이점은 [자료 분석](docs/ARCHIVE_ANALYSIS.md)을 확인하세요. UI는 PNG/JPG/ZIP을 지원합니다. PPTX는 미구현입니다.

## 구현 구조

`models.py`(입력 검증), `analysis.py`(자료 검사), `images.py`(사진 처리), `render.py`(렌더링), `templates/`(HTML/CSS), `cli.py`(명령행)를 분리했습니다. `gemini.py`(전송 동의·SDK), `ai_models.py`(발췌 근거), `library.py`(SQLite·검색), `workflow.py`(발췌 결과→광고 초안), `phase2_cli.py`는 Phase 2 기반입니다. `studio.py`(주간 저장·업로드·생성·ZIP), `briefs.py`(번호 분할·말투·사실 보존), `ui.py`(Streamlit)는 현재 제작 흐름입니다.

기술 구현 시 [Playwright 스크린샷 문서](https://playwright.dev/python/docs/screenshots), [Page API](https://playwright.dev/python/docs/api/class-page), [Pydantic 모델 문서](https://docs.pydantic.dev/latest/concepts/models/)를 참고했습니다.
