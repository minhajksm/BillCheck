"""Reading the reader's answer, now that nothing makes it well-formed.

No schema is sent with the request: PHASE 4 of the prompt states the shape and
asks for "a single JSON object and nothing else", and this is the half that
checks it got one. So these tests are the ways an answer can be wrong, and
what each one costs a family.

The rule throughout: an answer that can't be trusted reaches nobody. A bill
read badly is worse than a bill not read, because a family takes it to a
counter and asks the wrong question.
"""

import json

import pytest

from analysis import BillAnalysis
from ocr import ClaudeOcr, OcrError, _json_object, _parse

GOOD = {
    "bill": {
        "hospital": "City Care Hospital",
        "bill_no": "IP/2026/4417",
        "bill_date": "2026-10-11",
        "admission_date": "2026-10-09",
        "discharge_date": "",
        "stay_days": 3,
        "room_category": "Twin sharing",
        "total": 6500.0,
        "pages_processed": 1,
        "extraction_confidence": 0.92,
    },
    "lines": [
        {
            "line_id": "L1",
            "page": 1,
            "section": "Room",
            "description_verbatim": "Room rent, twin sharing",
            "item_name_plain": "Room rent, twin sharing",
            "category": "room_and_nursing",
            "attributes": {},
            "quantity": 1.0,
            "unit": "day",
            "rate": 6500.0,
            "amount": 6500.0,
            "date": "11 Oct",
            "mrp_printed": None,
            "confidence": 0.95,
            "ambiguous": False,
            "ambiguity_reason": "",
        }
    ],
    "findings": [
        {
            "finding_id": "f1",
            "rule": "A. quantity x rate != amount",
            "severity": "high",
            "line_ids": ["L1"],
            "evidence_quoted": "1 x 6,500 = 6,500",
            "statement": "The line adds up.",
            "confirmation_required": "Nothing.",
        }
    ],
    "requires_reference_price": [],
    "structural": {
        "consumable_share_pct": 0.0,
        "unitemised_share_pct": 0.0,
        "unreadable_line_count": 0,
    },
    "needs_human_review": False,
    "review_reasons": [],
}


def answer(**changes) -> str:
    """The sample answer, as the reader would send it, with `changes` applied."""
    return json.dumps({**GOOD, **changes})


# --- the shape PHASE 4 asks for ---------------------------------------------


def test_reads_the_shape_the_prompt_asks_for():
    analysis = _parse(answer())

    assert analysis.bill.hospital == "City Care Hospital"
    assert [line.line_id for line in analysis.lines] == ["L1"]
    assert analysis.findings[0].severity == "high"
    assert analysis.structural.unreadable_line_count == 0


def test_the_model_carries_exactly_the_prompt_s_fields():
    """Not one field more: the JSON the reader is asked for and the JSON this
    parses have to be the same document, or the prompt stops being the spec."""
    assert list(BillAnalysis.model_fields) == [
        "bill",
        "lines",
        "findings",
        "requires_reference_price",
        "structural",
        "needs_human_review",
        "review_reasons",
    ]


def test_attributes_take_whatever_the_bill_printed():
    """PHASE 2 names eight attributes; a bill prints the ones it prints. The
    field is an open map, so a gauge arrives as a gauge."""
    lines = [{**GOOD["lines"][0], "attributes": {"gauge": "18G", "volume": "500ml"}}]
    analysis = _parse(answer(lines=lines))
    assert analysis.lines[0].attributes == {"gauge": "18G", "volume": "500ml"}


# --- an answer that arrives wrapped ----------------------------------------


def test_reads_an_answer_in_a_code_fence():
    """The commonest wrapping, and the reason this isn't a bare json.loads."""
    assert _parse(f"```json\n{answer()}\n```").bill.bill_no == "IP/2026/4417"


def test_reads_an_answer_with_a_sentence_either_side():
    wrapped = f"Here is the analysis of the bill.\n\n{answer()}\n\nLet me know if you need more."
    assert _parse(wrapped).bill.bill_no == "IP/2026/4417"


def test_finds_the_object_past_a_brace_in_the_prose():
    assert _parse(f"The bill uses {{braces}} in a description.\n{answer()}").lines[0].line_id == "L1"


