from app.services import rag


def test_insufficient_answer_and_reference_numbers():
    assert rag.answer_is_insufficient("知识库没有关于今天准确售价的信息。")
    assert rag.factual_numbers("支持7天退货【656853205201749†L152-L168】[Source 2]") == {"7天"}
