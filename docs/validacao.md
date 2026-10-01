# Validação da reorganização

Verificações realizadas em 1º de outubro de 2026, no Windows, com Python 3.13.3. A base foi o commit `22605af`, da branch `fix/correcao-bugs`. O trabalho foi feito em `refactor/organizacao-projeto`, sem alterar a branch local `main`.

## Código e interface

Um script local de verificação em `build/validar.py` abriu a janela real com banco e planilhas fictícias em diretórios temporários. Os mesmos cenários passaram antes e depois da reorganização, e foram repetidos após as etapas que afetam execução e empacotamento.

| Verificação | Resultado |
| --- | --- |
| Abertura, processamento de eventos e fechamento da janela | Passou |
| Quatro abas, ícone do cabeçalho e alternância claro/escuro | Passou |
| Importação `.xlsx` e identificação das colunas | Passou |
| Criação de campanha e importação de contatos já enviados | Passou |
| Deduplicação, pesquisa e ordenação da campanha | Passou |
| Exportação de campanha e histórico para `.xlsx` | Passou |
| Normalização de telefone válido e rejeição de número curto | Passou |
| Envio simulado pela thread e fila reais | Passou |
| Personalização da mensagem e remoção de duplicados no lote | Passou |
| Persistência de sucesso e número sem WhatsApp na campanha | Passou |
| Contadores e histórico de falhas e sucessos | Passou |
| Entrada do pacote, equivalente a `python -m thbot` | Passou |

Na simulação, foram usados quatro registros: um contato repetido, um contato que retorna “Número sem WhatsApp” e um número inválido. O lote resultante teve três registros, com um sucesso e duas falhas, e duas chamadas simuladas ao envio. Nenhum contato real foi utilizado.

A comparação da árvore sintática confirmou que a classe `WhatsAppThbot` e as funções existentes, exceto as duas funções de localização de caminhos, mantiveram o mesmo conteúdo. `ui.py` manteve o conteúdo de `thbot_ui.py`. Imports, docstrings, entrada e caminhos foram os ajustes estruturais.

Foram verificados os caminhos de recursos e dados tanto no código quanto em condições simuladas de `sys.frozen` e `sys._MEIPASS`. A localização original do banco e das sessões foi preservada.

## Build e navegador

O ambiente Python já instalado passou nos cenários com CustomTkinter 6.0.0, pandas 3.0.5 e Playwright 1.58.0. Nesse ambiente, o Chromium presente não correspondia à revisão esperada pelo Playwright. Isso foi resolvido para a validação usando um ambiente virtual separado, sem alterar a instalação global.

O ambiente virtual foi instalado a partir de `requirements.txt`, sem modificar esse arquivo. Versões usadas na compilação:

| Dependência | Versão |
| --- | --- |
| CustomTkinter | 6.0.0 |
| pandas | 3.0.6 |
| openpyxl | 3.1.5 |
| Pillow | 12.3.0 |
| Playwright | 1.63.0 |
| PyInstaller | 6.22.3 |
| Chromium do Playwright | revisão 1243 |

Com `PLAYWRIGHT_BROWSERS_PATH=0`, foram executados a instalação do Chromium e o build por `packaging/thbot.spec`. A compilação terminou com sucesso; uma execução incremental confirmou código de saída zero. O resultado local foi `dist/thbot.exe`.

- O `.spec` resolveu entrada, ícone e imports quando avaliado a partir de outro diretório.
- A inspeção do arquivo do executável confirmou os módulos `thbot.app`, `thbot.ui`, CustomTkinter e Playwright, além do ícone e do Chromium incluídos.
- O executável foi iniciado com diretório de trabalho diferente da sua pasta. A janela “WhatsApp Thbot” foi criada e o processo respondeu, usando o banco ao lado do executável. O banco existente nessa pasta foi preservado.
- A função real de abertura do navegador iniciou Chromium com perfil temporário, carregou uma página HTML local e encerrou o contexto corretamente.
- Os artefatos de teste, logs e ambiente virtual permanecem ignorados pelo Git.

## Limites da validação

- Os envios e resultados do WhatsApp foram simulados. Não houve login, leitura de QR Code nem envio real.
- O executável foi testado neste computador; não foi validado em outra instalação limpa do Windows.
- A automação visual por `computer-use` não ficou disponível: a conexão com o serviço local retornou erro de pipe inexistente. As verificações de interface usaram a janela real, estado dos widgets e processamento de eventos por Python; não houve revisão por screenshot.
- Firefox, Google Chrome e arquivos `.xls` não foram exercitados nesta validação.
- O script auxiliar em `build/` é local e não faz parte do código distribuído nem de uma suíte versionada.

## Branches já mescladas

Após `git fetch origin`, a referência `origin/main` ficou em `1c2a178`, contendo as sete branches abaixo. A `main` local permaneceu em `9179800`, 14 commits atrás de `origin/main`. O conteúdo de `origin/main` era idêntico ao da base `22605af` usada na reorganização.

Comparadas à `main` **local**, nenhuma outra branch local ou remota estava integralmente mesclada. Comparadas à `origin/main` **atualizada**, estas são candidatas à exclusão, se não forem mais usadas:

| Branch local | Branch remota |
| --- | --- |
| `feat/aba-campanha` | `origin/feat/aba-campanha` |
| `feat/atualizacao-campanha` | `origin/feat/atualizacao-campanha` |
| `feat/new-front` | `origin/feat/new-front` |
| `fix/correcao` | `origin/fix/correcao` |
| `fix/correcao-bugs` | `origin/fix/correcao-bugs` |
| `fix/correcao-de-tela` | `origin/fix/correcao-de-tela` |
| `fix/readme` | `origin/fix/readme` |

Nenhuma branch foi apagada. Manter `main`, `origin/main` e `refactor/organizacao-projeto`. Qualquer exclusão fica pendente de confirmação explícita; antes de executá-la, conferir novamente as referências remotas.
