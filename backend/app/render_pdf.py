"""Disposable renderer: limited CPU/address space, no external document resources."""
import json,sys
try:
    import resource
    resource.setrlimit(resource.RLIMIT_CPU,(20,20))
    resource.setrlimit(resource.RLIMIT_AS,(1_000_000_000,1_000_000_000))
except ImportError:pass
from .config import Settings
from .reports import pdf
cfg=Settings(_env_file=None)
raw=sys.stdin.buffer.read(cfg.report_max_snapshot_bytes+1)
if len(raw)>cfg.report_max_snapshot_bytes:raise SystemExit(2)
content=pdf(json.loads(raw))
if len(content)>cfg.report_max_pdf_bytes:raise SystemExit(3)
sys.stdout.buffer.write(content)
