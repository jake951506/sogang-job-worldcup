from __future__ import annotations

import html
import hmac
import random
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import streamlit as st

from constants import (
    APP_CREDIT,
    APP_TITLE,
    GROUP_NAMES,
    JOBS,
    MAX_PARTICIPANT_NAME_LENGTH,
    MODE_CONFIG,
    TOTAL_SELECTIONS,
)
from seeding import compute_historical_stats, make_balanced_groups
from storage import (
    GoogleSheetsRepository,
    StorageConfigurationError,
    SubmissionBundle,
    build_submission_bundle,
)
from tournament import TournamentSession


st.set_page_config(
    page_title=APP_TITLE,
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_css() -> None:
    st.markdown(
        """
        <style>
        .block-container {
            max-width: 1120px;
            padding-top: 1.6rem;
            padding-bottom: 3rem;
        }
        h1, h2, h3 { letter-spacing: -0.035em; }
        div[data-testid="stMetric"] {
            border: 1px solid rgba(49, 51, 63, 0.16);
            border-radius: 0.85rem;
            padding: 0.7rem 0.9rem;
            background: rgba(255,255,255,0.55);
        }
        div[class*="st-key-choice-left-"] button,
        div[class*="st-key-choice-right-"] button {
            min-height: 10.5rem;
            white-space: normal;
            line-height: 1.5;
            font-size: 1.08rem;
            font-weight: 700;
            border-width: 2px;
            border-radius: 1rem;
            padding: 1.2rem;
        }
        div[class*="st-key-home-preference"] button,
        div[class*="st-key-home-avoidance"] button {
            min-height: 4.2rem;
            font-size: 1.05rem;
            font-weight: 700;
        }
        .hero-note {
            padding: 0.9rem 1rem;
            border-radius: 0.8rem;
            background: rgba(165, 0, 52, 0.07);
            border-left: 4px solid #A50034;
            margin-bottom: 1rem;
        }
        .result-card {
            padding: 1.1rem 1.2rem;
            border: 1px solid rgba(49, 51, 63, 0.16);
            border-radius: 1rem;
            margin-bottom: 0.8rem;
        }
        .jk-credit {
            text-align: right;
            font-size: 0.82rem;
            font-weight: 650;
            letter-spacing: 0.015em;
            color: rgba(49, 51, 63, 0.68);
            margin-top: -0.55rem;
            margin-bottom: 0.1rem;
        }
        .participant-note {
            text-align: right;
            font-size: 0.9rem;
            color: rgba(49, 51, 63, 0.72);
            margin-bottom: 0.35rem;
        }
        @media (max-width: 640px) {
            div[class*="st-key-choice-left-"] button,
            div[class*="st-key-choice-right-"] button {
                min-height: 8.5rem;
                font-size: 0.98rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_credit() -> None:
    st.markdown(
        f'<div class="jk-credit">{APP_CREDIT}</div>',
        unsafe_allow_html=True,
    )


def normalize_participant_name(value: str) -> str:
    return " ".join(str(value).split())


def init_state() -> None:
    defaults: dict[str, Any] = {
        "page": "home",
        "active_mode": None,
        "pending_mode": None,
        "participant_name": "",
        "tournament": None,
        "tournament_started_at": None,
        "participant_session_id": str(uuid.uuid4()),
        "completed_results": {},
        "submission_bundle": None,
        "save_state": "idle",
        "save_error": "",
        "save_receipt": None,
        "history_warning": "",
        "access_granted": False,
        "participation_finished": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def read_optional_app_setting(name: str, default: Any = "") -> Any:
    try:
        app_settings = st.secrets.get("app", {})
        return app_settings.get(name, default)
    except Exception:
        return default


@st.cache_resource(show_spinner=False)
def cached_repository() -> GoogleSheetsRepository:
    try:
        credentials = dict(st.secrets["gcp_service_account"])
        spreadsheet_id = str(st.secrets["google_sheets"]["spreadsheet_id"])
    except Exception as exc:
        raise StorageConfigurationError(
            "Google Sheets용 Streamlit 비밀정보가 설정되지 않았습니다."
        ) from exc
    return GoogleSheetsRepository(
        credentials_info=credentials,
        spreadsheet_id=spreadsheet_id,
    )


def get_repository() -> tuple[GoogleSheetsRepository | None, str]:
    try:
        return cached_repository(), ""
    except Exception as exc:
        return None, str(exc)


def enforce_optional_access_code() -> None:
    configured_code = str(read_optional_app_setting("access_code", "")).strip()
    if not configured_code or st.session_state.access_granted:
        return

    st.title("🔐 설문 접속 확인")
    st.write("관리자가 안내한 접속 코드를 입력해 주세요.")
    entered = st.text_input("접속 코드", type="password", key="access_code_input")
    if st.button("확인", type="primary", width="stretch"):
        if hmac.compare_digest(entered.strip(), configured_code):
            st.session_state.access_granted = True
            st.rerun()
        st.error("접속 코드가 올바르지 않습니다.")
    st.stop()


def start_tournament(mode: str) -> None:
    if mode not in MODE_CONFIG:
        st.error("지원하지 않는 조사 유형입니다.")
        return

    participant_name = normalize_participant_name(
        st.session_state.get("participant_name", "")
    )
    if not participant_name:
        st.session_state.pending_mode = mode
        st.session_state.page = "name_entry"
        st.rerun()
    st.session_state.participant_name = participant_name

    history_rankings: list[dict[str, list[str]]] = []
    cross_rankings: list[dict[str, list[str]]] = []
    warnings: list[str] = []
    repository, repository_error = get_repository()
    require_google_storage = bool(
        read_optional_app_setting("require_google_storage", False)
    )

    if repository is None and require_google_storage:
        st.error(
            "Google Sheets 연결이 필수로 설정되어 있어 조사를 시작할 수 없습니다. "
            "관리자가 Streamlit Secrets와 시트 공유 권한을 확인해야 합니다."
        )
        if repository_error:
            st.caption(repository_error)
        return

    current_participant_id = str(st.session_state.participant_session_id)
    if repository is not None:
        try:
            history_rankings = repository.load_completed_group_rankings(
                mode,
                exclude_participant_session_id=current_participant_id,
            )
        except Exception as exc:
            warnings.append(
                "동일 조사 유형의 과거 결과를 불러오지 못해 해당 시드 없이 "
                f"편성합니다. 원인: {exc}"
            )

        if mode == "avoidance":
            try:
                cross_rankings = repository.load_completed_group_rankings(
                    "preference",
                    exclude_participant_session_id=current_participant_id,
                )
            except Exception as exc:
                warnings.append(
                    "선호조사 교차 시드를 불러오지 못해 기피조사는 자체 시드만 "
                    f"사용합니다. 원인: {exc}"
                )
    elif repository_error:
        warnings.append(
            "Google Sheets가 연결되지 않아 저장된 과거 결과 없이 조를 편성합니다. "
            "조사는 진행할 수 있지만 완료 결과는 자동 저장되지 않습니다."
        )

    stats, valid_history_count = compute_historical_stats(JOBS, history_rankings)
    cross_stats = None
    cross_history_count = 0
    if mode == "avoidance":
        cross_stats, cross_history_count = compute_historical_stats(
            JOBS, cross_rankings
        )

    grouping_seed = secrets.randbits(63)
    groups, metadata = make_balanced_groups(
        JOBS,
        stats,
        valid_history_count,
        rng=random.Random(grouping_seed),
        cross_stats=cross_stats,
        cross_history_response_count=cross_history_count,
        cross_source_mode="preference" if cross_history_count else "",
    )
    metadata["grouping_random_seed"] = grouping_seed

    st.session_state.active_mode = mode
    st.session_state.pending_mode = None
    st.session_state.tournament = TournamentSession(
        mode=mode,
        groups=groups,
        seeding_metadata=metadata,
    )
    st.session_state.tournament_started_at = datetime.now(timezone.utc)
    st.session_state.history_warning = "\n\n".join(warnings)
    st.session_state.submission_bundle = None
    st.session_state.save_state = "idle"
    st.session_state.save_error = ""
    st.session_state.save_receipt = None
    st.session_state.participation_finished = False
    st.session_state.page = "tournament"
    st.rerun()

def reset_to_home() -> None:
    st.session_state.page = "home"
    st.session_state.active_mode = None
    st.session_state.pending_mode = None
    st.session_state.tournament = None
    st.session_state.tournament_started_at = None
    st.session_state.submission_bundle = None
    st.session_state.save_state = "idle"
    st.session_state.save_error = ""
    st.session_state.save_receipt = None
    st.session_state.history_warning = ""
    st.session_state.participation_finished = False
    st.rerun()


def select_survey(mode: str) -> None:
    if mode not in MODE_CONFIG:
        return
    st.session_state.pending_mode = mode
    st.session_state.page = "name_entry"
    st.rerun()


def finish_participation() -> None:
    """현재까지 완료한 한 개 또는 두 개 조사를 확정하고 종료 화면으로 이동한다."""
    st.session_state.participation_finished = True
    st.session_state.page = "complete"
    st.rerun()


def start_next_participant() -> None:
    """공용 PC에서도 다음 응답이 앞 참여자와 연결되지 않도록 초기화한다."""
    access_granted = bool(st.session_state.get("access_granted", False))
    st.session_state.page = "home"
    st.session_state.active_mode = None
    st.session_state.pending_mode = None
    st.session_state.participant_name = ""
    st.session_state.tournament = None
    st.session_state.tournament_started_at = None
    st.session_state.participant_session_id = str(uuid.uuid4())
    st.session_state.completed_results = {}
    st.session_state.submission_bundle = None
    st.session_state.save_state = "idle"
    st.session_state.save_error = ""
    st.session_state.save_receipt = None
    st.session_state.history_warning = ""
    st.session_state.participation_finished = False
    st.session_state.access_granted = access_granted
    st.rerun()


def render_sidebar() -> None:
    with st.sidebar:
        st.header("조사 안내")
        st.write("20개 직무 · 4개 조 · 총 56회 선택")
        st.caption("조별리그 40경기 + 결선 토너먼트 16경기")

        participant_name = normalize_participant_name(
            st.session_state.get("participant_name", "")
        )
        if participant_name:
            st.info(f"참여자: **{participant_name}**")

        repository, error = get_repository()
        if repository is not None:
            st.success(f"Google Sheets 연결됨\n\n`{repository.spreadsheet_title}`")
        else:
            st.warning("Google Sheets 미연결")
            with st.expander("연결 상태 보기"):
                st.write(error)

        if st.session_state.page == "tournament":
            st.divider()
            st.warning("중단하면 현재 진행 기록은 저장되지 않습니다.")
            if st.button("조사 중단 후 처음으로", width="stretch"):
                reset_to_home()
        elif st.session_state.page in ("home", "name_entry", "complete"):
            st.divider()
            if st.button("다음 참여자 시작", width="stretch"):
                start_next_participant()


def render_home() -> None:
    st.title("🏆 서강대학교 본부 20개 직무 조사")
    st.markdown(
        """
        <div class="hero-note">
        <strong>먼저 진행할 조사 하나를 선택해 주세요.</strong><br>
        선호조사 또는 기피조사 중 한 가지만 하고 마쳐도 됩니다. 한 조사를
        완료한 뒤에는 나머지 조사도 계속할지, 여기서 참여를 마칠지 직접
        선택하게 됩니다.
        </div>
        """,
        unsafe_allow_html=True,
    )

    completed = st.session_state.completed_results
    repository, repository_error = get_repository()
    require_google_storage = bool(
        read_optional_app_setting("require_google_storage", False)
    )
    storage_blocked = require_google_storage and repository is None
    if storage_blocked:
        st.error(
            "현재 Google Sheets 저장소가 연결되지 않아 설문 시작이 잠겨 있습니다. "
            "관리자가 배포용 Secrets와 시트 공유 권한을 확인해야 합니다."
        )
        if repository_error:
            st.caption(repository_error)

    col1, col2 = st.columns(2, gap="large")

    with col1:
        with st.container(border=True):
            config = MODE_CONFIG["preference"]
            st.subheader(f"{config['icon']} {config['label']}")
            st.write(config["description"])
            if "preference" in completed:
                st.success("이 참여 세션에서 완료됨")
            if st.button(
                config["start_label"],
                key="home-preference",
                type="primary",
                width="stretch",
                disabled=storage_blocked or "preference" in completed,
            ):
                select_survey("preference")

    with col2:
        with st.container(border=True):
            config = MODE_CONFIG["avoidance"]
            st.subheader(f"{config['icon']} {config['label']}")
            st.write(config["description"])
            if "avoidance" in completed:
                st.success("이 참여 세션에서 완료됨")
            if st.button(
                config["start_label"],
                key="home-avoidance",
                type="primary",
                width="stretch",
                disabled=storage_blocked or "avoidance" in completed,
            ):
                select_survey("avoidance")

    st.divider()
    with st.expander("진행 방식과 조 편성 원리", expanded=True):
        st.markdown(
            """
            **조별리그:** A~D조에 5개 직무씩 배정하고, 조 안에서 모든 직무가
            서로 한 번씩 맞붙습니다. 각 조 1~4위는 16강에 진출하고 5위만
            탈락합니다.

            **과거 상위권 분산:** 직무별 과거 조 1·2위 비율을 중심으로 시드
            점수를 만들고 4개씩 5개 포트로 나눕니다. 각 조가 모든 포트에서
            한 직무씩 받아 상위권이 한 조에 몰리지 않습니다.

            **기피조사의 선호 교차 분산:** 기피조사는 기피 기록뿐 아니라 과거
            선호조사의 시드 포트도 동시에 사용합니다. 선호 상위 1~4위권,
            5~8위권 등이 기피조사의 같은 조에 몰리는 것도 방지합니다. 현재
            참여자의 결과는 제외하고 앞선 완료 응답만 반영합니다.

            **같은 팀 업무 분산:** 교무팀, 학사지원팀, 전략기획팀, 예산팀,
            인사총무팀, 재무팀처럼 같은 소속에서 여러 업무가 출전한 경우에는
            가능한 한 서로 다른 조에 배치합니다. 시드 포트 조건과 동시에 완전
            분리가 불가능한 예외에서는 같은 팀 중복 수가 가장 적은 편성을 씁니다.

            **16강 이후:** A1-B4, C2-D3, C1-D4, A2-B3, B1-A4,
            D2-C3, D1-C4, B2-A3 순으로 시작합니다. 네 조 1위는 서로 다른
            8강 구역에 있어 4강 전에는 만나지 않습니다. 4강이 끝난 뒤
            3·4위전을 먼저 하고 결승을 진행해 최종 1~4위를 모두 확정합니다.

            **선택:** 직무 카드를 마우스로 누르거나 키보드 숫자 `1`, `2`를
            누릅니다. 한 조사당 총 56회 선택합니다.
            """
        )


def render_name_entry() -> None:
    mode = st.session_state.get("pending_mode")
    if mode not in MODE_CONFIG:
        st.session_state.page = "home"
        st.rerun()

    config = MODE_CONFIG[mode]
    st.title(f"✍️ {config['label']} 시작 전 이름 입력")
    st.markdown(
        f"""
        <div class="hero-note">
        선택한 조사: <strong>{config['icon']} {config['label']}</strong><br>
        게임을 시작하기 직전입니다. 결과를 구분할 수 있도록 본인 이름을
        입력해 주세요.
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("participant-name-form", clear_on_submit=False):
        entered_name = st.text_input(
            "이름",
            value=str(st.session_state.get("participant_name", "")),
            max_chars=MAX_PARTICIPANT_NAME_LENGTH,
            placeholder="예: 김재경",
            help="입력한 이름은 완료 결과와 함께 관리자용 Google Sheet에 저장됩니다.",
        )
        st.caption(
            "이름은 응답 결과를 구분하기 위한 용도로 저장됩니다. "
            "공개 화면에는 다른 참여자의 이름이 표시되지 않습니다."
        )
        submitted = st.form_submit_button(
            f"{config['label']} 시작",
            type="primary",
            width="stretch",
        )

    if submitted:
        normalized = normalize_participant_name(entered_name)
        if not normalized:
            st.error("이름을 입력해 주세요.")
        elif len(normalized) > MAX_PARTICIPANT_NAME_LENGTH:
            st.error(f"이름은 {MAX_PARTICIPANT_NAME_LENGTH}자 이하로 입력해 주세요.")
        else:
            st.session_state.participant_name = normalized
            with st.spinner("과거 결과를 반영해 조를 편성하고 있습니다..."):
                start_tournament(mode)

    if st.button("조사 선택 화면으로 돌아가기", width="stretch"):
        st.session_state.pending_mode = None
        st.session_state.page = "home"
        st.rerun()

def render_tournament_header(session: TournamentSession) -> None:
    config = MODE_CONFIG[session.mode]
    st.title(f"{config['icon']} {config['label']}")
    participant_name = normalize_participant_name(
        st.session_state.get("participant_name", "")
    )
    if participant_name:
        st.markdown(
            f'<div class="participant-note">참여자: {html.escape(participant_name)}</div>',
            unsafe_allow_html=True,
        )
    st.progress(
        session.progress_fraction,
        text=f"전체 진행: {session.selection_count}/{TOTAL_SELECTIONS}회 선택",
    )

    history_count = int(
        session.seeding_metadata.get("history_response_count", 0)
    )
    cross_history_count = int(
        session.seeding_metadata.get("cross_mode_history_response_count", 0)
    )

    if session.mode == "avoidance" and cross_history_count:
        st.caption(
            f"기피 과거 완료 응답 {history_count}건과 선호 과거 완료 응답 "
            f"{cross_history_count}건을 함께 반영해 두 기준으로 조를 분산했습니다."
        )
    elif history_count:
        st.caption(
            f"동일 조사 유형의 과거 완료 응답 {history_count}건을 반영해 "
            "조를 분산했습니다."
        )
    else:
        st.caption("유효한 동일 유형 과거 응답이 없어 무작위 균형 편성을 사용했습니다.")

    if bool(session.seeding_metadata.get("unit_separation_complete", False)):
        st.caption("같은 팀에서 나온 여러 업무도 서로 다른 조로 모두 분산했습니다.")
    else:
        collision_pairs = int(
            session.seeding_metadata.get("same_unit_collision_pairs", 0)
        )
        st.warning(
            "시드 포트 조건과 같은 팀 분산 조건을 동시에 완전히 만족할 수 없어 "
            f"같은 팀 조합 {collision_pairs}쌍만 남긴 최소 중복 편성을 사용했습니다."
        )

    if st.session_state.history_warning:
        st.warning(st.session_state.history_warning)

def render_match(session: TournamentSession) -> None:
    match = session.current_match
    if session.phase == "group_match":
        st.subheader(
            f"20강 조별리그 · {session.current_group}조 · "
            f"{session.group_match_index + 1}/10경기"
        )
    else:
        st.subheader(
            f"{session.current_round} · "
            f"{session.knockout_match_index + 1}/{len(session.knockout_matches)}경기"
        )

    st.markdown(f"### {MODE_CONFIG[session.mode]['question']}")
    st.caption("왼쪽은 키보드 1, 오른쪽은 키보드 2로도 선택할 수 있습니다.")

    left_col, right_col = st.columns(2, gap="large")
    match_key = session.selection_count + 1

    with left_col:
        left_clicked = st.button(
            f"① {match.left.job}\n\n{match.left.seed}",
            key=f"choice-left-{match_key}",
            shortcut="1",
            width="stretch",
        )
    with right_col:
        right_clicked = st.button(
            f"② {match.right.job}\n\n{match.right.seed}",
            key=f"choice-right-{match_key}",
            shortcut="2",
            width="stretch",
        )

    if left_clicked:
        handle_choice(session, 1)
    if right_clicked:
        handle_choice(session, 2)


def handle_choice(session: TournamentSession, side: int) -> None:
    event = session.record_choice(side)  # type: ignore[arg-type]
    if event == "finished":
        started_at = st.session_state.tournament_started_at
        if not isinstance(started_at, datetime):
            started_at = datetime.now(timezone.utc)
        bundle = build_submission_bundle(
            session,
            participant_session_id=st.session_state.participant_session_id,
            participant_name=st.session_state.participant_name,
            started_at=started_at,
        )
        st.session_state.submission_bundle = bundle
        st.session_state.save_state = "pending"
        st.session_state.page = "result"
    st.rerun()


def render_group_summary(session: TournamentSession) -> None:
    group_name = session.last_completed_group
    if not group_name:
        st.error("완료된 조 정보가 없습니다.")
        return

    st.subheader(f"{group_name}조 최종 순위")
    table = pd.DataFrame(session.completed_group_table(group_name))
    st.dataframe(table, hide_index=True, width="stretch")
    st.info("1~4위는 16강 진출, 5위는 탈락입니다.")

    is_last_group = session.group_index == len(GROUP_NAMES) - 1
    label = "16강 대진 시작" if is_last_group else "다음 조 진행"
    if st.button(
        label,
        type="primary",
        shortcut="Enter",
        width="stretch",
        key=f"continue-group-{group_name}",
    ):
        session.continue_from_summary()
        st.rerun()


def render_round_summary(session: TournamentSession) -> None:
    completed_round = session.last_completed_round or session.current_round
    st.subheader(f"{completed_round} 종료")

    if completed_round == "3·4위전":
        rows = [
            {"최종 순위": 3, "직무": session.third_place or "-"},
            {"최종 순위": 4, "직무": session.fourth_place or "-"},
        ]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        next_round = "결승"
    else:
        winner_rows = [
            {"경기": index, "진출 직무": participant.job, "시드": participant.seed}
            for index, participant in enumerate(session.round_winners, start=1)
        ]
        st.dataframe(pd.DataFrame(winner_rows), hide_index=True, width="stretch")
        next_round = {
            "16강": "8강",
            "8강": "4강",
            "4강": "3·4위전",
        }[completed_round]

    if st.button(
        f"{next_round} 시작",
        type="primary",
        shortcut="Enter",
        width="stretch",
        key=f"continue-round-{completed_round}",
    ):
        session.continue_from_summary()
        st.rerun()

def render_group_assignments(session: TournamentSession) -> None:
    with st.expander("현재 조 편성 보기"):
        unit_map = session.seeding_metadata.get("job_units", {})
        if not isinstance(unit_map, dict):
            unit_map = {}
        columns = st.columns(4)
        for column, group_name in zip(columns, GROUP_NAMES):
            with column:
                st.markdown(f"**{group_name}조**")
                rows = [
                    {"소속": unit_map.get(job, ""), "직무": job}
                    for job in session.groups[group_name]
                ]
                st.dataframe(
                    pd.DataFrame(rows),
                    hide_index=True,
                    width="stretch",
                )

def render_tournament() -> None:
    session = st.session_state.tournament
    if not isinstance(session, TournamentSession):
        st.error("진행 중인 조사 상태를 찾을 수 없습니다.")
        if st.button("처음으로"):
            reset_to_home()
        return

    render_tournament_header(session)
    render_group_assignments(session)

    if session.phase in ("group_match", "knockout_match"):
        render_match(session)
    elif session.phase == "group_summary":
        render_group_summary(session)
    elif session.phase == "round_summary":
        render_round_summary(session)
    elif session.phase == "finished":
        st.session_state.page = "result"
        st.rerun()


def attempt_save(bundle: SubmissionBundle) -> None:
    repository, error = get_repository()
    if repository is None:
        st.session_state.save_state = "unconfigured"
        st.session_state.save_error = error
        return

    try:
        receipt = repository.save_submission(bundle)
    except Exception as exc:
        st.session_state.save_state = "failed"
        st.session_state.save_error = str(exc)
        return

    st.session_state.save_state = "saved"
    st.session_state.save_error = ""
    st.session_state.save_receipt = receipt


def render_save_status(bundle: SubmissionBundle) -> None:
    if st.session_state.save_state == "pending":
        with st.spinner("완료 결과를 Google Sheets에 저장하고 있습니다..."):
            attempt_save(bundle)

    state = st.session_state.save_state
    if state == "saved":
        st.success(
            "Google Sheets에 저장되었습니다. "
            f"응답 ID: `{bundle.response_id}`"
        )
    elif state == "unconfigured":
        st.warning(
            "Google Sheets가 설정되지 않아 자동 저장하지 못했습니다. "
            "아래 JSON은 장애 시 수동 복구용입니다."
        )
    elif state == "failed":
        st.error(
            "Google Sheets 저장에 실패했습니다. 응답 ID를 유지한 채 다시 시도하면 "
            "이미 기록된 행은 건너뜁니다."
        )
        st.caption(st.session_state.save_error)
        if st.button("Google Sheets 저장 다시 시도", type="primary"):
            st.session_state.save_state = "pending"
            st.rerun()

    if state in ("unconfigured", "failed"):
        st.download_button(
            "비상 복구용 JSON 내려받기",
            data=bundle.as_json_bytes(),
            file_name=f"sogang-worldcup-{bundle.response_id}.json",
            mime="application/json",
            width="stretch",
        )


def render_result_tables(session: TournamentSession) -> None:
    with st.expander("조별 최종 순위"):
        tabs = st.tabs([f"{name}조" for name in GROUP_NAMES])
        for tab, group_name in zip(tabs, GROUP_NAMES):
            with tab:
                st.dataframe(
                    pd.DataFrame(session.completed_group_table(group_name)),
                    hide_index=True,
                    width="stretch",
                )

    with st.expander("결선 토너먼트 선택 기록"):
        rows = [
            {
                "라운드": row["stage"],
                "경기": row["match_no"],
                "선택": row["selected_job"],
                "상대": row["not_selected_job"],
            }
            for row in session.match_history
            if row["stage"] != "20강 조별리그"
        ]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def render_result() -> None:
    session = st.session_state.tournament
    bundle = st.session_state.submission_bundle
    if not isinstance(session, TournamentSession) or not isinstance(
        bundle, SubmissionBundle
    ):
        st.error("완료 결과를 찾을 수 없습니다.")
        if st.button("처음으로"):
            reset_to_home()
        return

    config = MODE_CONFIG[session.mode]
    st.title(f"{config['icon']} {config['label']} 완료")
    st.caption(f"참여자: {st.session_state.participant_name}")

    first, second = st.columns(2, gap="large")
    with first:
        st.metric(config["winner_label"], session.champion or "-")
    with second:
        st.metric(config["runner_label"], session.runner_up or "-")
    third, fourth = st.columns(2, gap="large")
    with third:
        st.metric(config["third_label"], session.third_place or "-")
    with fourth:
        st.metric(config["fourth_label"], session.fourth_place or "-")

    render_save_status(bundle)
    render_result_tables(session)

    st.session_state.completed_results[session.mode] = {
        "champion": session.champion,
        "runner_up": session.runner_up,
        "third_place": session.third_place,
        "fourth_place": session.fourth_place,
        "response_id": bundle.response_id,
        "saved": st.session_state.save_state == "saved",
    }

    st.divider()
    opposite_mode = "avoidance" if session.mode == "preference" else "preference"
    require_google_storage = bool(
        read_optional_app_setting("require_google_storage", False)
    )
    navigation_blocked = (
        require_google_storage and st.session_state.save_state != "saved"
    )
    if navigation_blocked:
        st.info(
            "운영 저장 필수 모드에서는 현재 결과가 Google Sheets에 저장된 뒤 "
            "참여 종료 또는 다음 조사로 이동할 수 있습니다."
        )

    if opposite_mode not in st.session_state.completed_results:
        st.subheader("이제 어떻게 할까요?")
        st.write(
            "현재 조사만으로 참여를 마치거나, 나머지 조사도 이어서 진행할 수 "
            "있습니다."
        )
        continue_col, finish_col = st.columns(2, gap="large")
        with continue_col:
            if st.button(
                f"{MODE_CONFIG[opposite_mode]['label']}도 계속하기",
                type="primary",
                width="stretch",
                disabled=navigation_blocked,
            ):
                with st.spinner("다음 조사 조를 편성하고 있습니다..."):
                    start_tournament(opposite_mode)
        with finish_col:
            if st.button(
                "여기서 참여 마치기",
                width="stretch",
                disabled=navigation_blocked,
            ):
                finish_participation()
    else:
        st.success("선호조사와 기피조사를 모두 완료했습니다.")
        if st.button(
            "두 조사 참여 마치기",
            type="primary",
            width="stretch",
            disabled=navigation_blocked,
        ):
            finish_participation()

def render_completion() -> None:
    completed = st.session_state.completed_results
    st.title("✅ 참여가 완료되었습니다")
    participant_name = normalize_participant_name(
        st.session_state.get("participant_name", "")
    )
    if participant_name:
        st.caption(f"참여자: {participant_name}")

    if len(completed) == 1:
        only_mode = next(iter(completed))
        st.success(
            f"{MODE_CONFIG[only_mode]['label']} 한 가지를 완료하고 참여를 "
            "마쳤습니다. 감사합니다."
        )
    elif len(completed) >= 2:
        st.success("선호조사와 기피조사를 모두 완료했습니다. 감사합니다.")
    else:
        st.info("완료된 조사 결과가 없습니다.")

    for mode in ("preference", "avoidance"):
        result = completed.get(mode)
        if not isinstance(result, dict):
            continue
        config = MODE_CONFIG[mode]
        with st.container(border=True):
            st.subheader(f"{config['icon']} {config['label']} 최종 1~4위")
            rows = [
                {"순위": 1, "직무": result.get("champion", "-")},
                {"순위": 2, "직무": result.get("runner_up", "-")},
                {"순위": 3, "직무": result.get("third_place", "-")},
                {"순위": 4, "직무": result.get("fourth_place", "-")},
            ]
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            if result.get("saved"):
                st.caption(f"Google Sheets 저장 완료 · 응답 ID `{result.get('response_id', '')}`")
            else:
                st.warning("이 결과는 Google Sheets 저장 완료 상태가 아닙니다.")

    st.divider()
    st.info(
        "공용 PC라면 아래 버튼을 눌러 다음 참여자의 세션을 새로 시작해 주세요."
    )
    if st.button("다음 참여자 시작", type="primary", width="stretch"):
        start_next_participant()


def main() -> None:
    inject_css()
    init_state()
    render_credit()
    enforce_optional_access_code()
    render_sidebar()

    page = st.session_state.page
    if page == "home":
        render_home()
    elif page == "name_entry":
        render_name_entry()
    elif page == "tournament":
        render_tournament()
    elif page == "result":
        render_result()
    elif page == "complete":
        render_completion()
    else:
        st.session_state.page = "home"
        st.rerun()


if __name__ == "__main__":
    main()
