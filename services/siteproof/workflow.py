import logging
import time
import uuid
from typing import TypedDict

import httpx
import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph

from . import db
from .audit import verify
from .config import settings
from .contracts import Budget, PageSpec, preserve_facts
from .journal import once
from .providers import provider
from .retrieval import cached_embedding, embedding_identity, index_embeddings, retrieve
from .storage import put


class State(TypedDict, total=False):
    tenant: str
    job_id: str
    action: str
    revision: int
    findings: list[dict]
    evidence: list[dict]
    facts: list[dict]
    spec: dict
    html: str
    after: list[dict]
    verification: dict
    repair_attempts: int
    started: float
    prior_elapsed: float
    budget: dict
    images: list[dict]
    guidance: list[dict]


def restore_usage(state, saved):
    current = Budget.model_validate(state.get("budget", {}))
    restored = Budget.model_validate(saved)
    for field in ("tokens", "tool_calls", "elapsed_seconds"):
        setattr(restored, field, max(getattr(current, field), getattr(restored, field)))
    restored.cost_unknown |= current.cost_unknown
    restored.cost = None if restored.cost_unknown else max(current.cost or 0, restored.cost or 0) if current.cost is not None or restored.cost is not None else None
    state["budget"] = restored.model_dump()


def check(state):
    job = db.get_job(state["tenant"], state["job_id"])
    if not job or job["status"] == "cancelled":
        raise ValueError("Job cancelled")
    budget = Budget.model_validate(state.get("budget", {}))
    elapsed = state.get("prior_elapsed", 0) + time.time() - state.get("started", time.time())
    budget.consume(elapsed=elapsed)
    state["budget"] = budget.model_dump()
    db.update_job(state["tenant"], state["job_id"], job["status"], {"budget": state["budget"]})


def record_run(state, run):
    db.save_records(state["tenant"], state["job_id"], "ModelRun", [dict(run, id="model-" + str(uuid.uuid4()))])
    budget = Budget.model_validate(state["budget"])
    budget.consume(tokens=run["tokens"], cost=run["cost"])
    state["budget"] = budget.model_dump()
    check(state)


def remote_capture(state, *, url=None, html=None, prefix=""):
    check(state)
    with httpx.Client(timeout=160) as client:
        response = client.post(
            settings.browser_url + "/capture",
            headers={"X-Browser-Key": settings.browser_key},
            json={"url": url, "html": html},
        )
        response.raise_for_status()
        data = response.json()
    check(state)
    phase = "after" if prefix else "before"
    for item in data["evidence"]:
        item["id"] = prefix + item["id"]
        item["phase"] = phase
    for shot in data["screenshots"]:
        shot["id"] = prefix + shot["id"]
        key = put(state["tenant"], state["job_id"], shot)
        data["evidence"].append(
            {
                "id": shot["id"],
                "kind": "screenshot",
                "viewport": shot["viewport"],
                "phase": phase,
                "artifact_key": key,
                "artifact_url": f"/api/artifacts/{state['job_id']}/{shot['id']}",
            }
        )
    db.save_records(state["tenant"], state["job_id"], "Evidence", data["evidence"])
    db.save_records(
        state["tenant"],
        state["job_id"],
        "Capture",
        [
            {
                "id": prefix + "capture",
                "partial": data["partial"],
                "phase": phase,
                "viewport_settings": {"desktop": [1440, 1000], "mobile": [390, 844]},
            }
        ],
    )
    return data


