from __future__ import annotations

from streamlit.testing.v1 import AppTest


def test_home_name_gate_credit_and_one_preference_choice() -> None:
    app = AppTest.from_file("streamlit_app.py", default_timeout=30).run()
    assert not app.exception
    assert any("20개 직무" in title.value for title in app.title)
    assert any("Developed by JK" in item.value for item in app.markdown)

    select_button = next(
        button for button in app.button if button.label == "선호조사 선택"
    )
    select_button.click().run()
    assert not app.exception
    assert app.session_state["page"] == "name_entry"
    assert any(input_box.label == "이름" for input_box in app.text_input)

    app.text_input[0].set_value(" 김재경 ")
    start_button = next(
        button for button in app.button if button.label == "선호조사 시작"
    )
    start_button.click().run()

    assert not app.exception
    assert app.session_state["participant_name"] == "김재경"
    assert app.session_state["tournament"].selection_count == 0
    assert app.session_state["tournament"].seeding_metadata[
        "unit_separation_complete"
    ] is True

    choice_button = next(
        button for button in app.button if button.label.startswith("①")
    )
    choice_button.click().run()
    assert not app.exception
    assert app.session_state["tournament"].selection_count == 1


def test_blank_name_does_not_start_survey() -> None:
    app = AppTest.from_file("streamlit_app.py", default_timeout=30).run()
    next(button for button in app.button if button.label == "기피조사 선택").click().run()
    next(button for button in app.button if button.label == "기피조사 시작").click().run()

    assert not app.exception
    assert app.session_state["page"] == "name_entry"
    assert app.session_state["tournament"] is None
    assert any("이름을 입력" in error.value for error in app.error)


def test_result_page_offers_other_survey_or_finish() -> None:
    import random
    from datetime import datetime, timezone

    from constants import JOBS
    from seeding import compute_historical_stats, make_balanced_groups
    from storage import build_submission_bundle
    from tournament import TournamentSession

    stats, count = compute_historical_stats(JOBS, [])
    groups, metadata = make_balanced_groups(
        JOBS, stats, count, rng=random.Random(11)
    )
    session = TournamentSession(
        "preference", groups, metadata, random_seed=12
    )
    while session.phase != "finished":
        if session.phase in ("group_match", "knockout_match"):
            session.record_choice(1)
        else:
            session.continue_from_summary()

    started_at = datetime.now(timezone.utc)
    bundle = build_submission_bundle(
        session,
        participant_session_id="participant-flow",
        participant_name="김재경",
        started_at=started_at,
    )

    app = AppTest.from_file("streamlit_app.py", default_timeout=30)
    app.session_state["page"] = "result"
    app.session_state["active_mode"] = "preference"
    app.session_state["pending_mode"] = None
    app.session_state["participant_name"] = "김재경"
    app.session_state["participant_session_id"] = "participant-flow"
    app.session_state["tournament"] = session
    app.session_state["tournament_started_at"] = started_at
    app.session_state["completed_results"] = {}
    app.session_state["submission_bundle"] = bundle
    app.session_state["save_state"] = "unconfigured"
    app.session_state["save_error"] = "test mode"
    app.session_state["save_receipt"] = None
    app.session_state["history_warning"] = ""
    app.session_state["access_granted"] = False
    app.session_state["participation_finished"] = False
    app.run()

    assert not app.exception
    assert any(button.label == "기피조사도 계속하기" for button in app.button)
    finish_button = next(
        button for button in app.button if button.label == "여기서 참여 마치기"
    )
    finish_button.click().run()
    assert not app.exception
    assert app.session_state["page"] == "complete"
    assert app.session_state["participation_finished"] is True
