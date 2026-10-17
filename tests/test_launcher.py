import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('bethunter_local_launcher',Path(__file__).parents[1]/'scripts/local.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def test_launcher_detects_sandbox(monkeypatch):
    def blocked(*args,**kwargs):
        raise PermissionError('Operation not permitted')
    monkeypatch.setattr(launcher.socket,'socket',blocked)
    with pytest.raises(RuntimeError,match='terminal normal'):
        launcher.check_ports()


def test_launcher_does_not_treat_missing_process_as_alive(monkeypatch):
    monkeypatch.setattr(launcher,'start_stamp',lambda pid:None)
    assert not launcher.alive({'pid':123,'stamp':None})
    assert not launcher.alive({'pid':123,'stamp':'old'})


def test_launcher_preserves_configuration_and_protects_secret(tmp_path,monkeypatch):
    monkeypatch.setattr(launcher,'RUNTIME',tmp_path/'runtime')
    first=launcher.configure()
    second=launcher.configure()
    assert first['DATABASE_URL']==second['DATABASE_URL']
    assert first['AUTH_ENCRYPTION_KEY']==second['AUTH_ENCRYPTION_KEY']
    from cryptography.fernet import Fernet
    Fernet(first['AUTH_ENCRYPTION_KEY'].encode())
    assert len(first['BETHUNTER_DB_PASSWORD'])==48
    assert (launcher.RUNTIME/'local.env').stat().st_mode & 0o777 == 0o600
    assert launcher.RUNTIME.stat().st_mode & 0o777 == 0o700
    assert first['ORIGIN']=='http://localhost:8080'


def test_source_identity_changes_with_source_and_not_pycache(tmp_path):
    import sys
    sys.path.insert(0,str(Path(__file__).parents[1]/'backend'))
    from app.build import source_id
    p=tmp_path/'app.py';p.write_text('version=1')
    first=source_id(tmp_path)
    (tmp_path/'cache.pyc').write_bytes(b'bytecode')
    assert source_id(tmp_path)==first
    p.write_text('version=2')
    assert source_id(tmp_path)!=first


def test_old_backend_is_not_accepted_as_current(monkeypatch):
    import io
    class Opener:
        def open(self,*args,**kwargs):return io.StringIO('{"build_id":"old"}')
    monkeypatch.setattr(launcher.urllib.request,'build_opener',lambda *a:Opener())
    monkeypatch.setattr(launcher,'expected_build',lambda:'new')
    assert launcher.current_backend() is False


def test_current_backend_is_accepted(monkeypatch):
    import io
    class Opener:
        def open(self,*args,**kwargs):return io.StringIO('{"build_id":"new"}')
    monkeypatch.setattr(launcher.urllib.request,'build_opener',lambda *a:Opener())
    monkeypatch.setattr(launcher,'expected_build',lambda:'new')
    assert launcher.current_backend() is True


def test_launcher_restarts_outdated_owned_services(monkeypatch):
    calls=[]
    monkeypatch.setattr(launcher.os,'geteuid',lambda:1000)
    monkeypatch.setattr(launcher,'records',lambda:{'backend':{'pid':1},'worker':{'pid':2},'frontend':{'pid':3}})
    monkeypatch.setattr(launcher,'alive',lambda record:True)
    monkeypatch.setattr(launcher,'health',lambda url:True)
    monkeypatch.setattr(launcher,'current_backend',lambda:False)
    monkeypatch.setattr(launcher,'stop',lambda:calls.append('stop'))
    def halt():
        calls.append('preflight')
        raise RuntimeError('test stops before installation')
    monkeypatch.setattr(launcher,'check_ports',halt)
    with pytest.raises(RuntimeError,match='test stops'):
        launcher.start()
    assert calls==['stop','preflight']


def test_port_check_accepts_reusable_recently_closed_listener(monkeypatch):
    ports=[]
    class FakeSocket:
        def __init__(self,*args):self.reuse=False
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def setsockopt(self,level,option,value):
            if level==launcher.socket.SOL_SOCKET and option==launcher.socket.SO_REUSEADDR and value==1:
                self.reuse=True
        def bind(self,address):
            if not self.reuse:raise OSError(98,'Address already in use: TIME_WAIT')
            ports.append(address[1])
    monkeypatch.setattr(launcher.socket,'socket',FakeSocket)
    launcher.check_ports()
    assert ports==[55432,8000,8080,1025]


def test_port_check_still_rejects_live_listener(monkeypatch):
    class BusySocket:
        def __init__(self,*args):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def setsockopt(self,*args):pass
        def bind(self,address):raise OSError(98,'Address already in use')
    monkeypatch.setattr(launcher.socket,'socket',BusySocket)
    with pytest.raises(RuntimeError,match='Porta 55432 indisponível'):
        launcher.check_ports()
