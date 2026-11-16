"""Streamlit 화면. 생성·저장·내보내기 로직은 Studio 서비스에 위임한다."""

import copy
import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import streamlit as st

from .models import Announcement, RenderOptions
from .studio import Card, Project, Studio, empty_card, split_local_text

TEMPLATES = {'notice': '텍스트 공지', 'photo': '사진 공지', 'cover': '예배 표지'}
STYLE = '''<style>
.block-container {max-width: 1500px; padding-top: 2.3rem; padding-bottom: 3rem;}
h1 {letter-spacing: -.06em; font-weight: 750!important;}
h2,h3 {letter-spacing: -.035em;}
[data-testid="stSidebar"] {border-right: 1px solid #dae4df;}
[data-testid="stButton"] button {min-height: 2.7rem; border-radius: .6rem;}
[data-testid="stMetric"] {padding: 12px 0;}
.studio-kicker {font-size: .75rem; letter-spacing: .18em; color: #147d84; font-weight: 700; margin-bottom: .8rem;}
.studio-intro {font-size: 1.05rem; color: #62736d; line-height: 1.8; margin-bottom: 1.8rem;}
.studio-note {padding: 18px 22px; border-left: 3px solid #147d84; background: #edf4f0; line-height: 1.8; margin: 12px 0 28px;}
</style>'''


def today() -> date:
    return datetime.now(timezone(timedelta(hours=9))).date()


def activate(project: Project):
    st.session_state.project = project
    st.session_state.selected_card = project.cards[0].id if project.cards else None
    st.session_state.editor_drafts = {}
    st.session_state.editor_epoch = st.session_state.get('editor_epoch', 0) + 1


def persist(service: Studio, project: Project):
    saved = service.save(project)
    st.session_state.project = saved
    return saved


def append_cards(service: Studio, cards: list[Card]):
    project = st.session_state.project.model_copy(deep=True)
    if any(card.data.get('worship') for card in cards) and any(card.data.get('worship') for card in project.cards):
        raise ValueError('고정 표지가 이미 있습니다. 표지를 선택해 주간 정보만 수정하세요.')
    project.cards.extend(cards)
    persist(service, project)
    st.session_state.selected_card = cards[0].id
    st.session_state.editor_epoch = st.session_state.get('editor_epoch', 0) + 1


def assets_widget(service: Studio, key: str, selected: list[str], *, limit=3) -> list[str]:
    assets = {item['path']: item['name'] for item in service.uploads()}
    for path in selected:
        assets.setdefault(path, Path(path).name)
    chosen = st.multiselect('사용할 사진', list(assets), default=[p for p in selected if p in assets],
                             format_func=lambda p: assets[p], max_selections=limit, key=key)
    return chosen


