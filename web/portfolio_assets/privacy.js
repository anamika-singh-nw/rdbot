(() => {
  const cookieName = 'portfolio_privacy';
  let aiAllowed = false, pending = null;
  const cookie = value => { document.cookie = `${cookieName}=${value}; Path=/; Max-Age=${180*86400}; SameSite=Lax${location.protocol === 'https:' ? '; Secure' : ''}`; };
  window.portfolioPrivacy = {
    ensureAIConsent() {
      if (aiAllowed) return Promise.resolve(true);
      if (pending) return pending;
      const dialog = document.getElementById('ai-privacy-dialog');
      const previousFocus = document.activeElement;
      pending = new Promise(resolve => {
        const finish = accepted => {
          aiAllowed = accepted; pending = null; dialog.close();
          dialog.removeEventListener('cancel', cancel);
          dialog.querySelectorAll('[data-ai-choice]').forEach(button => button.onclick = null);
          previousFocus?.focus(); resolve(accepted);
        };
        const cancel = event => { event.preventDefault(); finish(false); };
        dialog.addEventListener('cancel', cancel);
        dialog.querySelectorAll('[data-ai-choice]').forEach(button => button.onclick = () => finish(button.dataset.aiChoice === 'yes'));
        dialog.showModal();
      });
      return pending;
    }
  };
  document.addEventListener('DOMContentLoaded', () => {
    const banner = document.createElement('section');
    banner.className = 'cookie-panel'; banner.setAttribute('aria-label', 'Cookie information');
    banner.innerHTML = `<strong>Your privacy, your choice.</strong><p>No analytics or advertising cookies are used. If you choose “Remember necessary only”, we store one preference cookie for 180 days. You can continue without saving a cookie. AI messages have a separate permission step. <a href="/privacy#cookies">Read the cookie notice</a>.</p><div class="privacy-actions"><button type="button" data-remember>Remember necessary only</button><button type="button" data-no-cookie>Continue without saving</button></div>`;
    const remembered = document.cookie.split(';').some(part => part.trim() === cookieName + '=necessary-v1');
    banner.hidden = remembered; document.body.append(banner);
    banner.querySelector('[data-remember]').onclick = () => { cookie('necessary-v1'); banner.hidden = true; };
    banner.querySelector('[data-no-cookie]').onclick = () => { document.cookie = `${cookieName}=; Path=/; Max-Age=0; SameSite=Lax${location.protocol === 'https:' ? '; Secure' : ''}`; banner.hidden = true; };
    document.querySelectorAll('[data-cookie-settings]').forEach(button => button.onclick = () => { banner.hidden = false; banner.querySelector('button').focus(); });
    document.querySelectorAll('[data-privacy-reset]').forEach(button => button.onclick = () => {
      document.cookie = `${cookieName}=; Path=/; Max-Age=0; SameSite=Lax${location.protocol === 'https:' ? '; Secure' : ''}`;
      aiAllowed = false;
      location.reload();
    });
    const dialog = document.createElement('dialog');
    dialog.id = 'ai-privacy-dialog'; dialog.className = 'privacy-dialog'; dialog.setAttribute('aria-labelledby','ai-privacy-title');
    dialog.innerHTML = `<h2 id="ai-privacy-title">Before you try the AI assistant</h2><p>Your message and recent conversation will be sent through Vercel to Amazon Bedrock (Amazon Nova Lite) in the United States to generate a reply. This is optional; you can still browse the portfolio and use the deterministic examples.</p><p>Use fictional or public information only. Do not enter patient information, confidential business data, passwords or other personal details. These professional demos are intended for adults.</p><p>Permission lasts only on this page. Use “Withdraw AI permission / reset” to stop further messages and clear this page’s conversation. Already processed requests cannot be recalled. <a href="/privacy">Read the privacy notice, retention and your rights</a>.</p><div class="privacy-actions"><button type="button" data-ai-choice="no" autofocus>Keep browsing without AI</button><button type="button" data-ai-choice="yes">I’m 18+ and agree to AI processing</button></div>`;
    document.body.append(dialog);
  });
})();
