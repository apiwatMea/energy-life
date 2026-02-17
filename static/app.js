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

/**
 * ✅ รองรับผล compare ได้ 2 schema
 * A) bill_* (ของเดิม)
 *   - bill_non_tou.total, bill_tou.total
 *   - bill_recommend, bill_recommend_text
 * B) compare (ของใหม่ที่แนะนำ)
 *   - compare.non_tou_month, compare.tou_month
 *   - compare.recommend, compare.diff_month
 *
 * คืนค่า:
 * {
 *   nonTouMonth, touMonth,
 *   recommend, recommendText,
 *   diffMonth
 * }
 */
function getBillCompare(result) {
  // --- schema A: bill_* ---
  const bnA = result?.bill_non_tou?.total;
  const btA = result?.bill_tou?.total;
  if (bnA !== undefined && btA !== undefined) {
    const recommend = result?.bill_recommend || "";
    const recommendText = result?.bill_recommend_text || "";
    const diffMonth = toNumber(bnA, 0) - toNumber(btA, 0); // + = TOU ถูกกว่า
    return {
      nonTouMonth: toNumber(bnA, 0),
      touMonth: toNumber(btA, 0),
      recommend,
      recommendText,
      diffMonth,
    };
  }

  // --- schema B: compare ---
  const c = result?.compare;
  const bnB = c?.non_tou_month;
  const btB = c?.tou_month;
  if (bnB !== undefined && btB !== undefined) {
    const recommend = c?.recommend || "";
    const diffMonth =
      c?.diff_month !== undefined
        ? toNumber(c.diff_month, 0)
        : toNumber(bnB, 0) - toNumber(btB, 0);

    let recommendText = "";
    if (recommend) {
      const absDiff = Math.abs(diffMonth);
      if (absDiff < 0.01) {
        recommendText = `ค่าใกล้เคียงกัน — แนะนำ: ${recommend}`;
      } else if (diffMonth > 0) {
        recommendText = `แนะนำ: TOU (ประหยัด ~${Math.round(absDiff).toLocaleString()} บาท/เดือน)`;
      } else {
        recommendText = `แนะนำ: Non-TOU (ประหยัด ~${Math.round(absDiff).toLocaleString()} บาท/เดือน)`;
      }
    }

    return {
      nonTouMonth: toNumber(bnB, 0),
      touMonth: toNumber(btB, 0),
      recommend,
      recommendText,
      diffMonth,
    };
  }

  return null;
}

function getSelectedTariffMode() {
  // ✅ เอาตามที่ผู้ใช้ “เลือกอยู่ตอนนี้” เพื่อให้การ์ดประมาณ/เดือนไม่สับสน
  if ($("tariff_mode")) return String($("tariff_mode").value || "").toLowerCase();
  if ($("statTariff")) return String($("statTariff").textContent || "").toLowerCase();
  return "non_tou";
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

  const warnings = (result.warnings || []).map((w) => `<li>${escapeHtml(w)}</li>`).join("");
  const insights = (result.insights || []).map((i) => `<li>${escapeHtml(i)}</li>`).join("");

  const touLine =
    result.kwh_on !== undefined && result.kwh_off !== undefined
      ? `<div class="muted small mt1">TOU Split: On-Peak <b>${fmt(result.kwh_on, 2)}</b> kWh • Off-Peak <b>${fmt(
          result.kwh_off,
          2
        )}</b> kWh</div>`
      : "";

  const solarLine =
    result.kwh_solar_used !== undefined
      ? `<div class="muted small mt1">Solar ใช้ทดแทน: <b>${fmt(result.kwh_solar_used, 2)}</b> kWh</div>`
      : "";

  const evLine =
    result.kwh_ev !== undefined && toNumber(result.kwh_ev, 0) > 0
      ? `<div class="muted small mt1">EV รวม: <b>${fmt(result.kwh_ev, 2)}</b> kWh</div>`
      : "";

  // ✅ billing compare line (รองรับ bill_* และ compare)
  const cmp = getBillCompare(result);
  const billLine =
    cmp && Number.isFinite(cmp.nonTouMonth) && Number.isFinite(cmp.touMonth)
      ? `<div class="muted small mt1">
          📌 เปรียบเทียบ/เดือน: Non-TOU <b>${Math.round(cmp.nonTouMonth).toLocaleString()}</b> บาท •
          TOU <b>${Math.round(cmp.touMonth).toLocaleString()}</b> บาท
          ${
            cmp.recommendText
              ? `<br/><span class="muted small">${escapeHtml(cmp.recommendText)}</span>`
              : ""
          }
        </div>`
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
 * ✅ รองรับ 2 schema:
 * A) result.rooms_enabled + kwh_by_room + kwh_month_by_room + ...
 * B) result.rooms_breakdown (จาก app.py compute_daily_energy)
 */
