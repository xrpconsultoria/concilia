# Concilia · preparação contábil para Makro

Aplicativo de desenvolvimento para transformar extratos bancários em lançamentos no modelo de importação do Makro System. Mantém clientes, contas bancárias, regras de classificação e revisão manual em SQLite.

## Testar no Windows

1. Baixe o projeto pelo GitHub em **Code → Download ZIP** e extraia toda a pasta.
2. Instale **Python 3.12 de 64 bits** pela [página oficial do Python 3.12.10](https://www.python.org/downloads/release/python-31210/): em **Files**, escolha **Windows installer (64-bit)**. Se o instalador mostrar **Add python.exe to PATH**, marque essa opção.
3. Abra `Iniciar-Windows.bat` dentro da pasta extraída. A janela deve começar com **Concilia v0.5.3 - iniciar** e mostrar a pasta aberta. Na primeira vez, aguarde a instalação das dependências.
4. Quando aparecer **Running on**, copie o endereço mostrado pelo terminal para o navegador. Mantenha a janela aberta durante o uso. Ctrl+C encerra o servidor.

Esta versão usa o pacote de OCR `rapidocr-onnxruntime==1.4.4`, que exige Python anterior ao 3.13. As outras dependências fixadas exigem pelo menos 3.12. Por isso, o aplicativo usa **exatamente Python 3.12 de 64 bits**, com qualquer atualização dessa série. Python 3.13/3.14 pode continuar instalado para outros programas.

O inicializador pode ser aberto por outro Python (3.8 ou mais novo), mas `iniciar.py` localiza e seleciona o 3.12 antes de instalar as dependências. No Windows, ele consulta o launcher, o registro e os diretórios comuns de instalação. Não é obrigatório que o 3.12 seja o Python padrão no PATH. Um ambiente `.venv` já compatível é reutilizado.

Se o `.venv` foi criado com Python incompatível, o inicializador primeiro encontra o 3.12 e depois preserva o ambiente antigo em `.venv-backup-...`, criando um novo. A pasta `data/`, com cadastros, regras e conciliações, não é movida nem apagada. Se o Python correto estiver ausente, o programa mostra a versão necessária e o link de instalação sem tentar instalar os pacotes. Não use `--ignore-requires-python` nem versões antigas aleatórias do OCR para contornar a mensagem.

A seleção e a recuperação do ambiente foram executadas em Linux com Python 3.12 e 3.13, incluindo instalação limpa e carregamento local dos modelos de OCR. A resolução e o download de todos os pacotes para Windows/Python 3.12 de 64 bits foram verificados. A execução do arquivo `.bat` no Windows ainda precisa ser validada nesse sistema.

## Testar em macOS ou Linux

Instale **Python 3.12 de 64 bits** e execute, no terminal da pasta extraída:

```sh
bash iniciar-mac-linux.sh
```

Para instalação manual ou desenvolvimento, na raiz do projeto:

```sh
python3.12 iniciar.py --preparar
.venv/bin/python -m unittest discover -v
.venv/bin/python app.py
```

O aplicativo escuta somente em loopback, porta 5000; a variável `PORT` permite escolher outra porta. `/health` verifica o processo e o acesso ao SQLite. Não há compilação ou serviço de banco separado.

Esta versão usa o servidor de desenvolvimento do Flask e não inclui autenticação ou permissões por usuário. Precisa de preparação adicional antes de uma implantação para uso público.

## Fluxo guiado · v0.5.3

A rotina da equipe fica em **Nova conciliação**:

1. **Cliente e conta:** selecione o cliente; serão mostradas somente as contas dele. Confira o número e o código do Makro e clique em **Continuar: enviar extrato**.
2. **Extrato bancário:** escolha o arquivo do banco. Informe um período ou a senha do PDF se necessário. Clique em **Ler extrato e revisar**. Se houver erro, o arquivo e os campos permanecem na tela para correção.
3. **Revisão e Excel:** confira os movimentos, ajuste os códigos de contrapartida e a seleção das linhas. Os totais e a quantidade de pendências são atualizados na tela. Use **Baixar Excel para Makro**, disponível no topo e no final da revisão. Após a geração, procure o arquivo na pasta Downloads e faça a importação no Makro.

Em **Suas conciliações**, cada arquivo fica como **Aguardando revisão** ou **Excel já gerado**. Se uma revisão alterar os dados após gerar o Excel, a situação volta a aguardar revisão. Reenviar exatamente o mesmo arquivo e período abre a conciliação existente, sem criar outra.

### Cadastro e configuração

A área **Clientes e configurações** reúne o plano contábil, as contas e as regras; não é necessário passar por ela em cada conciliação.

- No primeiro uso, **Cadastrar cliente e conta** leva ao cadastro inicial. Carregue o plano geral do Makro em PDF ou CSV para usar seus códigos reais; o plano que acompanha o projeto é apenas demonstrativo. O plano próprio fica em `data/plano_de_contas.csv`, ignorado pelo Git.
- Cadastre o nome do cliente, o banco, o número completo da conta com dígito e a conta bancária correspondente no plano do Makro. Ao salvar, você segue diretamente para enviar o extrato.
- **Editar conta** permite corrigir o número antes da primeira conciliação. Contas com movimentos mantêm sua identificação para preservar o histórico; se for outra conta, faça um novo cadastro.
- **Regras** é uma configuração opcional por cliente e conta. Envie uma planilha Makro já conciliada para aprender descrições iguais, ou cadastre regras por trecho. A planilha pronta ensina a classificação; os movimentos exportados vêm do extrato bancário.
- Sem regra, os padrões são 106 para entradas e saídas. Eles podem ser ajustados em **Editar conta**, caso outra classificação geral seja válida para o cliente.

Regras exatas têm prioridade sobre regras por trecho; conflitos entre códigos ficam na **106**. Alterações nas regras afetam próximas importações. Conciliações anteriores preservam a classificação até a revisão manual. Alterar um código manualmente na revisão não cria uma regra automática.

### Atualizar uma instalação existente

1. Encerre o aplicativo com Ctrl+C na janela do servidor.
2. Baixe e extraia a versão nova em uma pasta diferente.
3. Copie a pasta **data** da instalação anterior para a nova, preservando a original como backup. Ela contém cadastros, regras, conciliações e seu plano contábil.
4. Abra `Iniciar-Windows.bat` diretamente dentro da nova pasta. Um atalho antigo pode continuar abrindo a instalação anterior. Confira **Concilia v0.5.3 - iniciar** e o caminho da pasta na janela. A atualização do banco é automática e preserva os registros existentes.
5. Confira **v0.5.3** na interface. Se necessário, recarregue a página com Ctrl+F5.

Não copie a pasta `.venv` entre instalações: o inicializador cria o ambiente da nova pasta. O banco local tem uma migração adicional para registrar quando um Excel foi gerado; isso não indica importação efetiva no Makro.

## Formatos aceitos

| Formato | Suporte desta versão |
| --- | --- |
| PDF Sicoob Internet Banking | Modelo de impressão do portal com Data/Documento/Histórico/Valor, inclusive cabeçalhos unidos e descrições entre páginas. Confere numeração de páginas, saldo anterior, saldos diários e saldo final; ordena por data sem remover movimentos iguais. Depósitos bloqueados com * ficam de fora; liberações e estornos C/D são preservados. |
| PDF Sicoob SISBR | Histórico de movimentação, descrições em várias linhas e valores com C/D; conferência dos saldos diários. |
| PDF C6 | Modelo com data de lançamento e data contábil, dentro de um mesmo ano; conferência dos totais mensais informados. |
| PDF Sicredi | Modelo de conta corrente com Documento/Histórico/Débito/Crédito/Saldo; valores lidos pela posição das colunas. Saldos e totais são conferidos; resumos e lançamentos futuros ficam de fora. |
| PDF Cresol | Modelo com saldos diários, valores com sinal e documento abaixo da descrição. Preserva estornos, confere os saldos e ordena os movimentos por data. |
| PDF Banco do Brasil | Extrato de Conta Corrente com Dia/Lote/Documento/Histórico/Valor e sinais (+)/(-). Confere saldos, preserva a data de efetivação e recompõe o ano dividido entre páginas quando o dígito está impresso. |
| PDF Inter | Modelo com saldo do dia e saldo por transação. Preserva continuações entre páginas e confere os saldos; não usa o saldo atual do cabeçalho como saldo final do período. |
| PDF Cora | Modelo Transações com favorecido, CPF/CNPJ e valores com sinal. Confere totais e saldos diários; mantém a ordem decrescente do PDF e as descrições da coluna de favorecido/CPF/CNPJ. |
| PDF Caixa | Extrato por período com documento, histórico/complemento, favorecido, valor e saldo C/D, em ordem decrescente. Confere o saldo de cada linha e exporta em ordem cronológica. O modelo digitalizado também é lido por OCR local. |
| PDF Nubank | Modelo Movimentações com totais diários, saldos e rendimento líquido no resumo. Preserva os detalhes de cada transferência; confere totais e saldos considerando o rendimento. |
| PDF protegido | Senha usada em memória para abrir o arquivo. Não é salva nos campos do lote; se aparecer no nome do arquivo, esse trecho é ocultado no nome salvo. |
| OFX | STMTTRN XML/SGML, DTPOSTED, TRNAMT, MEMO/NAME e FITID. |
| CSV / XLSX | Cabeçalho na primeira linha: data, descrição e valor com sinal; mapeamento de nomes de colunas disponível. CSV UTF-8 ou Windows-1252, delimitado por vírgula, ponto e vírgula ou tabulação. XLSX usa a primeira aba e rejeita fórmulas. |

Valores positivos na tabela de extrato representam entradas e negativos representam saídas. Planilhas Makro já conciliadas usam valores absolutos e devem ser enviadas no aprendizado, não como extrato. Outros layouts PDF exigem leitores adicionais. Limites: 16 MB por envio, 200 páginas por PDF com texto, 20 páginas por execução de OCR e 20.000 linhas por tabela. O OCR está limitado ao modelo Caixa descrito acima; documentos sem leitura financeira confiável são recusados.

O PDF do plano de contas deve ser o relatório tabular do Makro com classificação, S/A, código, descrição, D/C e tipo de saldo. CSV do plano usa ponto e vírgula e o cabeçalho:

```text
conta;tipo;codigo;descricao;natureza;tipo_saldo;inativada
```

Tipo deve ser S ou A e inativada deve ser sim ou nao. A conta analítica ativa 106 precisa existir. A troca de plano só é aceita se todos os códigos já usados nos cadastros, regras e lotes continuarem ativos.

Descrições do PDF são preservadas, incluindo nomes truncados e caracteres incomuns; o aplicativo não completa nomes. Uma planilha conciliada que tenha corrigido a grafia pode não gerar uma regra exata para o texto original do extrato. Nesses casos, revise a conta 106 ou cadastre uma regra por trecho. O Sicredi pode reunir mais de um mês no mesmo arquivo: use o filtro de datas quando quiser exportar apenas um mês.

Um arquivo idêntico com o mesmo período não pode gerar outro lote da mesma conta. Em arquivos distintos, movimentos com a mesma data, valor e descrição em lotes anteriores são possíveis repetidos: permanecem visíveis e começam desmarcados. A conferência humana distingue sobreposições de movimentos legítimos iguais. Repetições dentro de um mesmo arquivo são preservadas.

### Identificação da instalação na v0.5.3

A janela de início agora mostra a versão e a pasta aberta antes de buscar o Python. O bootstrap também mostra sua própria versão, a pasta do aplicativo e a versão do Python que o abriu, antes de selecionar o 3.12 para o aplicativo. Isso permite identificar arquivos de versões diferentes ou atalhos que ainda abrem uma instalação anterior. Se a janela mostrar apenas **Concilia - iniciar** e o erro antigo de `UnicodeDecodeError`, atualize a pasta conforme as instruções acima.

O Python 3.15 exibido no caminho de um erro confirma que essa versão abriu o inicializador; isso não informa se o 3.12 também está instalado. A busca da versão corrigida verifica o 3.12 separadamente. Se ele não for encontrado, a mensagem informa como instalar a versão necessária.

### Correção de inicialização no Windows da v0.5.2

Corrigida a leitura das respostas de outros interpretadores/launchers quando o Python novo usa UTF-8 e algum processo filho escreve mensagens em uma página de código antiga do Windows (como cp1252). Isso podia gerar `UnicodeDecodeError` em uma thread e fazer um Python válido passar despercebido, especialmente em caminhos com acentos. A busca agora captura bytes e usa um protocolo JSON ASCII para os dados do interpretador; nomes de pastas acentuados são preservados.

A busca também considera `py -V:3.12`, o registro com a identificação `3.12-64` e o diretório `Python/pythoncore-3.12-64` usado pelo gerenciador novo. Somente um Python 3.12 de 64 bits confirmado é usado para instalar e executar o aplicativo.

Se só houver Python 3.15 (ou outra versão mais nova), instale o 3.12 de 64 bits pelo link do início deste documento. Com o novo **Python Install Manager**, também é possível abrir o Prompt de Comando e executar `py install 3.12`; depois abra o inicializador do Concilia novamente. Não é necessário desinstalar as outras versões.

### Correção de instalação da v0.5.1

Corrigida a seleção de Python que permitia criar o ambiente com 3.13 ou mais novo e depois falhava ao instalar o OCR. Os dois inicializadores usam o mesmo bootstrap, que seleciona Python 3.12 de 64 bits, recupera ambientes incompatíveis com backup e verifica as bibliotecas antes de iniciar. Leitores bancários, regras, banco de dados e exportação Makro permanecem os mesmos da v0.5.

### Correções da v0.5

- O Sicoob Internet Banking é reconhecido como um layout separado do SISBR anterior. Os rodapés de impressão não entram nas descrições; registros continuam corretamente quando o histórico passa de uma página para outra. Divergências mostram data/página quando identificáveis e orientam a gerar novamente o PDF completo ou usar OFX.
- O aprendizado aceita linhas iniciais vazias e colunas extras apenas formatadas, sem dados. O cabeçalho deve continuar com as dez colunas Makro, na mesma ordem. Dados extras são recusados com indicação da linha; a exportação mantém somente as dez colunas padrão.
- No Sicoob Internet Banking, regras exatas também reconhecem formatos conhecidos de apresentação do mesmo histórico, complementos e documento (documento antes/depois do texto, separadores e rótulo de favorecido). Isso não completa nomes nem descarta informações para obter correspondência. Regras conflitantes continuam na 106; descrições truncadas/editadas podem exigir revisão ou uma regra por trecho do próprio cliente.
- Revisão e download aceitam formulários grandes, dentro do limite de 20.000 movimentos. Corrigido o limite de campos que causava erro de “arquivo maior que 16 MB” em conciliações com centenas de linhas. O plano e as regras são preparados uma vez por operação, e a busca de possíveis repetidos é feita uma vez por lote.
- O atalho para corrigir a conta aparece somente quando o número do extrato diverge do cadastro. Erros de leitura mantêm o arquivo e os campos e apresentam uma orientação correspondente ao problema.

Para testar a atualização, preserve `data/`, abra o inicializador da nova pasta e confira **v0.5.3**. Envie a planilha conciliada no aprendizado da conta e depois o PDF correspondente. Lotes antigos mantêm a revisão feita; a atualização não reclassifica dados já salvos. Reenviar um arquivo/período que já existe continua abrindo o lote anterior.

### Avisos dos novos layouts

O OCR da Caixa roda no computador, em memória, com RapidOCR/ONNX Runtime; não envia documentos a serviços externos. Os modelos vêm no pacote instalado pelo inicializador. A primeira instalação fica maior e exige internet para baixar as dependências; a leitura depois funciona sem internet. Não é necessário instalar Tesseract. Os saldos precisam fechar para aceitar o arquivo, mas nomes, espaços e acentos ainda podem conter erros de OCR: revise as descrições e regras. Dependências para Windows de 64 bits/Python 3.12 tiveram sua resolução e download verificados; a execução completa no Windows ainda precisa de validação nesse sistema.

Se o extrato Caixa trouxer movimentos do mesmo mês posteriores ao fim indicado no cabeçalho, eles são preservados com aviso visível. Confira o filtro de datas escolhido. Movimentos fora do mês são recusados.

No Nubank, rendimento líquido informado apenas no resumo, sem lançamento datado, participa da conferência do saldo e gera aviso visível. Ele **não cria uma linha com data inventada**: confira e registre o rendimento separadamente no Makro. A exportação contém as transações datadas do PDF. As descrições completas podem diferir de planilhas simplificadas; uma regra exata com texto diferente fica na 106. Confira especialmente o destinatário das transferências enviadas.

## Exportação Makro

`assets/makro.xlsx` é uma planilha vazia de demonstração, com a aba `Lancamentos`, cabeçalhos e formatos de dados do layout de importação:

`Data | Conta | Valor | Debito | Credito | Historico | SCP | Departamento | Documento | CNPJ`

- Data: data de lançamento como data Excel.
- Conta: descrição do movimento. O modelo Sicoob SISBR inclui o documento na descrição; no Internet Banking, ele fica disponível para consulta e a descrição reúne histórico e complementos.
- Valor: absoluto e numérico.
- Debito / Credito: conta bancária e contrapartida conforme o sentido do movimento.
- Historico: sempre o número **52**.
- SCP, Departamento, Documento e CNPJ: vazios.

A importação efetiva precisa ser conferida no próprio Makro. O aplicativo prepara lançamentos a partir de extratos; ainda não compara um razão contábil importado nem consulta o Makro por API.

## Testes

Execute `python -m unittest discover -v` no ambiente virtual. A suíte usa exemplos fictícios e verifica leitores, valores em centavos, datas, senhas, totais, conflitos, isolamento por conta, estrutura da exportação, códigos contábeis, fórmulas, duplicidades, plano local, cadastro guiado, edição segura de conta, erros de importação e migração do banco. Não depende de documentos de clientes. Os testes adicionais Sicredi e Cresol cobrem posição das colunas, saldo negativo, transporte entre páginas, totais, estornos, descrições em várias linhas, documentos ausentes, repetições legítimas e rejeição de linhas ambíguas. Os testes de BB, Inter, Cora, Caixa e Nubank cobrem datas divididas entre páginas, totais e saldos, continuação de dia, ordem decrescente, tarifas no mesmo horário, rendimento sem data, preservação do destinatário, avisos visíveis, confiança mínima do OCR e estrutura Makro. O fluxo completo também é validado em navegador, incluindo seleção por cliente, revisão, download e uso em tela móvel.

## Dados locais

`data/` contém o banco SQLite, a chave de sessão e o plano próprio carregado. `.venv/` contém as dependências. Ambos são ignorados pelo Git. Extratos, planilhas de clientes, exportações e screenshots não devem ser versionados. Os assets publicados são demonstrativos.

Ambientes `.venv-backup-...` são locais e ignorados pelo Git, assim como `.venv/`. Eles guardam somente o ambiente anterior, não substituem o backup da pasta `data/`.

O aplicativo armazena movimentos e resumo do lote, sem copiar o extrato original enviado. Faça backup de `data/` para preservar os cadastros e revisões. O ZIP baixado do GitHub começa sem clientes, regras ou movimentações.

Cada tarefa na nuvem já usa um ambiente isolado. Use o checkout existente, sem criar Git worktrees salvo pedido explícito. Processos precisam ser reiniciados após restauração da máquina.
