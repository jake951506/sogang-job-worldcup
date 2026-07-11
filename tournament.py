from __future__ import annotations

import itertools
import random
import secrets
from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any, Literal

from constants import GROUP_NAMES, MODE_CONFIG, ROUND_ORDER, TOTAL_SELECTIONS


@dataclass(frozen=True)
class Participant:
    job: str
    seed: str = ""


@dataclass(frozen=True)
class Match:
    left: Participant
    right: Participant
    stage: str
    group_or_round: str
    match_no: int


Phase = Literal[
    "group_match",
    "group_summary",
    "knockout_match",
    "round_summary",
    "finished",
]


class TournamentSession:
    """Streamlit 세션에 보관되는 20강 조별리그 + 순위결정 토너먼트 상태."""

    def __init__(
        self,
        mode: str,
        groups: dict[str, list[str]],
        seeding_metadata: dict[str, object],
        *,
        random_seed: int | None = None,
    ) -> None:
        if mode not in MODE_CONFIG:
            raise ValueError(f"지원하지 않는 조사 유형입니다: {mode}")
        if set(groups) != set(GROUP_NAMES):
            raise ValueError("A, B, C, D 네 개 조가 모두 필요합니다.")
        if any(len(groups[name]) != 5 for name in GROUP_NAMES):
            raise ValueError("각 조에는 정확히 5개 직무가 있어야 합니다.")
        flattened = [job for name in GROUP_NAMES for job in groups[name]]
        if len(flattened) != 20 or len(set(flattened)) != 20:
            raise ValueError("20개 직무는 중복 없이 한 번씩만 배정되어야 합니다.")

        self.mode = mode
        self.groups = deepcopy(groups)
        self.seeding_metadata = deepcopy(seeding_metadata)
        self.random_seed = random_seed if random_seed is not None else secrets.randbits(63)
        self.rng = random.Random(self.random_seed)

        self.phase: Phase = "group_match"
        self.group_index = 0
        self.group_matches: list[Match] = []
        self.group_match_index = 0
        self.last_completed_group: str | None = None

        self.group_wins: dict[str, dict[str, int]] = {
            group_name: {job: 0 for job in jobs}
            for group_name, jobs in self.groups.items()
        }
        self.head_to_head: dict[str, dict[frozenset[str], str]] = {
            group_name: {} for group_name in GROUP_NAMES
        }
        self.group_rankings: dict[str, list[str]] = {}

        self.current_round = ""
        self.knockout_matches: list[Match] = []
        self.knockout_match_index = 0
        self.round_winners: list[Participant] = []
        self.round_losers: list[Participant] = []
        self.last_completed_round: str | None = None
        self.finalists: list[Participant] = []
        self.semifinal_losers: list[Participant] = []

        self.champion: str | None = None
        self.runner_up: str | None = None
        self.third_place: str | None = None
        self.fourth_place: str | None = None
        self.match_history: list[dict[str, Any]] = []

        self._prepare_group(self.current_group)

    @property
    def current_group(self) -> str:
        return GROUP_NAMES[self.group_index]

    @property
    def selection_count(self) -> int:
        return len(self.match_history)

    @property
    def progress_fraction(self) -> float:
        return min(self.selection_count / TOTAL_SELECTIONS, 1.0)

    @property
    def current_match(self) -> Match:
        if self.phase == "group_match":
            return self.group_matches[self.group_match_index]
        if self.phase == "knockout_match":
            return self.knockout_matches[self.knockout_match_index]
        raise RuntimeError("현재는 선택 경기를 진행하는 단계가 아닙니다.")

    @property
    def top_four(self) -> list[str]:
        values = [
            self.champion,
            self.runner_up,
            self.third_place,
            self.fourth_place,
        ]
        return [value for value in values if value is not None]

    @property
    def final_top4(self) -> list[str]:
        """저장·분석 코드에서 쓰는 최종 1~4위 목록 별칭."""
        return self.top_four

    def _oriented_participants(
        self, first: Participant, second: Participant
    ) -> tuple[Participant, Participant]:
        if self.rng.random() < 0.5:
            return first, second
        return second, first

    def _prepare_group(self, group_name: str) -> None:
        raw_pairs = [
            (
                Participant(left, f"{group_name}조"),
                Participant(right, f"{group_name}조"),
            )
            for left, right in itertools.combinations(self.groups[group_name], 2)
        ]
        self.rng.shuffle(raw_pairs)
        self.group_matches = []
        for match_no, (first, second) in enumerate(raw_pairs, start=1):
            left, right = self._oriented_participants(first, second)
            self.group_matches.append(
                Match(
                    left=left,
                    right=right,
                    stage="20강 조별리그",
                    group_or_round=f"{group_name}조",
                    match_no=match_no,
                )
            )
        self.group_match_index = 0
        self.phase = "group_match"

    def record_choice(self, side: Literal[1, 2]) -> str:
        if side not in (1, 2):
            raise ValueError("선택은 1 또는 2여야 합니다.")
        match = self.current_match
        selected = match.left if side == 1 else match.right
        not_selected = match.right if side == 1 else match.left

        self.match_history.append(
            {
                "sequence_no": self.selection_count + 1,
                "stage": match.stage,
                "group_or_round": match.group_or_round,
                "match_no": match.match_no,
                "left_job": match.left.job,
                "right_job": match.right.job,
                "left_seed": match.left.seed,
                "right_seed": match.right.seed,
                "selected_side": side,
                "selected_job": selected.job,
                "not_selected_job": not_selected.job,
                "selected_seed": selected.seed,
                "not_selected_seed": not_selected.seed,
            }
        )

        if self.phase == "group_match":
            return self._record_group_choice(selected, not_selected)
        return self._record_knockout_choice(selected, not_selected)

    def _record_group_choice(
        self, selected: Participant, not_selected: Participant
    ) -> str:
        group_name = self.current_group
        self.group_wins[group_name][selected.job] += 1
        self.head_to_head[group_name][
            frozenset((selected.job, not_selected.job))
        ] = selected.job
        self.group_match_index += 1

        if self.group_match_index >= len(self.group_matches):
            self.group_rankings[group_name] = self.rank_group(group_name)
            self.last_completed_group = group_name
            self.phase = "group_summary"
            return "group_complete"
        return "next_match"

    def _record_knockout_choice(
        self, selected: Participant, not_selected: Participant
    ) -> str:
        self.round_winners.append(selected)
        self.round_losers.append(not_selected)
        self.knockout_match_index += 1

        if self.current_round == "결승":
            self.champion = selected.job
            self.runner_up = not_selected.job
            self.phase = "finished"
            return "finished"

        if self.current_round == "3·4위전":
            self.third_place = selected.job
            self.fourth_place = not_selected.job
            self.last_completed_round = self.current_round
            self.phase = "round_summary"
            return "round_complete"

        if self.knockout_match_index >= len(self.knockout_matches):
            if self.current_round == "4강":
                self.finalists = deepcopy(self.round_winners)
                self.semifinal_losers = deepcopy(self.round_losers)
            self.last_completed_round = self.current_round
            self.phase = "round_summary"
            return "round_complete"
        return "next_match"

    def rank_group(self, group_name: str) -> list[str]:
        """
        순위 규칙: 전체 승수 → 동률 직무 간 상대전적 → 이긴 상대 승수 합 → 추첨순.
        """
        members = self.groups[group_name]
        wins = self.group_wins[group_name]
        draw_order = {job: index for index, job in enumerate(members)}

        def mini_league_wins(job: str, tied: list[str]) -> int:
            score = 0
            for opponent in tied:
                if opponent == job:
                    continue
                if self.head_to_head[group_name].get(
                    frozenset((job, opponent))
                ) == job:
                    score += 1
            return score

        def strength_of_victory(job: str) -> int:
            score = 0
            for opponent in members:
                if opponent == job:
                    continue
                if self.head_to_head[group_name].get(
                    frozenset((job, opponent))
                ) == job:
                    score += wins[opponent]
            return score

        ranking: list[str] = []
        for win_count in sorted(set(wins.values()), reverse=True):
            tied = [job for job in members if wins[job] == win_count]
            tied.sort(
                key=lambda job: (
                    -mini_league_wins(job, tied),
                    -strength_of_victory(job),
                    draw_order[job],
                )
            )
            ranking.extend(tied)
        return ranking

    def continue_from_summary(self) -> None:
        if self.phase == "group_summary":
            if self.group_index < len(GROUP_NAMES) - 1:
                self.group_index += 1
                self._prepare_group(self.current_group)
            else:
                self._begin_knockout()
            return

        if self.phase == "round_summary":
            self._begin_next_knockout_round()
            return

        raise RuntimeError("계속 진행할 수 있는 요약 화면이 아닙니다.")

    def _seeded(self, group_name: str, rank: int) -> Participant:
        job = self.group_rankings[group_name][rank - 1]
        return Participant(job=job, seed=f"{group_name}조 {rank}위")

    def _begin_knockout(self) -> None:
        if set(self.group_rankings) != set(GROUP_NAMES):
            raise RuntimeError("모든 조의 순위가 확정되어야 16강을 시작할 수 있습니다.")

        # 인접한 두 경기가 하나의 8강 구역이다. 네 조 1위가 각기 다른
        # 8강 구역에 들어가므로 조 1위끼리는 4강 전에는 만날 수 없다.
        pairings = [
            (self._seeded("A", 1), self._seeded("B", 4)),
            (self._seeded("C", 2), self._seeded("D", 3)),
            (self._seeded("C", 1), self._seeded("D", 4)),
            (self._seeded("A", 2), self._seeded("B", 3)),
            (self._seeded("B", 1), self._seeded("A", 4)),
            (self._seeded("D", 2), self._seeded("C", 3)),
            (self._seeded("D", 1), self._seeded("C", 4)),
            (self._seeded("B", 2), self._seeded("A", 3)),
        ]
        self._start_knockout_round("16강", pairings)

    def _begin_next_knockout_round(self) -> None:
        completed_round = self.last_completed_round or self.current_round
        if completed_round not in ROUND_ORDER:
            raise RuntimeError("현재 결선 라운드 정보가 올바르지 않습니다.")

        if completed_round == "4강":
            if len(self.semifinal_losers) != 2:
                raise RuntimeError("3·4위전 진출 직무 정보가 올바르지 않습니다.")
            self._start_knockout_round(
                "3·4위전",
                [(self.semifinal_losers[0], self.semifinal_losers[1])],
            )
            return

        if completed_round == "3·4위전":
            if len(self.finalists) != 2:
                raise RuntimeError("결승 진출 직무 정보가 올바르지 않습니다.")
            self._start_knockout_round(
                "결승",
                [(self.finalists[0], self.finalists[1])],
            )
            return

        if completed_round in ("결승",):
            raise RuntimeError("결승 이후 라운드는 없습니다.")
        if len(self.round_winners) % 2 != 0:
            raise RuntimeError("다음 라운드 대진을 만들 수 없습니다.")

        current_index = ROUND_ORDER.index(completed_round)
        next_round = ROUND_ORDER[current_index + 1]
        pairings = [
            (self.round_winners[index], self.round_winners[index + 1])
            for index in range(0, len(self.round_winners), 2)
        ]
        self._start_knockout_round(next_round, pairings)

    def _start_knockout_round(
        self,
        round_name: str,
        pairings: list[tuple[Participant, Participant]],
    ) -> None:
        self.current_round = round_name
        self.knockout_matches = []
        for match_no, (first, second) in enumerate(pairings, start=1):
            left, right = self._oriented_participants(first, second)
            self.knockout_matches.append(
                Match(
                    left=left,
                    right=right,
                    stage=round_name,
                    group_or_round=round_name,
                    match_no=match_no,
                )
            )
        self.knockout_match_index = 0
        self.round_winners = []
        self.round_losers = []
        self.last_completed_round = None
        self.phase = "knockout_match"

    def completed_group_table(self, group_name: str) -> list[dict[str, Any]]:
        ranking = self.group_rankings[group_name]
        unit_map = self.seeding_metadata.get("job_units", {})
        if not isinstance(unit_map, dict):
            unit_map = {}
        return [
            {
                "순위": rank,
                "직무": job,
                "소속": unit_map.get(job, ""),
                "승": self.group_wins[group_name][job],
                "패": 4 - self.group_wins[group_name][job],
                "결과": "16강 진출" if rank <= 4 else "탈락",
            }
            for rank, job in enumerate(ranking, start=1)
        ]

    def to_serializable_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "random_seed": self.random_seed,
            "groups": deepcopy(self.groups),
            "seeding_metadata": deepcopy(self.seeding_metadata),
            "group_wins": deepcopy(self.group_wins),
            "group_rankings": deepcopy(self.group_rankings),
            "champion": self.champion,
            "runner_up": self.runner_up,
            "third_place": self.third_place,
            "fourth_place": self.fourth_place,
            "finalists": [asdict(participant) for participant in self.finalists],
            "semifinal_losers": [
                asdict(participant) for participant in self.semifinal_losers
            ],
            "match_history": deepcopy(self.match_history),
            "selection_count": self.selection_count,
            "phase": self.phase,
            "current_round": self.current_round,
            "knockout_matches": [asdict(match) for match in self.knockout_matches],
        }