def test_keeps_braces_inside_the_transcription():
    """A bill's own text is quoted verbatim, brackets and all, so the scan has
    to know a brace in a string from a brace in the structure."""
    lines = [{**GOOD["lines"][0], "description_verbatim": 'Inj. {Meropenem} "1g" }'}]
    analysis = _parse(answer(lines=lines))
    assert analysis.lines[0].description_verbatim == 'Inj. {Meropenem} "1g" }'


def test_an_escaped_quote_does_not_end_the_string():
    lines = [{**GOOD["lines"][0], "ambiguity_reason": 'reads \\"SET IV\\" and nothing more'}]
    assert _parse(answer(lines=lines)).lines[0].ambiguity_reason.startswith("reads")


# --- an answer that cannot be used -----------------------------------------


def test_refuses_an_answer_that_is_not_json():
    with pytest.raises(OcrError, match="no JSON object"):
        _parse("I could not read this bill, sorry.")


def test_refuses_an_answer_cut_off_mid_object():
    with pytest.raises(OcrError, match="stops in the middle"):
        _parse(answer()[:200])


def test_refuses_an_answer_missing_a_field_phase_4_asks_for():
    without = {key: value for key, value in GOOD.items() if key != "structural"}
    with pytest.raises(OcrError, match="doesn't match PHASE 4"):
        _parse(json.dumps(without))


def test_refuses_a_line_missing_a_field_phase_4_asks_for():
    lines = [{key: value for key, value in GOOD["lines"][0].items() if key != "amount"}]
    with pytest.raises(OcrError, match="doesn't match PHASE 4"):
        _parse(answer(lines=lines))


def test_refuses_the_prompt_s_own_error_shape():
    """PHASE 4's last instruction: not a hospital bill, or too degraded."""
    with pytest.raises(OcrError, match="not a hospital bill"):
        _parse(json.dumps({"error": "This is not a hospital bill.", "needs_human_review": True}))


def test_refuses_a_bill_with_no_lines_on_it():
    """Nothing to show a family, whatever else came back."""
    with pytest.raises(OcrError, match="No itemized lines"):
        _parse(answer(lines=[], findings=[]))


def test_a_bill_with_no_lines_says_why_where_the_reader_said():
    with pytest.raises(OcrError, match="page 2 is a blur"):
        _parse(answer(lines=[], findings=[], needs_human_review=True, review_reasons=["page 2 is a blur"]))


def test_refuses_a_read_the_reader_itself_had_no_confidence_in():
    """Human review asked for, nothing found, and the reader's own confidence
    in the transcription under half. Not a report to show as if it were
    clean."""
    with pytest.raises(OcrError, match="could not make out the amounts"):
        _parse(
            answer(
                bill={**GOOD["bill"], "extraction_confidence": 0.2},
                findings=[],
                needs_human_review=True,
                review_reasons=["could not make out the amounts"],
            )
        )


def test_keeps_a_read_the_reader_wants_looked_at_but_did_read():
    """`needs_human_review` on its own is for whoever runs this, not a reason
    to withhold a bill that was read."""
    analysis = _parse(answer(needs_human_review=True, review_reasons=["page 2 was skewed"]))
    assert analysis.lines, "the lines are what the family came for"
    assert analysis.review_reasons == ["page 2 was skewed"]


# --- which failures are worth a second read --------------------------------


@pytest.mark.parametrize(
    "bad",
    ["not json at all", "{{{", '{"lines": "a string"}'],
    ids=["no json", "truncated", "wrong types"],
)
def test_a_malformed_answer_is_worth_asking_again(bad: str):
    """The pages were fine and the answer was not, so one more read is worth
    paying for."""
    with pytest.raises(OcrError) as raised:
        _parse(bad)
    assert raised.value.retryable


@pytest.mark.parametrize(
    "payload",
    [json.dumps({"error": "Not a hospital bill."}), None],
    ids=["not a bill", "no lines"],
)
def test_a_settled_answer_is_not_worth_asking_again(payload: str | None):
    """A document that isn't a bill will not become one on a second read, and
    paying twice to be told so helps nobody."""
    with pytest.raises(OcrError) as raised:
        _parse(payload if payload is not None else answer(lines=[], findings=[]))
    assert not raised.value.retryable


# --- the two fields where being wrong costs something ----------------------


@pytest.mark.parametrize("sent", ["pharmacy_drug", "PHARMACY_DRUG", " Pharmacy_Drug ", "pharmacy-drug"])
def test_a_category_is_read_through_its_spelling(sent: str):
    lines = [{**GOOD["lines"][0], "category": sent}]
    assert _parse(answer(lines=lines)).lines[0].category == "pharmacy_drug"


