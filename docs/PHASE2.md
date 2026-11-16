# Phase 2 사용 및 구현 안내

## 예배 표지

실제 입력은 `outputs/phase2-cover/cover-input.json`, 개인 정보 없는 구조 예시는 `examples/worship.json`이다. 기존 상세 공지와 구형 cover 입력은 그대로 사용할 수 있다. `worship`을 지정한 cover만 새 예배 표지를 사용한다.

- `service_date`: `2026-11-15` 형식. 오늘이나 지난주 날짜로 자동 채우지 않는다.
- `service_time`: `13:20:00` 형식. 출력은 `1:20PM`이다.
- `church`, `location`, `welcome`: 교회·예배실·환영 문구.
- `brand`, `motto`: YES!와 Ethos Spirit. 사용자가 바꿀 수 있다.
- `song_list`: `['곡명 A', '곡명 B']` 형태의 순서 있는 목록. JSON에서는 큰따옴표를 사용한다.
- `service_order`: 인도자·기도·성경봉독·설교자 등의 label/value 목록.
- `confirmed`: 실제 날짜·담당자·본문을 검토했을 때 true.
- 최상위 `photos`: 중앙 사진 1장. `focal_x`, `focal_y`, `zoom`으로 크롭을 조절한다.

사진을 넣을 때 JSON 최상위에 아래처럼 추가한다. 실제 파일을 해당 위치에 저장해야 한다.

```json
"photos": [{"path": "data/samples/photos/worship.jpg", "focal_x": 0.5, "focal_y": 0.5, "zoom": 1}]
```

표지 오른쪽에는 곡명만 표시한다. 실제 곡명이 없으면 지난 광고에서 임의로 가져오지 않는다. 사진·곡명·예배 순서·최종 확인이 부족할 때는 `--draft`로만 렌더링하며 미입력 항목과 초안 표시가 남는다. 실제 교회 입력의 담당자 연결과 예시 날짜·시간은 사용자에게 확인받았다. 아직 사진과 곡명은 제공되지 않았다.

```powershell
./.venv/Scripts/python.exe -m church_studio render outputs/phase2-cover/cover-input.json --draft --name worship-review
```

송출본은 정보를 채운 후 새 이름으로 `--draft` 없이 생성한다. 원본이나 이전 PNG는 덮어쓰지 않는다. 새 표지는 이미지의 레이어 복원이나 원본 글꼴 복제가 아닌 편집 가능한 CSS 구현이다.

## 로컬 스타일 검색

`examples/styles/`에는 실제 광고의 시각적 구성을 참고하고 사용자 표지 요구를 반영해 수동 작성한 프로필 3종이 있다. 날짜·담당자·성경 본문·곡명은 포함하지 않는다. 현재 로컬 DB에는 대표 원본 3개의 참조와 프로필을 등록했다. 이미지를 DB로 복사하거나 외부로 전송하지 않는다.

```powershell
./.venv/Scripts/python.exe -m church_studio recommend "Song List 예배 표지 중앙 대표 사진"
```

`style-add --image <원본경로> --profile <프로필JSON> --reviewed`로 검토한 프로필을 등록한다. 동일 이미지 해시는 중복 등록하지 않고 프로필을 갱신한다. 기본 DB는 `outputs/library/styles.sqlite3`이다. 기존 광고의 과거 본문을 AI 입력에 자동 삽입하지 않는다.

기본 검색은 모델 다운로드 없이 동작하는 **문자 n-gram/NumPy 코사인 유사도**이다. 의미 검색과 혼동하지 않는다. 사진 수와 템플릿 제약을 적용하는 규칙 추천도 별도로 제공한다. AI가 추천한 cover에는 날짜·곡·담당자를 추정하여 채우지 않는다.

선택적으로 `pip install -e ".[semantic]"` 후 `--embedding-model <로컬모델폴더>`를 `style-add`와 `recommend` 양쪽에 지정하면 Sentence Transformers 어댑터를 사용한다. 모델 파일은 별도 준비해야 하며 자동 다운로드하지 않는다. 모델을 바꾸거나 같은 폴더의 가중치를 교체하면 새 DB에 다시 등록한다. 이 경로는 현재 모델 설치·실행·검색 품질을 검증하지 않았다.

