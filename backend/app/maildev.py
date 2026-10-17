"""Loopback/private-network SMTP capture for development. Never forwards mail."""
import argparse,asyncio,os,secrets
from pathlib import Path

async def connection(reader,writer,directory):
    async def reply(value):writer.write((value+'\r\n').encode());await writer.drain()
    try:
        await reply('220 BetHunter LOCAL CAPTURE ONLY')
        envelope=[];message=None
        for _ in range(100):
            line=await asyncio.wait_for(reader.readline(),60)
            if not line:break
            command=line.decode('utf-8',errors='replace').strip();verb=command.split(' ',1)[0].upper()
            if verb in ('EHLO','HELO'):await reply('250-bethunter.local\r\n250-SMTPUTF8\r\n250-8BITMIME\r\n250 SIZE 1000000')
            elif verb in ('MAIL','RCPT'):envelope.append(command);await reply('250 OK local capture')
            elif verb=='DATA':
                await reply('354 End with a dot')
                body=bytearray()
                while True:
                    chunk=await asyncio.wait_for(reader.readline(),60)
                    if not chunk:raise ValueError('incomplete')
                    if chunk in (b'.\r\n',b'.\n'):break
                    if chunk.startswith(b'..'):chunk=chunk[1:]
                    body.extend(chunk)
                    if len(body)>1_000_000:raise ValueError('too large')
                directory.mkdir(parents=True,exist_ok=True,mode=0o700)
                files=list(directory.glob('*.eml'))
                if len(files)>=1000 or sum(file.stat().st_size for file in files)+len(body)>20_000_000:
                    await reply('452 Local capture storage full');continue
                path=directory/(secrets.token_hex(16)+'.eml')
                fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
                with os.fdopen(fd,'wb') as file:file.write(bytes(body))
                await reply('250 Captured locally; NOT DELIVERED TO INTERNET');envelope=[]
            elif verb=='QUIT':await reply('221 Bye');break
            elif verb in ('RSET','NOOP'):envelope=[];await reply('250 OK')
            else:await reply('502 Local capture supports EHLO MAIL RCPT DATA QUIT only')
    except (ValueError,TimeoutError,ConnectionError,asyncio.LimitOverrunError):pass
    finally:
        writer.close()
        try:await writer.wait_closed()
        except ConnectionError:pass

async def serve(host,port,directory):
    slots=asyncio.Semaphore(10)
    async def accept(reader,writer):
        if slots.locked():writer.close();return
        async with slots:await connection(reader,writer,Path(directory))
    server=await asyncio.start_server(accept,host,port,limit=1_010_000)
    async with server:await server.serve_forever()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=1025);parser.add_argument('--directory',default='mail-capture');parser.add_argument('--inbox',action='store_true')
    args=parser.parse_args()
    if args.inbox:
        print('CAIXA LOCAL DE TESTE; não entregue para a internet. Links são privados.')
        for file in sorted(Path(args.directory).glob('*.eml'),key=lambda f:f.stat().st_mtime)[-20:]:
            from email import policy
            from email.parser import BytesParser
            mail=BytesParser(policy=policy.default).parsebytes(file.read_bytes());body=mail.get_body(preferencelist=('plain',))
            print(str(mail['Subject'])+'\n'+(body.get_content() if body else '')+'\n')
    else:asyncio.run(serve(args.host,args.port,args.directory))
