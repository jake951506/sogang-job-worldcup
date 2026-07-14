from __future__ import annotations

import json
import uuid
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from constants import (
    APP_VERSION,
    GROUP_NAMES,
    MAX_PARTICIPANT_NAME_LENGTH,
    MAX_SELECTION_REASON_LENGTH,
    MODE_CONFIG,
    TOTAL_SELECTIONS,
)
from tournament import TournamentSession

KST = timezone(timedelta(hours=9), name="KST")

SURVEY_RESULTS_SHEET = "survey_results"
GROUP_RESULTS_SHEET = "group_results"
MATCH_RESULTS_SHEET = "match_results"

# 새 열은 기존 운영 시트와의 자동 호환을 위해 항상 맨 뒤에 추가한다.
SURVEY_RESULT_HEADERS: tuple[str, ...] = (
    "response_id",
    "row_key",
    "participant_session_id",
    "started_at_utc",
    "completed_at_utc",
    "completed_at_kst",
    "duration_seconds",
    "mode",
    "mode_label",
    "status",
    "champion",
    "runner_up",
    "selection_count",
    "grouping_method",
    "seeding_algorithm_version",
    "history_response_count",
    "grouping_random_seed",
    "tournament_random_seed",
    "groups_json",
    "group_rankings_json",
    "group_wins_json",
    "seed_scores_json",
    "pots_json",
    "app_version",
    # v3.0 additions
    "third_place",
    "fourth_place",
    "same_mode_history_response_count",
    "cross_mode_history_response_count",
    "cross_mode_source",
    "same_mode_weight",
    "cross_mode_weight",
    "cross_mode_pots_json",
    "seed_components_json",
    # v3.1 additions (append-only for safe sheet migration)
    "participant_name",
    "final_top4_json",
    "job_units_json",
    "group_units_json",
    "group_unit_counts_json",
    "same_unit_collision_pairs",
    "same_unit_extra_jobs",
    "unit_separation_complete",
    "solver_fallback_used",
    # v3.3 additions
    "selection_reason",
)

GROUP_RESULT_HEADERS: tuple[str, ...] = (
    "response_id",
    "row_key",
    "participant_session_id",
    "completed_at_utc",
    "completed_at_kst",
    "mode",
    "group_name",
    "group_rank",
    "job",
    "group_wins",
    "group_losses",
    "qualified",
    "top2",
    "seed_score",
    "historical_appearances",
    "historical_top2_count",
    "historical_top2_rate",
    "historical_smoothed_top2_rate",
    "historical_average_rank",
    "app_version",
    # v3.0 additions
    "final_rank",
    "same_mode_seed_score",
    "cross_mode_seed_score",
    "cross_mode_weight",
    "cross_mode_historical_appearances",
    "cross_mode_historical_top2_count",
    "cross_mode_historical_top2_rate",
    "cross_mode_historical_average_rank",
    # v3.1 additions
    "source_unit",
    "same_unit_count_in_group",
)

MATCH_RESULT_HEADERS: tuple[str, ...] = (
    "response_id",
    "row_key",
    "participant_session_id",
    "completed_at_utc",
    "completed_at_kst",
    "mode",
    "sequence_no",
    "stage",
    "group_or_round",
    "match_no",
    "left_job",
    "right_job",
    "left_seed",
    "right_seed",
    "selected_side",
    "selected_job",
    "not_selected_job",
    "selected_seed",
    "not_selected_seed",
    "app_version",
)

SHEET_SCHEMAS: dict[str, tuple[str, ...]] = {
    SURVEY_RESULTS_SHEET: SURVEY_RESULT_HEADERS,
    GROUP_RESULTS_SHEET: GROUP_RESULT_HEADERS,
    MATCH_RESULTS_SHEET: MATCH_RESULT_HEADERS,
}


class StorageConfigurationError(RuntimeError):
    pass


class SheetSchemaError(RuntimeError):
    pass


