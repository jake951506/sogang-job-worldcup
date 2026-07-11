from __future__ import annotations

import random
from collections import Counter
from dataclasses import asdict, dataclass, replace
from typing import Iterable, Mapping, Sequence

from constants import (
    AVOIDANCE_PRIMARY_SEED_WEIGHT,
    GROUP_NAMES,
    JOB_UNITS,
)


@dataclass(frozen=True)
class HistoricalJobStat:
    job: str
    appearances: int
    top2_count: int
    top2_rate: float
    smoothed_top2_rate: float
    average_rank: float
    smoothed_rank_score: float
    seed_score: float

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _is_valid_ranking(
    ranking: Mapping[str, Sequence[str]], expected_jobs: set[str]
) -> bool:
    if set(ranking) != set(GROUP_NAMES):
        return False
    flattened: list[str] = []
    for group_name in GROUP_NAMES:
        jobs = ranking.get(group_name, [])
        if len(jobs) != 5:
            return False
        flattened.extend(jobs)
    return len(flattened) == len(expected_jobs) and set(flattened) == expected_jobs


def compute_historical_stats(
    jobs: Sequence[str],
    completed_group_rankings: Iterable[Mapping[str, Sequence[str]]],
    *,
    prior_strength: float = 5.0,
    top2_weight: float = 0.85,
) -> tuple[dict[str, HistoricalJobStat], int]:
    """과거 조별 순위로 직무별 완화 시드 점수를 계산한다."""
    if not 0.0 <= top2_weight <= 1.0:
        raise ValueError("top2_weight는 0과 1 사이여야 합니다.")
    if prior_strength < 0:
        raise ValueError("prior_strength는 0 이상이어야 합니다.")

    expected_jobs = set(jobs)
    appearances = {job: 0 for job in jobs}
    top2_counts = {job: 0 for job in jobs}
    rank_sums = {job: 0.0 for job in jobs}
    rank_score_sums = {job: 0.0 for job in jobs}
    valid_response_count = 0

    for ranking in completed_group_rankings:
        if not _is_valid_ranking(ranking, expected_jobs):
            continue
        valid_response_count += 1
        for group_name in GROUP_NAMES:
            for rank, job in enumerate(ranking[group_name], start=1):
                appearances[job] += 1
                rank_sums[job] += rank
                # 1위=1.0, 2위=0.75, 3위=0.5, 4위=0.25, 5위=0.0
                rank_score_sums[job] += (5 - rank) / 4
                if rank <= 2:
                    top2_counts[job] += 1

    baseline_top2_rate = 2 / 5
    baseline_rank_score = 0.5
    rank_weight = 1.0 - top2_weight
    stats: dict[str, HistoricalJobStat] = {}

    for job in jobs:
        n = appearances[job]
        top2_count = top2_counts[job]
        raw_top2_rate = top2_count / n if n else 0.0
        average_rank = rank_sums[job] / n if n else 3.0

        denominator = n + prior_strength
        if denominator:
            smoothed_top2_rate = (
                top2_count + prior_strength * baseline_top2_rate
            ) / denominator
            smoothed_rank_score = (
                rank_score_sums[job] + prior_strength * baseline_rank_score
            ) / denominator
        else:
            smoothed_top2_rate = baseline_top2_rate
            smoothed_rank_score = baseline_rank_score

        seed_score = (
            top2_weight * smoothed_top2_rate
            + rank_weight * smoothed_rank_score
        )
        stats[job] = HistoricalJobStat(
            job=job,
            appearances=n,
            top2_count=top2_count,
            top2_rate=raw_top2_rate,
            smoothed_top2_rate=smoothed_top2_rate,
            average_rank=average_rank,
            smoothed_rank_score=smoothed_rank_score,
            seed_score=seed_score,
        )

    return stats, valid_response_count


def _validate_stats(
    jobs: Sequence[str], stats: Mapping[str, HistoricalJobStat], label: str
) -> None:
    missing = [job for job in jobs if job not in stats]
    if missing:
        raise ValueError(f"{label} 시드 통계가 없는 직무가 있습니다: {missing}")


def _normalize_units(
    jobs: Sequence[str], job_units: Mapping[str, str] | None
) -> dict[str, str]:
    source = JOB_UNITS if job_units is None else job_units
    normalized: dict[str, str] = {}
    for job in jobs:
        unit = str(source.get(job, "")).strip()
        # 소속을 모르는 항목은 직무 자체를 고유 소속처럼 취급해 잘못 묶지 않는다.
        normalized[job] = unit or f"미분류::{job}"
    return normalized


