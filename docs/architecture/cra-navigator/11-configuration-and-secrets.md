# 11 — Configuração & Segredos

## 1. Princípio

Nenhum segredo, chave privada, token ou dado sensível é armazenado no repositório
público (confirmação: `policies/public-repository-policy.yaml`). Toda configuração
sensível é: (a) gerada no runtime; (b) armazenada no OS keychain; (c) nunca serializada
para o store sem cifra.

## 2. Matriz de configuração

| Item | Localização | Cifra | Mutável? | Observação |
|---|---|---|---|---|
| Feature flags (`ai.enabled`, etc.) | `user_prefs` table (store) | Não (integridade HMAC) | Sim (UI) | |
| Master key wrapper | `%LOCALAPPDATA%\...\keys\` (DPAPI) | Sim (DPAPI) | Auto | envoltório da chave SQLCipher |
| Local LLM model | `%LOCALAPPDATA%\...\models\` | Não | Manual | binário grand; excluded de backup |
| Rule package | `rules/v1.0.0/` (bundled) | Não (assinado) | Via update | read-only |
| App config (`config.json`) | `%LOCALAPPDATA%\.../config/` | Não | Auto | apenas não-sensível |
| License key (futuro) | Windows DPAPI | Sim | Não | futuro, ADR-001 |

## 3. Segredos sensíveis (Zona B / DPAPI)

### 3.1 Crypto-key-provider (Windows)
- Usa `CryptProtectData` / `CryptUnprotectData` (DPAPI) para proteger o master key wrapper.
- O master key (256-bit random) é gerado no primeiro boot; nunca persiste em texto.
- DPAPI liga a chave ao utilizador Windows logado → isolamento por utilizador automático.

### 3.2 Chave do SQLCipher
- `k = PBKDF2-HMAC-SHA256(master_key, salt, 200_000)`; salt persistido no store header.
- `PRAGMA key = 'x' || hex(k)`; modo `AES-256-GCM`.

## 4. Secrets em runtime (processos Electron)

- A chave mestra é carregada no `Domain Engine` apenas em memória volátil.
- `process.env` **nunca** carrega secrets (proibido pelo `public-repository-policy`).
- Preload script usa `contextIsolation: true`, `nodeIntegration: false`; IPC para acesso
  à chave passa pelo Domain Engine só (o Renderer nunca toca a chave).

## 5. Escopo e permissões do OS (Windows)

- App executa com o privilégio do utilizador logado (nunca `runas admin` no MVP).
- Pasta de dados é `%LOCALAPPDATA%\BlitzHub\CRANavigator\` — ACL por utilizador Windows.
- Nenhuma escrita em `Program Files` ou `HKLM` no MVP (rever se auto-update for permitido).

## 6. Injeção de configuração (futuro, reversível)

- Se uma variante cloud/appliance precisar de secrets centralizados, usar um
  **pluggable vault adapter** (ADR-005) — nunca hardcode.

## 7. Verificação (contrato)

- Teste: `config_never_contains_secrets_at_build` — scanning `config/*.json`.
- Teste: `master_key_not_in_process_memory_dump` — smoke test em runtime.