def editor(service: Studio, project: Project, card: Card):
    draft_key = project.id + ':' + card.id
    drafts = st.session_state.setdefault('editor_drafts', {})
    original = copy.deepcopy(drafts.get(draft_key, {'data': card.data, 'enabled': card.enabled, 'reviewed': card.reviewed}))
    data = original['data']
    prefix = f'e:{project.id}:{card.id}:{st.session_state.get("editor_epoch", 0)}'
    template = data.get('template', 'notice')
    is_cover = bool(data.get('worship'))
    template = 'cover' if is_cover else ('photo' if data.get('photos') else 'notice')
    st.caption('고정 예배 표지' if is_cover else '사진 유무에 맞춰 광고 구성을 자동 선택합니다.')
    p = prefix + (':cover' if is_cover else ':detail')
    chosen = copy.deepcopy(data)
    chosen['template'] = template
    left, right = st.columns([1.05, 1.15], gap='large')
    with left:
        st.subheader('광고 내용')
        chosen['heading'] = st.text_input('상단 안내', value='YOUTH WORSHIP' if is_cover else data.get('heading', ''), max_chars=100, key=p + ':heading', disabled=is_cover)
        chosen['title'] = st.text_input('제목', value='청년 예배' if is_cover else data.get('title', ''), max_chars=100, key=p + ':title', disabled=is_cover)
        if card.source_text:
            with st.expander(f'{card.number}번 원문과 확인할 내용', expanded=bool(card.review_notes)):
                st.text(card.source_text)
                for note in card.review_notes:
                    st.warning(note)
        if template == 'cover':
            st.caption('예배 표지는 환영 문구와 예배 정보로 구성됩니다.')
            worship = data.get('worship') or empty_card('cover', project.week).data['worship']
            a, b = st.columns(2)
            with a:
                day = st.date_input('예배 날짜', value=date.fromisoformat(str(worship['service_date'])), key=p + ':date')
            with b:
                hour = st.time_input('예배 시간', value=time.fromisoformat(str(worship['service_time'])), key=p + ':time')
            fixed = service.cover_settings()
            church, location, welcome = fixed['church'], fixed['location'], fixed['welcome']
            st.write('**교회 / 장소:** ' + (church or '기본 설정 필요') + ' · ' + (location or '기본 설정 필요'))
            st.text(welcome)
            st.caption('교회·장소·환영 문구·브랜드는 고정입니다. 최초 변경은 표지 기본 설정에서 진행하세요.')
            songs = st.text_area('Song List · 한 줄에 한 곡', value='\n'.join(worship['song_list']), height=145, key=p + ':songs')
            st.caption('예배 순서와 담당자 · 성경 본문')
            values = {row['label']: row['value'] for row in worship['service_order']}
            rows = [{'label': label, 'value': values.get(label, '')} for label in ['인도자', '기도', '성경봉독', '설교자']]
            order = []
            for i, row in enumerate(rows):
                a, b = st.columns([1, 2.5])
                label = a.text_input(f'순서 {i + 1}', value=row['label'], max_chars=16, key=p + f':role:{i}', disabled=True)
                value = b.text_input(f'담당 / 본문 {i + 1}', value=row['value'], max_chars=160, key=p + f':person:{i}')
                order.append({'label': label, 'value': value})
            brand, motto = fixed['brand'], fixed['motto']
            st.caption(brand + ' / ' + motto)
            chosen.update(paragraphs=[], facts=[], worship={
                'service_date': str(day), 'service_time': hour.isoformat(), 'church': church, 'location': location,
                'welcome': welcome, 'song_list': [line.strip() for line in songs.splitlines() if line.strip()],
                'service_order': order, 'brand': brand, 'motto': motto, 'confirmed': False})
        else:
            body = st.text_area('본문 · 빈 줄로 문단 구분', value='\n\n'.join(data.get('paragraphs', [])), height=210, key=p + ':body')
            chosen['paragraphs'] = [text.strip() for text in body.split('\n\n') if text.strip()]
            facts = '\n'.join(f'{f["label"]}: {f["value"]}' for f in data.get('facts', []))
            fact_text = st.text_area('일정·장소 등 · 한 줄에 항목: 내용', value=facts, height=115, key=p + ':facts',
                                     help='예: 일시: 11월 22일 오후 2시')
            chosen['facts'] = []
            fact_error = False
            for line in fact_text.splitlines():
                if not line.strip():
                    continue
                if ':' not in line:
                    st.warning('일정·장소는 "항목: 내용"으로 입력해 주세요.')
                    fact_error = True
                else:
                    label, value = line.split(':', 1)
                    chosen['facts'].append({'label': label.strip(), 'value': value.strip()})
            chosen['worship'] = None
            chosen['highlight_title'] = st.checkbox('제목 노란색 강조', value=data.get('highlight_title', True), key=p + ':highlight')
        chosen['footer'] = '' if is_cover else st.text_input('하단 문구', value=data.get('footer', ''), max_chars=120, key=p + ':footer')
        st.subheader('사진과 배치')
        selected = [str(item['path']) for item in data.get('photos', [])]
        selected = selected[:1] if is_cover else selected
        paths = assets_widget(service, p + ':photos', selected, limit=1 if is_cover else 3)
        existing = {str(photo['path']): photo for photo in data.get('photos', [])}
        chosen['photos'] = []
        for i, path in enumerate(paths):
            photo = existing.get(path, {'path': path, 'caption': '', 'focal_x': .5, 'focal_y': .5, 'zoom': 1.0})
            with st.expander(f'사진 {i + 1} 위치·크기', expanded=True):
                st.image(path, width=240)
                caption = st.text_input('사진 설명', value=photo.get('caption', ''), max_chars=80, key=p + f':caption:{i}:{path}')
                x = st.slider('가로 위치', 0.0, 1.0, float(photo.get('focal_x', .5)), .05, key=p + f':x:{i}:{path}')
                y = st.slider('세로 위치', 0.0, 1.0, float(photo.get('focal_y', .5)), .05, key=p + f':y:{i}:{path}')
                zoom = st.slider('사진 확대', 1.0, 3.0, float(photo.get('zoom', 1)), .05, key=p + f':zoom:{i}:{path}')
                chosen['photos'].append({'path': path, 'caption': caption, 'focal_x': x, 'focal_y': y, 'zoom': zoom})
        if not is_cover:
            template = 'photo' if chosen['photos'] else 'notice'
            chosen['template'] = template
        if not service.uploads():
            st.caption('왼쪽 사진 보관함에서 사진을 올린 뒤 여기서 연결하세요.')
        with st.expander('로고·배경'):
            assets = {item['path']: item['name'] for item in service.uploads()}
            for field, label in [('logo', '교회 로고'), ('background', '배경 이미지')]:
                current = str(data[field]) if data.get(field) else None
                if current:
                    assets.setdefault(current, Path(current).name)
                options = [None, *assets]
                chosen[field] = st.selectbox(label, options, index=options.index(current),
                    format_func=lambda v: '사용 안 함' if v is None else assets[v], key=p + ':' + field)
        enabled = True if is_cover else st.checkbox('전체 다운로드에 포함', value=original['enabled'], key=p + ':enabled')
        reviewed = st.checkbox('내용과 날짜·장소·담당자를 확인했습니다', value=original['reviewed'], key=p + ':reviewed')
        if chosen.get('worship'):
            chosen['worship']['confirmed'] = reviewed
        draft = {'data': chosen, 'enabled': enabled, 'reviewed': reviewed}
        drafts[draft_key] = copy.deepcopy(draft)
        dirty = (chosen != card.data or enabled != card.enabled or reviewed != card.reviewed)
        if dirty:
            st.caption('수정 사항이 있습니다. 저장하거나 미리보기를 생성해 반영하세요.')
        a, b = st.columns(2)
        save = a.button('변경 사항 저장', key=p + ':save', width='stretch')
        with st.expander('출력 설정'):
            scale = st.selectbox('이미지 크기', [1, 2], format_func=lambda n: '1920 × 1080' if n == 1 else '3840 × 2160 (4K)', key=p + ':scale')
            preview_draft = st.checkbox('표지 미입력 항목을 초안으로 표시', value=bool(chosen.get('worship') and (not chosen.get('photos') or not chosen['worship'].get('song_list'))), key=p + ':draft')
        generate = b.button('저장하고 미리보기 생성', key=p + ':generate', type='primary', width='stretch')
        if save or generate:
            if template != 'cover' and fact_error:
                st.error('일정·장소 입력 형식을 먼저 확인해 주세요.')
            else:
                try:
                    edited = project.model_copy(deep=True)
                    target = next(c for c in edited.cards if c.id == card.id)
                    target.data, target.enabled, target.reviewed = chosen, enabled, reviewed
                    if generate:
                        with st.spinner('한글과 사진을 배치하고 이미지를 만들고 있습니다…'):
                            rendered = service.generate(target, RenderOptions(scale=scale, draft=preview_draft))
                            target.data = rendered.data
                            target.artifact = rendered.artifact
                    persist(service, edited)
                    st.success('이미지를 생성하고 저장했습니다.' if generate else '변경 사항을 저장했습니다.')
                    st.rerun()
                except Exception as exc:
                    st.error(f'저장·생성을 마치지 못했습니다: {exc}')
    with right:
        st.subheader('미리보기')
        if card.artifact:
            try:
                st.image(str(service.result_path(card.artifact['png'])), width='stretch')
            except (ValueError, OSError):
                st.warning('이전 이미지 파일이 없습니다. 다시 생성해 주세요.')
            ready = service.current(card) and not dirty
            if not ready:
                st.warning('내용이 변경되었습니다. 현재 내용으로 다시 생성해 주세요.')
            elif card.artifact['draft']:
                st.info('초안 미리보기입니다. 사진·곡명·확인 항목을 채우고 송출본을 생성하세요.')
            for warning in card.artifact.get('warnings', []):
                st.caption('확인 필요: ' + warning)
            kind = st.radio('개별 이미지 형식', ['PNG', 'JPG'], horizontal=True, key=p + ':download-kind')
            if ready and card.reviewed:
                try:
                    content = service.download(card, kind, allow_draft=True)
                    st.download_button('초안 이미지 다운로드' if card.artifact['draft'] else '이 광고 다운로드', content,
                        file_name=f'{project.week}-{card.id[:6]}{"-draft" if card.artifact["draft"] else ""}.{kind.lower()}',
                        mime='image/png' if kind == 'PNG' else 'image/jpeg', key=p + ':download', width='stretch')
                except ValueError as exc:
                    st.warning(str(exc))
            elif not card.reviewed:
                st.caption('다운로드 전에 왼쪽의 내용 확인 항목을 체크하고 저장하세요.')
        else:
            st.markdown('<div class="studio-note">문구와 사진을 넣고<br><b>저장하고 미리보기 생성</b>을 눌러 주세요.<br>여기에 실제 생성 이미지가 표시됩니다.</div>', unsafe_allow_html=True)
        with st.expander('템플릿 구성 안내', expanded=True):
            st.markdown({'notice': '**텍스트 공지**\n\n노란 제목 강조와 중앙 본문. 일정·장소를 별도 줄로 표시합니다.',
                         'photo': '**사진 공지**\n\n사진 1~3장과 본문. 사진마다 위치·확대율을 조절할 수 있습니다.',
                         'cover': '**예배 표지**\n\n중앙 사진 · 오른쪽 Song List · 왼쪽 날짜와 환영 문구 · 하단 예배 순서.'}[template])


