"""Strict-schema tests for the Claude judge reply.

Run: .venv/bin/python -m pytest test_analyzer.py -q
pytest is a LOCAL dev dependency only — deliberately not in requirements.txt,
because GitHub Actions runs the agent, not the tests.
"""
import pytest

import analyzer

VALID = {"BBB", "CCC"}
LINE = "BBB $10 — up\nRisks: x\nVerdict: y\nInvalid below: $9.10"


def wrap(picks_json):
    return '{"picks": [' + picks_json + "]}"


def good_reply():
    return wrap('{"ticker": "BBB", "line": ' + repr(LINE).replace("'", '"') + "}")


# ---------- what a well-formed reply must still do ----------

def test_good_reply_parses():
    picks = analyzer.parse_picks(good_reply(), VALID)
    assert [p["ticker"] for p in picks] == ["BBB"]


def test_explicit_empty_picks_is_a_legitimate_rejection():
    """Valid JSON saying "nothing qualifies" is NOT an error."""
    assert analyzer.parse_picks('{"picks": []}', VALID) == []


def test_prose_and_code_fences_around_valid_json_still_ok():
    text = "Here are my picks:\n```json\n" + good_reply() + "\n```"
    assert len(analyzer.parse_picks(text, VALID)) == 1


def test_unclosed_brackets_are_repaired():
    text = good_reply()[:-2]  # drop the closing "]}"
    assert len(analyzer.parse_picks(text, VALID)) == 1


# ---------- what must now be REJECTED LOUDLY instead of silently ----------

@pytest.mark.parametrize("text, why", [
    ("None of these candidates are actionable today.", "prose only, no JSON"),
    ('{"verdict": "no"}', "missing picks key"),
    ('{"picks": 5}', "picks is not a list"),
    ('{"picks": [{"ticker": "ZZZ", "line": "x\\nInvalid below: $1"}]}', "hallucinated ticker"),
    ('{"picks": [{"ticker": "BBB"}]}', "missing line"),
    ('{"picks": [{"ticker": "BBB", "line": 5}]}', "line is not a string"),
    ('{"picks": [{"ticker": "BBB", "line": "BBB $10 — up"}]}', "no invalidation level"),
    ('{"picks": ["BBB"]}', "pick is not an object"),
    ('{"picks": [{"ticker": "BBB", "line": "BBB $10 — up' , "died mid-sentence"),
])
def test_malformed_replies_raise(text, why):
    with pytest.raises(analyzer.JudgeFormatError):
        analyzer.parse_picks(text, VALID)


def test_over_length_line_raises():
    long_line = "BBB $10 — " + "x" * 500 + "\nInvalid below: $9.10"
    text = '{"picks": [{"ticker": "BBB", "line": %s}]}' % repr(long_line).replace("'", '"')
    with pytest.raises(analyzer.JudgeFormatError):
        analyzer.parse_picks(text, VALID)


def test_duplicate_tickers_raise():
    p = '{"ticker": "BBB", "line": %s}' % repr(LINE).replace("'", '"')
    with pytest.raises(analyzer.JudgeFormatError):
        analyzer.parse_picks(wrap(p + "," + p), VALID)


def test_unknown_keys_raise():
    p = '{"ticker": "BBB", "confidence": 0.9, "line": %s}' % repr(LINE).replace("'", '"')
    with pytest.raises(analyzer.JudgeFormatError):
        analyzer.parse_picks(wrap(p), VALID)


def test_error_message_names_the_problem():
    with pytest.raises(analyzer.JudgeFormatError) as e:
        analyzer.parse_picks('{"picks": [{"ticker": "ZZZ", "line": "x\\nInvalid below: $1"}]}',
                             VALID)
    assert "ZZZ" in str(e.value)


# ---------- one bounded retry, then fail loudly ----------

class FakeBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class FakeResp:
    stop_reason = "end_turn"

    def __init__(self, text):
        self.content = [FakeBlock(text)]


class FakeClient:
    """Returns the queued replies in order and records the calls it received."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        return FakeResp(self.replies.pop(0))


CANDS = [{"ticker": "BBB"}, {"ticker": "CCC"}]


def test_judge_retries_once_after_a_malformed_reply():
    c = FakeClient(["I don't think any of these work.", good_reply()])
    picks = analyzer.judge(CANDS, client=c)
    assert [p["ticker"] for p in picks] == ["BBB"]
    assert len(c.calls) == 2
    # the retry must tell the model what was wrong, not just ask again
    assert len(c.calls[1]["messages"]) > len(c.calls[0]["messages"])


def test_judge_gives_up_after_two_bad_replies():
    c = FakeClient(["nope", "still nope"])
    with pytest.raises(analyzer.JudgeFormatError):
        analyzer.judge(CANDS, client=c)
    assert len(c.calls) == 2  # bounded: exactly one retry, no loop


def test_judge_does_not_retry_a_valid_empty_reply():
    c = FakeClient(['{"picks": []}'])
    assert analyzer.judge(CANDS, client=c) == []
    assert len(c.calls) == 1


def test_judge_records_the_raw_reply_and_stop_reason():
    c = FakeClient([good_reply()])
    analyzer.judge(CANDS, client=c)
    assert analyzer.LAST_STOP_REASON == "end_turn"
    assert "BBB" in analyzer.LAST_REPLY
