import pytest

from mrhub.agents.review_export import ExportError, export_review_summary


def data(**kw):
    d={"revision":1,"digest":"a"*64,"approved":False,"findings":["needs review"]}
    d.update(kw);return d

def test_deterministic_export_and_hash():
    a=export_review_summary(data());b=export_review_summary(data())
    assert a==b and len(a["sha256"])==64 and a["schema_version"]==1

@pytest.mark.parametrize("change",[{"revision":True},{"approved":"yes"},{"digest":"bad"},{"findings":"oops"}])
def test_rejects_malformed(change):
    with pytest.raises(ExportError):export_review_summary(data(**change))

def test_bounds_findings():
    with pytest.raises(ExportError):export_review_summary(data(findings=["x"]*501))


def test_digest_requires_lowercase_hex():
    with pytest.raises(ExportError):
        export_review_summary(data(digest="g" * 64))


def test_utf8_payload_byte_limit_is_enforced():
    with pytest.raises(ExportError):
        export_review_summary(data(findings=["é" * 500] * 500))
