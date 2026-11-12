"""Write dev/sample-refund.json: a synthetic, hand-written map for exercising the viewer.

It is not analyzer output. It covers what the expense sample lacks: branches that meet
again, a retry loop, an error path, a candidate edge, a new step, a removed step, a change
with no place on the map, a flow that can only reach changed code, a removed flow, a
skeleton flow and a changed file that was not analyzed. Its flows sit in four modules, so the
overview has a module that holds the changes and modules that do not.
"""

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "dev" / "sample-refund.json"
evidence: list[dict] = []
excerpts: dict[str, str] = {}


def ev(
    path: str, start: int, end: int | None = None, side: str = "head", text: str | None = None
) -> str:
    evidence_id = f"ev_{len(evidence):04d}{side[0]}"
    evidence.append(
        {
            "evidence_id": evidence_id,
            "side": side,
            "path": path,
            "range": {"start_line": start, "end_line": end or start},
        }
    )
    if text is not None:
        excerpts[evidence_id] = text
    return evidence_id


def step(
    key, name, kind, anchors=(), resolution="resolved", reason=None, findings=(), code=None, line=1
):
    item = {
        "step_id": f"step_{key}",
        "name": name,
        "kind": kind,
        "support": "agent_synthesis",
        "resolution": resolution,
        "anchors": [f"fp_{a}" for a in anchors] or [f"fp_{key}"],
        "evidence_ids": [ev("refunds/service.py", line, line, text=code)],
        "finding_ids": list(findings),
    }
    if reason:
        item["reason"] = reason
    return item


def edge(
    source, target, relation="sequence", label=None, branch=None, resolution="resolved", reason=None
):
    item = {
        "source": f"step_{source}",
        "target": f"step_{target}",
        "relation": relation,
        "support": "agent_synthesis",
        "resolution": resolution,
        "evidence_ids": [ev("refunds/service.py", 1)],
    }
    if branch is not None:
        item["condition"] = {"label": label, "branch": branch, "anchor": f"fp_{source}"}
    elif label:
        item["label"] = label
    if reason:
        item["reason"] = reason
    return item


refund = {
    "flow_id": "flow_refund",
    "name": "申请退款",
    "summary": "买家申请退款。已发货的订单先退货；未发货的订单按金额决定是否需要人工审批，然后调用支付渠道退款，失败会自动重试。",
    "stage": "synthesized",
    "support": "agent_synthesis",
    "entries": [
        {
            "entry_id": "entry_refund",
            "symbol_id": "refunds/api.py#create_refund",
            "kind": "http_route",
            "detection": "adapter",
            "framework": "fastapi",
            "attributes": {"method": "POST", "path": "/orders/{order_id}/refunds"},
            "evidence_ids": [ev("refunds/api.py", 12)],
        }
    ],
    "steps": [
        step(
            "received",
            "收到退款申请",
            "trigger",
            line=12,
            code='@router.post("/orders/{order_id}/refunds")',
        ),
        step("load", "读取订单和支付记录", "action", line=14, code="order = orders.get(order_id)"),
        step("shipped", "订单是否已经发货", "decision", line=16, code="if order.shipped:"),
        step("return", "生成退货单", "action", line=17, code="ticket = returns.open(order)"),
        step(
            "await",
            "等待买家寄回商品",
            "result",
            line=18,
            code='return {"status": "awaiting_return"}',
        ),
        step(
            "amount",
            "退款金额是否超过 500 元",
            "decision",
            anchors=("amount_new",),
            line=20,
            code="if refund.amount > 500:",
        ),
        step(
            "review",
            "交给客服人工审批",
            "external",
            line=21,
            code="decision = await approvals.request(refund)",
        ),
        step(
            "approved",
            "审批是否通过",
            "decision",
            anchors=("approved_new",),
            line=22,
            code="if not decision.approved:",
        ),
        step("rejected", "退款被拒绝", "result", line=23, code='return {"status": "rejected"}'),
        step(
            "pay",
            "调用支付渠道退款",
            "external",
            anchors=("pay", "retry_new"),
            findings=("find_retry",),
            line=25,
            code="for attempt in range(3):\n    result = await gateway.refund(order.payment_id, refund.amount)",
        ),
        step("paid", "渠道是否返回成功", "decision", line=27, code="if result.ok:"),
        step("mark", "把订单标为已退款", "action", line=28, code='orders.mark(order, "refunded")'),
        step("done", "退款完成，通知买家", "result", line=29, code='return {"status": "refunded"}'),
        step(
            "failed",
            "退款异常，转人工处理",
            "result",
            resolution="candidate",
            reason="渠道抛出异常时会进入 except 分支，静态分析没有覆盖 try/except。",
            line=33,
            code='except GatewayError:\n    return {"status": "manual"}',
        ),
    ],
    "edges": [
        edge("received", "load"),
        edge("load", "shipped"),
        edge("shipped", "return", "branch", "已发货", "true"),
        edge("return", "await"),
        edge("shipped", "amount", "branch", "未发货", "false"),
        edge("amount", "review", "branch", "超过 500 元", "true"),
        edge("review", "approved"),
        edge("approved", "rejected", "branch", "审批没通过", "true"),
        edge("approved", "pay", "branch", "审批通过", "false"),
        edge("amount", "pay", "branch", "不超过 500 元", "false"),
        edge("pay", "paid"),
        edge("paid", "mark", "branch", "成功", "true"),
        edge("paid", "pay", "loop", "失败时重试，最多 3 次", None),
        edge("mark", "done"),
        edge(
            "pay",
            "failed",
            "exception",
            "渠道报错",
            resolution="candidate",
            reason="try/except 没有被分析",
        ),
    ],
    "accounting": {"accountable": 9, "covered": 9, "omitted": 0, "unaccounted": 0},
    "finding_ids": [],
}

