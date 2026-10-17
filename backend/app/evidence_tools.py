"""Owner-scoped comparisons, bounded evidence exports and stored PDF verification."""

import hashlib
import io
import json
from zipfile import ZipFile, ZIP_DEFLATED
from threading import BoundedSemaphore
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from .db import get_db
from .security import current_user, limit
from .models import Analysis, Domain, Case, RawDocument, Report, Audit, now
from .report_queue import snapshot_for

router = APIRouter(prefix="/api")
MAX_EXPORT_BYTES = 20_000_000
MAX_DOCUMENTS = 1000
export_slots = BoundedSemaphore(2)


def own_analysis(db, user, id):
    row = db.scalar(
        select(Analysis).join(Domain).where(Analysis.id == id, Domain.owner_id == user.id)
    )
    if row is None:
        raise HTTPException(404, "Análise não encontrada")
    return row


def comparable(analysis):
    result = analysis.result
    tech = result.get("technical", {})
    reg = result.get("regulation", {})
    context = reg.get("normative_context", {})
    return {
        "ips": sorted(tech.get("ips", [])),
        "tls": tech.get("tls"),
        "http_hops": tech.get("hops", []),
        "content_sha256": tech.get("content_sha256"),
        "content_bytes": tech.get("bytes"),
        "asns": sorted(tech.get("infrastructure", {}).get("asns", [])),
        "prefix": tech.get("infrastructure", {}).get("prefix"),
        "activity": tech.get("activity_context"),
        "terms": sorted(tech.get("matched_terms", [])),
        "operator_signals": sorted(tech.get("operator_signals", [])),
        "collection": tech.get("collection_status"),
        "score": analysis.score,
        "classification": analysis.classification,
        "rule_version": result.get("rule_version"),
        "factors": result.get("factors", []),
        "regulatory_status": reg.get("status"),
        "regulatory_document": reg.get("document_sha256") or context.get("document_sha256"),
        "regulatory_version": context.get("version"),
    }


@router.get("/analyses/{id}/compare")
def compare(
    id: int,
    previous_id: int | None = Query(None, ge=1),
    user=Depends(current_user),
    db=Depends(get_db),
):
    current = own_analysis(db, user, id)
    query = select(Analysis).where(
        Analysis.domain_id == current.domain_id, Analysis.id < current.id
    )
    if previous_id is not None:
        query = query.where(Analysis.id == previous_id)
    previous = db.scalar(query.order_by(Analysis.id.desc()).limit(1))
    if previous is None:
        if previous_id is not None:
            raise HTTPException(404, "Análise anterior não disponível neste domínio")
        return {
            "available": False,
            "reason": "Não há análise anterior deste domínio para comparar",
            "changes": [],
        }
    before = comparable(previous)
    after = comparable(current)
    changes = [
        {"field": key, "before": before[key], "after": after[key]}
        for key in before
        if before[key] != after[key]
    ]
    return {
        "available": True,
        "previous": {"id": previous.id, "created": previous.created},
        "current": {"id": current.id, "created": current.created},
        "score_delta": current.score - previous.score,
        "added_ips": sorted(set(after["ips"]) - set(before["ips"])),
        "removed_ips": sorted(set(before["ips"]) - set(after["ips"])),
        "changes": changes,
        "notice": "Diferenças entre observações próprias. Mudança de IP/CDN ou conteúdo não comprova operador, incidente ou irregularidade.",
    }


def document_ids(value):
    ids = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "raw_document_ids" and isinstance(item, list):
                ids.update(i for i in item if type(i) is int)
            elif key == "document_id" and type(item) is int:
                ids.add(item)
            else:
                ids.update(document_ids(item))
    elif isinstance(value, list):
        for item in value:
            ids.update(document_ids(item))
    return ids


@router.post("/cases/{id}/evidence-export")
def evidence_export(id: int, user=Depends(current_user), db=Depends(get_db)):
    if not export_slots.acquire(blocking=False):
        raise HTTPException(429, "Exportação ocupada; tente novamente")
    try:
        return build_export(id, user, db)
    finally:
        export_slots.release()


