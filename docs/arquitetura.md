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
| `seed/` | Criação dos dados sintéticos quando os arquivos não existem |
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
| Dados sintéticos criados na partida, só para arquivos ausentes | Execução idempotente: nunca sobrescreve dados existentes, e `data/` fica fora do git |
| Guardrails atrás da interface `Guardrail` | Permite trocar por um serviço gerenciado sem mexer nos agentes |
| Modelo juiz só em caso de suspeita; falha do juiz bloqueia | Economiza chamadas e falha de forma segura |
| Fachada `ChatService.send` como único ponto de entrada | Captura qualquer exceção e devolve resposta amigável |
| Checkpointer em memória indexado pelo identificador da conversa | Mantém o estado entre turnos sem gravar a conversa em disco |
| CPF validado pelos dígitos verificadores | Descarta erros de digitação antes de consultar a base |

## Decisões em pontos que o enunciado não define

O enunciado deixa lacunas e ambiguidades. Cada decisão abaixo foi tomada de forma explícita, com o motivo.

### Autenticação

| Decisão | Motivo |
|---|---|
| Três falhas seguidas encerram o atendimento (a primeira tentativa mais as duas novas do enunciado) | Segue o texto do enunciado, sem tentativa extra |
| CPF e data são extraídos dos grupos de dígitos (11 e 8), ignorando espaços, pontos, traços e barras. A data aceita `DDMMAAAA` e `AAAAMMDD`, só para quem tem 18 anos ou mais e ano a partir de 1900 (uma data válida de menor de idade recebe a mensagem "parece ser um erro" e conta como tentativa); `MMDDAAAA` não é aceito | Tolera digitação irregular sem tentar adivinhar formatos ambíguos |
| Falha de CPF e falha de data geram a mesma mensagem | Evita revelar qual dado está certo |
| CPF com dígitos verificadores inválidos ou com formato ilegível conta como tentativa | Evita que erros de digitação ou testes de força bruta escapem do limite |
| A autenticação não usa o modelo | Um texto do cliente ("já estou autenticado") não pode substituir a verificação |

### Crédito

| Decisão | Motivo |
|---|---|
| Faixas de score definidas em `score_limite.csv`: 0–300 até R$ 1.000, 301–500 até R$ 5.000, 501–700 até R$ 15.000, 701–1000 até R$ 40.000 | O enunciado cita a tabela, mas não os valores. As faixas são fictícias e editáveis no arquivo |
| O teto de cada faixa é inclusivo: pedir exatamente o teto é aprovado, e um centavo acima é rejeitado | Evita ambiguidade na fronteira |
| Status gravados como `aprovado` e `rejeitado` | O enunciado usa "rejeitado" na coluna e "reprovado" no texto. Adotei um só termo para facilitar filtros |
| Pedido aprovado atualiza o limite em `clientes.csv` | Sem isso, a consulta seguinte mostraria o limite antigo e o atendimento ficaria incoerente |
| Valor igual ou menor que o limite atual é recusado, sem registro e sem alterar o limite | Um pedido de aumento nunca deve reduzir o limite. Reduzir é outra operação, que exigiria confirmação do cliente |
| Pedido rejeitado informa o teto do score atual | Dá ao cliente um valor possível para tentar de novo |
| Após a rejeição, o atendimento oferece a entrevista e, se aceita, reanalisa o mesmo valor por código | O cliente não precisa repetir o pedido, e o resultado não depende de o modelo lembrar |

### Entrevista

| Decisão | Motivo |
|---|---|
| O modelo conduz a conversa, e o código controla ordem, validação e cálculo | Conversa natural (adequada a canais como o WhatsApp) sem abrir mão de regras exatas |
| Uma pergunta por vez, na ordem do enunciado | Evita respostas misturadas e respostas fora de ordem |
| Respostas naturais ("CLT", "uns 8 mil", "dois filhos") são aceitas e convertidas | O cliente não deve precisar reescrever o que já foi entendido |
| Resposta ambígua ou contraditória é recusada (por exemplo, "CLT e também MEI") | É melhor perguntar de novo do que calcular um score com dado duvidoso |
| Após duas falhas na mesma pergunta, o atendimento oferece pausar ou parar | Evita um laço de perguntas repetidas |
| A fórmula do enunciado é aplicada como está: 3 ou mais dependentes pesam 30, arredondamento comercial, resultado limitado a 0–1000 | Mantém a fórmula pedida e garante a faixa de 0 a 1000 |
| Desistir no meio não altera o score | O score só é gravado com as cinco respostas válidas |

