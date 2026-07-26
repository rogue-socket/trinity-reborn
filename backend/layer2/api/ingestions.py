import hashlib
import json
import uuid
from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.layer2.contracts.layer1 import Layer1Package, SUPPORTED_SCHEMA_VERSION
from backend.shared.db import get_session
from backend.layer2.models import IngestionRun, RawPackage, RejectedPackage, Topic, TopicLifecycleTransition
from backend.layer2.policy import GRAPH_MODEL_VERSION, ONTOLOGY_VERSION, PIPELINE_VERSION
from backend.layer2.services.canonicalization import materialize_new_canonical_objects
from backend.layer2.services.mentions import persist_accepted_mentions
from backend.layer2.services.validation import validate_objects

router = APIRouter(tags=["ingestions"])


def report_for(run: IngestionRun, raw_package: RawPackage, topic: Topic) -> dict:
    return {
        "ingestion_id": str(run.id),
        "package_id": str(raw_package.package_id),
        "topic_id": str(topic.id),
        "status": run.status,
        "input_schema_version": run.input_schema_version,
        "pipeline_version": run.pipeline_version,
        "graph_model_version": run.graph_model_version,
        "ontology_version": run.ontology_version,
        "processing_duration_ms": run.report_json.get("processing_duration_ms"),
        "summary": run.report_json["summary"],
        "object_results": run.report_json["object_results"],
        "warnings": run.report_json["warnings"],
        "errors": run.report_json["errors"],
    }


def store_rejected_package(session: Session, raw_body: bytes, errors: object) -> None:
    try:
        envelope = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        envelope = {}
    schema_version = envelope.get("schema_version") if isinstance(envelope, dict) else None
    topic_key = envelope.get("topic_key") if isinstance(envelope, dict) else None
    package_id = envelope.get("package_id") if isinstance(envelope, dict) else None
    try:
        parsed_package_id = uuid.UUID(package_id) if package_id else None
    except (TypeError, ValueError):
        parsed_package_id = None
    session.add(
        RejectedPackage(
            package_id=parsed_package_id,
            schema_version=schema_version if isinstance(schema_version, str) else None,
            topic_key=topic_key if isinstance(topic_key, str) else None,
            payload_bytes=raw_body,
            payload_checksum=hashlib.sha256(raw_body).hexdigest(),
            report_json={"status": "rejected", "errors": errors},
        )
    )
    session.commit()


@router.post("/ingestions", status_code=status.HTTP_201_CREATED)
async def ingest(
    request: Request, response: Response, session: Session = Depends(get_session)
) -> dict:
    processing_started = perf_counter()
    raw_body = await request.body()
    try:
        package = Layer1Package.model_validate_json(raw_body)
    except ValidationError as error:
        details = [
            {"loc": [str(part) for part in item["loc"]], "message": item["msg"], "type": item["type"]}
            for item in error.errors()
        ]
        store_rejected_package(session, raw_body, details)
        raise HTTPException(status_code=400, detail=details)

    if package.schema_version != SUPPORTED_SCHEMA_VERSION:
        store_rejected_package(
            session,
            raw_body,
            [f"unsupported schema_version; supported versions: {SUPPORTED_SCHEMA_VERSION}"],
        )
        raise HTTPException(
            status_code=400,
            detail=f"unsupported schema_version; supported versions: {SUPPORTED_SCHEMA_VERSION}",
        )

    topic = session.scalar(select(Topic).where(Topic.topic_key == package.topic_key))
    if topic is None:
        store_rejected_package(session, raw_body, ["unknown topic_key"])
        raise HTTPException(status_code=404, detail="unknown topic_key")

    should_reopen_topic = topic.status == "closed"

    session.execute(select(func.pg_advisory_xact_lock(func.hashtext(str(topic.id)))))
    checksum = hashlib.sha256(raw_body).hexdigest()
    retry = session.scalar(
        select(RawPackage).where(
            RawPackage.package_id == package.package_id,
            RawPackage.schema_version == package.schema_version,
            RawPackage.payload_checksum == checksum,
        )
    )
    if retry is not None:
        run = session.scalar(select(IngestionRun).where(IngestionRun.raw_package_id == retry.id))
        if run is None:
            raise HTTPException(status_code=500, detail="package retry has no ingestion report")
        if should_reopen_topic:
            session.add(
                TopicLifecycleTransition(
                    topic_id=topic.id,
                    ingestion_id=run.id,
                    from_status="closed",
                    to_status="active",
                    reason="New Layer 1 package received.",
                )
            )
            topic.status = "active"
            session.commit()
        response.status_code = status.HTTP_200_OK
        return report_for(run, retry, topic)

    revision = (
        session.scalar(
            select(func.max(RawPackage.revision)).where(
                RawPackage.package_id == package.package_id,
                RawPackage.schema_version == package.schema_version,
            )
        )
        or 0
    ) + 1

    payload = json.loads(raw_body)
    validation = validate_objects(payload)
    raw_package = RawPackage(
        package_id=package.package_id,
        schema_version=package.schema_version,
        topic_id=topic.id,
        payload=payload,
        payload_bytes=raw_body,
        payload_checksum=checksum,
        revision=revision,
    )
    session.add(raw_package)
    session.flush()
    persist_accepted_mentions(session, raw_package, payload, validation.report)
    run = IngestionRun(
        raw_package_id=raw_package.id,
        status=validation.status,
        input_schema_version=package.schema_version,
        pipeline_version=PIPELINE_VERSION,
        graph_model_version=GRAPH_MODEL_VERSION,
        ontology_version=ONTOLOGY_VERSION,
        report_json=validation.report,
    )
    session.add(run)
    session.flush()
    if should_reopen_topic:
        session.add(
            TopicLifecycleTransition(
                topic_id=topic.id,
                ingestion_id=run.id,
                from_status="closed",
                to_status="active",
                reason="New Layer 1 package received.",
            )
        )
        topic.status = "active"
    run.report_json = materialize_new_canonical_objects(
        session, raw_package, run, topic.id, validation.report
    )
    run.report_json["processing_duration_ms"] = int((perf_counter() - processing_started) * 1000)
    session.commit()
    session.refresh(run)
    if validation.status == "rejected":
        response.status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    return report_for(run, raw_package, topic)