def intake(service: Studio, project: Project):
    from .briefs import CopyResult, cards_from_copy, local_copy, parse_numbered
    with st.expander('번호별 광고 입력 · 사진 연결 · 말투 다듬기', expanded=True):
        text = st.text_area('이번 주 광고 원문', height=170, key='intake:' + project.id,
            placeholder='0. 새신자 환영\n1. 10월 생일축하\n2. 추수감사 특새 광고 (복장, 모임시간)\n3. 광고 이후 추수감사 특송 연습\n4. 배트민턴 광고 (우천시 취소)')
        st.caption('0번부터 번호 하나당 광고 한 장이 됩니다. 표지는 별도로 항상 첫 장입니다. 다시 만들면 번호 광고 목록을 교체하고 표지와 수동 광고는 유지합니다.')
        try:
            briefs = parse_numbered(text) if text.strip() else []
        except ValueError as exc:
            st.warning(str(exc))
            briefs = []
        assignments = {}
        uploads = {item['path']: item['name'] for item in service.uploads()}
        for brief in briefs:
            assignments[brief.number] = st.multiselect(f'{brief.number}번 사진 · {brief.text.splitlines()[0]}',
                list(uploads), format_func=lambda path: uploads[path], max_selections=3,
                key=f'assign:{project.id}:{brief.number}')
        st.caption('사진을 골라 광고 번호에 연결하세요. 사진 파일과 배정 정보는 AI로 전송하지 않습니다.')
        if st.button('번호별 광고 만들기 · 기본 말투', disabled=not briefs, key='split:' + project.id):
            try:
                result = CopyResult(pages=[local_copy(brief) for brief in briefs])
                cards = cards_from_copy(briefs, result, assignments, service.root)
                activate(service.apply_numbered(st.session_state.project, cards))
                st.session_state.selected_card = cards[0].id
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
        st.divider()
        st.markdown('**Gemini로 교회 광고 말투 다듬기**')
        st.caption('모델을 다시 훈련하지 않고 문체 지침과 예시를 사용합니다. 번호·사진 배정은 유지하고 문장만 자연스럽게 작성합니다.')
        model = st.text_input('사용할 Gemini 모델 ID', key='ai-model')
        api_key = st.text_input('Gemini API 키 · 이번 브라우저 세션에서만 사용', type='password', key='ai-key')
        if briefs and model.strip():
            from .gemini import execute_plan, make_plan
            plan = make_plan('copy', model, text, [], service.root)
            with st.expander('전송할 내용 확인'):
                st.text(text)
                st.caption('수신: Google Gemini / 모델: ' + model)
            approved = st.checkbox('위 광고 원문을 Google Gemini로 전송하는 데 동의합니다', key='consent:' + plan.digest())
            if st.button('AI 광고 문장으로 만들기', disabled=not approved, key='ai-execute:' + project.id):
                try:
                    with st.spinner('번호별 광고 문장을 다듬고 있습니다…'):
                        response = execute_plan(plan, plan.digest(), api_key=api_key or None)
                        result = CopyResult.model_validate(response['result'])
                        cards = cards_from_copy(briefs, result, assignments, service.root)
                    activate(service.apply_numbered(st.session_state.project, cards))
                    st.session_state.selected_card = cards[0].id
                    st.session_state.ai_notice = response['warnings']
                    st.rerun()
                except Exception:
                    st.error('문장 작성을 마치지 못했습니다. 키·모델 또는 번호·숫자·취소 조건을 확인하세요. 자동 재전송하지 않습니다.')