### Câmbio

| Decisão | Motivo |
|---|---|
| AwesomeAPI, que não exige chave | Qualquer pessoa executa o projeto sem criar conta em outro serviço |
| Usa o valor de compra (`bid`) em reais | Um único valor, claro para o cliente |
| Sem moeda informada, consulta o dólar | O enunciado cita o dólar como padrão |
| Toda resposta traz valor, moeda e horário da consulta | Deixa claro que a cotação é de um instante |
| Moeda desconhecida ou API fora do ar nunca produz um valor inventado | Um número errado é pior que nenhuma resposta |

### Segurança e conduta

| Decisão | Motivo |
|---|---|
| O CPF autenticado fica no estado do grafo, e nenhuma ferramenta o recebe como argumento | O modelo não consegue consultar outro cliente |
| Guardrails de entrada e de saída atrás de uma interface substituível | Permite trocar por um serviço gerenciado sem mexer nos agentes |
| Regras locais decidem os casos claros, e o modelo juiz só é chamado em caso de suspeita | Economiza chamadas e custo |
| Se o juiz falhar, a mensagem é bloqueada | Na dúvida, o sistema escolhe o lado seguro |
| O juiz usa o mesmo tempo limite do modelo do atendimento (60 s, até 3 tentativas) | Quem administra escolhe um modelo rápido em `JUDGE_CHAT_MODEL`, sem um limite fixo próprio |
| Sem `JUDGE_CHAT_MODEL`, o juiz usa o modelo do atendimento | Uma única chave basta para executar o projeto |
| Pedido para encerrar a conversa vale a qualquer momento: nos agentes, pela ferramenta `end_conversation`; na autenticação e na triagem, por classificação do modelo, com a mesma despedida | Triagem e autenticação não têm ferramentas. Na autenticação, o modelo só recebe mensagens sem nenhum número, nunca vê CPF nem data e só sugere: se falhar, o login continua. Encerrar durante o login não gasta tentativa |
| Três bloqueios seguidos encerram o atendimento | Limita tentativas repetidas de manipulação |
| Respostas com CPF, limite ou score de outro cliente são trocadas por uma resposta segura | Última barreira contra vazamento, mesmo que um agente erre |
| Respostas não mencionam agentes, ferramentas nem transferências | Cumpre a regra de que o cliente percebe um único atendente |

### Sessão e dados

| Decisão | Motivo |
|---|---|
| A conversa fica só na memória do processo | Nenhum dado pessoal da conversa é gravado em disco; reiniciar o serviço encerra as conversas e o cliente se autentica de novo |
| Conversa inativa por 5 minutos é encerrada (configurável, `0` desliga) | Evita deixar uma sessão autenticada aberta |
| Os dados de teste são criados na primeira execução e a pasta `data/` não é versionada | Execução simples e sem risco de sobrescrever dados existentes |
| Logs e traces mascaram o CPF e não registram o texto do cliente | Privacidade dos dados, inclusive em ferramentas de observabilidade |

## Segurança e privacidade

- O CPF aparece mascarado (`***.456.789-**`) em logs, eventos de bloqueio e traces.
- O texto livre digitado pelo cliente não é registrado em logs nem enviado a traces.
- Uma mensagem bloqueada é trocada por um marcador no histórico depois de gerar a resposta fixa. O texto original nunca chega aos agentes e a tela continua mostrando o balão do cliente.
- Respostas com CPF, score ou limite de outro cliente são trocadas por uma resposta segura.

## Estratégia de testes

- Os testes executam código real. O modelo é substituído por um modelo falso com respostas roteirizadas e a API de câmbio por respostas HTTP simuladas.
- Entram só testes que pegariam um defeito plausível: limites de faixa, permissões, persistência, falhas de arquivo e de API, concorrência de estado e validação.
- Um teste de ponta a ponta percorre o caminho de pedido rejeitado, entrevista e reanálise automática.