progress = {
    "flow_id": "flow_progress",
    "name": "查询退款进度",
    "summary": "买家在订单页查看退款走到了哪一步。",
    "stage": "synthesized",
    "support": "agent_synthesis",
    "entries": [
        {
            "entry_id": "entry_progress",
            "symbol_id": "refunds/api.py#refund_status",
            "kind": "http_route",
            "detection": "adapter",
            "attributes": {"method": "GET", "path": "/orders/{order_id}/refunds"},
            "evidence_ids": [ev("refunds/api.py", 40)],
        }
    ],
    "steps": [
        step(
            "q_received",
            "收到查询",
            "trigger",
            line=40,
            code='@router.get("/orders/{order_id}/refunds")',
        ),
        step(
            "q_lookup",
            "向支付渠道查询退款状态",
            "external",
            line=42,
            code="state = await gateway.status(order.payment_id)",
        ),
        step("q_known", "渠道是否知道这笔退款", "decision", line=43, code="if state is None:"),
        step(
            "q_missing",
            "显示“还没有提交到渠道”",
            "result",
            line=44,
            code='return {"status": "pending"}',
        ),
        step(
            "q_show", "显示渠道返回的进度", "result", line=45, code='return {"status": state.name}'
        ),
    ],
    "edges": [
        edge("q_received", "q_lookup"),
        edge("q_lookup", "q_known"),
        edge("q_known", "q_missing", "branch", "渠道没有记录", "true"),
        edge("q_known", "q_show", "branch", "渠道有记录", "false"),
    ],
    "accounting": {"accountable": 3, "covered": 3, "omitted": 0, "unaccounted": 0},
}

cancel = {
    "flow_id": "flow_cancel",
    "name": "POST /refunds/{refund_id}/cancel · cancel_refund",
    "stage": "skeleton",
    "support": "static_fact",
    "entries": [
        {
            "entry_id": "entry_cancel",
            "symbol_id": "refunds/api.py#cancel_refund",
            "kind": "http_route",
            "detection": "adapter",
            "attributes": {"method": "POST", "path": "/refunds/{refund_id}/cancel"},
            "evidence_ids": [ev("refunds/api.py", 52)],
        }
    ],
    "steps": [
        {
            **step("c_entry", "cancel_refund(refund_id)", "trigger", line=52),
            "support": "static_fact",
        },
        {
            **step("c_cond", "refund.status != 'pending'", "decision", line=54),
            "support": "static_fact",
        },
        {
            **step("c_raise", "raise RefundLocked(refund_id)", "result", line=55),
            "support": "static_fact",
        },
        {**step("c_call", "refunds.cancel(refund)", "action", line=56), "support": "static_fact"},
        {
            **step("c_ret", "return {'status': 'cancelled'}", "result", line=57),
            "support": "static_fact",
        },
    ],
    "edges": [
        edge("c_entry", "c_cond"),
        edge("c_cond", "c_raise", "branch", "true", "true"),
        edge("c_cond", "c_call", "branch", "false", "false"),
        edge("c_call", "c_ret"),
    ],
    "accounting": {"accountable": 3, "covered": 2, "omitted": 0, "unaccounted": 1},
    "unaccounted": ["fp_c_extra"],
}

