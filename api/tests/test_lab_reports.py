"""Lab reports: read, explained in plain words, kept to read again.

What matters most here is what the feature refuses to do. It explains a
result against the range the report prints and never says what the result
means for the patient; it never tells a family a value is within range when
the printed numbers say otherwise; and it reads nothing before the person
has agreed to it, because the consent given at sign-up covers bills.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from lab_analysis import LabAnalysis, LabTest, checked_status, recheck
from lab_prompt import PROMPT
from tables import User
from tests.conftest import FakeSms, sign_up
from tests.test_cases_and_bills import page


def agree(client: TestClient, headers: dict) -> None:
    assert client.post("/lab-reports/consent", json={"consent": True}, headers=headers).status_code == 204


def upload(client: TestClient, headers: dict) -> dict:
    response = client.post("/lab-reports", files=[page()], headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


# --- consent first ------------------------------------------------------------


def test_nothing_is_read_before_the_person_agrees(client: TestClient, auth_headers: dict):
    """Sign-up consent covers "the bills I add", used "only to check my bills".
    A lab report is neither, so it is not read on the strength of it."""
    response = client.post("/lab-reports", files=[page()], headers=auth_headers)

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "lab_consent_required"
    assert client.get("/lab-reports", headers=auth_headers).json() == []


def test_agreeing_is_recorded_and_the_app_can_see_it(client: TestClient, auth_headers: dict):
    assert client.get("/auth/me", headers=auth_headers).json()["lab_consent"] is False

    agree(client, auth_headers)

    assert client.get("/auth/me", headers=auth_headers).json()["lab_consent"] is True


def test_agreeing_twice_keeps_the_first_date(client: TestClient, auth_headers: dict, db: Session):
    agree(client, auth_headers)
    first = db.scalars(select(User)).one().lab_consented_at
    assert first is not None

    agree(client, auth_headers)
    db.expire_all()
    assert db.scalars(select(User)).one().lab_consented_at == first


def test_only_true_is_consent(client: TestClient, auth_headers: dict):
    assert (
        client.post("/lab-reports/consent", json={"consent": False}, headers=auth_headers).status_code == 422
    )
    assert client.get("/auth/me", headers=auth_headers).json()["lab_consent"] is False


# --- reading and keeping it ---------------------------------------------------


def test_a_report_is_explained_in_both_languages(client: TestClient, auth_headers: dict):
    agree(client, auth_headers)
    report = upload(client, auth_headers)

    assert report["lab_name"] == "Sample Diagnostics"
    assert report["report_date"] == "06/05/2025", "as printed, never parsed"
    first = report["tests"][0]
    assert first["name"] == "Haemoglobin"
    assert first["value"] == "9.8" and first["unit"] == "g/dL"
    assert first["range"] == "12.0 - 15.0", "the range the report printed, verbatim"
    assert first["status"] == "low"
    assert "oxygen" in first["explanation_en"]
    assert "ऑक्सीजन" in first["explanation_hi"]
    assert report["summary_en"] and report["summary_hi"]
    assert len(report["questions_en"]) == len(report["questions_hi"]) == 2
    assert report["urgent"] is False


def test_it_can_be_opened_again(client: TestClient, auth_headers: dict):
    agree(client, auth_headers)
    report = upload(client, auth_headers)

    again = client.get(f"/lab-reports/{report['id']}", headers=auth_headers)
    assert again.status_code == 200
    assert again.json() == report


def test_the_list_says_how_many_results_are_outside_their_range(client: TestClient, auth_headers: dict):
    agree(client, auth_headers)
    report = upload(client, auth_headers)

    (row,) = client.get("/lab-reports", headers=auth_headers).json()
    assert row["id"] == report["id"]
    assert row["test_count"] == 4
    assert row["outside_range"] == 2, "low and high; in range and no range don't count"


def test_someone_else_s_report_does_not_exist(client: TestClient, auth_headers: dict, sms: FakeSms):
    """Not found rather than forbidden: an id must not say whether a stranger
    has had blood taken."""
    agree(client, auth_headers)
    report = upload(client, auth_headers)
    other = {"Authorization": f"Bearer {sign_up(client, sms, phone='+919812345678', name='Anita')['token']}"}

    response = client.get(f"/lab-reports/{report['id']}", headers=other)
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "lab_report_not_found"
    assert client.delete(f"/lab-reports/{report['id']}", headers=other).status_code == 404
    assert client.get("/lab-reports", headers=other).json() == []


def test_a_report_can_be_deleted_for_good(client: TestClient, auth_headers: dict):
    agree(client, auth_headers)
    report = upload(client, auth_headers)

    assert client.delete(f"/lab-reports/{report['id']}", headers=auth_headers).status_code == 204
    assert client.get(f"/lab-reports/{report['id']}", headers=auth_headers).status_code == 404
    assert client.get("/lab-reports", headers=auth_headers).json() == []


def test_an_unreadable_report_leaves_nothing_behind(
    client: TestClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
):
    import ocr

    def refuse(self, pages):
        raise ocr.OcrError("This is not a laboratory report.")

    monkeypatch.setattr(ocr.StubOcr, "read_lab_report", refuse)
    agree(client, auth_headers)

    response = client.post("/lab-reports", files=[page()], headers=auth_headers)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "unreadable_lab_report"
    assert client.get("/lab-reports", headers=auth_headers).json() == []


def test_it_shares_the_daily_allowance_with_bills(
    client: TestClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
):
    """Both are a paid read, so one allowance covers both."""
    from settings import get_settings

    monkeypatch.setenv("BILL_UPLOADS_PER_DAY", "1")
    get_settings.cache_clear()
    try:
        agree(client, auth_headers)
        assert client.post("/bills", files=[page()], headers=auth_headers).status_code == 201
        response = client.post("/lab-reports", files=[page()], headers=auth_headers)
    finally:
        get_settings.cache_clear()

    assert response.status_code == 429


# --- the one claim that is checked --------------------------------------------


def result(value: str, range_: str, status: str = "in_range") -> LabTest:
    return LabTest(name="Test", value=value, range=range_, status=status)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("value", "printed", "expected"),
    [
        ("9.8", "12.0 - 15.0", "low"),
        ("16", "12.0 - 15.0", "high"),
        ("12.0", "12.0 - 15.0", "in_range"),
        ("15", "12-15", "in_range"),
        ("13,400", "4000 - 11000", "high"),
        ("13", "12 to 15", "in_range"),
        ("13", "12.0 – 15.0", "in_range"),
        ("240", "< 200", "high"),
        ("180", "Up to 200", "in_range"),
        ("35", "> 40", "low"),
        ("45", "≥ 40", "in_range"),
    ],
)
def test_where_both_are_numbers_the_arithmetic_decides(value: str, printed: str, expected: str):
    """The reader says "in_range" on every one of these. Where the printed
    numbers disagree, a family is shown what the numbers say."""
    assert checked_status(result(value, printed, "in_range")) == expected


@pytest.mark.parametrize(
    ("value", "printed", "said"),
    [
        ("Negative", "Negative", "in_range"),
        ("<0.5", "0 - 1", "in_range"),
        ("1+", "Nil", "high"),
        ("9.8", "Varies with age; see note", "low"),
    ],
)
def test_where_either_is_not_a_number_the_reader_s_reading_stands(value: str, printed: str, said: str):
    assert checked_status(result(value, printed, said)) == said


def test_a_result_with_no_printed_range_has_no_status():
    """The reader is forbidden from supplying a range of its own. A "low" with
    nothing printed beside it is one it supplied anyway."""
    assert checked_status(result("9.8", "", "low")) == "no_range"
    assert checked_status(result("9.8", "   ", "in_range")) == "no_range"


def test_a_corrected_status_keeps_the_reader_s_own_beside_it():
    """A record of the reader getting it wrong, for judging it later."""
    analysis = LabAnalysis(tests=[result("16", "12.0 - 15.0", "in_range"), result("13", "12.0 - 15.0")])

    corrected, agreed = recheck(analysis)
    assert corrected["status"] == "high"
    assert corrected["reader_status"] == "in_range"
    assert agreed["status"] == "in_range"
    assert "reader_status" not in agreed


def test_the_wrong_answer_is_not_shown_to_the_family(
    client: TestClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
):
    import ocr

    plain = ocr.StubOcr.read_lab_report

    def wrong(self, pages):
        analysis = plain(self, pages)
        analysis.tests[0] = analysis.tests[0].model_copy(update={"status": "in_range"})
        return analysis

    monkeypatch.setattr(ocr.StubOcr, "read_lab_report", wrong)
    agree(client, auth_headers)
    report = upload(client, auth_headers)

    assert report["tests"][0]["status"] == "low", "9.8 against 12.0 - 15.0"
    assert "reader_status" not in report["tests"][0]


# --- the reader's answer --------------------------------------------------------


def test_an_unrecognised_status_claims_nothing():
    assert LabTest(name="X", status="borderline").status == "no_range"  # type: ignore[arg-type]


def test_a_report_with_no_results_is_not_an_explanation():
    import json

    from ocr import OcrError, _parse_lab

    with pytest.raises(OcrError, match="No test results"):
        _parse_lab(json.dumps({"tests": []}))


def test_a_document_that_is_not_a_lab_report_says_so():
    import json

    from ocr import OcrError, _parse_lab

    with pytest.raises(OcrError, match="not a laboratory report"):
        _parse_lab(json.dumps({"error": "This is not a laboratory report."}))


# --- the rules the reader is given ----------------------------------------------


@pytest.mark.parametrize(
    "rule",
    [
        "NEVER invent a value, a unit or a reference range",
        "NEVER say or suggest the patient has, may have, or is at risk of any",
        "NEVER suggest starting, stopping or changing any medicine",
        "is a question for the doctor, not a\n   verdict",
        'Do not set\n   "urgent" on your own judgement',
        "explanation_en",
        "explanation_hi",
    ],
)
def test_the_prompt_keeps_the_rules_that_make_this_safe(rule: str):
    """These are the design, not the wording. An edit that drops one should
    fail here and be a decision, not an accident."""
    assert rule in PROMPT
