# 10 — Mecanismo de Atualização

## 1. Modelo (MVP)

A atualização do app e dos rule packages usa o mesmo fluxo:

```
[Update Service] --(signed release)--> [Shell] --verify--> [Domain] --schedule--> restart
```

- **Fonte**: GitHub Releases do repositório `pestoura/blitzhub-cra-navigator`.
- **Verificação de integridade**: SHA-256 do asset comparado com o publicado.
- **Verificação de autenticidade**: assinatura `.sig` do release verificada com a chave
  pública embutida no app (não configurável pelo utilizador). Veja ADR-006 (extended).
- **Download**: apenas para `temp/` dentro da pasta do app; nunca executa diretamente.
- **Aplicação**: restart elegante; rollback automático se o boot falhar 2x.

## 2. Tipos de release

| Tipo | Target | Verificação | Observação |
|---|---|---|---|
| App full | `BlitzHub CRA Navigator Setup.exe` | assinatura + hash | instalador do app |
| App delta | `.mar` (Mozilla MAR) | assinatura + hash | patch incremental |
| Rule package | `cra-rules.zip` | hash + manifest assinado | carregado no Rules Engine |

## 3. Segurança

- `pull_request_target` **nunca** usado em workflows que processam atualização.
- A chave privada de assinatura **não** vive no repositório; workflow usa GitHub
  Environment + trusted signing (veja ADR-006, ADR-008).
- O app verifica a cadeia de certificado do release contra `api.github.com` via TLS.

## 4. Modo offline

- Se offline, o app continua funcional com o release/last rule package.
- Verificação de update é best-effort: falha silenciosa (não fatal) e é retry em background
  com backoff exponencial (máx. 1 dia).

## 5. Auto-atualização (MVP vs futuro)

- **MVP**: *opt-in* — o utilizador confirma em download + apply. Nunca automático.
- **Futuro (v2)**: auto-update silenciosa para patches de segurança críticos, com
  configuração `updates.auto_install_security` (default `false` no MVP).

## 6. Trust boundary

O Update Service está na **Zona D (External)**. Qualquer release não verificado é
rejeitado — o app **não** aplica updates sem verificação. Veja threat model `T-UPDATE`.