def edit_page(service: Studio):
    project = st.session_state.get('project')
    if not project:
        st.markdown('<div class="studio-kicker">YOUR WEEKLY CREATIVE DESK</div>', unsafe_allow_html=True)
        st.title('이번 주 이야기를,\n한 장의 광고로.')
        st.markdown('<div class="studio-intro">문구를 적고, 사진을 고르고, 예배 화면에 띄워 보세요.<br>매주 반복하는 광고 제작을 한곳에서 이어갑니다.</div>', unsafe_allow_html=True)
        st.info('왼쪽에서 주간 광고 이름과 기준 날짜를 정하고 시작하세요.')
        cols = st.columns(3)
        for column, title, text in zip(cols, TEMPLATES.values(), ['중요한 안내를 크고 명확하게.', '함께한 순간에 소식을 더해요.', 'Song List와 예배 순서를 한눈에.']):
            with column:
                st.subheader(title)
                st.write(text)
        return
    st.markdown('<div class="studio-kicker">WEEKLY WORKSPACE</div>', unsafe_allow_html=True)
    st.title(project.name)
    st.caption(f'{project.week:%Y.%m.%d} 기준 · 저장된 광고 {len(project.cards)}개 · 편집 후 저장하면 제작 기록에 남습니다.')
    if project.copied_from:
        st.warning('이전 광고를 복사한 작업입니다. 유지할 광고도 날짜·장소·담당자를 확인해 주세요.')
    if st.session_state.get('ai_notice'):
        with st.expander('AI 검토 항목', expanded=True):
            for item in st.session_state.ai_notice:
                st.write('• ' + item)
    intake(service, project)
    cols = st.columns(2)
    for column, template in zip(cols, ['notice', 'photo']):
        if column.button(TEMPLATES[template] + ' 추가', key='add:' + template, width='stretch'):
            append_cards(service, [empty_card(template, project.week)])
            st.rerun()
    source = service.root / 'outputs/phase2-cover/cover-input.json'
    if source.is_file() and not any(card.data.get('worship') for card in project.cards) and st.button('고정 예배 표지 적용', width='stretch'):
        try:
            ad = Announcement.model_validate_json(source.read_text(encoding='utf-8'))
            ad.worship.service_date, ad.worship.confirmed = project.week, False
            append_cards(service, [Card(data=ad.model_dump(mode='json'))])
            st.rerun()
        except (ValueError, OSError) as exc:
            st.error(str(exc))
    with st.expander('기존 입력 JSON 가져오기'):
        imported = st.file_uploader('광고 JSON', type=['json'], key='import:' + project.id)
        if imported and st.button('입력 파일에서 광고 추가'):
            try:
                raw = json.loads(imported.getvalue().decode('utf-8-sig'))
                ad = Announcement.model_validate(raw.get('input', raw))
                service.validate_paths(ad)
                append_cards(service, [Card(data=ad.model_dump(mode='json'))])
                st.rerun()
            except (ValueError, OSError) as exc:
                st.error('입력 파일을 확인하세요: ' + str(exc))
    if not project.cards:
        st.markdown('<div class="studio-note">위에서 광고 종류를 선택하거나 여러 광고 원문을 한 번에 입력해 보세요.</div>', unsafe_allow_html=True)
        return
    ids = [card.id for card in project.cards]
    selected = st.session_state.get('selected_card')
    if selected not in ids:
        selected = ids[0]
    labels = {card.id: ('표지 · ' if card.data.get('worship') else f'{card.number}번 · ' if card.number is not None else f'추가 {i} · ') + (card.data.get('title') or '제목 없는 광고') for i, card in enumerate(project.cards, 1)}
    selected = st.selectbox('편집할 광고', ids, index=ids.index(selected), format_func=labels.get,
                            key=f'card-selector:{project.id}:{st.session_state.get("editor_epoch", 0)}')
    st.session_state.selected_card = selected
    index = ids.index(selected)
    a, b, _ = st.columns([1, 1, 5])
    for column, label, offset in [(a, '위로 이동', -1), (b, '아래로 이동', 1)]:
        can_move = 0 <= index + offset < len(ids) and not project.cards[index].data.get('worship') and not project.cards[index + offset].data.get('worship')
        if column.button(label, disabled=not can_move, key='move:' + str(offset)):
            edited = project.model_copy(deep=True)
            edited.cards[index], edited.cards[index + offset] = edited.cards[index + offset], edited.cards[index]
            persist(service, edited)
            st.rerun()
    editor(service, project, project.cards[index])
    st.divider()
    st.subheader('한 주 광고 완성하기')
    dirty = any(item['data'] != card.data or item['enabled'] != card.enabled or item['reviewed'] != card.reviewed
                for card in project.cards if (item := st.session_state.get('editor_drafts', {}).get(project.id + ':' + card.id)))
    if dirty:
        st.info('저장하지 않은 수정 사항이 있습니다. 전체 생성·다운로드 전에 저장해 주세요.')
    if st.button('저장된 광고 전체 생성 · 변경된 광고만', disabled=dirty):
        edited = project.model_copy(deep=True)
        included = [card for card in edited.cards if card.enabled]
        progress = st.progress(0.0)
        failures = []
        for i, card in enumerate(included):
            try:
                if not service.current(card) or card.artifact['draft']:
                    rendered = service.generate(card, RenderOptions())
                    card.data = rendered.data
                    card.artifact = rendered.artifact
            except Exception as exc:
                failures.append(f'{card.data.get("title") or "제목 없음"}: {exc}')
            progress.progress((i + 1) / len(included))
        persist(service, edited)
        st.session_state.batch_errors = failures
        st.rerun()
    for message in st.session_state.get('batch_errors', []):
        st.error(message)
    kind = st.radio('전체 다운로드 형식', ['PNG', 'JPG'], horizontal=True)
    # 내려받을 때까지 ZIP을 반복 생성하지 않는다. 현재 상태가 유효한 경우에만 제공한다.
    included = [card for card in project.cards if card.enabled]
    ready = included and not dirty and all(card.reviewed and service.current(card) and not card.artifact['draft'] for card in included)
    if ready:
        st.download_button('전체 이미지 ZIP 다운로드', service.bundle(project, kind),
            file_name=f'church-studio-{project.week}-{kind.lower()}.zip', mime='application/zip', type='primary')
    else:
        st.caption('포함된 광고를 모두 검토·저장하고 송출본으로 생성하면 전체 ZIP을 받을 수 있습니다.')


