from __future__ import annotations

import random

import pytest

from constants import GROUP_NAMES, JOBS, TOTAL_SELECTIONS
from seeding import compute_historical_stats, make_balanced_groups
from tournament import TournamentSession


def new_session(mode: str = "preference") -> TournamentSession:
    stats, history_count = compute_historical_stats(JOBS, [])
    groups, metadata = make_balanced_groups(
        JOBS,
        stats,
        history_count,
        rng=random.Random(101),
    )
    return TournamentSession(
        mode=mode,
        groups=groups,
        seeding_metadata=metadata,
        random_seed=202,
    )


def finish_group_stage(session: TournamentSession) -> None:
    while session.phase in ("group_match", "group_summary"):
        if session.phase == "group_match":
            session.record_choice(1)
        else:
            session.continue_from_summary()


def finish_tournament(session: TournamentSession) -> None:
    while session.phase != "finished":
        if session.phase in ("group_match", "knockout_match"):
            session.record_choice(1)
        elif session.phase in ("group_summary", "round_summary"):
            session.continue_from_summary()
        else:  # pragma: no cover - future phase additions should fail loudly
            raise AssertionError(f"Unexpected phase: {session.phase}")


def test_group_stage_has_40_matches_and_complete_rankings() -> None:
    session = new_session()
    finish_group_stage(session)

    assert session.phase == "knockout_match"
    assert session.current_round == "16강"
    assert session.selection_count == 40
    assert set(session.group_rankings) == set(GROUP_NAMES)
    assert all(len(session.group_rankings[group]) == 5 for group in GROUP_NAMES)


def test_group_winners_are_in_four_different_quarterfinal_regions() -> None:
    session = new_session()
    finish_group_stage(session)

    matches = session.knockout_matches
    assert len(matches) == 8

    # 인접한 16강 두 경기가 하나의 8강 구역을 구성한다.
    for start in range(0, 8, 2):
        region = matches[start : start + 2]
        participants = [
            participant
            for match in region
            for participant in (match.left, match.right)
        ]
        first_seeds = [p for p in participants if p.seed.endswith("1위")]
        assert len(first_seeds) == 1

    unordered_pairings = {
        frozenset((match.left.seed, match.right.seed)) for match in matches
    }
    assert unordered_pairings == {
        frozenset(("A조 1위", "B조 4위")),
        frozenset(("C조 2위", "D조 3위")),
        frozenset(("C조 1위", "D조 4위")),
        frozenset(("A조 2위", "B조 3위")),
        frozenset(("B조 1위", "A조 4위")),
        frozenset(("D조 2위", "C조 3위")),
        frozenset(("D조 1위", "C조 4위")),
        frozenset(("B조 2위", "A조 3위")),
    }


@pytest.mark.parametrize("mode", ["preference", "avoidance"])
def test_full_tournament_finishes_after_56_choices(mode: str) -> None:
    session = new_session(mode)
    finish_tournament(session)

    assert session.phase == "finished"
    assert session.selection_count == TOTAL_SELECTIONS == 56
    assert session.champion in JOBS
    assert session.runner_up in JOBS
    assert session.champion != session.runner_up
    assert session.third_place in JOBS
    assert session.fourth_place in JOBS
    assert len({
        session.champion,
        session.runner_up,
        session.third_place,
        session.fourth_place,
    }) == 4
    assert len(session.match_history) == 56
    assert sum(row["stage"] == "20강 조별리그" for row in session.match_history) == 40
    assert sum(row["stage"] != "20강 조별리그" for row in session.match_history) == 16
    assert sum(row["stage"] == "3·4위전" for row in session.match_history) == 1
    assert sum(row["stage"] == "결승" for row in session.match_history) == 1


def test_invalid_choice_is_rejected() -> None:
    session = new_session()
    with pytest.raises(ValueError):
        session.record_choice(3)  # type: ignore[arg-type]


def test_third_place_match_precedes_final_and_sets_top_four() -> None:
    session = new_session()
    seen_rounds: list[str] = []

    while session.phase != "finished":
        if session.phase in ("group_match", "knockout_match"):
            if session.phase == "knockout_match" and (
                not seen_rounds or seen_rounds[-1] != session.current_round
            ):
                seen_rounds.append(session.current_round)
            session.record_choice(1)
        else:
            session.continue_from_summary()

    assert seen_rounds == ["16강", "8강", "4강", "3·4위전", "결승"]
    assert len(session.final_top4) == 4
    assert session.match_history[-2]["stage"] == "3·4위전"
    assert session.match_history[-1]["stage"] == "결승"
