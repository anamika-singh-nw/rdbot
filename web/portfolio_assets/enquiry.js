(() => {
  const form = document.getElementById('brief-form'), result = document.getElementById('brief-result');
  const output = document.getElementById('brief-output'), status = document.getElementById('brief-status');
  form.addEventListener('submit', event => {
    event.preventDefault();
    const read = id => document.getElementById('brief-' + id).value.trim();
    output.textContent = `Professional project enquiry\n\nProfile / company: ${read('profile')}\nService: ${read('service')}\n\nProblem and deliverables:\n${read('scope')}\n\nData / systems: ${read('data') || 'To discuss'}\nBudget / scoping: ${read('budget')}\nTimeline and decision role: ${read('timeline')}\n\nI would like to discuss scope, availability and a suitable engagement.`;
    result.hidden = false; status.textContent = 'Prepared in this browser. Nothing has been sent.';
  });
  form.addEventListener('reset', () => { output.textContent = ''; status.textContent = ''; result.hidden = true; });
  document.getElementById('brief-copy').onclick = async () => {
    try { await navigator.clipboard.writeText(output.textContent); status.textContent = 'Copied. Paste into your LinkedIn message or email when ready.'; }
    catch { status.textContent = 'Copy the displayed text manually; clipboard access is unavailable.'; }
  };
})();
