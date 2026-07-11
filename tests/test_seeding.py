from __future__ import annotations

import random
from collections import defaultdict

from constants import GROUP_NAMES, JOBS, JOB_UNITS
from seeding import compute_historical_stats, make_balanced_groups


def sample_ranking() -> dict[str, list[str]]:
    """상위 4개가 각 조 1위, 다음 4개가 각 조 2위인 정상 순위표."""
    return {
        "A": [JOBS[0], JOBS[4], JOBS[8], JOBS[12], JOBS[16]],
        "B": [JOBS[1], JOBS[5], JOBS[9], JOBS[13], JOBS[17]],
        "C": [JOBS[2], JOBS[6], JOBS[10], JOBS[14], JOBS[18]],
        "D": [JOBS[3], JOBS[7], JOBS[11], JOBS[15], JOBS[19]],
    }


def reverse_sample_ranking() -> dict[str, list[str]]:
    """선호 축이 주 시드 축과 다르게 정렬되도록 만든 정상 순위표."""
    reversed_jobs = list(reversed(JOBS))
    return {
        "A": [
            reversed_jobs[0],
            reversed_jobs[4],
            reversed_jobs[8],
            reversed_jobs[12],
            reversed_jobs[16],
        ],
        "B": [
            reversed_jobs[1],
            reversed_jobs[5],
            reversed_jobs[9],
            reversed_jobs[13],
            reversed_jobs[17],
        ],
        "C": [
            reversed_jobs[2],
            reversed_jobs[6],
            reversed_jobs[10],
            reversed_jobs[14],
            reversed_jobs[18],
        ],
        "D": [
            reversed_jobs[3],
            reversed_jobs[7],
            reversed_jobs[11],
            reversed_jobs[15],
            reversed_jobs[19],
        ],
    }


def assigned_group(groups: dict[str, list[str]], job: str) -> str:
    return next(group for group in GROUP_NAMES if job in groups[group])


def assert_repeated_units_are_split(groups: dict[str, list[str]]) -> None:
    jobs_by_unit: dict[str, list[str]] = defaultdict(list)
    for job in JOBS:
        jobs_by_unit[JOB_UNITS[job]].append(job)

    for unit_jobs in jobs_by_unit.values():
        if len(unit_jobs) <= 1:
            continue
        assigned = [assigned_group(groups, job) for job in unit_jobs]
        assert len(assigned) == len(set(assigned))


def test_all_four_academic_affairs_jobs_are_in_different_groups() -> None:
    academic_affairs_jobs = list(JOBS[:4])
    assert all(JOB_UNITS[job] == "교무팀" for job in academic_affairs_jobs)

    stats, count = compute_historical_stats(JOBS, [sample_ranking()] * 10)
    groups, metadata = make_balanced_groups(
        JOBS,
        stats,
        count,
        rng=random.Random(20260713),
    )

    assigned = [assigned_group(groups, job) for job in academic_affairs_jobs]
    assert set(assigned) == set(GROUP_NAMES)
    assert metadata["same_unit_collision_pairs"] == 0


def test_historical_stats_use_only_valid_complete_rankings() -> None:
    valid = sample_ranking()
    invalid = {"A": list(JOBS[:5])}

    stats, count = compute_historical_stats(JOBS, [valid, invalid, valid])

    assert count == 2
    assert stats[JOBS[0]].appearances == 2
    assert stats[JOBS[0]].top2_count == 2
    assert stats[JOBS[16]].top2_count == 0
    assert stats[JOBS[0]].seed_score > stats[JOBS[4]].seed_score
    assert stats[JOBS[4]].seed_score > stats[JOBS[8]].seed_score


def test_balanced_groups_split_every_seed_pot_and_repeated_unit() -> None:
    stats, count = compute_historical_stats(JOBS, [sample_ranking()] * 20)
    groups, metadata = make_balanced_groups(
        JOBS,
        stats,
        count,
        rng=random.Random(20260711),
    )

    assert set(groups) == set(GROUP_NAMES)
    assert all(len(groups[group]) == 5 for group in GROUP_NAMES)
    assert {job for group in GROUP_NAMES for job in groups[group]} == set(JOBS)

    for pot in metadata["pots"]:
        assigned_groups = {assigned_group(groups, job) for job in pot}
        assert assigned_groups == set(GROUP_NAMES)

    assert_repeated_units_are_split(groups)
    assert metadata["same_unit_collision_pairs"] == 0
    assert metadata["unit_separation_complete"] is True


def test_no_history_still_produces_valid_random_unit_balanced_groups() -> None:
    stats, count = compute_historical_stats(JOBS, [])
    groups, metadata = make_balanced_groups(
        JOBS,
        stats,
        count,
        rng=random.Random(42),
    )

    assert count == 0
    assert metadata["method"] == "random_unit_stratified"
    assert all(len(groups[group]) == 5 for group in GROUP_NAMES)
    assert len({job for group in GROUP_NAMES for job in groups[group]}) == 20
    assert_repeated_units_are_split(groups)


def test_avoidance_groups_split_avoidance_preference_and_units() -> None:
    avoidance_stats, avoidance_count = compute_historical_stats(
        JOBS, [sample_ranking()] * 20
    )
    preference_stats, preference_count = compute_historical_stats(
        JOBS, [reverse_sample_ranking()] * 20
    )

    groups, metadata = make_balanced_groups(
        JOBS,
        avoidance_stats,
        avoidance_count,
        rng=random.Random(20260712),
        cross_stats=preference_stats,
        cross_history_response_count=preference_count,
        cross_source_mode="preference",
    )

    assert metadata["method"] == "historical_dual_unit_stratified"
    assert metadata["cross_mode_history_response_count"] == 20
    assert metadata["cross_mode_source"] == "preference"

    # 각 기피 시드 포트와 각 선호 시드 포트가 모두 A~D조에 하나씩 분산된다.
    for pot_name in ("pots", "cross_mode_pots"):
        for pot in metadata[pot_name]:
            assert {assigned_group(groups, job) for job in pot} == set(GROUP_NAMES)

    assert_repeated_units_are_split(groups)


def test_dual_axis_and_unit_assignment_is_valid_across_many_random_ties() -> None:
    avoidance_stats, avoidance_count = compute_historical_stats(
        JOBS, [sample_ranking()] * 3
    )
    preference_stats, preference_count = compute_historical_stats(
        JOBS, [reverse_sample_ranking()] * 3
    )

    for seed in range(25):
        groups, metadata = make_balanced_groups(
            JOBS,
            avoidance_stats,
            avoidance_count,
            rng=random.Random(seed),
            cross_stats=preference_stats,
            cross_history_response_count=preference_count,
            cross_source_mode="preference",
        )
        assert all(len(groups[group]) == 5 for group in GROUP_NAMES)
        assert len({job for group in GROUP_NAMES for job in groups[group]}) == 20
        for pot in metadata["cross_mode_pots"]:
            assert {assigned_group(groups, job) for job in pot} == set(GROUP_NAMES)
        assert_repeated_units_are_split(groups)