def photos_page(service: Studio):
    st.title('사진 보관함')
    st.write('사진·로고·배경을 올려 두고 각 광고에서 선택하세요. 파일은 이 컴퓨터에 저장됩니다.')
    files = st.file_uploader('사진 여러 장 올리기', type=['png', 'jpg', 'jpeg', 'webp'], accept_multiple_files=True, key='library-upload')
    if st.button('보관함에 저장', disabled=not files):
        count = 0
        for uploaded in files:
            try:
                service.upload(uploaded.name, uploaded.getvalue())
                count += 1
            except (ValueError, OSError) as exc:
                st.error(f'{uploaded.name}: {exc}')
        st.success(f'{count}개 파일을 보관함에 저장했습니다. 광고 편집에서 연결하세요.')
    assets = service.uploads()
    if not assets:
        st.info('아직 등록한 사진이 없습니다. PNG·JPG·WebP, 파일당 최대 20 MB를 지원합니다.')
    for i, asset in enumerate(assets):
        if i % 3 == 0:
            cols = st.columns(3)
        with cols[i % 3]:
            st.image(asset['path'], width='stretch')
            st.write(asset['name'])
            st.caption(f'{asset["width"]} × {asset["height"]}')


def history_page(service: Studio):
    st.title('제작 기록')
    st.write('기존 주간 광고를 열거나 새 주로 복사해 변경할 광고만 수정하세요.')
    records = service.projects()
    if not records:
        st.info('아직 저장된 제작 기록이 없습니다.')
        return
    labels = {r['id']: f'{r["week"]} · {r["name"]}' for r in records}
    selected = st.selectbox('주간 광고 선택', list(labels), format_func=labels.get)
    source = service.get(selected)
    st.caption(f'광고 {len(source.cards)}개 · 마지막 저장 {next(r["updated_at"] for r in records if r["id"] == selected)} UTC')
    if st.button('이 작업 이어서 편집'):
        activate(source)
        st.session_state.pending_nav = '광고 편집'
        st.rerun()
    with st.form('clone-project'):
        name = st.text_input('새 주간 광고 이름', value=source.name + ' 복사본', max_chars=100)
        week = st.date_input('새 기준 날짜', value=source.week + timedelta(days=7))
        st.caption('원본은 유지합니다. 표지 날짜는 새 날짜로 바꾸고 모든 광고의 검토 표시를 초기화합니다.')
        if st.form_submit_button('새 주로 복사', type='primary'):
            try:
                activate(service.clone(source, name, week))
                st.session_state.pending_nav = '광고 편집'
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    for i, card in enumerate(source.cards, 1):
        with st.expander(f'{i:02d} · {card.data.get("title") or "제목 없는 광고"}'):
            st.write(TEMPLATES.get(card.data.get('template'), '광고'))
            if card.artifact and service.current(card):
                st.image(str(service.result_path(card.artifact['png'])), width='stretch')