def _ordered_pots(
    jobs: Sequence[str],
    stats: Mapping[str, HistoricalJobStat],
    rng: random.Random,
) -> list[list[str]]:
    random_tiebreak = {job: rng.random() for job in jobs}
    ordered = sorted(
        jobs,
        key=lambda job: (-stats[job].seed_score, random_tiebreak[job]),
    )
    return [ordered[index : index + 4] for index in range(0, 20, 4)]


def _pot_index(pots: Sequence[Sequence[str]]) -> dict[str, int]:
    return {
        job: pot_number
        for pot_number, pot in enumerate(pots)
        for job in pot
    }


def _unit_metrics(
    groups: Mapping[str, Sequence[str]], units: Mapping[str, str]
) -> tuple[int, int, dict[str, dict[str, int]]]:
    collision_pairs = 0
    extra_jobs = 0
    group_counts: dict[str, dict[str, int]] = {}
    for group_name in GROUP_NAMES:
        counts = Counter(units[job] for job in groups[group_name])
        group_counts[group_name] = dict(counts)
        collision_pairs += sum(count * (count - 1) // 2 for count in counts.values())
        extra_jobs += sum(max(0, count - 1) for count in counts.values())
    return collision_pairs, extra_jobs, group_counts


def _balance_metric(
    groups: Mapping[str, Sequence[str]], scores: Mapping[str, float]
) -> tuple[float, float]:
    totals = [sum(scores[job] for job in groups[name]) for name in GROUP_NAMES]
    spread = max(totals) - min(totals)
    mean = sum(totals) / len(totals)
    squared_deviation = sum((value - mean) ** 2 for value in totals)
    return round(spread, 12), round(squared_deviation, 12)


def _assignment_metric(
    groups: Mapping[str, Sequence[str]],
    scores: Mapping[str, float],
    units: Mapping[str, str],
) -> tuple[int, int, float, float]:
    collisions, extras, _ = _unit_metrics(groups, units)
    spread, squared_deviation = _balance_metric(groups, scores)
    return collisions, extras, spread, squared_deviation


def _solve_once(
    jobs: Sequence[str],
    primary_index: Mapping[str, int],
    cross_index: Mapping[str, int] | None,
    units: Mapping[str, str],
    scores: Mapping[str, float],
    *,
    hard_unit_separation: bool,
    rng: random.Random,
    node_limit: int = 250_000,
) -> dict[str, list[str]] | None:
    """
    20개 직무를 네 조에 배정하는 작은 제약충족 문제를 푼다.

    각 조는 기본 시드 포트마다 한 직무를 받고, 교차 축이 있으면 교차 포트마다
    한 직무를 받는다. hard_unit_separation=True일 때는 같은 소속을 한 조에
    두지 않는다. 첫 포트를 네 조에 고정 배치해 조 이름 대칭을 제거한 뒤,
    남은 직무는 최소 잔여값(MRV) 방식으로 탐색한다.
    """
    groups: dict[str, list[str]] = {name: [] for name in GROUP_NAMES}
    used_primary = {name: set() for name in GROUP_NAMES}
    used_cross = {name: set() for name in GROUP_NAMES}
    used_units = {name: Counter() for name in GROUP_NAMES}
    group_totals = {name: 0.0 for name in GROUP_NAMES}

    first_pot_jobs = [job for job in jobs if primary_index[job] == 0]
    if len(first_pot_jobs) != len(GROUP_NAMES):
        raise RuntimeError("첫 번째 시드 포트의 크기가 올바르지 않습니다.")
    rng.shuffle(first_pot_jobs)

    for group_name, job in zip(GROUP_NAMES, first_pot_jobs):
        groups[group_name].append(job)
        used_primary[group_name].add(primary_index[job])
        if cross_index is not None:
            used_cross[group_name].add(cross_index[job])
        used_units[group_name][units[job]] += 1
        group_totals[group_name] += scores[job]

    remaining = set(jobs) - set(first_pot_jobs)
    random_priority = {job: rng.random() for job in jobs}
    nodes = 0

    def feasible_groups(job: str) -> list[str]:
        possible: list[str] = []
        p_index = primary_index[job]
        c_index = cross_index[job] if cross_index is not None else None
        unit = units[job]
        for group_name in GROUP_NAMES:
            if len(groups[group_name]) >= 5:
                continue
            if p_index in used_primary[group_name]:
                continue
            if c_index is not None and c_index in used_cross[group_name]:
                continue
            if hard_unit_separation and used_units[group_name][unit] > 0:
                continue
            possible.append(group_name)
        return possible

    def forward_check() -> bool:
        # 모든 남은 직무가 적어도 한 조에는 들어갈 수 있어야 한다.
        for pending_job in remaining:
            if not feasible_groups(pending_job):
                return False
        # 각 조의 빈 칸 수와 배정 가능한 남은 직무 수를 비교한다.
        for group_name in GROUP_NAMES:
            needed = 5 - len(groups[group_name])
            if needed <= 0:
                continue
            available = sum(
                group_name in feasible_groups(pending_job)
                for pending_job in remaining
            )
            if available < needed:
                return False
        return True

    def search() -> bool:
        nonlocal nodes
        nodes += 1
        if nodes > node_limit:
            return False
        if not remaining:
            return all(len(groups[name]) == 5 for name in GROUP_NAMES)

        candidates: list[tuple[int, int, float, str, list[str]]] = []
        unit_frequency = Counter(units[job] for job in remaining)
        for job in remaining:
            domain = feasible_groups(job)
            if not domain:
                return False
            # 도메인이 좁고, 같은 소속의 남은 업무가 많은 직무부터 배정한다.
            candidates.append(
                (
                    len(domain),
                    -unit_frequency[units[job]],
                    random_priority[job],
                    job,
                    domain,
                )
            )
        _, _, _, job, domain = min(candidates)

        unit = units[job]
        target_partial_total = sum(scores.values()) / len(GROUP_NAMES)
        domain_tiebreak = {name: rng.random() for name in domain}
        domain.sort(
            key=lambda group_name: (
                used_units[group_name][unit],
                abs((group_totals[group_name] + scores[job]) - target_partial_total),
                group_totals[group_name],
                domain_tiebreak[group_name],
            )
        )

        remaining.remove(job)
        for group_name in domain:
            groups[group_name].append(job)
            used_primary[group_name].add(primary_index[job])
            if cross_index is not None:
                used_cross[group_name].add(cross_index[job])
            used_units[group_name][unit] += 1
            group_totals[group_name] += scores[job]

            if forward_check() and search():
                return True

            group_totals[group_name] -= scores[job]
            used_units[group_name][unit] -= 1
            if used_units[group_name][unit] == 0:
                del used_units[group_name][unit]
            if cross_index is not None:
                used_cross[group_name].remove(cross_index[job])
            used_primary[group_name].remove(primary_index[job])
            groups[group_name].pop()

        remaining.add(job)
        return False

    if not forward_check() or not search():
        return None

    # 화면과 저장 결과에서 각 조의 직무 순서를 기본 시드 포트 순으로 정돈한다.
    for group_name in GROUP_NAMES:
        groups[group_name].sort(key=lambda job: primary_index[job])
    return groups


def _choose_assignment(
    jobs: Sequence[str],
    primary_pots: Sequence[Sequence[str]],
    cross_pots: Sequence[Sequence[str]] | None,
    units: Mapping[str, str],
    scores: Mapping[str, float],
    rng: random.Random,
) -> tuple[dict[str, list[str]], bool]:
    primary_index = _pot_index(primary_pots)
    cross_index = _pot_index(cross_pots) if cross_pots is not None else None

    best: dict[str, list[str]] | None = None
    best_metric: tuple[int, int, float, float] | None = None

    # 먼저 같은 소속 중복을 완전히 금지한 해를 여러 번 찾아 시드 균형이 가장
    # 좋은 것을 고른다. 무작위 재시작은 동점 포트에서도 편성이 고착되는 것을 막는다.
    hard_attempts = 48 if cross_pots is not None else 24
    for _ in range(hard_attempts):
        attempt_rng = random.Random(rng.getrandbits(64))
        candidate = _solve_once(
            jobs,
            primary_index,
            cross_index,
            units,
            scores,
            hard_unit_separation=True,
            rng=attempt_rng,
        )
        if candidate is None:
            continue
        metric = _assignment_metric(candidate, scores, units)
        if best_metric is None or metric < best_metric:
            best = candidate
            best_metric = metric

    if best is not None:
        return best, False

    # 시드 포트 조합상 완전 분리가 불가능한 경우에도 설문은 시작되어야 한다.
    # 같은 소속 중복을 허용하되 중복 수를 가장 먼저 최소화하는 해를 선택한다.
    fallback_attempts = 96
    for _ in range(fallback_attempts):
        attempt_rng = random.Random(rng.getrandbits(64))
        candidate = _solve_once(
            jobs,
            primary_index,
            cross_index,
            units,
            scores,
            hard_unit_separation=False,
            rng=attempt_rng,
        )
        if candidate is None:
            continue
        metric = _assignment_metric(candidate, scores, units)
        if best_metric is None or metric < best_metric:
            best = candidate
            best_metric = metric

    if best is None:
        raise RuntimeError("시드 포트 조건을 만족하는 조 편성을 만들지 못했습니다.")
    return best, True


def _single_mode_job_stats(
    jobs: Sequence[str], stats: Mapping[str, HistoricalJobStat]
) -> dict[str, dict[str, object]]:
    payload: dict[str, dict[str, object]] = {}
    for job in jobs:
        item = stats[job].as_dict()
        item.update(
            {
                "same_mode_seed_score": stats[job].seed_score,
                "cross_mode_seed_score": 0.0,
                "cross_mode_weight": 0.0,
                "cross_mode_appearances": 0,
                "cross_mode_top2_count": 0,
                "cross_mode_top2_rate": 0.0,
                "cross_mode_average_rank": 3.0,
            }
        )
        payload[job] = item
    return payload


def make_balanced_groups(
    jobs: Sequence[str],
    stats: Mapping[str, HistoricalJobStat],
    history_response_count: int,
    *,
    rng: random.Random | None = None,
    cross_stats: Mapping[str, HistoricalJobStat] | None = None,
    cross_history_response_count: int = 0,
    cross_source_mode: str = "",
    job_units: Mapping[str, str] | None = None,
    primary_weight: float = AVOIDANCE_PRIMARY_SEED_WEIGHT,
) -> tuple[dict[str, list[str]], dict[str, object]]:
    """
    과거 시드 포트, 교차 시드 포트, 소속 분산을 함께 만족하도록 조를 편성한다.

    - 모든 조는 동일 조사 시드 포트 1~5에서 한 직무씩 받는다.
    - 유효한 교차 이력이 있으면 모든 조는 교차 시드 포트 1~5에서도 한 직무씩 받는다.
    - 같은 팀에서 나온 업무는 가능한 한 서로 다른 조에 배치한다.
    - 위 조건을 만족하는 후보 중 조별 시드 점수 합이 균형적인 편성을 선택한다.
    """
    if len(jobs) != 20 or len(set(jobs)) != 20:
        raise ValueError("서로 다른 직무 20개가 필요합니다.")
    if not 0.0 <= primary_weight <= 1.0:
        raise ValueError("primary_weight는 0과 1 사이여야 합니다.")
    _validate_stats(jobs, stats, "동일 조사")

    rng = rng or random.Random()
    units = _normalize_units(jobs, job_units)
    primary_pots = _ordered_pots(jobs, stats, rng)

    use_cross = (
        cross_stats is not None and cross_history_response_count > 0
    )
    cross_pots: list[list[str]] | None = None
    cross_weight = 0.0

    if use_cross:
        assert cross_stats is not None
        _validate_stats(jobs, cross_stats, "교차 조사")
        cross_pots = _ordered_pots(jobs, cross_stats, rng)
        cross_weight = 1.0 - primary_weight
        combined_scores = {
            job: (
                primary_weight * stats[job].seed_score
                + cross_weight * cross_stats[job].seed_score
            )
            for job in jobs
        }
    else:
        combined_scores = {job: stats[job].seed_score for job in jobs}

    groups, fallback_used = _choose_assignment(
        jobs,
        primary_pots,
        cross_pots,
        units,
        combined_scores,
        rng,
    )

    flattened = [job for group_name in GROUP_NAMES for job in groups[group_name]]
    if len(flattened) != 20 or set(flattened) != set(jobs):
        raise RuntimeError("조 편성 결과가 올바르지 않습니다.")

    # 포트 분산 불변조건을 실행 시에도 확인한다.
    for pot in primary_pots:
        assigned = {
            group_name
            for group_name in GROUP_NAMES
            for job in pot
            if job in groups[group_name]
        }
        if assigned != set(GROUP_NAMES):
            raise RuntimeError("동일 조사 시드 포트가 네 조로 분산되지 않았습니다.")
    if cross_pots is not None:
        for pot in cross_pots:
            assigned = {
                group_name
                for group_name in GROUP_NAMES
                for job in pot
                if job in groups[group_name]
            }
            if assigned != set(GROUP_NAMES):
                raise RuntimeError("교차 조사 시드 포트가 네 조로 분산되지 않았습니다.")

    collision_pairs, extra_jobs, group_unit_counts = _unit_metrics(groups, units)
    group_totals = {
        group_name: sum(combined_scores[job] for job in groups[group_name])
        for group_name in GROUP_NAMES
    }

    if use_cross:
        assert cross_stats is not None
        job_stats: dict[str, dict[str, object]] = {}
        for job in jobs:
            combined = replace(stats[job], seed_score=combined_scores[job])
            item = combined.as_dict()
            item.update(
                {
                    "seed_score": combined_scores[job],
                    "same_mode_seed_score": stats[job].seed_score,
                    "cross_mode_seed_score": cross_stats[job].seed_score,
                    "cross_mode_weight": cross_weight,
                    "cross_mode_appearances": cross_stats[job].appearances,
                    "cross_mode_top2_count": cross_stats[job].top2_count,
                    "cross_mode_top2_rate": cross_stats[job].top2_rate,
                    "cross_mode_average_rank": cross_stats[job].average_rank,
                }
            )
            job_stats[job] = item
        method = (
            "historical_dual_unit_stratified"
            if history_response_count > 0
            else "cross_historical_dual_unit_stratified"
        )
        algorithm_version = "dual-seed-pot-unit-csp-v1"
    else:
        job_stats = _single_mode_job_stats(jobs, stats)
        method = (
            "historical_unit_stratified"
            if history_response_count > 0
            else "random_unit_stratified"
        )
        algorithm_version = "seed-pot-unit-csp-v1"

    metadata: dict[str, object] = {
        "algorithm_version": algorithm_version,
        "method": method,
        # backward-compatible field: the same-mode response count
        "history_response_count": history_response_count,
        "same_mode_history_response_count": history_response_count,
        "cross_mode_history_response_count": (
            cross_history_response_count if use_cross else 0
        ),
        # aliases retained for earlier app/analysis code
        "cross_history_response_count": (
            cross_history_response_count if use_cross else 0
        ),
        "cross_mode_source": cross_source_mode if use_cross else "",
        "cross_source_mode": cross_source_mode if use_cross else "",
        "same_mode_weight": primary_weight if use_cross else 1.0,
        "cross_mode_weight": cross_weight,
        "pots": primary_pots,
        "cross_mode_pots": cross_pots or [],
        # alias retained for older analysis/test code
        "cross_pots": cross_pots or [],
        "group_seed_totals": {
            group_name: round(group_totals[group_name], 8)
            for group_name in GROUP_NAMES
        },
        "job_stats": job_stats,
        "job_units": {job: units[job] for job in jobs},
        "group_units": {
            group_name: [units[job] for job in groups[group_name]]
            for group_name in GROUP_NAMES
        },
        "group_unit_counts": group_unit_counts,
        "same_unit_collision_pairs": collision_pairs,
        "same_unit_extra_jobs": extra_jobs,
        "unit_separation_complete": collision_pairs == 0,
        "solver_fallback_used": fallback_used,
    }
    return groups, metadata


def make_dually_balanced_groups(
    jobs: Sequence[str],
    primary_stats: Mapping[str, HistoricalJobStat],
    cross_stats: Mapping[str, HistoricalJobStat],
    primary_history_response_count: int,
    cross_history_response_count: int,
    *,
    primary_weight: float = AVOIDANCE_PRIMARY_SEED_WEIGHT,
    cross_mode_source: str = "preference",
    rng: random.Random | None = None,
    job_units: Mapping[str, str] | None = None,
) -> tuple[dict[str, list[str]], dict[str, object]]:
    """이전 호출부를 위한 명시적 이중 시드 편성 래퍼."""
    return make_balanced_groups(
        jobs,
        primary_stats,
        primary_history_response_count,
        rng=rng,
        cross_stats=cross_stats,
        cross_history_response_count=cross_history_response_count,
        cross_source_mode=cross_mode_source,
        job_units=job_units,
        primary_weight=primary_weight,
    )
