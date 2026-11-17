from typing import cast
from pathlib import Path

import shutil
import pyodbc
import pdfplumber
import mysql.connector

# --- CONFIGURAÇÕES ---
ARQUIVO_PDF = "relatorios/Financeiro - 2026 - Janeiro .pdf"
TABELA = "CARGA_PLANILHA"

# Parâmetros de conexão direta ao MySQL (sem ODBC)
CONFIG_BANCO = {
    "host": "localhost",
    "user": "root",
    "password": "root",
    "database": "IZZY_FINANCS",
    "port": 3306
}

COLUNAS_TABELA = ["ID", "ID_USUARIO", "DESCRICAO", "VALOR", "OBSERVACAO", "TIPO", "MES"]

########################### Funçao limpa String valor ###########################
def limpar_valor(valor_texto):
    if not valor_texto:
        return 0.0

    texto_limpo = str(valor_texto).replace("R$", "").strip()

    if "," in texto_limpo:
        texto_limpo = texto_limpo.replace(".", "").replace(",", ".")

    return float(texto_limpo)

########################### Processo ###########################

def carregar_saidas(caminho_pdf, mes):
    saidas = []
    contador = 1

    with pdfplumber.open(caminho_pdf) as pdf:
        tabela = pdf.pages[0].extract_table()

        for linha in tabela:
            if linha[0] == "Entradas acumuladas":
                break

            if linha[0] and linha[0] not in ["Despesas", "Descrição", "Total Gasto", "Total Restante"]:
                descricao = linha[0]
                valor = limpar_valor(linha[1])
                observacao = linha[2] if len(linha) > 2 and linha[2] else ""

                saidas.append({
                    "id": contador,
                    "id_usuario": 1,
                    "descricao": descricao,
                    "valor": valor,
                    "observacao": observacao,
                    "tipo": 1,
                    "mes": mes
                })

                contador += 1

    return saidas


def carregar_entradas(caminho_pdf, mes):
    entradas = []
    ler_entradas = False
    contador = 1

    with pdfplumber.open(caminho_pdf) as pdf:
        tabela = pdf.pages[0].extract_table()

        for linha in tabela:
            if linha[0] == "Entradas acumuladas":
                ler_entradas = True
                continue

            if ler_entradas:
                if linha[0] and "Tabela para gerar gráfico" in linha[0]:
                    break

                if linha[0] and linha[0] not in ["Descrição", "Total", "Total - Divida"]:
                    desc = linha[0]
                    valor = limpar_valor(linha[1])
                    rendimento = linha[2] if len(linha) > 2 and linha[2] else ""

                    # Monta a observação concatenando o rendimento se existir
                    obs = f"Rendimento: {rendimento}" if rendimento else ""

                    # TUDO DENTRO DO IF (com 4 espaços a mais de recuo):
                    entradas.append({
                        "id": contador,
                        "id_usuario": 1,
                        "descricao": desc,
                        "valor": valor,
                        "observacao": obs,
                        "tipo": 0,
                        "mes": mes
                    })

                    contador += 1  # Incrementa o contador aqui dentro

    return entradas


########################### Gravação no Banco ###########################

def gravar(registros: list) -> None:
    if not registros:
        print("Nenhum registro para gravar.")
        return

    colunas = ", ".join(COLUNAS_TABELA)
    placeholders = ", ".join(["%s"] * len(COLUNAS_TABELA))
    sql_insert = f"INSERT INTO {TABELA} ({colunas}) VALUES ({placeholders})"

    dados_para_inserir = [
        tuple(item[col.lower()] for col in COLUNAS_TABELA)
        for item in registros
    ]

    # Conexão direta via mysql-connector
    conexao = mysql.connector.connect(**CONFIG_BANCO)
    cursor = conexao.cursor()

    cursor.executemany(sql_insert, dados_para_inserir)
    conexao.commit()

    print(f"✅ {cursor.rowcount} registros inseridos com sucesso!")

    cursor.close()
    conexao.close()


################## Execução #####################

def main() -> None:
    print("Iniciando leitura do PDF...")

    pasta_relatorios = Path("relatorios")
    i = 0;

    # .glob("*.pdf") busca automaticamente TODOS os arquivos que terminam com .pdf na pasta
    for arquivo_pdf in pasta_relatorios.glob("*.pdf"):
        print(f"\n📄 Processando arquivo: {arquivo_pdf.name}")

        i += 1
        # Passamos 'arquivo_pdf' (o caminho dinâmico) para as suas funções
        lista_entradas = carregar_entradas(arquivo_pdf, i)
        lista_saidas = carregar_saidas(arquivo_pdf, i)

        print(f"Entradas encontradas: {len(lista_entradas)} | Saídas encontradas: {len(lista_saidas)}")

        # Grava no MySQL os dados deste arquivo
        gravar(lista_entradas)
        gravar(lista_saidas)

        # Dentro do loop, logo após o gravar():
        pasta_destino = Path("relatorios/processados")
        pasta_destino.mkdir(exist_ok=True)  # Cria a pasta 'processados' se não existir
        shutil.move(str(arquivo_pdf), str(pasta_destino / arquivo_pdf.name))

    print("\n🎉 Todos os arquivos da pasta foram processados e gravados com sucesso!")

if __name__ == "__main__":
    main()