def auditor(state):
    if state["action"] == "redesign":
        state["evidence"] = [
            e
            for e in db.records(state["tenant"], state["job_id"], "Evidence")
            if e.get("phase", "before") == "before" and not e["id"].startswith("after-")
        ]
        state["findings"] = db.records(state["tenant"], state["job_id"], "Finding")
        state["facts"] = db.records(state["tenant"], state["job_id"], "BusinessFact")
        state["guidance"] = db.get_job(state["tenant"], state["job_id"])["data"].get("guidance_snapshot", [])
        with db.connection() as conn:
            row = conn.execute("SELECT result FROM workflow_steps WHERE tenant_id=%s AND job_id=%s AND step='capture-v1' AND status='succeeded'", (state["tenant"], state["job_id"])).fetchone()
        state["images"] = row["result"]["screenshots"] if row else []
        return state
    db.update_job(state["tenant"], state["job_id"], "capturing")
    job = db.get_job(state["tenant"], state["job_id"])
    capture = once(
        state["tenant"], state["job_id"], "capture-v1", lambda: remote_capture(state, url=job["canonical_url"])
    )
    state["evidence"], state["facts"] = capture["evidence"], capture["facts"]
    if capture.get("canonical_url"):
        with db.connection() as conn:
            conn.execute(
                "UPDATE audit_jobs SET canonical_url=%s WHERE tenant_id=%s AND id=%s AND status <> 'cancelled'",
                (capture["canonical_url"], state["tenant"], state["job_id"]),
            )
    db.save_records(state["tenant"], state["job_id"], "BusinessFact", state["facts"])
    db.update_job(state["tenant"], state["job_id"], "auditing")
    query = "accessibility OR contact OR mobile OR navigation"
    model_provider = provider()
    budget = Budget.model_validate(state["budget"])
    embedding = None
    if settings.mode == "live":

        def persist_embedding(run, usage):
            # Commit each successful embedding call before proceeding to the next remote call.
            with db.locked_job(state["tenant"], state["job_id"]):
                db.save_records(
                    state["tenant"], state["job_id"], "ModelRun", [dict(run, id="embedding-" + run["content_hash"])]
                )
                db.update_job(state["tenant"], state["job_id"], "auditing", {"budget": usage.model_dump()})

        def embed():
            index_embeddings(state["tenant"], model_provider, budget, on_run=persist_embedding)
            vector = cached_embedding(state["tenant"], query, model_provider, budget, on_run=persist_embedding)
            return {"vector": vector, "budget": budget.model_dump()}

        embedded = once(state["tenant"], state["job_id"], "embeddings-v1", embed, paid=True)
        embedding = embedded["vector"]
        budget = Budget.model_validate(embedded["budget"])
        state["budget"] = budget.model_dump()
        check(state)
    guidance = retrieve(state["tenant"], query, embedding=embedding)

    def diagnose():
        findings, run = model_provider.findings(
            state["evidence"], guidance, images=capture["screenshots"], budget=budget
        )
        budget.consume(tokens=run["tokens"], cost=run["cost"])
        return {"findings": findings, "run": run, "guidance": guidance, "budget": budget.model_dump()}

    diagnosed = once(state["tenant"], state["job_id"], "findings-v2", diagnose, paid=settings.mode == "live")
    guidance = diagnosed.get("guidance", guidance)
    findings, run = diagnosed["findings"], diagnosed["run"]
    run = dict(
        run,
        retrieval_strategy="hybrid" if embedding is not None else "keyword",
        embedding_identity=embedding_identity() if embedding is not None else None,
        retrieved_guidance_ids=[g["id"] for g in guidance],
    )
    db.save_records(state["tenant"], state["job_id"], "ModelRun", [dict(run, id="audit-model")])
    # Restore the pre-call budget on replay; charge the persisted result exactly once.
    restore_usage(state, diagnosed["budget"])
    check(state)
    state["findings"] = findings
    db.save_records(state["tenant"], state["job_id"], "Finding", findings)
    db.update_job(
        state["tenant"],
        state["job_id"],
        "needs_review",
        {
            "fixture": settings.mode == "fixture",
            "guidance_ids": [g["id"] for g in guidance],
            "guidance_snapshot": guidance,
            "versions": {"prompt": "auditor-v2", "guidance": "guidance-v1", "renderer": "components-v2"},
            "elapsed_seconds": state["budget"].get("elapsed_seconds"),
            "budget": state["budget"],
        },
    )
    return state


