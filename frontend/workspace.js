// URL routing preserves mounted form and completed-result ownership.
const legacy = { home: 'simulator', analyse: 'simulator', explore: 'simulator', dca: 'simulator', methodology: 'methods' };
export function initWorkspace(onRoute = () => {}) {
  const views = [...document.querySelectorAll('[data-workspace]')];
  function route() {
    const requested = location.hash.slice(1).split('?')[0] || 'simulator';
    const name = legacy[requested] || requested;
    const active = views.some(v => v.dataset.workspace === name) ? name : 'simulator';
    views.forEach(view => { view.hidden = view.dataset.workspace !== active; });
    document.querySelectorAll('.main-nav a, .mobile-nav a').forEach(link => {
      if (link.hash === `#${active}`) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    });
    document.body.dataset.workspace = active;
    onRoute(active, requested);
  }
  document.querySelector('.skip-link')?.addEventListener('click', event => {
    event.preventDefault(); document.querySelector('main').focus();
  });
  addEventListener('hashchange', route);
  route();
  return route;
}
