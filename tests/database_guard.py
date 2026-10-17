"""Prevent destructive test fixtures from using an application database."""
from pathlib import Path
from sqlalchemy.engine import make_url


def ensure_test_database(url,allowed=False):
    parsed=make_url(url)
    if parsed.get_backend_name()=='sqlite' and parsed.database in (None,'',':memory:'):return
    name=Path(parsed.database or '').name
    test_name=name.startswith('test_') or name.endswith(('_test','_test.db','_test.sqlite'))
    if not allowed or not test_name:
        raise RuntimeError('Banco de testes recusado: a suíte apaga tabelas. Use banco exclusivo test_* ou *_test e BETHUNTER_ALLOW_TEST_DB_RESET=1. Nunca utilize o banco da aplicação.')
