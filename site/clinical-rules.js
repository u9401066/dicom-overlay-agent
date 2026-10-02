// Progressive enhancement: complete rules remain readable without JavaScript.
const search = document.querySelector('#rule-search');
const modality = document.querySelector('#rule-modality');
const rules = [...document.querySelectorAll('.clinical-rule')];
const searchableRules = rules.map(rule => ({rule, text: rule.textContent.toLocaleLowerCase()}));
const filter = () => {
  const term = search.value.trim().toLocaleLowerCase();
  let count = 0;
  for (const {rule, text} of searchableRules) {
    rule.hidden = !(text.includes(term) && (!modality.value || rule.dataset.modality === modality.value));
    if (!rule.hidden) count += 1;
  }
  document.querySelector('#rule-count').textContent = `顯示 ${count} / ${rules.length} 條規則`;
  document.querySelector('#rule-empty').hidden = count !== 0;
};
const clear = () => { search.value = ''; modality.value = ''; filter(); };
document.querySelector('.clinical-filters').hidden = false;
search.addEventListener('input', filter);
modality.addEventListener('change', filter);
document.querySelector('#rule-reset').addEventListener('click', () => { clear(); search.focus(); });
document.querySelector('.clinical-index').addEventListener('click', event => {
  if (event.target.closest('a')) clear();
});
// Direct links, including Back/Forward, must not target a filtered-out rule.
const revealHashTarget = () => {
  let id;
  try { id = decodeURIComponent(location.hash.slice(1)); } catch { return; }
  const target = document.getElementById(id);
  if (target?.classList.contains('reading-stage')) {
    target.open = true;
    target.scrollIntoView();
  }
  if (target?.classList.contains('clinical-rule') && target.hidden) {
    clear();
    target.scrollIntoView();
  }
};
window.addEventListener('hashchange', revealHashTarget);
revealHashTarget();
filter();
