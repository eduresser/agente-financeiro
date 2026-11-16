# Arquitetura

## Visão geral

Um único grafo LangGraph com estado compartilhado atende toda a conversa. O cliente fala com um atendente só; internamente, nós diferentes cuidam de cada etapa e a resposta final vem sempre do último nó da vez.

## Fluxo de uma mensagem

1. O guardrail de entrada verifica a mensagem. Se for bloqueada, o cliente recebe uma resposta fixa e nenhum agente é acionado.
2. O roteador escolhe o nó pela fase da conversa: `auth`, `active` ou `ended`.
3. Na fase `auth`, um nó de código valida CPF e data de nascimento, sem chamar o modelo.
4. Na fase `active`, a triagem classifica o assunto e entrega para crédito, entrevista ou câmbio.
5. Um agente pode passar o controle a outro na mesma rodada, sem emitir resposta própria.
6. O guardrail de saída verifica cada resposta antes de chegar ao cliente.

## Estado do grafo

| Campo | Para quê |
|---|---|
| `messages` | Histórico da conversa |
| `phase` | `auth`, `active` ou `ended` |
| `auth_attempts`, `cpf_candidate` | Fluxo de autenticação |
| `customer_cpf` | Cliente autenticado |
| `active_agent` | `triage`, `credit`, `interview` ou `exchange` |
| `pending_limit` | Valor do aumento rejeitado, usado na reanálise |
| `interview` | Respostas já coletadas e score calculado |
| `blocked_streak`, `blocked_input` | Bloqueios seguidos dos guardrails |

## Módulos

| Pasta | Responsabilidade |
|---|---|
| `config.py`, `llm.py` | Configuração por variáveis de ambiente e fábrica do modelo |
| `logging_utils.py`, `observability.py` | Mascaramento de CPF em logs e traces |
| `domain/` | Regras puras: CPF, autenticação, regras de crédito e score |
| `storage/` | Repositórios CSV com gravação atômica |
| `exchange/` | Interface de cotação e implementação da AwesomeAPI |
| `guardrails/` | Interface, regras locais e modelo juiz |
| `tools/` | Ferramentas de cada agente, com o CPF já injetado |
| `graph/` | Estado, nós, agentes e montagem do grafo |
| `service.py` | Fachada de conversa, persistência e tratamento de erro |
| `ui/` | Tela Streamlit |

## Decisões

| Decisão | Motivo |
|---|---|
| Autenticação em código, com mensagens fixas | Barata, testável e imune a manipulação por texto |
| CPF injetado nas ferramentas por código | O modelo não consegue pedir dados de outro cliente |
| Agentes conduzidos pelo modelo, com ferramentas de escopo fechado | Conversa natural sem abrir mão de regras |
| Entrevista com ordem e validação em ferramentas | O modelo escolhe as palavras; o código garante a sequência e a validade |
| Reanálise após a entrevista executada por código | Não depende de o modelo lembrar do pedido |
| Regras de negócio em funções puras | Testáveis sem modelo |
| CSV gravado em arquivo temporário e renomeado | Falha no meio da gravação não corrompe a base |
| Guardrails atrás da interface `Guardrail` | Permite trocar por um serviço gerenciado sem mexer nos agentes |
| Modelo juiz só em caso de suspeita; falha do juiz bloqueia | Economiza chamadas e falha de forma segura |
| Fachada `ChatService.send` como único ponto de entrada | Captura qualquer exceção e devolve resposta amigável |
| Checkpointer SQLite indexado pelo identificador da conversa | Retoma a conversa após reinício |
| CPF validado pelos dígitos verificadores | Descarta erros de digitação antes de consultar a base |

## Segurança e privacidade

- O CPF aparece mascarado (`***.456.789-**`) em logs, eventos de bloqueio e traces.
- O texto livre digitado pelo cliente não é registrado em logs nem enviado a traces.
- Uma mensagem bloqueada é removida do histórico depois de gerar a resposta fixa.
- Respostas com CPF, score ou limite de outro cliente são trocadas por uma resposta segura.

## Estratégia de testes

- Os testes executam código real. O modelo é substituído por um modelo falso com respostas roteirizadas e a API de câmbio por respostas HTTP simuladas.
- Entram só testes que pegariam um defeito plausível: limites de faixa, permissões, persistência, falhas de arquivo e de API, concorrência de estado e validação.
- Um teste de ponta a ponta percorre o caminho de pedido rejeitado, entrevista e reanálise automática.