def archive_page(service: Studio):
    st.title('기존 교회 광고')
    st.write('기존 자료는 디자인 참고용으로만 표시합니다. 원본 파일은 수정하지 않습니다.')
    archive = service.root / 'data/archive'
    weeks = sorted([p for p in archive.iterdir() if p.is_dir()]) if archive.is_dir() else []
    if not weeks:
        st.info('data/archive에 참고할 이미지를 넣어 주세요.')
        return
    folder = st.selectbox('자료 폴더', weeks, format_func=lambda p: p.name)
    paths = [p for p in folder.iterdir() if p.suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp'}]
    for i, path in enumerate(sorted(paths)):
        if i % 2 == 0:
            cols = st.columns(2)
        with cols[i % 2]:
            try:
                st.image(str(path), width='stretch')
                st.caption(path.name)
            except Exception:
                st.warning('읽을 수 없는 이미지: ' + path.name)


def cover_settings_page(service: Studio):
    st.title('표지 기본 설정')
    st.write('교회 고정정보를 최초 한 번 설정합니다. 주간 편집에서는 날짜·곡명·예배 담당자·사진만 바꿉니다.')
    fixed = service.cover_settings()
    with st.form('cover-settings'):
        settings = {}
        for field, label in [('church', '교회 이름'), ('location', '예배 장소'), ('brand', '브랜드'), ('motto', '슬로건')]:
            settings[field] = st.text_input(label, value=fixed[field], max_chars=100)
        settings['welcome'] = st.text_area('고정 환영 문구', value=fixed['welcome'], max_chars=200)
        if st.form_submit_button('표지 고정정보 저장', type='primary'):
            try:
                service.save_cover_settings(settings)
                st.success('저장했습니다. 기존 표지는 편집 화면에서 다시 저장·생성하면 새 설정이 반영됩니다.')
            except ValueError as exc:
                st.error(str(exc))


def main(root: Path):
    st.set_page_config(page_title='Church Studio · 주간 광고', page_icon='◻', layout='wide')
    st.markdown(STYLE, unsafe_allow_html=True)
    service = Studio(root)
    if 'pending_nav' in st.session_state:
        st.session_state.nav = st.session_state.pop('pending_nav')
    if 'project' not in st.session_state and service.projects():
        activate(service.get(service.projects()[0]['id']))
    with st.sidebar:
        st.markdown('### CHURCH\n### STUDIO')
        st.caption('매주의 소식을 담는 작업실')
        nav = st.radio('작업 메뉴', ['광고 편집', '사진 보관함', '제작 기록', '기존 자료', '표지 기본 설정'], key='nav')
        st.divider()
        with st.form('new-project'):
            st.markdown('**새 주간 광고**')
            name = st.text_input('주간 광고 이름', value='이번 주 광고', max_chars=100)
            week = st.date_input('기준 날짜', value=today())
            if st.form_submit_button('새 작업 시작', type='primary', width='stretch'):
                try:
                    activate(service.new_project(name, week))
                    st.session_state.pending_nav = '광고 편집'
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
        st.divider()
        st.caption('로컬 작업실 · 자료는 이 컴퓨터에 저장\n\nAI 전송은 별도 동의 후 실행됩니다.')
    {'광고 편집': edit_page, '사진 보관함': photos_page, '제작 기록': history_page, '기존 자료': archive_page, '표지 기본 설정': cover_settings_page}[nav](service)