def test_an_unknown_category_files_the_line_under_the_catch_all():
    """It decides a heading in the report and nothing else, so the line keeps
    its place on the family's bill rather than taking the bill down with it."""
    lines = [{**GOOD["lines"][0], "category": "Pharmacy"}]
    analysis = _parse(answer(lines=lines))
    assert analysis.lines[0].category == "unclassified"
    assert analysis.lines[0].amount == 6500.0, "the line itself is untouched"


@pytest.mark.parametrize("sent", ["high", "HIGH", " High "])
def test_a_severity_is_read_through_its_spelling(sent: str):
    findings = [{**GOOD["findings"][0], "severity": sent}]
    assert _parse(answer(findings=findings)).findings[0].severity == "high"


def test_an_unknown_severity_refuses_the_bill():
    """This is the field that decides red or amber -- whether a family is told
    the bill proves something or that it is worth asking. There is no safe
    guess, so the bill is refused and retaken."""
    findings = [{**GOOD["findings"][0], "severity": "serious"}]
    with pytest.raises(OcrError, match="doesn't match PHASE 4"):
        _parse(answer(findings=findings))


# --- the scan itself --------------------------------------------------------


def test_the_object_scan_returns_only_the_object():
    assert json.loads(_json_object('prose {"a": 1} more prose')) == {"a": 1}


def test_the_object_scan_handles_nesting():
    assert json.loads(_json_object('{"a": {"b": [{"c": 1}]}}')) == {"a": {"b": [{"c": 1}]}}


# --- the request, and asking twice ------------------------------------------


class FakeResponse:
    """Just enough of a Messages response for `ClaudeOcr._ask`."""

    def __init__(self, text: str, stop_reason: str = "end_turn") -> None:
        self.stop_reason = stop_reason
        self.content = [type("Block", (), {"type": "text", "text": text})()]

    def model_dump_json(self, **_: object) -> str:
        return json.dumps({"stop_reason": self.stop_reason})


class FakeClient:
    def __init__(self, *answers: str | Exception) -> None:
        self.answers = list(answers)
        self.requests: list[dict] = []
        self.refuse = False
        self.cut_off = False
        self.messages = self

    def create(self, **request: object) -> FakeResponse:
        self.requests.append(request)
        if self.refuse:
            return FakeResponse("", stop_reason="refusal")
        if self.cut_off:
            return FakeResponse('{"bill": {', stop_reason="max_tokens")
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return FakeResponse(answer)


def reader(*answers: str | Exception) -> tuple[ClaudeOcr, FakeClient]:
    """A ClaudeOcr wired to a fake client, built without touching the SDK.

    Returns both, so a test asserts against the fake rather than reaching back
    through the reader's private attribute for it.
    """
    from ocr import ClaudeOcr

    client = FakeClient(*answers)
    instance = ClaudeOcr.__new__(ClaudeOcr)
    instance._client = client  # type: ignore[assignment]
    instance._model = "claude-sonnet-5-5"
    instance._effort = "medium"
    return instance, client


def one_page():
    from ocr import BillPage

    return [BillPage(data=b"\xff\xd8\xff\xe0 a page", content_type="image/jpeg")]


def test_the_request_sends_no_schema():
    """PHASE 4 of the prompt is the only statement of the shape. A schema here
    would be a second one, and the two would drift."""
    bill, client = reader(answer())
    bill.read_bill(one_page())

    (request,) = client.requests
    assert "output_format" not in request
    assert "output_config" in request, "effort is still set"
    assert set(request) == {"model", "max_tokens", "system", "output_config", "messages"}


def test_the_prompt_is_what_is_sent():
    from analysis_prompt import PROMPT

    bill, client = reader(answer())
    bill.read_bill(one_page())
    assert client.requests[0]["system"] == PROMPT, "no assembly, no interpolation"


def test_a_malformed_answer_is_read_again():
    bill, client = reader("I'll analyse this bill for you.", answer())
    analysis = bill.read_bill(one_page())

    assert analysis.bill.hospital == "City Care Hospital"
    assert len(client.requests) == 2, "the same pages, asked once more"