sms_flow = {
    "flow_id": "flow_sms_receipt",
    "name": "退款短信回执",
    "summary": "退款完成后给买家发短信，并记录短信是否送达。",
    "stage": "synthesized",
    "support": "agent_synthesis",
    "entries": [
        {
            "entry_id": "entry_sms",
            "symbol_id": "refunds/notify.py#send_receipt",
            "kind": "task",
            "detection": "adapter",
            "attributes": {"name": "send_refund_receipt"},
            "evidence_ids": [ev("refunds/notify.py", 8, side="base")],
        }
    ],
    "steps": [
        {
            **step("s_task", "收到发送任务", "trigger", line=8),
            "evidence_ids": [ev("refunds/notify.py", 8, side="base")],
        },
        {
            **step("s_send", "发送退款短信", "external", line=10),
            "evidence_ids": [ev("refunds/notify.py", 10, side="base")],
        },
        {
            **step("s_log", "记录送达结果", "result", line=12),
            "evidence_ids": [ev("refunds/notify.py", 12, side="base")],
        },
    ],
    "edges": [edge("s_task", "s_send"), edge("s_send", "s_log")],
    "accounting": {"accountable": 2, "covered": 2, "omitted": 0, "unaccounted": 0},
}

def simple_flow(flow_id, name, summary, entry, steps, edges):
    return {
        "flow_id": flow_id,
        "name": name,
        "summary": summary,
        "stage": "synthesized",
        "support": "agent_synthesis",
        "entries": [entry],
        "steps": steps,
        "edges": edges,
        "accounting": {"accountable": 2, "covered": 2, "omitted": 0, "unaccounted": 0},
    }


callback = simple_flow(
    "flow_callback",
    "渠道退款回调",
    "支付渠道处理完退款后回调我们，更新退款状态。",
    {
        "entry_id": "entry_callback",
        "symbol_id": "payments/webhooks.py#refund_callback",
        "kind": "http_route",
        "detection": "adapter",
        "attributes": {"method": "POST", "path": "/webhooks/refunds"},
        "evidence_ids": [ev("payments/webhooks.py", 12)],
    },
    [
        step("cb_in", "收到渠道回调", "trigger", line=12),
        step("cb_sig", "签名是否有效", "decision", line=14),
        step("cb_update", "更新退款状态", "action", line=16),
        step("cb_ok", "回复渠道成功", "result", line=18),
        step("cb_reject", "拒绝这次回调", "result", line=20),
    ],
    [
        edge("cb_in", "cb_sig"),
        edge("cb_sig", "cb_update", "branch", "签名有效", "true"),
        edge("cb_sig", "cb_reject", "branch", "签名无效", "false"),
        edge("cb_update", "cb_ok"),
    ],
)

email = simple_flow(
    "flow_email",
    "退款结果邮件",
    "退款有结果后给买家发一封邮件。",
    {
        "entry_id": "entry_email",
        "symbol_id": "notify/email.py#send_refund_email",
        "kind": "task",
        "detection": "adapter",
        "attributes": {"name": "send_refund_email"},
        "evidence_ids": [ev("notify/email.py", 6)],
    },
    [
        step("em_task", "收到发邮件任务", "trigger", line=6),
        step("em_send", "调用邮件服务", "external", line=8),
        step("em_log", "记录发送结果", "result", line=10),
    ],
    [edge("em_task", "em_send"), edge("em_send", "em_log")],
)

reconcile = simple_flow(
    "flow_reconcile",
    "每日退款对账",
    "每天核对渠道账单和我们记的退款是否一致。",
    {
        "entry_id": "entry_reconcile",
        "symbol_id": "reconcile/jobs.py#daily_refunds",
        "kind": "scheduled",
        "detection": "adapter",
        "attributes": {"schedule": "0 3 * * *"},
        "evidence_ids": [ev("reconcile/jobs.py", 4)],
    },
    [
        step("rc_start", "每天凌晨开始", "trigger", line=4),
        step("rc_pull", "拉取渠道账单", "external", line=6),
        step("rc_same", "金额是否一致", "decision", line=8),
        step("rc_done", "标记已对账", "result", line=9),
        step("rc_ticket", "生成差异工单", "result", line=11),
    ],
    [
        edge("rc_start", "rc_pull"),
        edge("rc_pull", "rc_same"),
        edge("rc_same", "rc_done", "branch", "一致", "true"),
        edge("rc_same", "rc_ticket", "branch", "不一致", "false"),
    ],
)

