from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone

import pytest

from constants import JOBS
from seeding import compute_historical_stats, make_balanced_groups
from storage import (
    GROUP_RESULT_HEADERS,
    MATCH_RESULT_HEADERS,
    SURVEY_RESULT_HEADERS,
    build_submission_bundle,
)
from tournament import TournamentSession


def completed_session() -> TournamentSession:
    stats, history_count = compute_historical_stats(JOBS, [])
    groups, metadata = make_balanced_groups(
        JOBS,
        stats,
        history_count,
        rng=random.Random(303),
    )
    session = TournamentSession(
        mode="preference",
        groups=groups,
        seeding_metadata=metadata,
        random_seed=404,
    )

    while session.phase != "finished":
        if session.phase in ("group_match", "knockout_match"):
            session.record_choice(1)
        else:
            session.continue_from_summary()
    return session


def test_submission_bundle_has_name_top4_and_all_detail_rows() -> None:
    session = completed_session()
    started = datetime(2026, 7, 11, 1, 0, tzinfo=timezone.utc)
    completed = started + timedelta(minutes=12)

    bundle = build_submission_bundle(
        session,
        participant_session_id="participant-test",
        participant_name=" 김재경 ",
        selection_reason="  업무 책임과 일정 부담을 고려함  ",
        started_at=started,
        completed_at=completed,
        response_id="response-test",
    )

    assert bundle.response_id == "response-test"
    assert bundle.summary_row["participant_name"] == "김재경"
    assert bundle.summary_row["selection_reason"] == "업무 책임과 일정 부담을 고려함"
    assert bundle.summary_row["selection_count"] == 56
    assert bundle.summary_row["duration_seconds"] == 720
    assert bundle.summary_row["third_place"] == session.third_place
    assert bundle.summary_row["fourth_place"] == session.fourth_place
    assert len(json.loads(bundle.summary_row["final_top4_json"])) == 4
    assert bundle.summary_row["unit_separation_complete"] is True
    assert len(bundle.group_rows) == 20
    assert len(bundle.match_rows) == 56
    assert len({row["row_key"] for row in bundle.group_rows}) == 20
    assert len({row["row_key"] for row in bundle.match_rows}) == 56
    assert sum(bool(row["top2"]) for row in bundle.group_rows) == 8
    assert sum(bool(row["qualified"]) for row in bundle.group_rows) == 16
    assert all(row["source_unit"] for row in bundle.group_rows)
    assert all(row["same_unit_count_in_group"] == 1 for row in bundle.group_rows)

    assert set(bundle.summary_row) == set(SURVEY_RESULT_HEADERS)
    assert all(set(row) == set(GROUP_RESULT_HEADERS) for row in bundle.group_rows)
    assert all(set(row) == set(MATCH_RESULT_HEADERS) for row in bundle.match_rows)


def test_submission_bundle_rejects_blank_name() -> None:
    with pytest.raises(ValueError, match="이름"):
        build_submission_bundle(
            completed_session(),
            participant_session_id="participant-test",
            participant_name="   ",
            started_at=datetime.now(timezone.utc),
        )


def test_backup_json_is_utf8_and_contains_korean_name() -> None:
    bundle = build_submission_bundle(
        completed_session(),
        participant_session_id="participant-test",
        participant_name="김재경",
        started_at=datetime.now(timezone.utc),
        response_id="response-json-test",
    )
    decoded = bundle.as_json_bytes().decode("utf-8")
    assert "선호조사" in decoded
    assert "김재경" in decoded
    assert "group_results" in decoded
    assert "match_results" in decoded


class FakeReadWorksheet:
    def __init__(self, values: list[list[str]]) -> None:
        self.values = values

    def get_all_values(self) -> list[list[str]]:
        return self.values


class FakeAppendWorksheet:
    def __init__(self) -> None:
        self.rows: list[list[object]] = []

    def get(self, _range: str) -> list[list[object]]:
        return [["response_id", "row_key"], *[row[:2] for row in self.rows]]

    def append_rows(self, rows: list[list[object]], **_kwargs: object) -> None:
        self.rows.extend(rows)


def test_completed_history_is_filtered_by_mode_and_participant() -> None:
    from constants import GROUP_NAMES
    from storage import GoogleSheetsRepository, SURVEY_RESULTS_SHEET

    ranking_a = {
        group: list(JOBS[index * 5 : (index + 1) * 5])
        for index, group in enumerate(GROUP_NAMES)
    }
    ranking_b = {
        group: list(reversed(JOBS[index * 5 : (index + 1) * 5]))
        for index, group in enumerate(GROUP_NAMES)
    }

    header = list(SURVEY_RESULT_HEADERS)
    rows: list[list[str]] = [header]
    for mode, ranking, status, participant_id in (
        ("preference", ranking_a, "completed", "p1"),
        ("preference", ranking_b, "completed", "p2"),
        ("avoidance", ranking_b, "completed", "p3"),
        ("preference", ranking_b, "partial", "p4"),
    ):
        row = {key: "" for key in header}
        row["mode"] = mode
        row["status"] = status
        row["participant_session_id"] = participant_id
        row["group_rankings_json"] = json.dumps(ranking, ensure_ascii=False)
        rows.append([str(row[key]) for key in header])

    repository = object.__new__(GoogleSheetsRepository)
    repository._worksheets = {SURVEY_RESULTS_SHEET: FakeReadWorksheet(rows)}

    assert repository.load_completed_group_rankings(
        "preference", exclude_participant_session_id="p2"
    ) == [ranking_a]
    assert repository.load_completed_group_rankings("avoidance") == [ranking_b]


def test_append_retry_skips_existing_row_keys() -> None:
    from storage import GoogleSheetsRepository

    worksheet = FakeAppendWorksheet()
    repository = object.__new__(GoogleSheetsRepository)
    rows = [
        {"response_id": "r1", "row_key": "a", "value": 1},
        {"response_id": "r1", "row_key": "b", "value": 2},
    ]
    headers = ("response_id", "row_key", "value")

    assert repository._append_missing_rows(worksheet, headers, rows, "r1") == 2
    assert repository._append_missing_rows(worksheet, headers, rows, "r1") == 0
    assert len(worksheet.rows) == 2
