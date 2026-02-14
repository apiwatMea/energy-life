// static/app.js

function $(id) {
  return document.getElementById(id);
}

function toNumber(v, fallback = 0) {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function fmt(n, digits = 1) {
  const x = toNumber(n, 0);
  return x.toFixed(digits);
}

function escapeHtml(str) {
  return String(str ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function apiGetState() {
  const res = await fetch("/api/state", { credentials: "same-origin" });
  if (!res.ok) throw new Error("โหลด state ไม่สำเร็จ");
  return res.json();
}

async function apiSaveState(payload) {
  const res = await fetch("/api/state", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("บันทึกไม่สำเร็จ");
  return res.json();
}

async function apiSimulateDay() {
  const res = await fetch("/api/simulate_day", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!res.ok) throw new Error("จำลองไม่สำเร็จ");
  return res.json();
}

function renderResultBox(result) {
  const box = $("resultBox");
  if (!box) return;

  const warnings = (result.warnings || []).map(w => `<li>${escapeHtml(w)}</li>`).join("");
  const insights = (result.insights || []).map(i => `<li>${escapeHtml(i)}</li>`).join("");

  const touLine = (result.kwh_on !== undefined && result.kwh_off !== undefined)
    ? `<div class="muted small mt1">TOU Split: On-Peak <b>${fmt(result.kwh_on, 2)}</b> kWh • Off-Peak <b>${fmt(result.kwh_off, 2)}</b> kWh</div>`
    : "";

  const solarLine = (result.kwh_solar_used !== undefined)
    ? `<div class="muted small mt1">Solar ใช้ทดแทน: <b>${fmt(result.kwh_solar_used, 2)}</b> kWh</div>`
    : "";

  const evLine = (result.kwh_ev !== undefined && toNumber(result.kwh_ev, 0) > 0)
    ? `<div class="muted small mt1">EV รวม: <b>${fmt(result.kwh_ev, 2)}</b> kWh</div>`
    : "";

  box.innerHTML = `
    <div class="row between">
      <div>
        <div class="mini-title">สรุปการจำลอง</div>
        <div class="muted small">รวมทุกห้อง (ถ้ามีการตั้งค่าแยกห้อง ระบบจะรวมให้อัตโนมัติ)</div>
      </div>
    </div>

    <div class="mt1">
      <div class="big">⚡ ${fmt(result.kwh_total, 2)} kWh</div>
      <div class="big">💰 ${fmt(result.cost_thb, 0)} บาท</div>
      ${touLine}
      ${solarLine}
      ${evLine}
    </div>

    ${insights ? `<div class="mt2"><div class="mini-title">✅ อินไซต์</div><ul class="tips">${insights}</ul></div>` : ""}
    ${warnings ? `<div class="mt2"><div class="mini-title">⚠️ คำเตือน</div><ul class="tips">${warnings}</ul></div>` : ""}
  `;
}

function renderRoomsSummary(result) {
  const el = $("roomsSummary");
  if (!el) return;

  const roomsEnabled = !!result.rooms_enabled;
  const byRoom = result.kwh_by_room || {};
  const evByRoom = result.kwh_ev_by_room || {};

  const keys = Object.keys(byRoom);

  if (!roomsEnabled || keys.length === 0) {
    el.innerHTML = `
      <div class="muted">
        ยังไม่มีข้อมูลรายห้อง — ไปที่ “ตั้งค่าโครงสร้างบ้าน” เพื่อสร้างห้อง แล้วเข้าหน้า “ตั้งค่าอุปกรณ์แยกตามห้อง”
        จากนั้นกด “จำลองไปอีก 1 วัน” อีกครั้ง
      </div>
    `;
    return;
  }

  // sort ใช้ไฟมาก -> น้อย
  keys.sort((a, b) => toNumber(byRoom[b], 0) - toNumber(byRoom[a], 0));

  const total = keys.reduce((s, k) => s + toNumber(byRoom[k], 0), 0);

  const rows = keys.map((rid) => {
    const kwh = toNumber(byRoom[rid], 0);
    const ev = toNumber(evByRoom[rid], 0);
    const pct = total > 0 ? Math.round((kwh / total) * 100) : 0;

    const evBadge = ev > 0
      ? `<span class="badge" style="margin-left:6px;">EV ${fmt(ev, 1)} kWh</span>`
      : "";

    return `
      <div style="padding:10px 0;border-bottom:1px dashed rgba(255,255,255,.08);">
        <div class="row between">
          <div>
            <div class="mini-title">${escapeHtml(rid)}</div>
            <div class="muted small">${pct}% ของทั้งบ้าน ${evBadge}</div>
          </div>
          <div class="big" style="font-size:18px;">${fmt(kwh, 2)} kWh</div>
        </div>
      </div>
    `;
  }).join("");

  el.innerHTML = `
    <div class="muted small">รวมทั้งบ้าน (รายห้อง): <b>${fmt(total, 2)}</b> kWh</div>
    <div class="mt1">${rows}</div>
  `;
}

function updateTopStats(result, dayCounter) {
  if ($("statKwhDay")) $("statKwhDay").textContent = `${fmt(result.kwh_total, 2)}`;
  if ($("statCostDay")) $("statCostDay").textContent = `${fmt(result.cost_thb, 0)}`;
  if ($("statCostMonth")) $("statCostMonth").textContent = `${fmt(toNumber(result.cost_thb, 0) * 30, 0)}`;
  if ($("dayCounter") && dayCounter !== undefined) $("dayCounter").textContent = String(dayCounter);
}

function collectPayloadFromUI(currentState) {
  const profile = currentState.profile || {};
  const state = currentState.state || {};

  // profile
  profile.player_type = $("player_type") ? $("player_type").value : profile.player_type;
  profile.house_type = $("house_type") ? $("house_type").value : profile.house_type;
  profile.house_size = $("house_size") ? $("house_size").value : profile.house_size;
  profile.residents = $("residents") ? toNumber($("residents").value, profile.residents) : profile.residents;

  // state
  state.tariff_mode = $("tariff_mode") ? $("tariff_mode").value : state.tariff_mode;
  state.solar_mode = $("solar_mode") ? $("solar_mode").value : state.solar_mode;
  state.solar_kw = $("solar_kw") ? toNumber($("solar_kw").value, state.solar_kw) : state.solar_kw;

  // legacy EV
  state.ev_enabled = $("ev_enabled") ? $("ev_enabled").checked : state.ev_enabled;
  state.ev = state.ev || {};
  if ($("ev_batt")) state.ev.battery_kwh = toNumber($("ev_batt").value, state.ev.battery_kwh);
  if ($("ev_charger")) state.ev.charger_kw = toNumber($("ev_charger").value, state.ev.charger_kw);
  if ($("ev_start")) state.ev.charge_start_hour = toNumber($("ev_start").value, state.ev.charge_start_hour);
  if ($("ev_from")) state.ev.soc_from = toNumber($("ev_from").value, state.ev.soc_from);
  if ($("ev_to")) state.ev.soc_to = toNumber($("ev_to").value, state.ev.soc_to);

  return { profile, state };
}

async function main() {
  let current = await apiGetState();

  const saveBtn = $("saveBtn");
  const simBtn = $("simBtn");

  if (saveBtn) {
    saveBtn.addEventListener("click", async (e) => {
      e.preventDefault();
      try {
        const payload = collectPayloadFromUI(current);
        await apiSaveState({ profile: payload.profile, state: payload.state });
        current = await apiGetState();

        // update header quick stats
        if ($("statTariff")) $("statTariff").textContent = current.state.tariff_mode;
        if ($("statSolar")) $("statSolar").textContent = String(current.state.solar_kw);
        if ($("statEv")) $("statEv").textContent = current.state.ev_enabled ? "ON" : "OFF";

        alert("บันทึกแล้ว ✅");
      } catch (err) {
        console.error(err);
        alert("บันทึกไม่สำเร็จ ❌");
      }
    });
  }

  if (simBtn) {
    simBtn.addEventListener("click", async (e) => {
      e.preventDefault();
      try {
        const data = await apiSimulateDay();
        const result = data.result;

        updateTopStats(result, data.day_counter);
        renderResultBox(result);
        renderRoomsSummary(result);
      } catch (err) {
        console.error(err);
        alert("จำลองไม่สำเร็จ ❌");
      }
    });
  }

  // initial: ถ้ามีการจำลองแล้วในหน้าอื่น อยากให้ยังโชว์เป็น default ก็ปล่อยไว้
}

document.addEventListener("DOMContentLoaded", () => {
  main().catch((e) => console.error(e));
});
