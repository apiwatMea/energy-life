async function api(url, method="GET", body=null){
  const opt = {method, headers: {"Content-Type":"application/json"}};
  if(body) opt.body = JSON.stringify(body);
  const res = await fetch(url, opt);
  const data = await res.json().catch(()=> ({}));
  if(!res.ok) throw new Error(data.error || "Request failed");
  return data;
}

function q(sel, root=document){ return root.querySelector(sel); }
function qa(sel, root=document){ return Array.from(root.querySelectorAll(sel)); }

function setTextIfExists(id, text){
  const el = document.getElementById(id);
  if(el) el.textContent = text;
}

function collectState(){
  const profile = {
    display_name: "ผู้เล่น",
    player_type: q("#player_type").value,
    house_type: q("#house_type").value,
    house_size: q("#house_size").value,
    residents: parseInt(q("#residents").value || "3", 10),
  };
  const state = {
    tariff_mode: q("#tariff_mode").value,
    solar_mode: q("#solar_mode").value,
    solar_kw: parseFloat(q("#solar_kw").value || "0"),
    ev_enabled: q("#ev_enabled").checked,
    appliances: {}
  };

  qa(".appliance").forEach(card=>{
    const key = card.dataset.key;
    const enabled = q(".ap-enabled", card).checked;
    const ap = {enabled};

    if(key === "ac"){
      ap.btu = parseFloat(q(".ac-btu", card).value);
      ap.set_temp = parseFloat(q(".ac-temp", card).value || "26");
      ap.hours = parseFloat(q(".ac-hours", card).value || "0");
      ap.start_hour = parseInt(q(".ac-start", card).value || "0", 10);
      ap.end_hour = parseInt(q(".ac-end", card).value || "0", 10);
      ap.inverter = q(".ac-inverter", card).checked;
    }else if(key === "lights"){
      ap.mode = q(".li-mode", card).value;
      ap.watts = parseFloat(q(".li-watts", card).value || "0");
      ap.hours = parseFloat(q(".li-hours", card).value || "0");
    }else if(key === "fridge"){
      ap.kwh_per_day = parseFloat(q(".fr-kwh", card).value || "0");
    }else{
      const w = q(".ge-watts", card);
      const h = q(".ge-hours", card);
      if(w) ap.watts = parseFloat(w.value || "0");
      if(h) ap.hours = parseFloat(h.value || "0");
    }
    state.appliances[key] = ap;
  });

  state.ev = {
    battery_kwh: parseFloat(q("#ev_batt").value || "60"),
    charger_kw: parseFloat(q("#ev_charger").value || "7.4"),
    soc_from: parseFloat(q("#ev_from").value || "30"),
    soc_to: parseFloat(q("#ev_to").value || "80"),
    charge_start_hour: parseInt(q("#ev_start").value || "22", 10)
  };

  return {profile, state};
}

function renderResult(result){
  // ===== อัปเดตสรุปย่อ (ถ้ามีในหน้า) =====
  const kwhDay = Number(result.kwh_total || 0);
  const costDay = Number(result.cost_thb || 0);
  const costMonth = costDay * 30;

  setTextIfExists("statKwhDay", kwhDay.toFixed(2));
  setTextIfExists("statCostDay", costDay.toFixed(2));
  setTextIfExists("statCostMonth", costMonth.toFixed(2));

  // header badges (ถ้ามี)
  if(result.solar_kw !== undefined){
    // ไม่บังคับ
  }

  const box = q("#resultBox");
  const warn = (result.warnings||[]).map(w=>`<div class="flash error">⚠️ ${w}</div>`).join("");
  const ins = (result.insights||[]).map(i=>`<div class="flash success">✅ ${i}</div>`).join("");

  box.innerHTML = `
    <div class="grid3">
      <div class="mini">
        <div class="mini-title">⚡ kWh รวม</div>
        <div class="big">${kwhDay.toFixed(2)}</div>
      </div>
      <div class="mini">
        <div class="mini-title">💰 ค่าไฟ (฿)</div>
        <div class="big">${costDay.toFixed(2)}</div>
      </div>
      <div class="mini">
        <div class="mini-title">⭐ คะแนนที่ได้</div>
        <div class="big">+${Number(result.points_earned||0)}</div>
      </div>
    </div>

    <div class="grid3 mt2">
      <div class="mini">
        <div class="mini-title">☀️ Solar ใช้เอง (kWh)</div>
        <div class="big">${Number(result.kwh_solar_used||0).toFixed(2)}</div>
      </div>
      <div class="mini">
        <div class="mini-title">🚗 EV (kWh)</div>
        <div class="big">${Number(result.kwh_ev||0).toFixed(2)}</div>
      </div>
      <div class="mini">
        <div class="mini-title">TOU On/Off (kWh)</div>
        <div class="muted">${Number(result.kwh_on||0).toFixed(2)} / ${Number(result.kwh_off||0).toFixed(2)}</div>
      </div>
    </div>

    <div class="divider"></div>

    <h3>แยกตามอุปกรณ์</h3>
    <div class="panel">
      ${Object.entries(result.breakdown||{}).map(([k,v])=>`
        <div class="row between">
          <div class="muted">${k}</div>
          <div><b>${Number(v||0).toFixed(2)}</b> kWh</div>
        </div>`).join("")}
    </div>

    <div class="divider"></div>
    ${warn}
    ${ins}
  `;
}

async function save(){
  const payload = collectState();
  await api("/api/state", "POST", payload);

  // อัปเดต header status ในหน้า (ถ้ามี)
  setTextIfExists("statTariff", payload.state.tariff_mode);
  setTextIfExists("statSolar", String(payload.state.solar_kw));
  setTextIfExists("statEv", payload.state.ev_enabled ? "ON" : "OFF");
}

async function simulate(){
  await save();
  const out = await api("/api/simulate_day", "POST", {});
  // ของเดิมยังใช้ได้
  const p = document.getElementById("points");
  if(p) p.textContent = out.points;
  setTextIfExists("dayCounter", out.day_counter);
  renderResult(out.result);
}

function toggleEvPanel(){
  const ev = document.getElementById("ev_enabled");
  const panel = document.getElementById("ev_panel");
  if(!ev || !panel) return;
  const on = ev.checked;
  panel.style.opacity = on ? "1" : ".35";
  panel.style.pointerEvents = on ? "auto" : "none";
}

document.addEventListener("DOMContentLoaded", ()=>{
  toggleEvPanel();
  const ev = document.getElementById("ev_enabled");
  if(ev) ev.addEventListener("change", toggleEvPanel);

  const saveBtn = document.getElementById("saveBtn");
  if(saveBtn) saveBtn.addEventListener("click", async ()=>{
    try{ await save(); alert("บันทึกเรียบร้อย"); }catch(e){ alert(e.message); }
  });

  const simBtn = document.getElementById("simBtn");
  if(simBtn) simBtn.addEventListener("click", async ()=>{
    try{ await simulate(); }catch(e){ alert(e.message); }
  });
});
