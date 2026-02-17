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

/* =========================
 * ✅ NEW: โชว์ “สรุปโครงสร้างบ้านที่บันทึกแล้ว” เหมือนรูปที่ 3
 * ========================= */
function renderHouseStructure(current) {
  const box = $("houseStructureBox");
  if (!box) return;

  const state = current?.state || {};
  const profile = current?.profile || {};

  // house type (พยายามอ่านหลายคีย์ เผื่อ backend ใช้ชื่อไม่เหมือนกัน)
  const houseType =
    state.house_type ||
    state.houseType ||
    state.house?.type ||
    state.house_setup?.house_type ||
    profile.house_type ||
    "—";

  // room counts
  const counts =
    state.room_counts ||
    state.rooms_count ||
    state.house_setup?.counts ||
    state.house?.counts ||
    null;

  // rooms list
  let rooms =
    state.rooms ||
    state.rooms_list ||
    state.house_rooms ||
    state.house_setup?.rooms ||
    null;

  // normalize rooms -> array of room objects {id,type,name,saved?}
  let roomArr = [];

  if (Array.isArray(rooms)) {
    roomArr = rooms.map((r) => {
      if (typeof r === "string") return { id: r };
      return r || {};
    });
  } else if (rooms && typeof rooms === "object") {
    // could be dict keyed by room_id
    roomArr = Object.keys(rooms).map((rid) => {
      const r = rooms[rid];
      if (typeof r === "object") return { id: rid, ...(r || {}) };
      return { id: rid };
    });
  }

  // fallback: ถ้ามี counts แต่ไม่มี rooms list -> สร้างจาก pattern เบื้องต้น (bedroom_1 ฯลฯ)
  if (roomArr.length === 0 && counts && typeof counts === "object") {
    const pushN = (prefix, n) => {
      const N = toNumber(n, 0);
      for (let i = 1; i <= N; i++) roomArr.push({ id: `${prefix}_${i}`, type: prefix });
    };
    pushN("bedroom", counts.bedroom);
    pushN("bathroom", counts.bathroom);
    pushN("living", counts.living);
    pushN("kitchen", counts.kitchen);
    pushN("work", counts.work);
    pushN("parking", counts.parking);
  }

  const hasAny = houseType !== "—" && (counts || roomArr.length > 0);

  if (!hasAny) {
    box.innerHTML = `<div class="muted">ยังไม่มีข้อมูลโครงสร้างบ้าน — กด “ตั้งค่าโครงสร้างบ้าน” เพื่อสร้างห้อง</div>`;
    return;
  }

  // helper: ตรวจว่า “ห้องนี้มีการบันทึกอุปกรณ์แล้ว” หรือไม่ (อ่านหลายคีย์ เผื่อ backend ต่างกัน)
  const roomDetailMaps = [
    state.rooms_detail,
    state.room_details,
    state.rooms_config,
    state.room_configs,
    state.appliances_by_room,
    state.room_appliances,
  ].filter(Boolean);

  function isRoomSaved(rid, roomObj) {
    if (roomObj?.saved === true || roomObj?.is_saved === true || roomObj?.configured === true) return true;
    for (const m of roomDetailMaps) {
      if (m && typeof m === "object" && m[rid]) return true;
    }
    return false;
  }

  // text counts line (ถ้ามี counts)
  const countLine = counts && typeof counts === "object"
    ? `จำนวนห้อง: bedroom ${toNumber(counts.bedroom,0)} • bathroom ${toNumber(counts.bathroom,0)} • living ${toNumber(counts.living,0)} • kitchen ${toNumber(counts.kitchen,0)} • work ${toNumber(counts.work,0)} • parking ${toNumber(counts.parking,0)}`
    : "";

  // edit url template
  const tpl = box.getAttribute("data-room-edit-url-template") || "/room/ROOM_ID";
  const editUrl = (rid) => tpl.replace("ROOM_ID", encodeURIComponent(rid));

  // rows
  const rows = roomArr.map((r) => {
    const rid = r.id || r.room_id || r.roomId || "unknown";
    const rtype = r.type || r.room_type || r.roomType || "";
    const saved = isRoomSaved(rid, r);

    const statusIcon = saved ? "✅" : "🟡";
    const statusText = saved ? "บันทึกแล้ว" : "ยังไม่บันทึก";

    return `
      <div style="padding:10px 0;border-bottom:1px dashed rgba(255,255,255,.08);">
        <div class="row between">
          <div>
            <div class="mini-title">${escapeHtml(rid)}</div>
            <div class="muted small">room_id: ${escapeHtml(rid)}${rtype ? ` • type: ${escapeHtml(rtype)}` : ""}</div>
            <div class="big" style="font-size:18px;margin-top:4px;">${statusIcon} ${escapeHtml(statusText)}</div>
          </div>
          <a class="btn" href="${editUrl(rid)}">แก้ไขห้องนี้</a>
        </div>
      </div>
    `;
  }).join("");

  box.innerHTML = `
    <div class="mini-title">📌 สรุปโครงสร้างบ้านที่บันทึกแล้ว</div>
    <div class="muted small">ประเภทบ้าน: <b>${escapeHtml(houseType)}</b></div>
    ${countLine ? `<div class="muted small">จำนวนห้อง: ${escapeHtml(countLine.replace("จำนวนห้อง: ",""))}</div>` : ""}
    <div class="divider" style="margin:12px 0;"></div>
    ${rows || `<div class="muted">ยังไม่มีรายการห้อง (ลองกดบันทึกและสร้างห้องอีกครั้ง)</div>`}
  `;
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
  const reco = result.bill_recommend_text;

  const billLine = (bn !== undefined && bt !== undefined)
    ? `<div class="muted small mt1">📌 เปรียบเทียบ/เดือน: Non-TOU <b>${fmt(bn,0)}</b> บาท • TOU <b>${fmt(bt,0)}</b> บาท<br/>
       <span class="muted small">${escapeHtml(reco || "")}</span></div>`
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
      ${billLine}
    </div>

    ${insights ? `<div class="mt2"><div class="mini-title">✅ อินไซต์</div><ul class="tips">${insights}</ul></div>` : ""}
    ${warnings ? `<div class="mt2"><div class="mini-title">⚠️ คำเตือน</div><ul class="tips">${warnings}</ul></div>` : ""}
  `;
}

/**
 * รองรับ 2 schema:
 * A) result.rooms_enabled + kwh_by_room + kwh_month_by_room + ...
 * B) result.rooms_breakdown
 */
function renderRoomsSummary(result) {
  const el = $("roomsSummary");
  if (!el) return;

  const rb = result.rooms_breakdown && typeof result.rooms_breakdown === "object"
    ? result.rooms_breakdown
    : null;

  if (rb && Object.keys(rb).length > 0) {
    const byRoom = {};
    const byRoomMonth = {};
    const evByRoom = {};
    const evByRoomMonth = {};

    Object.keys(rb).forEach((rid) => {
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

  const roomsEnabled = !!result.rooms_enabled;
  const byRoom = result.kwh_by_room || {};
  const byRoomMonth = result.kwh_month_by_room || {};
  const evByRoom = result.kwh_ev_by_room || {};
  const evByRoomMonth = result.kwh_ev_month_by_room || {};

  const keysA = Object.keys(byRoom || {});
  if (!roomsEnabled || keysA.length === 0) {
    el.innerHTML = `
      <div class="muted">
        ยังไม่มีข้อมูลรายห้อง — ไปที่ “ตั้งค่าโครงสร้างบ้าน” เพื่อสร้างห้อง แล้วกด “จำลองไปอีก 1 วัน” อีกครั้ง
      </div>
    `;
    return;
  }

  return renderRoomsSummaryFromMaps(el, byRoom, byRoomMonth, evByRoom, evByRoomMonth);
}

function renderRoomsSummaryFromMaps(el, byRoom, byRoomMonth, evByRoom, evByRoomMonth) {
  const keys = Object.keys(byRoom || {});
  if (keys.length === 0) {
    el.innerHTML = `
      <div class="muted">
        ยังไม่มีข้อมูลรายห้อง — ไปที่ “ตั้งค่าโครงสร้างบ้าน” เพื่อสร้างห้อง แล้วกด “จำลองไปอีก 1 วัน” อีกครั้ง
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

function updateTopStats(result, dayCounter) {
  if ($("statKwhDay")) $("statKwhDay").textContent = `${fmt(result.kwh_total, 2)}`;
  if ($("statCostDay")) $("statCostDay").textContent = `${fmt(result.cost_thb, 0)}`;

  const bn = result.bill_non_tou?.total;
  const bt = result.bill_tou?.total;
  const reco = result.bill_recommend_text || "";

  if ($("statCostMonth")) {
    if (bn !== undefined && bt !== undefined) {
      const recommended = (result.bill_recommend === "TOU") ? bt
        : (result.bill_recommend === "Non-TOU") ? bn
        : Math.min(bn, bt);

      $("statCostMonth").textContent = `${fmt(recommended, 0)}`;
      if ($("statCostMonthHint")) {
        $("statCostMonthHint").textContent = `Non-TOU ${fmt(bn,0)} • TOU ${fmt(bt,0)} — ${reco}`;
      }
    } else {
      $("statCostMonth").textContent = `—`;
      if ($("statCostMonthHint")) $("statCostMonthHint").textContent = `คำนวณจากผลจำลองล่าสุด`;
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

  // ✅ render โครงสร้างบ้านทันทีตอนโหลดหน้า (แก้เคส “กลับมาหน้า Home แล้วหาย”)
  renderHouseStructure(current);

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

        // ✅ render โครงสร้างบ้านใหม่หลังบันทึก
        renderHouseStructure(current);

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

        // ✅ เผื่อบางระบบ update state ระหว่าง simulate
        current = await apiGetState();
        renderHouseStructure(current);
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
