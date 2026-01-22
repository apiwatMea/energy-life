// static/app.js (REAL MODE - no game/shop dependency)

async function api(url, method = "GET", body = null) {
  const opt = { method, headers: { "Content-Type": "application/json" } };
  if (body) opt.body = JSON.stringify(body);

  const res = await fetch(url, opt);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Request failed");
  return data;
}

function q(sel, root = document) { return root.querySelector(sel); }
function qa(sel, root = document) { return Array.from(root.querySelectorAll(sel)); }

// helper: set text safely (if element exists)
function setText(sel, text) {
  const el = q(sel);
  if (el) el.textContent = String(text);
}

function collectState() {
  // NOTE: อย่า set display_name แบบ hardcode เพราะจะไปทับของเดิมใน DB
  const profile = {
    player_type: q("#player_type") ? q("#player_type").value : "family",
    house_type: q("#house_type") ? q("#house_type").value : "condo",
    house_size: q("#house_size") ? q("#house_size").value : "medium",
    residents: q("#residents") ? parseInt(q("#residents").value || "3", 10) : 3,
  };

  const state = {
    tariff_mode: q("#tariff_mode") ? q("#tariff_mode").value : "non_tou",
    solar_mode: q("#solar_mode") ? q("#solar_mode").value : "manual",
    solar_kw: q("#solar_kw") ? parseFloat(q("#solar_kw").value || "0") : 0,
    ev_enabled: q("#ev_enabled") ? q("#ev_enabled").checked : false,
    appliances: {}
  };

  // appliances
  qa(".appliance").forEach(card => {
    const key = card.dataset.key;
    const enabledEl = q(".ap-enabled", card);
    const enabled = enabledEl ? enabledEl.checked : false;
    const ap = { enabled };

    if (key === "ac") {
      ap.btu = parseFloat((q(".ac-btu", card)?.value) || "12000");
      ap.set_temp = parseFloat((q(".ac-temp", card)?.value) || "26");
      ap.hours = parseFloat((q(".ac-hours", card)?.value) || "0");
      ap.start_hour = parseInt((q(".ac-start", card)?.value) || "20", 10);
      ap.end_hour = parseInt((q(".ac-end", card)?.value) || "2", 10);
      ap.inverter = !!q(".ac-inverter", card)?.checked;
    } else if (key === "lights") {
      ap.mode = (q(".li-mode", card)?.value) || "LED";
      ap.watts = parseFloat((q(".li-watts", card)?.value) || "0");
      ap.hours = parseFloat((q(".li-hours", card)?.value) || "0");
    } else if (key === "fridge") {
      ap.kwh_per_day = parseFloat((q(".fr-kwh", card)?.value) || "1.2");
    } else {
      const w = q(".ge-watts", card);
      const h = q(".ge-hours", card);
      if (w) ap.watts = parseFloat(w.value || "0");
      if (h) ap.hours = parseFloat(h.value || "0");
    }

    state.appliances[key] = ap;
  });

  // EV
  state.ev = {
    battery_kwh: q("#ev_batt") ? parseFloat(q("#ev_batt").value || "60") : 60,
    charger_kw: q("#ev_charger") ? parseFloat(q("#ev_charger").value || "7.4") : 7.4,
    soc_from: q("#ev_from") ? parseFloat(q("#ev_from").value || "30") : 30,
    soc_to: q("#ev_to") ? parseFloat(q("#ev_to").value || "80") : 80,
    charge_start_hour: q("#ev_start") ? parseInt(q("#ev_start").value || "22", 10) : 22
  };

  return { profile, state };
}

function renderResult(result) {
  const box = q("#resultBox");
  if (!box) return;

  const warn = (result.warnings || [])
    .map(w => `<div class="flash error">⚠️ ${w}</div>`).join("");
  const ins = (result.insights || [])
    .map(i => `<div class="flash success">✅ ${i}</div>`).join("");

  const breakdownHtml = result.breakdown
    ? Object.entries(result.breakdown)
        .map(([k, v]) =>
          `<div class="row between"><div class="muted">${k}</div><div><b>${Number(v).toFixed(2)}</b> kWh</div></div>`
        ).join("")
    : `<div class="muted">ไม่มีข้อมูล breakdown</div>`;

  box.innerHTML = `
    <div class="grid3">
      <div class="mini">
        <div class="mini-title">⚡ kWh รวม</div>
        <div class="big">${Number(result.kwh_total || 0).toFixed(2)}</div>
      </div>
      <div class="mini">
        <div class="mini-title">💰 ค่าไฟ (฿)</div>
        <div class="big">${Number(result.cost_thb || 0).toFixed(2)}</div>
      </div>
      <div class="mini">
        <div class="mini-title">⭐ คะแนนที่ได้</div>
        <div class="big">+${Number(result.points_earned || 0)}</div>
      </div>
    </div>

    <div class="grid3 mt2">
      <div class="mini">
        <div class="mini-title">☀️ Solar ใช้เอง (kWh)</div>
        <div class="big">${Number(result.kwh_solar_used || 0).toFixed(2)}</div>
      </div>
      <div class="mini">
        <div class="mini-title">🚗 EV (kWh)</div>
        <div class="big">${Number(result.kwh_ev || 0).toFixed(2)}</div>
      </div>
      <div class="mini">
        <div class="mini-title">TOU On/Off (kWh)</div>
        <div class="muted">${Number(result.kwh_on || 0).toFixed(2)} / ${Number(result.kwh_off || 0).toFixed(2)}</div>
      </div>
    </div>

    <div class="divider"></div>

    <h3>แยกตามอุปกรณ์</h3>
    <div class="panel">
      ${breakdownHtml}
    </div>

    <div class="divider"></div>
    ${warn}
    ${ins}
  `;
}

async function save() {
  const payload = collectState();
  await api("/api/state", "POST", payload);
}

async function simulate() {
  await save();
  const out = await api("/api/simulate_day", "POST", {});
  // กันพังถ้า home.html แบบซ่อนเกม ไม่มี #points ก็ไม่เป็นไร
  setText("#points", out.points);
  setText("#dayCounter", out.day_counter);
  renderResult(out.result);
}

function toggleEvPanel() {
  const evEnabled = q("#ev_enabled");
  const panel = q("#ev_panel");
  if (!evEnabled || !panel) return;

  const on = evEnabled.checked;
  panel.style.opacity = on ? "1" : ".35";
  panel.style.pointerEvents = on ? "auto" : "none";
}

document.addEventListener("DOMContentLoaded", () => {
  toggleEvPanel();

  const evEnabled = q("#ev_enabled");
  if (evEnabled) evEnabled.addEventListener("change", toggleEvPanel);

  const saveBtn = q("#saveBtn");
  if (saveBtn) {
    saveBtn.addEventListener("click", async () => {
      try {
        await save();
        alert("บันทึกเรียบร้อย");
      } catch (e) {
        alert(e.message);
      }
    });
  }

  const simBtn = q("#simBtn");
  if (simBtn) {
    simBtn.addEventListener("click", async () => {
      try {
        await simulate();
      } catch (e) {
        alert(e.message);
      }
    });
  }

  // ✅ โหมดใช้งานจริง: ไม่ผูกกับปุ่มซื้อของ/ร้านค้า
  // ถ้าหน้าไหนยังมี .buyBtn อยู่ ก็ไม่ทำอะไร (หรือจะเอาออกทีหลังได้)
});
