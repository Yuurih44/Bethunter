"""Public enrichment adapters. Configuration errors never become findings."""
import asyncio
import hashlib
import json
from typing import Protocol
from urllib.parse import urlencode
from . import network
from .models import now

class InfrastructureProvider(Protocol):
    async def lookup(self, ip: str) -> dict: ...

class RIPEstatProvider:
    async def lookup(self, ip: str) -> dict:
        if not network.public_ip(ip):
            raise network.UnsafeTarget('ASN requer endereço público')
        url='https://stat.ripe.net/data/network-info/data.json?'+urlencode({'resource':ip})
        raw, hops, headers=await asyncio.wait_for(network.fetch(url),20)
        payload=json.loads(raw)
        if payload.get('status')!='ok' or not isinstance(payload.get('data',{}).get('asns'),list):
            raise ValueError('Formato RIPEstat não reconhecido')
        data=payload['data']
        out={'ip':ip,'asns':data['asns'],'prefix':data.get('prefix'),'source':url,'collected':now().isoformat(),'source_sha256':hashlib.sha256(raw).hexdigest(),'holders':[], 'limitation':'ASN anunciante de rota não identifica necessariamente o provedor de hospedagem ou operador do site.'}
        if data.get('prefix'):
            detail_url='https://stat.ripe.net/data/prefix-overview/data.json?'+urlencode({'resource':data['prefix']})
            try:
                raw, _, _=await asyncio.wait_for(network.fetch(detail_url),20)
                detail=json.loads(raw)
                if detail.get('status')=='ok':
                    out['holders']=detail.get('data',{}).get('asns',[])
                    out['holder_source']=detail_url
                    out['holder_source_sha256']=hashlib.sha256(raw).hexdigest()
            except Exception as exc:
                out['holder_error']=type(exc).__name__
        return out
