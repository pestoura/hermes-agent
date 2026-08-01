# 04 — Persistência Local, Cifragem, Backup, Restore & Migrações

## 1. Modelo de dados versionado

O modelo de dados do CRA Navigator é versionado com `schema_version` semântico
`MAJOR.MINOR.PATCH`. Cada alteração que quebra compatibilidade bumpa o `MAJOR`.

| Versão | Data | Componente | Breaking? | Nota |
|---|---|---|---|---|
| 1.0.0 | 2026-07-31 | store + vault metadata | — | baseline da arquitetura |
| 1.0.1 | (deferido) | evidence metadata | no | indexação por tag |

**Local**: `contracts/01-store-schema.yaml` (authoritative).

### 1.1 Tabelas-chave do Local Store (MVP baseline 1.0.0)

| Tabela | Descrição | Cifra? |
|---|---|---|
| `scopes` | decisões de âmbito + rationale | yes |
| `assessments` | resultados de avaliação por produto | yes |
| `evidence_meta` | metadados de evidências (id, sha256, mime, size, tags) | yes |
| `rule_package_meta` | versão + hash do pacote de regras carregado | yes |
| `user_prefs` | preferências UI (não sensíveis) | no (integridade) |
| `migrations_log` | histórico de migrações aplicadas | yes |
| `report_manifests` | metadados de relatórios gerados | yes |

## 2. Cifragem em repouso

**Decisão**: SQLCipher (WAL mode) com chave derivada da **Windows DPAPI** via
`crypto-key-provider`. Veja ADR-005.

- A chave mestra é gerada por `crypto-key-provider` e **armazenada no Windows DPAPI**
  (`CryptProtectData`), nunca como texto no disk do aplicativo.
- Chave-mestra > deriva (PBKDF2-HMAC-SHA256, 200k iters) > cifra SQLCipher
  (AES-256-GCM, WAL).
- `user_prefs` não é cifrada (precisa de leitura rápida em boot) mas tem **integridade
  verificada** (HMAC por linha).
- Backup da chave: exportação opcional protegida por password (não automática).

### 2.1 Vault de ficheiros (Evidências)

- Ficheiros binários vivem em `<user-data>/evidence/` fora do SQLCipher.
- Nomes são substituídos por `<sha256>.<safe-ext>` (content-addressing).
- Pasta é sandboxed: proibido path traversal (`..\`, `/`, `\\uXXXX`).
- Cifra por-ficheiro opcional (quando ativada): chave do vault derivada da chave-mestra.

## 3. Backup & Restore

### 3.1 Backup
- `Store.backup(path?)` → `BackupHandle`.
- Output: ficheiro `.cra-backup` contendo: dump SQLCipher (encrypted) + vault manifest +
  hash de integridade (SHA-256 do conteúdo).
- Backup **herdado do Windows DPAPI**: o backup é cifrado com a mesma chave-mestra do
  utilizador ativo; para backup offline, o utilizador fornece password que deriva uma
  chave de exportação.
- Metadados de backup: `schema_version`, `created_at`, `app_version`, `scope_count`,
  `evidence_count`, `integrity_hash`.

### 3.2 Restore
- `Store.restore(backupFile, {password?})` → `MigrationResult`.
- Flow:
  1. verifica `integrity_hash`;
  2. descriptografa dump (chave do utilizador ou password);
  3. aplica migrações até `schema_version` atual;
  4. restaura vault para `<user-data>/evidence/` com re-escrita de paths;
  5. regista em `migrations_log`.
- Restauro **substitui** o store corrente (após confirmação explícita do utilizador) ou
  importa em modo sandbox (restore-into) para revisão.

### 3.3 Confidencialidade e integridade do backup
- Confidencialidade: cifra (chave-mestra ou password-derived).
- Integridade: SHA-256 do payload; assinatura opcional do app para backups locais.
Veja Threat Model `T-BACKUP`.

## 4. Migrações

- Motor: `migrations/` dentro do app (script pura, declarativa).
- Execução: antes de qualquer leitura, na abertura da base.
- Atomicidade: cada migração é `BEGIN IMMEDIATE` + `COMMIT`; rollback automático em erro.
- Idempotência: cada migração regista `version` em `migrations_log`; re-execução é no-op.
- Reversibilidade: migrações destrutivas (`DROP COLUMN`) devem manter dados numa tabela
  `_pending_drop_<v>` por 2 versões antes de purgar (política ADR-002).

## 5. Layout no disco (Windows)

```
%LOCALAPPDATA%\BlitzHub\CRANavigator\
  data.sqlite            # SQLCipher store
  evidence/              # vault (content-addressed files)
  keys/                  # DPAPI-protected master key wrapper
  migrations/            # migration scripts (bundled)
  logs/                  # logs estruturados (local, não sensíveis)
  exports/               # relatórios exportados pelo utilizador
  backups/               # backups locais do utilizador
```

**Nota de privacidade**: nada é escrito fora desta pasta sem ação explícita do utilizador.
Nenhuma pasta é partilhada entre utilizadores do SO (ACL por utilizador Windows).

## 6. Testes de persistência (contrato para vaga 2)

- `Store.migrate` preserva todos os dados entre versões.
- `backup → restore` round-trip preserva schema + conteúdo (SHA-256 invariant).
- Corrupção intencional de ficheiro é detetada (`integrity_hash` falha).
- Abertura com chave errada falha sem vazar dados.
