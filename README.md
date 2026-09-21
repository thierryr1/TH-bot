# Thbot

Aplicação desktop em Python para enviar mensagens personalizadas pelo WhatsApp Web a partir de uma planilha Excel.

> Use somente contatos que autorizaram receber mensagens. O uso indevido pode resultar em bloqueios no WhatsApp e violações de privacidade.

## Recursos

- Interface em CustomTkinter com temas claro e noturno, cartões alinhados e tabelas nativas com divisórias entre colunas. O seletor de modo noturno fica no cabeçalho.
- Importa planilhas `.xlsx` e `.xls`.
- Personaliza mensagens com `{nome}` e `{telefone}`.
- Controla campanhas/lotes e evita reenvios dentro de uma campanha.
- Mantém histórico local de envios e permite exportação para Excel.
- Permite configurar DDI, navegador, timeout e intervalo variável entre envios.
- Mantém a sessão do WhatsApp Web localmente após a leitura inicial do QR Code.

## Requisitos

- Windows 10 ou superior.
- Python 3.10 ou superior.
- Acesso à internet e uma conta do WhatsApp.

## Instalação

No PowerShell, dentro da pasta do projeto:

```powershell
python -m pip install -r requirements.txt
playwright install chromium firefox
```

## Como executar

```powershell
python thbot.py
```

Na primeira utilização, será aberta uma janela do WhatsApp Web. Leia o QR Code para iniciar a sessão.

## Planilha de contatos

A planilha precisa ter uma coluna de telefone com DDD. Uma coluna de nome é opcional. Os números podem ser informados com ou sem pontuação e DDI; o programa os normaliza conforme o DDI configurado.

## Dados locais

Estes arquivos são criados ao lado do programa e não devem ser enviados ao GitHub:

- `thbot_envios.sqlite3`: campanhas e histórico de envios.
- `.whatsapp-playwright/`: sessão local do WhatsApp Web.

Faça cópias de segurança do banco SQLite se precisar preservar o histórico.

## Gerar executável portátil

Instale o Chromium do Playwright localmente e gere o executável:

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = "0"
playwright install chromium
python -m PyInstaller --clean --noconfirm thbot.spec
```

O arquivo será criado em `dist/thbot.exe`. Ele inclui o Chromium, portanto não exige Python ou navegador instalado no computador de destino.

Como o executável é grande, publique-o em uma GitHub Release, e não junto ao código no repositório.

## Estrutura

```text
thbot/
├── thbot.py          # Aplicação
├── thbot_icone.ico   # Ícone
├── requirements.txt  # Dependências de execução
├── thbot.spec        # Configuração do PyInstaller
├── .gitignore        # Arquivos locais e gerados ignorados
└── README.md         # Documentação
```
