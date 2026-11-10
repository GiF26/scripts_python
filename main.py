import csv
import re
from pathlib import Path

import pyodbc


# --- Configuração -----------------------------------------------------------

ARQUIVO = Path(
    r"C:\Utilitarios\Dados\Convenio\Gravia\20261104"
    r"\TXDIG261005_261009\TXDIG_VW_FASTERIX_CLIENTES_TELEFONES0001.sql"
)
CONEXAO = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=localhost;DATABASE=VM_DIGGER;Trusted_Connection=yes;"
)
TABELA = "dbo.VW_FASTERIX_CLIENTES_TELEFONES"

# Ordem das colunas no INSERT da tabela de destino
COLUNAS_TABELA = [
    "CODIGO", "NOME", "TIPO_CLIENTE", "CPF_X", "EMAIL",
    "DDDTELEFONE", "TELEFONE", "DDDTELEFONE2", "TELEFONE2", "SEQUENCIA",
    "DDDTELEFONECONTATO", "TELEFONECONTATO", "NOME_CONTATO", "EMAIL_CONTATO",
]

# Colunas assumidas quando o INSERT não traz a lista de colunas
# COLUNAS_PADRAO = [
#     "TIPO_CLIENTE", "CPF", "CODIGO", "NOME", "EMAIL",
#     "DDDTELEFONE", "TELEFONE", "DDDTELEFONE2", "TELEFONE2", "SEQUENCIA",
#     "DDDTELEFONECONTATO", "TELEFONECONTATO", "NOME_CONTATO", "EMAIL_CONTATO",
# ]

# Nome normalizado da coluna no arquivo -> coluna na tabela.
# Ex.: "Código" e "C�digo" (encoding quebrado) viram ambos "cdigo".
MAPA_COLUNAS = {
    "tipocliente":          "TIPO_CLIENTE",
    "cpf":                  "CPF",
    "cdigo":                "CODIGO",
    "nome":                 "NOME",
    "email":                "EMAIL",
    "dddtelefone1":         "DDDTELEFONE",
    "telefone1":            "TELEFONE",
    "dddtelefone2":         "DDDTELEFONE2",
    "telefone2":            "TELEFONE2",
    "sequncia":             "SEQUENCIA",
    "dddtelefonedocontato": "DDDTELEFONECONTATO",
    "telefonedocontato":    "TELEFONECONTATO",
    "nomedocontato":        "NOME_CONTATO",
    "emaildocontato":       "EMAIL_CONTATO",
}

COLUNAS_INTEIRAS = {"CODIGO", "SEQUENCIA"}

REGEX_INSERT = re.compile(
    r"insert\s+into\s+\S+\s*(?:\((.*?)\)\s*)?values\s*\((.*)\)\s*;",
    re.IGNORECASE,
)


# --- Leitura do arquivo -----------------------------------------------------

def normalizar_nome(nome: str) -> str:
    """Mantém só letras ASCII e dígitos, em minúsculas."""
    return re.sub(r"[^A-Za-z0-9]", "", nome).lower()


def mapear_colunas(lista_colunas: str | None, num_linha: int) -> list[str]:
    """Converte a lista de colunas do INSERT nos nomes da tabela."""
    # if not lista_colunas:
    #     return COLUNAS_PADRAO

    nomes = [n.strip() for n in lista_colunas.split(",")]
    destinos = [MAPA_COLUNAS.get(normalizar_nome(n)) for n in nomes]

    nao_mapeadas = [n for n, d in zip(nomes, destinos) if d is None]
    if nao_mapeadas:
        raise ValueError(f"Linha {num_linha}: colunas sem mapeamento: {nao_mapeadas}")

    return destinos


def converter_valor(coluna: str, valor: str) -> str | int | None:
    """Trata string vazia como NULL e converte colunas inteiras."""
    valor = valor.strip()
    if valor == "":
        return None
    if coluna in COLUNAS_INTEIRAS:
        return int(valor)
    return valor


