# 🏢 Nexus ERP v1 — Primeira versão do ERP Enterprise

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?logo=sqlite&logoColor=white)
![Status](https://img.shields.io/badge/status-versão%20legada-lightgrey)

Primeira versão completa do **Nexus ERP**: sistema desktop de gestão com financeiro, estoque, RH, controladoria, conciliação bancária e controle de acesso por perfil.

> 👉 **A versão mais recente e evoluída está em [nexus-erp](https://github.com/walacevdgicm-ops/nexus-erp)**, com hash de senhas, consulta pública de CNPJ e melhorias de arquitetura. Este repositório fica como registro da evolução do projeto.

## ✨ O que já existia nesta versão

- 🔐 Login com **RBAC** (Admin, Financeiro, Faturamento, Estoque, RH)
- 👥 Cadastro de clientes e fornecedores com busca automática de **CNPJ**
- 💸 Contas a pagar e a receber · 🧾 simulador de NF-e
- 📦 Controle de estoque · 👔 cadastro de colaboradores
- 📊 **DRE** e orçamento por centro de custo
- 🏦 Importação de extrato **OFX** e simulação de Open Finance
- 🕵️ Trilha de auditoria e 📈 dashboard com Matplotlib

## 🚀 Como executar

```bash
pip install -r requirements.txt
python nexus_erp_v1.py
```

Login de demonstração: `admin@nexusdemo.com.br` / `admin123` (dados fictícios).

## 👨‍💻 Autor

**Walace Soares Vidigal Junior** · [GitHub](https://github.com/walacevdgicm-ops)

Licença [MIT](LICENSE)
