from app.domain.states import AnswerStatus, PaperStatus, ProjectStatus


def test_initial_states_match_the_product_workflow() -> None:
    assert ProjectStatus.DRAFT == "DRAFT"
    assert PaperStatus.DISCOVERED == "DISCOVERED"
    assert AnswerStatus.QUESTION_RECEIVED == "QUESTION_RECEIVED"


def test_evidence_failure_is_an_explicit_answer_state() -> None:
    assert AnswerStatus.INSUFFICIENT_EVIDENCE == "INSUFFICIENT_EVIDENCE"