def build_export(id, user, db):
    limit(("evidence.export", user.id), 3, 60)
    case = db.scalar(select(Case).where(Case.id == id, Case.owner_id == user.id))
    if case is None:
        raise HTTPException(404, "Caso não encontrado")
    snapshot, _ = snapshot_for(db, case, False)
    checked_records = 0
    for record in snapshot.get("Domínios e histórico", []):
        for evidence in record.get("evidence", []):
            digest = hashlib.sha256(
                json.dumps(evidence["payload"], sort_keys=True).encode()
            ).hexdigest()
            if digest != evidence["sha256"]:
                raise HTTPException(
                    409, "Registro estruturado com hash divergente; exportação interrompida"
                )
            checked_records += 1
    requested = document_ids(snapshot)
    if len(requested) > MAX_DOCUMENTS:
        raise HTTPException(422, "Pacote excede 1.000 documentos; reduza o escopo do caso")
    snapshot_bytes = json.dumps(
        snapshot, ensure_ascii=False, sort_keys=True, default=str, indent=2
    ).encode()
    used = len(snapshot_bytes)
    entries = [("case.json", snapshot_bytes)]
    documents = []
    included = set()
    for identifier in sorted(requested):
        row = db.get(RawDocument, identifier)
        # Official public documents or the owner's data only, even for forged references.
        if row is None or row.owner_id not in (None, user.id):
            continue
        used += len(row.content)
        if used > MAX_EXPORT_BYTES:
            raise HTTPException(422, "Pacote excede 20 MB; reduza o escopo do caso")
        digest = hashlib.sha256(row.content).hexdigest()
        if digest != row.sha256:
            raise HTTPException(409, "Documento com hash divergente; exportação interrompida")
        name = f"documents/{row.id}.bin"
        entries.append((name, row.content))
        included.add(row.id)
        documents.append(
            {
                "id": row.id,
                "path": name,
                "url": row.url,
                "collected": row.collected.isoformat(),
                "media_type": row.media_type,
                "sha256": digest,
            }
        )
    readme = b"BetHunter evidence export. Verify every file listed in manifest.json using SHA-256. Raw .bin files are untrusted content, not executable attachments. The manifest is not digitally signed. case.json states history limits.\n"
    entries.append(("README.txt", readme))
    used += len(readme)
    manifest = {
        "format": "bethunter-evidence-v1",
        "case_id": case.id,
        "exported": now().isoformat(),
        "files": [
            {"path": name, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
            for name, body in entries
        ],
        "structured_records_checked": checked_records,
        "structured_hash_method": "SHA-256 of UTF-8 json.dumps(payload, sort_keys=True) with Python default separators and ensure_ascii=True",
        "documents": documents,
        "unavailable_document_count": len(requested - included),
        "limitations": "Pacote do snapshot limitado, não do histórico integral. SHA-256 detecta mudança de bytes; não há assinatura digital ou prova automática de autoria. Arquivos .bin podem conter HTML não confiável: examine como texto em ambiente apropriado.",
    }
    manifest_bytes = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, default=str, indent=2
    ).encode()
    if used + len(manifest_bytes) > MAX_EXPORT_BYTES:
        raise HTTPException(422, "Pacote excede limite de 20 MB")
    stream = io.BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        for name, body in entries:
            archive.writestr(name, body)
        archive.writestr("manifest.json", manifest_bytes)
    content = stream.getvalue()
    digest = hashlib.sha256(content).hexdigest()
    db.add(
        Audit(
            user_id=user.id,
            action="case.evidence.export",
            details={"case_id": case.id, "files": len(entries), "sha256": digest},
        )
    )
    db.commit()
    return Response(
        content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="bethunter-case-{case.id}-evidence.zip"',
            "X-Evidence-SHA256": digest,
        },
    )


@router.get("/reports/{id}/integrity")
def report_integrity(id: int, user=Depends(current_user), db=Depends(get_db)):
    report = db.scalar(select(Report).join(Case).where(Report.id == id, Case.owner_id == user.id))
    if report is None:
        raise HTTPException(404, "Relatório não encontrado")
    if report.archived:
        return {
            "id": report.id,
            "status": "unavailable",
            "verified": False,
            "reason": "Bytes arquivados; não é possível conferir o PDF nesta instalação",
            "expected_sha256": report.sha256,
        }
    actual = hashlib.sha256(report.content).hexdigest()
    return {
        "id": report.id,
        "status": "verified" if actual == report.sha256 else "mismatch",
        "verified": actual == report.sha256,
        "expected_sha256": report.sha256,
        "actual_sha256": actual,
        "bytes": len(report.content),
        "notice": "Confere somente os bytes preservados do PDF; não comprova veracidade, assinatura ou integridade do arquivo após download.",
    }
