"""Tests of Thermal Wellbeing: learning what feels right."""

from custom_components.thermgenie.feel import FeelLearner, Moment, tendency

DAY = 86400.0


def moment(day=0, hour=8.0, outdoor=0.0, preset="heat_comfort", base=21.0, weekend=False):
    return Moment(day * DAY + hour * 3600, hour, weekend, outdoor, preset, base)


def test_without_answers_the_preset_counts():
    assert FeelLearner().target(moment()) == 21.0


def test_cold_mornings_learn_a_warmer_morning_but_leave_the_evening():
    feel = FeelLearner()
    for day in range(10):
        m = moment(day, 7.5)
        feel.feel("cool", 21.0, 21.0, m)
    morning = feel.target(moment(10, 7.5))
    evening = feel.target(moment(10, 20.0))
    assert morning >= 21.5
    assert evening == 21.0


def test_the_form_of_the_day_counts_at_once_and_fades():
    feel = FeelLearner()
    now = moment(0, 14.0)
    assert feel.feel("cold", 21.0, 21.0, now) == 22.0
    later = moment(0, 22.0)
    assert feel.target(later) < 22.0


def test_old_answers_fade_back_to_the_preset():
    feel = FeelLearner()
    for day in range(5):
        feel.feel("warm", 21.0, 21.0, moment(day, 18.0))
    assert feel.target(moment(5, 18.0)) <= 20.5
    assert feel.target(moment(400, 18.0)) == 21.0


def test_presets_learn_on_their_own():
    feel = FeelLearner()
    for day in range(10):
        feel.feel("cool", 18.0, 18.0, moment(day, 23.0, preset="heat_sleep", base=18.0))
    assert feel.target(moment(10, 23.0, preset="heat_sleep", base=18.0)) >= 18.5
    # The comfort preset hears only a little of it
    assert feel.target(moment(10, 23.0)) <= 21.5


def test_asks_once_the_room_got_there_and_stops_when_settled():
    feel = FeelLearner()
    m = moment(0, 8.0)
    feel.feel("cool", 21.0, 21.0, m)
    assert not feel.due(m.now + 1800, None)
    assert not feel.due(m.now + 3600, m.now + 3000)
    assert feel.due(m.now + 7200, m.now + 3000)
    feel.asked()
    for day in range(1, 4):
        feel.feel("good", 21.5, 21.5, moment(day, 8.0))
    assert feel.ask_at is None


def test_a_hand_set_point_counts_less_than_a_feeling():
    soft, real = FeelLearner(), FeelLearner()
    soft.hand_set(23.0, moment(0, 9.0))
    real.feel("cold", 22.0, 22.0, moment(0, 9.0))
    real.day_form = 0.0
    assert soft.learned_diff(moment(1, 9.0)) < real.learned_diff(moment(1, 9.0))


def test_it_survives_a_restart():
    feel = FeelLearner()
    feel.feel("cool", 21.0, 21.0, moment(0, 8.0))
    again = FeelLearner(feel.as_dict())
    assert again.target(moment(0, 9.0)) == feel.target(moment(0, 9.0))
    assert again.last_feeling == "cool"


def test_tendency():
    assert tendency(20.0, 21.0, True) == "warming"
    assert tendency(21.9, 21.0, True) == "cooling"
    assert tendency(21.1, 21.0, True) == "holding"
    assert tendency(18.0, 21.0, False) == "holding"
    # A sensor flickering by 0.1 K around a small gap does not flip it
    assert tendency(21.3, 21.0, True) == "holding"
    assert tendency(21.5, 21.0, True) == "cooling"
    assert tendency(21.2, 21.0, True, "cooling") == "cooling"
    assert tendency(21.1, 21.0, True, "cooling") == "holding"


def test_second_tap_corrects_the_first():
    learner = FeelLearner()
    m = Moment(now=1000.0, hour=18.0, weekend=False, outdoor=8.0, preset="heat_comfort", base=22.0)
    learner.feel("warm", 22.0, 22.0, m)
    m2 = Moment(now=1003.0, hour=18.0, weekend=False, outdoor=8.0, preset="heat_comfort", base=22.0)
    target = learner.feel("cool", 22.0, 22.0, m2)
    assert len(learner.answers) == 1
    assert learner.answers[0].diff == 0.5
    assert target == 22.5
    m3 = Moment(now=1003.0 + 600, hour=18.2, weekend=False, outdoor=8.0, preset="heat_comfort", base=22.0)
    learner.feel("good", 22.5, 22.5, m3)
    assert len(learner.answers) == 2


def test_face_goes_back_to_neutral_once_the_room_got_there():
    learner = FeelLearner()
    m = Moment(now=1000.0, hour=18.0, weekend=False, outdoor=8.0, preset="heat_comfort", base=22.0)
    learner.feel("cool", 22.0, 22.0, m)
    assert learner.status(m)["showing"] == "cool"
    assert not learner.arrived(1000.0 + 60)  # too soon, the face stays
    assert learner.arrived(1000.0 + 20 * 60)
    assert learner.status(m)["showing"] is None
    assert learner.last_feeling == "cool"
    restored = FeelLearner(learner.as_dict())
    assert restored.showing() is None