def test_a_second_malformed_answer_is_the_bill_not_the_luck():
    bill, client = reader("no json here", "still no json")
    with pytest.raises(OcrError):
        bill.read_bill(one_page())
    assert len(client.requests) == 2, "two reads, not a loop"


def test_a_document_that_is_not_a_bill_is_not_read_twice():
    """Paying for a second read to be told the same thing helps nobody."""
    bill, client = reader(json.dumps({"error": "This is a prescription, not a bill."}))
    with pytest.raises(OcrError, match="prescription"):
        bill.read_bill(one_page())
    assert len(client.requests) == 1


def test_an_answer_cut_off_at_max_tokens_says_so():
    """The fix is a bigger max_tokens, not a better photograph, so the message
    whoever runs this sees has to say which."""
    bill, client = reader()
    client.cut_off = True
    with pytest.raises(OcrError, match="max_tokens"):
        bill.read_bill(one_page())


def test_a_refusal_is_not_read_again():
    bill, client = reader()
    client.refuse = True
    with pytest.raises(OcrError, match="couldn't be read"):
        bill.read_bill(one_page())


# --- the prompt's own conventions, which the model has to take --------------
#
# These were found the hard way: a real bill came back as valid JSON and the
# parser threw all 26 lines of it away. Both causes are the prompt instructing
# the reader to do something the model refused to accept.


@pytest.mark.parametrize("field", ["unit", "date", "ambiguity_reason", "section", "item_name_plain"])
def test_a_null_text_field_reads_as_nothing_printed(field: str):
    """ABSOLUTE CONSTRAINT 3 tells the reader to output null where a field is
    unreadable. "Not printed" and "unreadable" are the same to everything
    downstream -- nothing to show -- so both are ""."""
    lines = [{**GOOD["lines"][0], field: None}]
    assert getattr(_parse(answer(lines=lines)).lines[0], field) == ""


@pytest.mark.parametrize(
    "printed,read",
    [
        ("1 1/4", 1.25),
        ("1/4", 0.25),
        ("2 1/2", 2.5),
        ("3", 3.0),
        ("5,150.00", 5150.0),
        ("Rs. 450", 450.0),
        ("₹1,250.50", 1250.5),
        (" 6 ", 6.0),
    ],
)
def test_a_figure_is_read_as_the_bill_prints_it(printed: str, read: float):
    """PHASE 1 asks for verbatim transcription, so figures arrive formatted
    the way a hospital writes them. Part-day beds really are billed "1 1/4"."""
    lines = [{**GOOD["lines"][0], "quantity": printed}]
    assert _parse(answer(lines=lines)).lines[0].quantity == read


@pytest.mark.parametrize("printed", ["---", "", "as per chart", "N/A"])
def test_a_figure_that_is_not_one_reads_as_nothing_stated(printed: str):
    """Null, not zero: a quantity the bill does not state is not a quantity of
    none, and treating it as one would understate a line."""
    lines = [{**GOOD["lines"][0], "quantity": printed}]
    assert _parse(answer(lines=lines)).lines[0].quantity is None


def test_a_part_day_stay_is_not_rounded_away():
    """31 hours 45 minutes is 1.32 days, and the reader says so."""
    assert _parse(answer(bill={**GOOD["bill"], "stay_days": 1.32})).bill.stay_days == 1.32


def test_a_count_arriving_as_text_is_still_a_count():
    lines = [{**GOOD["lines"][0], "page": "1"}]
    assert _parse(answer(lines=lines)).lines[0].page == 1


def test_fields_the_reader_invents_are_ignored():
    """Readers add detail the format never asked for -- a payment block, a
    note beside a figure. None of it is read, and none of it is fatal: the
    format is the contract, and extra is not a breach of it."""
    extra = {**GOOD["bill"], "payment": {"status": "PAID"}, "stay_days_note": "about 31 hours"}
    analysis = _parse(answer(bill=extra, consulting_doctors=["Dr. A. Example"]))
    assert analysis.bill.total == 6500.0
    assert not hasattr(analysis.bill, "payment")


def test_a_reader_that_states_no_confidence_is_not_a_bad_read():
    """An absent figure says nothing either way, so it must not be read as
    zero and condemn a bill the reader actually read."""
    bill = {**GOOD["bill"], "extraction_confidence": None}
    analysis = _parse(answer(bill=bill, findings=[], needs_human_review=True))
    assert analysis.unreadable() == ""
    assert analysis.lines
