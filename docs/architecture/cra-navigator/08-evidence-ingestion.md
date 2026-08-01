# 08 — Ingestão & Armazenamento de Evidências

## 1. Princípio

Toda evidência carregada pelo utilizador é **maliciosa até provado o contrário**. A ingestão
passa por três etapas obrigatórias antes de atingir o Domain Engine (Zona A):

```
SME upload
  → frontend-sanitizer (type + size + name)
  → UI Renderer (preview sem exec)
  → Domain Engine (request)
  → Evidence Vault.validateSafety (magic bytes + content-addressing)
  → Evidence Vault.ingest (sandbox path)
  → EvidenceRecord (id, sha256, mime, size, meta)
  → Domain Engine (persist meta in store)
```

## 2. Tipos aceites (MVP baseline)

| Tipo | Magic bytes | Ext. permitidas | Tamanho máximo |
|---|---|---|---|
| PDF | `%PDF-` | `.pdf` | 50 MB |
| Imagem | `PNG/8950`, `JPEG/FFD8`, `GIF/GIF8`, `WEBP/RIFF` | `.png .jpg .jpeg .gif .webp` | 25 MB |
| Texto | n/a | `.txt .md .csv .log` | 10 MB |
| Spreadsheet | `PK` (OOXML) | `.xlsx .xls` | 30 MB |
| Arquivo | `PK`/`7z`/`Rar`/`ustar` | `.zip .7z .7zip .rar .tar .gz .tgz` | 100 MB |

**Proibido**: `.exe .dll .bat .sh .ps1 .js .vbs .jar .com .scr .msi` e qualquer MIME
`application/x-msdownload` / `application/x-executable`.

## 3. Validação de segurança (`vault.validateSafety`)

Sempre executada antes de ingestão:

1. **Size check**: rejeita-se se > limite por tipo.
2. **MIME spoof check**: o magic-bytes deve coincidir com o content-type declarado;
   mismatch → rejeição + log de alerta.
3. **Path traversal**: nome é reduzido a leaf; `\`, `/`, `..`, NUL, `\\uXXXX` são
   rejeitados; path é content-addressed.
4. **Arquivo (zip) descompressão**: se for `.zip`, extrai-se em sandbox temporário e
   re-valida cada membro contra a mesma política (path traversal + tipo proibido).
   - Limitação: profundidade máxima 5; member count máximo 10.000; member size total ≤ 200 MB.
5. **Content-addressing**: SHA-256 do conteúdo; colisão reutiliza o `EvidenceRecord`.

> Ver threat model `T-FILEUPLOAD`, `T-PATHTRAVERSAL`, `T-ARCHIVE`.

## 4. Metadados e integridade

- `EvidenceRecord.id` = `sha256(content)` (sem extensão).
- Metadados (nome original, size, mime, tags, `provenance`, `added_at`) vivem no store.
  O nome original é **apenas** metadado: nunca executado nem seguido como path.
- Ficheiro é imutável: alteração = novo `id`. Não há update in-place.
- Hash de integridade verificado a cada leitura (`vault.read` re-haseia).

## 5. Quarentena e exclusão

- Uploads suspeitos entram em `quarantine/` (Zona B) com estado `pending_review` e são
  visíveis ao utilizador para aprovação/rejeição.
- Ficheiros rejeitados são apagados; a ação é append-logged.
- Evidências podem ser **revogadas** (soft-delete) — marca `deleted_at` no store; o
  ficheiro binário é removido do vault e registrado. Relatórios já gerados não são
  retroativamente alterados (integridade do report — veja `09-report-generation.md`).

## 6. Limite de confiança para ficheiros carregados

- O Evidence Vault **não executa** conteúdo. PDF preview usa renderização estática
  (nunca JS). Imagens são decodificadas em processo isolado (sandbox de renderer).
- Nenhum caminho carregado é passado para `shell.exec`, `eval`, `require` ou template
  engine. Veja `03-data-flows.md` §4.

## 7. Interface (contrato)

`contracts/02-evidence-vault.yaml` define:
- `FileMeta` (name, size, mime, lastModified).
- `SafetyVerdict` (safe, reason, mime_verified, magic_match).
- `EvidenceRecord` (id, sha256, mime, size, tags, added_at, provenance).

## 8. Testes de contrato (para vaga 2)

- `path_traversal_rejected`: nomes com `..`, `/`, `\\` → rejeitados.
- `mime_spoof_detected`: ficheiro .exe renomeado .pdf → rejeitado.
- `zip_bomb_limit`: zip malicioso → rejeitado por member-size.
- `content_addressing_idempotent`: upload duplo de mesmo contento → mesmo `id`.