def render_spec(state):
    check(state)
    preserve_facts(PageSpec.model_validate(state["spec"]), state["facts"])
    with httpx.Client(timeout=15) as client:
        response = client.post(
            settings.web_url + "/internal/render",
            headers={"X-Render-Key": settings.render_key},
            json={"spec": state["spec"]},
        )
        response.raise_for_status()
        state["html"] = response.text
    check(state)
    db.save_records(
        state["tenant"],
        state["job_id"],
        "Redesign",
        [
            {
                "id": f"redesign-{state.get('revision', 0)}-{state.get('repair_attempts', 0)}",
                "spec": state["spec"],
                "html": state["html"],
                "version": "components-v2",
                "revision": state.get("revision", 0),
                "repair_attempts": state.get("repair_attempts", 0),
                "targeted_finding_ids": [f["id"] for f in state["findings"] if f.get("approved")],
                "guidance_ids": db.get_job(state["tenant"], state["job_id"])["data"].get("guidance_ids", []),
                "missing_content": [name for name, missing in [("services", not state["spec"]["services"]), ("contacts", not state["spec"]["contacts"])] if missing],
                "design_decisions": [{"finding_id": f["id"], "proposed_change": f["proposed_change"], "verification_method": f["verification_method"], "selected_layout": state["spec"]["layout"], "outcome": "Requires executable verification or human review"} for f in state["findings"] if f.get("approved")],
            }
        ],
    )


def designer(state):
    if state["action"] != "redesign":
        return state
    check(state)
    db.update_job(state["tenant"], state["job_id"], "designing")
    dom = next((e["data"] for e in state["evidence"] if e["kind"] == "dom"), {})
    headings = [h["text"] for h in dom.get("headings", []) if h["text"]]
    contacts = [
        {
            "kind": f["kind"],
            "value": f["value"],
            "href": f.get("href", ("mailto:" if f["kind"] == "email" else "tel:") + f["value"]),
        }
        for f in state["facts"]
        if f["kind"] in ("email", "phone")
    ]
    spec = PageSpec(
        title=dom.get("title", "Business homepage"),
        headline=headings[0] if headings else "Contact our business",
        about=" ".join(p["text"] for p in dom.get("about", [])) or "Contact us to discuss the services listed on our original website.",
        services=[f["value"] for f in state["facts"] if f["kind"] == "service"],
        details=[f["value"] for f in state["facts"] if f["kind"] in ("hours", "price")],
        contacts=contacts,
        fixture=settings.mode == "fixture",
    )
    if settings.mode == "live":
        def design_once():
            usage = Budget.model_validate(state["budget"])
            result, run = provider().design(spec, state["facts"], [f for f in state["findings"] if f.get("approved")], usage, guidance=state.get("guidance", []), images=state.get("images", []))
            usage.consume(tokens=run["tokens"], cost=run["cost"])
            return {"spec": result.model_dump(), "run": run, "budget": usage.model_dump()}

        designed = once(state["tenant"], state["job_id"], f"design-v2-{state.get('revision', 0)}", design_once, paid=True)
        spec = PageSpec.model_validate(designed["spec"])
        db.save_records(state["tenant"], state["job_id"], "ModelRun", [dict(designed["run"], id=f"design-model-{state.get('revision', 0)}")])
        restore_usage(state, designed["budget"])
        check(state)
    state["spec"] = spec.model_dump()
    render_spec(state)
    return state


def verifier(state):
    if state["action"] != "redesign":
        return state
    db.update_job(state["tenant"], state["job_id"], "verifying")
    result = None
    for attempt in range(3):
        state["repair_attempts"] = attempt
        check(state)
        prefix = f"after-{state.get('revision', 0)}-{attempt}-"
        captured = once(state["tenant"], state["job_id"], f"verify-capture-{prefix}", lambda prefix=prefix: {"capture": remote_capture(state, html=state["html"], prefix=prefix), "budget": state["budget"]})
        capture = captured["capture"]
        restore_usage(state, captured["budget"])
        state["after"] = capture["evidence"]
        result = verify(
            [f for f in state["findings"] if f.get("approved")],
            state["evidence"],
            state["after"],
            state["facts"],
            state["spec"],
            require_lighthouse=True,
        )
        result.update(id=f"verification-{state.get('revision', 0)}-{attempt}", repair_attempts=attempt, revision=state.get("revision", 0), layout=state["spec"]["layout"])
        state["verification"] = result
        db.save_records(state["tenant"], state["job_id"], "VerificationResult", [result])
        if result["required_checks_passed"] or attempt == 2:
            break
        failed_names = {e.get("name") for e in state["after"] if e["kind"] == "check" and e.get("passed") is False}
        # A bounded layout repair can address visibility/overflow, never missing tools or invented facts.
        next_layout = "compact" if attempt == 0 else "classic"
        if result["missing_checks"] or not failed_names.intersection({"contact_visible", "horizontal_overflow"}):
            break
        if state["spec"]["layout"] == next_layout:
            break
        state["spec"]["layout"] = next_layout
        state["repair_attempts"] = attempt + 1
        render_spec(state)
    check(state)
    db.update_job(
        state["tenant"],
        state["job_id"],
        "needs_review",
        {
            "verification_passed": result["required_checks_passed"],
            "repair_attempts": state["repair_attempts"],
            "elapsed_seconds": state["budget"].get("elapsed_seconds"),
            "budget": state["budget"],
        },
    )
    return state


