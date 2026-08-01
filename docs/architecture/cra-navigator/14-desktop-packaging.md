# 14 — Embalagem Desktop (Windows)

## 1. Princípio

A entrega desktop Windows é o **primeiro caminho** do MVP. O utilizador final (PME) não
deve precisar de Docker, de instalar runtimes, ou de configurar firewalls. A solução é
um instalador nativo Windows (`.exe` / `.msi`).

## 2. Stack de embalagem (baseline, reversível)

| Camada | Tecnologia-sugestão (reversível) | Justificação | ADR |
|---|---|---|---|
| Runtime desktop | Electron | UI web reutilizável + Windows nativo; cross-platform futuro | ADR-001 |
| Packaging | electron-builder | `.exe` NSIS + `.msi`, code-signing integrado | ADR-001 |
| Code signing | code signing cert (EV recomendado) | SmartScreen do Windows | ADR-008 |
| Key provider | Windows DPAPI | sem prompts ao utilizador; isolamento por conta | ADR-005 |

> **Reversível**: a decisão sobre Electron vs Tauri vs nativo .NET é adiada ao ADR-001
> (ver `17-deferred-decisions.md`). A arquitetura (Zonas A/B/C/D) é independente da
> stack de embalagem.

## 3. Assunções de instalação (MVP)

- Instalador: `BlitzHub-CRA-Navigator-Setup.exe` (per-machine ou per-user).
- Per-user (recomendado para MVP): não requer elevate; dados em `%LOCALAPPDATA%`.
- Per-machine (futuro): requer elevate; dados em `%PROGRAMDATA%`.
- Nenhum serviço Windows (`services`) no MVP — tudo em processo do utilizador.
- Nenhum firewall exception necesário (nada escuta em rede no MVP).

## 4. Isolamento e integridade

- Processo: Electron com `nodeIntegration: false`, `contextIsolation: true`,
  `sandbox: true` no renderer (processos sandboxed Chromium).
- O Node main (`domain-engine`) roda no processo principal; mas ficheiros de evidence
  são lidos via `shell` (preloaded, validated paths) — o renderer nunca faz file-I/O
  direto.
- Code signing de todos os binários (app + DLL do Node + asar) — requisito de SmartScreen.

## 5. Privilege boundaries (Windows)

- MVP roda com o token do utilizador logado (standard user).
- Nenhuma operação eleva privilégios. `CryptProtectData` (DPAPI) funciona ao nível do
  utilizador sem elevar.
- OEvidence Vault path é limitado a `%LOCALAPPDATA%` (não `%PROGRAMFILES%`).

## 6. Acessibilidade

- O renderer Chromium é acessível por padrão (Chromium a11y).
- Testado com NVDA + Narrator (automatizado parcialmente na vaga 3).
- `prefers-reduced-motion` respeitado (política `visual-assets-policy.yaml`).

## 7. Portabilidade (futuro, reversível)

- A mesma base Electron pode produzir `.AppImage` / `.dmg` sem mexer no core. Veja
  `13-future-integration-boundaries.md`.
