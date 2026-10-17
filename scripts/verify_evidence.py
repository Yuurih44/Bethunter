#!/usr/bin/env python3
"""Verify exported bytes offline without extracting or executing raw evidence."""

import argparse
import hashlib
import json
import re
from pathlib import Path
from zipfile import ZipFile, BadZipFile


def verify(path):
    path = Path(path)
    if path.stat().st_size > 24_000_000:
        raise ValueError("Arquivo excede limite de tamanho")
    with ZipFile(path) as archive:
        members = archive.infolist()
        names = [entry.filename for entry in members]
        if len(members) > 1003 or len(set(names)) != len(names):
            raise ValueError("Quantidade de arquivos ou nomes duplicados inválidos")
        if sum(entry.file_size for entry in members) > 20_000_000:
            raise ValueError("Conteúdo expandido excede 20 MB")
        if "manifest.json" not in names or archive.getinfo("manifest.json").file_size > 1_000_000:
            raise ValueError("Manifesto ausente ou grande demais")
        manifest = json.loads(archive.read("manifest.json"))
        if not isinstance(manifest, dict):
            raise ValueError("Manifesto inválido")
        if manifest.get("format") != "bethunter-evidence-v1":
            raise ValueError("Formato não reconhecido")
        listed = manifest.get("files", [])
        if not isinstance(listed, list) or not listed:
            raise ValueError("Manifesto sem arquivos")
        paths = []
        for item in listed:
            if not isinstance(item, dict):
                raise ValueError("Entrada inválida no manifesto")
            name = item.get("path", "")
            if name not in ("case.json", "README.txt") and not re.fullmatch(
                r"documents/[0-9]+\.bin", name
            ):
                raise ValueError("Caminho inesperado no manifesto")
            paths.append(name)
            content = archive.read(name)
            if len(content) != item.get("bytes") or hashlib.sha256(content).hexdigest() != item.get(
                "sha256"
            ):
                raise ValueError("Integridade divergente: " + name)
        if (
            len(set(paths)) != len(paths)
            or set(names) != set(paths) | {"manifest.json"}
            or not {"case.json", "README.txt"} <= set(paths)
        ):
            raise ValueError("Conteúdo não corresponde ao manifesto")
        return {
            "verified": True,
            "files_checked": len(paths),
            "case_id": manifest.get("case_id"),
            "notice": "Hashes conferem com o manifesto fornecido. Sem assinatura digital: não comprova origem, veracidade ou autoria.",
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file")
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.file), ensure_ascii=False))
    except (OSError, ValueError, KeyError, BadZipFile, RuntimeError, TypeError) as exc:
        parser.exit(1, "Verificação falhou: " + str(exc) + "\n")
