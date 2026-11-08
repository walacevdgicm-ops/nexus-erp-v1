# =========================================================================
# ERP ENTERPRISE - SISTEMA DE GESTÃO INTEGRADO (FINANCEIRO, FISCAL, HCM, BI)
# =========================================================================
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from datetime import datetime, timedelta
import webbrowser
import threading
import sqlite3
import socket
import os
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# Tentativa de importação do OfxParser para Conciliação Bancária
try:
    from ofxparse import OfxParser
except ImportError:
    OfxParser = None

# =========================================================================
# CAMADA DE ARQUITETURA: SERVIÇO CORE / BACKEND INTEGRADO (PADRÃO CLIENTE-SERVIDOR)
# =========================================================================
class BackendAPI:
    """
    Camada de abstração que encapsula as regras de negócio, persistência de dados,
    mecanismo de auditoria ativa e motor fiscal. Centraliza as operações simulando 
    uma infraestrutura cliente-servidor para garantir o desacoplamento da UI.
    """
    def __init__(self, db_path="sistema_gestao_enterprise.db"):
        self.db_path = db_path
        self.inicializar_banco_dados()

    def conectar(self):
        conexao = sqlite3.connect(self.db_path)
        conexao.execute("PRAGMA foreign_keys = ON;")
        return conexao

    def inicializar_banco_dados(self):
        with self.conectar() as conn:
            cursor = conn.cursor()
            
            # Tabela de Usuários com Perfil RBAC incorporado
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    senha TEXT NOT NULL,
                    perfil TEXT NOT NULL CHECK(perfil IN ('Admin', 'Financeiro_Operador', 'Faturamento', 'Estoque', 'RH'))
                )
            """)
            
            # Tabela de Entidades (Clientes e Fornecedores)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entidades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario_id INTEGER NOT NULL,
                    tipo TEXT NOT NULL,
                    nome TEXT NOT NULL,
                    cnpj TEXT,
                    telefone TEXT,
                    localidade TEXT,
                    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
                )
            """)
            
            # Tabela de Estoque Geral
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS estoque (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario_id INTEGER NOT NULL,
                    descricao TEXT NOT NULL,
                    part_number TEXT NOT NULL,
                    fornecedor TEXT NOT NULL,
                    quantidade INTEGER NOT NULL,
                    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
                )
            """)
            
            # Tabela de Contas a Pagar
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS contas_pagar (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario_id INTEGER NOT NULL,
                    descricao TEXT NOT NULL,
                    valor REAL NOT NULL,
                    forma TEXT NOT NULL,
                    parcelas TEXT NOT NULL,
                    vencimento TEXT NOT NULL,
                    categoria TEXT DEFAULT 'Geral',
                    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
                )
            """)
            
            # Tabela de Contas a Receber com Detalhes do Motor Fiscal
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS contas_receber (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario_id INTEGER NOT NULL,
                    descricao TEXT NOT NULL,
                    valor_bruto REAL NOT NULL,
                    valor_liquido REAL NOT NULL,
                    impostos_retidos REAL NOT NULL,
                    regime_fiscal TEXT NOT NULL,
                    vencimento TEXT NOT NULL,
                    categoria TEXT DEFAULT 'Prestação de Serviços',
                    chave_nfe TEXT DEFAULT 'Não Transmitida',
                    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
                )
            """)
            
            # Tabela de Planejamento Orçamentário (Budget vs Actual)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orcamento (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario_id INTEGER NOT NULL,
                    categoria TEXT NOT NULL,
                    limite REAL NOT NULL,
                    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
                    UNIQUE(usuario_id, categoria)
                )
            """)

            # Tabela de Recursos Humanos (HCM) e Segurança do Trabalho
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS colaboradores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario_id INTEGER NOT NULL,
                    nome TEXT NOT NULL,
                    cargo TEXT NOT NULL,
                    salario REAL NOT NULL,
                    centro_custo TEXT NOT NULL,
                    data_admissao TEXT NOT NULL,
                    vencimento_aso TEXT NOT NULL,
                    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
                )
            """)
            
            # Tabela do Módulo de Auditoria Ativa e Compliance (Logs)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS auditoria (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario_id INTEGER,
                    usuario_email TEXT,
                    acao TEXT NOT NULL,
                    tabela_afetada TEXT NOT NULL,
                    descricao TEXT NOT NULL,
                    data_hora TEXT NOT NULL,
                    ip_maquina TEXT NOT NULL
                )
            """)
            
            # Tabela de Movimentações Bancárias (Conciliação e Open Finance)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS movimentacoes_bancarias (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario_id INTEGER NOT NULL,
                    data_movimento TEXT NOT NULL,
                    descricao TEXT NOT NULL,
                    valor REAL NOT NULL,
                    conciliado INTEGER DEFAULT 0,
                    origem_dados TEXT DEFAULT 'OFX Manual',
                    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
                )
            """)

            # Inserção de Usuários Padrão para Testes de Matriz RBAC (Caso a tabela esteja vazia)
            cursor.execute("SELECT COUNT(*) FROM usuarios")
            if cursor.fetchone()[0] == 0:
                perfis_padrao = [
                    ("admin@nexusdemo.com.br", "admin123", "Admin"),
                    ("financeiro@nexusdemo.com.br", "fin123", "Financeiro_Operador"),
                    ("faturamento@nexusdemo.com.br", "fat123", "Faturamento"),
                    ("estoque@nexusdemo.com.br", "est123", "Estoque"),
                    ("rh@nexusdemo.com.br", "rh123", "RH")
                ]
                cursor.executemany("INSERT INTO usuarios (email, senha, perfil) VALUES (?, ?, ?)", perfis_padrao)
            
            conn.commit()

    def obter_ip_local(self):
        try:
            return socket.gethostbyname(socket.gethostname())
        except:
            return "127.0.0.1"

    def registrar_log(self, usuario_id, email, acao, tabela, descricao):
        ip = self.obter_ip_local()
        dh = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        with self.conectar() as conn:
            conn.cursor().execute("""
                INSERT INTO auditoria (usuario_id, usuario_email, acao, tabela_afetada, descricao, data_hora, ip_maquina)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (usuario_id, email, acao, tabela, descricao, dh, ip))
            conn.commit()

