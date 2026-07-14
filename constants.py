from __future__ import annotations

from typing import Final

APP_VERSION: Final[str] = "3.3.1"
APP_TITLE: Final[str] = "서강대학교 본부 직무 이상형 월드컵"
APP_CREDIT: Final[str] = "Developed by JK"
MAX_PARTICIPANT_NAME_LENGTH: Final[int] = 40
MAX_SELECTION_REASON_LENGTH: Final[int] = 1000

JOBS: Final[tuple[str, ...]] = (
    "교무팀 - 전임교원 업적평가·승진·재임용",
    "교무팀 - 전임교원 책임시수",
    "전임교원 급여 및 보상",
    "전임교원 신규임용",
    "학사지원팀 - 교과과정 개설·운영",
    "학사지원팀 - 수강신청",
    "학사지원팀 - 졸업사정·과목이수",
    "전략기획팀 - 장·단기 발전계획",
    "전략기획팀 - 교육부 인증·평가",
    "전략기획팀 - 국외평가",
    "예산팀 - 본예산 편성",
    "예산팀 - 예산조정",
    "교육혁신팀 - 교육혁신기획",
    "인사총무팀 - 정규직 인사·채용·노무",
    "인사총무팀 - 급여",
    "재무팀 - 자금 투자 및 운용",
    "재무팀 - 교비회계 결산 및 세무조정",
    "구매팀 - 이공대 연구장비·기자재(외자 포함)",
    "학생지원팀 - 국가장학금",
    "대학원혁신전략팀 - 대학원 제도 개편 및 전략기획",
)

# 조 편성에서 같은 소속의 업무가 한 조에 겹치지 않도록 사용하는 분류입니다.
# 원 목록에서 소속이 생략된 "전임교원 급여 및 보상"과 "전임교원 신규임용"도
# 확인된 소속에 따라 교무팀으로 분류했습니다. 교무팀의 네 업무는 가능한 경우
# A~D조에 하나씩 배치됩니다.
JOB_UNITS: Final[dict[str, str]] = {
    JOBS[0]: "교무팀",
    JOBS[1]: "교무팀",
    JOBS[2]: "교무팀",
    JOBS[3]: "교무팀",
    JOBS[4]: "학사지원팀",
    JOBS[5]: "학사지원팀",
    JOBS[6]: "학사지원팀",
    JOBS[7]: "전략기획팀",
    JOBS[8]: "전략기획팀",
    JOBS[9]: "전략기획팀",
    JOBS[10]: "예산팀",
    JOBS[11]: "예산팀",
    JOBS[12]: "교육혁신팀",
    JOBS[13]: "인사총무팀",
    JOBS[14]: "인사총무팀",
    JOBS[15]: "재무팀",
    JOBS[16]: "재무팀",
    JOBS[17]: "구매팀",
    JOBS[18]: "학생지원팀",
    JOBS[19]: "대학원혁신전략팀",
}

GROUP_NAMES: Final[tuple[str, ...]] = ("A", "B", "C", "D")
ROUND_ORDER: Final[tuple[str, ...]] = ("16강", "8강", "4강", "3·4위전", "결승")
TOTAL_SELECTIONS: Final[int] = 56

# 기피 조 편성에서 조별 시드 총합을 비교할 때 기피 이력을 70%,
# 선호 이력을 30% 반영합니다. 포트 분산 자체는 두 이력을 각각 독립적으로
# 적용하므로, 선호 상위권과 기피 상위권이 모두 서로 다른 조로 흩어집니다.
AVOIDANCE_PRIMARY_SEED_WEIGHT: Final[float] = 0.70

MODE_CONFIG: Final[dict[str, dict[str, str]]] = {
    "preference": {
        "label": "선호조사",
        "worldcup_label": "선호 월드컵",
        "short_label": "선호",
        "question": "둘 중 더 선호하는 직무를 선택해 주세요.",
        "winner_label": "1위 · 가장 선호하는 직무",
        "runner_label": "2위 · 두 번째로 선호하는 직무",
        "third_label": "3위 · 세 번째로 선호하는 직무",
        "fourth_label": "4위 · 네 번째로 선호하는 직무",
        "start_label": "선호조사 선택",
        "icon": "❤️",
        "description": "내가 더 맡고 싶은 직무를 매 경기 선택합니다.",
    },
    "avoidance": {
        "label": "기피조사",
        "worldcup_label": "기피 월드컵",
        "short_label": "기피",
        "question": "둘 중 더 기피하는 직무를 선택해 주세요.",
        "winner_label": "1위 · 가장 기피하는 직무",
        "runner_label": "2위 · 두 번째로 기피하는 직무",
        "third_label": "3위 · 세 번째로 기피하는 직무",
        "fourth_label": "4위 · 네 번째로 기피하는 직무",
        "start_label": "기피조사 선택",
        "icon": "⚠️",
        "description": "내가 더 피하고 싶은 직무를 매 경기 선택합니다.",
    },
}
