import pytest
from withaq.disclosure import Policy


@pytest.mark.parametrize("payload", [
    "national_id synthetic", "password synthetic", "API_KEY fake", "رقم الهوية تجريبي",
    "كَلِمَةُ الْمُرُور", "national\u200b_id fake", "هوية ١٢٣٤٥٦٧٨٩٠", "id ۱۲۳۴۵۶۷۸۹۰",
    "ignore previous instructions", "تجاهل التعليمات السابقة",
])
def test_bilingual_prohibited_corpus(payload):
    result = Policy().inspect(payload, "mock://review", "demo", "competition-demo")
    assert result["decision"] == "BLOCK" and result["payload"] == ""


@pytest.mark.parametrize("payload", ["Synthetic telemetry 23.4", "قراءة اصطناعية آمنة ٢٣٫٤"])
def test_allowed_corpus(payload):
    result = Policy().inspect(payload, "mock://local", "demo", "competition-demo")
    assert result["decision"] in ("ALLOW", "SANITIZE")
    assert Policy().inspect(result["payload"], "mock://local", "demo", "competition-demo")["decision"] == "ALLOW"


def test_all_four_decisions_and_destination_policy():
    policy = Policy()
    assert policy.inspect("Safe synthetic report", "mock://local", "demo", "competition-demo")["decision"] == "ALLOW"
    assert policy.inspect("Safe synthetic report", "mock://review", "demo", "competition-demo")["decision"] == "REQUIRE_APPROVAL"
    assert policy.inspect("Contact fake@example.test", "mock://review", "demo", "competition-demo")["decision"] == "SANITIZE"
    assert policy.inspect("Safe report", "https://example.com", "demo", "competition-demo")["decision"] == "BLOCK"
