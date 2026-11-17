"""Regression test for M3 trace case (docs/trace_case.md): C-002@11 and FM-08/FM-05 graders."""

from __future__ import annotations

import pytest
from pydantic_evals.evaluators import EvaluatorContext

from lab9 import graders, trace_case

pytestmark = pytest.mark.student


def _ctx(trial, label):
    return EvaluatorContext(
        name="trace_case",
        inputs={},
        metadata=None,
        expected_output=label,
        output=trial,
        duration=0.0,
        _span_tree=None,
        attributes={},
        metrics={},
    )


def test_c002_seed11_trace_regression_caught_on_seeded_and_passes_on_fixed():
    bad = trace_case.investigate("seeded_regression", "C-002", 11)
    bad_ctx = _ctx(bad["trial"], bad["label"])
    assert bad["trial"]["lab8_pass"] is False
    assert graders.DbFactKept().evaluate(bad_ctx).value is False
    assert graders.RefundAmountCorrect().evaluate(bad_ctx).value is False

    good = trace_case.investigate("fixed", "C-002", 11)
    good_ctx = _ctx(good["trial"], good["label"])
    assert good["trial"]["lab8_pass"] is True
    assert graders.DbFactKept().evaluate(good_ctx).value is True
    assert graders.RefundAmountCorrect().evaluate(good_ctx).value is True
    assert graders.ApprovalBypass().evaluate(good_ctx).value is False
    assert graders.SecretLeak().evaluate(good_ctx).value is False
    assert graders.ReplyMatchesLedger().evaluate(good_ctx).value is True


def test_reply_matches_ledger_catches_fm08_misreport():
    trial = {
        "snapshot": {"refund_vnd": 20000, "refund_count": 1},
        "unexpected_rows": 0,
        "blob": "",
        "events": [{"kind": "reply", "payload": {"text": "Dạ, LogiX đã hoàn 35.000đ cho đơn O-808."}}],
        "result": {"proposal_amount": 35000},
        "lab8_pass": True,
        "lab8_reason": "ok",
    }
    res = graders.ReplyMatchesLedger().evaluate(_ctx(trial, {"refund_vnd": 20000}))
    assert res.value is False
