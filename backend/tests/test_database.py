import json
import uuid
from datetime import datetime

from sqlalchemy import func, select

from app.database.models import Device, Incident, Investigation, InvestigationEvidence, Log, Server, Service, ToolExecution
from app.services import log_service
from app.services.seed_service import seed_core, seed_summary


def test_seed_counts_and_relations(db):
    s = seed_summary(db)
    assert s["devices"] >= 100 and s["servers"] == 5 and s["services"] == 6 and s["incidents"] >= 8 and s["logs"] >= 10000
    assert s["historical_incidents"] >= 100 and s["sop_versions"] >= 11
    pc = db.scalar(select(Device).where(Device.hostname == "PC-POLI3-001"))
    sw = db.get(Device, pc.switch_id)
    assert sw.hostname == "SW-POLI3" and pc.unit == "Poli 3" and pc.vlan == 30
    assert db.scalar(select(func.count()).select_from(Log).where(Log.source == "server")) >= 5000
    assert db.scalar(select(func.count()).select_from(Log).where(Log.source == "network")) >= 5000


def test_models_use_uuid_and_timestamps(db):
    for m in (Server, Service, Device, Incident):
        row = db.scalars(select(m).limit(1)).first()
        assert isinstance(row.id, uuid.UUID) and row.created_at and row.updated_at


def test_seed_is_idempotent(db, settings):
    assert seed_core(db, settings.raw_dir) == {"users": 0, "servers": 0, "devices": 0, "services": 0, "incidents": 0}


def test_investigation_row_insertion_and_cascade_relations(db):
    inc = db.scalars(select(Incident).limit(1)).first()
    inv = Investigation(incident_id=inc.id, status="queued", stages={})
    db.add(inv)
    db.flush()
    db.add(
        InvestigationEvidence(
            investigation_id=inv.id, evidence_key="E01", source_type="mcp_tool", evidence_text="x", relevance_score=0.5, tags=["a"]
        )
    )
    db.add(
        ToolExecution(
            investigation_id=inv.id, tool_name="ping_host", arguments={"host": "x"}, result={"ok": 1}, execution_time=1.2, status="success"
        )
    )
    db.commit()
    got = db.get(Investigation, inv.id)
    assert len(got.evidence_items) == 1 and got.tool_executions[0].tool_name == "ping_host" and got.incident.id == inc.id
    for o in (*got.evidence_items, *got.tool_executions, got):
        db.delete(o)
    db.commit()


def test_log_ingestion_validates_and_reports_rejects(db, tmp_path):
    f = tmp_path / "bad.csv"
    f.write_text(
        "timestamp,hostname,service,level,event_type,message,source_ip,metadata\n"
        "2030-01-01 10:00:00,SRV-X,simrs,ERROR,HTTP_TIMEOUT,timeout one,10.0.0.1,{}\n"
        "not-a-date,SRV-X,simrs,ERROR,HTTP_TIMEOUT,bad ts,10.0.0.1,{}\n"
        "2030-01-01 10:00:01,SRV-X,simrs,LOUD,HTTP_TIMEOUT,bad level,10.0.0.1,{}\n"
        "2030-01-01 10:00:02,SRV-X,simrs,INFO,OK,,10.0.0.1,{}\n"
        "2030-01-01 10:00:03,SRV-X,simrs,INFO,OK,bad meta,10.0.0.1,{not json\n",
        encoding="utf-8",
    )
    rep = log_service.ingest_file(db, f)
    assert rep["kind"] == "server" and rep["inserted"] == 1 and rep["rejected"] == 4
    assert {r["row"] for r in rep["rejects"]} == {3, 4, 5, 6}
    again = log_service.ingest_file(db, f)
    assert again["inserted"] == 0 and again["skipped_duplicates"] == 1  # idempotent
    db.query(Log).filter(Log.hostname == "SRV-X").delete()
    db.commit()


def test_log_ingestion_json_network_and_bad_schema(db, tmp_path):
    j = tmp_path / "net.json"
    j.write_text(
        json.dumps(
            [
                {
                    "timestamp": "2031-01-01T00:00:00",
                    "source_device": "PC-X",
                    "destination": "SRV",
                    "protocol": "TCP",
                    "port": "80",
                    "latency_ms": "5",
                    "packet_loss": "0",
                    "status": "ok",
                    "event_type": "PING_OK",
                    "message": "ok",
                },
                {
                    "timestamp": "2031-01-01T00:00:01",
                    "source_device": "PC-X",
                    "destination": "SRV",
                    "protocol": "TCP",
                    "port": "80",
                    "latency_ms": "5",
                    "packet_loss": "150",
                    "status": "ok",
                    "event_type": "PING_OK",
                    "message": "loss out of range",
                },
            ]
        )
    )
    rep = log_service.ingest_file(db, j)
    assert rep["kind"] == "network" and rep["inserted"] == 1 and rep["rejected"] == 1
    db.query(Log).filter(Log.hostname == "PC-X").delete()
    db.commit()
    wrong = tmp_path / "w.csv"
    wrong.write_text("a,b\n1,2\n")
    try:
        log_service.ingest_file(db, wrong)
        raise AssertionError("expected ValueError")
    except ValueError as e:
        assert "unrecognised log schema" in str(e)
    _ = datetime
