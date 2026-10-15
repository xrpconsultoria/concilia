# Concilia · preparação contábil para Makro

Aplicativo de desenvolvimento para transformar extratos bancários em lançamentos no modelo de importação do Makro System. Mantém clientes, contas bancárias, regras de classificação e revisão manual em SQLite.

## Testar no Windows

1. Baixe o projeto pelo GitHub em **Code → Download ZIP** e extraia toda a pasta.
2. Instale Python 3.12 pelo site oficial [python.org](https://www.python.org/downloads/), marcando **Add Python to PATH**.
3. Abra `Iniciar-Windows.bat`. Na primeira vez, aguarde a instalação das dependências.
4. Quando aparecer **Running on**, copie o endereço mostrado pelo terminal para o navegador. Mantenha a janela aberta durante o uso. Ctrl+C encerra o servidor.

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

## Primeiro uso

1. Em **Plano de contas local**, carregue o plano geral do Makro em PDF ou CSV. O projeto contém apenas contas de demonstração, insuficientes para uso contábil real. O plano carregado fica em `data/plano_de_contas.csv`, ignorado pelo Git.
2. Cadastre o cliente e a conta bancária, incluindo o dígito. Selecione o código correto da conta bancária no seu plano, inclusive quando houver mais de uma conta do mesmo banco.
3. Em **Configurar regras**, envie uma planilha Makro já conciliada. O aplicativo aprende correspondências exatas de descrição e sentido do movimento, específicas por cliente e conta. Também é possível cadastrar regras por trecho de descrição.
4. Importe o extrato e selecione o período desejado. A exportação usa a data de lançamento.
5. Confira os movimentos e ajuste a contrapartida. A conta **106** representa pendências e permanece permitida na exportação. Regras exatas têm prioridade sobre regras por trecho; conflitos entre códigos ficam na 106.
6. Selecione as linhas desejadas e use **Salvar revisão** para atualizar os totais. **Baixar Excel Makro** também salva a revisão antes de gerar o arquivo.

Sem regra, as contrapartidas padrão são 106 para entradas e saídas; outra conta pode ser configurada no cadastro bancário. Alterações nas regras afetam próximas importações; lotes anteriores preservam sua classificação até a revisão manual.

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

Execute `python -m unittest discover -v` no ambiente virtual. A suíte usa exemplos fictícios e verifica leitores, valores em centavos, datas, senhas, totais, conflitos, isolamento por conta, estrutura da exportação, códigos contábeis, fórmulas, duplicidades, plano local e fluxo HTTP completo. Não depende de documentos de clientes.

## Dados locais

`data/` contém o banco SQLite, a chave de sessão e o plano próprio carregado. `.venv/` contém as dependências. Ambos são ignorados pelo Git. Extratos, planilhas de clientes, exportações e screenshots não devem ser versionados. Os assets publicados são demonstrativos.

O aplicativo armazena movimentos e resumo do lote, sem copiar o extrato original enviado. Faça backup de `data/` para preservar os cadastros e revisões. O ZIP baixado do GitHub começa sem clientes, regras ou movimentações.

Cada tarefa na nuvem já usa um ambiente isolado. Use o checkout existente, sem criar Git worktrees salvo pedido explícito. Processos precisam ser reiniciados após restauração da máquina.
