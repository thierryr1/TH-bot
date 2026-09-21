import os
import re
import sys
import queue
import random
import sqlite3
import threading
import unicodedata
from datetime import datetime, timezone

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, simpledialog

import pandas as pd

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_DISPONIVEL = True
except ImportError:
    PLAYWRIGHT_DISPONIVEL = False


MENSAGEM_PADRAO = (
    "Olá, {nome}!\n\n"
    "Tudo bem?\n\n"
    "Temos uma novidade especial para você!\n\n"
    "Aproveite 😉"
)

CODIGO_PAIS_PADRAO = "55"
TIMEOUT_PADRAO = 45
DELAY_MIN_PADRAO = 5
DELAY_MAX_PADRAO = 25
ARQUIVO_BANCO_ENVIOS = "thbot_envios.sqlite3"


def formatar_numero(numero: str, codigo_pais: str) -> str | None:
    """
    Recebe um número no formato "xx xxxxx-xxxx" (DDD + número, sem DDI) e
    devolve no formato internacional E.164, ex: "+5585999990001".
    Retorna None se a quantidade de dígitos não bater.
    """
    apenas_digitos = re.sub(r"\D", "", str(numero))

    if apenas_digitos.startswith(codigo_pais) and len(apenas_digitos) in (12, 13):
        apenas_digitos = apenas_digitos[len(codigo_pais):]

    if len(apenas_digitos) not in (10, 11):
        return None

    return f"+{codigo_pais}{apenas_digitos}"

def caminho_recurso(nome):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, nome)

    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        nome
    )


