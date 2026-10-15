document.addEventListener('DOMContentLoaded', () => {
  const choices = new Map([...document.querySelectorAll('#account-codes option')].map(option => [option.value, option.textContent]));
  const clientPicker = document.querySelector('#client-picker');
  const accountPicker = document.querySelector('#account-picker');
  if (clientPicker && accountPicker) {
    const options = [...accountPicker.options].slice(1).map(option => option.cloneNode(true));
    const filterAccounts = () => {
      accountPicker.replaceChildren(new Option('Selecione a conta bancária', ''));
      accountPicker.options[0].disabled = true;
      const matching = options.filter(option => option.dataset.client === clientPicker.value);
      matching.forEach(option => accountPicker.append(option.cloneNode(true)));
      accountPicker.value = matching.length === 1 ? matching[0].value : '';
      accountPicker.disabled = !clientPicker.value || !matching.length;
      document.querySelector('#account-picker-hint').textContent = !clientPicker.value ? 'Selecione o cliente primeiro.' : !matching.length ? 'Este cliente ainda não tem conta. Use Cadastrar cliente ou conta.' : 'Confira o número e o dígito antes de continuar.';
      document.querySelector('#choose-account-form button').disabled = !accountPicker.value;
    };
    clientPicker.addEventListener('change', filterAccounts);
    accountPicker.addEventListener('change', () => { document.querySelector('#choose-account-form button').disabled = !accountPicker.value; });
    filterAccounts();
  }

  const setupClient = document.querySelector('#setup-client');
  if (setupClient) {
    const toggleClient = () => {
      const fields = document.querySelector('#new-client-fields');
      fields.hidden = Boolean(setupClient.value);
      fields.querySelectorAll('input').forEach(input => { input.disabled = Boolean(setupClient.value); });
    };
    setupClient.addEventListener('change', toggleClient);
    toggleClient();
  }

  document.querySelectorAll('input[type=file]').forEach(input => {
    input.addEventListener('change', () => {
      const label = input.closest('label')?.querySelector('[data-file-name]');
      if (label) label.textContent = input.files.length ? `${input.files[0].name} · ${Math.ceil(input.files[0].size / 1024)} KB` : 'Selecione um arquivo para continuar · até 16 MB';
    });
  });

  const rows = [...document.querySelectorAll('.review-table tbody tr')];
  const rowFilter = document.querySelector('#row-filter');
  const search = document.querySelector('#movement-search');
  const formatMoney = cents => (cents / 100).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const applyFilter = () => {
    const filter = rowFilter?.value || 'all';
    const text = (search?.value || '').toLocaleLowerCase('pt-BR');
    let visible = 0;
    rows.forEach(row => {
      const matches = filter === 'all' || (filter === 'pending' && row.dataset.pending === '1') || (filter === 'duplicate' && row.dataset.duplicate === '1') || (filter === 'excluded' && !row.querySelector('input[type=checkbox]').checked);
      row.hidden = !matches || !row.querySelector('.description').textContent.toLocaleLowerCase('pt-BR').includes(text);
      if (!row.hidden) visible++;
    });
    const count = document.querySelector('#visible-count');
    if (count) count.textContent = `${visible} de ${rows.length} movimentos`;
    const empty = document.querySelector('#no-movements');
    if (empty) empty.hidden = visible > 0;
  };
  const updateTotals = () => {
    let selected = 0, incoming = 0, outgoing = 0, pending = 0;
    rows.forEach(row => {
      const code = row.querySelector('.code-input');
      row.dataset.pending = code.value === '106' ? '1' : '0';
      row.querySelector('.pending-badge').hidden = code.value !== '106';
      row.classList.toggle('excluded-row', !row.querySelector('input[type=checkbox]').checked);
      if (!row.querySelector('input[type=checkbox]').checked) return;
      selected++;
      if (code.value === '106') pending++;
      const cents = Number(row.dataset.cents);
      if (cents > 0) incoming += cents; else outgoing -= cents;
    });
    document.querySelectorAll('[data-selected]').forEach(el => { el.textContent = selected; });
    document.querySelectorAll('[data-pending]').forEach(el => { if (el.tagName !== 'TR') el.textContent = pending; });
    document.querySelectorAll('[data-incoming]').forEach(el => { if (el.tagName !== 'TR') el.textContent = formatMoney(incoming); });
    document.querySelectorAll('[data-outgoing]').forEach(el => { el.textContent = formatMoney(outgoing); });
    document.querySelectorAll('[data-download]').forEach(button => { button.disabled = selected === 0; });
    applyFilter();
  };
  rows.forEach(row => {
    const input = row.querySelector('.code-input');
    input.addEventListener('input', () => {
      const status = document.querySelector('#download-status');
      if (status) status.hidden = true;
      input.setCustomValidity(!choices.has(input.value) ? 'Escolha um código analítico ativo do plano de contas.' : input.value === row.dataset.bank ? 'A contrapartida deve ser diferente da conta bancária.' : '');
      row.querySelector('.code-description').textContent = choices.get(input.value) || 'Código não encontrado';
      const incoming = row.dataset.incoming === '1';
      row.querySelector('.dc-cell').textContent = `D ${incoming ? row.dataset.bank : input.value} / C ${incoming ? input.value : row.dataset.bank}`;
      row.querySelector('.reason').textContent = 'Ajustado nesta revisão';
      updateTotals();
    });
    row.querySelector('input[type=checkbox]').addEventListener('change', () => {
      const status = document.querySelector('#download-status');
      if (status) status.hidden = true;
      updateTotals();
    });
    input.addEventListener('invalid', () => {
      if (row.hidden) {
        rowFilter.value = 'all';
        search.value = '';
        applyFilter();
      }
    });
  });
  rowFilter?.addEventListener('change', applyFilter);
  search?.addEventListener('input', applyFilter);
  if (rows.length) updateTotals();

  const bindSearch = (inputId, tableId, emptyId) => {
    document.querySelector(inputId)?.addEventListener('input', event => {
      let shown = 0;
      document.querySelectorAll(`${tableId} tbody tr`).forEach(row => {
        row.hidden = !row.textContent.toLocaleLowerCase('pt-BR').includes(event.target.value.toLocaleLowerCase('pt-BR'));
        if (!row.hidden) shown++;
      });
      const empty = emptyId && document.querySelector(emptyId);
      if (empty) empty.hidden = shown > 0;
    });
  };
  bindSearch('#history-search', '#history-table', '#history-no-match');
  bindSearch('#accounts-search', '#accounts-table');

  document.querySelectorAll('form[data-async]').forEach(form => {
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const submitter = event.submitter;
      const action = submitter?.getAttribute('formaction') ? submitter.formAction : form.action;
      const buttons = [...form.querySelectorAll('button[type=submit], button:not([type])')];
      const labels = buttons.map(button => button.textContent);
      const error = form.querySelector('.inline-error');
      if (error) { error.hidden = true; error.replaceChildren(); }
      const body = new FormData(form);
      buttons.forEach(button => { button.disabled = true; });
      if (submitter) submitter.textContent = submitter.dataset.loading || 'Processando…';
      try {
        const response = await fetch(action, { method: 'POST', body, headers: { Accept: 'application/json' } });
        const json = (response.headers.get('content-type') || '').includes('application/json');
        const result = json ? await response.json() : null;
        if (!response.ok) {
          const message = result?.error || (response.status === 400 ? 'O formulário expirou. Atualize a página e tente novamente.' : 'Não foi possível concluir. Verifique o arquivo e tente novamente.');
          if (error) {
            error.textContent = message;
            if (result?.account_url) {
              const link = document.createElement('a');
              link.href = result.account_url;
              link.textContent = 'Conferir cadastro da conta →';
              error.append(document.createElement('br'), link);
            }
            error.hidden = false;
            error.focus();
          }
          return;
        }
        if (result?.redirect) { window.location.assign(result.redirect); return; }
        if ((response.headers.get('content-type') || '').includes('spreadsheetml')) {
          const blob = await response.blob();
          const objectUrl = URL.createObjectURL(blob);
          const filename = (response.headers.get('content-disposition') || '').match(/filename="?([^";]+)"?/i)?.[1] || 'Makro.xlsx';
          const link = document.createElement('a');
          link.href = objectUrl; link.download = filename; document.body.append(link); link.click(); link.remove();
          setTimeout(() => URL.revokeObjectURL(objectUrl), 60000);
          const status = document.querySelector('#download-status');
          if (status) { status.hidden = false; status.focus({ preventScroll: true }); }
          return;
        }
        throw new Error('Resposta inesperada');
      } catch (exception) {
        if (error) { error.textContent = 'Não foi possível confirmar a operação. Verifique se a janela do aplicativo continua aberta e tente novamente. Seus campos foram mantidos.'; error.hidden = false; error.focus(); }
      } finally {
        buttons.forEach((button, i) => { button.disabled = false; button.textContent = labels[i]; });
        if (rows.length) updateTotals();
      }
    });
  });
});
