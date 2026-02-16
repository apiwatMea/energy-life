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

/**
 * ✅ รองรับ 2 schema:
 * A) result.rooms_enabled + kwh_by_room + kwh_month_by_room + ...
 * B) result.rooms_breakdown (จาก app.py compute_daily_energy)
 */
function renderRoomsSummary(result) {
  const el = $("roomsSummary");
  if (!el) return;

  // -------------------------------
  // Schema B: rooms_breakdown
  // -------------------------------
  const rb = result.rooms_breakdown && typeof result.rooms_breakdown === "object"
    ? result.rooms_breakdown
    : null;

  if (rb && Object.keys(rb).length > 0) {
    const byRoom = {};
    const byRoomMonth = {};
    const evByRoom = {};
    const evByRoomMonth = {};

    const keys = Object.keys(rb);

    keys.forEach((rid) => {
      const roomObj = rb[rid] || {};
      const kwhDay = toNumber(roomObj.kwh_total, 0);

      const breakdown = roomObj.breakdown || {};
      const evDay = toNumber(breakdown.ev_charger, 0);

      byRoom[rid] = kwhDay;
      evByRoom[rid] = evDay;

      const kwhMonthFromBackend =
        toNumber(roomObj.kwh_month_total, NaN) ||
        toNumber(roomObj.kwh_total_month, NaN) ||
        toNumber(roomObj.month_kwh_total, NaN);

      byRoomMonth[rid] = Number.isFinite(kwhMonthFromBackend) ? kwhMonthFromBackend : (kwhDay * 30);

      const evMonthFromBackend =
        toNumber(roomObj.kwh_ev_month, NaN) ||
        toNumber(roomObj.ev_kwh_month, NaN) ||
        toNumber(roomObj.kwh_month_ev, NaN);

      evByRoomMonth[rid] = Number.isFinite(evMonthFromBackend) ? evMonthFromBackend : (evDay * 30);
    });

    return renderRoomsSummaryFromMaps(el, byRoom, byRoomMonth, evByRoom, evByRoomMonth);
  }

  // -------------------------------
  // Schema A: fields แบบเดิม
  // -------------------------------
  const roomsEnabled = !!result.rooms_enabled;
  const byRoom = result.kwh_by_room || {};
  const byRoomMonth = result.kwh_month_by_room || {};
  const evByRoom = result.kwh_ev_by_room || {};
  const evByRoomMonth = result.kwh_ev_month_by_room || {};

  const keysA = Object.keys(byRoom || {});
  if (!roomsEnabled || keysA.length === 0) {
    el.innerHTML = `
      <div class="muted">
        ยังไม่มีข้อมูลรายห้อง — ไปที่ “ตั้งค่าโครงสร้างบ้าน” เพื่อสร้างห้อง แล้วเข้าหน้า “ตั้งค่าอุปกรณ์แยกตามห้อง”
        จากนั้นกด “จำลองไปอีก 1 วัน” อีกครั้ง
      </div>
    `;
    return;
  }

  return renderRoomsSummaryFromMaps(el, byRoom, byRoomMonth, evByRoom, evByRoomMonth);
}

/**
 * วาด UI จากแผนที่ byRoom / byRoomMonth / evByRoom / evByRoomMonth
 */
function renderRoomsSummaryFromMaps(el, byRoom, byRoomMonth, evByRoom, evByRoomMonth) {
  const keys = Object.keys(byRoom || {});
  if (keys.length === 0) {
    el.innerHTML = `
      <div class="muted">
        ยังไม่มีข้อมูลรายห้อง — ไปที่ “ตั้งค่าโครงสร้างบ้าน” เพื่อสร้างห้อง แล้วเข้าหน้า “ตั้งค่าอุปกรณ์แยกตามห้อง”
        จากนั้นกด “จำลองไปอีก 1 วัน” อีกครั้ง
      </div>
    `;
    return;
  }

  keys.sort((a, b) => toNumber(byRoom[b], 0) - toNumber(byRoom[a], 0));

  const totalDay = keys.reduce((s, k) => s + toNumber(byRoom[k], 0), 0);
  const totalMonth = keys.reduce((s, k) => {
    const m = toNumber(byRoomMonth[k], NaN);
    const d = toNumber(byRoom[k], 0);
    return s + (Number.isFinite(m) ? m : d * 30);
  }, 0);

  const rows = keys.map((rid) => {
    const kwhDay = toNumber(byRoom[rid], 0);

    const monthRaw = toNumber(byRoomMonth[rid], NaN);
    const kwhMonth = Number.isFinite(monthRaw) ? monthRaw : (kwhDay * 30);

    const pct = totalDay > 0 ? Math.round((kwhDay / totalDay) * 100) : 0;

    const evDay = toNumber(evByRoom?.[rid], 0);
    const evMonthRaw = toNumber(evByRoomMonth?.[rid], NaN);
    const evMonth = Number.isFinite(evMonthRaw) ? evMonthRaw : (evDay * 30);

    const evBadge = evDay > 0
      ? `<span class="badge" style="margin-left:6px;">EV ${fmt(evDay, 1)} kWh/วัน • ${fmt(evMonth, 0)} kWh/เดือน</span>`
      : "";

    return `
      <div style="padding:10px 0;border-bottom:1px dashed rgba(255,255,255,.08);">
        <div class="row between">
          <div>
            <div class="mini-title">${escapeHtml(rid)}</div>
            <div class="muted small">${pct}% ของทั้งบ้าน ${evBadge}</div>
            <div class="muted small">รายวัน: <b>${fmt(kwhDay, 2)}</b> kWh • รายเดือน: <b>${fmt(kwhMonth, 0)}</b> kWh</div>
          </div>
          <div class="big" style="font-size:18px;text-align:right;">
            ${fmt(kwhDay, 2)} kWh<br/>
            <span class="muted small">${fmt(kwhMonth, 0)} kWh/เดือน</span>
          </div>
        </div>
      </div>
    `;
  }).join("");

  el.innerHTML = `
    <div class="muted small">
      รวมทั้งบ้าน (รายวัน): <b>${fmt(totalDay, 2)}</b> kWh •
      รวมทั้งบ้าน (รายเดือน): <b>${fmt(totalMonth, 0)}</b> kWh
    </div>
    <div class="mt1">${rows}</div>
  `;
}