finding = {
    "finding_id": "find_retry",
    "source": "agent_observation",
    "severity": "medium",
    "statement": "重试时没有带幂等键。渠道超时但其实已经退款时，再次调用可能给买家退两次钱。",
    "evidence_ids": [ev("refunds/service.py", 25, 26)],
}


def side(kind, text, anchor, path, line, side_name):
    return {
        "side": side_name,
        "text": text,
        "anchor": f"fp_{anchor}",
        "evidence_ids": [ev(path, line, side=side_name, text=text)],
    }


changes = [
    {
        "change_id": "chg_amount",
        "kind": "condition_modified",
        "symbol_id": "refunds/service.py#create_refund",
        "before": side(
            "c", "if refund.amount > 1000:", "amount_old", "refunds/service.py", 20, "base"
        ),
        "after": side(
            "c", "if refund.amount > 500:", "amount_new", "refunds/service.py", 20, "head"
        ),
        "projection": {"status": "projected", "flow_id": "flow_refund", "step_id": "step_amount"},
        "explanation": {
            "summary": "需要人工审批的金额门槛从 1000 元降到了 500 元。",
            "effect": "500 到 1000 元之间、还没发货的退款，现在要等客服审批，不再自动退款。",
        },
        "tests": {
            "verdict": "covered",
            "basis": ["static_fact", "agent_assessment"],
            "execution_data": "not_collected",
            "note": "测试分别用 499、500、501 元提交，并断言 501 元会进入审批。",
            "items": [
                {
                    "test_id": "head::tests/test_refund.py#test_review_threshold",
                    "tags": ["related", "assertion_found"],
                    "evidence_ids": [ev("tests/test_refund.py", 30, 41)],
                }
            ],
        },
    },
    {
        "change_id": "chg_approved",
        "kind": "condition_added",
        "symbol_id": "refunds/service.py#create_refund",
        "after": side(
            "c", "if not decision.approved:", "approved_new", "refunds/service.py", 22, "head"
        ),
        "projection": {"status": "projected", "flow_id": "flow_refund", "step_id": "step_approved"},
        "explanation": {
            "summary": "新增了审批结果判断：客服不同意时直接拒绝退款。",
            "effect": "以前审批只是记录，现在客服可以真正拦下一笔退款。",
        },
        "tests": {
            "verdict": "unknown",
            "basis": ["agent_assessment"],
            "execution_data": "not_collected",
            "note": "测试把审批服务换成了固定返回“通过”的替身，看不出拒绝的分支有没有被断言。",
            "items": [
                {
                    "test_id": "head::tests/test_refund.py#test_large_refund_waits",
                    "tags": ["related", "fixture_or_mock_related"],
                    "evidence_ids": [ev("tests/test_refund.py", 50, 58)],
                }
            ],
        },
    },
    {
        "change_id": "chg_retry",
        "kind": "loop_added",
        "symbol_id": "refunds/service.py#create_refund",
        "after": side(
            "l",
            "for attempt in range(3):\n    result = await gateway.refund(order.payment_id, refund.amount)\n    if result.ok:\n        break",
            "retry_new",
            "refunds/service.py",
            25,
            "head",
        ),
        "projection": {"status": "projected", "flow_id": "flow_refund", "step_id": "step_pay"},
        "other_projections": [
            {
                "status": "projected",
                "flow_id": "flow_progress",
                "step_id": "step_q_lookup",
                "reason": "查询进度也会调用同一个渠道客户端。",
            }
        ],
        "explanation": {
            "summary": "支付渠道失败时会自动重试，最多 3 次。",
            "effect": "渠道临时故障时买家不用重新申请；但重试没有幂等键，可能重复退款。",
        },
        "tests": {
            "verdict": "not_reached",
            "basis": ["static_fact"],
            "execution_data": "not_collected",
            "note": "没有测试模拟渠道失败。",
        },
        "finding_ids": ["find_retry"],
    },
    {
        "change_id": "chg_sms",
        "kind": "call_removed",
        "symbol_id": "refunds/service.py#create_refund",
        "before": side(
            "c",
            "await sms.send(order.buyer_phone, receipt)",
            "sms_old",
            "refunds/service.py",
            30,
            "base",
        ),
        "projection": {
            "status": "removed_step",
            "flow_id": "flow_refund",
            "removed_step": {"step_id": "step_sms", "name": "给买家发退款短信"},
        },
        "explanation": {
            "summary": "退款完成后不再给买家发短信。",
            "effect": "买家只能在订单页看到退款结果。",
        },
        "tests": {
            "verdict": "reached_only",
            "basis": ["static_fact", "agent_assessment"],
            "execution_data": "not_collected",
            "note": "退款完成的测试还在，但没有检查是否发了短信。",
            "items": [
                {
                    "test_id": "head::tests/test_refund.py#test_small_refund_paid",
                    "tags": ["related"],
                    "evidence_ids": [ev("tests/test_refund.py", 70, 80)],
                }
            ],
        },
    },
    {
        "change_id": "chg_currency",
        "kind": "source_modified",
        "symbol_id": "refunds/settings.py",
        "before": side(
            "s", 'DEFAULT_CURRENCY = "CNY"', "cur_old", "refunds/settings.py", 3, "base"
        ),
        "after": side("s", 'DEFAULT_CURRENCY = "USD"', "cur_new", "refunds/settings.py", 3, "head"),
        "projection": {"status": "unassigned", "reason": "No step of the map rests on this code."},
        "explanation": {
            "summary": "默认币种从人民币改成了美元。",
            "effect": "没有指定币种的退款会按美元记账。",
        },
    },
]

