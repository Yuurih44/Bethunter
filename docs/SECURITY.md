> Atualização: a implementação posterior adicionou SMTP/verificação/recuperação, papéis PostgreSQL separados, backups, paginação e fila PDF. Consulte [OPERATIONS.md](OPERATIONS.md) para o comportamento atual e [VERIFICATION.md](VERIFICATION.md) para validações e pendências. As observações históricas abaixo não substituem esses documentos.

# Cadastro e segurança de contas

O cadastro padrão é `REGISTRATION_MODE=invite`. Contas existentes continuam podendo entrar com a senha atual; a exigência de 15 caracteres se aplica a novos cadastros e trocas de senha. `closed` bloqueia cadastros. `open` é opção explícita de desenvolvimento e é rejeitada quando `APP_ENV=production`.

## Instalação local existente

No terminal normal, sem sudo:

```bash
cd /home/kali/bethunter
./iniciar.sh stop
./iniciar.sh
./iniciar.sh admin seu-email@exemplo.com
```

O último comando cria um administrador com senha solicitada sem eco ou promove a conta existente, com auditoria. Somente o operador com acesso ao terminal deve executar esse comando. Entre em http://localhost:8080 e abra **Segurança da conta**. Configure o autenticador TOTP, confirme o código e guarde os oito códigos de recuperação. Um código TOTP já utilizado exige aguardar o próximo intervalo de 30 segundos para nova operação sensível.

A interface permite emitir convites como administrador com MFA e senha atual. Para emissão pelo operador local:

```bash
./iniciar.sh invite convidado@exemplo.com
```

O convite dura 24 horas, só funciona para esse email e só pode ser usado uma vez. Apenas o hash é persistido. O código aparece uma vez na interface/resposta de emissão ou no terminal; compartilhe por canal privado. Não é enviado email. **Vincular um convite ao email não verifica a posse da caixa postal.** Confirmação e recuperação por email estão implementadas separadamente; o modo local captura sem entregar na internet. Produção exige SMTP real com STARTTLS e confirmação real.

## MFA, sessões e recuperação

TOTP usa segredo criptografado com Fernet, sob `AUTH_ENCRYPTION_KEY`; códigos de recuperação são armazenados somente como hashes, de uso único. Ativar MFA, trocar senha e desativar MFA revogam as sessões anteriores. Desativar MFA exige senha e segundo fator e encerra todas as sessões. Administradores precisam de MFA para ações administrativas, mas podem entrar e configurar seu próprio MFA antes disso. A janela de TOTP aceita o intervalo anterior/atual/próximo, sem reutilizar um contador já aceito.

O inicializador nativo gera automaticamente a chave em `.runtime/local.env` e preserva a chave nas próximas execuções, com permissão 0600. Faça backup desse arquivo de forma protegida junto com o banco. Perder/trocar a chave impossibilita decifrar segredos MFA existentes. Nunca copie esse arquivo para entregas ou repositórios.

No Compose, gere uma chave e grave em `.env` antes de iniciar:

```bash
python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
# Defina AUTH_ENCRYPTION_KEY com a saída, sem divulgá-la.
docker compose up --build -d
docker compose exec backend python -m app.cli seu-email@exemplo.com
```

O comando Python requer cryptography instalado; alternativa com OpenSSL: `openssl rand -base64 32 | tr '/+' '_-'`. No PowerShell, use o comando Python após instalar a dependência ou um gerenciador de segredos capaz de gerar uma chave Fernet.

Recuperação excepcional pelo operador local, quando os códigos de recuperação não estão disponíveis:

```bash
./iniciar.sh reset-mfa seu-email@exemplo.com
# Desativar uma conta e revogar suas sessões:
./iniciar.sh disable conta@exemplo.com
```

Equivalentes no Compose: `docker compose exec backend python -m app.cli EMAIL --reset-mfa` e `--disable`. Essas operações são privilegiadas e auditadas; não existem rotas públicas para promover contas ou remover MFA sem prova de identidade.

Sessões têm limite absoluto de oito horas e de 30 minutos sem atividade por padrão. Polling GET do dashboard não prolonga a sessão; interações de teclado/ponteiro enviam sinal de atividade limitado a uma vez por minuto. A área Segurança lista sessões ainda não expiradas e permite encerrar outras sessões mediante reautenticação. Contas desativadas não acessam a API.

Após cinco falhas por identidade, o login fica limitado por 15 minutos, com estado no banco que sobrevive ao reinício do processo. Há também limites locais por IP/operação; hashes Argon2 são limitados a duas operações concorrentes por processo. Esses controles não substituem proteção de borda e limites distribuídos em implantação grande.

## Acesso externo

`ORIGIN` fora de localhost/127.0.0.1/::1 exige HTTPS e `COOKIE_SECURE=true`. Produção exige também chave MFA e cadastro por convite/fechado, e desabilita Swagger/OpenAPI. Configure o certificado e o proxy HTTPS antes de publicar. O Compose continua vinculado a 127.0.0.1:8080 por padrão; o preview nativo serve desenvolvimento local. O backend valida Host, Origin e CSRF, usa cookies HttpOnly/SameSite Strict e adiciona cabeçalhos defensivos. Não houve pentest independente ou certificação de segurança.
