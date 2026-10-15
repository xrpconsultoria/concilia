document.addEventListener('DOMContentLoaded', () => {
  const choices = new Map([...document.querySelectorAll('#account-codes option')].map(option => [option.value, option.textContent]));
  document.querySelectorAll('.code-input').forEach(input => {
    input.addEventListener('input', () => {
      const row = input.closest('tr');
      row.dataset.pending = input.value === '106' ? '1' : '0';
      row.querySelector('.code-description').textContent = choices.get(input.value) || 'Código não encontrado';
      const incoming = row.dataset.incoming === '1';
      row.querySelector('.dc-cell').textContent = `D ${incoming ? row.dataset.bank : input.value} / C ${incoming ? input.value : row.dataset.bank}`;
    });
  });
  document.querySelector('#row-filter')?.addEventListener('change', event => {
    document.querySelectorAll('.review-table tbody tr').forEach(row => {
      row.hidden = event.target.value === 'pending' ? row.dataset.pending !== '1' : event.target.value === 'duplicate' ? row.dataset.duplicate !== '1' : false;
    });
  });
});
