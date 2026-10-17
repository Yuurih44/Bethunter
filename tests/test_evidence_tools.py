import hashlib, io, json
import importlib.util
from pathlib import Path
import pytest
from zipfile import ZipFile
from datetime import timedelta
from sqlalchemy import select, func
from app.db import SessionLocal
from app.models import User, Domain, Analysis, Case, CaseDomain, RawDocument, Report, Audit, now
from app.reports import report_html, TEMPLATE_VERSION
from app.report_queue import snapshot_for, queue_report, tick_reports
import asyncio


def setup_case(db):
    owner = db.scalar(select(User))
    domain = Domain(owner_id=owner.id, name="evidence.example.org")
    db.add(domain)
    db.flush()
    case = Case(owner_id=owner.id, title="Investigação técnica de teste")
    db.add(case)
    db.flush()
    db.add(CaseDomain(case_id=case.id, domain_id=domain.id))
    db.flush()
    return owner, domain, case


def test_compare_detects_changes_and_rejects_other_domain(auth):
    with SessionLocal() as db:
        owner, domain, _ = setup_case(db)
        previous = Analysis(
            domain_id=domain.id,
            score=10,
            classification="Requer investigação",
            result={
                "technical": {
                    "ips": ["1.1.1.1"],
                    "tls": {"notAfter": "2026"},
                    "content_sha256": "a" * 64,
                }
            },
        )
        current = Analysis(
            domain_id=domain.id,
            score=25,
            classification="Requer investigação",
            result={
                "technical": {
                    "ips": ["8.8.8.8"],
                    "tls": {"notAfter": "2027"},
                    "content_sha256": "b" * 64,
                }
            },
        )
        other = Domain(owner_id=owner.id, name="other.example.org")
        db.add(other)
        db.flush()
        foreign = Analysis(domain_id=other.id, score=0, classification="Fixture", result={})
        db.add_all([previous, current, foreign])
        db.commit()
        ids = (previous.id, current.id, foreign.id)
    data = auth.get(f"/api/analyses/{ids[1]}/compare").json()
    assert data["available"] and data["score_delta"] == 15
    assert data["added_ips"] == ["8.8.8.8"] and data["removed_ips"] == ["1.1.1.1"]
    assert {"ips", "tls", "content_sha256", "score"} <= {c["field"] for c in data["changes"]}
    assert auth.get(f"/api/analyses/{ids[1]}/compare?previous_id={ids[2]}").status_code == 404
    assert auth.get(f"/api/analyses/{ids[0]}/compare").json()["available"] is False


def test_evidence_export_manifest_matches_bytes_and_is_audited(auth, tmp_path):
    with SessionLocal() as db:
        owner, domain, case = setup_case(db)
        content = b"<html>explicit synthetic evidence</html>"
        document = RawDocument(
            owner_id=owner.id,
            url="https://evidence.example.org/",
            sha256=hashlib.sha256(content).hexdigest(),
            content=content,
            media_type="text/html",
        )
        db.add(document)
        db.flush()
        from app.models import Evidence

        analysis = Analysis(
            domain_id=domain.id,
            score=25,
            classification="Fixture",
            result={"raw_document_ids": [document.id], "technical": {}},
        )
        db.add(analysis)
        db.flush()
        payload = {"domain": domain.name, "fixture": True}
        db.add(
            Evidence(
                analysis_id=analysis.id,
                sha256=hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
                payload=payload,
            )
        )
        db.commit()
        identifier = case.id
    response = auth.post(f"/api/cases/{identifier}/evidence-export")
    assert response.status_code == 200, response.text
    assert hashlib.sha256(response.content).hexdigest() == response.headers["x-evidence-sha256"]
    with ZipFile(io.BytesIO(response.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert (
            manifest["unavailable_document_count"] == 0
            and manifest["structured_records_checked"] == 1
        )
        for item in manifest["files"]:
            assert hashlib.sha256(archive.read(item["path"])).hexdigest() == item["sha256"]
        assert any(name.endswith(".bin") for name in archive.namelist())
        assert json.loads(archive.read("case.json"))["Modelo do relatório"] == TEMPLATE_VERSION
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(Audit)
                .where(Audit.action == "case.evidence.export")
            )
            == 1
        )
    file = tmp_path / "evidence.zip"
    file.write_bytes(response.content)
    module = Path(__file__).resolve().parents[1] / "scripts/verify_evidence.py"
    spec = importlib.util.spec_from_file_location("verify_evidence", module)
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    assert verifier.verify(file)["verified"]
    with ZipFile(file, "a") as archive:
        archive.writestr("unexpected.txt", b"changed fixture")
    with pytest.raises(ValueError):
        verifier.verify(file)