/* =========================
   ✅ NEW: หา kWh รายเดือนรวมจาก result
   ========================= */
function getMonthlyKwhTotal(result) {
  // 1) backend ส่งตรง
  const direct =
    toNumber(result.kwh_month_total, NaN) ||
    toNumber(result.kwh_total_month, NaN) ||
    toNumber(result.month_kwh_total, NaN);

  if (Number.isFinite(direct)) return direct;

  // 2) schema A: kwh_month_by_room
  if (result.kwh_month_by_room && typeof result.kwh_month_by_room === "object") {
    const m = Object.values(result.kwh_month_by_room).reduce((s, v) => s + toNumber(v, 0), 0);
    if (m > 0) return m;
  }

  // 3) schema B: rooms_breakdown (ถ้ามี month ต่อห้องให้ใช้, ถ้าไม่มีก็ fallback day*30)
  const rb = result.rooms_breakdown && typeof result.rooms_breakdown === "object" ? result.rooms_breakdown : null;
  if (rb && Object.keys(rb).length > 0) {
    const keys = Object.keys(rb);
    const sum = keys.reduce((s, rid) => {
      const r = rb[rid] || {};
      const m =
        toNumber(r.kwh_month_total, NaN) ||
        toNumber(r.kwh_total_month, NaN) ||
        toNumber(r.month_kwh_total, NaN);

      if (Number.isFinite(m)) return s + m;
      return s + toNumber(r.kwh_total, 0) * 30;
    }, 0);
    if (sum > 0) return sum;
  }

  // 4) fallback: รายวัน * 30
  return toNumber(result.kwh_total, 0) * 30;
}

/* =========================
   ✅ NEW: หา "ค่าไฟรายเดือน" ให้ถูกต้อง
   ========================= */
function getMonthlyCost(result) {
  // 1) backend ส่งตรง (แนะนำที่สุด)
  const direct =
    toNumber(result.cost_month_thb, NaN) ||
    toNumber(result.cost_thb_month, NaN) ||
    toNumber(result.month_cost_thb, NaN);

  if (Number.isFinite(direct)) return direct;

  // 2) ถ้ามีเรทรวมมาใน result ค่อยคูณ (เผื่ออนาคต backend แนบ rate)
  const kwhMonth = getMonthlyKwhTotal(result);

  const tariffMode = result.tariff_mode; // ถ้า backend แนบมา
  const nonTouRate = toNumber(result.non_tou_rate, NaN);
  const touOnRate = toNumber(result.tou_on_rate, NaN);
  const touOffRate = toNumber(result.tou_off_rate, NaN);

  if (tariffMode === "tou" && Number.isFinite(touOnRate) && Number.isFinite(touOffRate)) {
    // ถ้ามี on/off เดือนส่งมา
    const onM = toNumber(result.kwh_on_month, NaN);
    const offM = toNumber(result.kwh_off_month, NaN);
    if (Number.isFinite(onM) && Number.isFinite(offM)) {
      return onM * touOnRate + offM * touOffRate;
    }
    // ไม่มี split เดือน -> fallback ดีกว่า
  }

  if (Number.isFinite(nonTouRate)) {
    return kwhMonth * nonTouRate;
  }

  // 3) fallback สุดท้าย: cost รายวัน * 30 (อาจผิดกรณี EV)
  return toNumber(result.cost_thb, 0) * 30;
}

function updateTopStats(result, dayCounter) {
  if ($("statKwhDay")) $("statKwhDay").textContent = `${fmt(result.kwh_total, 2)}`;
  if ($("statCostDay")) $("statCostDay").textContent = `${fmt(result.cost_thb, 0)}`;

  // ✅ FIX: ใช้ค่าไฟรายเดือนจริง (ถ้ามี) ไม่ใช่รายวัน*30
  if ($("statCostMonth")) {
    const costMonth = getMonthlyCost(result);
    $("statCostMonth").textContent = `${fmt(costMonth, 0)}`;
  }

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
        const result = data.result || data;

        updateTopStats(result, data.day_counter);
        renderResultBox(result);
        renderRoomsSummary(result);
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
