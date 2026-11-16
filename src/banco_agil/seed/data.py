CUSTOMERS_FILE = "clientes.csv"
SCORE_LIMITS_FILE = "score_limite.csv"
LIMIT_REQUESTS_FILE = "solicitacoes_aumento_limite.csv"

CUSTOMERS_COLUMNS = ["cpf", "nome", "data_nascimento", "limite_credito", "score_credito"]
CUSTOMERS_ROWS = [
    ["11144477735", "Ana Souza", "1990-05-17", "5000.00", "650"],
    ["52998224725", "Bruno Lima", "1985-11-02", "1000.00", "300"],
    ["39053344705", "Carla Mendes", "1992-03-28", "3000.00", "501"],
    ["16899535009", "Diego Alves", "1978-08-09", "40000.00", "850"],
    ["74519126800", "Elisa Prado", "2001-01-30", "8000.00", "700"],
    ["28145637937", "Fábio Teixeira", "1969-12-12", "500.00", "0"],
]

SCORE_LIMITS_COLUMNS = ["score_minimo", "score_maximo", "limite_maximo"]
SCORE_LIMITS_ROWS = [
    ["0", "300", "1000.00"],
    ["301", "500", "5000.00"],
    ["501", "700", "15000.00"],
    ["701", "1000", "40000.00"],
]

LIMIT_REQUESTS_COLUMNS = [
    "cpf_cliente",
    "data_hora_solicitacao",
    "limite_atual",
    "novo_limite_solicitado",
    "status_pedido",
]
LIMIT_REQUESTS_ROWS: list[list[str]] = []

DATASETS = {
    CUSTOMERS_FILE: (CUSTOMERS_COLUMNS, CUSTOMERS_ROWS),
    SCORE_LIMITS_FILE: (SCORE_LIMITS_COLUMNS, SCORE_LIMITS_ROWS),
    LIMIT_REQUESTS_FILE: (LIMIT_REQUESTS_COLUMNS, LIMIT_REQUESTS_ROWS),
}