# =========================================================================
# INTERFACE VISUAL PRINCIPAL DO ERP (APLICAÇÃO ENTERPRISE)
# =========================================================================
class AppControleFinanceiro:
    def __init__(self, root):
        self.root = root
        self.root.title("Consultoria e Gestão Financeira - Painel Corporativo Enterprise v2.0")
        self.root.geometry("1300x850")
        self.root.configure(bg="#f4f6f9")
        
        # Inicialização do Backend Centralizado
        self.api = BackendAPI()
        
        # Estado Padrão do Regime Fiscal da Empresa
        self.regime_fiscal_ativo = "Simples Nacional"
        
        self.criar_tela_login()

    # =========================================================================
    # AUTENTICAÇÃO E CONTROLE DE ACESSO (RBAC)
    # =========================================================================
    def criar_tela_login(self):
        self.frame_login = tk.Frame(self.root, bg="#f4f6f9")
        self.frame_login.place(relx=0.5, rely=0.5, anchor="center", width=480, height=520)
        
        card = tk.Frame(self.frame_login, bg="white", highlightbackground="#e2e8f0", highlightthickness=1, padx=35, pady=30)
        card.pack(fill="both", expand=True)
        
        tk.Label(card, text="ERP Enterprise - Corporate Login", font=("Arial", 16, "bold"), fg="#1a365d", bg="white").pack(pady=(5, 15))
        
        tk.Label(card, text="E-mail Corporativo:", font=("Arial", 10, "bold"), fg="#4a5568", bg="white").pack(anchor="w", pady=(10, 2))
        self.entry_login_email = ttk.Entry(card, font=("Arial", 11), width=35)
        self.entry_login_email.pack(fill="x", ipady=4, pady=(0, 15))
        self.entry_login_email.insert(0, "admin@nexusdemo.com.br") # Facilitador de homologação
        
        tk.Label(card, text="Senha de Acesso:", font=("Arial", 10, "bold"), fg="#4a5568", bg="white").pack(anchor="w", pady=(5, 2))
        self.entry_login_senha = ttk.Entry(card, font=("Arial", 11), width=35, show="*")
        self.entry_login_senha.pack(fill="x", ipady=4, pady=(0, 20))
        self.entry_login_senha.insert(0, "admin123")
        
        self.btn_acao_auth = ttk.Button(card, text="Autenticar no Sistema", command=self.processar_autenticacao)
        self.btn_acao_auth.pack(fill="x", ipady=6, pady=(10, 15))

        # Painel Informativo sobre as credenciais de homologação RBAC disponíveis
        info_frame = tk.LabelFrame(card, text=" Matriz de Credenciais RBAC para Homologação ", font=("Arial", 8, "bold"), bg="#f7fafc", fg="#4a5568")
        info_frame.pack(fill="x", pady=5)
        credenciais_texto = "admin@nexusdemo.com.br / admin123 (Acesso Total)\nfinanceiro@nexusdemo.com.br / fin123 (Financeiro)\nestoque@nexusdemo.com.br / est123 (Apenas Estoque)\nrh@nexusdemo.com.br / rh123 (Apenas RH/HCM)"
        tk.Label(info_frame, text=credenciais_texto, font=("Arial", 8), bg="#f7fafc", fg="#718096", justify="left").pack(padx=5, pady=5)

    def processar_autenticacao(self):
        email = self.entry_login_email.get().strip().lower()
        senha = self.entry_login_senha.get().strip()
        
        if not email or not senha:
            messagebox.showerror("Aviso", "Preencha todos os campos corporativos para prosseguir.")
            return
            
        with self.api.conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, email, perfil FROM usuarios WHERE email = ? AND senha = ?", (email, senha))
            usuario = cursor.fetchone()
            
            if usuario:
                self.usuario_logado_id = usuario[0]
                self.usuario_logado_email = usuario[1]
                self.usuario_logado_perfil = usuario[2]
                
                # Registro imediato em Auditoria Ativa
                self.api.registrar_log(self.usuario_logado_id, self.usuario_logado_email, "LOGIN", "usuarios", f"Autenticação bem-sucedida. Perfil ativo: {self.usuario_logado_perfil}")
                
                self.frame_login.destroy()
                self.construir_painel_principal()
            else:
                messagebox.showerror("Erro de Segurança", "Credenciais incorretas ou inexistentes na base corporativa.")

    # =========================================================================
    # PAINEL CENTRAL E CONTROLES DE INTERFACE (MATRIZ DE PERMISSÕES)
    # =========================================================================
    def construir_painel_principal(self):
        self.container_main = tk.Frame(self.root, bg="#f4f6f9")
        self.container_main.pack(fill="both", expand=True)

        # Barra de Status Superior Informativa do Usuário e Perfil
        status_topo = tk.Frame(self.container_main, bg="#1a365d", height=35)
        status_topo.pack(fill="x", side="top")
        lbl_user_info = tk.Label(status_topo, text=f"SESSÃO ATIVA: {self.usuario_logado_email} | PERFIL: {self.usuario_logado_perfil} | AMBIENTE: Produção Enterprise", font=("Arial", 9, "bold"), fg="#e2e8f0", bg="#1a365d")
        lbl_user_info.pack(side="left", padx=15, pady=8)

        self.notebook = ttk.Notebook(self.container_main)
        self.notebook.pack(fill="both", expand=True, padx=15, pady=(10, 5))
        
        # Abas Estruturais do Sistema
        self.aba_dashboard = ttk.Frame(self.notebook)
        self.aba_entidades = ttk.Frame(self.notebook)
        self.aba_estoque = ttk.Frame(self.notebook)
        self.aba_financeiro = ttk.Frame(self.notebook)
        self.aba_hcm = ttk.Frame(self.notebook)
        self.aba_controladoria = ttk.Frame(self.notebook)
        self.aba_conciliacao = ttk.Frame(self.notebook)
        
        self.notebook.add(self.aba_dashboard, text="Dashboard Executivo")
        self.notebook.add(self.aba_entidades, text="Cadastro de Entidades")
        self.notebook.add(self.aba_estoque, text="Gerenciamento de Estoque")
        self.notebook.add(self.aba_financeiro, text="Movimentação Financeira & Fiscal")
        self.notebook.add(self.aba_hcm, text="Recursos Humanos & HCM")
        self.notebook.add(self.aba_controladoria, text="Controladoria, DRE & Compliance")
        self.notebook.add(self.aba_conciliacao, text="Conciliação Bancária & Open Finance")
        
        self.notebook.bind("<<NotebookTabChanged>>", self.ao_alternar_aba)
        
        # Renderização dos Layouts das Abas
        self.criar_layout_entidades()
        self.criar_layout_estoque()
        self.criar_layout_financeiro()
        self.criar_layout_hcm()
        self.criar_layout_controladoria()
        self.criar_layout_conciliacao()
        
        self.aplicar_restricoes_rbac()
        self.criar_barra_botoes_atalho()
        self.renderizar_dashboard_executivo()

    def aplicar_restricoes_rbac(self):
        """
        Mapeia o perfil do usuário logado e bloqueia/oculta componentes da interface
        para garantir a governança e conformidade com a LGPD e políticas corporativas.
        """
        perfil = self.usuario_logado_perfil
        if perfil == "Admin":
            return # Acesso irrestrito total
        
        # Dicionário de permissões permitidas por perfil (Índices das abas do Notebook)
        permissoes = {
            "Financeiro_Operador": [0, 1, 3, 5, 6],
            "Faturamento": [0, 1, 3],
            "Estoque": [0, 2],
            "RH": [0, 4]
        }
        
        abas_permitidas = permissoes.get(perfil, [0])
        # Desabilita abas que não estão na lista de permissão do perfil do colaborador
        for idx in range(7):
            if idx not in abas_permitidas:
                self.notebook.tab(idx, state="disabled")
                
        # Redireciona o colaborador para a primeira aba disponível para ele
        self.notebook.select(abas_permitidas[0])

    def ao_alternar_aba(self, event):
        if not hasattr(self, 'usuario_logado_id'): return
        aba_atual = self.notebook.index(self.notebook.select())
        self.atualizar_combos_vinculo_entidades()
        
        if aba_atual == 0: self.renderizar_dashboard_executivo()
        elif aba_atual == 2: self.atualizar_tabela_estoque_visual()
        elif aba_atual == 3: self.atualizar_tabelas_financeiras()
        elif aba_atual == 4: self.atualizar_tabela_hcm()
        elif aba_atual == 5: 
            self.calcular_dre_estruturada()
            self.atualizar_tabela_orcamento()
            self.atualizar_tabela_auditoria()
        elif aba_atual == 6: self.atualizar_tabela_conciliacao()

    def criar_barra_botoes_atalho(self):
        frame_atalhos = tk.LabelFrame(self.container_main, text=" Painel Integrado de Atalhos (Acesso Rápido de Acordo com Perfil RBAC) ", font=("Arial", 10, "bold"), fg="#2b6cb0", bg="white", padx=10, pady=8)
        frame_atalhos.pack(fill="x", padx=15, pady=(5, 15), side="bottom")
        
        botoes_config = [
            ("📊 Dashboard", 0), ("👥 Entidades", 1), ("📦 Estoque Geral", 2),
            ("💸 Movimentação Financeira", 3), ("👥 Recursos Humanos", 4),
            ("📈 Controladoria & DRE", 5), ("🏦 Conciliação", 6)
        ]
        
        perfil = self.usuario_logado_perfil
        permissoes_indices = {
            "Admin": range(7), "Financeiro_Operador": [0, 1, 3, 5, 6],
            "Faturamento": [0, 1, 3], "Estoque": [0, 2], "RH": [0, 4]
        }.get(perfil, [0])

        for idx, (texto, aba_id) in enumerate(botoes_config):
            btn = tk.Button(frame_atalhos, text=texto, font=("Arial", 9, "bold"), fg="#1a365d", bg="#e2e8f0", activebackground="#cbd5e0", relief="groove", bd=2, cursor="hand2", padx=10, pady=4,
                            command=lambda a_id=aba_id: self.notebook.select(a_id))
            if aba_id in permissoes_indices:
                btn.grid(row=0, column=idx, padx=5, pady=2, sticky="nsew")
                frame_atalhos.grid_columnconfigure(idx, weight=1)

    # =========================================================================
    # MÓDULO 1: CADASTRO DE ENTIDADES (COM BUSCA ASSÍNCRONA)
    # =========================================================================
    def criar_layout_entidades(self):
        frame_form = tk.LabelFrame(self.aba_entidades, text=" Cadastrar Cliente ou Fornecedor ", font=("Arial", 11, "bold"), fg="#1a365d", bg="white", padx=15, pady=15)
        frame_form.pack(fill="x", padx=10, pady=10)
        
        tk.Label(frame_form, text="Tipo:", bg="white").grid(row=0, column=0, sticky="w", pady=5)
        self.combo_tipo_entidade = ttk.Combobox(frame_form, values=["Cliente", "Fornecedor"], width=15, state="readonly")
        self.combo_tipo_entidade.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        self.combo_tipo_entidade.set("Cliente")
        
        self.lbl_documento = tk.Label(frame_form, text="CNPJ:", bg="white")
        self.lbl_documento.grid(row=0, column=2, sticky="w", padx=15)
        self.entry_documento = ttk.Entry(frame_form, width=22)
        self.entry_documento.grid(row=0, column=3, padx=5, pady=5, sticky="w")
        
        self.btn_buscar_cnpj = ttk.Button(frame_form, text="Buscar Dados Corporativos", command=self.disparar_busca_cnpj)
        self.btn_buscar_cnpj.grid(row=0, column=4, padx=15, pady=5, sticky="w")
        
        tk.Label(frame_form, text="Nome / Razão Social:", bg="white").grid(row=1, column=0, sticky="w", pady=5)
        self.entry_nome_entidade = ttk.Entry(frame_form, width=35)
        self.entry_nome_entidade.grid(row=1, column=1, columnspan=2, padx=5, pady=5, sticky="w")
        
        tk.Label(frame_form, text="Telefone Comercial:", bg="white").grid(row=1, column=3, sticky="w", padx=15)
        self.entry_tel_entidade = ttk.Entry(frame_form, width=18)
        self.entry_tel_entidade.grid(row=1, column=4, padx=5, pady=5, sticky="w")
        
        tk.Label(frame_form, text="Cidade/UF:", bg="white").grid(row=2, column=0, sticky="w", pady=5)
        self.entry_cidade_entidade = ttk.Entry(frame_form, width=25)
        self.entry_cidade_entidade.grid(row=2, column=1, padx=5, pady=5, sticky="w")
        
        ttk.Button(frame_form, text="Salvar Registro de Entidade", command=self.adicionar_entidade).grid(row=3, column=0, columnspan=5, pady=10)
        
        frame_tabela = tk.LabelFrame(self.aba_entidades, text=" Entidades Cadastradas ", font=("Arial", 11, "bold"), bg="white", padx=10, pady=10)
        frame_tabela.pack(fill="both", expand=True, padx=10, pady=10)
        
        colunas = ("id", "tipo", "nome", "documento", "telefone", "localidade")
        self.tree_entidades = ttk.Treeview(frame_tabela, columns=colunas, show="headings")
        self.tree_entidades.heading("id", text="ID"); self.tree_entidades.heading("tipo", text="Tipo")
        self.tree_entidades.heading("nome", text="Nome / Razão Social"); self.tree_entidades.heading("documento", text="CPF / CNPJ")
        self.tree_entidades.heading("telefone", text="Telefone"); self.tree_entidades.heading("localidade", text="Cidade/UF")
        
        self.tree_entidades.column("id", width=50, anchor="center"); self.tree_entidades.column("tipo", width=100, anchor="center")
        self.tree_entidades.column("nome", width=320, anchor="w"); self.tree_entidades.column("documento", width=160, anchor="center")
        self.tree_entidades.column("telefone", width=120, anchor="center"); self.tree_entidades.column("localidade", width=150, anchor="w")
        
        self.tree_entidades.pack(fill="both", expand=True)
        self.atualizar_tabela_entidades()

    def disparar_busca_cnpj(self):
        cnpj = "".join(filter(str.isdigit, self.entry_documento.get().strip()))
        if len(cnpj) != 14: 
            messagebox.showwarning("Aviso Fiscal", "Insira um CNPJ com 14 dígitos numéricos para efetuar a busca assíncrona.")
            return
        self.btn_buscar_cnpj.config(state="disabled")
        threading.Thread(target=self.executar_busca_api_cnpj, args=(cnpj,), daemon=True).start()

    def ejecutar_busca_api_cnpj(self, cnpj):
        try:
            import requests
            resposta = requests.get(f"https://receitaws.com.br/v1/cnpj/{cnpj}", timeout=5)
            if resposta.status_code == 200:
                dados = resposta.json()
                if dados.get("status") != "ERROR":
                    self.root.after(0, lambda: self.preencher_campos_cnpj(dados.get("nome", ""), f"{dados.get('municipio', '')}/{dados.get('uf', '')}", dados.get("telefone", "")))
                else:
                    self.root.after(0, lambda: messagebox.showerror("Erro de Cadastro", "CNPJ não localizado na base pública consultada."))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Falha de Comunicação", f"Erro ao contatar servidor público: {str(e)}"))
        finally:
            self.root.after(0, lambda: self.btn_buscar_cnpj.config(state="normal"))

    def preencher_campos_cnpj(self, nome, city, tel):
        self.entry_nome_entidade.delete(0, tk.END); self.entry_nome_entidade.insert(0, nome)
        self.entry_cidade_entidade.delete(0, tk.END); self.entry_cidade_entidade.insert(0, city)
        self.entry_tel_entidade.delete(0, tk.END); self.entry_tel_entidade.insert(0, tel)

    def adicionar_entidade(self):
        tipo = self.combo_tipo_entidade.get()
        nome = self.entry_nome_entidade.get().strip()
        doc = self.entry_documento.get().strip()
        tel = self.entry_tel_entidade.get().strip()
        cidade = self.entry_cidade_entidade.get().strip()
        
        if not nome:
            messagebox.showerror("Erro de Validação", "O Nome ou Razão Social é obrigatório.")
            return
            
        with self.api.conectar() as conn:
            conn.cursor().execute("INSERT INTO entidades (usuario_id, tipo, nome, cnpj, telefone, localidade) VALUES (?, ?, ?, ?, ?, ?)",
                                (self.usuario_logado_id, tipo, nome, doc, tel, cidade))
            conn.commit()
            
        self.api.registrar_log(self.usuario_logado_id, self.usuario_logado_email, "INSERÇÃO", "entidades", f"Nova entidade cadastrada: {nome} ({tipo})")
        self.atualizar_tabela_entidades()
        self.atualizar_combos_vinculo_entidades()
        messagebox.showinfo("Sucesso", f"{tipo} gravado com sucesso nas bases corporativas.")

    def atualizar_tabela_entidades(self):
        for item in self.tree_entidades.get_children(): self.tree_entidades.delete(item)
        with self.api.conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, tipo, nome, cnpj, telefone, localidade FROM entidades WHERE usuario_id = ?", (self.usuario_logado_id,))
            for row in cursor.fetchall(): self.tree_entidades.insert("", "end", values=row)

    def atualizar_combos_vinculo_entidades(self):
        with self.api.conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT nome FROM entidades WHERE usuario_id = ? AND tipo = 'Cliente'", (self.usuario_logado_id,))
            clientes = [r[0] for r in cursor.fetchall()]
            cursor.execute("SELECT nome FROM entidades WHERE usuario_id = ? AND tipo = 'Fornecedor'", (self.usuario_logado_id,))
            fornecedores = [r[0] for r in cursor.fetchall()]
            
        if hasattr(self, 'combo_fornecedor_pagar'): self.combo_fornecedor_pagar.config(values=fornecedores)
        if hasattr(self, 'combo_cliente_receber'): self.combo_cliente_receber.config(values=clientes)
        if hasattr(self, 'combo_fornecedor_produto'): self.combo_fornecedor_produto.config(values=fornecedores)

    # =========================================================================
    # MÓDULO 2: GESTÃO DE ESTOQUE
    # =========================================================================
    def criar_layout_estoque(self):
        frame_form = tk.LabelFrame(self.aba_estoque, text=" Cadastrar Novo Item no Estoque Geral ", font=("Arial", 11, "bold"), fg="#1a365d", bg="white", padx=15, pady=15)
        frame_form.pack(fill="x", padx=10, pady=10)
        
        tk.Label(frame_form, text="Descrição Item:", bg="white").grid(row=0, column=0, sticky="w", pady=5)
        self.entry_desc_produto = ttk.Entry(frame_form, width=30)
        self.entry_desc_produto.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        
        tk.Label(frame_form, text="Part Number (P/N):", bg="white").grid(row=0, column=2, sticky="w", padx=15)
        self.entry_part_number = ttk.Entry(frame_form, width=20)
        self.entry_part_number.grid(row=0, column=3, padx=5, pady=5, sticky="w")
        
        tk.Label(frame_form, text="Fornecedor:", bg="white").grid(row=1, column=0, sticky="w", pady=5)
        self.combo_fornecedor_produto = ttk.Combobox(frame_form, values=[], width=27, state="readonly")
        self.combo_fornecedor_produto.grid(row=1, column=1, padx=5, pady=5, sticky="w")
        
        tk.Label(frame_form, text="Qtd Inicial:", bg="white").grid(row=1, column=2, sticky="w", padx=15)
        self.entry_qtd_inicial = ttk.Entry(frame_form, width=10)
        self.entry_qtd_inicial.grid(row=1, column=3, padx=5, pady=5, sticky="w")
        self.entry_qtd_inicial.insert(0, "0")
        
        ttk.Button(frame_form, text="Adicionar ao Inventário", command=self.adicionar_produto_estoque).grid(row=2, column=0, columnspan=4, pady=12)
        
        frame_tabela = tk.LabelFrame(self.aba_estoque, text=" Inventário Consolidado de Itens ", font=("Arial", 11, "bold"), bg="white", padx=10, pady=10)
        frame_tabela.pack(fill="both", expand=True, padx=10, pady=10)
        
        colunas = ("id", "desc", "pn", "forn", "qtd")
        self.tree_estoque = ttk.Treeview(frame_tabela, columns=colunas, show="headings")
        self.tree_estoque.heading("id", text="ID"); self.tree_estoque.heading("desc", text="Descrição Item")
        self.tree_estoque.heading("pn", text="Part Number"); self.tree_estoque.heading("forn", text="Fornecedor"); self.tree_estoque.heading("qtd", text="Estoque Atual")
        
        self.tree_estoque.column("id", width=50, anchor="center"); self.tree_estoque.column("desc", width=350, anchor="w")
        self.tree_estoque.column("pn", width=150, anchor="center"); self.tree_estoque.column("forn", width=200, anchor="w"); self.tree_estoque.column("qtd", width=120, anchor="center")
        self.tree_estoque.pack(fill="both", expand=True)
        
        frame_botoes = ttk.Frame(frame_tabela)
        frame_botoes.pack(pady=10, fill="x")
        ttk.Button(frame_botoes, text="➕ Entrada de Mercadoria", command=lambda: self.alterar_quantidade_estoque("entrada")).pack(side="left", padx=20, expand=True)
        ttk.Button(frame_botoes, text="➖ Baixa / Saída de Estoque", command=lambda: self.alterar_quantidade_estoque("saida")).pack(side="right", padx=20, expand=True)

    def adicionar_produto_estoque(self):
        desc = self.entry_desc_produto.get().strip()
        pn = self.entry_part_number.get().strip()
        forn = self.combo_fornecedor_produto.get()
        try:
            qtd = int(self.entry_qtd_inicial.get().strip())
        except ValueError:
            messagebox.showerror("Erro", "Quantidade inicial inválida.")
            return
            
        with self.api.conectar() as conn:
            conn.cursor().execute("INSERT INTO estoque (usuario_id, descricao, part_number, fornecedor, quantidade) VALUES (?, ?, ?, ?, ?)",
                                (self.usuario_logado_id, desc, pn, forn, qtd))
            conn.commit()
            
        self.api.registrar_log(self.usuario_logado_id, self.usuario_logado_email, "INSERÇÃO", "estoque", f"Novo item de estoque: {desc} | P/N: {pn} | Qtd: {qtd}")
        self.atualizar_tabela_estoque_visual()
        self.entry_desc_produto.delete(0, tk.END); self.entry_part_number.delete(0, tk.END)

    def atualizar_tabela_estoque_visual(self):
        for item in self.tree_estoque.get_children(): self.tree_estoque.delete(item)
        with self.api.conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, descricao, part_number, fornecedor, quantidade FROM estoque WHERE usuario_id = ?", (self.usuario_logado_id,))
            for row in cursor.fetchall(): self.tree_estoque.insert("", "end", values=row)

    def alterar_quantidade_estoque(self, operacao):
        selecionado = self.tree_estoque.selection()
        if not selecionado:
            messagebox.showwarning("Aviso", "Selecione um item da listagem de inventário.")
            return
        valores = self.tree_estoque.item(selecionado[0], "values")
        id_prod, desc_prod, _, _, qtd_atual = valores[0], valores[1], valores[2], valores[3], int(valores[4])
        
        qtd_mov = simpledialog.askinteger("Movimentação de Estoque", f"Quantidade para consolidar a {operacao} do item '{desc_prod}':", minvalue=1)
        if qtd_mov:
            nova_qtd = qtd_atual + qtd_mov if operacao == "entrada" else qtd_atual - qtd_mov
            if nova_qtd < 0:
                messagebox.showerror("Compliance de Estoque", "Operação negada. Saldo final de inventário não pode ser negativo.")
                return
                
            with self.api.conectar() as conn:
                conn.cursor().execute("UPDATE estoque SET quantidade = ? WHERE id = ? AND usuario_id = ?", (nova_qtd, id_prod, self.usuario_logado_id))
                conn.commit()
                
            self.api.registrar_log(self.usuario_logado_id, self.usuario_logado_email, "ALTERAÇÃO", "estoque", f"Estoque alterado para {operacao} do item ID {id_prod}. Mudança de {qtd_atual} para {nova_qtd}")
            self.atualizar_tabela_estoque_visual()

    # =========================================================================
    # MÓDULO 3: MOVIMENTAÇÃO FINANCEIRA & MOTOR FISCAL INTEGRADO
    # =========================================================================
    def criar_layout_financeiro(self):
        sub_notebook_fin = ttk.Notebook(self.aba_financeiro)
        sub_notebook_fin.pack(fill="both", expand=True, padx=5, pady=5)
        
        aba_pagar = ttk.Frame(sub_notebook_fin)
        aba_receber = ttk.Frame(sub_notebook_fin)
        sub_notebook_fin.add(aba_pagar, text="Contas a Pagar (Despesas)")
        sub_notebook_fin.add(aba_receber, text="Contas a Receber (Faturamento / Motor Fiscal)")
        
        # --- SUB-ABA CONTAS A PAGAR ---
        f_form_pagar = tk.LabelFrame(aba_pagar, text=" Lançamento de Despesas Corporativas ", font=("Arial", 10, "bold"), bg="white", padx=10, pady=10)
        f_form_pagar.pack(fill="x", padx=10, pady=5)
        
        tk.Label(f_form_pagar, text="Descrição:", bg="white").grid(row=0, column=0, sticky="w")
        self.entry_desc_pagar = ttk.Entry(f_form_pagar, width=20)
        self.entry_desc_pagar.grid(row=0, column=1, padx=5, pady=5)
        
        tk.Label(f_form_pagar, text="Valor (R$):", bg="white").grid(row=0, column=2, sticky="w", padx=10)
        self.entry_val_pagar = ttk.Entry(f_form_pagar, width=12)
        self.entry_val_pagar.grid(row=0, column=3, padx=5, pady=5)
        
        tk.Label(f_form_pagar, text="Vencimento:", bg="white").grid(row=0, column=4, sticky="w", padx=10)
        self.entry_data_pagar = ttk.Entry(f_form_pagar, width=12)
        self.entry_data_pagar.grid(row=0, column=5, padx=5, pady=5)
        self.entry_data_pagar.insert(0, datetime.now().strftime("%d/%m/%Y"))

        tk.Label(f_form_pagar, text="Fornecedor:", bg="white").grid(row=1, column=0, sticky="w")
        self.combo_fornecedor_pagar = ttk.Combobox(f_form_pagar, values=[], width=18, state="readonly")
        self.combo_fornecedor_pagar.grid(row=1, column=1, padx=5, pady=5)
        
        tk.Label(f_form_pagar, text="Setor / Categoria:", bg="white").grid(row=1, column=2, sticky="w", padx=10)
        self.combo_cat_pagar = ttk.Combobox(f_form_pagar, values=["Geral", "TI", "Marketing", "RH", "Operacional", "Logística"], width=14, state="readonly")
        self.combo_cat_pagar.grid(row=1, column=3, padx=5, pady=5)
        self.combo_cat_pagar.set("Geral")
        
        ttk.Button(f_form_pagar, text="Lançar Despesa com Verificação de Budget", command=self.adicionar_conta_pagar).grid(row=1, column=4, columnspan=2, padx=15)
        
        self.tree_pagar = ttk.Treeview(aba_pagar, columns=("id", "desc", "val", "venc", "cat"), show="headings")
        self.tree_pagar.heading("id", text="ID"); self.tree_pagar.heading("desc", text="Despesa / Fornecedor")
        self.tree_pagar.heading("val", text="Valor"); self.tree_pagar.heading("venc", text="Vencimento"); self.tree_pagar.heading("cat", text="Categoria")
        self.tree_pagar.pack(fill="both", expand=True, padx=10, pady=5)
        
        # --- SUB-ABA CONTAS A RECEBER (MOTOR FISCAL & TRANSMISSÃO) ---
        f_config_fiscal = tk.LabelFrame(aba_receber, text=" Configurações Tributárias de Enquadramento da Empresa ", font=("Arial", 10, "bold"), bg="#f7fafc", padx=10, pady=5)
        f_config_fiscal.pack(fill="x", padx=10, pady=5)
        tk.Label(f_config_fiscal, text="Regime Fiscal Vigente:", bg="#f7fafc", font=("Arial", 9, "bold")).pack(side="left", padx=5)
        self.combo_regime_fiscal = ttk.Combobox(f_config_fiscal, values=["Simples Nacional", "Lucro Presumido", "Lucro Real"], width=18, state="readonly")
        self.combo_regime_fiscal.pack(side="left", padx=10)
        self.combo_regime_fiscal.set("Simples Nacional")
        
        f_form_receber = tk.LabelFrame(aba_receber, text=" Lançamento de Ordem de Faturamento Financeiro (Receita) ", font=("Arial", 10, "bold"), bg="white", padx=10, pady=10)
        f_form_receber.pack(fill="x", padx=10, pady=5)
        
        tk.Label(f_form_receber, text="Descrição Serviço/Venda:", bg="white").grid(row=0, column=0, sticky="w")
        self.entry_desc_receber = ttk.Entry(f_form_receber, width=22)
        self.entry_desc_receber.grid(row=0, column=1, padx=5, pady=5)
        
        tk.Label(f_form_receber, text="Valor Bruto (R$):", bg="white").grid(row=0, column=2, sticky="w", padx=10)
        self.entry_val_receber = ttk.Entry(f_form_receber, width=12)
        self.entry_val_receber.grid(row=0, column=3, padx=5, pady=5)
        
        tk.Label(f_form_receber, text="Cliente Alvo:", bg="white").grid(row=0, column=4, sticky="w", padx=10)
        self.combo_cliente_receber = ttk.Combobox(f_form_receber, values=[], width=18, state="readonly")
        self.combo_cliente_receber.grid(row=0, column=5, padx=5, pady=5)
        
        tk.Label(f_form_receber, text="Data Vencimento:", bg="white").grid(row=1, column=0, sticky="w")
        self.entry_data_receber = ttk.Entry(f_form_receber, width=12)
        self.entry_data_receber.grid(row=1, column=1, padx=5, pady=5)
        self.entry_data_receber.insert(0, datetime.now().strftime("%d/%m/%Y"))
        
        ttk.Button(f_form_receber, text="Calcular Impostos e Lançar", command=self.adicionar_conta_receber).grid(row=1, column=2, columnspan=2, padx=10)
        ttk.Button(f_form_receber, text="⚡ Emitir & Transmitir NF-e (SEFAZ)", command=self.transmitir_nfe_sefaz).grid(row=1, column=4, columnspan=2, padx=10)
        
        colunas_rec = ("id", "desc", "bruto", "retido", "liquido", "regime", "venc", "nfe")
        self.tree_receber = ttk.Treeview(aba_receber, columns=colunas_rec, show="headings")
        self.tree_receber.heading("id", text="ID"); self.tree_receber.heading("desc", text="Descrição / Cliente")
        self.tree_receber.heading("bruto", text="Vl. Bruto"); self.tree_receber.heading("retido", text="Impostos Retidos")
        self.tree_receber.heading("liquido", text="Vl. Líquido"); self.tree_receber.heading("regime", text="Regime Fiscal")
        self.tree_receber.heading("venc", text="Vencimento"); self.tree_receber.heading("nfe", text="Chave de Acesso NF-e / Status")
        
        for col in colunas_rec:
            self.tree_receber.column(col, width=110, anchor="center")
        self.tree_receber.column("desc", width=250, anchor="w")
        self.tree_receber.column("nfe", width=180, anchor="center")
        self.tree_receber.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.atualizar_tabelas_financeiras()

    def adicionar_conta_pagar(self):
        try:
            desc = self.entry_desc_pagar.get().strip()
            forn = self.combo_fornecedor_pagar.get()
            valor = float(self.entry_val_pagar.get().strip().replace(".", "").replace(",", "."))
            venc = self.entry_data_pagar.get().strip()
            cat = self.combo_cat_pagar.get()
            datetime.strptime(venc, "%d/%m/%Y")
            
            exibicao = f"{desc} [{forn}]" if forn else desc
            
            # Validação Crítica de Teto de Gastos Orçamentários (Controladoria Compliance)
            with self.api.conectar() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT limite FROM orcamento WHERE usuario_id = ? AND categoria = ?", (self.usuario_logado_id, cat))
                res = cursor.fetchone()
                if res:
                    limite = res[0]
                    cursor.execute("SELECT SUM(valor) FROM contas_pagar WHERE usuario_id = ? AND categoria = ?", (self.usuario_logado_id, cat))
                    atual = cursor.fetchone()[0] or 0.0
                    if (atual + valor) > limite:
                        aut = messagebox.askyesno("Compliance Orçamentário", f"O lançamento excederá o teto definido de R$ {limite:,.2f} para a categoria '{cat}'.\nPretende forçar a gravação com ressalva em auditoria?")
                        if not aut: return
            
            with self.api.conectar() as conn:
                conn.cursor().execute("INSERT INTO contas_pagar (usuario_id, descricao, valor, forma, parcelas, vencimento, categoria) VALUES (?, ?, ?, 'Pix', 'À Vista', ?, ?)",
                                    (self.usuario_logado_id, exibicao, valor, venc, cat))
                conn.commit()
                
            self.api.registrar_log(self.usuario_logado_id, self.usuario_logado_email, "INSERÇÃO", "contas_pagar", f"Despesa adicionada: {exibicao} | Valor: R$ {valor:,.2f} | Categoria: {cat}")
            self.atualizar_tabelas_financeiras()
            self.entry_desc_pagar.delete(0, tk.END); self.entry_val_pagar.delete(0, tk.END)
        except ValueError:
            messagebox.showerror("Erro de Formato", "Verifique o valor e a data inserida (DD/MM/AAAA).")

    def adicionar_conta_receber(self):
        """
        Mecanismo de Automação do Motor Fiscal. Efetua a retenção de alíquotas de tributos
        (ICMS, ISS, PIS, COFINS, CSLL) dependendo do enquadramento legal selecionado.
        """
        try:
            desc = self.entry_desc_receber.get().strip()
            cli = self.combo_cliente_receber.get()
            v_bruto = float(self.entry_val_receber.get().strip().replace(".", "").replace(",", "."))
            venc = self.entry_data_receber.get().strip()
            regime = self.combo_regime_fiscal.get()
            datetime.strptime(venc, "%d/%m/%Y")
            
            # Definição de Alíquotas Dinâmicas Consolidadas baseadas no Regime Tributário
            if regime == "Simples Nacional":
                aliquota = 0.06 # 6% unificado DAS
            elif regime == "Lucro Presumido":
                aliquota = 0.0865 # 8.65% (PIS + COFINS + ISS Presumido)
            else:
                aliquota = 0.1525 # 15.25% (PIS + COFINS + ISS + CSLL Retido)
                
            imp_retidos = v_bruto * aliquota
            v_liquido = v_bruto - imp_retidos
            exibicao = f"{desc} [{cli}]" if cli else desc
            
            with self.api.conectar() as conn:
                conn.cursor().execute("""
                    INSERT INTO contas_receber (usuario_id, descricao, valor_bruto, valor_liquido, impostos_retidos, regime_fiscal, vencimento, categoria)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'Prestação de Serviços')
                """, (self.usuario_logado_id, exibicao, v_bruto, v_liquido, imp_retidos, regime, venc))
                conn.commit()
                
            self.api.registrar_log(self.usuario_logado_id, self.usuario_logado_email, "INSERÇÃO", "contas_receber", f"Receita lançada com cálculo de impostos: {exibicao} | Bruto: R$ {v_bruto:,.2f} | Alíquota: {aliquota*100}%")
            self.atualizar_tabelas_financeiras()
            self.entry_desc_receber.delete(0, tk.END); self.entry_val_receber.delete(0, tk.END)
            messagebox.showinfo("Motor Fiscal", f"Lançamento processado!\nImpostos Retidos Calculados: R$ {imp_retidos:,.2f}\nLíquido Financeiro: R$ {v_liquido:,.2f}")
        except ValueError:
            messagebox.showerror("Erro de Formato", "Verifique os dados numéricos digitados.")

    def transmitir_nfe_sefaz(self):
        """
        Simulador Avançado de Mensageria Fiscal. Assina eletronicamente a nota fiscal e
        gera a chave de acesso padrão SEFAZ de 44 dígitos com registro logístico.
        """
        selecionado = self.tree_receber.selection()
        if not selecionado:
            messagebox.showwarning("Faturamento Fiscal", "Selecione a ordem de receita desejada para efetuar a transmissão da NF-e.")
            return
        valores = self.tree_receber.item(selecionado[0], "values")
        id_rec, desc_rec = valores[0], valores[1]
        
        if "3526" in valores[7]: # Validação se já possui chave de acesso
            messagebox.showwarning("Mensageria Fiscal", "Esta nota fiscal já foi transmitida e homologada pela SEFAZ.")
            return
            
        import random
        chave_sefaz = "3526" + "".join([str(random.randint(0, 9)) for _ in range(40)])
        
        with self.api.conectar() as conn:
            conn.cursor().execute("UPDATE contas_receber SET chave_nfe = ? WHERE id = ? AND usuario_id = ?", (chave_sefaz, id_rec, self.usuario_logado_id))
            conn.commit()
            
        self.api.registrar_log(self.usuario_logado_id, self.usuario_logado_email, "FATURAMENTO FISCAL", "contas_receber", f"NF-e Transmitida e Autorizada para o item ID {id_rec}. Chave gerada: {chave_sefaz}")
        self.atualizar_tabelas_financeiras()
        
        messagebox.showinfo("Módulo Fiscal Concluído", f"Nota Fiscal Eletrônica Autorizada com Sucesso!\n\nProtocolo SEFAZ: {random.randint(100000,999999)}\nChave de Acesso: {chave_sefaz}\nStatus: 🟢 Autorizada o Uso da NF-e")

    def atualizar_tabelas_financeiras(self):
        # Atualização Contas a Pagar
        for item in self.tree_pagar.get_children(): self.tree_pagar.delete(item)
        with self.api.conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, descricao, valor, vencimento, categoria FROM contas_pagar WHERE usuario_id = ?", (self.usuario_logado_id,))
            for row in cursor.fetchall():
                self.tree_pagar.insert("", "end", values=(row[0], row[1], f"R$ {row[2]:,.2f}", row[3], row[4]))
                
        # Atualização Contas a Receber
        for item in self.tree_receber.get_children(): self.tree_receber.delete(item)
        with self.api.conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, descricao, valor_bruto, impostos_retidos, valor_liquido, regime_fiscal, vencimento, chave_nfe FROM contas_receber WHERE usuario_id = ?", (self.usuario_logado_id,))
            for row in cursor.fetchall():
                self.tree_receber.insert("", "end", values=(row[0], row[1], f"R$ {row[2]:,.2f}", f"R$ {row[3]:,.2f}", f"R$ {row[4]:,.2f}", row[5], row[6], row[7]))

    # =========================================================================
    # MÓDULO 4: RECURSOS HUMANOS (HCM) & SEGURANÇA DO TRABALHO
    # =========================================================================
    def criar_layout_hcm(self):
        f_form = tk.LabelFrame(self.aba_hcm, text=" Cadastro e Prontuário de Colaborador (HCM / DP) ", font=("Arial", 11, "bold"), fg="#1a365d", bg="white", padx=15, pady=15)
        f_form.pack(fill="x", padx=10, pady=10)
        
        tk.Label(f_form, text="Nome Completo:", bg="white").grid(row=0, column=0, sticky="w")
        self.entry_hcm_nome = ttk.Entry(f_form, width=25)
        self.entry_hcm_nome.grid(row=0, column=1, padx=5, pady=5)
        
        tk.Label(f_form, text="Cargo Atual:", bg="white").grid(row=0, column=2, sticky="w", padx=15)
        self.entry_hcm_cargo = ttk.Entry(f_form, width=20)
        self.entry_hcm_cargo.grid(row=0, column=3, padx=5, pady=5)
        
        tk.Label(f_form, text="Salário Base (R$):", bg="white").grid(row=0, column=4, sticky="w", padx=15)
        self.entry_hcm_salario = ttk.Entry(f_form, width=15)
        self.entry_hcm_salario.grid(row=0, column=5, padx=5, pady=5)
        
        tk.Label(f_form, text="Centro de Custo:", bg="white").grid(row=1, column=0, sticky="w")
        self.combo_hcm_cc = ttk.Combobox(f_form, values=["Administrativo", "TI / Sistemas", "Faturamento", "Operações Logísticas"], width=22, state="readonly")
        self.combo_hcm_cc.grid(row=1, column=1, padx=5, pady=5)
        self.combo_hcm_cc.set("Administrativo")
        
        tk.Label(f_form, text="Data Admissão:", bg="white").grid(row=1, column=2, sticky="w", padx=15)
        self.entry_hcm_admissao = ttk.Entry(f_form, width=15)
        self.entry_hcm_admissao.grid(row=1, column=3, padx=5, pady=5)
        self.entry_hcm_admissao.insert(0, datetime.now().strftime("%d/%m/%Y"))
        
        tk.Label(f_form, text="Vencimento ASO:", bg="white").grid(row=1, column=4, sticky="w", padx=15)
        self.entry_hcm_aso = ttk.Entry(f_form, width=15)
        self.entry_hcm_aso.grid(row=1, column=5, padx=5, pady=5)
        self.entry_hcm_aso.insert(0, (datetime.now() + timedelta(days=365)).strftime("%d/%m/%Y"))
        
        ttk.Button(f_form, text="Salvar Registro no Departamento Pessoal", command=self.adicionar_colaborador_hcm).grid(row=2, column=0, columnspan=6, pady=12)
        
        f_tabela = tk.LabelFrame(self.aba_hcm, text=" Quadro Geral de Colaboradores e Monitoramento de Saúde Ocupacional (ASO) ", font=("Arial", 11, "bold"), bg="white", padx=10, pady=10)
        f_tabela.pack(fill="both", expand=True, padx=10, pady=10)
        
        colunas = ("id", "nome", "cargo", "salario", "cc", "admissao", "aso", "status")
        self.tree_hcm = ttk.Treeview(f_tabela, columns=colunas, show="headings")
        self.tree_hcm.heading("id", text="ID"); self.tree_hcm.heading("nome", text="Colaborador")
        self.tree_hcm.heading("cargo", text="Cargo"); self.tree_hcm.heading("salario", text="Salário Contratual")
        self.tree_hcm.heading("cc", text="Centro de Custo"); self.tree_hcm.heading("admissao", text="Admissão")
        self.tree_hcm.heading("aso", text="Vencimento ASO"); self.tree_hcm.heading("status", text="Status Compliance ASO")
        
        for col in colunas: self.tree_hcm.column(col, width=130, anchor="center")
        self.tree_hcm.column("nome", width=250, anchor="w")
        self.tree_hcm.pack(fill="both", expand=True)
        self.atualizar_tabela_hcm()

    def adicionar_colaborador_hcm(self):
        try:
            nome = self.entry_hcm_nome.get().strip()
            cargo = self.entry_hcm_cargo.get().strip()
            salario = float(self.entry_hcm_salario.get().strip().replace(".", "").replace(",", "."))
            cc = self.combo_hcm_cc.get()
            adm = self.entry_hcm_admissao.get().strip()
            aso = self.entry_hcm_aso.get().strip()
            
            if not nome or not cargo: raise ValueError
            datetime.strptime(adm, "%d/%m/%Y"); datetime.strptime(aso, "%d/%m/%Y")
            
            with self.api.conectar() as conn:
                conn.cursor().execute("""
                    INSERT INTO colaboradores (usuario_id, nome, cargo, salario, centro_custo, data_admissao, vencimento_aso)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (self.usuario_logado_id, nome, cargo, salario, cc, adm, aso))
                conn.commit()
                
            self.api.registrar_log(self.usuario_logado_id, self.usuario_logado_email, "INSERÇÃO", "colaboradores", f"Ficha de colaborador cadastrada: {nome} | Cargo: {cargo}")
            self.atualizar_tabela_hcm()
            self.entry_hcm_nome.delete(0, tk.END); self.entry_hcm_cargo.delete(0, tk.END); self.entry_hcm_salario.delete(0, tk.END)
        except ValueError:
            messagebox.showerror("Erro de Prontuário", "Revise os campos obrigatórios, numéricos ou formatos de data.")

    def atualizar_tabela_hcm(self):
        for item in self.tree_hcm.get_children(): self.tree_hcm.delete(item)
        with self.api.conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, nome, cargo, salario, centro_custo, data_admissao, vencimento_aso FROM colaboradores WHERE usuario_id = ?", (self.usuario_logado_id,))
            for row in cursor.fetchall():
                try:
                    data_aso = datetime.strptime(row[6], "%d/%m/%Y")
                    if data_aso < datetime.now():
                        status = "🔴 VENCIDO (Bloqueio CIPA)"
                    elif data_aso < (datetime.now() + timedelta(days=30)):
                        status = "🟡 ALERTA (Agendar Renovação)"
                    else:
                        status = "🟢 Regularizado"
                except:
                    status = "Não Informado"
                self.tree_hcm.insert("", "end", values=(row[0], row[1], row[2], f"R$ {row[3]:,.2f}", row[4], row[5], row[6], status))

    # =========================================================================
    # MÓDULO 5: CONTROLADORIA, DRE E AUDITORIA CORPORATIVA (COMPLIANCE / BI)
    # =========================================================================
    def criar_layout_controladoria(self):
        sub_notebook_ctrl = ttk.Notebook(self.aba_controladoria)
        sub_notebook_ctrl.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.sub_aba_dre = ttk.Frame(sub_notebook_ctrl)
        self.sub_aba_orcamento = ttk.Frame(sub_notebook_ctrl)
        self.sub_aba_auditoria = ttk.Frame(sub_notebook_ctrl)
        
        sub_notebook_ctrl.add(self.sub_aba_dre, text="DRE Estruturada")
        sub_notebook_ctrl.add(self.sub_aba_orcamento, text="Planejamento Orçamentário (Budget)")
        sub_notebook_ctrl.add(self.sub_aba_auditoria, text="Trilhas de Auditoria & Compliance LGPD")
        
        # --- SUB-ABA DRE ---
        f_topo_dre = tk.Frame(self.sub_aba_dre, bg="white", padx=10, pady=10)
        f_topo_dre.pack(fill="x")
        tk.Label(f_topo_dre, text="Demonstração do Resultado do Exercício Consolidada", font=("Arial", 11, "bold"), fg="#1a365d", bg="white").pack(side="left")
        ttk.Button(f_topo_dre, text="🖨️ Exportar Relatório Executivo PDF/HTML", command=self.exportar_relatorio_executivo).pack(side="right")
        
        self.tree_dre = ttk.Treeview(self.sub_aba_dre, columns=("item", "valor"), show="headings")
        self.tree_dre.heading("item", text="Estrutura Contábil / Linha da DRE")
        self.tree_dre.heading("valor", text="Montante Consolidado")
        self.tree_dre.column("item", width=650, anchor="w"); self.tree_dre.column("valor", width=250, anchor="e")
        self.tree_dre.pack(fill="both", expand=True, padx=10, pady=10)
        
        # --- SUB-ABA ORÇAMENTO ---
        f_form_orc = tk.LabelFrame(self.sub_aba_orcamento, text=" Definir Teto de Gastos Orçamentários Corporativos (Budget) ", font=("Arial", 10, "bold"), bg="white", padx=10, pady=10)
        f_form_orc.pack(fill="x", padx=10, pady=10)
        tk.Label(f_form_orc, text="Categoria/Setor Alvo:", bg="white").grid(row=0, column=0, sticky="w")
        self.combo_setor_orc = ttk.Combobox(f_form_orc, values=["Geral", "TI", "Marketing", "RH", "Operacional", "Logística"], width=18, state="readonly")
        self.combo_setor_orc.grid(row=0, column=1, padx=5); self.combo_setor_orc.set("TI")
        tk.Label(f_form_orc, text="Limite Financeiro Máximo (R$):", bg="white").grid(row=0, column=2, sticky="w", padx=15)
        self.entry_limite_orc = ttk.Entry(f_form_orc, width=15)
        self.entry_limite_orc.grid(row=0, column=3, padx=5)
        ttk.Button(f_form_orc, text="Gravar Planejamento Orçamentário", command=self.salvar_limite_orcamento).grid(row=0, column=4, padx=20)
        
        self.tree_orcamento = ttk.Treeview(self.sub_aba_orcamento, columns=("cat", "orcado", "realizado", "saldo", "status"), show="headings")
        for col in ["cat", "orcado", "realizado", "saldo", "status"]: self.tree_orcamento.heading(col, text=col.upper())
        self.tree_orcamento.pack(fill="both", expand=True, padx=10, pady=5)
        
        # --- SUB-ABA AUDITORIA ATIVA ---
        f_info_aud = tk.Frame(self.sub_aba_auditoria, bg="#fff5f5", padx=10, pady=10, highlightbackground="#feb2b2", highlightthickness=1)
        f_info_aud.pack(fill="x", padx=10, pady=5)
        tk.Label(f_info_aud, text="🔒 TRILHA DE AUDITORIA CONTÍNUA (LGPD & GOVERNANÇA CORPORATIVA)\nTodos os acessos, inserções, alterações e force de travas de segurança são gravados automaticamente com captura de IP.", font=("Arial", 9, "bold"), fg="#9b2c2c", bg="#fff5f5", justify="left").pack(side="left")
        
        colunas_aud = ("id", "user", "perfil", "acao", "tabela", "desc", "dh", "ip")
        self.tree_auditoria = ttk.Treeview(self.sub_aba_auditoria, columns=colunas_aud, show="headings")
        for col in colunas_aud: self.tree_auditoria.heading(col, text=col.upper()); self.tree_auditoria.column(col, width=110, anchor="center")
        self.tree_auditoria.column("desc", width=300, anchor="w")
        self.tree_auditoria.pack(fill="both", expand=True, padx=10, pady=10)

    def calcular_dre_estruturada(self):
        for item in self.tree_dre.get_children(): self.tree_dre.delete(item)
        with self.api.conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT SUM(valor_bruto), SUM(impostos_retidos), SUM(valor_liquido) FROM contas_receber WHERE usuario_id = ?", (self.usuario_logado_id,))
            res_rec = cursor.fetchone()
            bruto = res_rec[0] or 0.0
            retido = res_rec[1] or 0.0
            liquido = res_rec[2] or 0.0
            
            # Custo de Pessoal oriundo do módulo de Recursos Humanos (HCM)
            cursor.execute("SELECT SUM(salario) FROM colaboradores WHERE usuario_id = ?", (self.usuario_logado_id,))
            custo_folha = cursor.fetchone()[0] or 0.0
            
            cursor.execute("SELECT SUM(valor) FROM contas_pagar WHERE usuario_id = ?", (self.usuario_logado_id,))
            despesas_operacionais = cursor.fetchone()[0] or 0.0
            
        resultado_liquido_exercicio = liquido - custo_folha - despesas_operacionais
        
        self.tree_dre.insert("", "end", values=("1. RECEITA BRUTA DE VENDAS E SERVIÇOS", f"R$ {bruto:,.2f}"))
        self.tree_dre.insert("", "end", values=("     (-) Deduções de Impostos e Retenções Fiscais", f"R$ {retido:,.2f}"))
        self.tree_dre.insert("", "end", values=("2. RECEITA LÍQUIDA OPERACIONAL", f"R$ {liquido:,.2f}"))
        self.tree_dre.insert("", "end", values=("     (-) Custos com Pessoal e Folha de Pagamento (HCM)", f"R$ {custo_folha:,.2f}"))
        self.tree_dre.insert("", "end", values=("     (-) Despesas Operacionais e Administrativas Gerais", f"R$ {despesas_operacionais:,.2f}"))
        self.tree_dre.insert("", "end", values=("=" * 60, "=" * 30))
        self.tree_dre.insert("", "end", values=("3. RESULTADO LÍQUIDO DO EXERCÍCIO (LUCRO/PREJUÍZO)", f"R$ {resultado_liquido_exercicio:,.2f}"))

    def salvar_limite_orcamento(self):
        cat = self.combo_setor_orc.get()
        try:
            limite = float(self.entry_limite_orc.get().strip().replace(".", "").replace(",", "."))
            with self.api.conectar() as conn:
                conn.cursor().execute("INSERT INTO orcamento (usuario_id, categoria, limite) VALUES (?, ?, ?) ON CONFLICT(usuario_id, categoria) DO UPDATE SET limite = excluded.limite",
                                    (self.usuario_logado_id, cat, limite))
                conn.commit()
                
            self.api.registrar_log(self.usuario_logado_id, self.usuario_logado_email, "ALTERAÇÃO ORÇAMENTO", "orcamento", f"Teto orçamentário definido para {cat}: R$ {limite:,.2f}")
            self.entry_limite_orc.delete(0, tk.END)
            self.atualizar_tabela_orcamento()
            messagebox.showinfo("Sucesso", f"Budget para {cat} estabelecido com sucesso.")
        except ValueError:
            messagebox.showerror("Erro", "Valor de limite financeiro inválido.")

    def atualizar_tabela_orcamento(self):
        for item in self.tree_orcamento.get_children(): self.tree_orcamento.delete(item)
        with self.api.conectar() as conn:
            cursor = conn.cursor()
            for cat in ["Geral", "TI", "Marketing", "RH", "Operacional", "Logística"]:
                cursor.execute("SELECT limite FROM orcamento WHERE usuario_id = ? AND categoria = ?", (self.usuario_logado_id, cat))
                res = cursor.fetchone()
                limite = res[0] if res else 0.0
                cursor.execute("SELECT SUM(valor) FROM contas_pagar WHERE usuario_id = ? AND categoria = ?", (self.usuario_logado_id, cat))
                realizado = cursor.fetchone()[0] or 0.0
                saldo = limite - realizado
                status = "Sem Teto" if limite == 0 else ("🔴 EXCEDIDO" if saldo < 0 else "🟢 Conforme")
                self.tree_orcamento.insert("", "end", values=(cat, f"R$ {limite:,.2f}", f"R$ {realizado:,.2f}", f"R$ {saldo:,.2f}", status))

    def atualizar_tabela_auditoria(self):
        for item in self.tree_auditoria.get_children(): self.tree_auditoria.delete(item)
        if self.usuario_logado_perfil != "Admin": return # Trava RBAC para visualização de Logs de Auditoria
        with self.api.conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT a.id, a.usuario_email, u.perfil, a.acao, a.tabela_afetada, a.descricao, a.data_hora, a.ip_maquina FROM auditoria a LEFT JOIN usuarios u ON a.usuario_id = u.id ORDER BY a.id DESC")
            for row in cursor.fetchall(): self.tree_auditoria.insert("", "end", values=row)

    def exportar_relatorio_executivo(self):
        """
        Mecanismo Avançado de BI: Exporta relatórios contábeis corporativos diretamente
        em HTML executivo responsivo com suporte nativo de impressão em PDF scaneável.
        """
        with self.api.conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT SUM(valor_bruto), SUM(impostos_retidos), SUM(valor_liquido) FROM contas_receber WHERE usuario_id = ?", (self.usuario_logado_id,))
            res_rec = cursor.fetchone()
            bruto = res_rec[0] or 0.0; retido = res_rec[1] or 0.0; liquido = res_rec[2] or 0.0
            cursor.execute("SELECT SUM(salario) FROM colaboradores WHERE usuario_id = ?", (self.usuario_logado_id,))
            folha = cursor.fetchone()[0] or 0.0
            cursor.execute("SELECT SUM(valor) FROM contas_pagar WHERE usuario_id = ?", (self.usuario_logado_id,))
            despesas = cursor.fetchone()[0] or 0.0
            
        resultado = liquido - folha - despesas
        
        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; color: #333; }}
                .header {{ text-align: center; border-bottom: 2px solid #1a365d; padding-bottom: 20px; }}
                .title {{ color: #1a365d; font-size: 24px; font-weight: bold; }}
                .meta {{ font-size: 11px; color: #666; margin-top: 5px; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 30px; }}
                th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
                th {{ background-color: #f4f6f9; color: #1a365d; font-weight: bold; }}
                .bold {{ font-weight: bold; color: #1a365d; }}
                .right {{ text-align: right; }}
                .total-row {{ background-color: #e2e8f0; font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="header">
                <div class="title">RELATÓRIO EXECUTIVO - DEMONSTRAÇÃO DO RESULTADO (DRE)</div>
                <div class="meta">Emitido por: {self.usuario_logado_email} | Data de Emissão: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</div>
            </div>
            <table>
                <thead>
                    <tr><th>Estrutura Contábil da Demonstração</th><th class="right">Valor Acumulado (R$)</th></tr>
                </thead>
                <tbody>
                    <tr><td class="bold">1. RECEITA OPERACIONAL BRUTA</td><td class="right bold">R$ {bruto:,.2f}</td></tr>
                    <tr><td>(-) Deduções de Impostos (Motor Fiscal Automático)</td><td class="right">R$ {retido:,.2f}</td></tr>
                    <tr class="bold"><td>2. RECEITA OPERACIONAL LÍQUIDA</td><td class="right">R$ {liquido:,.2f}</td></tr>
                    <tr><td>(-) Custos Operacionais com Pessoal e Prontuários (HCM)</td><td class="right">R$ {folha:,.2f}</td></tr>
                    <tr><td>(-) Despesas Administrativas e Operacionais Gerais</td><td class="right">R$ {despesas:,.2f}</td></tr>
                    <tr class="total-row"><td>3. RESULTADO LÍQUIDO DO EXERCÍCIO (LUCRO COMPLIANCE)</td><td class="right">R$ {resultado:,.2f}</td></tr>
                </tbody>
            </table>
        </body>
        </html>
        """
        caminho_arquivo = os.path.abspath("Relatorio_Executivo_DRE.html")
        with open(caminho_arquivo, "w", encoding="utf-8") as f:
            f.write(html_content)
        webbrowser.open(f"file://{caminho_arquivo}")
        self.api.registrar_log(self.usuario_logado_id, self.usuario_logado_email, "EXPORTAÇÃO", "contas_receber", "Relatório Executivo DRE exportado em HTML/PDF.")

    # =========================================================================
    # MÓDULO 6: CONCILIAÇÃO BANCÁRIA & ECOSSISTEMA OPEN FINANCE AUTOMÁTICO
    # =========================================================================
    def criar_layout_conciliacao(self):
        f_topo = tk.Frame(self.aba_conciliacao, bg="white", padx=15, pady=15)
        f_topo.pack(fill="x", padx=10, pady=5)
        
        tk.Label(f_topo, text="Conciliador de Extratos Integrado", font=("Arial", 12, "bold"), fg="#1a365d", bg="white").pack(side="left")
        
        # Inovação de BI/Open Finance: Integração automatizada em background
        ttk.Button(f_topo, text="🔄 Sincronizar via Open Finance API", command=self.disparar_sincronismo_open_finance).pack(side="right", padx=10)
        ttk.Button(f_topo, text="📁 Carga de Extrato Manual (OFX)", command=self.importar_extrato_manual_ofx).pack(side="right")
        
        self.tree_conciliacao = ttk.Treeview(self.aba_conciliacao, columns=("id", "data", "desc", "valor", "origem", "status"), show="headings")
        for col in ["id", "data", "desc", "valor", "origem", "status"]: self.tree_conciliacao.heading(col, text=col.upper()); self.tree_conciliacao.column(col, width=130, anchor="center")
        self.tree_conciliacao.column("desc", width=350, anchor="w")
        self.tree_conciliacao.pack(fill="both", expand=True, padx=10, pady=10)
        
        ttk.Button(self.aba_conciliacao, text="Validar & Conciliar Lançamento Selecionado", command=self.mudar_status_conciliacao).pack(pady=10)

    def importar_extrato_manual_ofx(self):
        caminho = filedialog.askopenfilename(filetypes=[("Arquivos de Extrato", "*.ofx")])
        if not caminho: return
        
        with self.api.conectar() as conn:
            # Emulação de Parse OFX estruturado
            conn.cursor().execute("INSERT INTO movimentacoes_bancarias (usuario_id, data_movimento, descricao, valor, conciliado, origem_dados) VALUES (?, ?, 'Tarifa Conta Corrente PJ', -49.90, 0, 'OFX Manual')", (self.usuario_logado_id, datetime.now().strftime("%d/%m/%Y")))
            conn.commit()
        self.atualizar_tabela_conciliacao()
        messagebox.showinfo("Carga Manual", "Registros do arquivo OFX importados para conciliação.")

    def disparar_sincronismo_open_finance(self):
        """
        Módulo Open Finance: Executa chamada assíncrona em background simulando a 
        comunicação com APIs bancárias via barramento seguro.
        """
        popup = tk.Toplevel(self.root)
        popup.title("Conexão Segura Open Finance")
        popup.geometry("350x150")
        popup.configure(bg="white")
        popup.transient(self.root)
        popup.grab_set()
        
        tk.Label(popup, text="Autenticando no Barramento Central Interbancário...", font=("Arial", 9, "bold"), bg="white", fg="#4a5568").pack(pady=15)
        progress = ttk.Progressbar(popup, orient="horizontal", length=250, mode="determinate")
        progress.pack(pady=5)
        
        def run_sync():
            import time
            import random
            for i in range(1, 101, 20):
                time.sleep(0.3)
                self.root.after(0, lambda val=i: progress.configure(value=val))
                
            # Carga de lançamentos automáticos via Open Finance
            lancamentos = [
                ("Liquidação Cartão de Crédito Corporate Caju", -1250.40),
                ("PIX Recebido Cliente Consultoria Demo", 8500.00),
                ("TED Liquidação de Duplicata Cliente SP", 3200.00)
            ]
            
            with self.api.conectar() as conn:
                cursor = conn.cursor()
                dt = datetime.now().strftime("%d/%m/%Y")
                for desc, val in lancamentos:
                    cursor.execute("INSERT INTO movimentacoes_bancarias (usuario_id, data_movimento, descricao, valor, conciliado, origem_dados) VALUES (?, ?, ?, ?, 0, 'Open Finance API')",
                                   (self.usuario_logado_id, dt, desc, val))
                conn.commit()
                
            self.api.registrar_log(self.usuario_logado_id, self.usuario_logado_email, "OPEN FINANCE", "movimentacoes_bancarias", f"Sincronização realizada com sucesso. {len(lancamentos)} novos registros importados das APIs bancárias.")
            
            self.root.after(0, lambda: [popup.destroy(), self.atualizar_tabela_conciliacao(), messagebox.showinfo("Open Finance", "Sincronização Concluída!\nNovos lançamentos capturados automaticamente via API.")])

        threading.Thread(target=run_sync, daemon=True).start()

    def mudar_status_conciliacao(self):
        selecionado = self.tree_conciliacao.selection()
        selectedCard = selecionado
        if not selectedCard:
            messagebox.showwarning("Aviso", "Selecione o registro bancário para conciliação.")
            return
        valores = self.tree_conciliacao.item(selectedCard[0], "values")
        id_mov = valores[0]
        status = valores[5]
        
        novo = 1 if "Pendente" in status else 0
        with self.api.conectar() as conn:
            conn.cursor().execute("UPDATE movimentacoes_bancarias SET conciliado = ? WHERE id = ? AND usuario_id = ?", (novo, id_mov, self.usuario_logado_id))
            conn.commit()
        self.atualizar_tabela_conciliacao()

    def atualizar_tabela_conciliacao(self):
        for item in self.tree_conciliacao.get_children(): self.tree_conciliacao.delete(item)
        with self.api.conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, data_movimento, descricao, valor, origem_dados, conciliado FROM movimentacoes_bancarias WHERE usuario_id = ?", (self.usuario_logado_id,))
            for row in cursor.fetchall():
                st = "🟢 Conciliado" if row[5] == 1 else "🔴 Pendente"
                self.tree_conciliacao.insert("", "end", values=(row[0], row[1], row[2], f"R$ {row[3]:,.2f}", row[4], st))

    # =========================================================================
    # RENDERIZAÇÃO DO REPOSITÓRIO GRÁFICO (DASHBOARD BI)
    # =========================================================================
    def renderizar_dashboard_executivo(self):
        for widget in self.aba_dashboard.winfo_children(): widget.destroy()
        
        with self.api.conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT SUM(valor_bruto) FROM contas_receber WHERE usuario_id = ?", (self.usuario_logado_id,))
            faturamento = cursor.fetchone()[0] or 0.0
            cursor.execute("SELECT SUM(valor) FROM contas_pagar WHERE usuario_id = ?", (self.usuario_logado_id,))
            despesas = cursor.fetchone()[0] or 0.0
            cursor.execute("SELECT SUM(salario) FROM colaboradores WHERE usuario_id = ?", (self.usuario_logado_id,))
            folha = cursor.fetchone()[0] or 0.0
            
        total_saidas = despesas + folha
        lucro = faturamento - total_saidas
        
        f_cards = ttk.Frame(self.aba_dashboard)
        f_cards.pack(fill="x", padx=10, pady=10)
        
        kpis = [
            ("Faturamento Bruto Consolidado", f"R$ {faturamento:,.2f}", "#2f855a"),
            ("Custos Operacionais + Pessoal", f"R$ {total_saidas:,.2f}", "#c53030"),
            ("Resultado do Exercício (EBITDA)", f"R$ {lucro:,.2f}", "#2b6cb0" if lucro >= 0 else "#c53030")
        ]
        
        for i, (tit, val, cor) in enumerate(kpis):
            card = tk.Frame(f_cards, bg="white", highlightbackground="#e2e8f0", highlightthickness=1, padx=15, pady=15)
            card.grid(row=0, column=i, padx=10, pady=5, sticky="nsew")
            tk.Label(card, text=tit, font=("Arial", 9, "bold"), fg="#718096", bg="white").pack(anchor="w")
            tk.Label(card, text=val, font=("Arial", 16, "bold"), fg=cor, bg="white", pady=5).pack(anchor="w")
            f_cards.grid_columnconfigure(i, weight=1)
            
        f_grafico = ttk.Frame(self.aba_dashboard)
        f_grafico.pack(fill="both", expand=True, padx=10, pady=10)
        
        fig, ax = plt.subplots(figsize=(10, 3.5))
        fig.patch.set_facecolor('#f4f6f9')
        ax.bar(['Faturamento', 'Custos de Operação', 'Resultado Líquido'], [faturamento, total_saidas, lucro], color=['#2f855a', '#c53030', '#2b6cb0'], width=0.4)
        ax.set_title("Visão Analítica BI - Saúde Financeira da Empresa", fontdict={'fontsize': 11, 'weight': 'bold', 'color': '#1a365d'})
        
        canvas = FigureCanvasTkAgg(fig, master=f_grafico)
        canvas.get_tk_widget().pack(fill="both", expand=True)
        canvas.draw()

# Inicialização e Execução Segura do App ERP Enterprise
if __name__ == "__main__":
    root = tk.Tk()
    app = AppControleFinanceiro(root)
    root.mainloop()