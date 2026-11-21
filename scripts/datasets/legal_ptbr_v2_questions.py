# ruff: noqa: E501 -- the strings are Portuguese questions and answers; wrapping them hides the text
"""Questions of the ``legal-ptbr-v2`` dataset that are new in v2 (ROADMAP task 3.x, limitation L10).

Each entry is ``(group, style, question, expected answer, evidence)``. The evidence is a list of
``(law, article, phrase)``. The relevant documents of a question are the documents that hold its
evidence articles, so a question with two evidence articles in two documents needs both. The
builder fails if a phrase is not in the text of its article.

Groups:

- ``lgpd``, ``cdc``, ``mci``, ``lai``: one law answers the question.
- ``multi``: the answer needs two articles that live in different documents (or in two laws).
- ``cross``: a definition or a list that other laws of the dataset also have in similar words, so
  the question names its law.

Styles: ``formal`` uses the words of the law. ``colloquial`` is how a person asks, in the first
person and without the key terms of the law.

The 20 questions of ``legal-ptbr`` (v1) are not here. The builder takes them from
``build_legal_ptbr.QUESTIONS`` and keeps them first, in the same order.
"""

from __future__ import annotations

Evidence = list[tuple[str, int, str]]
Question = tuple[str, str, str, str, Evidence]