payload = {
    "format_version": 1,
    "share": False,
    "map": {
        "snapshot_id": "sha256:sample",
        "side": "head",
        "analysis_status": "partial",
        "domains": [
            {
                "domain_id": "dom_refund",
                "name": "退款",
                "support": "agent_synthesis",
                "flow_ids": ["flow_refund", "flow_progress", "flow_cancel"],
            },
            {
                "domain_id": "dom_payments",
                "name": "支付渠道",
                "support": "agent_synthesis",
                "flow_ids": ["flow_callback"],
            },
            {
                "domain_id": "dom_notify",
                "name": "通知",
                "support": "agent_synthesis",
                "flow_ids": ["flow_email"],
            },
            {
                "domain_id": "dom_reconcile",
                "name": "对账",
                "support": "agent_synthesis",
                "flow_ids": ["flow_reconcile"],
            },
        ],
        "flows": [refund, progress, cancel, callback, email, reconcile],
        "findings": [finding],
        "coverage": {
            "scope": "3 planned flows covering 3 of 4 entries.",
            "entries_total": 4,
            "entries_planned": 3,
            "entries_skipped": 1,
            "skipped_entries": [
                {
                    "entry_id": "entry_health",
                    "symbol_id": "app.py#health",
                    "reason": "infrastructure",
                }
            ],
            "entries_unhandled": 0,
            "tasks_total": 3,
            "tasks_validated": 2,
            "tasks_pending": 1,
            "tasks_failed": 0,
        },
        "limitations": [
            {
                "code": "skeleton_flows",
                "message": "1 flow is still a static skeleton.",
                "affects_completeness": True,
            }
        ],
        "evidence": evidence,
    },
    "report": {
        "base_ref": "main",
        "base_revision": "9c1e2f4b7a0d",
        "head_ref": "feat/refund-review",
        "head_revision": "41aa09d3e2c1",
        "analysis_status": "complete",
        "changes": changes,
        "removed_flows": [sms_flow],
        "possibly_affected": [
            {
                "flow_id": "flow_cancel",
                "change_ids": ["chg_retry"],
                "reason": "取消退款会调用改过的渠道客户端。",
            }
        ],
        "unanalyzed_changes": [
            {
                "path": "web/src/RefundForm.tsx",
                "change": "modified",
                "reason": "TypeScript is not analyzed.",
            }
        ],
        "finding_changes": [
            {
                "status": "introduced",
                "finding": finding,
                "flow_id": "flow_refund",
                "step_id": "step_pay",
            }
        ],
        "limitations": [
            {
                "code": "no_execution_data",
                "message": "No test was run; verdicts come from reading source.",
            }
        ],
        "evidence": [],
    },
    "excerpts": excerpts,
}

OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(OUT)