def diretorio_dados():
    """Retorna uma pasta gravável ao lado do programa distribuído.

    No executável gerado pelo PyInstaller, ``__file__`` aponta para uma pasta
    temporária. Usar o caminho do executável preserva o histórico e o login do
    WhatsApp entre aberturas do programa.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

class WhatsAppThbot(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("WhatsApp Thbot")
        self.iconbitmap(caminho_recurso("thbot_icone.ico"))
        self.geometry("1500x950")
        self.minsize(1150, 700)

        self._configurar_estilo()

        self.df = None
        self.caminho_planilha = tk.StringVar(value="")
        self.coluna_telefone = tk.StringVar(value="")
        self.coluna_nome = tk.StringVar(value="")
        self.campanha_var = tk.StringVar(value="")

        self.delay_min_var = tk.IntVar(value=DELAY_MIN_PADRAO)
        self.delay_max_var = tk.IntVar(value=DELAY_MAX_PADRAO)
        self.quantidade_var = tk.IntVar(value=0)

        self.codigo_pais_var = tk.StringVar(value=CODIGO_PAIS_PADRAO)
        self.timeout_var = tk.IntVar(value=TIMEOUT_PADRAO)
        self.navegador_var = tk.StringVar(value="Chromium")
        self._playwright = None
        self._contexto_navegador = None

        self.enviados = 0
        self.falhas = 0
        self.total = 0
        self.historico = []

        self.fila_eventos = queue.Queue()
        self.thread_envio = None
        self.evento_pausa = threading.Event()
        self.evento_parar = threading.Event()

        self._inicializar_banco_envios()

        self._construir_layout()
        self._processar_fila()
        self.protocol("WM_DELETE_WINDOW", self._ao_fechar_janela)

    def _ao_fechar_janela(self):
        # O contexto é aberto pela thread de envio. Não o fechamos aqui para
        # evitar concorrência com uma operação do Playwright em andamento.
        self.destroy()

    def _configurar_estilo(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TNotebook.Tab", padding=(16, 8))
        style.configure("Card.TLabelframe", padding=12)
        style.configure("Card.TLabelframe.Label", font=("Segoe UI", 10, "bold"))
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))
        style.configure("Treeview", rowheight=26)
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

    def _construir_layout(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(10, 0))

        self.aba_envio = ttk.Frame(self.notebook)
        self.aba_historico = ttk.Frame(self.notebook)
        self.aba_campanhas = ttk.Frame(self.notebook)
        self.aba_config = ttk.Frame(self.notebook)

        self.notebook.add(self.aba_envio, text="  🛫  Envio de Mensagens  ")
        self.notebook.add(self.aba_historico, text="  🕘  Histórico de Envios  ")
        self.notebook.add(self.aba_campanhas, text="  📋  Campanhas  ")
        self.notebook.add(self.aba_config, text="  ⚙️  Configurações  ")

        self._montar_aba_envio()
        self._montar_aba_historico()
        self._montar_aba_campanhas()
        self._montar_aba_config()

        self.status_var = tk.StringVar(value="Pronto para iniciar.")
        barra_status = ttk.Frame(self, relief="sunken")
        barra_status.pack(fill="x", side="bottom")
        ttk.Label(barra_status, textvariable=self.status_var, padding=(10, 4)).pack(side="left")

    def _montar_aba_envio(self):
        container = ttk.Frame(self.aba_envio)
        container.pack(fill="both", expand=True, padx=10, pady=10)
        container.columnconfigure(0, weight=55)
        container.columnconfigure(1, weight=45)
        container.rowconfigure(0, weight=1)

        col_esquerda = ttk.Frame(container)
        col_esquerda.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        col_direita = ttk.Frame(container)
        col_direita.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        self._secao_planilha(col_esquerda)
        self._secao_mensagem(col_esquerda)
        self._secao_delay_quantidade_controles(col_esquerda)
        self._secao_progresso_resumo(col_esquerda)

        self._secao_historico_lateral(col_direita)

    def _secao_planilha(self, parent):
        frame_topo = ttk.Frame(parent)
        frame_topo.pack(fill="x", pady=(0, 8))
        frame_topo.columnconfigure(0, weight=1)
        frame_topo.columnconfigure(1, weight=1)

        bloco1 = ttk.Labelframe(frame_topo, text="1. Selecionar Planilha", style="Card.TLabelframe")
        bloco1.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        linha = ttk.Frame(bloco1)
        linha.pack(fill="x")
        entrada = ttk.Entry(linha, textvariable=self.caminho_planilha, state="readonly")
        entrada.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ttk.Button(linha, text="Selecionar...", command=self._selecionar_planilha).pack(side="left")

        ttk.Label(
            bloco1,
            text="ℹ️  A planilha deve conter uma coluna de telefone com DDD.",
            foreground="#666666",
            wraplength=260,
        ).pack(anchor="w", pady=(8, 0))

        bloco2 = ttk.Labelframe(frame_topo, text="2. Selecionar Colunas", style="Card.TLabelframe")
        bloco2.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        linha_tel = ttk.Frame(bloco2)
        linha_tel.pack(fill="x", pady=(0, 6))
        ttk.Label(linha_tel, text="Coluna Telefone:").pack(side="left")
        self.combo_telefone = ttk.Combobox(
            linha_tel, textvariable=self.coluna_telefone, state="readonly", width=16
        )
        self.combo_telefone.pack(side="right")

        linha_nome = ttk.Frame(bloco2)
        linha_nome.pack(fill="x")
        ttk.Label(linha_nome, text="Coluna Nome (opcional):").pack(side="left")
        self.combo_nome = ttk.Combobox(
            linha_nome, textvariable=self.coluna_nome, state="readonly", width=16
        )
        self.combo_nome.pack(side="right")

    def _secao_mensagem(self, parent):
        bloco = ttk.Labelframe(parent, text="3. Mensagem", style="Card.TLabelframe")
        bloco.pack(fill="both", expand=False, pady=(0, 8))

        self.texto_mensagem = tk.Text(bloco, height=9, wrap="word", font=("Segoe UI", 10))
        self.texto_mensagem.pack(fill="both", expand=True)
        self.texto_mensagem.insert("1.0", MENSAGEM_PADRAO)

        rodape = ttk.Frame(bloco)
        rodape.pack(fill="x", pady=(8, 0))

        self.menubtn_variaveis = ttk.Menubutton(rodape, text="Inserir variável  ▾")
        self.menu_variaveis = tk.Menu(self.menubtn_variaveis, tearoff=False)
        self.menubtn_variaveis["menu"] = self.menu_variaveis
        self.menubtn_variaveis.pack(side="left")
        self._atualizar_menu_variaveis()

        ttk.Label(rodape, text="Campanha / lote (opcional):").pack(side="left", padx=(20, 6))
        self.combo_campanha = ttk.Combobox(
            rodape,
            textvariable=self.campanha_var,
            width=28,
            postcommand=self._atualizar_lista_campanhas,
        )
        self.combo_campanha.pack(side="left")
        menu_campanha = tk.Menu(rodape, tearoff=False)
        menu_campanha.add_command(label="Criar campanha", command=self._nova_campanha)
        menu_campanha.add_command(label="Excluir campanha", command=self._excluir_campanha)
        acoes_campanha = ttk.Menubutton(rodape, text="", width=2)
        acoes_campanha["menu"] = menu_campanha
        acoes_campanha.pack(side="left", padx=(6, 0))
        ttk.Label(rodape, text="Deixe vazio para permitir reenvios.", foreground="#666666").pack(side="left", padx=(6, 0))

    def _inserir_variavel(self, variavel: str):
        self.texto_mensagem.insert(tk.INSERT, variavel)
        self.texto_mensagem.focus_set()

    def _atualizar_menu_variaveis(self):
        self.menu_variaveis.delete(0, "end")
        variaveis = ["nome", "telefone"]
        if self.df is not None:
            variaveis.extend(str(coluna) for coluna in self.df.columns)
        for variavel in dict.fromkeys(variaveis):
            marcador = f"{{{variavel}}}"
            self.menu_variaveis.add_command(
                label=marcador,
                command=lambda marcador=marcador: self._inserir_variavel(marcador),
            )

    def _nova_campanha(self):
        nome = simpledialog.askstring(
            "Nova campanha",
            "Informe o nome da nova campanha/lote:",
            parent=self,
        )
        nome = (nome or "").strip()
        if not nome:
            return

        with sqlite3.connect(self._caminho_banco_envios()) as conexao:
            conexao.execute(
                "INSERT OR IGNORE INTO campanhas (nome, criada_em) VALUES (?, ?)",
                (nome, datetime.now().isoformat(timespec="seconds")),
            )
        self.campanha_var.set(nome)
        self._atualizar_lista_campanhas()
        self.campanha_consulta_var.set(nome)
        self._carregar_envios_campanha()

    def _excluir_campanha(self):
        campanha = self.campanha_var.get().strip()
        if not campanha:
            messagebox.showwarning(
                "Nenhuma campanha selecionada",
                "Selecione uma campanha antes de excluí-la.",
                parent=self,
            )
            return

        confirmar = messagebox.askyesno(
            "Excluir campanha",
            f"Excluir a campanha '{campanha}' e o histórico de envios dela?\n\n"
            "Essa ação não poderá ser desfeita.",
            parent=self,
        )
        if not confirmar:
            return

        with sqlite3.connect(self._caminho_banco_envios()) as conexao:
            conexao.execute("DELETE FROM envios_por_campanha WHERE campanha = ?", (campanha,))
            conexao.execute("DELETE FROM campanhas WHERE nome = ?", (campanha,))

        self.campanha_var.set("")
        if self.campanha_consulta_var.get() == campanha:
            self.campanha_consulta_var.set("")
        self._atualizar_lista_campanhas()
        self._carregar_envios_campanha()
        self.status_var.set(f"Campanha '{campanha}' excluída.")

    @staticmethod
    def _caminho_banco_envios():
        return os.path.join(diretorio_dados(), ARQUIVO_BANCO_ENVIOS)

    def _inicializar_banco_envios(self):
        with sqlite3.connect(self._caminho_banco_envios()) as conexao:
            conexao.execute(
                """
                CREATE TABLE IF NOT EXISTS campanhas (
                    nome TEXT PRIMARY KEY COLLATE NOCASE,
                    criada_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conexao.execute(
                """
                CREATE TABLE IF NOT EXISTS envios_por_campanha (
                    campanha TEXT NOT NULL COLLATE NOCASE,
                    telefone TEXT NOT NULL,
                    nome TEXT NOT NULL DEFAULT '',
                    enviado_em TEXT NOT NULL,
                    PRIMARY KEY (campanha, telefone)
                )
                """
            )
            colunas = {linha[1] for linha in conexao.execute("PRAGMA table_info(envios_por_campanha)")}
            if "nome" not in colunas:
                conexao.execute("ALTER TABLE envios_por_campanha ADD COLUMN nome TEXT NOT NULL DEFAULT ''")

    def _atualizar_lista_campanhas(self):
        with sqlite3.connect(self._caminho_banco_envios()) as conexao:
            campanhas = [linha[0] for linha in conexao.execute(
                "SELECT nome FROM campanhas ORDER BY nome COLLATE NOCASE"
            )]
        self.combo_campanha["values"] = campanhas
        if hasattr(self, "combo_campanha_consulta"):
            self.combo_campanha_consulta["values"] = campanhas

    def _telefones_enviados_na_campanha(self, campanha: str) -> set[str]:
        with sqlite3.connect(self._caminho_banco_envios()) as conexao:
            return {
                linha[0] for linha in conexao.execute(
                    "SELECT telefone FROM envios_por_campanha WHERE campanha = ?",
                    (campanha,),
                )
            }

    def _registrar_envio_na_campanha(self, campanha: str, telefone: str, nome: str):
        with sqlite3.connect(self._caminho_banco_envios()) as conexao:
            conexao.execute(
                "INSERT OR IGNORE INTO campanhas (nome, criada_em) VALUES (?, ?)",
                (campanha, datetime.now().isoformat(timespec="seconds")),
            )
            conexao.execute(
                """
                INSERT OR IGNORE INTO envios_por_campanha (campanha, telefone, nome, enviado_em)
                VALUES (?, ?, ?, ?)
                """,
                (campanha, telefone, nome, datetime.now().isoformat(timespec="seconds")),
            )

    def _secao_delay_quantidade_controles(self, parent):
        linha = ttk.Frame(parent)
        linha.pack(fill="x", pady=(0, 8))
        linha.columnconfigure(0, weight=1)
        linha.columnconfigure(1, weight=1)
        linha.columnconfigure(2, weight=1)

        bloco4 = ttk.Labelframe(linha, text="4. Delay entre envios", style="Card.TLabelframe")
        bloco4.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        sub = ttk.Frame(bloco4)
        sub.pack(anchor="w")
        ttk.Label(sub, text="De").pack(side="left")
        ttk.Spinbox(sub, from_=5, to=600, textvariable=self.delay_min_var, width=5).pack(side="left", padx=(4, 8))
        ttk.Label(sub, text="até").pack(side="left")
        ttk.Spinbox(sub, from_=5, to=600, textvariable=self.delay_max_var, width=5).pack(side="left", padx=(4, 0))
        ttk.Label(sub, text=" segundos").pack(side="left")
        ttk.Label(bloco4, text="Um tempo aleatório do intervalo será usado após cada envio.", foreground="#666666",
                  wraplength=160).pack(anchor="w", pady=(6, 0))

        bloco5 = ttk.Labelframe(linha, text="5. Quantidade (opcional)", style="Card.TLabelframe")
        bloco5.grid(row=0, column=1, sticky="nsew", padx=6)
        ttk.Spinbox(bloco5, from_=0, to=100000, textvariable=self.quantidade_var, width=8).pack(anchor="w")
        ttk.Label(bloco5, text="0 = Enviar para todos os contatos.", foreground="#666666",
                  wraplength=180).pack(anchor="w", pady=(6, 0))

        bloco6 = ttk.Labelframe(linha, text="6. Controles", style="Card.TLabelframe")
        bloco6.grid(row=0, column=2, sticky="nsew", padx=(6, 0))
        sub6 = ttk.Frame(bloco6)
        sub6.pack(anchor="w")

        self.btn_iniciar = ttk.Button(sub6, text="▶  Iniciar", style="Accent.TButton", command=self._iniciar_envio)
        self.btn_iniciar.pack(side="left", padx=(0, 4))

        self.btn_pausar = ttk.Button(sub6, text="⏸  Pausar", command=self._alternar_pausa, state="disabled")
        self.btn_pausar.pack(side="left", padx=4)

        self.btn_parar = ttk.Button(sub6, text="⏹  Parar", command=self._parar_envio, state="disabled")
        self.btn_parar.pack(side="left", padx=(4, 0))

    def _secao_progresso_resumo(self, parent):
        linha = ttk.Frame(parent)
        linha.pack(fill="both", expand=True)
        linha.columnconfigure(0, weight=65)
        linha.columnconfigure(1, weight=35)

        bloco_prog = ttk.Labelframe(linha, text="Progresso do envio", style="Card.TLabelframe")
        bloco_prog.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        self.barra_progresso = ttk.Progressbar(bloco_prog, orient="horizontal", mode="determinate")
        self.barra_progresso.pack(fill="x", pady=(4, 4))

        self.label_percentual = ttk.Label(bloco_prog, text="0%")
        self.label_percentual.pack(anchor="center")

        self.label_enviando = ttk.Label(bloco_prog, text="", foreground="#444444")
        self.label_enviando.pack(anchor="w", pady=(8, 0))

        bloco_resumo = ttk.Labelframe(linha, text="Resumo", style="Card.TLabelframe")
        bloco_resumo.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        self.label_enviados = self._linha_resumo(bloco_resumo, "Enviados:", "0", "#1a7f37")
        self.label_falhas = self._linha_resumo(bloco_resumo, "Falhas:", "0", "#c62828")
        self.label_restantes = self._linha_resumo(bloco_resumo, "Restantes:", "0", "#b26a00")
        self.label_total = self._linha_resumo(bloco_resumo, "Total:", "0", "#222222")

    def _linha_resumo(self, parent, rotulo, valor_inicial, cor):
        linha = ttk.Frame(parent)
        linha.pack(fill="x", pady=2)
        ttk.Label(linha, text=rotulo).pack(side="left")
        lbl_valor = ttk.Label(linha, text=valor_inicial, foreground=cor, font=("Segoe UI", 10, "bold"))
        lbl_valor.pack(side="right")
        return lbl_valor

    def _secao_historico_lateral(self, parent):
        bloco = ttk.Labelframe(parent, text="Histórico de envios", style="Card.TLabelframe")
        bloco.pack(fill="both", expand=True, pady=(0, 8))

        colunas = ("data_hora", "telefone", "nome", "status", "erro")
        self.tree_lateral = self._criar_treeview(bloco, colunas)

        bloco_log = ttk.Labelframe(parent, text="Log de atividades", style="Card.TLabelframe")
        bloco_log.pack(fill="both", expand=True)

        self.texto_log = scrolledtext.ScrolledText(bloco_log, height=10, state="disabled", font=("Consolas", 9))
        self.texto_log.pack(fill="both", expand=True)

        rodape = ttk.Frame(parent)
        rodape.pack(fill="x", pady=(8, 0))
        ttk.Button(rodape, text="📊  Exportar para Excel", command=self._exportar_excel).pack(side="left")
        ttk.Button(rodape, text="🗑  Limpar log", command=self._limpar_log).pack(side="right")

    def _criar_treeview(self, parent, colunas):
        rotulos = {
            "data_hora": "Data/Hora",
            "telefone": "Telefone",
            "nome": "Nome",
            "status": "Status",
            "erro": "Erro",
        }
        larguras = {"data_hora": 130, "telefone": 110, "nome": 90, "status": 80, "erro": 120}

        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)

        tree = ttk.Treeview(frame, columns=colunas, show="headings", height=8)
        for c in colunas:
            tree.heading(c, text=rotulos[c])
            tree.column(c, width=larguras[c], anchor="w")

        scroll_y = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll_y.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll_y.pack(side="right", fill="y")

        tree.tag_configure("ok", foreground="#1a7f37")
        tree.tag_configure("erro", foreground="#c62828")
        return tree

    def _montar_aba_historico(self):
        container = ttk.Frame(self.aba_historico)
        container.pack(fill="both", expand=True, padx=10, pady=10)

        ttk.Label(container, text="Histórico completo da sessão", font=("Segoe UI", 11, "bold")).pack(
            anchor="w", pady=(0, 8)
        )

        colunas = ("data_hora", "telefone", "nome", "status", "erro")
        self.tree_historico_completo = self._criar_treeview(container, colunas)

        rodape = ttk.Frame(container)
        rodape.pack(fill="x", pady=(8, 0))
        ttk.Button(rodape, text="📊  Exportar para Excel", command=self._exportar_excel).pack(side="left")
        ttk.Button(rodape, text="🗑  Limpar histórico", command=self._limpar_log).pack(side="right")

    def _montar_aba_campanhas(self):
        container = ttk.Frame(self.aba_campanhas)
        container.pack(fill="both", expand=True, padx=10, pady=10)

        filtro = ttk.Labelframe(container, text="Consultar campanha", style="Card.TLabelframe")
        filtro.pack(fill="x", pady=(0, 8))

        self.campanha_consulta_var = tk.StringVar()
        ttk.Label(filtro, text="Campanha:").pack(side="left")
        self.combo_campanha_consulta = ttk.Combobox(
            filtro,
            textvariable=self.campanha_consulta_var,
            state="readonly",
            width=35,
            postcommand=self._atualizar_lista_campanhas,
        )
        self.combo_campanha_consulta.pack(side="left", padx=(8, 8))
        self.combo_campanha_consulta.bind("<<ComboboxSelected>>", self._carregar_envios_campanha)
        ttk.Button(filtro, text="Atualizar", command=self._carregar_envios_campanha).pack(side="left")
        ttk.Button(
            filtro,
            text="Importar planilha",
            command=self._importar_registros_campanha,
        ).pack(side="left", padx=(8, 0))

        self.pesquisa_campanha_var = tk.StringVar()
        ttk.Label(filtro, text="Pesquisar:").pack(side="left", padx=(24, 6))
        entrada_pesquisa = ttk.Entry(filtro, textvariable=self.pesquisa_campanha_var, width=28)
        entrada_pesquisa.pack(side="left")
        self.pesquisa_campanha_var.trace_add("write", self._filtrar_envios_campanha)
        ttk.Button(filtro, text="Limpar", command=self._limpar_pesquisa_campanha).pack(side="left", padx=(6, 0))

        self.resumo_campanha_var = tk.StringVar(value="Selecione uma campanha para consultar os envios.")
        ttk.Label(container, textvariable=self.resumo_campanha_var, font=("Segoe UI", 10, "bold")).pack(
            anchor="w", pady=(0, 8)
        )

        self.tree_campanha = self._criar_treeview(
            container, ("data_hora", "telefone", "nome")
        )
        self.tree_campanha.configure(selectmode="extended")
        self.tree_campanha.bind("<Delete>", self._excluir_registro_campanha)
        self.envios_campanha = []
        self.coluna_ordenacao_campanha = None
        self.ordem_decrescente_campanha = False
        for coluna in ("data_hora", "telefone", "nome"):
            self.tree_campanha.heading(
                coluna,
                command=lambda coluna=coluna: self._ordenar_envios_campanha(coluna),
            )

        self._atualizar_lista_campanhas()

    def _carregar_envios_campanha(self, _evento=None):
        campanha = self.campanha_consulta_var.get().strip()
        if not campanha:
            self.envios_campanha = []
            self.resumo_campanha_var.set("Selecione uma campanha para consultar os envios.")
            self._exibir_envios_campanha()
            return

        with sqlite3.connect(self._caminho_banco_envios()) as conexao:
            campanha_info = conexao.execute(
                "SELECT criada_em FROM campanhas WHERE nome = ?", (campanha,)
            ).fetchone()
            envios = list(conexao.execute(
                """
                SELECT enviado_em, telefone, nome
                FROM envios_por_campanha
                WHERE campanha = ?
                ORDER BY enviado_em DESC
                """,
                (campanha,),
            ))

        criada_em = self._formatar_data_criacao(campanha_info[0]) if campanha_info else "-"
        self.resumo_campanha_var.set(
            f"{campanha} — {len(envios)} contato(s) enviado(s) — criada em {criada_em}"
        )
        self.envios_campanha = []
        for enviado_em, telefone, nome in envios:
            try:
                data_hora = datetime.fromisoformat(enviado_em).strftime("%d/%m/%Y %H:%M:%S")
            except ValueError:
                data_hora = enviado_em
            self.envios_campanha.append({
                "data_hora": data_hora,
                "ordenacao_data": enviado_em,
                "telefone": telefone,
                "nome": nome,
            })
        self._exibir_envios_campanha()

    def _importar_registros_campanha(self):
        campanha = self.campanha_consulta_var.get().strip()
        if not campanha:
            messagebox.showwarning(
                "Selecione uma campanha",
                "Selecione a campanha que receberá os contatos importados.",
                parent=self,
            )
            return

        caminho = filedialog.askopenfilename(
            title="Importar registros enviados",
            filetypes=[("Planilhas Excel", "*.xlsx *.xls"), ("Todos os arquivos", "*.*")],
        )
        if not caminho:
            return

        try:
            planilha = pd.read_excel(caminho, dtype=str).fillna("")
        except Exception as exc:
            messagebox.showerror("Erro ao abrir planilha", f"Não foi possível ler o arquivo:\n{exc}", parent=self)
            return

        if planilha.empty:
            messagebox.showwarning("Planilha vazia", "A planilha não possui contatos para importar.", parent=self)
            return

        planilha.columns = [str(coluna) for coluna in planilha.columns]
        colunas = list(planilha.columns)
        coluna_telefone = self._adivinhar_coluna(
            colunas, ["telefone", "numero", "número", "fone", "celular"], usar_primeira=False
        )
        coluna_nome = self._adivinhar_coluna(colunas, ["nome", "cliente"], usar_primeira=False)
        if not coluna_telefone:
            messagebox.showerror(
                "Coluna de telefone não identificada",
                "A planilha precisa ter uma coluna com nome como Telefone, Número, Fone ou Celular.",
                parent=self,
            )
            return

        codigo_pais = self.codigo_pais_var.get().strip()
        importados = duplicados = invalidos = 0
        horario_importacao = datetime.now().isoformat(timespec="seconds")

        with sqlite3.connect(self._caminho_banco_envios()) as conexao:
            conexao.execute(
                "INSERT OR IGNORE INTO campanhas (nome, criada_em) VALUES (?, ?)",
                (campanha, horario_importacao),
            )
            for _, contato in planilha.iterrows():
                telefone = formatar_numero(contato[coluna_telefone], codigo_pais)
                if not telefone:
                    invalidos += 1
                    continue
                nome = str(contato[coluna_nome]).strip() if coluna_nome else ""
                cursor = conexao.execute(
                    """
                    INSERT OR IGNORE INTO envios_por_campanha (campanha, telefone, nome, enviado_em)
                    VALUES (?, ?, ?, ?)
                    """,
                    (campanha, telefone, nome, horario_importacao),
                )
                if cursor.rowcount:
                    importados += 1
                else:
                    duplicados += 1

        self._carregar_envios_campanha()
        self.status_var.set(f"{importados} contato(s) importado(s) na campanha '{campanha}'.")
        messagebox.showinfo(
            "Importação concluída",
            f"Campanha: {campanha}\n\n"
            f"Importados como enviados: {importados}\n"
            f"Já existentes na campanha: {duplicados}\n"
            f"Números inválidos ignorados: {invalidos}",
            parent=self,
        )

    def _filtrar_envios_campanha(self, *_args):
        if hasattr(self, "tree_campanha"):
            self._exibir_envios_campanha()

    def _excluir_registro_campanha(self, _evento=None):
        selecionado = self.tree_campanha.selection()
        campanha = self.campanha_consulta_var.get().strip()
        if not selecionado or not campanha:
            return

        telefones = [self.tree_campanha.item(item, "values")[1] for item in selecionado]
        quantidade = len(telefones)
        descricao = (
            f"Excluir {quantidade} contatos selecionados"
            if quantidade > 1
            else f"Excluir o contato {telefones[0]}"
        )
        confirmar = messagebox.askyesno(
            "Excluir registro",
            f"{descricao} dos registros da campanha '{campanha}'?",
            parent=self,
        )
        if not confirmar:
            return

        with sqlite3.connect(self._caminho_banco_envios()) as conexao:
            conexao.executemany(
                "DELETE FROM envios_por_campanha WHERE campanha = ? AND telefone = ?",
                [(campanha, telefone) for telefone in telefones],
            )
        self._carregar_envios_campanha()
        self.status_var.set(f"{quantidade} registro(s) excluído(s) da campanha '{campanha}'.")

    def _limpar_pesquisa_campanha(self):
        self.pesquisa_campanha_var.set("")

    def _ordenar_envios_campanha(self, coluna: str):
        if coluna == self.coluna_ordenacao_campanha:
            self.ordem_decrescente_campanha = not self.ordem_decrescente_campanha
        else:
            self.coluna_ordenacao_campanha = coluna
            self.ordem_decrescente_campanha = False
        self._exibir_envios_campanha()

    def _exibir_envios_campanha(self):
        busca = self.pesquisa_campanha_var.get().strip().casefold()
        envios = [
            envio for envio in self.envios_campanha
            if not busca or busca in f"{envio['telefone']} {envio['nome']}".casefold()
        ]

        if self.coluna_ordenacao_campanha:
            campo = "ordenacao_data" if self.coluna_ordenacao_campanha == "data_hora" else self.coluna_ordenacao_campanha
            envios.sort(
                key=lambda envio: str(envio[campo]).casefold(),
                reverse=self.ordem_decrescente_campanha,
            )

        for item in self.tree_campanha.get_children():
            self.tree_campanha.delete(item)
        for envio in envios:
            self.tree_campanha.insert(
                "", "end", values=(envio["data_hora"], envio["telefone"], envio["nome"])
            )

    @staticmethod
    def _formatar_data_criacao(valor: str) -> str:
        try:
            if "T" in valor:
                return datetime.fromisoformat(valor).strftime("%d/%m/%Y %H:%M:%S")
            return (
                datetime.strptime(valor, "%Y-%m-%d %H:%M:%S")
                .replace(tzinfo=timezone.utc)
                .astimezone()
                .strftime("%d/%m/%Y %H:%M:%S")
            )
        except ValueError:
            return valor

    def _montar_aba_config(self):
        container = ttk.Frame(self.aba_config)
        container.pack(fill="both", expand=True, padx=10, pady=10)

        bloco = ttk.Labelframe(container, text="Configurações de envio", style="Card.TLabelframe")
        bloco.pack(fill="x", anchor="n")

        linha1 = ttk.Frame(bloco)
        linha1.pack(fill="x", pady=6)
        ttk.Label(linha1, text="Código do país (DDI):", width=32).pack(side="left")
        ttk.Entry(linha1, textvariable=self.codigo_pais_var, width=8).pack(side="left")
        ttk.Label(linha1, text="  Ex: 55 para o Brasil.", foreground="#666666").pack(side="left")

        linha_browser = ttk.Frame(bloco)
        linha_browser.pack(fill="x", pady=6)
        ttk.Label(linha_browser, text="Navegador:", width=32).pack(side="left")
        ttk.Combobox(
            linha_browser, textvariable=self.navegador_var, state="readonly",
            values=("Chromium", "Google Chrome", "Firefox"), width=18,
        ).pack(side="left")
        ttk.Label(linha_browser, text="  A sessão de login é salva localmente.", foreground="#666666").pack(side="left")

        linha2 = ttk.Frame(bloco)
        linha2.pack(fill="x", pady=6)
        ttk.Label(linha2, text="Limite de espera por evento (s):", width=32).pack(side="left")
        ttk.Spinbox(linha2, from_=10, to=180, textvariable=self.timeout_var, width=8).pack(side="left")
        ttk.Label(linha2, text="  Usado apenas como limite; não há espera fixa.",
                  foreground="#666666").pack(side="left")

        if not PLAYWRIGHT_DISPONIVEL:
            aviso = ttk.Label(
                container,
                text=(
                    "⚠️  A biblioteca 'playwright' não está instalada. Instale com:\n"
                    "pip install playwright\nplaywright install chromium firefox"
                ),
                foreground="#c62828",
            )
            aviso.pack(anchor="w", pady=(16, 0))

    def _selecionar_planilha(self):
        caminho = filedialog.askopenfilename(
            title="Selecionar planilha de clientes",
            filetypes=[("Planilhas Excel", "*.xlsx *.xls"), ("Todos os arquivos", "*.*")],
        )
        if not caminho:
            return

        try:
            df = pd.read_excel(caminho, dtype=str)
        except Exception as e:
            messagebox.showerror("Erro ao abrir planilha", f"Não foi possível ler o arquivo:\n{e}")
            return

        self.df = df
        self.df.columns = [str(coluna) for coluna in self.df.columns]
        self.caminho_planilha.set(os.path.basename(caminho))
        self._caminho_completo_planilha = caminho

        colunas = list(self.df.columns)
        self.combo_telefone["values"] = colunas
        self.combo_nome["values"] = colunas

        self.coluna_telefone.set(self._adivinhar_coluna(colunas, ["telefone", "numero", "número", "fone", "celular"]))
        self.coluna_nome.set(self._adivinhar_coluna(colunas, ["nome", "cliente"]))
        self._atualizar_menu_variaveis()

        self.status_var.set(f"Planilha carregada: {len(df)} contato(s) encontrados.")

    @staticmethod
    def _adivinhar_coluna(colunas, candidatos, usar_primeira=True):
        candidatos_normalizados = {
            unicodedata.normalize("NFD", candidato).encode("ascii", "ignore").decode().lower()
            for candidato in candidatos
        }
        for c in colunas:
            nome_normalizado = unicodedata.normalize("NFD", str(c)).encode("ascii", "ignore").decode().lower()
            if nome_normalizado.strip() in candidatos_normalizados:
                return c
        for c in colunas:
            nome_normalizado = unicodedata.normalize("NFD", str(c)).encode("ascii", "ignore").decode().lower()
            if any(candidato in nome_normalizado for candidato in candidatos_normalizados):
                return c
        return colunas[0] if usar_primeira and colunas else ""

    def _iniciar_envio(self):
        if self.df is None:
            messagebox.showwarning("Planilha não selecionada", "Selecione uma planilha antes de iniciar.")
            return

        if not self.coluna_telefone.get():
            messagebox.showwarning("Coluna não selecionada", "Selecione a coluna de telefone.")
            return

        if not PLAYWRIGHT_DISPONIVEL:
            messagebox.showerror(
                "Dependência ausente",
                "A biblioteca 'playwright' não está instalada.\n"
                "Instale com: pip install playwright\nplaywright install chromium firefox",
            )
            return

        template_mensagem = self.texto_mensagem.get("1.0", "end-1c").strip()
        if not template_mensagem:
            messagebox.showwarning("Mensagem vazia", "Escreva a mensagem que será enviada.")
            return

        campanha = self.campanha_var.get().strip()

        try:
            delay_min = self.delay_min_var.get()
            delay_max = self.delay_max_var.get()
        except tk.TclError:
            messagebox.showwarning("Delay inválido", "Informe valores numéricos para o intervalo de delay.")
            return

        if delay_min < 5 or delay_max < 5 or delay_max < delay_min:
            messagebox.showwarning(
                "Intervalo de delay inválido",
                "Os valores devem ser de ao menos 5 segundos, e o valor inicial não pode ser maior que o final.",
            )
            return

        # Com campanha, telefones já confirmados nela (inclusive duplicados
        # na própria planilha) são ignorados. Sem campanha, o envio é livre.
        ja_enviados = self._telefones_enviados_na_campanha(campanha) if campanha else set()
        vistos_no_lote = set()
        ignorados = 0
        contatos = []
        for _, linha in self.df.iterrows():
            campos = {
                str(coluna): "" if pd.isna(valor) else str(valor).strip()
                for coluna, valor in linha.items()
            }
            tel = campos.get(self.coluna_telefone.get(), "")
            nome = campos.get(self.coluna_nome.get(), "") if self.coluna_nome.get() else ""
            if tel:
                telefone_formatado = formatar_numero(tel, self.codigo_pais_var.get().strip())
                if campanha and telefone_formatado and (telefone_formatado in ja_enviados or telefone_formatado in vistos_no_lote):
                    ignorados += 1
                    continue
                if campanha and telefone_formatado:
                    vistos_no_lote.add(telefone_formatado)
                contatos.append({"telefone": tel, "nome": nome or "Cliente", "campos": campos})

        if self.quantidade_var.get() and self.quantidade_var.get() > 0:
            contatos = contatos[: self.quantidade_var.get()]

        if not contatos:
            mensagem = "Todos os contatos válidos já receberam esta campanha." if ignorados else "Nenhum contato válido encontrado na planilha."
            messagebox.showwarning("Nenhum contato disponível", mensagem)
            return

        self.enviados = 0
        self.falhas = 0
        self.total = len(contatos)
        self._atualizar_resumo()
        self.barra_progresso["maximum"] = self.total
        self.barra_progresso["value"] = 0

        self.evento_pausa.clear()
        self.evento_parar.clear()

        self.btn_iniciar.config(state="disabled")
        self.btn_pausar.config(state="normal", text="⏸  Pausar")
        self.btn_parar.config(state="normal")
        if ignorados:
            self._adicionar_log(f"{datetime.now():%d/%m/%Y %H:%M:%S}  [i]  {ignorados} contato(s) ignorado(s): já receberam a campanha '{campanha}'.\n")
        self.status_var.set(f"Enviando campanha: {campanha}" if campanha else "Enviando mensagens (sem campanha)...")

        self.thread_envio = threading.Thread(
            target=self._executar_envio,
            args=(contatos, template_mensagem, self.codigo_pais_var.get().strip(),
                  self.timeout_var.get(), self.navegador_var.get(), delay_min, delay_max, campanha),
            daemon=True,
        )
        self.thread_envio.start()

    def _alternar_pausa(self):
        if self.evento_pausa.is_set():
            self.evento_pausa.clear()
            self.btn_pausar.config(text="⏸  Pausar")
            self.status_var.set("Envio retomado.")
        else:
            self.evento_pausa.set()
            self.btn_pausar.config(text="▶  Retomar")
            self.status_var.set("Envio pausado.")

    def _parar_envio(self):
        self.evento_parar.set()
        self.evento_pausa.clear()
        self.status_var.set("Parando envio...")
        self.btn_parar.config(state="disabled")
        self.btn_pausar.config(state="disabled")

    def _esperar_delay(self, delay: float) -> bool:
        """
        Espera 'delay' segundos em pequenos passos, verificando Parar a cada
        instante (para que clicar em Parar durante o delay seja imediato).
        Retorna False se o envio foi interrompido durante a espera.
        """
        passo = 0.1
        tempo_restante = delay
        while tempo_restante > 0:
            if self.evento_parar.is_set():
                return False
            self.evento_parar.wait(min(passo, tempo_restante))
            tempo_restante -= passo
        return True

    def _abrir_contexto_playwright(self, navegador: str):
        """Abre um contexto persistente para que o QR/login sobreviva às sessões."""
        # Perfis separados evitam misturar os formatos internos de Chromium e
        # Firefox. Cada navegador solicita QR Code apenas na primeira vez.
        perfil = os.path.join(
            diretorio_dados(), ".whatsapp-playwright",
            navegador.lower().replace(" ", "-"),
        )
        os.makedirs(perfil, exist_ok=True)
        self._playwright = sync_playwright().start()
        # Sem viewport emulado: o WhatsApp calcula a altura real da janela e
        # mantém a barra de digitação acima da barra de tarefas do Windows.
        opcoes = {"headless": False, "no_viewport": True}
        if navegador == "Firefox":
            contexto = self._playwright.firefox.launch_persistent_context(perfil, **opcoes)
        elif navegador == "Google Chrome":
            contexto = self._playwright.chromium.launch_persistent_context(
                perfil, channel="chrome", args=["--start-maximized"], **opcoes
            )
        else:
            contexto = self._playwright.chromium.launch_persistent_context(
                perfil, args=["--start-maximized"], **opcoes
            )
        contexto.set_default_timeout(45_000)
        self._contexto_navegador = contexto
        return contexto

    def _fechar_contexto_playwright(self, contexto):
        """Fecha o perfil persistente no fim do lote e libera seu bloqueio."""
        try:
            if contexto is not None:
                contexto.close()
        except Exception:
            # O navegador pode já ter sido fechado manualmente.
            pass
        finally:
            if self._contexto_navegador is contexto:
                self._contexto_navegador = None
            if self._playwright is not None:
                try:
                    self._playwright.stop()
                except Exception:
                    pass
                self._playwright = None

    @staticmethod
    def _telefone_para_url(numero: str) -> str:
        return re.sub(r"\D", "", numero)

    def _aguardar_whatsapp_pronto(self, page):
        """Aguarda QR/login e o carregamento do WhatsApp antes do lote."""
        self.fila_eventos.put(("preparando", "Abrindo o WhatsApp Web..."))
        page.goto("https://web.whatsapp.com/", wait_until="domcontentloaded")

        # O QR Code não usa o timeout de cada mensagem: o usuário pode
        # escaneá-lo no próprio ritmo. Só seguimos com a lista disponível.
        seletor_pronto = "#pane-side [role='grid'], #pane-side [role='list'], [data-testid='chat-list'], [data-testid='default-user']"
        seletor_qr = "[data-ref], canvas[aria-label*='QR'], [data-testid='qrcode']"
        qr_informado = False
        while not self.evento_parar.is_set():
            estado = page.evaluate(
                """({pronto, qr}) => ({
                    pronto: Boolean(document.querySelector(pronto)),
                    qr: Boolean(document.querySelector(qr))
                })""",
                {"pronto": seletor_pronto, "qr": seletor_qr},
            )
            if estado["pronto"]:
                self.fila_eventos.put(("preparando", "WhatsApp Web pronto. Iniciando envios..."))
                return True
            if estado["qr"] and not qr_informado:
                self.fila_eventos.put(("preparando", "Leia o QR Code no navegador; aguardando o login..."))
                qr_informado = True
            page.wait_for_timeout(250)
        return False

    @staticmethod
    def _numero_inexistente_na_tela(page) -> bool:
        """Lê o aviso exibido pelo WhatsApp para número sem conta."""
        try:
            return page.evaluate(
                """() => {
                    const texto = (document.body?.innerText || '')
                        .normalize('NFD').replace(/[\\u0300-\\u036f]/g, '')
                        .toLowerCase();
                    return [
                        'numero de telefone compartilhado atraves da url e invalido',
                        'numero de telefone compartilhado via url e invalido',
                        'numero de telefone nao e valido',
                        'nao esta no whatsapp',
                        'este numero de telefone nao esta no whatsapp',
                        'esse numero de telefone nao esta no whatsapp',
                        'this phone number is not on whatsapp',
                        "this phone number isn't on whatsapp",
                        'phone number shared via url is invalid'
                    ].some(aviso => texto.includes(aviso));
                }"""
            )
        except Exception:
            return False

    def _enviar_via_whatsapp(self, page, numero, texto, timeout_ms):
        """Envia e confirma quando o WhatsApp limpa a caixa de texto.

        A URL abre diretamente a conversa. Os ``wait_for`` abaixo dependem
        exclusivamente de estados e elementos que o WhatsApp Web apresenta.
        """
        page.goto(f"https://web.whatsapp.com/send?phone={self._telefone_para_url(numero)}", wait_until="domcontentloaded")
        seletor_caixa = 'footer div[contenteditable="true"][role="textbox"]'
        caixa = page.locator(seletor_caixa).last
        try:
            estado = page.wait_for_function(
                """editorSelector => {
                    const texto = (document.body?.innerText || '')
                        .normalize('NFD').replace(/[\\u0300-\\u036f]/g, '')
                        .toLowerCase();
                    const avisos = [
                        'numero de telefone compartilhado atraves da url e invalido',
                        'numero de telefone compartilhado via url e invalido',
                        'numero de telefone nao e valido',
                        'nao esta no whatsapp',
                        'este numero de telefone nao esta no whatsapp',
                        'esse numero de telefone nao esta no whatsapp',
                        'this phone number is not on whatsapp',
                        "this phone number isn't on whatsapp",
                        'phone number shared via url is invalid'
                    ];
                    if (avisos.some(aviso => texto.includes(aviso))) return 'numero_inexistente';
                    const editor = document.querySelector(editorSelector);
                    const visivel = editor && editor.getClientRects().length > 0;
                    return visivel ? 'conversa_pronta' : false;
                }""",
                arg=seletor_caixa,
                timeout=timeout_ms,
            ).json_value()
            if estado == "numero_inexistente":
                raise RuntimeError("Número sem WhatsApp")
        except PlaywrightTimeoutError as exc:
            if self._numero_inexistente_na_tela(page):
                raise RuntimeError("Número sem WhatsApp") from exc
            raise RuntimeError("A conversa não ficou disponível; confirme o QR Code/login no WhatsApp Web") from exc

        caixa.click()
        page.keyboard.insert_text(texto)
        botao_enviar = page.locator(
            'button[aria-label="Enviar"], button[aria-label="Send"], button:has([data-icon="send"])'
        ).last
        botao_enviar.wait_for(state="visible", timeout=timeout_ms)
        botao_enviar.click()

        page.wait_for_function(
            """editorSelector => {
                const editor = document.querySelector(editorSelector);
                return Boolean(editor && !editor.innerText.trim());
            }""",
            arg='footer div[contenteditable="true"][role="textbox"]',
            timeout=timeout_ms,
        )

    def _executar_envio(self, contatos, template_mensagem, codigo_pais, timeout, navegador, delay_min, delay_max, campanha):
        """Roda em thread separada; Playwright nunca acessa widgets Tk."""
        contexto = None
        try:
            contexto = self._abrir_contexto_playwright(navegador)
            page = contexto.pages[0] if contexto.pages else contexto.new_page()
            timeout_ms = max(10, timeout) * 1000
            page.set_default_timeout(timeout_ms)
            if not self._aguardar_whatsapp_pronto(page):
                self._fechar_contexto_playwright(contexto)
                self.fila_eventos.put(("parado", None))
                return
        except Exception as exc:
            self._fechar_contexto_playwright(contexto)
            self.fila_eventos.put(("erro_geral", f"Não foi possível abrir {navegador}: {exc}"))
            return

        for indice, contato in enumerate(contatos, start=1):
            if self.evento_parar.is_set():
                self._fechar_contexto_playwright(contexto)
                self.fila_eventos.put(("parado", None))
                return

            while self.evento_pausa.is_set():
                if self.evento_parar.is_set():
                    self._fechar_contexto_playwright(contexto)
                    self.fila_eventos.put(("parado", None))
                    return
                self.evento_parar.wait(0.2)

            # Se somente a aba foi fechada, o contexto persistente ainda pode
            # criar outra e seguir. Se o navegador inteiro foi fechado, paramos
            # o lote em vez de registrar falhas repetidas para todos os contatos.
            try:
                if page.is_closed():
                    page = contexto.new_page()
                    page.set_default_timeout(timeout_ms)
            except Exception as exc:
                self._fechar_contexto_playwright(contexto)
                self.fila_eventos.put(("erro_geral", f"Navegador fechado durante o envio: {exc}"))
                return

            nome = contato["nome"]
            numero_formatado = formatar_numero(contato["telefone"], codigo_pais)

            if numero_formatado is None:
                self.fila_eventos.put((
                    "resultado", {
                        "telefone": contato["telefone"],
                        "nome": nome,
                        "status": "Falhou",
                        "erro": "Número inválido",
                        "campanha": campanha,
                        "enviando_label": f"{contato['telefone']} - {nome}",
                    }
                ))
                if indice < len(contatos):
                    if not self._esperar_delay(random.uniform(delay_min, delay_max)):
                        self._fechar_contexto_playwright(contexto)
                        self.fila_eventos.put(("parado", None))
                        return
                continue

            self.fila_eventos.put(("enviando", f"{numero_formatado} - {nome}"))

            valores_mensagem = {**contato["campos"], "nome": nome, "telefone": numero_formatado}
            texto = template_mensagem
            for campo, valor in valores_mensagem.items():
                texto = texto.replace(f"{{{campo}}}", valor)

            erro_msg = "-"
            status = "Enviado"
            try:
                self._enviar_via_whatsapp(page, numero_formatado, texto, timeout_ms)
            except Exception as e:
                status = "Falhou"
                erro_msg = str(e)

            self.fila_eventos.put((
                "resultado", {
                    "telefone": numero_formatado,
                    "nome": nome,
                    "status": status,
                    "erro": erro_msg,
                    "campanha": campanha,
                    "enviando_label": f"{numero_formatado} - {nome}",
                }
            ))

            if "Target page, context or browser has been closed" in erro_msg:
                self._fechar_contexto_playwright(contexto)
                self.fila_eventos.put(("erro_geral", "O navegador foi fechado durante o envio; lote interrompido."))
                return

            if indice < len(contatos):
                if not self._esperar_delay(random.uniform(delay_min, delay_max)):
                    self._fechar_contexto_playwright(contexto)
                    self.fila_eventos.put(("parado", None))
                    return

        # A caixa vazia confirma o envio, mas o WhatsApp ainda pode estar
        # renderizando/despachando a última bolha. Damos tempo ao navegador
        # para concluir essa operação antes de liberar o perfil persistente.
        try:
            page.wait_for_timeout(5_000)
        except Exception:
            pass
        self._fechar_contexto_playwright(contexto)
        self.fila_eventos.put(("concluido", None))

    def _processar_fila(self):
        try:
            while True:
                tipo, payload = self.fila_eventos.get_nowait()

                if tipo == "enviando":
                    self.label_enviando.config(text=f"Enviando: {payload}")

                elif tipo == "preparando":
                    self.status_var.set(payload)
                    self.label_enviando.config(text=payload)

                elif tipo == "resultado":
                    self._registrar_resultado(payload)

                elif tipo == "concluido":
                    self._finalizar_envio("Envio concluído.")

                elif tipo == "parado":
                    self._finalizar_envio("Envio interrompido.")

                elif tipo == "erro_geral":
                    self._adicionar_log(f"{datetime.now():%d/%m/%Y %H:%M:%S}  [⊗]  {payload}\n")
                    self._finalizar_envio(payload)

        except queue.Empty:
            pass

        self.after(100, self._processar_fila)

    def _registrar_resultado(self, dados):
        agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        if dados["status"] == "Enviado":
            self.enviados += 1
            if dados["campanha"]:
                self._registrar_envio_na_campanha(
                    dados["campanha"], dados["telefone"], dados["nome"]
                )
                if self.campanha_consulta_var.get() == dados["campanha"]:
                    self._carregar_envios_campanha()
            tag = "ok"
            icone = "[✓]"
        else:
            self.falhas += 1
            tag = "erro"
            icone = "[⊗]"

        registro = {
            "Data/Hora": agora,
            "Telefone": dados["telefone"],
            "Nome": dados["nome"],
            "Campanha": dados["campanha"],
            "Status": dados["status"],
            "Erro": dados["erro"],
        }
        self.historico.append(registro)

        valores = (agora, dados["telefone"], dados["nome"], dados["status"], dados["erro"])
        self.tree_lateral.insert("", "end", values=valores, tags=(tag,))
        self.tree_historico_completo.insert("", "end", values=valores, tags=(tag,))
        self.tree_lateral.yview_moveto(1)
        self.tree_historico_completo.yview_moveto(1)

        if dados["status"] == "Enviado":
            detalhe_campanha = f" ({dados['campanha']})" if dados["campanha"] else ""
            linha_log = f"{agora}  {icone}  Enviado para {dados['telefone']} - {dados['nome']}{detalhe_campanha}\n"
        else:
            linha_log = f"{agora}  {icone}  Falha ao enviar para {dados['telefone']} - {dados['nome']} ({dados['erro']})\n"
        self._adicionar_log(linha_log)

        self.barra_progresso["value"] = self.enviados + self.falhas
        self._atualizar_resumo()

    def _adicionar_log(self, texto):
        self.texto_log.config(state="normal")
        self.texto_log.insert("end", texto)
        self.texto_log.see("end")
        self.texto_log.config(state="disabled")

    def _atualizar_resumo(self):
        restantes = max(self.total - self.enviados - self.falhas, 0)
        self.label_enviados.config(text=str(self.enviados))
        self.label_falhas.config(text=str(self.falhas))
        self.label_restantes.config(text=str(restantes))
        self.label_total.config(text=str(self.total))

        percentual = int(((self.enviados + self.falhas) / self.total) * 100) if self.total else 0
        self.label_percentual.config(text=f"{percentual}%")

    def _finalizar_envio(self, mensagem_status):
        self.btn_iniciar.config(state="normal")
        self.btn_pausar.config(state="disabled", text="⏸  Pausar")
        self.btn_parar.config(state="disabled")
        self.label_enviando.config(text="")
        self.status_var.set(mensagem_status)
        self._trazer_janela_para_frente()

    def _trazer_janela_para_frente(self):
        """
        Traz a janela do programa de volta para frente/foco. O navegador pode
        ficar em foco durante os envios; ao terminar,
        o usuário deve ver a tela do programa automaticamente, sem precisar
        clicar no ícone na barra de tarefas.
        """
        try:
            self.deiconify()
            self.lift()
            # "topmost" temporário força a janela para frente mesmo se outro
            # app (o navegador) estiver em foco; depois desliga para não
            # atrapalhar o uso normal do computador.
            self.attributes("-topmost", True)
            self.after(300, lambda: self.attributes("-topmost", False))
            self.focus_force()
        except tk.TclError:
            pass

    def _exportar_excel(self):
        if not self.historico:
            messagebox.showinfo("Nada para exportar", "Ainda não há envios registrados nesta sessão.")
            return

        caminho = filedialog.asksaveasfilename(
            title="Exportar histórico",
            defaultextension=".xlsx",
            filetypes=[("Planilha Excel", "*.xlsx")],
            initialfile="historico_envios.xlsx",
        )
        if not caminho:
            return

        try:
            pd.DataFrame(self.historico).to_excel(caminho, index=False)
            messagebox.showinfo("Exportado", f"Histórico exportado com sucesso para:\n{caminho}")
        except Exception as e:
            messagebox.showerror("Erro ao exportar", f"Não foi possível exportar:\n{e}")

    def _limpar_log(self):
        if not messagebox.askyesno("Limpar histórico", "Tem certeza que deseja limpar o histórico e o log desta sessão?"):
            return
        for item in self.tree_lateral.get_children():
            self.tree_lateral.delete(item)
        for item in self.tree_historico_completo.get_children():
            self.tree_historico_completo.delete(item)
        self.texto_log.config(state="normal")
        self.texto_log.delete("1.0", "end")
        self.texto_log.config(state="disabled")
        self.historico.clear()
        self.status_var.set("Histórico e log limpos.")


def main():
    app = WhatsAppThbot()
    app.mainloop()


if __name__ == "__main__":
    main()
