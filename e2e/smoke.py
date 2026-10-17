"""Real browser/API/worker smoke against a disposable Compose deployment."""
import hashlib,os,re,time
from pathlib import Path
import pyotp
from playwright.sync_api import sync_playwright,expect

if os.getenv('BETHUNTER_E2E')!='1':raise SystemExit('Use somente no deployment descartável de E2E')
base=os.getenv('E2E_ORIGIN','http://localhost:8080')
password=os.environ['E2E_PASSWORD']
with sync_playwright() as p:
    browser=p.chromium.launch()
    context=browser.new_context(accept_downloads=True)
    page=context.new_page();errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base);page.get_by_label('Email',exact=True).fill('e2e@example.org');page.get_by_label('Senha',exact=True).fill(password)
    page.get_by_role('button',name='Entrar no workspace').click()
    expect(page.get_by_role('heading',name='Central de operações')).to_be_visible()
    page.get_by_role('link',name='Domínios',exact=True).click();expect(page.get_by_text('Página 1 de 2 · 55 registros')).to_be_visible()
    page.get_by_role('button',name='Próxima',exact=True).click();expect(page.get_by_text('Página 2 de 2 · 55 registros')).to_be_visible()
    page.get_by_role('link',name='Investigações',exact=True).click();page.get_by_role('button',name='Abrir caso').click()
    form=page.locator('form.case-form');form.get_by_label('Título',exact=True).fill('Caso E2E — demonstração')
    form.get_by_label('fixture-0054.example.org',exact=True).check();form.get_by_role('button',name='Próxima',exact=True).click()
    form.get_by_label('fixture-0000.example.org',exact=True).check();form.get_by_role('button',name='Salvar caso').click()
    expect(page.get_by_text('2 domínios',exact=True)).to_be_visible()
    page.get_by_role('button',name='Enfileirar PDF',exact=True).click()
    page.get_by_role('link',name='Relatórios e denúncias',exact=True).click()
    expect(page.get_by_role('button',name='PDF',exact=True)).to_be_visible(timeout=90000)
    with page.expect_download() as download_info:page.get_by_role('button',name='PDF',exact=True).first.click()
    target=Path(download_info.value.path());assert target.read_bytes().startswith(b'%PDF')
    page.get_by_role('link',name='Segurança da conta',exact=True).click()
    page.get_by_label('Senha atual',exact=True).first.fill(password)
    page.get_by_role('button',name='Configurar autenticador',exact=True).click()
    secret=page.locator('code.secret').first.inner_text()
    page.get_by_label('Código do aplicativo',exact=True).fill(pyotp.TOTP(secret).now())
    page.get_by_role('button',name='Confirmar e ativar',exact=True).click()
    expect(page.get_by_role('heading',name='Guarde seus oito códigos de recuperação')).to_be_visible()
    page.get_by_role('button',name='Já guardei os códigos').click()
    page.get_by_role('button',name='Solicitar confirmação',exact=True).click()
    # Mail is processed by the real worker and delivered to the local SMTP capture.
    for _ in range(25):
        page.get_by_role('button',name='Abrir caixa local de teste').click()
        if page.get_by_text('Confirmação de email BetHunter',exact=True).count():break
        page.wait_for_timeout(2000)
    page.get_by_text('Confirmação de email BetHunter',exact=True).first.click()
    page.get_by_role('link',name='Abrir ação do email').first.click()
    expect(page.get_by_role('heading',name='Confirmar email',exact=True)).to_be_visible()
    page.get_by_role('button',name='Confirmar',exact=True).click()
    expect(page.get_by_text('Email confirmado no modo local de teste.',exact=True)).to_be_visible()
    assert not errors,errors
    browser.close()
print('E2E OK: login, inventory pagination, multi-page case selection, queued PDF download, MFA and local SMTP verification.')
