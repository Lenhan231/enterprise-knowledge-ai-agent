/* Dashboard display conventions are independent of the browser locale and timezone. */
const DashboardFormatting = (() => {
  function number(value, {unit = '', currency = null} = {}) {
    if (!['number','string'].includes(typeof value) || typeof value === 'string' && !value.trim() || !Number.isFinite(Number(value))) return '—';
    unit = (unit || '').toLowerCase();
    let amount = Number(value);
    const percentage = unit === 'percent' || unit.startsWith('fraction');
    if (unit.startsWith('fraction')) amount *= 100;
    const money = !!currency || /^(currency|unknown_currency)/.test(unit) || ['vnd','usd','eur'].includes(unit);
    const digits = percentage ? 1 : money || ['count','products','orders','units','sessions','rows'].includes(unit) ? 0 : 2;
    let shown = new Intl.NumberFormat('vi-VN', {maximumFractionDigits:digits}).format(amount);
    if (/^-0(?:,0+)?$/.test(shown)) shown = shown.slice(1);
    return shown + (percentage ? '%' : currency === 'VND' ? ' ₫' : currency ? ` ${currency}` : '');
  }
  function datetime(value) {
    if (!value) return '—';
    const instant = new Date(typeof value === 'string' && /^\d{4}-\d{2}-\d{2}[T ]\d\d:\d\d(?::\d\d(?:\.\d+)?)?$/.test(value) ? value.replace(' ','T')+'Z' : value);
    if (!Number.isFinite(instant.getTime())) return '—';
    const parts = Object.fromEntries(new Intl.DateTimeFormat('vi-VN', {timeZone:'Asia/Ho_Chi_Minh',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(instant).map(p=>[p.type,p.value]));
    return `${parts.day}/${parts.month}/${parts.year} ${parts.hour}:${parts.minute}`;
  }
  return {number, datetime};
})();
