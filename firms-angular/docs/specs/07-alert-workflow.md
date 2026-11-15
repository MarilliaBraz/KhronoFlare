# Spec 07 — Workflow de alerta e CAP

## Objetivo
Estados new → draft → pending → sent → cancelled + CAP + activity.

## Dependências
Spec 06.

## Acceptance criteria
- [x] Draft com level/event/action/area/author
- [x] Pending com approver ≠ author e checagens
- [x] Approve gera CAP XML e publica ntfy
- [x] Cancel / dismiss / return to draft
- [x] Activity log; slots harmônicos como "—"

## Fora de escopo
Persistência em servidor; autenticação real.
