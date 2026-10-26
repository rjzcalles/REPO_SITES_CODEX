if (document.body.dataset.running === 'true') {
  window.setTimeout(() => {
    if (!document.querySelector('form:focus-within')) window.location.reload();
    else window.setTimeout(() => window.location.reload(), 20000);
  }, 8000);
}
