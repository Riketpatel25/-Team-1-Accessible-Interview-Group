/* ===========================================================================
   Interview Studio — app.js
   Single-page frontend: auth, setup, interview, report, history.
   Talks to the Flask API. Text-to-speech + voice input via Web Speech API.
   =========================================================================== */
(function () {
  "use strict";
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];

  // ---- tiny API helper (cookies carry the login session) ------------------
  async function api(path, method = "GET", body) {
    const res = await fetch(path, {
      method,
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || "Something went wrong. Please retry.");
    return data;
  }

  // ---- app state ----------------------------------------------------------
  const state = {
    user: null,
    track: "Behavioral", difficulty: "Standard", length: 15,
    mode: "mock", voice: false, readAloud: false,
    interviewId: null, qIndex: 1, total: 4, currentQ: "",
  };

  // ---- view switching -----------------------------------------------------
  function show(view) {
    $$(".view").forEach((v) => (v.hidden = true));
    $("#view-" + view).hidden = false;
    $("#nav-actions").hidden = !state.user;
    window.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" });
  }

  /* =========================================================================
     THEME + TEXT SIZE (F10, R12)
     ========================================================================= */
  const root = document.documentElement;
  function prefersDark(){ return matchMedia("(prefers-color-scheme: dark)").matches; }
  function currentDark(){ const a=root.getAttribute("data-theme"); return a?a==="dark":prefersDark(); }
  $("#theme-toggle").addEventListener("click", () => {
    root.setAttribute("data-theme", currentDark() ? "light" : "dark");
    $("#theme-label").textContent = currentDark() ? "Light" : "Dark";
  });

  $$(".textsize button").forEach((b) =>
    b.addEventListener("click", () => {
      $$(".textsize button").forEach((x) => x.setAttribute("aria-pressed", "false"));
      b.setAttribute("aria-pressed", "true");
      document.body.dataset.scale = b.dataset.scale;
      if (state.user) api("/api/prefs", "POST",
        { text_scale: { sm:90, md:100, lg:115, xl:130 }[b.dataset.scale], read_aloud: state.readAloud }).catch(()=>{});
    })
  );

  /* =========================================================================
     AUTH (F15, R1, R2)
     ========================================================================= */
  const authForm = $("#auth-form");
  let authMode = "login";
  $$("#auth-tabs button").forEach((b) =>
    b.addEventListener("click", () => {
      authMode = b.dataset.mode;
      $$("#auth-tabs button").forEach((x) => x.setAttribute("aria-pressed", "false"));
      b.setAttribute("aria-pressed", "true");
      $("#name-field").hidden = authMode === "login";
      $("#auth-submit").textContent = authMode === "login" ? "Log in" : "Create account";
      $("#auth-error").textContent = "";
    })
  );
  authForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    $("#auth-error").textContent = "";
    const payload = {
      name: $("#f-name").value, email: $("#f-email").value, password: $("#f-pass").value,
    };
    try {
      const r = await api(authMode === "login" ? "/api/login" : "/api/register", "POST", payload);
      onLogin(r.user);
    } catch (err) { $("#auth-error").textContent = err.message; }
  });

  $("#logout-btn").addEventListener("click", async () => {
    await api("/api/logout", "POST").catch(()=>{});
    state.user = null; show("auth");
  });

  function onLogin(user) {
    state.user = user;
    $("#user-name").textContent = user.name;
    // apply saved prefs
    const scaleMap = { 90:"sm",100:"md",115:"lg",130:"xl" };
    document.body.dataset.scale = scaleMap[user.text_scale] || "md";
    $$(".textsize button").forEach((x)=>x.setAttribute("aria-pressed", x.dataset.scale===document.body.dataset.scale ? "true":"false"));
    state.readAloud = !!user.read_aloud;
    show("setup");
  }

  /* =========================================================================
     SETUP (R3, R4, R5, F2, F8)
     ========================================================================= */
  $$("#track-group .track").forEach((btn) =>
    btn.addEventListener("click", () => {
      $$("#track-group .track").forEach((b) => b.setAttribute("aria-pressed", "false"));
      btn.setAttribute("aria-pressed", "true");
      state.track = btn.dataset.track;
    })
  );
  bindSeg("#diff-group", "difficulty", (v) => (state.difficulty = v));
  bindSeg("#len-group", "length", (v) => (state.length = parseInt(v)));
  bindSeg("#mode-group", "mode", (v) => {
    state.mode = v;
    $("#jd-wrap").hidden = false; // job description available in both modes
  });

  function bindSeg(sel, key, cb) {
    const btns = $$(sel + " button");
    btns.forEach((b) =>
      b.addEventListener("click", () => {
        btns.forEach((x) => x.setAttribute("aria-pressed", "false"));
        b.setAttribute("aria-pressed", "true");
        cb(b.dataset[key]);
      })
    );
  }

  $("#voice-switch").addEventListener("click", () => toggleSwitch("#voice-switch", (on)=>state.voice=on));
  $("#aloud-switch").addEventListener("click", () => toggleSwitch("#aloud-switch", (on)=>{
    state.readAloud=on;
    if(state.user) api("/api/prefs","POST",{text_scale:{sm:90,md:100,lg:115,xl:130}[document.body.dataset.scale||"md"],read_aloud:on}).catch(()=>{});
  }));
  function toggleSwitch(sel, cb){ const el=$(sel); const on=el.getAttribute("aria-checked")==="true"; el.setAttribute("aria-checked",(!on).toString()); cb(!on); }

  $("#begin-btn").addEventListener("click", startInterview);

  async function startInterview() {
    $("#begin-btn").disabled = true;
    try {
      const r = await api("/api/interviews", "POST", {
        track: state.track, difficulty: state.difficulty, mode: state.mode,
        length: state.length,
        job_title: $("#f-jobtitle").value, job_description: $("#f-jd").value,
      });
      state.interviewId = r.interview_id; state.qIndex = r.q_index;
      state.total = r.total; state.currentQ = r.question;
      setupStage(r);
      show("interview");
    } catch (err) {
      alert(err.message); // NF12 retry-friendly
    } finally { $("#begin-btn").disabled = false; }
  }

  /* =========================================================================
     INTERVIEW STAGE (R6, R7, R8, F5, F6, F9, F11, F12)
     ========================================================================= */
  const messages = $("#messages");

  function setupStage(r) {
    messages.innerHTML = "";
    $("#ctx-role").textContent = `${state.track} · ${state.difficulty}`;
    $("#qcount").innerHTML = state.mode === "practice"
      ? "Practice" : `Q <b>${r.q_index}</b>/${r.total}`;
    $("#pause-btn").hidden = state.mode === "practice";
    resetRail();
    addAi(r.question, r.tag);
    $("#aloud-btn").setAttribute("aria-pressed", state.readAloud.toString());
    if (state.readAloud) speak(r.question);
    $("#answer").value = ""; $("#send").disabled = true;
  }

  function addAi(text, tag) {
    const el = document.createElement("div");
    el.className = "msg ai";
    el.innerHTML =
      `<span class="ava" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none"><path d="M12 2a5 5 0 0 0-5 5v3a5 5 0 0 0 10 0V7a5 5 0 0 0-5-5Zm8 9a8 8 0 0 1-16 0M12 19v3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
       <div><div class="name">Ava</div><div class="b"></div>
       <button class="speak" aria-label="Read this question aloud"><svg viewBox="0 0 24 24" fill="none"><path d="M11 5 6 9H3v6h3l5 4V5Z" fill="currentColor"/><path d="M16 9a3 3 0 0 1 0 6M18.5 6.5a7 7 0 0 1 0 11" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>Read aloud</button></div>`;
    el.querySelector(".b").textContent = text;
    if (tag) { const s=document.createElement("span"); s.className="tag"; s.textContent=tag; el.querySelector(".b").appendChild(s); }
    el.querySelector(".speak").addEventListener("click", () => speak(text));
    messages.appendChild(el); messages.scrollTop = messages.scrollHeight;
  }
  function addMe(text) {
    const el = document.createElement("div"); el.className = "msg me";
    el.innerHTML = `<div><div class="name">You</div><div class="b"></div></div>`;
    el.querySelector(".b").textContent = text;
    messages.appendChild(el); messages.scrollTop = messages.scrollHeight;
  }
  function addTyping() {
    const el = document.createElement("div"); el.className = "msg ai"; el.id = "typing";
    el.innerHTML = `<span class="ava"></span><div class="b typing"><span></span><span></span><span></span></div>`;
    messages.appendChild(el); messages.scrollTop = messages.scrollHeight; return el;
  }

  const answer = $("#answer");
  answer.addEventListener("input", () => {
    answer.style.height = "auto"; answer.style.height = Math.min(answer.scrollHeight, 130) + "px";
    $("#send").disabled = answer.value.trim() === "";
  });
  answer.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendAnswer(); } });
  $("#send").addEventListener("click", sendAnswer);

  async function sendAnswer() {
    const val = answer.value.trim(); if (!val) return;
    addMe(val); answer.value = ""; answer.style.height = "auto"; $("#send").disabled = true;
    const typing = addTyping();
    try {
      const r = await api(`/api/interviews/${state.interviewId}/answer`, "POST", { answer: val });
      typing.remove();
      updateRail(r);
      if (r.is_last) {
        finishInterview();
      } else {
        state.qIndex = r.q_index; state.currentQ = r.next_question;
        $("#qcount").innerHTML = `Q <b>${r.q_index}</b>/${r.total}`;
        addAi(r.next_question, r.tag);
        if (state.readAloud) speak(r.next_question);
      }
    } catch (err) {
      typing.remove();
      const e = addTyping(); e.querySelector(".b").className = "b"; e.querySelector(".b").textContent = err.message + " (tap send to retry)";
      $("#send").disabled = false;
    }
  }

  async function finishInterview() {
    const typing = addTyping();
    try {
      const r = await api(`/api/interviews/${state.interviewId}/complete`, "POST");
      typing.remove();
      renderReport(r.report, r.transcript);
      show("report");
    } catch (err) { typing.remove(); alert(err.message); }
  }

  // pause / resume (F9, R11)
  $("#pause-btn").addEventListener("click", async () => {
    await api(`/api/interviews/${state.interviewId}/pause`, "POST").catch(()=>{});
    alert("Interview paused — your progress is saved. You can resume it from History.");
    loadHistory(); show("history");
  });

  /* ---- feedback rail ---- */
  function resetRail() {
    $("#ring-num").textContent = "–"; $("#ring-fg").setAttribute("stroke-dashoffset", "100.5");
    $$("#rail .bar > i").forEach((i)=>i.style.width="0%");
    $$("#rail .v").forEach((v)=>v.textContent="–");
    $("#tip-body").textContent = "Answer the question to see your live score and one concrete tip.";
  }
  function updateRail(r) {
    const s = r.score;
    setRing(s.confidence);
    setBar("structure", s.structure); setBar("clarity", s.clarity);
    setBar("relevance", s.relevance); setBar("completeness", s.completeness);
    $("#tip-body").innerHTML = `<b>${escapeHtml(r.strengths||"")}</b> ${escapeHtml(r.tip||"")}`;
  }
  function setRing(v) {
    $("#ring-num").textContent = v;
    $("#ring-fg").setAttribute("stroke-dashoffset", (100.5 * (1 - v / 100)).toFixed(1));
  }
  function setBar(key, v) {
    $("#bar-" + key).style.width = v + "%";
    $("#v-" + key).textContent = v;
  }

  /* =========================================================================
     TEXT-TO-SPEECH + VOICE INPUT (F11, F12, R13)  — Web Speech API
     ========================================================================= */
  function speak(text) {
    if (!("speechSynthesis" in window)) return;
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 1; u.pitch = 1;
    speechSynthesis.speak(u);
  }
  $("#aloud-btn").addEventListener("click", () => {
    state.readAloud = !state.readAloud;
    $("#aloud-btn").setAttribute("aria-pressed", state.readAloud.toString());
    if (state.readAloud) speak(state.currentQ); else speechSynthesis.cancel();
  });

  // voice input (dictation) via SpeechRecognition where supported
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const mic = $("#mic");
  let recog = null;
  mic.addEventListener("click", () => {
    if (!SR) { alert("Voice input isn't supported in this browser. You can type your answer, or use Read Aloud to hear questions."); return; }
    const on = mic.getAttribute("aria-pressed") === "true";
    if (on) { recog && recog.stop(); return; }
    recog = new SR(); recog.lang = "en-US"; recog.interimResults = true; recog.continuous = true;
    mic.setAttribute("aria-pressed", "true"); $("#listen-hint").hidden = false;
    let base = answer.value ? answer.value + " " : "";
    recog.onresult = (e) => {
      let t = ""; for (let i = e.resultIndex; i < e.results.length; i++) t += e.results[i][0].transcript;
      answer.value = base + t; $("#send").disabled = answer.value.trim() === "";
    };
    recog.onend = () => { mic.setAttribute("aria-pressed", "false"); $("#listen-hint").hidden = true; };
    recog.start();
  });

  /* =========================================================================
     REPORT (F7, R9)
     ========================================================================= */
  function renderReport(report, transcript) {
    $("#rep-score").textContent = report.overall;
    $("#rep-ring").setAttribute("stroke-dashoffset", (100.5 * (1 - report.overall / 100)).toFixed(1));
    $("#rep-strengths").textContent = report.strengths;
    $("#rep-improve").textContent = report.improvements;
    const list = $("#rep-transcript"); list.innerHTML = "";
    (transcript || []).forEach((row) => {
      const d = document.createElement("div"); d.className = "rcard";
      d.innerHTML = `<h5>Q${row.q_index} · ${row.confidence != null ? row.confidence + "/100" : "—"}</h5>
        <p style="margin:0 0 8px;font-weight:600">${escapeHtml(row.prompt)}</p>
        <p style="margin:0 0 8px" class="muted">${escapeHtml(row.answer || "(no answer)")}</p>
        ${row.tip ? `<p style="margin:0" class="muted"><b>Tip:</b> ${escapeHtml(row.tip)}</p>` : ""}`;
      list.appendChild(d);
    });
  }
  $("#rep-new").addEventListener("click", () => show("setup"));
  $("#rep-history").addEventListener("click", () => { loadHistory(); show("history"); });

  /* =========================================================================
     HISTORY + STATS (F13, F14, R14, R15, R16)
     ========================================================================= */
  async function loadHistory() {
    try {
      const [{ interviews }, { stats }] = await Promise.all([api("/api/history"), api("/api/stats")]);
      // stats tiles
      $("#stat-completed").textContent = stats.completed;
      $("#stat-avg").textContent = stats.avg_score != null ? stats.avg_score : "–";
      $("#stat-weak").textContent = stats.weakest_area || "–";
      // list
      const list = $("#hist-list"); list.innerHTML = "";
      if (!interviews.length) { list.innerHTML = `<p class="muted">No interviews yet — start one to see it here.</p>`; return; }
      interviews.forEach((iv) => {
        const row = document.createElement("div"); row.className = "hrow";
        const status = iv.status === "completed" ? "" : iv.status === "paused" ? "paused" : "";
        row.innerHTML = `<div class="hs">${iv.overall_score != null ? iv.overall_score : "–"}</div>
          <div><div class="ht">${escapeHtml(iv.track)} · ${escapeHtml(iv.difficulty)}</div>
          <div class="hd">${iv.mode} · ${new Date(iv.created_at).toLocaleDateString()}</div></div>
          <span class="pill ${status}">${iv.status.replace("_"," ")}</span>`;
        row.addEventListener("click", () => openPast(iv));
        list.appendChild(row);
      });
    } catch (err) { console.warn(err); }
  }

  async function openPast(iv) {
    if (iv.status === "paused") {
      const r = await api(`/api/interviews/${iv.id}/resume`, "POST").catch(()=>null);
      if (r) {
        state.interviewId = iv.id; state.track = iv.track; state.difficulty = iv.difficulty;
        state.mode = iv.mode; state.total = r.transcript.length + 1;
        messages.innerHTML = ""; $("#ctx-role").textContent = `${iv.track} · ${iv.difficulty}`;
        $("#pause-btn").hidden = false; resetRail();
        r.transcript.forEach((row) => { addAi(row.prompt, row.tag); if (row.answer) addMe(row.answer); });
        show("interview"); return;
      }
    }
    // completed -> show report
    const r = await api(`/api/interviews/${iv.id}`).catch(()=>null);
    if (r) { renderReport({ overall: iv.overall_score, strengths: iv.strengths, improvements: iv.improvements }, r.transcript); show("report"); }
  }

  $("#nav-history").addEventListener("click", () => { loadHistory(); show("history"); });
  $("#nav-new").addEventListener("click", () => show("setup"));
  $("#hist-new").addEventListener("click", () => show("setup"));

  /* =========================================================================
     AMBIENT SOUNDWAVE BACKGROUND
     ========================================================================= */
  (function background() {
    const canvas = $("#bg-canvas"); if (!canvas) return;
    const ctx = canvas.getContext("2d"); let W, H, bars, dpr, t = 0, raf;
    const css = (v) => getComputedStyle(root).getPropertyValue(v).trim();
    function resize() {
      dpr = Math.min(devicePixelRatio || 1, 2);
      W = canvas.clientWidth; H = canvas.clientHeight;
      canvas.width = W * dpr; canvas.height = H * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const gap = 26, n = Math.ceil(W / gap) + 2; bars = [];
      for (let i = 0; i < n; i++) bars.push({ x: i * gap, p: Math.random() * 6.28, s: .6 + Math.random(), base: Math.random() });
    }
    function draw() {
      ctx.clearRect(0, 0, W, H);
      const cyan = css("--cyan"), amber = css("--amber");
      for (const b of bars) {
        const amp = Math.sin(t * b.s + b.p) * .5 + .5;
        const h = 18 + amp * (56 + b.base * 66), y = H * .5;
        const g = ctx.createLinearGradient(0, y - h, 0, y + h);
        g.addColorStop(0, amber); g.addColorStop(1, cyan);
        ctx.fillStyle = g; ctx.globalAlpha = .14 + amp * .14;
        if (ctx.roundRect) { ctx.beginPath(); ctx.roundRect(b.x, y - h, 4, h * 2, 2); ctx.fill(); }
        else ctx.fillRect(b.x, y - h, 4, h * 2);
      }
      ctx.globalAlpha = 1; t += .018; raf = requestAnimationFrame(draw);
    }
    resize(); addEventListener("resize", resize);
    if (!reduce) draw();
    else { const cyan = css("--cyan"); for (const b of bars) { ctx.fillStyle = cyan; ctx.globalAlpha = .12; ctx.fillRect(b.x, H*.5 - (24 + b.base*66), 4, (24 + b.base*66)*2); } ctx.globalAlpha = 1; }
  })();

  function escapeHtml(s){ return (s||"").replace(/[&<>"']/g, (c)=>({ "&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;" }[c])); }

  /* =========================================================================
     BOOT — check if already logged in
     ========================================================================= */
  (async function boot() {
    try { const r = await api("/api/me"); if (r.user) { onLogin(r.user); return; } } catch (e) {}
    show("auth");
  })();
})();
