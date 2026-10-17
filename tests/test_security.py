import asyncio
from unittest.mock import AsyncMock
import httpx
import pytest
from app import network

@pytest.mark.parametrize('value',['localhost','http://127.0.0.1','https://[::1]','http://a.local','ftp://example.org','http://user:pass@example.org','https://example.org:8080','https://example.org:0','https://example.org\\@127.0.0.1','https://example.org\n','http://169.254.169.254','http://2130706433','http://a.invalid','http://example.org:bad'])
def test_normalize_rejects(value):
    with pytest.raises(ValueError): network.normalize(value)

@pytest.mark.parametrize('ip',['127.0.0.1','10.0.0.1','172.16.0.1','192.168.1.1','169.254.169.254','0.0.0.0','100.64.0.1','192.0.2.1','224.0.0.1','::1','fe80::1','fc00::1','::ffff:127.0.0.1','2002:7f00:1::'])
def test_reserved_ips(ip):
    assert not network.public_ip(ip)

def test_normalization_idn():
    assert network.normalize('HTTPS://EXAMPLE.ORG/path')=='example.org'
    assert network.normalize('café.com.br')=='xn--caf-dma.com.br'

def test_mixed_dns_blocks(monkeypatch):
    class Resolver:
        async def resolve(self,host,kind,lifetime):
            return ['93.184.216.34','127.0.0.1'] if kind=='A' else []
    monkeypatch.setattr(network.dns.asyncresolver,'Resolver',Resolver)
    with pytest.raises(network.UnsafeTarget): asyncio.run(network.resolve('example.org'))

def test_pinning_and_redirect_to_private(monkeypatch):
    requests=[]
    async def handler(request):
        requests.append(request)
        return httpx.Response(302,headers={'location':'http://internal.company.org/'})
    real_client=httpx.AsyncClient
    monkeypatch.setattr(network.httpx,'AsyncClient',lambda **kwargs:real_client(transport=httpx.MockTransport(handler),**kwargs))
    async def resolve(host):
        if host=='internal.company.org': raise network.UnsafeTarget('private')
        return ['93.184.216.34']
    monkeypatch.setattr(network,'resolve',resolve)
    with pytest.raises(network.UnsafeTarget):asyncio.run(network.fetch('https://example.org'))
    assert len(requests)==1
    assert requests[0].url.host=='93.184.216.34'
    assert requests[0].headers['host']=='example.org'
    assert requests[0].extensions['sni_hostname']=='example.org'

def test_redirect_dns_rebinding_revalidated(monkeypatch):
    calls=[]
    async def resolve(host):
        calls.append(host)
        if len(calls)>1: raise network.UnsafeTarget('DNS changed to private')
        return ['93.184.216.34']
    async def handler(request):return httpx.Response(302,headers={'location':'/second'})
    real_client=httpx.AsyncClient
    monkeypatch.setattr(network.httpx,'AsyncClient',lambda **kw:real_client(transport=httpx.MockTransport(handler),**kw))
    monkeypatch.setattr(network,'resolve',resolve)
    with pytest.raises(network.UnsafeTarget):asyncio.run(network.fetch('https://example.org'))
    assert len(calls)==2

def test_response_size_limit(monkeypatch):
    async def handler(request):return httpx.Response(200,content=b'x'*100)
    real_client=httpx.AsyncClient
    monkeypatch.setattr(network.httpx,'AsyncClient',lambda **kw:real_client(transport=httpx.MockTransport(handler),**kw))
    monkeypatch.setattr(network,'resolve',AsyncMock(return_value=['93.184.216.34']))
    with pytest.raises(network.UnsafeTarget):asyncio.run(network.fetch('https://example.org',max_bytes=10))

def test_compressed_response_rejected(monkeypatch):
    import gzip
    async def handler(request):return httpx.Response(200,content=gzip.compress(b'x'*10000),headers={'content-encoding':'gzip'})
    real_client=httpx.AsyncClient
    monkeypatch.setattr(network.httpx,'AsyncClient',lambda **kw:real_client(transport=httpx.MockTransport(handler),**kw))
    monkeypatch.setattr(network,'resolve',AsyncMock(return_value=['93.184.216.34']))
    with pytest.raises(network.UnsafeTarget):asyncio.run(network.fetch('https://example.org'))
