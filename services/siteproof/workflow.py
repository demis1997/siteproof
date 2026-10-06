import time
import uuid
from typing import TypedDict

import httpx
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
        return {"findings": findings, "run": run, "budget": budget.model_dump()}

    diagnosed = once(state["tenant"], state["job_id"], "findings-v2", diagnose, paid=settings.mode == "live")
    findings, run = diagnosed["findings"], diagnosed["run"]
    run = dict(
        run,
        retrieval_strategy="hybrid" if embedding is not None else "keyword",
        embedding_identity=embedding_identity() if embedding is not None else None,
        retrieved_guidance_ids=[g["id"] for g in guidance],
    )
    db.save_records(state["tenant"], state["job_id"], "ModelRun", [dict(run, id="audit-model")])
    # Restore the pre-call budget on replay; charge the persisted result exactly once.
    state["budget"] = diagnosed["budget"]
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
            "versions": {"prompt": "auditor-v2", "guidance": "guidance-v1", "renderer": "components-v1"},
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
                "id": "redesign",
                "spec": state["spec"],
                "html": state["html"],
                "version": "components-v1",
                "revision": state.get("revision", 0),
                "repair_attempts": state.get("repair_attempts", 0),
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
        about=" ".join(headings[1:3]) or "Contact us to discuss the services listed on our original website.",
        services=[f["value"] for f in state["facts"] if f["kind"] == "service"],
        details=[f["value"] for f in state["facts"] if f["kind"] in ("hours", "price")],
        contacts=contacts,
        fixture=settings.mode == "fixture",
    )
    if settings.mode == "live":
        spec, run = provider().design(
            spec,
            state["facts"],
            [f for f in state["findings"] if f.get("approved")],
            Budget.model_validate(state["budget"]),
        )
        record_run(state, run)
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
        capture = remote_capture(state, html=state["html"], prefix=prefix)
        state["after"] = capture["evidence"]
        result = verify(
            [f for f in state["findings"] if f.get("approved")],
            state["evidence"],
            state["after"],
            state["facts"],
            state["spec"],
        )
        result.update(id="verification", repair_attempts=attempt, revision=state.get("revision", 0))
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


def build_graph(checkpointer=None):
    graph = StateGraph(State)
    graph.add_node("auditor", auditor)
    graph.add_node("designer", designer)
    graph.add_node("verifier", verifier)
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
        if snapshot.values and not snapshot.next:
            return  # Duplicate queue delivery of a completed graph, no repeated paid calls.
        budget = Budget.model_validate(job["data"].get("budget", {}))
        if snapshot.next:
            # Substeps commit usage inside the Auditor node, before the node checkpoint exists.
            # Restore the authoritative durable budget rather than replaying its older checkpoint value.
            graph.update_state(config, {"budget": budget.model_dump()})
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
