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
from tkinter import ttk, filedialog, messagebox, simpledialog

import customtkinter as ctk
from thbot_ui import (
    Card, NumberInput, MenuButton, CampaignCombo, Button, Entry, Table,
    BACKGROUND, SURFACE, TEXT, MUTED, BORDER, ACCENT, configurar_tema,
)
from PIL import Image

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

class WhatsAppThbot(ctk.CTk):
    def __init__(self):
        ctk.set_appearance_mode("light")
        configurar_tema()
        super().__init__()
        self.configure(fg_color=BACKGROUND)
        self.title("WhatsApp Thbot")
        self.iconbitmap(caminho_recurso("thbot_icone.ico"))
        largura = min(1500, self.winfo_screenwidth() - 80)
        altura = min(950, self.winfo_screenheight() - 120)
        self.geometry(f"{largura}x{altura}+20+20")
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
        dark = ctk.get_appearance_mode() == "Dark"
        index = int(dark)
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview", rowheight=34, background=SURFACE[index],
                        fieldbackground=SURFACE[index], foreground=TEXT[index],
                        bordercolor=BORDER[index], lightcolor=BORDER[index], darkcolor=BORDER[index],
                        borderwidth=1, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", background="#263544" if dark else "#eaf0f5",
                        foreground=TEXT[index], bordercolor=BORDER[index],
                        lightcolor=BORDER[index], darkcolor=BORDER[index],
                        relief="solid", borderwidth=1, padding=(12, 10), font=("Segoe UI", 10, "bold"))
        style.map("Treeview", background=[("selected", "#244f46" if dark else "#d3eee5")],
                  foreground=[("selected", "#edfff8" if dark else "#145c46")])
        style.map("Treeview.Heading", background=[("active", "#34485c" if dark else "#dce7ef")])

    def _alternar_tema(self):
        self.modo_noturno_var.set(not self.modo_noturno_var.get())
        ctk.set_appearance_mode("dark" if self.modo_noturno_var.get() else "light")
        self._configurar_estilo()
        self.botao_tema.configure(text="☀" if self.modo_noturno_var.get() else "☾")
        for tree in (self.tree_lateral, self.tree_historico_completo, self.tree_campanha):
            tree.update_theme()

    def _construir_layout(self):
        cabecalho = ctk.CTkFrame(self, fg_color="transparent")
        cabecalho.pack(fill="x", padx=24, pady=(18, 4))
        with Image.open(caminho_recurso("thbot_icone.ico")) as logo:
            self.logo_cabecalho = ctk.CTkImage(light_image=logo.convert("RGBA"), size=(44, 44))
        marca = ctk.CTkFrame(cabecalho, fg_color="#1b2530", corner_radius=10, width=52, height=52)
        marca.pack(side="left")
        marca.pack_propagate(False)
        ctk.CTkLabel(marca, text="", image=self.logo_cabecalho).pack(expand=True)
        ctk.CTkLabel(cabecalho, text="Automação de mensagens", text_color=TEXT,
                     font=("Segoe UI", 20, "bold")).pack(side="left", padx=14)
        self.modo_noturno_var = tk.BooleanVar(value=False)
        self.botao_tema = Button(
            cabecalho,
            text="☾",
            width=38,
            height=34,
            font=("Segoe UI Symbol", 18),
            command=self._alternar_tema,
        )
        self.botao_tema.pack(side="right")

        self.status_var = tk.StringVar(value="Pronto para iniciar.")
        ctk.CTkLabel(self, text="", textvariable=self.status_var, anchor="w",
                     text_color=MUTED).pack(side="bottom", fill="x", padx=24, pady=8)
        self.notebook = ctk.CTkTabview(self, fg_color=BACKGROUND, corner_radius=12,
                                     segmented_button_fg_color=("#e3eaf0", "#233240"),
                                     segmented_button_unselected_color=("#e3eaf0", "#233240"),
                                     segmented_button_unselected_hover_color=("#d3dfe8", "#34485c"),
                                     segmented_button_selected_color=("#b9ded3", "#245448"),
                                     segmented_button_selected_hover_color=("#a5d2c5", "#2c6758"),
                                     text_color=TEXT)
        self.notebook.pack(fill="both", expand=True, padx=14, pady=(4, 0))
        self.aba_envio = self.notebook.add("Envio de mensagens")
        self.aba_historico = self.notebook.add("Histórico de envios")
        self.aba_campanhas = self.notebook.add("Campanhas")
        self.aba_config = self.notebook.add("Configurações")
        self._montar_aba_envio()
        self._montar_aba_historico()
        self._montar_aba_campanhas()
        self._montar_aba_config()

    def _montar_aba_envio(self):
        container = ctk.CTkFrame(self.aba_envio, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=10, pady=10)
        container.columnconfigure(0, weight=55, minsize=620, uniform="paineis")
        container.columnconfigure(1, weight=45, uniform="paineis")
        container.rowconfigure(0, weight=1)

        col_esquerda = ctk.CTkFrame(container, fg_color=BACKGROUND)
        col_esquerda.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        col_esquerda.columnconfigure(0, weight=1)
        col_esquerda.rowconfigure(1, weight=2)
        col_esquerda.rowconfigure(2, weight=1, minsize=166)
        col_esquerda.rowconfigure(3, weight=2, minsize=104)

        col_direita = ctk.CTkFrame(container, fg_color="transparent")
        col_direita.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        self._secao_planilha(col_esquerda)
        self._secao_mensagem(col_esquerda)
        self._secao_delay_quantidade_controles(col_esquerda)
        self._secao_progresso_resumo(col_esquerda)

        self._secao_historico_lateral(col_direita)

    def _secao_planilha(self, parent):
        frame_topo = ctk.CTkFrame(parent, fg_color=BACKGROUND)
        frame_topo.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        bloco1 = Card(frame_topo, text="Selecionar planilha", compact=True)
        bloco1.pack(fill="x")
        bloco1 = bloco1.body

        linha = ctk.CTkFrame(bloco1, fg_color="transparent")
        linha.pack(fill="x")
        entrada = Entry(linha, textvariable=self.caminho_planilha, state="readonly")
        entrada.pack(side="left", fill="x", expand=True, padx=(0, 6))
        Button(linha, text="Selecionar...", command=self._selecionar_planilha).pack(side="left")

    def _secao_mensagem(self, parent):
        bloco = Card(parent, text="Mensagem", compact=True, center_content=False)
        bloco.grid(row=1, column=0, sticky="nsew", pady=(0, 8))
        bloco = bloco.body
        rodape = ctk.CTkFrame(bloco, fg_color="transparent")
        rodape.pack(side="bottom", fill="x", pady=(8, 0))

        self.menubtn_variaveis = MenuButton(rodape, text="Inserir variável  ▾")
        self.menu_variaveis = tk.Menu(self.menubtn_variaveis, tearoff=False)
        self.menubtn_variaveis.menu = self.menu_variaveis
        self.menubtn_variaveis.pack(side="left")
        self._atualizar_menu_variaveis()

        ctk.CTkLabel(rodape, text="Campanha:").pack(side="left", padx=(12, 6))
        self.combo_campanha = CampaignCombo(
            rodape,
            variable=self.campanha_var,
            width=180,
            postcommand=self._atualizar_lista_campanhas,
        )
        self.combo_campanha.pack(side="left")
        menu_campanha = tk.Menu(rodape, tearoff=False)
        menu_campanha.add_command(label="Criar campanha", command=self._nova_campanha)
        menu_campanha.add_command(label="Excluir campanha", command=self._excluir_campanha)
        acoes_campanha = MenuButton(rodape, text="⋯", width=34)
        acoes_campanha.menu = menu_campanha
        acoes_campanha.pack(side="left", padx=(6, 0))
        self.texto_mensagem = ctk.CTkTextbox(bloco, height=70, wrap="word", font=("Segoe UI", 13))
        self.texto_mensagem.pack(fill="both", expand=True)
        self.texto_mensagem.insert("1.0", MENSAGEM_PADRAO)

    def _inserir_variavel(self, variavel: str):
        self.texto_mensagem.insert(tk.INSERT, variavel)
        self.texto_mensagem.focus_set()

    def _atualizar_menu_variaveis(self):
        self.menu_variaveis.delete(0, "end")
        variaveis = [] if self.df is None else [
            str(coluna) for coluna in self.df.columns if self._coluna_util(coluna)
        ]
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
                    status TEXT NOT NULL DEFAULT 'Enviado',
                    PRIMARY KEY (campanha, telefone)
                )
                """
            )
            colunas = {linha[1] for linha in conexao.execute("PRAGMA table_info(envios_por_campanha)")}
            if "nome" not in colunas:
                conexao.execute("ALTER TABLE envios_por_campanha ADD COLUMN nome TEXT NOT NULL DEFAULT ''")
            if "status" not in colunas:
                conexao.execute(
                    "ALTER TABLE envios_por_campanha ADD COLUMN status TEXT NOT NULL DEFAULT 'Enviado'"
                )
            conexao.execute(
                """
                CREATE TABLE IF NOT EXISTS historico_resultados (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    registrado_em TEXT NOT NULL,
                    telefone TEXT NOT NULL,
                    nome TEXT NOT NULL DEFAULT '',
                    campanha TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    erro TEXT NOT NULL DEFAULT ''
                )
                """
            )

    def _atualizar_lista_campanhas(self):
        with sqlite3.connect(self._caminho_banco_envios()) as conexao:
            campanhas = [linha[0] for linha in conexao.execute(
                "SELECT nome FROM campanhas ORDER BY nome COLLATE NOCASE"
            )]
        self.combo_campanha.configure(values=campanhas)
        if hasattr(self, "combo_campanha_consulta"):
            self.combo_campanha_consulta.configure(values=campanhas)

    def _telefones_enviados_na_campanha(self, campanha: str) -> set[str]:
        with sqlite3.connect(self._caminho_banco_envios()) as conexao:
            return {
                linha[0] for linha in conexao.execute(
                    "SELECT telefone FROM envios_por_campanha WHERE campanha = ?",
                    (campanha,),
                )
            }

    def _registrar_contato_processado_na_campanha(
        self, campanha: str, telefone: str, nome: str, status: str = "Enviado"
    ):
        with sqlite3.connect(self._caminho_banco_envios()) as conexao:
            conexao.execute(
                "INSERT OR IGNORE INTO campanhas (nome, criada_em) VALUES (?, ?)",
                (campanha, datetime.now().isoformat(timespec="seconds")),
            )
            conexao.execute(
                """
                INSERT OR IGNORE INTO envios_por_campanha (campanha, telefone, nome, enviado_em, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (campanha, telefone, nome, datetime.now().isoformat(timespec="seconds"), status),
            )

    def _registrar_resultado_no_historico(self, dados):
        with sqlite3.connect(self._caminho_banco_envios()) as conexao:
            conexao.execute(
                """
                INSERT INTO historico_resultados
                    (registrado_em, telefone, nome, campanha, status, erro)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now().isoformat(timespec="seconds"),
                    dados["telefone"],
                    dados["nome"],
                    dados["campanha"],
                    dados["status"],
                    dados["erro"],
                ),
            )

    def _atualizar_resumo_diario_historico(self):
        with sqlite3.connect(self._caminho_banco_envios()) as conexao:
            enviados, falhados = conexao.execute(
                """
                SELECT
                    COALESCE(SUM(status = 'Enviado'), 0),
                    COALESCE(SUM(status <> 'Enviado'), 0)
                FROM historico_resultados
                WHERE substr(registrado_em, 1, 10) = ?
                """,
                (datetime.now().date().isoformat(),),
            ).fetchone()
        texto_enviados = "mensagem enviada" if enviados == 1 else "mensagens enviadas"
        texto_falhados = "mensagem falhada" if falhados == 1 else "mensagens falhadas"
        self.resumo_diario_historico_var.set(
            f"Hoje: {enviados} {texto_enviados} | {falhados} {texto_falhados}"
        )

    def _secao_delay_quantidade_controles(self, parent):
        linha = ctk.CTkFrame(parent, fg_color=BACKGROUND)
        linha.grid(row=2, column=0, sticky="nsew", pady=(0, 8))
        linha.rowconfigure(0, weight=1)
        for coluna in range(3):
            linha.columnconfigure(coluna, weight=1, uniform="controles")

        bloco4 = Card(linha, text="Intervalo (segundos)", compact=True)
        bloco4.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        bloco4 = bloco4.body
        for rotulo, variavel in (("De", self.delay_min_var), ("Até", self.delay_max_var)):
            sub = ctk.CTkFrame(bloco4, fg_color="transparent")
            sub.pack(fill="x", pady=(0, 8))
            ctk.CTkLabel(sub, text=rotulo, width=30, anchor="w").pack(side="left")
            NumberInput(sub, from_=5, to=600, textvariable=variavel, width=35).pack(side="left", fill="x", expand=True)

        bloco5 = Card(linha, text="Quantidade", compact=True)
        bloco5.grid(row=0, column=1, sticky="nsew", padx=6)
        bloco5 = bloco5.body
        NumberInput(bloco5, from_=0, to=100000, textvariable=self.quantidade_var, width=60).pack(fill="x")
        ctk.CTkLabel(bloco5, text="0 = Enviar para todos os contatos.", text_color=MUTED,
                  wraplength=140, justify="left").pack(anchor="w", pady=(6, 0))

        bloco6 = Card(linha, text="Controles", compact=True)
        bloco6.grid(row=0, column=2, sticky="nsew", padx=(6, 0))
        bloco6 = bloco6.body
        sub6 = ctk.CTkFrame(bloco6, fg_color="transparent")
        sub6.pack(fill="x")

        self.btn_iniciar = Button(sub6, text="Iniciar", width=100, command=self._iniciar_envio)
        self.btn_iniciar.pack(fill="x", pady=(0, 4))

        self.btn_pausar = Button(sub6, text="Pausar", width=100, command=self._alternar_pausa, state="disabled")
        self.btn_pausar.pack(fill="x", pady=4)

        self.btn_parar = Button(sub6, text="Parar", width=100, command=self._parar_envio, state="disabled")
        self.btn_parar.pack(fill="x", pady=(4, 0))

    def _secao_progresso_resumo(self, parent):
        bloco_prog = Card(parent, text="Progresso", compact=True)
        bloco_prog.grid(row=3, column=0, sticky="nsew")
        bloco_prog = bloco_prog.body
        progresso = ctk.CTkFrame(bloco_prog, fg_color="transparent")
        progresso.pack(fill="x")
        self.barra_progresso = ctk.CTkProgressBar(progresso, height=8, progress_color="#168468")
        self.barra_progresso.set(0)
        self.barra_progresso.pack(side="left", fill="x", expand=True)
        self.label_percentual = ctk.CTkLabel(progresso, text="0%", width=42, height=20)
        self.label_percentual.pack(side="right", padx=(8, 0))
        bloco_resumo = ctk.CTkFrame(bloco_prog, fg_color="transparent")
        bloco_resumo.pack(fill="x", pady=(4, 0))
        self.label_enviando = ctk.CTkLabel(bloco_prog, text="", text_color=MUTED,
                                          height=20, anchor="w")
        self.label_enviando.pack(fill="x")

        self.label_enviados = self._linha_resumo(bloco_resumo, "Enviados:", "0", ("#18724f", "#6dd7ac"))
        self.label_falhas = self._linha_resumo(bloco_resumo, "Falhas:", "0", ("#b63440", "#ff9999"))
        self.label_restantes = self._linha_resumo(bloco_resumo, "Restantes:", "0", ("#906014", "#f2c471"))
        self.label_total = self._linha_resumo(bloco_resumo, "Total:", "0", TEXT)

    def _linha_resumo(self, parent, rotulo, valor_inicial, cor):
        linha = ctk.CTkFrame(parent, fg_color="transparent")
        linha.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(linha, text=rotulo, height=20).pack(side="left")
        lbl_valor = ctk.CTkLabel(linha, text=valor_inicial, height=20, text_color=cor, font=("Segoe UI", 13, "bold"))
        lbl_valor.pack(side="left", padx=(4, 8))
        return lbl_valor

    def _secao_historico_lateral(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=3)
        parent.rowconfigure(1, weight=2)
        bloco = Card(parent, text="Histórico de envios", center_content=False)
        bloco.grid(row=0, column=0, sticky="nsew", pady=(0, 12))
        bloco = bloco.body

        colunas = ("data_hora", "telefone", "nome", "status", "erro")
        self.tree_lateral = self._criar_treeview(bloco, colunas)

        bloco_log = Card(parent, text="Log de atividades", center_content=False)
        bloco_log.grid(row=1, column=0, sticky="nsew")
        bloco_log = bloco_log.body

        self.texto_log = ctk.CTkTextbox(bloco_log, height=160, state="disabled", font=("Consolas", 12))
        self.texto_log.pack(fill="both", expand=True)

        rodape = ctk.CTkFrame(parent, fg_color="transparent")
        rodape.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        Button(rodape, text="📊  Exportar para Excel", command=self._exportar_excel).pack(side="left")
        Button(rodape, text="🗑  Limpar log", command=self._limpar_log).pack(side="right")

    def _criar_treeview(self, parent, colunas):
        rotulos = {
            "data_hora": "Data/Hora",
            "telefone": "Telefone",
            "nome": "Nome",
            "status": "Status",
            "erro": "Erro",
        }
        larguras = {"data_hora": 130, "telefone": 110, "nome": 90, "status": 160, "erro": 120}

        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        tree = Table(frame, columns=colunas, show="headings", height=8)
        for c in colunas:
            tree.heading(c, text=rotulos[c])
            tree.column(c, width=larguras[c], minwidth=90, anchor="w")

        scroll_y = ctk.CTkScrollbar(frame, orientation="vertical", command=tree.yview)
        scroll_x = ctk.CTkScrollbar(frame, orientation="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        tree.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        return tree

    def _montar_aba_historico(self):
        container = ctk.CTkFrame(self.aba_historico, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(container, text="Histórico completo da sessão", font=("Segoe UI", 15, "bold")).pack(
            anchor="w", pady=(0, 12)
        )

        self.resumo_diario_historico_var = tk.StringVar()
        ctk.CTkLabel(
            container,
            textvariable=self.resumo_diario_historico_var,
            font=("Segoe UI", 13, "bold"),
            text_color=MUTED,
        ).pack(anchor="w", pady=(0, 10))
        self._atualizar_resumo_diario_historico()

        colunas = ("data_hora", "telefone", "nome", "status", "erro")
        self.tree_historico_completo = self._criar_treeview(container, colunas)

        rodape = ctk.CTkFrame(container, fg_color="transparent")
        rodape.pack(fill="x", pady=(8, 0))
        Button(rodape, text="📊  Exportar para Excel", command=self._exportar_excel).pack(side="left")
        Button(rodape, text="🗑  Limpar histórico", command=self._limpar_log).pack(side="right")

    def _montar_aba_campanhas(self):
        container = ctk.CTkFrame(self.aba_campanhas, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=10, pady=10)

        filtro = Card(container, text="Consultar campanha")
        filtro.pack(fill="x", pady=(0, 12))
        filtro = filtro.body

        selecao = ctk.CTkFrame(filtro, fg_color="transparent")
        selecao.pack(fill="x", pady=(0, 10))
        self.campanha_consulta_var = tk.StringVar()
        ctk.CTkLabel(selecao, text="Campanha:", width=70, anchor="w").pack(side="left")
        self.combo_campanha_consulta = CampaignCombo(
            selecao,
            variable=self.campanha_consulta_var,
            state="readonly",
            width=210,
            postcommand=self._atualizar_lista_campanhas,
        )
        self.combo_campanha_consulta.pack(side="left", padx=(0, 8))
        self.combo_campanha_consulta.configure(command=self._carregar_envios_campanha)
        Button(selecao, text="Atualizar", command=self._carregar_envios_campanha).pack(side="left")
        Button(
            selecao,
            text="Importar planilha",
            command=self._importar_registros_campanha,
        ).pack(side="left", padx=(8, 0))
        Button(
            selecao,
            text="Exportar histórico",
            command=self._exportar_historico_campanha,
        ).pack(side="left", padx=(8, 0))

        busca = ctk.CTkFrame(filtro, fg_color="transparent")
        busca.pack(fill="x")
        self.pesquisa_campanha_var = tk.StringVar()
        ctk.CTkLabel(busca, text="Pesquisar:", width=70, anchor="w").pack(side="left")
        entrada_pesquisa = Entry(busca, textvariable=self.pesquisa_campanha_var, width=210)
        entrada_pesquisa.pack(side="left")
        self.pesquisa_campanha_var.trace_add("write", self._filtrar_envios_campanha)
        Button(busca, text="Limpar", command=self._limpar_pesquisa_campanha).pack(side="left", padx=(8, 0))

        self.resumo_campanha_var = tk.StringVar(value="Selecione uma campanha para consultar os envios.")
        ctk.CTkLabel(container, text="", textvariable=self.resumo_campanha_var, font=("Segoe UI", 13, "bold")).pack(
            anchor="w", pady=(0, 12)
        )

        self.tree_campanha = self._criar_treeview(
            container, ("data_hora", "telefone", "nome", "status")
        )
        self.tree_campanha.configure(selectmode="extended")
        self.tree_campanha.bind("<Delete>", self._excluir_registro_campanha)
        self.envios_campanha = []
        self.coluna_ordenacao_campanha = None
        self.ordem_decrescente_campanha = False
        for coluna in ("data_hora", "telefone", "nome", "status"):
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
                SELECT enviado_em, telefone, nome, status
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
        for enviado_em, telefone, nome, status in envios:
            try:
                data_hora = datetime.fromisoformat(enviado_em).strftime("%d/%m/%Y %H:%M:%S")
            except ValueError:
                data_hora = enviado_em
            self.envios_campanha.append({
                "data_hora": data_hora,
                "ordenacao_data": enviado_em,
                "telefone": telefone,
                "nome": nome,
                "status": status,
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
        coluna_nome = self._adivinhar_coluna(
            colunas, ["nome", "cliente", "usuário", "usuario", "pessoa"], usar_primeira=False
        )
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
                    INSERT OR IGNORE INTO envios_por_campanha (campanha, telefone, nome, enviado_em, status)
                    VALUES (?, ?, ?, ?, 'Enviado')
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

    def _exportar_historico_campanha(self):
        campanha = self.campanha_consulta_var.get().strip()
        if not campanha:
            messagebox.showwarning(
                "Selecione uma campanha",
                "Selecione a campanha cujo histórico deseja exportar.",
                parent=self,
            )
            return

        with sqlite3.connect(self._caminho_banco_envios()) as conexao:
            registros = list(conexao.execute(
                """
                SELECT enviado_em, telefone, nome, status
                FROM envios_por_campanha
                WHERE campanha = ?
                ORDER BY enviado_em DESC
                """,
                (campanha,),
            ))

        if not registros:
            messagebox.showinfo(
                "Nada para exportar",
                "Esta campanha ainda não possui registros.",
                parent=self,
            )
            return

        nome_arquivo = re.sub(r'[\\/:*?"<>|]+', "_", campanha).strip(". ") or "campanha"
        caminho = filedialog.asksaveasfilename(
            title="Exportar histórico da campanha",
            defaultextension=".xlsx",
            filetypes=[("Planilha Excel", "*.xlsx")],
            initialfile=f"historico_{nome_arquivo}.xlsx",
            parent=self,
        )
        if not caminho:
            return

        historico = pd.DataFrame(
            registros,
            columns=["Data/Hora", "Telefone", "Nome", "Status"],
        )
        historico.insert(0, "Campanha", campanha)
        try:
            historico.to_excel(caminho, index=False)
            self.status_var.set(f"Histórico da campanha '{campanha}' exportado.")
            messagebox.showinfo(
                "Exportado",
                f"Histórico da campanha exportado com sucesso para:\n{caminho}",
                parent=self,
            )
        except Exception as exc:
            messagebox.showerror(
                "Erro ao exportar",
                f"Não foi possível exportar:\n{exc}",
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
                "", "end", values=(envio["data_hora"], envio["telefone"], envio["nome"], envio["status"])
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
        container = ctk.CTkFrame(self.aba_config, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=10, pady=10)

        bloco = Card(container, text="Configurações de envio")
        bloco.pack(fill="x", anchor="n")
        bloco = bloco.body

        linha1 = ctk.CTkFrame(bloco, fg_color="transparent")
        linha1.pack(fill="x", pady=6)
        ctk.CTkLabel(linha1, text="Código do país (DDI):", width=235, anchor="w").pack(side="left")
        Entry(linha1, textvariable=self.codigo_pais_var, width=180).pack(side="left")
        ctk.CTkLabel(linha1, text="  Ex: 55 para o Brasil.", text_color=MUTED).pack(side="left")

        linha_browser = ctk.CTkFrame(bloco, fg_color="transparent")
        linha_browser.pack(fill="x", pady=6)
        ctk.CTkLabel(linha_browser, text="Navegador:", width=235, anchor="w").pack(side="left")
        CampaignCombo(
            linha_browser, variable=self.navegador_var, state="readonly",
            values=("Chromium", "Google Chrome", "Firefox"), width=180,
        ).pack(side="left")
        ctk.CTkLabel(linha_browser, text="  A sessão de login é salva localmente.", text_color=MUTED).pack(side="left")

        linha2 = ctk.CTkFrame(bloco, fg_color="transparent")
        linha2.pack(fill="x", pady=6)
        ctk.CTkLabel(linha2, text="Limite de espera por evento (s):", width=235, anchor="w").pack(side="left")
        NumberInput(linha2, from_=10, to=180, textvariable=self.timeout_var, width=116).pack(side="left")
        ctk.CTkLabel(linha2, text="  Usado apenas como limite; não há espera fixa.",
                  text_color=MUTED).pack(side="left")

        if not PLAYWRIGHT_DISPONIVEL:
            aviso = ctk.CTkLabel(
                container,
                text=(
                    "⚠️  A biblioteca 'playwright' não está instalada. Instale com:\n"
                    "pip install playwright\nplaywright install chromium firefox"
                ),
                text_color=("#b63440", "#ff9999"),
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

        df.columns = [str(coluna) for coluna in df.columns]
        colunas = [coluna for coluna in df.columns if self._coluna_util(coluna)]
        coluna_telefone = self._adivinhar_coluna(
            colunas, ["telefone", "numero", "número", "fone", "celular"], usar_primeira=False
        )
        if not coluna_telefone:
            messagebox.showerror(
                "Coluna de telefone não identificada",
                "A planilha precisa ter uma coluna com nome como Telefone, Número, Fone ou Celular.",
            )
            return

        self.df = df
        self.caminho_planilha.set(os.path.basename(caminho))
        self._caminho_completo_planilha = caminho
        self.coluna_telefone.set(coluna_telefone)
        self.coluna_nome.set(
            self._adivinhar_coluna(
                colunas, ["nome", "cliente", "usuário", "usuario", "pessoa"], usar_primeira=False
            )
        )
        self._atualizar_menu_variaveis()

        self.status_var.set(f"Planilha carregada: {len(df)} contato(s) encontrados.")

    @staticmethod
    def _coluna_util(coluna) -> bool:
        nome = str(coluna).strip()
        return bool(nome) and not nome.casefold().startswith("unnamed:")

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
        self.barra_progresso.set(0)

        self.evento_pausa.clear()
        self.evento_parar.clear()

        self.btn_iniciar.configure(state="disabled")
        self.btn_pausar.configure(state="normal", text="Pausar")
        self.btn_parar.configure(state="normal")
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
            self.btn_pausar.configure(text="Pausar")
            self.status_var.set("Envio retomado.")
        else:
            self.evento_pausa.set()
            self.btn_pausar.configure(text="Retomar")
            self.status_var.set("Envio pausado.")

    def _parar_envio(self):
        self.evento_parar.set()
        self.evento_pausa.clear()
        self.status_var.set("Parando envio...")
        self.btn_parar.configure(state="disabled")
        self.btn_pausar.configure(state="disabled")

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
                    self.label_enviando.configure(text=f"Enviando: {payload}")

                elif tipo == "preparando":
                    self.status_var.set(payload)
                    self.label_enviando.configure(text=payload)

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
                self._registrar_contato_processado_na_campanha(
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
            # Números que o WhatsApp confirmou não possuir conta também são
            # resultados definitivos da campanha. Mantê-los no banco evita
            # novas tentativas quando a mesma planilha for executada de novo.
            if dados["campanha"] and dados["erro"].casefold() == "número sem whatsapp":
                self._registrar_contato_processado_na_campanha(
                    dados["campanha"], dados["telefone"], dados["nome"], "Número sem WhatsApp"
                )
                if self.campanha_consulta_var.get() == dados["campanha"]:
                    self._carregar_envios_campanha()

        registro = {
            "Data/Hora": agora,
            "Telefone": dados["telefone"],
            "Nome": dados["nome"],
            "Campanha": dados["campanha"],
            "Status": dados["status"],
            "Erro": dados["erro"],
        }
        self.historico.append(registro)
        self._registrar_resultado_no_historico(dados)
        self._atualizar_resumo_diario_historico()

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

        self.barra_progresso.set((self.enviados + self.falhas) / self.total if self.total else 0)
        self._atualizar_resumo()

    def _adicionar_log(self, texto):
        self.texto_log.configure(state="normal")
        self.texto_log.insert("end", texto)
        self.texto_log.see("end")
        self.texto_log.configure(state="disabled")

    def _atualizar_resumo(self):
        restantes = max(self.total - self.enviados - self.falhas, 0)
        self.label_enviados.configure(text=str(self.enviados))
        self.label_falhas.configure(text=str(self.falhas))
        self.label_restantes.configure(text=str(restantes))
        self.label_total.configure(text=str(self.total))

        percentual = int(((self.enviados + self.falhas) / self.total) * 100) if self.total else 0
        self.label_percentual.configure(text=f"{percentual}%")

    def _finalizar_envio(self, mensagem_status):
        self.btn_iniciar.configure(state="normal")
        self.btn_pausar.configure(state="disabled", text="Pausar")
        self.btn_parar.configure(state="disabled")
        self.label_enviando.configure(text="")
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
        self.texto_log.configure(state="normal")
        self.texto_log.delete("1.0", "end")
        self.texto_log.configure(state="disabled")
        self.historico.clear()
        self.status_var.set("Histórico e log limpos.")


def main():
    app = WhatsAppThbot()
    app.mainloop()


if __name__ == "__main__":
    main()