function renderRoomsSummary(result) {
  const el = $("roomsSummary");
  if (!el) return;

  const rb = result.rooms_breakdown && typeof result.rooms_breakdown === "object" ? result.rooms_breakdown : null;

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

      byRoomMonth[rid] = Number.isFinite(kwhMonthFromBackend) ? kwhMonthFromBackend : kwhDay * 30;

      const evMonthFromBackend =
        toNumber(roomObj.kwh_ev_month, NaN) || toNumber(roomObj.ev_kwh_month, NaN) || toNumber(roomObj.kwh_month_ev, NaN);

      evByRoomMonth[rid] = Number.isFinite(evMonthFromBackend) ? evMonthFromBackend : evDay * 30;
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
        ยังไม่มีข้อมูลรายห้อง — ไปที่ “ตั้งค่าโครงสร้างบ้าน” เพื่อสร้างห้อง
        จากนั้นกด “จำลองไปอีก 1 วัน” อีกครั้ง
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
        ยังไม่มีข้อมูลรายห้อง — ไปที่ “ตั้งค่าโครงสร้างบ้าน” เพื่อสร้างห้อง
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

  const rows = keys
    .map((rid) => {
      const kwhDay = toNumber(byRoom[rid], 0);
      const monthRaw = toNumber(byRoomMonth[rid], NaN);
      const kwhMonth = Number.isFinite(monthRaw) ? monthRaw : kwhDay * 30;

      const pct = totalDay > 0 ? Math.round((kwhDay / totalDay) * 100) : 0;

      const evDay = toNumber(evByRoom?.[rid], 0);
      const evMonthRaw = toNumber(evByRoomMonth?.[rid], NaN);
      const evMonth = Number.isFinite(evMonthRaw) ? evMonthRaw : evDay * 30;

      const evBadge =
        evDay > 0
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
    })
    .join("");

  el.innerHTML = `
    <div class="muted small">
      รวมทั้งบ้าน (รายวัน): <b>${fmt(totalDay, 2)}</b> kWh •
      รวมทั้งบ้าน (รายเดือน): <b>${fmt(totalMonth, 0)}</b> kWh
    </div>
    <div class="mt1">${rows}</div>
  `;
}

/**
 * ✅ Top stats:
 * - “ประมาณ/เดือน” = “ตามมิเตอร์ที่เลือกอยู่ตอนนี้” (กันสับสน)
 *   - เลือก non_tou -> โชว์ Non-TOU/เดือน
 *   - เลือก tou -> โชว์ TOU/เดือน
 * - ส่วน compare ยังโชว์ใน “ผลลัพธ์วันนี้” ตามเดิม
 */
function updateTopStats(result, dayCounter) {
  if ($("statKwhDay")) $("statKwhDay").textContent = `${fmt(result.kwh_total, 2)}`;
  if ($("statCostDay")) $("statCostDay").textContent = `${fmt(result.cost_thb, 0)}`;

  const cmp = getBillCompare(result);
  const selectedMode = getSelectedTariffMode(); // "non_tou" | "tou"

  if ($("statCostMonth")) {
    if (cmp && Number.isFinite(cmp.nonTouMonth) && Number.isFinite(cmp.touMonth)) {
      // ✅ แสดง “ตามมิเตอร์ที่เลือก” เท่านั้น
      const monthValue = selectedMode === "tou" ? cmp.touMonth : cmp.nonTouMonth;

      $("statCostMonth").textContent = `${Math.round(monthValue).toLocaleString()}`;

      if ($("statCostMonthHint")) {
        const hint = `Non-TOU ${Math.round(cmp.nonTouMonth).toLocaleString()} • TOU ${Math.round(cmp.touMonth).toLocaleString()}${
          cmp.recommendText ? ` — ${cmp.recommendText}` : ""
        }`;
        $("statCostMonthHint").textContent = hint;
      }
    } else {
      // fallback: cost_month_est หรือ today*30
      const m =
        result.cost_month_est !== undefined ? toNumber(result.cost_month_est, NaN) : toNumber(result.cost_thb, 0) * 30;

      $("statCostMonth").textContent = Number.isFinite(m) ? `${Math.round(m).toLocaleString()}` : `—`;
      if ($("statCostMonthHint")) $("statCostMonthHint").textContent = `คำนวณจาก “วันนี้ × 30”`;
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
