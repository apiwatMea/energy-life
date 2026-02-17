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

  const bn = result.bill_non_tou?.total;
  const bt = result.bill_tou?.total;
  const reco = result.bill_recommend_text || "";

  const billLine = (bn !== undefined && bt !== undefined)
    ? `<div class="muted small mt1">
         📌 เปรียบเทียบ/เดือน: Non-TOU <b>${fmt(bn,0)}</b> บาท • TOU <b>${fmt(bt,0)}</b> บาท<br/>
         <span class="muted small">${escapeHtml(reco)}</span>
       </div>`
    : `<div class="muted small mt1">⚠️ ยังไม่พบข้อมูล “บิลจริง/เดือน” (ตรวจ app.py compute_daily_energy)</div>`;

  box.innerHTML = `
    <div class="row between">
      <div>
        <div class="mini-title">สรุปการจำลอง</div>
        <div class="muted small">รวมการใช้ไฟจากผลจำลองล่าสุด</div>
      </div>
    </div>

    <div class="mt1">
      <div class="big">⚡ ${fmt(result.kwh_total, 2)} kWh</div>
      <div class="big">💰 ${fmt(result.cost_thb, 0)} บาท</div>
      ${touLine}
      ${solarLine}
      ${evLine}
      ${billLine}
    </div>

    ${insights ? `<div class="mt2"><div class="mini-title">✅ อินไซต์</div><ul class="tips">${insights}</ul></div>` : ""}
    ${warnings ? `<div class="mt2"><div class="mini-title">⚠️ คำเตือน</div><ul class="tips">${warnings}</ul></div>` : ""}
  `;
}

function updateTopStats(result, dayCounter) {
  if ($("statKwhDay")) $("statKwhDay").textContent = `${fmt(result.kwh_total, 2)}`;
  if ($("statCostDay")) $("statCostDay").textContent = `${fmt(result.cost_thb, 0)}`;

  const bn = result.bill_non_tou?.total;
  const bt = result.bill_tou?.total;
  const reco = result.bill_recommend_text || "";

  if ($("statCostMonth")) {
    if (bn !== undefined && bt !== undefined) {
      const recommended =
        (result.bill_recommend === "TOU") ? bt :
        (result.bill_recommend === "Non-TOU") ? bn :
        Math.min(bn, bt);

      $("statCostMonth").textContent = `${fmt(recommended, 0)}`;
      if ($("statCostMonthHint")) {
        $("statCostMonthHint").textContent = `Non-TOU ${fmt(bn,0)} • TOU ${fmt(bt,0)} — ${reco}`;
      }
    } else {
      $("statCostMonth").textContent = `—`;
      if ($("statCostMonthHint")) $("statCostMonthHint").textContent = `รอผลจำลองเพื่อคำนวณบิลจริง`;
    }
  }

  if ($("dayCounter") && dayCounter !== undefined) $("dayCounter").textContent = String(dayCounter);
}

function collectPayloadFromUI(currentState) {
  const profile = currentState.profile || {};
  const state = currentState.state || {};

  state.tariff_mode = $("tariff_mode") ? $("tariff_mode").value : state.tariff_mode;
  state.solar_mode = $("solar_mode") ? $("solar_mode").value : state.solar_mode;
  state.solar_kw = $("solar_kw") ? toNumber($("solar_kw").value, state.solar_kw) : state.solar_kw;

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

        if ($("statTariff")) $("statTariff").textContent = current.state.tariff_mode;
        if ($("statSolar")) $("statSolar").textContent = String(current.state.solar_kw);

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
        const result = data.result || data;

        updateTopStats(result, data.day_counter);
        renderResultBox(result);
      } catch (err) {
        console.error(err);
        alert("จำลองไม่สำเร็จ ❌");
      }
    });
  }
}

document.addEventListener("DOMContentLoaded", () => {
  main().catch((e) => console.error(e));
});
