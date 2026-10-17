"""Only public HTTPS/HTTP, DNS pinned on every hop; never inherit proxy env."""
import asyncio
import ipaddress
import re
import ssl
from urllib.parse import urlsplit, urljoin
import dns.asyncresolver
import httpx

MAX_BYTES = 512_000
semaphore = asyncio.Semaphore(4)

class UnsafeTarget(ValueError):
    pass

def normalize(value: str) -> str:
    if len(value) > 2048 or any(ord(c) < 33 for c in value) or "\\" in value:
        raise UnsafeTarget("URL inválida")
    p = urlsplit(value if "://" in value else "https://"+value)
    if p.scheme not in ("http", "https") or p.username or p.password or not p.hostname:
        raise UnsafeTarget("Somente domínios HTTP(S), sem credenciais")
    if p.port is not None and p.port != (443 if p.scheme == "https" else 80):
        raise UnsafeTarget("Porta não permitida")
    host = p.hostname.rstrip(".").encode("idna").decode().lower()
    if len(host) > 253 or "." not in host or not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in host.split(".")):
        raise UnsafeTarget("Domínio inválido")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise UnsafeTarget("Informe um domínio, não um IP")
    if host.endswith((".localhost", ".local", ".internal", ".test", ".invalid", ".example")):
        raise UnsafeTarget("Domínio reservado")
    return host

def public_ip(ip):
    address = ipaddress.ip_address(ip)
    return address.is_global and not address.is_multicast and not address.is_reserved and not (address.version == 6 and (address.ipv4_mapped or address.sixtofour or address.teredo))

async def resolve(host):
    ips = []
    resolver = dns.asyncresolver.Resolver()
    for kind in ("A", "AAAA"):
        try:
            answer = await resolver.resolve(host, kind, lifetime=3)
            ips.extend(str(x) for x in answer)
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            continue
    if not ips or any(not public_ip(ip) for ip in ips):
        raise UnsafeTarget("DNS sem destino público seguro")
    return sorted(set(ips))

async def fetch(url, max_bytes=MAX_BYTES, allowed_hosts=None, https_only=False):
    hops = []
    # Pool origins are the pinned IP, not the original hostname. Disable reuse so
    # different virtual hosts sharing an IP always get their own SNI/TLS check.
    async with httpx.AsyncClient(timeout=httpx.Timeout(8), trust_env=False, follow_redirects=False,
                                 limits=httpx.Limits(max_keepalive_connections=0)) as client:
        for _ in range(5):
            host = normalize(url)
            p = urlsplit(url)
            if allowed_hosts is not None and host not in allowed_hosts:
                raise UnsafeTarget('Host da fonte/redirecionamento não autorizado')
            if https_only and p.scheme != 'https':
                raise UnsafeTarget('Fonte exige HTTPS em todos os saltos')
            ips = await resolve(host)
            ip = ips[0]
            authority = f"[{ip}]" if ":" in ip else ip
            pinned = f"{p.scheme}://{authority}{p.path or '/'}" + ("?"+p.query if p.query else "")
            async with client.stream("GET", pinned, headers={"Host":host,"User-Agent":"BetHunter/1.0 (public research)","Accept-Encoding":"identity"}, extensions={"sni_hostname":host}) as response:
                hops.append({"url":url,"ip":ip,"status":response.status_code})
                if response.status_code in (301,302,303,307,308):
                    url = urljoin(url, response.headers.get("location", ""))
                    continue
                response.raise_for_status()
                if response.headers.get("content-encoding", "identity").lower() not in ("identity", ""):
                    raise UnsafeTarget("Conteúdo comprimido não permitido na coleta limitada")
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > max_bytes:
                        raise UnsafeTarget("Resposta excede limite")
                return bytes(data), hops, dict(response.headers)
    raise UnsafeTarget("Limite de redirecionamentos excedido")

async def certificate(host, ip):
    writer = None
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(ip,443,ssl=ssl.create_default_context(),server_hostname=host), timeout=6)
        cert = writer.get_extra_info("ssl_object").getpeercert()
        return {"issuer":str(cert.get("issuer")), "notBefore":cert.get("notBefore"), "notAfter":cert.get("notAfter"), "subjectAltName":cert.get("subjectAltName", [])}
    finally:
        if writer:
            writer.close()
            await writer.wait_closed()
