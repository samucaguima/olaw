-- Termo inicial dos prazos legais (plano, Seção 7.1). Pressupõe 0002.
-- A tabela de prazos conferida em 10/10/2026 (docs/fase0/dados-publicos/
-- tabela_prazos_legais.csv) registra atos cujo prazo não corre da publicação
-- no DJEN; o motor de prazos não pode calculá-los a partir dela.

BEGIN;

ALTER TABLE sgj.prazos_legais
    ADD COLUMN termo text NOT NULL DEFAULT 'publicacao' CHECK (termo IN ('publicacao', 'manual')),
    ADD COLUMN observacoes text;
COMMENT ON COLUMN sgj.prazos_legais.termo IS
    'publicacao: contado da publicação no DJEN pelo motor de prazos; manual: termo inicial diverso, controlado pelo advogado.';

UPDATE sgj.prazos_legais SET observacoes = 'Na falta de preceito legal ou de prazo fixado pelo juiz'
WHERE tipo_ato = 'manifestacao_sem_prazo_fixado';
UPDATE sgj.prazos_legais SET observacoes = 'Recursos e respectivas respostas; não se aplica aos embargos de declaração'
WHERE tipo_ato = 'recurso_ou_resposta';
UPDATE sgj.prazos_legais SET observacoes = 'Agravo contra decisão de relator ou outra decisão unipessoal em tribunal'
WHERE tipo_ato = 'agravo_decisao_unipessoal_tribunal';
UPDATE sgj.prazos_legais SET observacoes = 'Réplica quando o réu alega fato impeditivo modificativo ou extintivo'
WHERE tipo_ato = 'manifestacao_fato_impeditivo';
UPDATE sgj.prazos_legais SET observacoes = 'Réplica quando o réu alega matéria do art. 337'
WHERE tipo_ato = 'manifestacao_preliminares';
UPDATE sgj.prazos_legais SET observacoes = '[CONFERIR] natureza do prazo de pagamento para fins de contagem em dias úteis'
WHERE tipo_ato = 'pagamento_cumprimento_sentenca';
UPDATE sgj.prazos_legais SET termo = 'manual',
       observacoes = 'Inicia-se após o prazo do art. 523 sem pagamento; controle encadeado'
WHERE tipo_ato = 'impugnacao_cumprimento_sentenca';
UPDATE sgj.prazos_legais SET termo = 'manual',
       observacoes = 'Termo inicial pelos incisos do art. 335 e não pela publicação no DJEN; controle manual do termo'
WHERE tipo_ato = 'contestacao';
UPDATE sgj.prazos_legais SET termo = 'manual',
       observacoes = 'Termo inicial na forma do art. 231 (citação) e não pela publicação no DJEN; controle manual do termo'
WHERE tipo_ato = 'embargos_a_execucao';

COMMIT;