@dataclass(frozen=True)
class SubmissionBundle:
    response_id: str
    summary_row: dict[str, Any]
    group_rows: list[dict[str, Any]]
    match_rows: list[dict[str, Any]]

    def as_backup_dict(self) -> dict[str, Any]:
        return {
            "summary": deepcopy(self.summary_row),
            "group_results": deepcopy(self.group_rows),
            "match_results": deepcopy(self.match_rows),
        }

    def as_json_bytes(self) -> bytes:
        return json.dumps(
            self.as_backup_dict(),
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def build_submission_bundle(
    session: TournamentSession,
    *,
    participant_session_id: str,
    participant_name: str,
    selection_reason: str = "",
    started_at: datetime,
    completed_at: datetime | None = None,
    response_id: str | None = None,
) -> SubmissionBundle:
    placements = [
        session.champion,
        session.runner_up,
        session.third_place,
        session.fourth_place,
    ]
    if session.phase != "finished" or any(value is None for value in placements):
        raise ValueError("1~4위가 확정된 완료 월드컵만 저장할 수 있습니다.")
    if len(set(placements)) != 4:
        raise ValueError("최종 1~4위 직무가 서로 달라야 합니다.")
    if session.selection_count != TOTAL_SELECTIONS:
        raise ValueError(
            f"완료 경기 수가 올바르지 않습니다: {session.selection_count}/{TOTAL_SELECTIONS}"
        )

    normalized_name = " ".join(str(participant_name).split())
    if not normalized_name:
        raise ValueError("참여자 이름이 필요합니다.")
    if len(normalized_name) > MAX_PARTICIPANT_NAME_LENGTH:
        raise ValueError(
            f"참여자 이름은 {MAX_PARTICIPANT_NAME_LENGTH}자 이하여야 합니다."
        )

    normalized_reason = " ".join(str(selection_reason).split())
    if len(normalized_reason) > MAX_SELECTION_REASON_LENGTH:
        raise ValueError(
            f"선택 이유 메모는 {MAX_SELECTION_REASON_LENGTH}자 이하여야 합니다."
        )

    response_id = response_id or str(uuid.uuid4())
    completed_at_utc = _as_utc(completed_at or datetime.now(timezone.utc))
    started_at_utc = _as_utc(started_at)
    completed_at_kst = completed_at_utc.astimezone(KST)
    duration_seconds = max(
        0, int((completed_at_utc - started_at_utc).total_seconds())
    )

    metadata = session.seeding_metadata
    job_stats = metadata.get("job_stats", {})
    if not isinstance(job_stats, Mapping):
        job_stats = {}
    job_units = metadata.get("job_units", {})
    if not isinstance(job_units, Mapping):
        job_units = {}
    group_units = metadata.get("group_units", {})
    if not isinstance(group_units, Mapping):
        group_units = {}
    group_unit_counts = metadata.get("group_unit_counts", {})
    if not isinstance(group_unit_counts, Mapping):
        group_unit_counts = {}

    seed_scores = {
        job: round(float(stat.get("seed_score", 0.0)), 8)
        for job, stat in job_stats.items()
        if isinstance(stat, Mapping)
    }
    seed_components = {
        job: {
            "combined_seed_score": round(float(stat.get("seed_score", 0.0)), 8),
            "same_mode_seed_score": round(
                float(stat.get("same_mode_seed_score", stat.get("seed_score", 0.0))),
                8,
            ),
            "cross_mode_seed_score": round(
                float(stat.get("cross_mode_seed_score", 0.0)), 8
            ),
            "cross_mode_weight": round(
                float(stat.get("cross_mode_weight", 0.0)), 8
            ),
        }
        for job, stat in job_stats.items()
        if isinstance(stat, Mapping)
    }

    summary_row: dict[str, Any] = {
        "response_id": response_id,
        "row_key": "summary",
        "participant_session_id": participant_session_id,
        "started_at_utc": started_at_utc.isoformat(),
        "completed_at_utc": completed_at_utc.isoformat(),
        "completed_at_kst": completed_at_kst.isoformat(),
        "duration_seconds": duration_seconds,
        "mode": session.mode,
        "mode_label": MODE_CONFIG[session.mode]["label"],
        "status": "completed",
        "champion": session.champion,
        "runner_up": session.runner_up,
        "selection_count": session.selection_count,
        "grouping_method": metadata.get("method", "unknown"),
        "seeding_algorithm_version": metadata.get("algorithm_version", "unknown"),
        "history_response_count": int(metadata.get("history_response_count", 0)),
        # 64비트 정수는 Google Sheets의 숫자 정밀도를 넘을 수 있어 문자열로 저장한다.
        "grouping_random_seed": str(metadata.get("grouping_random_seed", "")),
        "tournament_random_seed": str(session.random_seed),
        "groups_json": _json(session.groups),
        "group_rankings_json": _json(session.group_rankings),
        "group_wins_json": _json(session.group_wins),
        "seed_scores_json": _json(seed_scores),
        "pots_json": _json(metadata.get("pots", [])),
        "app_version": APP_VERSION,
        "third_place": session.third_place,
        "fourth_place": session.fourth_place,
        "same_mode_history_response_count": int(
            metadata.get("same_mode_history_response_count", 0)
        ),
        "cross_mode_history_response_count": int(
            metadata.get("cross_mode_history_response_count", 0)
        ),
        "cross_mode_source": str(metadata.get("cross_mode_source", "")),
        "same_mode_weight": round(float(metadata.get("same_mode_weight", 1.0)), 8),
        "cross_mode_weight": round(float(metadata.get("cross_mode_weight", 0.0)), 8),
        "cross_mode_pots_json": _json(metadata.get("cross_mode_pots", [])),
        "seed_components_json": _json(seed_components),
        "participant_name": normalized_name,
        "final_top4_json": _json(
            [
                {"rank": rank, "job": job}
                for rank, job in enumerate(session.final_top4, start=1)
            ]
        ),
        "job_units_json": _json(dict(job_units)),
        "group_units_json": _json(dict(group_units)),
        "group_unit_counts_json": _json(dict(group_unit_counts)),
        "same_unit_collision_pairs": int(
            metadata.get("same_unit_collision_pairs", 0)
        ),
        "same_unit_extra_jobs": int(metadata.get("same_unit_extra_jobs", 0)),
        "unit_separation_complete": bool(
            metadata.get("unit_separation_complete", False)
        ),
        "solver_fallback_used": bool(metadata.get("solver_fallback_used", False)),
        "selection_reason": normalized_reason,
    }

    final_rank_by_job = {
        str(session.champion): 1,
        str(session.runner_up): 2,
        str(session.third_place): 3,
        str(session.fourth_place): 4,
    }

    group_rows: list[dict[str, Any]] = []
    for group_name in GROUP_NAMES:
        ranking = session.group_rankings[group_name]
        unit_counts = Counter(str(job_units.get(job, "")) for job in ranking)
        for rank, job in enumerate(ranking, start=1):
            stat = job_stats.get(job, {})
            if not isinstance(stat, Mapping):
                stat = {}
            wins = session.group_wins[group_name][job]
            group_rows.append(
                {
                    "response_id": response_id,
                    "row_key": f"group-{group_name}-{rank:02d}",
                    "participant_session_id": participant_session_id,
                    "completed_at_utc": completed_at_utc.isoformat(),
                    "completed_at_kst": completed_at_kst.isoformat(),
                    "mode": session.mode,
                    "group_name": group_name,
                    "group_rank": rank,
                    "job": job,
                    "group_wins": wins,
                    "group_losses": 4 - wins,
                    "qualified": rank <= 4,
                    "top2": rank <= 2,
                    "seed_score": round(float(stat.get("seed_score", 0.0)), 8),
                    "historical_appearances": int(stat.get("appearances", 0)),
                    "historical_top2_count": int(stat.get("top2_count", 0)),
                    "historical_top2_rate": round(
                        float(stat.get("top2_rate", 0.0)), 8
                    ),
                    "historical_smoothed_top2_rate": round(
                        float(stat.get("smoothed_top2_rate", 0.0)), 8
                    ),
                    "historical_average_rank": round(
                        float(stat.get("average_rank", 3.0)), 8
                    ),
                    "app_version": APP_VERSION,
                    "final_rank": final_rank_by_job.get(job, ""),
                    "same_mode_seed_score": round(
                        float(
                            stat.get(
                                "same_mode_seed_score",
                                stat.get("seed_score", 0.0),
                            )
                        ),
                        8,
                    ),
                    "cross_mode_seed_score": round(
                        float(stat.get("cross_mode_seed_score", 0.0)), 8
                    ),
                    "cross_mode_weight": round(
                        float(stat.get("cross_mode_weight", 0.0)), 8
                    ),
                    "cross_mode_historical_appearances": int(
                        stat.get("cross_mode_appearances", 0)
                    ),
                    "cross_mode_historical_top2_count": int(
                        stat.get("cross_mode_top2_count", 0)
                    ),
                    "cross_mode_historical_top2_rate": round(
                        float(stat.get("cross_mode_top2_rate", 0.0)), 8
                    ),
                    "cross_mode_historical_average_rank": round(
                        float(stat.get("cross_mode_average_rank", 3.0)), 8
                    ),
                    "source_unit": str(job_units.get(job, "")),
                    "same_unit_count_in_group": int(
                        unit_counts[str(job_units.get(job, ""))]
                    ),
                }
            )

    match_rows: list[dict[str, Any]] = []
    for match in session.match_history:
        match_rows.append(
            {
                "response_id": response_id,
                "row_key": f"match-{int(match['sequence_no']):03d}",
                "participant_session_id": participant_session_id,
                "completed_at_utc": completed_at_utc.isoformat(),
                "completed_at_kst": completed_at_kst.isoformat(),
                "mode": session.mode,
                "sequence_no": int(match["sequence_no"]),
                "stage": match["stage"],
                "group_or_round": match["group_or_round"],
                "match_no": int(match["match_no"]),
                "left_job": match["left_job"],
                "right_job": match["right_job"],
                "left_seed": match["left_seed"],
                "right_seed": match["right_seed"],
                "selected_side": int(match["selected_side"]),
                "selected_job": match["selected_job"],
                "not_selected_job": match["not_selected_job"],
                "selected_seed": match["selected_seed"],
                "not_selected_seed": match["not_selected_seed"],
                "app_version": APP_VERSION,
            }
        )

    return SubmissionBundle(
        response_id=response_id,
        summary_row=summary_row,
        group_rows=group_rows,
        match_rows=match_rows,
    )


class GoogleSheetsRepository:
    """
    Google Sheets를 추가 전용 저장소로 사용한다.

    세부 행을 먼저 기록하고 survey_results 요약 행을 마지막에 기록한다.
    과거 시드 계산은 요약 행만 읽으므로 요약 행이 커밋 마커 역할을 한다.
    response_id + row_key를 확인해 동일 제출의 재시도도 중복 없이 처리한다.
    """

    def __init__(
        self,
        *,
        credentials_info: Mapping[str, Any],
        spreadsheet_id: str,
    ) -> None:
        if not spreadsheet_id or not spreadsheet_id.strip():
            raise StorageConfigurationError("Google 스프레드시트 ID가 비어 있습니다.")

        credentials = dict(credentials_info)
        private_key = credentials.get("private_key")
        if isinstance(private_key, str):
            credentials["private_key"] = private_key.replace("\\n", "\n")
        required = {"type", "project_id", "private_key", "client_email", "token_uri"}
        missing = sorted(required - set(credentials))
        if missing:
            raise StorageConfigurationError(
                "서비스 계정 비밀정보에 필요한 항목이 없습니다: " + ", ".join(missing)
            )

        try:
            import gspread
            from gspread.http_client import BackOffHTTPClient
        except ImportError as exc:
            raise StorageConfigurationError(
                "gspread가 설치되지 않았습니다. requirements.txt를 확인하세요."
            ) from exc

        self._gspread = gspread
        try:
            self.client = gspread.service_account_from_dict(
                credentials,
                http_client=BackOffHTTPClient,
            )
            self.spreadsheet = self.client.open_by_key(spreadsheet_id.strip())
        except Exception as exc:
            raise StorageConfigurationError(
                "Google Sheets 연결에 실패했습니다. 스프레드시트 공유 권한과 비밀정보를 확인하세요."
            ) from exc

        self._worksheets: dict[str, Any] = {}
        self.ensure_schema()

    @property
    def spreadsheet_title(self) -> str:
        return str(self.spreadsheet.title)

    def ensure_schema(self) -> None:
        for title, headers in SHEET_SCHEMAS.items():
            self._worksheets[title] = self._ensure_worksheet(title, headers)

    def _ensure_worksheet(self, title: str, headers: Sequence[str]) -> Any:
        try:
            worksheet = self.spreadsheet.worksheet(title)
        except self._gspread.WorksheetNotFound:
            try:
                worksheet = self.spreadsheet.add_worksheet(
                    title=title,
                    rows=1000,
                    cols=max(26, len(headers)),
                )
            except Exception:
                # 첫 동시 접속에서 다른 세션이 먼저 탭을 만들었을 수 있다.
                worksheet = self.spreadsheet.worksheet(title)

        expected = list(headers)
        try:
            current_cols = int(getattr(worksheet, "col_count", 0) or 0)
            if current_cols and current_cols < len(expected):
                worksheet.resize(cols=len(expected))
        except Exception as exc:
            raise SheetSchemaError(
                f"'{title}' 탭의 열 수를 현재 스키마에 맞게 확장하지 못했습니다."
            ) from exc

        existing = worksheet.row_values(1)
        if not existing:
            worksheet.update([expected], "A1")
            try:
                worksheet.freeze(rows=1)
            except Exception:
                pass
        elif existing[: len(expected)] == expected:
            pass
        elif expected[: len(existing)] == existing:
            # 이전 버전 헤더가 현재 헤더의 정확한 접두사이면 새 열만 안전하게 확장한다.
            worksheet.update([expected], "A1")
        else:
            raise SheetSchemaError(
                f"'{title}' 탭의 1행 헤더가 앱 스키마와 다릅니다. "
                "기존 데이터를 백업한 뒤 탭 이름을 바꾸거나 헤더를 복구하세요."
            )
        return worksheet

    def healthcheck(self) -> dict[str, str]:
        self.ensure_schema()
        return {
            "status": "ok",
            "spreadsheet_title": self.spreadsheet_title,
        }

    def load_completed_group_rankings(
        self,
        mode: str,
        *,
        exclude_participant_session_id: str | None = None,
    ) -> list[dict[str, list[str]]]:
        if mode not in MODE_CONFIG:
            raise ValueError(f"지원하지 않는 조사 유형입니다: {mode}")

        worksheet = self._worksheets[SURVEY_RESULTS_SHEET]
        values = worksheet.get_all_values()
        if len(values) <= 1:
            return []

        headers = values[0]
        index = {name: position for position, name in enumerate(headers)}
        required = {"mode", "status", "group_rankings_json"}
        if not required.issubset(index):
            raise SheetSchemaError("survey_results 탭에 필요한 열이 없습니다.")

        rankings: list[dict[str, list[str]]] = []
        for row in values[1:]:
            padded = row + [""] * (len(headers) - len(row))
            if padded[index["mode"]] != mode:
                continue
            if padded[index["status"]] != "completed":
                continue
            if (
                exclude_participant_session_id
                and "participant_session_id" in index
                and padded[index["participant_session_id"]]
                == exclude_participant_session_id
            ):
                continue
            raw = padded[index["group_rankings_json"]]
            try:
                parsed = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(parsed, dict):
                continue
            normalized: dict[str, list[str]] = {}
            valid = True
            for group_name in GROUP_NAMES:
                jobs = parsed.get(group_name)
                if not isinstance(jobs, list) or not all(
                    isinstance(job, str) for job in jobs
                ):
                    valid = False
                    break
                normalized[group_name] = jobs
            if valid:
                rankings.append(normalized)
        return rankings

    def load_admin_records(self) -> dict[str, list[dict[str, str]]]:
        """관리자 통계 화면용으로 세 탭의 전체 레코드를 반환한다."""
        self.ensure_schema()
        return {
            SURVEY_RESULTS_SHEET: self._worksheets[SURVEY_RESULTS_SHEET].get_all_records(),
            GROUP_RESULTS_SHEET: self._worksheets[GROUP_RESULTS_SHEET].get_all_records(),
            MATCH_RESULTS_SHEET: self._worksheets[MATCH_RESULTS_SHEET].get_all_records(),
        }

    def clear_all_survey_data(self) -> dict[str, int]:
        """세 결과 시트의 응답 행을 모두 삭제하고 헤더만 유지한다."""
        self.ensure_schema()
        headers_by_sheet = {
            SURVEY_RESULTS_SHEET: SURVEY_RESULT_HEADERS,
            GROUP_RESULTS_SHEET: GROUP_RESULT_HEADERS,
            MATCH_RESULTS_SHEET: MATCH_RESULT_HEADERS,
        }
        cleared: dict[str, int] = {}
        for title, headers in headers_by_sheet.items():
            worksheet = self._worksheets[title]
            existing = worksheet.get_all_values()
            cleared[title] = max(len(existing) - 1, 0)
            worksheet.clear()
            worksheet.update([list(headers)], "A1")
            try:
                worksheet.freeze(rows=1)
            except Exception:
                pass
        return cleared

    def save_submission(self, bundle: SubmissionBundle) -> dict[str, int | str]:
        self.ensure_schema()

        group_added = self._append_missing_rows(
            self._worksheets[GROUP_RESULTS_SHEET],
            GROUP_RESULT_HEADERS,
            bundle.group_rows,
            bundle.response_id,
        )
        match_added = self._append_missing_rows(
            self._worksheets[MATCH_RESULTS_SHEET],
            MATCH_RESULT_HEADERS,
            bundle.match_rows,
            bundle.response_id,
        )
        # 요약 행을 마지막에 기록해 완료된 제출만 과거 시드에 사용한다.
        summary_added = self._append_missing_rows(
            self._worksheets[SURVEY_RESULTS_SHEET],
            SURVEY_RESULT_HEADERS,
            [bundle.summary_row],
            bundle.response_id,
        )
        return {
            "response_id": bundle.response_id,
            "summary_rows_added": summary_added,
            "group_rows_added": group_added,
            "match_rows_added": match_added,
        }

    def _append_missing_rows(
        self,
        worksheet: Any,
        headers: Sequence[str],
        rows: Sequence[Mapping[str, Any]],
        response_id: str,
    ) -> int:
        existing_keys = self._existing_row_keys(worksheet, response_id)
        pending: list[list[Any]] = []
        seen_pending: set[str] = set()

        for row in rows:
            row_key = str(row.get("row_key", ""))
            if not row_key:
                raise ValueError("저장 행에 row_key가 없습니다.")
            if row_key in existing_keys or row_key in seen_pending:
                continue
            pending.append([row.get(header, "") for header in headers])
            seen_pending.add(row_key)

        if pending:
            worksheet.append_rows(
                pending,
                value_input_option="RAW",
                insert_data_option="INSERT_ROWS",
                table_range="A1",
            )
        return len(pending)

    @staticmethod
    def _existing_row_keys(worksheet: Any, response_id: str) -> set[str]:
        values = worksheet.get("A:B")
        keys: set[str] = set()
        for row in values[1:]:
            if not row or row[0] != response_id:
                continue
            if len(row) > 1 and row[1]:
                keys.add(str(row[1]))
        return keys
