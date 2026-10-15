# Desenvolvimento do Concilia

- Não envie ao Git dados de clientes, extratos, planilhas conciliadas, exportações, screenshots, bancos SQLite, chaves, senhas ou arquivos de configuração privada.
- A pasta data/ é local e privada. Não a inclua em commits, pacotes ou artefatos destinados ao repositório.
- assets/ deve conter somente exemplos genéricos. Planos de contas reais devem ser carregados no aplicativo e ficar em data/.
- Use exclusivamente dados fictícios nos testes e nos exemplos de interface. Confira também metadados de documentos antes de versionar arquivos binários.
- Preserve Historico=52, a conta 106 para pendências e o layout de dez colunas do Makro.
- Antes de enviar alterações, execute python -m unittest discover -v e revise os arquivos exatos do commit.
- Cada tarefa já usa um ambiente isolado; não crie Git worktrees sem solicitação explícita.