def traced_node(name, operation):
    def invoke(state: State) -> State:
        started = time.monotonic()
        event = {"id": f"trace-{name}-{state.get('revision', 0)}-{uuid.uuid4()}", "stage": name, "job_id": state["job_id"], "tenant_id": state["tenant"], "revision": state.get("revision", 0)}
        try:
            result = operation(state)
            event["status"] = "succeeded"
            return result
        except Exception as exc:
            event.update(status="failed", error_type=type(exc).__name__)
            raise
        finally:
            event["duration_ms"] = round((time.monotonic()-started)*1000)
            try:
                db.save_records(state["tenant"], state["job_id"], "TraceEvent", [event])
            except psycopg.Error as trace_error:
                event["trace_persistence_error"] = type(trace_error).__name__
            logging.getLogger(__name__).info(__import__("json").dumps(event))
    return invoke


def build_graph(checkpointer=None):
    graph = StateGraph(State)
    graph.add_node("auditor", traced_node("auditor", auditor))
    graph.add_node("designer", traced_node("designer", designer))
    graph.add_node("verifier", traced_node("verifier", verifier))
    graph.add_edge(START, "auditor")
    graph.add_edge("auditor", "designer")
    graph.add_edge("designer", "verifier")
    graph.add_edge("verifier", END)
    return graph.compile(checkpointer=checkpointer)


def run_job(tenant, job_id, action="audit"):
    job = db.get_job(tenant, job_id)
    if not job or job["status"] in ("cancelled", "completed", "failed"):
        return
    revision = job["data"].get("redesign_revision", 0) if action == "redesign" else 0
    with PostgresSaver.from_conn_string(settings.database_url) as saver:
        saver.setup()
        graph = build_graph(saver)
        config = {"configurable": {"thread_id": f"{tenant}:{job_id}:{action}:{revision}"}}
        snapshot = graph.get_state(config)
        if snapshot.values and not snapshot.next and action == "redesign" and job["stage"] == "verifying":
            # Recover a pending verifier even if a legacy state refresh advanced its edge.
            # Successful verification commits needs_review before the graph finishes.
            graph.update_state(config, {}, as_node="designer")
            snapshot = graph.get_state(config)
        if snapshot.values and not snapshot.next:
            return  # Duplicate queue delivery of a completed graph, no repeated paid calls.
        budget = Budget.model_validate(job["data"].get("budget", {}))
        if snapshot.next:
            # Substeps commit usage inside the Auditor node, before the node checkpoint exists.
            # Restore the authoritative durable budget rather than replaying its older checkpoint value.
            predecessor = {"auditor": START, "designer": "auditor", "verifier": "designer"}[snapshot.next[0]]
            graph.update_state(config, {"budget": budget.model_dump(), "started": time.time(), "prior_elapsed": budget.elapsed_seconds}, as_node=predecessor)
        initial = (
            None
            if snapshot.next
            else {
                "tenant": tenant,
                "job_id": job_id,
                "action": action,
                "revision": revision,
                "started": time.time(),
                "prior_elapsed": budget.elapsed_seconds,
                "budget": budget.model_dump(),
                "repair_attempts": 0,
            }
        )
        graph.invoke(initial, config)