def test_exports_and_comparison_do_not_leak_another_owner(auth):
    with SessionLocal() as db:
        owner, domain, case = setup_case(db)
        other = User(email="evidence-other@example.org", password="unused", role="analyst")
        db.add(other)
        db.flush()
        secret = b"other owner fixture"
        document = RawDocument(
            owner_id=other.id,
            url="https://private.example.org/",
            sha256=hashlib.sha256(secret).hexdigest(),
            content=secret,
        )
        db.add(document)
        db.flush()
        own = Analysis(
            domain_id=domain.id,
            score=0,
            classification="Fixture",
            result={"raw_document_ids": [document.id]},
        )
        db.add(own)
        foreign_case = Case(owner_id=other.id, title="Outro caso")
        foreign_domain = Domain(owner_id=other.id, name="private.example.org")
        db.add_all([foreign_case, foreign_domain])
        db.flush()
        foreign_analysis = Analysis(
            domain_id=foreign_domain.id, score=0, classification="Fixture", result={}
        )
        db.add(foreign_analysis)
        db.commit()
        ids = (case.id, foreign_case.id, foreign_analysis.id)
    assert auth.post(f"/api/cases/{ids[1]}/evidence-export").status_code == 404
    assert auth.get(f"/api/analyses/{ids[2]}/compare").status_code == 404
    with ZipFile(io.BytesIO(auth.post(f"/api/cases/{ids[0]}/evidence-export").content)) as archive:
        assert not any(name.startswith("documents/") for name in archive.namelist())
        assert json.loads(archive.read("manifest.json"))["unavailable_document_count"] == 1


def test_export_rejects_corrupt_document_and_size_overflow(auth, monkeypatch):
    with SessionLocal() as db:
        owner, domain, case = setup_case(db)
        document = RawDocument(
            owner_id=owner.id,
            url="https://evidence.example.org/",
            sha256="a" * 64,
            content=b"changed fixture",
        )
        db.add(document)
        db.flush()
        db.add(
            Analysis(
                domain_id=domain.id,
                score=0,
                classification="Fixture",
                result={"raw_document_ids": [document.id]},
            )
        )
        db.commit()
        identifier = case.id
    assert auth.post(f"/api/cases/{identifier}/evidence-export").status_code == 409
    monkeypatch.setattr("app.evidence_tools.MAX_EXPORT_BYTES", 1)
    assert auth.post(f"/api/cases/{identifier}/evidence-export").status_code == 422


def test_report_integrity_detects_changes_archiving_and_owner(auth):
    with SessionLocal() as db:
        _, _, case = setup_case(db)
        body = b"%PDF synthetic fixture"
        report = Report(
            case_id=case.id, sha256=hashlib.sha256(body).hexdigest(), snapshot={}, content=body
        )
        db.add(report)
        db.commit()
        identifier = report.id
    assert auth.get(f"/api/reports/{identifier}/integrity").json()["verified"]
    with SessionLocal() as db:
        db.get(Report, identifier).content = b"changed"
        db.commit()
    assert auth.get(f"/api/reports/{identifier}/integrity").json()["status"] == "mismatch"
    with SessionLocal() as db:
        db.get(Report, identifier).archived = True
        db.commit()
    assert auth.get(f"/api/reports/{identifier}/integrity").json()["status"] == "unavailable"


def test_technical_html_escapes_input_and_real_pdf_contains_snapshot(auth):
    with SessionLocal() as db:
        owner, domain, case = setup_case(db)
        case.notes = "<script>alert(1)</script>"
        db.add(
            Analysis(
                domain_id=domain.id,
                score=25,
                classification="Fixture",
                result={
                    "technical": {
                        "ips": ["1.1.1.1"],
                        "tls": {"issuer": "fixture CA"},
                        "hops": [
                            {"url": "https://evidence.example.org/", "ip": "1.1.1.1", "status": 200}
                        ],
                    },
                    "factors": [
                        {"key": "betting_content", "weight": 25, "explanation": "fixture only"}
                    ],
                    "regulation": {"status": "not_verified"},
                    "errors": [],
                    "limitations": ["Fixture only"],
                },
                review="Parecer humano de teste",
            )
        )
        db.flush()
        snapshot, _ = snapshot_for(db, case, False)
        html = report_html(snapshot)
        assert "<script>" not in html and "&lt;script&gt;" in html
        for text in [
            "Certificado TLS",
            "Cadeia HTTP observada",
            "Fatores da prioridade",
            "SHA-256",
            "Revisão humana",
            "Histórico das verificações",
        ]:
            assert text in html
        job = queue_report(db, case, owner.id)
        db.commit()
        identifier = job.id
    assert asyncio.run(tick_reports())
    from app.models import ReportJob

    with SessionLocal() as db:
        job = db.get(ReportJob, identifier)
        assert job.status == "done", job.error
        report = db.get(Report, job.report_id)
        assert report.content.startswith(b"%PDF")
        assert report.snapshot["Modelo do relatório"] == TEMPLATE_VERSION


def test_export_rejects_corrupt_structured_record(auth):
    from app.models import Evidence

    with SessionLocal() as db:
        _, domain, case = setup_case(db)
        analysis = Analysis(domain_id=domain.id, score=0, classification="Fixture", result={})
        db.add(analysis)
        db.flush()
        db.add(Evidence(analysis_id=analysis.id, sha256="a" * 64, payload={"changed": "fixture"}))
        db.commit()
        identifier = case.id
    assert auth.post(f"/api/cases/{identifier}/evidence-export").status_code == 409


def test_report_template_upgrade_does_not_reuse_previous_fingerprint(auth, monkeypatch):
    with SessionLocal() as db:
        _, _, case = setup_case(db)
        _, before = snapshot_for(db, case, False)
        monkeypatch.setattr("app.report_queue.TEMPLATE_VERSION", "technical-template-fixture-next")
        snapshot, after = snapshot_for(db, case, False)
        assert (
            before != after and snapshot["Modelo do relatório"] == "technical-template-fixture-next"
        )
