# TH-bot

Aplicação desktop em Python para enviar mensagens personalizadas pelo WhatsApp Web a partir de uma planilha Excel. A interface usa CustomTkinter, a automação usa Playwright e o histórico fica em um banco SQLite local.

## Recursos

- Identificação automática das colunas de telefone e nome.
- Mensagens com variáveis da planilha, como `{Nome}`, `{Cidade}` e `{Produto}`.
- Campanhas com controle de contatos processados, incluindo números sem WhatsApp, para evitar novas tentativas na mesma campanha.
- Importação de contatos já enviados, pesquisa, ordenação e exclusão de registros por campanha.
- Histórico da sessão, resumo diário e exportação para Excel.
- Intervalo variável entre envios, limite de quantidade, pausa e interrupção.
- Seleção de navegador, DDI e tempo limite; temas claro e escuro.
- Sessão persistente do WhatsApp, com QR Code no primeiro acesso de cada perfil.

## Interface

Espaço reservado para um print da interface.

<!-- Adicione assets/interface.png e descomente a linha abaixo quando houver um print sem dados pessoais. -->
<!-- ![Interface do TH-bot](assets/interface.png) -->

## Requisitos

- Windows 10 ou superior.
- Python 3.10 ou superior, com Tkinter, para executar pelo código.
- Acesso à internet e uma conta do WhatsApp para os envios.
- Chromium instalado pelo Playwright, Google Chrome instalado no computador ou Firefox instalado pelo Playwright.

O executável inclui o Python e as bibliotecas necessárias. A configuração de compilação permite incluir também o Chromium.

## Instalação

No PowerShell, dentro da raiz deste repositório:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
```

Para usar a opção Firefox, instale também a versão gerenciada pelo Playwright:

```powershell
python -m playwright install firefox
```

O Firefox comum instalado no computador não substitui essa instalação. A opção Google Chrome usa o Chrome instalado no Windows.

Se não ativar o ambiente virtual, substitua `python` por `.\.venv\Scripts\python.exe` e `pip` por `.\.venv\Scripts\python.exe -m pip` nos comandos.

## Como executar

Na raiz do projeto, com o ambiente virtual ativo:

```powershell
python -m thbot
```

1. Selecione uma planilha de contatos.
2. Escreva a mensagem e insira as variáveis desejadas.
3. Selecione ou crie uma campanha para controlar reenvios. Sem campanha, o envio é livre.
4. Confira navegador, DDI, quantidade e intervalos.
5. Clique em **Iniciar** e leia o QR Code no navegador, se solicitado.

O navegador é aberto ao iniciar um lote, não ao abrir a interface. O comando antigo `python thbot.py` foi substituído por `python -m thbot`.

### Planilha de contatos

Use preferencialmente `.xlsx`, com uma coluna como `Telefone`, `Número`, `Fone` ou `Celular`. A coluna `Nome` é opcional; outras colunas podem personalizar a mensagem.

Os números devem conter DDD e podem incluir pontuação ou DDI. A validação atual aceita 10 ou 11 dígitos após a remoção do DDI reconhecido, mantendo a regra original do programa.

O seletor também aceita `.xls`, mas esse formato exige o pacote opcional `xlrd`, ausente de `requirements.txt`:

```powershell
pip install xlrd
```

Para disponibilizar `.xls` no executável, instale essa dependência no ambiente antes de compilá-lo e valide a leitura nesse formato.

## Dados locais

| Arquivo ou pasta | Conteúdo |
| --- | --- |
| `thbot_envios.sqlite3` | Campanhas, contatos processados e histórico de resultados. |
| `.whatsapp-playwright/` | Perfis e sessões de login separados por navegador. |

Ao executar pelo código, esses dados permanecem **na raiz do repositório**, preservando a localização usada antes da reorganização. No executável, permanecem **ao lado de `thbot.exe`**. Use uma pasta com permissão de escrita.

Faça cópias de segurança do banco com a aplicação fechada. Não distribua banco, sessões ou credenciais com o programa.

As pastas opcionais `data/` e `exports/` são ignoradas pelo Git e podem guardar planilhas pessoais. A aplicação continua permitindo escolher qualquer pasta; planilhas salvas em outros locais do repositório não são automaticamente ignoradas.

## Gerar o executável

No Windows, na raiz do projeto e usando o mesmo ambiente virtual da instalação:

```powershell
python -m pip install pyinstaller
$env:PLAYWRIGHT_BROWSERS_PATH = "0"
python -m playwright install chromium
python -m PyInstaller --clean --noconfirm packaging/thbot.spec
```

`PLAYWRIGHT_BROWSERS_PATH=0` instala o Chromium dentro do pacote Playwright, permitindo incluí-lo na distribuição. A instalação deve usar o mesmo Python da compilação, para que navegador e biblioteca sejam compatíveis. Esse procedimento segue a [documentação do Playwright para PyInstaller](https://playwright.dev/python/docs/library#pyinstaller).

O resultado é `dist/thbot.exe`, um executável único, sem console, com o ícone e os recursos da interface. Os arquivos intermediários ficam em `build/`. A configuração versionada permanece em `packaging/`, separada desses artefatos. Veja também a [documentação dos arquivos spec do PyInstaller](https://pyinstaller.org/en/stable/spec-files.html).

Distribua `dist/thbot.exe` para uso com Chromium sem instalar Python ou navegador no destino. Para incluir Firefox, execute `python -m playwright install firefox` com `PLAYWRIGHT_BROWSERS_PATH=0` antes da compilação. Google Chrome continua exigindo instalação no computador de destino.

Depois de compilar, a variável permanece definida nessa sessão do PowerShell. Se executar pelo código em outra sessão e quiser usar o navegador instalado dentro do pacote, defina novamente `$env:PLAYWRIGHT_BROWSERS_PATH = "0"`; alternativamente, execute `python -m playwright install chromium` nessa sessão para instalar no local padrão.

Gere novamente o executável após alterar código, interface, recursos ou dependências. O arquivo é grande por incluir o navegador; distribua-o por uma Release, sem adicioná-lo ao Git.

## Estrutura do projeto

```text
TH-bot/
├── thbot/
│   ├── __init__.py       # Identifica o pacote
│   ├── __main__.py       # Entrada: python -m thbot e PyInstaller
│   ├── app.py            # Aplicação, campanhas e automação
│   └── ui.py             # Tema e componentes visuais reutilizáveis
├── assets/
│   └── thbot_icone.ico
├── packaging/
│   └── thbot.spec        # Configuração do executável
├── docs/
│   ├── melhorias.md      # Sugestões de organização interna
│   └── validacao.md      # Verificações da reorganização
├── .gitignore
├── README.md
└── requirements.txt
```

`.venv/`, `build/`, `dist/`, `data/` e `exports/` são diretórios locais ignorados pelo Git. Banco e sessões também são ignorados.

## Manutenção

As oportunidades de refatoração estão em [docs/melhorias.md](docs/melhorias.md), e os testes realizados estão em [docs/validacao.md](docs/validacao.md).

## Licença

A escolha da licença está pendente do titular. O arquivo `LICENSE` será adicionado após essa definição.