def test_the_outlook_tells_the_times_of_the_day_in_words():
    learner = FeelLearner()
    # Evenings it was wanted warmer, three times
    for day in range(3):
        m = Moment(1_800_000_000 + day * 86400, 19.0, False, 5.0, "heat_comfort", 21.0)
        learner.feel("cold", 21.0, 21.0, m)
    now = Moment(1_800_000_000 + 3 * 86400 + 3600, 19.2, False, 5.0, "heat_comfort", 21.0)
    outlook = learner.outlook(now)
    slots = {s["slot"]: s for s in outlook["slots"]}
    assert slots["evening"]["lean"].startswith("warmer")
    assert slots["evening"]["confidence"] in ("medium", "high")
    assert slots["evening"]["now"] is True
    assert slots["morning"]["lean"] == "open"  # nothing said about the morning
    assert all(isinstance(v, (str, bool)) for s in outlook["slots"] for v in s.values())  # words, never temperatures


def _settled_evening(learner):
    for day in range(4):
        learner.feel("good", 21.0, 21.0, Moment(1_800_000_000 + day * 86400, 19.0, False, 5.0, "heat_comfort", 21.0))


def test_an_unusual_answer_asks_for_a_reason_and_sport_does_not_count():
    learner = FeelLearner()
    _settled_evening(learner)
    m = Moment(1_800_000_000 + 4 * 86400, 19.0, False, 5.0, "heat_comfort", 21.0)
    before = learner.learned_diff(m)
    learner.feel("hot", 21.0, 21.0, m)  # far too warm where it usually fits: sport
    assert learner.status(m)["checking"] is True
    assert learner.explain("sport", Moment(m.now + 60, 19.0, False, 5.0, "heat_comfort", 21.0))
    assert learner.learned_diff(m) == before
    assert learner.form(m.now) == 0.0
    assert learner.exceptions()[0]["reason"] == "sport"
    assert learner.status(m)["checking"] is False


def test_a_usual_answer_and_normal_keep_learning():
    learner = FeelLearner()
    _settled_evening(learner)
    m = Moment(1_800_000_000 + 4 * 86400, 19.0, False, 5.0, "heat_comfort", 21.0)
    learner.feel("good", 21.0, 21.0, m)
    assert learner.checking is None
    learner.feel("cold", 21.0, 21.0, Moment(m.now + 600, 19.2, False, 5.0, "heat_comfort", 21.0))
    assert learner.checking is not None
    assert learner.explain("normal", Moment(m.now + 700, 19.2, False, 5.0, "heat_comfort", 21.0))
    assert learner.answers[-1].weight == 1.0


def test_an_answer_with_the_window_open_is_kept_but_not_learned():
    learner = FeelLearner()
    m = Moment(1_800_000_000, 19.0, False, 5.0, "heat_comfort", 21.0)
    learner.feel("good", 17.0, 21.0, m, special="window")
    assert learner.learned_diff(m) == 0.0
    assert learner.exceptions()[0]["reason"] == "window"
    assert learner.status(m)["answers"] == 0


def test_no_further_word_means_it_fits_the_face_goes_neutral_after_two_hours():
    learner = FeelLearner()
    m = Moment(now=1000.0, hour=12.0, weekend=False, outdoor=8.0, preset="heat_comfort", base=21.0)
    learner.feel("warm", 22.4, 21.0, m)  # a heating-only room that cannot get cooler on its own
    assert not learner.arrived(1000.0 + 3600, done=False)
    assert learner.status(m)["showing"] == "warm"
    assert learner.arrived(1000.0 + 2 * 3600 + 60, done=False)
    assert learner.status(m)["showing"] is None


def test_the_face_goes_neutral_once_the_devices_do_all_they_can():
    learner = FeelLearner()
    m = Moment(now=1000.0, hour=12.0, weekend=False, outdoor=8.0, preset="heat_comfort", base=21.0)
    learner.feel("warm", 22.4, 21.0, m)
    assert learner.arrived(1000.0 + 20 * 60, done=True)


def test_guests_count_for_today_but_not_for_later():
    learner = FeelLearner()
    _settled_evening(learner)
    m = Moment(1_800_000_000 + 4 * 86400, 19.0, False, 5.0, "heat_comfort", 21.0)
    before = learner.learned_diff(m)
    learner.feel("cold", 21.0, 21.0, m)
    assert learner.explain("guests", Moment(m.now + 60, 19.0, False, 5.0, "heat_comfort", 21.0))
    assert learner.learned_diff(m) == before
    assert learner.form(m.now + 60) > 0  # warmer for the rest of the visit
