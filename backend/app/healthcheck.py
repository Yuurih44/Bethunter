"""Worker liveness from its own persisted heartbeat; no fabricated health state."""
from .db import SessionLocal
from .models import SystemSchedule,now
with SessionLocal() as db:
    pulse=db.get(SystemSchedule,'worker_heartbeat')
    if not pulse or pulse.next_run.replace(tzinfo=now().tzinfo)<now():raise SystemExit(1)
print('worker heartbeat current')