def ler_linha_insert(linha: str, num_linha: int) -> dict | None:
    """Lê um INSERT e devolve um dict {coluna_da_tabela: valor}.
    Retorna None para linhas que não são INSERT (comentários, USE, DELETE, GO...).
    """
    m = REGEX_INSERT.search(linha)
    if not m:
        return None

    lista_colunas, lista_valores = m.group(1), m.group(2)
    colunas = mapear_colunas(lista_colunas, num_linha)

    valores = next(csv.reader([lista_valores], quotechar="'", skipinitialspace=True))
    if len(valores) != len(colunas):
        raise ValueError(
            f"Linha {num_linha}: {len(valores)} valores para {len(colunas)} colunas"
        )

    # Colunas que o INSERT não trouxe ficam None
    registro = {col: None for col in MAPA_COLUNAS.values()}
    for col, valor in zip(colunas, valores):
        registro[col] = converter_valor(col, valor)
    return registro


def ler_arquivo(caminho: Path) -> list[dict]:
    registros = []
    with caminho.open(encoding="cp1252", errors="replace") as f:
        for num_linha, linha in enumerate(f, 1):
            registro = ler_linha_insert(linha, num_linha)
            if registro is not None:
                registros.append(registro)
    return registros


# --- Tratamento dos dados ---------------------------------------------------

# def normalizar_cpf(documento: str | None) -> str | None:
#     """CPF tem até 11 dígitos; CNPJ tem 14. Completa com zeros à esquerda."""
#     if not documento:
#         return None
#     tamanho = 14 if len(documento) > 11 else 11
#     return documento.zfill(tamanho)


def escolher_contato_principal(registros: list[dict]) -> list[dict]:
    """Uma linha por cliente: fica o contato de menor sequência."""
    escolhidos: dict[tuple[str, str], dict] = {}

    for reg in registros:
        codigo = reg["CODIGO"]
        tipo = reg["TIPO_CLIENTE"]
        cpf = reg["CPF"]
        sequencia = reg["SEQUENCIA"] or 0

        if cpf is None or tipo is None:
            continue

        chave = (codigo, tipo, cpf, sequencia)

        atual = escolhidos.get(chave)

        escolhidos[chave] = {**reg,
                             "CODIGO": codigo,
                             "TIPO_CLIENTE": tipo,
                             "CPF_X": cpf,
                             "SEQUENCIA": sequencia}
        if atual is None or seq < atual["SEQUENCIA"]:
            pass

    return list(escolhidos.values())


def montar_linhas_destino(clientes: list[dict]) -> list[tuple]:
    """Monta as tuplas na ordem das colunas da tabela de destino."""
    linhas = []
    for c in clientes:
        linhas.append((
            c["CODIGO"],
            (c["NOME"] or "")[:50] or None,
            c["TIPO_CLIENTE"][:10],
            c["CPF_X"],
            c["EMAIL"],
            c["DDDTELEFONE"],
            c["TELEFONE"],
            c["DDDTELEFONE2"],
            c["TELEFONE2"],
            c["SEQUENCIA"],
            c["DDDTELEFONECONTATO"],
            c["TELEFONECONTATO"],
            (c["NOME_CONTATO"] or "")[:50] or None,
            c["EMAIL_CONTATO"],
        ))
    return linhas


# --- Gravação ---------------------------------------------------------------

def gravar(linhas: list[tuple]) -> None:
    """Apaga e recarrega a tabela numa única transação."""
    colunas = ", ".join(COLUNAS_TABELA)
    placeholders = ", ".join("?" * len(COLUNAS_TABELA))
    sql_insert = f"INSERT INTO {TABELA} ({colunas}) VALUES ({placeholders})"

    with pyodbc.connect(CONEXAO) as cn:
        cur = cn.cursor()
        cur.fast_executemany = True
        cur.execute(f"DELETE FROM {TABELA};")
        cur.executemany(sql_insert, linhas)
        cn.commit()


# --- Execução ---------------------------------------------------------------

def main() -> None:
    registros = ler_arquivo(ARQUIVO)
    clientes = escolher_contato_principal(registros)
    linhas = montar_linhas_destino(clientes)

    print(f"Lidos: {len(registros)} | Clientes após deduplicação: {len(linhas)}")
    gravar(linhas)
    print("Carga concluída.")


if __name__ == "__main__":
    main()