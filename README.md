# Concilia · preparação contábil para Makro

Aplicativo de desenvolvimento para transformar extratos bancários em lançamentos no modelo de importação do Makro System. Mantém clientes, contas bancárias, regras de classificação e revisão manual em SQLite.

## Testar no Windows

1. Baixe o projeto pelo GitHub em **Code → Download ZIP** e extraia toda a pasta.
2. Instale Python 3.12 ou posterior pelo site oficial [python.org](https://www.python.org/downloads/windows/). Se o instalador mostrar **Add python.exe to PATH**, marque essa opção.
3. Abra `Iniciar-Windows.bat`. Na primeira vez, aguarde a instalação das dependências.
4. Quando aparecer **Running on**, copie o endereço mostrado pelo terminal para o navegador. Mantenha a janela aberta durante o uso. Ctrl+C encerra o servidor.

Se aparecer “Nenhum Python 3.12 ou superior foi encontrado”, a instalação do Python ainda é necessária ou não está acessível ao inicializador. Ele procura `py -3.12`, `py -3`, `python` e `python3`, além de reutilizar um ambiente `.venv` válido. Depois de instalar, feche a janela antiga e abra o inicializador novamente. Se continuar falhando, envie os resultados de `py --list` e `python --version`, executados no Prompt de Comando.

O inicializador para Windows ainda precisa ser validado nesse sistema. O aplicativo e os testes foram executados em Linux com Python 3.12.

## Testar em macOS ou Linux

Instale Python 3.12 ou posterior e execute, no terminal da pasta extraída:

```sh
bash iniciar-mac-linux.sh
```

Para instalação manual ou desenvolvimento, na raiz do projeto:

```sh
python -m venv .venv
.venv/bin/python -m pip install --disable-pip-version-check --no-cache-dir -r requirements.txt
.venv/bin/python -m unittest discover -v
.venv/bin/python app.py
```

O aplicativo escuta somente em loopback, porta 5000; a variável `PORT` permite escolher outra porta. `/health` verifica o processo e o acesso ao SQLite. Não há compilação ou serviço de banco separado.

Esta versão usa o servidor de desenvolvimento do Flask e não inclui autenticação ou permissões por usuário. Precisa de preparação adicional antes de uma implantação para uso público.

## Fluxo guiado · v0.2

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
4. Abra o inicializador da nova pasta. A atualização do banco é automática e preserva os registros existentes.
5. Confira **v0.2** na interface. Se necessário, recarregue a página com Ctrl+F5.

Não copie a pasta `.venv` entre instalações: o inicializador cria o ambiente da nova pasta. O banco local tem uma migração adicional para registrar quando um Excel foi gerado; isso não indica importação efetiva no Makro.

## Formatos aceitos

| Formato | Suporte desta versão |
| --- | --- |
| PDF Sicoob SISBR | Histórico de movimentação, descrições em várias linhas e valores com C/D; conferência dos saldos diários. |
| PDF C6 | Modelo com data de lançamento e data contábil, dentro de um mesmo ano; conferência dos totais mensais informados. |
| PDF protegido | Senha usada em memória para abrir o arquivo. Não é salva nos campos do lote; se aparecer no nome do arquivo, esse trecho é ocultado no nome salvo. |
| OFX | STMTTRN XML/SGML, DTPOSTED, TRNAMT, MEMO/NAME e FITID. |
| CSV / XLSX | Cabeçalho na primeira linha: data, descrição e valor com sinal; mapeamento de nomes de colunas disponível. CSV UTF-8 ou Windows-1252, delimitado por vírgula, ponto e vírgula ou tabulação. XLSX usa a primeira aba e rejeita fórmulas. |

Valores positivos na tabela de extrato representam entradas e negativos representam saídas. Planilhas Makro já conciliadas usam valores absolutos e devem ser enviadas no aprendizado, não como extrato. PDFs digitalizados e outros layouts PDF exigem leitores adicionais; não há OCR nesta versão. Limites: 16 MB por envio, 200 páginas por PDF e 20.000 linhas por tabela.

O PDF do plano de contas deve ser o relatório tabular do Makro com classificação, S/A, código, descrição, D/C e tipo de saldo. CSV do plano usa ponto e vírgula e o cabeçalho:

```text
conta;tipo;codigo;descricao;natureza;tipo_saldo;inativada
```

Tipo deve ser S ou A e inativada deve ser sim ou nao. A conta analítica ativa 106 precisa existir. A troca de plano só é aceita se todos os códigos já usados nos cadastros, regras e lotes continuarem ativos.

Um arquivo idêntico com o mesmo período não pode gerar outro lote da mesma conta. Em arquivos distintos, movimentos com a mesma data, valor e descrição em lotes anteriores são possíveis repetidos: permanecem visíveis e começam desmarcados. A conferência humana distingue sobreposições de movimentos legítimos iguais. Repetições dentro de um mesmo arquivo são preservadas.

## Exportação Makro

`assets/makro.xlsx` é uma planilha vazia de demonstração, com a aba `Lancamentos`, cabeçalhos e formatos de dados do layout de importação:

`Data | Conta | Valor | Debito | Credito | Historico | SCP | Departamento | Documento | CNPJ`

- Data: data de lançamento como data Excel.
- Conta: descrição do movimento; no Sicoob inclui o documento na descrição.
- Valor: absoluto e numérico.
- Debito / Credito: conta bancária e contrapartida conforme o sentido do movimento.
- Historico: sempre o número **52**.
- SCP, Departamento, Documento e CNPJ: vazios.

A importação efetiva precisa ser conferida no próprio Makro. O aplicativo prepara lançamentos a partir de extratos; ainda não compara um razão contábil importado nem consulta o Makro por API.

## Testes

Execute `python -m unittest discover -v` no ambiente virtual. A suíte usa exemplos fictícios e verifica leitores, valores em centavos, datas, senhas, totais, conflitos, isolamento por conta, estrutura da exportação, códigos contábeis, fórmulas, duplicidades, plano local, cadastro guiado, edição segura de conta, erros de importação e migração do banco. Não depende de documentos de clientes. O fluxo completo também é validado em navegador, incluindo seleção por cliente, revisão, download e uso em tela móvel.

## Dados locais

`data/` contém o banco SQLite, a chave de sessão e o plano próprio carregado. `.venv/` contém as dependências. Ambos são ignorados pelo Git. Extratos, planilhas de clientes, exportações e screenshots não devem ser versionados. Os assets publicados são demonstrativos.

O aplicativo armazena movimentos e resumo do lote, sem copiar o extrato original enviado. Faça backup de `data/` para preservar os cadastros e revisões. O ZIP baixado do GitHub começa sem clientes, regras ou movimentações.

Cada tarefa na nuvem já usa um ambiente isolado. Use o checkout existente, sem criar Git worktrees salvo pedido explícito. Processos precisam ser reiniciados após restauração da máquina.
