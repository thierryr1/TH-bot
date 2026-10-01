# Organização interna: sugestões pendentes

A reorganização preserva as regras de negócio, a interface e o fluxo de envio. As sugestões abaixo não foram aplicadas porque exigem decisões ou testes específicos além de mover os arquivos.

## Responsabilidades e métodos extensos

- `WhatsAppThbot`, em `thbot/app.py`, reúne janela, banco, planilhas, campanhas e navegador. Uma evolução pode separar persistência, preparação de contatos e automação em módulos próprios.
- `_iniciar_envio` combina validação, normalização, remoção de duplicados e controle da thread. Extrair a preparação do lote facilitaria testar as regras sem criar uma janela.
- `_executar_envio` reúne o ciclo do navegador, pausa, interrupção, personalização e resultados. A extração de etapas deve preservar o uso do Playwright na mesma thread e a comunicação pela fila.
- `_importar_registros_campanha` combina leitura, identificação de colunas, normalização e gravação. Separar essas etapas ajudaria a tratar falhas sem misturar responsabilidades.

## Nomes e duplicações

- `CampaignCombo`, em `thbot/ui.py`, também seleciona navegador. Um nome como `RefreshableComboBox` descreveria melhor seu comportamento.
- Nomes como `bloco4`, `bloco5` e `sub6` podem indicar a função do componente: intervalo, quantidade ou controles.
- `_telefones_enviados_na_campanha` inclui também números sem WhatsApp. Um nome referente a contatos processados representaria melhor a regra atual.
- Os candidatos a colunas de nome e telefone aparecem em mais de um método.
- A normalização dos nomes de colunas se repete em `_adivinhar_coluna`.
- Os avisos de número sem WhatsApp e o seletor da caixa de mensagem se repetem no JavaScript usado pelo Playwright.
- O encerramento do contexto e a publicação de eventos se repetem em vários caminhos de saída do envio. Revisar isso exige cuidado para não alterar a liberação do perfil nem a confirmação do último envio.

## Configurações e erros

- Consolidar cores, dimensões, tempos de espera, seletores e textos de status em constantes, sem mudar seus valores.
- Tratar erros de SQLite nos callbacks, inclusive banco bloqueado, indisponível ou sem permissão de escrita.
- Fechar explicitamente conexões SQLite: `with sqlite3.connect(...)` controla a transação, mas não fecha a conexão. A liberação hoje depende da coleta de lixo.
- Validar quantidade e timeout digitados antes de chamar `.get()` e alterar o estado dos botões. A validação atual cobre os intervalos de envio, mas não todos os campos numéricos.
- Revisar `except Exception` silenciosos, distinguindo encerramento esperado do navegador de problemas que merecem diagnóstico.
- Revisar o fechamento da janela durante um envio, preservando a afinidade de thread do Playwright e a persistência dos resultados.

## Dependências e documentação

- Decidir se o suporte a `.xls` deve fazer parte da instalação padrão. O seletor aceita o formato, mas `xlrd` não está declarado nas dependências atuais.
- Definir uma política de versões para tornar builds reproduzíveis; apenas CustomTkinter possui versão fixa hoje. Não houve alteração de versões no arquivo de requisitos nesta reorganização.
- Adicionar um print da interface sem contatos, mensagens ou dados de sessão.
- Escolher a licença e o titular para preencher `LICENSE`.

## Pequenas mudanças aplicadas

- Pacote `thbot`, imports internos e ponto de entrada explícito.
- Nomes `app.py` e `ui.py`, com responsabilidades descritas nos módulos.
- Centralização da raiz do projeto usada para encontrar recursos e preservar os dados existentes.
- Caminhos do `.spec` derivados de sua localização, independentes do diretório de trabalho.

Nenhuma regra de validação, envio, deduplicação, pausa, histórico ou armazenamento foi reescrita.