## Gemini 전송과 원문 구조화

설치: `pip install -e ".[dev,ai]"`. 이번 환경에서는 google-genai 2.34.0을 설치하고 실제 SDK 타입과 모의 응답으로 검사했다. 실제 API 호출은 하지 않았다. 키는 `GEMINI_API_KEY` 환경변수로만 읽는다. SDK는 [공식 문서](https://googleapis.github.io/python-genai/index.html), 구조화 출력은 [Google 안내](https://ai.google.dev/gemini-api/docs/structured-output)를 참고했다.

전송은 두 단계로 분리한다. 먼저 로컬 계획을 만들고, 그 안의 텍스트·이미지 경로/해시·모델·시스템 지침을 검토한다. 프로젝트 개발 승인은 교회 자료의 외부 전송 승인으로 간주하지 않는다.

```powershell
./.venv/Scripts/python.exe -m church_studio ai-plan --operation structure --model 실제사용할모델ID --text data/samples/announcements.txt --photo-ids photo-01 photo-02 --output outputs/ai/plan.json
```

이 명령은 API를 호출하지 않는다. 실제 텍스트가 비어 있으면 실패한다. `--operation structure`는 텍스트와 사진 ID만 계획에 넣고 실제 사진 파일은 전송하지 않는다. `--operation style --images <이미지경로>`는 지정한 사진만 전송 대상으로 나열한다. PNG/JPG/WebP, 한 장당 8 MB 이하, 최대 5장을 지원한다.

사용자가 계획의 전송 내용과 외부 전송에 동의한 경우에만 아래 명령을 사용한다. 현재 작업에서는 실행하지 않았다.

```powershell
./.venv/Scripts/python.exe -m church_studio ai-run --plan outputs/ai/plan.json --approve-sha256 검토한계획의SHA256 --output outputs/ai/response.json
```

텍스트·모델·사진 목록·지침·응답 스키마가 바뀌면 해시가 달라지고, 이미지 파일 내용이 바뀌어도 전송을 거부한다. 승인 검사 이전에는 API 키 조회나 클라이언트 생성을 하지 않는다. 실패 자동 재시도는 하지 않으며 오류에 원문이나 API 키를 출력하지 않는다. 응답에는 모델·시간·토큰 사용량을 기록하지만 금액을 추정하지 않는다. 실제 모델 ID 지원 여부, 권한, 스키마 지원, 쿼터·과금은 실연결 검증이 필요하다.

구조화 응답은 여러 광고와 각 광고의 원문 근거, 발췌 본문·제목, 사실 정보, 사진 ID, 누락 정보를 포함한다. 근거 없는 값, 등록하지 않은 사진, 원문을 바꾼 본문·제목은 거부한다. 원문 부분 문자열 검사는 사실의 진위나 날짜·요일 일치를 증명하지 않는다. 누락이나 잘못된 광고 분리도 사람이 최종 검토해야 한다. 스타일 분석 응답도 검토 전에는 라이브러리에 등록하지 않는다.

## AI 결과를 광고 JSON으로 연결

```powershell
./.venv/Scripts/python.exe -m church_studio ai-drafts --plan outputs/ai/plan.json --response outputs/ai/response.json --output outputs/ai/drafts
```

사진이 있으면 `--photo-map <JSON파일>`로 `{"photo-01": "data/samples/photos/a.jpg"}` 같은 객체를 제공한다. 계획과 응답의 해시 및 원문 근거를 다시 검사한 뒤 광고별 JSON과 `review.json`을 만든다. 이 작업은 네트워크를 사용하지 않는다. 사진 수에 맞춰 notice/photo를 추천하고 표지의 예배 정보는 별도 입력을 요구한다. 작성한 JSON을 검토·수정한 다음 기존 `render` 명령으로 PNG를 만든다.

현재까지 실제 사진 내용에 기반한 자동 연결과 RAG 결과를 포함한 Gemini 실응답 품질은 검증하지 않았다. 추천·스타일 검색·구조화 어댑터를 각각 분리 구현한 상태이다. Streamlit 업로드·드래그 편집 화면은 Phase 3 범위다.