QUESTIONS: list[Question] = [
    # ------------------------------------------------------------------ LGPD
    (
        "lgpd",
        "formal",
        "A LGPD vale para uma empresa estrangeira que trata dados de pessoas que estão no Brasil?",
        "Sim. A lei se aplica quando a atividade de tratamento tem por objetivo a oferta de bens ou "
        "serviços, ou o tratamento de dados de indivíduos localizados no território nacional, "
        "independentemente do país da sede.",
        [("lgpd", 3, "localizados no território nacional")],
    ),
    (
        "lgpd",
        "colloquial",
        "Se eu der meu consentimento para uma empresa usar meus dados, posso desistir depois?",
        "Sim. O consentimento pode ser revogado a qualquer momento, por manifestação expressa do "
        "titular, em procedimento gratuito e facilitado.",
        [("lgpd", 8, "pode ser revogado a qualquer momento")],
    ),
    (
        "lgpd",
        "formal",
        "Uma autorização genérica para o tratamento de dados pessoais é válida?",
        "Não. O consentimento deve se referir a finalidades determinadas, e as autorizações "
        "genéricas para o tratamento de dados pessoais são nulas.",
        [("lgpd", 8, "autorizações genéricas para o tratamento de dados pessoais serão nulas")],
    ),
    (
        "lgpd",
        "formal",
        "Em que situações dados pessoais sensíveis podem ser tratados sem o consentimento do "
        "titular?",
        "Quando o tratamento for indispensável para cumprir obrigação legal ou regulatória, executar "
        "políticas públicas, realizar estudos por órgão de pesquisa, exercer direitos, proteger a "
        "vida, tutelar a saúde ou prevenir fraude nos processos de identificação e autenticação.",
        [("lgpd", 11, "sem fornecimento de consentimento do titular")],
    ),
    (
        "lgpd",
        "colloquial",
        "Dados anonimizados ainda contam como dados pessoais?",
        "Em regra não. Só contam se o processo de anonimização for revertido com meios próprios ou "
        "puder ser revertido com esforços razoáveis.",
        [("lgpd", 12, "Os dados anonimizados não serão considerados dados pessoais")],
    ),
    (
        "lgpd",
        "formal",
        "O que acontece com os dados pessoais depois que o tratamento termina?",
        "Eles são eliminados, e a conservação só é autorizada para cumprir obrigação legal, para "
        "estudo por órgão de pesquisa, para transferência a terceiro ou para uso exclusivo do "
        "controlador com os dados anonimizados.",
        [("lgpd", 16, "serão eliminados após o término de seu tratamento")],
    ),
    (
        "lgpd",
        "colloquial",
        "Posso levar meus dados de um serviço para outro concorrente?",
        "Sim. O titular tem direito à portabilidade dos dados a outro fornecedor de serviço ou "
        "produto, mediante requisição expressa.",
        [("lgpd", 18, "portabilidade dos dados a outro fornecedor de serviço ou produto")],
    ),
    (
        "lgpd",
        "formal",
        "Quais são os direitos do titular dos dados pessoais perante o controlador?",
        "Confirmação da existência de tratamento, acesso, correção, anonimização, bloqueio ou "
        "eliminação de dados, portabilidade, eliminação dos dados tratados com consentimento, "
        "informação sobre o compartilhamento, informação sobre a possibilidade de não consentir e "
        "revogação do consentimento.",
        [("lgpd", 18, "confirmação da existência de tratamento")],
    ),
    (
        "lgpd",
        "colloquial",
        "Preciso pagar para pedir à empresa acesso aos meus dados pessoais?",
        "Não. O requerimento do titular é atendido sem custos, nos prazos e nos termos previstos "
        "em regulamento.",
        [("lgpd", 18, "sem custos para o titular")],
    ),
    (
        "lgpd",
        "formal",
        "Em que casos a transferência internacional de dados pessoais é permitida?",
        "Para países ou organismos com grau de proteção adequado, quando o controlador oferece "
        "garantias (cláusulas contratuais, cláusulas-padrão, normas corporativas globais, selos), "
        "para cooperação jurídica internacional, para proteger a vida, com autorização da "
        "autoridade nacional, com consentimento específico e em destaque do titular, entre outros "
        "casos.",
        [("lgpd", 33, "transferência internacional de dados pessoais somente é permitida")],
    ),
    (
        "lgpd",
        "colloquial",
        "Se uma empresa vazar meus dados e eu tiver prejuízo, quem tem que me indenizar?",
        "O controlador ou o operador que causou o dano em violação à legislação de proteção de "
        "dados é obrigado a repará-lo. Em certos casos eles respondem solidariamente.",
        [("lgpd", 42, "é obrigado a repará-lo")],
    ),
    (
        "lgpd",
        "formal",
        "O juiz pode inverter o ônus da prova a favor do titular dos dados em uma ação de "
        "reparação?",
        "Sim, quando a alegação for verossímil, houver hipossuficiência para produzir a prova ou a "
        "produção da prova for excessivamente onerosa para o titular.",
        [("lgpd", 42, "inverter o ônus da prova a favor do titular dos dados")],
    ),
    (
        "lgpd",
        "formal",
        "Que medidas de segurança os agentes de tratamento devem adotar?",
        "Medidas de segurança, técnicas e administrativas, aptas a proteger os dados pessoais de "
        "acessos não autorizados e de situações acidentais ou ilícitas, observadas desde a "
        "concepção do produto ou do serviço até a sua execução.",
        [("lgpd", 46, "medidas de segurança, técnicas e administrativas")],
    ),
    (
        "lgpd",
        "colloquial",
        "Além da multa, que outras punições uma empresa pode receber por descumprir a lei de "
        "proteção de dados?",
        "Advertência, multa diária, publicização da infração, bloqueio ou eliminação dos dados, "
        "suspensão do banco de dados ou da atividade de tratamento por até 6 meses, e proibição "
        "parcial ou total das atividades de tratamento.",
        [("lgpd", 52, "publicização da infração")],
    ),
    (
        "lgpd",
        "colloquial",
        "Preciso do consentimento de alguém para usar dados que essa própria pessoa tornou "
        "públicos?",
        "Não. A lei dispensa o consentimento para os dados tornados manifestamente públicos pelo "
        "titular, resguardados os direitos do titular e os princípios da lei.",
        [("lgpd", 7, "manifestamente públicos pelo titular")],
    ),
    # ------------------------------------------------------------------ CDC
    (
        "cdc",
        "formal",
        "O fabricante responde pelos danos causados por um defeito do produto mesmo sem culpa?",
        "Sim. O fabricante, o produtor, o construtor e o importador respondem independentemente da "
        "existência de culpa pela reparação dos danos causados por defeitos do produto.",
        [("cdc", 12, "independentemente da existência de culpa")],
    ),
    (
        "cdc",
        "formal",
        "Em que situações o fabricante não é responsabilizado pelo defeito do produto?",
        "Quando prova que não colocou o produto no mercado, que o defeito não existe ou que houve "
        "culpa exclusiva do consumidor ou de terceiro.",
        [("cdc", 12, "culpa exclusiva do consumidor ou de terceiro")],
    ),
    (
        "cdc",
        "colloquial",
        "Se a empresa descobrir depois da venda que um produto é perigoso, o que ela tem que "
        "fazer?",
        "Comunicar o fato imediatamente às autoridades competentes e aos consumidores, mediante "
        "anúncios publicitários.",
        [("cdc", 10, "mediante anúncios publicitários")],
    ),
    (
        "cdc",
        "formal",
        "O que o consumidor pode exigir quando um serviço é prestado com vício de qualidade?",
        "Alternativamente e à sua escolha: a reexecução do serviço sem custo adicional, a "
        "restituição imediata da quantia paga com atualização monetária ou o abatimento "
        "proporcional do preço.",
        [("cdc", 20, "a reexecução dos serviços")],
    ),
    (
        "cdc",
        "colloquial",
        "A oficina pode usar peça usada ou paralela no conserto do meu aparelho?",
        "A oficina deve empregar componentes de reposição originais adequados e novos, ou que "
        "mantenham as especificações técnicas do fabricante, salvo autorização em contrário do "
        "consumidor.",
        [
            ("cdc", 21, "componentes de reposição originais"),
            # Art. 70 makes it a crime to use used parts without the consent of the consumer.
            ("cdc", 70, "peça ou componentes de reposição usados"),
        ],
    ),
    (
        "cdc",
        "formal",
        "A garantia legal de adequação do produto depende de um termo escrito?",
        "Não. A garantia legal independe de termo expresso, e a lei veda a exoneração contratual "
        "do fornecedor.",
        [("cdc", 24, "independe de termo expresso")],
    ),
    (
        "cdc",
        "formal",
        "Que informações a oferta e a apresentação de um produto devem trazer?",
        "Informações corretas, claras, precisas, ostensivas e em língua portuguesa sobre "
        "características, qualidades, quantidade, composição, preço, garantia, prazos de validade, "
        "origem e riscos.",
        [("cdc", 31, "em língua portuguesa")],
    ),
    (
        "cdc",
        "colloquial",
        "Até quando o fabricante precisa vender peças de reposição do produto que fez?",
        "Enquanto não cessar a fabricação ou a importação do produto. Depois disso, a oferta deve "
        "ser mantida por período razoável de tempo, na forma da lei.",
        [("cdc", 32, "componentes e peças de reposição")],
    ),
    (
        "cdc",
        "formal",
        "O que é publicidade enganosa?",
        "Qualquer informação ou comunicação publicitária, inteira ou parcialmente falsa, ou capaz "
        "de induzir o consumidor em erro, inclusive por omissão de dado essencial.",
        [("cdc", 37, "capaz de induzir em erro o consumidor")],
    ),
    (
        "cdc",
        "colloquial",
        "Numa propaganda, quem precisa provar que o que ela diz é verdade?",
        "Quem patrocina a publicidade. O ônus da prova da veracidade e da correção da informação "
        "cabe a ele.",
        [("cdc", 38, "cabe a quem as patrocina")],
    ),
    (
        "cdc",
        "colloquial",
        "Recebi em casa um produto que eu não pedi. Preciso pagar por ele?",
        "Não. O produto enviado sem solicitação prévia equipara-se a amostra grátis, e não existe "
        "obrigação de pagamento.",
        [("cdc", 39, "equiparam-se às amostras grátis")],
    ),
    (
        "cdc",
        "formal",
        "Como as cláusulas de um contrato de consumo são interpretadas?",
        "De maneira mais favorável ao consumidor.",
        [("cdc", 47, "mais favorável ao consumidor")],
    ),
    (
        "cdc",
        "formal",
        "Que cláusulas contratuais são nulas de pleno direito nas relações de consumo?",
        "Entre outras, as que exoneram ou atenuam a responsabilidade do fornecedor por vícios, "
        "transferem responsabilidades a terceiros, invertem o ônus da prova em prejuízo do "
        "consumidor, impõem arbitragem compulsória ou permitem a variação unilateral do preço.",
        [("cdc", 51, "nulas de pleno direito")],
    ),
    (
        "cdc",
        "colloquial",
        "O que a loja precisa me informar antes de eu fechar um financiamento?",
        "O preço em moeda corrente nacional, o montante dos juros de mora e a taxa efetiva anual de "
        "juros, os acréscimos legais, o número e a periodicidade das prestações e a soma total a "
        "pagar, com e sem financiamento.",
        [("cdc", 52, "taxa efetiva anual de juros")],
    ),
    (
        "cdc",
        "formal",
        "Como devem ser redigidos os contratos de adesão escritos?",
        "Em termos claros e com caracteres ostensivos e legíveis, de modo a facilitar a "
        "compreensão pelo consumidor.",
        [("cdc", 54, "caracteres ostensivos e legíveis")],
    ),
    # ------------------------------------------------------------------ Marco Civil
    (
        "mci",
        "formal",
        "Em que caso o sigilo das comunicações privadas pela internet pode ser quebrado?",
        "Somente por ordem judicial, na forma da lei.",
        [("mci", 7, "salvo por ordem judicial")],
    ),
    (
        "mci",
        "colloquial",
        "Por quanto tempo a empresa que me dá acesso à internet precisa guardar meus registros de "
        "conexão?",
        "Pelo prazo de 1 ano, sob sigilo, em ambiente controlado e de segurança, nos termos do "
        "regulamento.",
        [("mci", 13, "pelo prazo de 1 (um) ano")],
    ),
    (
        "mci",
        "formal",
        "Por quanto tempo o provedor de aplicações de internet deve guardar os registros de acesso "
        "a aplicações?",
        "Pelo prazo de 6 meses, sob sigilo, em ambiente controlado e de segurança, nos termos do "
        "regulamento.",
        [("mci", 15, "pelo prazo de 6 (seis) meses")],
    ),
    (
        "mci",
        "formal",
        "Qual é a multa máxima por violar as regras de privacidade e de guarda de dados do Marco "
        "Civil da Internet?",
        "Até 10% do faturamento do grupo econômico no Brasil no último exercício, excluídos os "
        "tributos.",
        [("mci", 12, "10% (dez por cento) do faturamento")],
    ),
    (
        "mci",
        "formal",
        "Quando um provedor de aplicações pode ser responsabilizado por conteúdo gerado por "
        "terceiros?",
        "Somente se, após ordem judicial específica, não tomar as providências para tornar "
        "indisponível o conteúdo apontado como infringente, no prazo assinalado.",
        [("mci", 19, "após ordem judicial específica")],
    ),
    (
        "mci",
        "colloquial",
        "Alguém publicou um vídeo íntimo meu sem eu deixar. A plataforma precisa tirar do ar?",
        "Sim. O provedor responde subsidiariamente se, depois de notificado pelo participante ou "
        "por seu representante legal, deixar de indisponibilizar o conteúdo de forma diligente.",
        [("mci", 21, "cenas de nudez")],
    ),
    (
        "mci",
        "formal",
        "O que é a neutralidade de rede?",
        "O dever do responsável pela transmissão, comutação ou roteamento de tratar de forma "
        "isonômica quaisquer pacotes de dados, sem distinção por conteúdo, origem e destino, "
        "serviço, terminal ou aplicação.",
        [("mci", 9, "tratar de forma isonômica quaisquer pacotes de dados")],
    ),
    (
        "mci",
        "colloquial",
        "A operadora que me vende a internet pode guardar quais sites e aplicativos eu acesso?",
        "Não. Na provisão de conexão é vedado guardar os registros de acesso a aplicações de "
        "internet.",
        [("mci", 14, "é vedado guardar os registros de acesso a aplicações de internet")],
    ),
    (
        "mci",
        "formal",
        "O provedor de conexão à internet responde por danos causados por conteúdo de terceiros?",
        "Não. O provedor de conexão não será responsabilizado civilmente por danos decorrentes de "
        "conteúdo gerado por terceiros.",
        [("mci", 18, "não será responsabilizado civilmente")],
    ),
    (
        "mci",
        "colloquial",
        "Quando eu parar de usar um aplicativo, posso pedir que apaguem meus dados de lá?",
        "Sim. O usuário tem direito à exclusão definitiva dos dados pessoais que forneceu a "
        "determinada aplicação, a seu requerimento, ao término da relação, ressalvada a guarda "
        "obrigatória de registros.",
        [
            ("mci", 7, "exclusão definitiva dos dados pessoais"),
            # Art. 60 of the LGPD rewrites art. 7, X of the Marco Civil with the same sentence.
            ("lgpd", 60, "exclusão definitiva dos dados pessoais"),
        ],
    ),
    (
        "mci",
        "formal",
        "A lei brasileira se aplica a uma empresa sediada no exterior que coleta dados no Brasil?",
        "Sim, desde que ofereça serviço ao público brasileiro ou que uma integrante do mesmo grupo "
        "econômico tenha estabelecimento no Brasil.",
        [
            (
                "mci",
                11,
                "mesmo que as atividades sejam realizadas por pessoa jurídica sediada no exterior",
            )
        ],
    ),
    (
        "mci",
        "colloquial",
        "Posso instalar um programa para controlar o que meus filhos veem na internet?",
        "Sim. O usuário tem a opção de livre escolha de programa de computador para exercer o "
        "controle parental de conteúdo impróprio a seus filhos menores.",
        [("mci", 29, "controle parental")],
    ),
    (
        "mci",
        "formal",
        "Quando o Marco Civil da Internet entra em vigor?",
        "Após decorridos 60 dias de sua publicação oficial.",
        [("mci", 32, "60 (sessenta) dias")],
    ),
    (
        "mci",
        "formal",
        "Que requisitos o pedido de fornecimento de registros ao juiz deve cumprir?",
        "Fundados indícios da ocorrência do ilícito, justificativa motivada da utilidade dos "
        "registros para investigação ou instrução probatória e o período a que se referem os "
        "registros.",
        [("mci", 22, "fundados indícios da ocorrência do ilícito")],
    ),
    (
        "mci",
        "formal",
        "O que é registro de conexão?",
        "O conjunto de informações sobre a data e a hora de início e término de uma conexão à "
        "internet, sua duração e o endereço IP usado pelo terminal.",
        [("mci", 5, "data e hora de início e término de uma conexão")],
    ),
    (
        "mci",
        "colloquial",
        "A operadora pode cortar minha internet se eu atrasar a conta?",
        "Sim, mas só por débito diretamente decorrente da utilização do serviço. A conexão não "
        "pode ser suspensa por outro motivo.",
        [("mci", 7, "não suspensão da conexão à internet, salvo por débito")],
    ),
    (
        "mci",
        "formal",
        "Em quanto tempo a autoridade que pediu a guarda de registros por prazo maior deve pedir a "
        "autorização judicial de acesso?",
        "No prazo de 60 dias, contados a partir do requerimento.",
        [("mci", 13, "60 (sessenta) dias")],
    ),
    (
        "mci",
        "colloquial",
        "Quando a plataforma derruba um conteúdo meu, ela precisa me explicar o motivo?",
        "Sim. Se tiver os dados de contato do usuário responsável, o provedor deve comunicar-lhe os "
        "motivos e informações da indisponibilização, que permitam o contraditório e a ampla defesa.",
        [("mci", 20, "comunicar-lhe os motivos")],
    ),
    (
        "mci",
        "formal",
        "As autoridades administrativas podem acessar dados cadastrais sem ordem judicial?",
        "Sim, quanto aos dados cadastrais que informem qualificação pessoal, filiação e endereço, "
        "na forma da lei, pelas autoridades com competência legal para a sua requisição.",
        [("mci", 10, "dados cadastrais que informem qualificação pessoal, filiação e endereço")],
    ),
    # ------------------------------------------------------------------ Lei de Acesso à Informação
    (
        "lai",
        "formal",
        "Em quanto tempo o órgão público deve responder a um pedido de acesso à informação que não "
        "pode atender de imediato?",
        "Em prazo não superior a 20 dias.",
        [("lai", 11, "em prazo não superior a 20 (vinte) dias")],
    ),
    (
        "lai",
        "colloquial",
        "O órgão pode pedir mais tempo para responder meu pedido de informação?",
        "Sim. O prazo pode ser prorrogado por mais 10 dias, mediante justificativa expressa, da "
        "qual o requerente é cientificado.",
        [("lai", 11, "prorrogado por mais 10 (dez) dias")],
    ),
    (
        "lai",
        "formal",
        "Qual é o prazo para recorrer quando o acesso à informação é negado?",
        "10 dias, a contar da ciência da decisão.",
        [("lai", 15, "no prazo de 10 (dez) dias a contar da sua ciência")],
    ),
    (
        "lai",
        "formal",
        "Por quantos anos uma informação ultrassecreta pode ficar com acesso restrito?",
        "Pelo prazo máximo de 25 anos, contados da data de sua produção.",
        [("lai", 24, "ultrassecreta: 25 (vinte e cinco) anos")],
    ),
    (
        "lai",
        "colloquial",
        "Preciso explicar por que quero uma informação pública quando faço o pedido?",
        "Não. São vedadas quaisquer exigências relativas aos motivos determinantes da solicitação "
        "de informações de interesse público.",
        [("lai", 10, "São vedadas quaisquer exigências relativas aos motivos determinantes")],
    ),
    (
        "lai",
        "colloquial",
        "Tenho que pagar para o governo me entregar uma informação?",
        "A busca e o fornecimento da informação são gratuitos. Só pode ser cobrado o custo da "
        "reprodução de documentos, e quem não pode pagar sem prejudicar o próprio sustento fica "
        "isento.",
        [("lai", 12, "O serviço de busca e fornecimento da informação é gratuito")],
    ),
    (
        "lai",
        "formal",
        "A quem recorrer quando o Poder Executivo Federal nega o acesso a uma informação?",
        "À Controladoria-Geral da União, depois de o recurso passar por pelo menos uma autoridade "
        "hierarquicamente superior. Da negativa da CGU, cabe recurso à Comissão Mista de "
        "Reavaliação de Informações.",
        [("lai", 16, "recorrer à Controladoria")],
    ),
    (
        "lai",
        "formal",
        "Por quanto tempo as informações pessoais ligadas à intimidade e à vida privada têm acesso "
        "restrito?",
        "Pelo prazo máximo de 100 anos a contar da data de produção, independentemente de "
        "classificação de sigilo.",
        [("lai", 31, "100 (cem) anos")],
    ),
    (
        "lai",
        "colloquial",
        "O que acontece com o servidor público que se recusa a me dar uma informação que tenho "
        "direito de receber?",
        "A recusa de fornecer informação requerida, o atraso deliberado ou o fornecimento incorreto "
        "são condutas ilícitas que geram responsabilidade do agente público.",
        [
            ("lai", 32, "recusar-se a fornecer informação requerida"),
            # Art. 7, par. 4: an unfounded refusal makes the person in charge liable to discipline.
            ("lai", 7, "sujeitará o responsável a medidas disciplinares"),
        ],
    ),
    (
        "lai",
        "formal",
        "Que informações os órgãos públicos devem divulgar, no mínimo, independentemente de "
        "requerimento?",
        "Competências e estrutura organizacional, endereços e telefones, repasses de recursos, "
        "despesas, licitações e contratos, dados para acompanhar programas e obras e respostas a "
        "perguntas frequentes.",
        [("lai", 8, "registros das despesas")],
    ),
    (
        "lai",
        "colloquial",
        "Prefeitura de cidade pequena também precisa divulgar tudo na internet?",
        "Os Municípios com até 10.000 habitantes ficam dispensados da divulgação obrigatória na "
        "internet, mas mantêm a divulgação em tempo real da execução orçamentária e financeira.",
        [("lai", 8, "10.000 (dez mil) habitantes")],
    ),
    (
        "lai",
        "formal",
        "Que informações podem ser classificadas como sigilosas por serem imprescindíveis à "
        "segurança da sociedade ou do Estado?",
        "As que, se divulgadas, puderem pôr em risco a defesa e a soberania nacionais, as relações "
        "internacionais, a vida, a segurança ou a saúde da população, a estabilidade financeira do "
        "País, entre outros casos.",
        [("lai", 23, "pôr em risco a defesa e a soberania nacionais")],
    ),
    (
        "lai",
        "formal",
        "Quem pode classificar uma informação no grau ultrassecreto na administração pública "
        "federal?",
        "O Presidente da República, o Vice-Presidente, os Ministros de Estado, os Comandantes das "
        "Forças Armadas e os Chefes de Missões Diplomáticas e Consulares permanentes no exterior.",
        [("lai", 27, "Presidente da República")],
    ),
    (
        "lai",
        "colloquial",
        "O governo pode esconder documentos sobre violação de direitos humanos?",
        "Não. As informações ou documentos sobre violação dos direitos humanos praticada por "
        "agentes públicos ou a mando de autoridades não podem ser objeto de restrição de acesso.",
        [("lai", 21, "violação dos direitos humanos praticada por agentes públicos")],
    ),
    (
        "lai",
        "colloquial",
        "Onde posso ir pedir informações pessoalmente em um órgão público?",
        "No serviço de informações ao cidadão, que cada órgão ou entidade deve criar em local com "
        "condições apropriadas para atender, orientar o público e protocolizar requerimentos.",
        [("lai", 9, "serviço de informações ao cidadão")],
    ),
    (
        "lai",
        "formal",
        "O que acontece quando só parte de um documento é sigilosa?",
        "É assegurado o acesso à parte não sigilosa, por meio de certidão, extrato ou cópia com "
        "ocultação da parte sob sigilo.",
        [("lai", 7, "certidão, extrato ou cópia com ocultação da parte sob sigilo")],
    ),
    (
        "lai",
        "formal",
        "A Lei de Acesso à Informação vale para entidades privadas?",
        "Aplica-se, no que couber, às entidades privadas sem fins lucrativos que recebam recursos "
        "públicos para ações de interesse público. A publicidade se refere à parcela dos recursos "
        "públicos recebidos e à sua destinação.",
        [("lai", 2, "entidades privadas sem fins lucrativos")],
    ),
    (
        "lai",
        "colloquial",
        "Que punição uma empresa que trabalha para o governo recebe se esconder informações?",
        "Advertência, multa, rescisão do vínculo, suspensão temporária de licitar e impedimento de "
        "contratar por até 2 anos, e declaração de inidoneidade para licitar ou contratar com a "
        "administração pública.",
        [("lai", 33, "declaração de inidoneidade para licitar")],
    ),
    (
        "lai",
        "formal",
        "Qual é o mandato dos integrantes da Comissão Mista de Reavaliação de Informações?",
        "Mandato de 2 anos.",
        [("lai", 35, "mandato de 2 (dois) anos")],
    ),
    (
        "lai",
        "colloquial",
        "Se o órgão negar meu pedido, posso receber a decisão por escrito?",
        "Sim. É direito do requerente obter o inteiro teor da decisão de negativa de acesso, por "
        "certidão ou cópia.",
        [("lai", 14, "inteiro teor de decisão de negativa de acesso")],
    ),
    # ------------------------------------------------------------------ multi: two documents
    (
        "multi",
        "formal",
        "Qual é a diferença entre o prazo de guarda dos registros de conexão e o dos registros de "
        "acesso a aplicações de internet?",
        "Os registros de conexão ficam guardados por 1 ano, pelo administrador de sistema "
        "autônomo. Os registros de acesso a aplicações ficam guardados por 6 meses, pelo provedor "
        "de aplicações.",
        [
            ("mci", 13, "pelo prazo de 1 (um) ano"),
            ("mci", 15, "pelo prazo de 6 (seis) meses"),
        ],
    ),
    (
        "multi",
        "colloquial",
        "Em quantos dias o órgão público tem que me responder e em quantos dias eu posso recorrer "
        "se ele negar?",
        "O órgão tem prazo não superior a 20 dias, prorrogável por mais 10. O interessado pode "
        "recorrer em 10 dias a contar da ciência da negativa.",
        [
            ("lai", 11, "em prazo não superior a 20 (vinte) dias"),
            ("lai", 15, "no prazo de 10 (dez) dias a contar da sua ciência"),
        ],
    ),
    (
        "multi",
        "formal",
        "Quem é o encarregado pelo tratamento de dados pessoais e quais são as atividades dele?",
        "É a pessoa indicada pelo controlador que atua como canal de comunicação entre o "
        "controlador, os titulares e a autoridade nacional. Ele aceita reclamações dos titulares, "
        "recebe comunicações da autoridade, orienta funcionários e contratados e executa as demais "
        "atribuições determinadas.",
        [
            ("lgpd", 5, "canal de comunicação"),
            ("lgpd", 41, "aceitar reclamações e comunicações dos titulares"),
        ],
    ),
    (
        "multi",
        "colloquial",
        "Quanto tempo tenho para reclamar de um defeito e quanto tempo a loja tem para consertar?",
        "O prazo para reclamar de vício aparente é de 90 dias para produtos duráveis e de 30 dias "
        "para não duráveis. O fornecedor tem o prazo máximo de 30 dias para sanar o vício.",
        [
            ("cdc", 26, "noventa dias"),
            ("cdc", 18, "trinta dias"),
        ],
    ),
    (
        "multi",
        "formal",
        "Qual é a multa máxima da LGPD e qual é a do Marco Civil da Internet?",
        "A LGPD prevê multa simples de até 2% do faturamento no Brasil, limitada a R$ 50 milhões "
        "por infração. O Marco Civil prevê multa de até 10% do faturamento do grupo econômico no "
        "Brasil.",
        [
            ("lgpd", 52, "50.000.000,00"),
            ("mci", 12, "10% (dez por cento) do faturamento"),
        ],
    ),
    (
        "multi",
        "colloquial",
        "Que direitos eu tenho sobre meus dados pessoais, pela lei de proteção de dados e pelo "
        "Marco Civil?",
        "Pela LGPD: confirmação do tratamento, acesso, correção, portabilidade, eliminação e "
        "revogação do consentimento, entre outros. Pelo Marco Civil: informações claras sobre a "
        "coleta, consentimento expresso e exclusão definitiva dos dados ao fim da relação.",
        [
            ("lgpd", 18, "portabilidade dos dados a outro fornecedor"),
            ("mci", 7, "exclusão definitiva dos dados pessoais"),
        ],
    ),
    (
        "multi",
        "formal",
        "Quem pode classificar uma informação como ultrassecreta e por quantos anos ela fica em "
        "sigilo?",
        "O Presidente da República, o Vice-Presidente, os Ministros de Estado e outras autoridades "
        "podem classificar. O sigilo vai até 25 anos.",
        [
            ("lai", 27, "Presidente da República"),
            ("lai", 24, "ultrassecreta: 25 (vinte e cinco) anos"),
        ],
    ),
    (
        "multi",
        "formal",
        "O que é registro de conexão e por quanto tempo ele deve ser guardado?",
        "É o conjunto de informações sobre data e hora de início e término da conexão, duração e "
        "endereço IP. Deve ser guardado por 1 ano pelo administrador de sistema autônomo.",
        [
            ("mci", 5, "data e hora de início e término de uma conexão"),
            ("mci", 13, "pelo prazo de 1 (um) ano"),
        ],
    ),
    (
        "multi",
        "formal",
        "Como a LGPD e a Lei de Acesso à Informação tratam o consentimento para dados pessoais?",
        "A LGPD define consentimento como a manifestação livre, informada e inequívoca do titular. "
        "A LAI permite divulgar informações pessoais a terceiros diante de previsão legal ou "
        "consentimento expresso da pessoa.",
        [
            ("lgpd", 5, "manifestação livre, informada e inequívoca"),
            # Art. 8 is how the LGPD says the consent must be given.
            ("lgpd", 8, "deverá ser fornecido por escrito"),
            ("lai", 31, "consentimento expresso da pessoa"),
        ],
    ),
    (
        "multi",
        "colloquial",
        "Que consequências sofrem o servidor que esconde informação e a empresa contratada que "
        "descumpre a lei de acesso?",
        "O agente público que se recusa a informar, retarda ou informa de forma incorreta comete "
        "conduta ilícita, apenada no mínimo com suspensão. A empresa que detém informações por "
        "vínculo com o poder público sofre advertência, multa, rescisão, impedimento de contratar "
        "ou declaração de inidoneidade.",
        [
            ("lai", 32, "recusar-se a fornecer informação requerida"),
            ("lai", 33, "declaração de inidoneidade para licitar"),
        ],
    ),
    # ------------------------------------------------------------------ cross: similar words in several laws
    (
        "cross",
        "formal",
        "Segundo a Lei de Acesso à Informação, o que é informação pessoal?",
        "A informação relacionada à pessoa natural identificada ou identificável.",
        [("lai", 4, "informação pessoal: aquela relacionada à pessoa natural identificada")],
    ),
    (
        "cross",
        "formal",
        "O que significa eliminação de dados segundo a LGPD?",
        "A exclusão de dado ou de conjunto de dados armazenados em banco de dados, independentemente "
        "do procedimento empregado.",
        [("lgpd", 5, "exclusão de dado ou de conjunto de dados")],
    ),
    (
        "cross",
        "formal",
        "Segundo o Marco Civil da Internet, o que é um endereço IP?",
        "O código atribuído a um terminal de uma rede para permitir sua identificação, definido "
        "segundo parâmetros internacionais.",
        [("mci", 5, "código atribuído a um terminal de uma rede")],
    ),
    (
        "cross",
        "formal",
        "Segundo o Código de Defesa do Consumidor, o que é considerado produto?",
        "Qualquer bem, móvel ou imóvel, material ou imaterial.",
        [("cdc", 3, "Produto é qualquer bem")],
    ),
    (
        "cross",
        "formal",
        "Quais são os princípios que regem o uso da internet no Brasil?",
        "Liberdade de expressão, proteção da privacidade, proteção dos dados pessoais, neutralidade "
        "de rede, estabilidade, segurança e funcionalidade da rede, responsabilização dos agentes, "
        "natureza participativa da rede e liberdade dos modelos de negócios.",
        [("mci", 3, "preservação e garantia da neutralidade de rede")],
    ),
    (
        "cross",
        "formal",
        "Quais são os princípios que as atividades de tratamento de dados pessoais devem observar?",
        "A boa-fé e os princípios da finalidade, adequação, necessidade, livre acesso, qualidade "
        "dos dados, transparência, segurança, prevenção, não discriminação e responsabilização.",
        [("lgpd", 6, "deverão observar a boa-fé e os seguintes princípios")],
    ),
    (
        "cross",
        "formal",
        "Quais diretrizes a Lei de Acesso à Informação estabelece para os procedimentos de acesso?",
        "Publicidade como preceito geral e sigilo como exceção, divulgação de informações de "
        "interesse público independentemente de solicitações, uso da tecnologia da informação, "
        "cultura de transparência e controle social da administração pública.",
        [("lai", 3, "observância da publicidade como preceito geral e do sigilo como exceção")],
    ),
    (
        "cross",
        "colloquial",
        "Na lei de proteção de dados, o que quer dizer consentimento?",
        "A manifestação livre, informada e inequívoca pela qual o titular concorda com o "
        "tratamento de seus dados pessoais para uma finalidade determinada.",
        [("lgpd", 5, "manifestação livre, informada e inequívoca")],
    ),
    (
        "cross",
        "formal",
        "Quando uma informação pessoal em poder do governo pode ser divulgada a terceiros segundo "
        "a Lei de Acesso à Informação?",
        "Diante de previsão legal ou de consentimento expresso da pessoa a que a informação se "
        "refere. O consentimento é dispensado em casos como tratamento médico, pesquisas de "
        "interesse público e cumprimento de ordem judicial.",
        [("lai", 31, "previsão legal ou consentimento expresso da pessoa")],
    ),
    (
        "cross",
        "colloquial",
        "Em que situação o provedor de internet é obrigado a entregar registros que identificam "
        "um usuário?",
        "Somente mediante ordem judicial, nos termos da Seção IV do capítulo do Marco Civil, "
        "respeitado o direito do usuário à inviolabilidade de sua intimidade e vida privada.",
        [("mci", 10, "mediante ordem judicial")],
    ),
]
