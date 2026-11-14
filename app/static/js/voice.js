/*
 * GreenHarvest — نظام الصوت المشترك (ملف واحد لكل الموقع):
 *   القراءة بالصوت: "اقرأ الصفحة" وزر "اسمع الرد"، مع إيقاف/إيقاف مؤقت/سرعة.
 * بيعتمد على Web Speech API للمتصفح. مفيش خدمة مدفوعة ومفيش مفاتيح هنا.
 */
(function () {
  'use strict';

  var LANG = 'ar-EG';
  var RATE_KEY = 'gh-read-rate';
  var DEFAULT_RATE = 0.95;

  // ---------- دوال مستقلة (بتتختبر من Node) ----------

  // بينضّف النص عشان الصوت ميقراش إيموجي ولا رموز ولا علامات غريبة
  function cleanForSpeech(text) {
    return String(text || '')
      .replace(/[\u064B-\u0652\u0640]/g, '')                 // التشكيل والتطويل
      .replace(/\*\*|__|[*_#`>|•·×✔✘←→↑↓]/g, ' ')
      .replace(/\p{Extended_Pictographic}|\uFE0F|\u200D/gu, ' ')  // إيموجي
      .replace(/[^\p{L}\p{N}\s.,!?؟،:;%]/gu, ' ')              // أي رمز تاني (ومنه الشرطات)
      .replace(/\s+/g, ' ')
      .trim();
  }

  function hasSpeakableText(part) {
    return /[\p{L}\p{N}]/u.test(part);
  }

  // بيقسم النص لأجزاء قصيرة عشان القراءة الصوتية ماتقطعش في النص الطويل
  function splitForSpeech(text, maxLen) {
    maxLen = maxLen || 180;
    var clean = cleanForSpeech(text);
    if (!clean) return [];
    var sentences = clean.match(/[^.!?؟]+[.!?؟]*/g) || [clean];
    var chunks = [];
    var current = '';

    function push(part) {
      part = part.trim();
      if (part && hasSpeakableText(part)) chunks.push(part);
    }

    sentences.forEach(function (sentence) {
      var s = sentence.trim();
      while (s.length > maxLen) {
        var cut = s.lastIndexOf(' ', maxLen);
        if (cut <= 0) cut = maxLen;
        push(s.slice(0, cut));
        s = s.slice(cut).trim();
      }
      if (!s) return;
      if ((current + ' ' + s).trim().length > maxLen) {
        push(current);
        current = s;
      } else {
        current = (current + ' ' + s).trim();
      }
    });
    push(current);
    return chunks;
  }

  function pickArabicVoice(voices) {
    var list = voices || [];
    for (var i = 0; i < list.length; i++) {
      if (/^ar[-_]EG/i.test(list[i].lang)) return list[i];
    }
    for (var j = 0; j < list.length; j++) {
      if (/^ar/i.test(list[j].lang)) return list[j];
    }
    return null;
  }

  // بيجمع النص المرئي بترتيب منطقي: العناوين والفقرات والتعليمات والرسايل، من غير الأزرار والقوائم المتكررة
  function orderedTexts(texts) {
    var out = [];
    texts.forEach(function (t) {
      var clean = String(t || '').replace(/\s+/g, ' ').trim();
      if (clean && out[out.length - 1] !== clean) out.push(clean);
    });
    return out;
  }

  var api = {
    cleanForSpeech: cleanForSpeech,
    splitForSpeech: splitForSpeech,
    pickArabicVoice: pickArabicVoice,
    orderedTexts: orderedTexts
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
    return;
  }

  // ---------- التحكم في القراءة (مشترك بين كل الصفحة) ----------

  var listeners = [];
  var state = { playing: false, paused: false, owner: null, token: 0, rate: loadRate() };

  function loadRate() {
    try {
      var v = parseFloat(window.localStorage.getItem(RATE_KEY));
      return v > 0.5 && v < 1.5 ? v : DEFAULT_RATE;
    } catch (e) {
      return DEFAULT_RATE;
    }
  }

  function saveRate(v) {
    try { window.localStorage.setItem(RATE_KEY, String(v)); } catch (e) { /* التخزين مش متاح: مش مشكلة */ }
  }

  function ttsSupported() {
    return typeof window !== 'undefined' && 'speechSynthesis' in window && typeof SpeechSynthesisUtterance !== 'undefined';
  }

  function notify() {
    var snapshot = { playing: state.playing, paused: state.paused, owner: state.owner };
    listeners.forEach(function (fn) { fn(snapshot); });
  }

  function endCurrent() {
    var owner = state.owner;
    state.playing = false;
    state.paused = false;
    state.owner = null;
    notify();
    if (owner && owner.onEnd) owner.onEnd();
  }

  function stopSpeech() {
    state.token += 1; // أي نهاية قديمة جاية بعد كده هتتجاهل
    if (ttsSupported()) window.speechSynthesis.cancel();
    endCurrent();
  }

  // بيشغّل أجزاء النص بالترتيب. أي قراءة جديدة بتوقف القديمة الأول (مفيش صوتين مع بعض)
  var NO_ARABIC_VOICE = 'جهازك مفيهوش صوت عربي للقراءة. ' +
    'افتح إعدادات الجهاز > الصوت والنطق (Text-to-Speech) وحمّل صوت عربي، أو جرّب متصفح Chrome.';

  // قايمة الأصوات بتتحمّل بعد شوية في بعض المتصفحات، فبنستنى لحد ما تتحمّل (لحد ثانية ونص)
  function getVoicesReady(callback) {
    var synth = window.speechSynthesis;
    var list = synth.getVoices();
    if (list.length) return callback(list);
    var finished = false;
    function done() {
      if (finished) return;
      finished = true;
      synth.onvoiceschanged = null;
      callback(synth.getVoices());
    }
    synth.onvoiceschanged = done;
    setTimeout(done, 1500);
  }

  // رسالة للمستخدم بالعربي: في شريط القراءة لو موجود، وإلا في رسالة الصفحة
  function report(msg) {
    var el = document.getElementById('reader-status');
    if (el) { el.textContent = msg; return; }
    var box = document.getElementById('notice');
    if (box) { box.textContent = msg; box.hidden = false; return; }
    window.alert(msg);
  }

  function speakChunks(chunks, owner) {
    stopSpeech();
    if (!ttsSupported() || !chunks.length) return false;
    var token = state.token;
    state.playing = true;
    state.paused = false;
    state.owner = owner;
    notify();

    getVoicesReady(function (voices) {
      if (token !== state.token) return; // اتوقف أو اتبدل قبل ما الأصوات تتحمّل
      var voice = pickArabicVoice(voices);
      if (!voice) {
        endCurrent();
        report(NO_ARABIC_VOICE);
        return;
      }
      chunks.forEach(function (chunk, index) {
        var utter = new SpeechSynthesisUtterance(chunk);
        utter.lang = LANG;
        utter.rate = state.rate;
        utter.voice = voice;
        utter.onend = function () {
          if (token === state.token && index === chunks.length - 1) endCurrent();
        };
        utter.onerror = function (event) {
          if (token !== state.token) return;
          if (event.error === 'interrupted' || event.error === 'canceled') return;
          endCurrent();
        };
        window.speechSynthesis.speak(utter);
      });
    });
    return true;
  }

  function togglePause() {
    if (!ttsSupported() || !state.playing) return;
    if (state.paused) {
      window.speechSynthesis.resume();
      state.paused = false;
    } else {
      window.speechSynthesis.pause();
      state.paused = true;
    }
    notify();
  }

  function setRate(v) {
    state.rate = v;
    saveRate(v);
  }

  // ---------- قراءة الصفحة ----------

  var SKIP_ANCESTORS = 'nav, header, footer, script, style, [data-no-read], [aria-hidden="true"]';
  var READ_SELECTOR = 'h1, h2, h3, h4, p, li, label, dt, dd, th, td, .warn, .flash, .empty, .stat';

  function visibleText(el) {
    var clone = el.cloneNode(true);
    clone.querySelectorAll('button, select, input, textarea, script, style, .speak-btn, [hidden]').forEach(function (n) {
      n.remove();
    });
    return clone.textContent;
  }

  function collectPageTexts(root) {
    var nodes = Array.prototype.slice.call(root.querySelectorAll(READ_SELECTOR));
    var texts = [];
    nodes.forEach(function (el) {
      if (el.closest(SKIP_ANCESTORS)) return;
      if (el.hidden || el.closest('[hidden]')) return;
      var parent = el.parentElement && el.parentElement.closest(READ_SELECTOR);
      if (parent && root.contains(parent)) return; // النص موجود في العنصر الأب
      texts.push(visibleText(el));
    });
    return orderedTexts(texts);
  }

  function readPage() {
    var main = document.querySelector('main') || document.body;
    var texts = collectPageTexts(main);
    var chunks = [];
    texts.forEach(function (t) { chunks = chunks.concat(splitForSpeech(t)); });
    return chunks;
  }

  // ---------- واجهة شريط القراءة ----------

  function initReader() {
    var bar = document.getElementById('reader-bar');
    if (!bar) return;
    var readBtn = document.getElementById('read-page');
    var pauseBtn = document.getElementById('read-pause');
    var stopBtn = document.getElementById('read-stop');
    var speed = document.getElementById('read-speed');
    var status = document.getElementById('reader-status');

    if (!ttsSupported()) {
      readBtn.disabled = true;
      status.textContent = 'القراءة بالصوت مش مدعومة في المتصفح ده. جرّب Chrome أو Safari.';
      return;
    }

    speed.value = String(state.rate);
    speed.addEventListener('change', function () { setRate(parseFloat(speed.value)); });

    readBtn.addEventListener('click', function () {
      if (state.playing) { stopSpeech(); return; }
      var chunks = readPage();
      if (!chunks.length) { status.textContent = 'مفيش نص يتقري في الصفحة دي.'; return; }
      speakChunks(chunks, { onEnd: null, label: 'page' });
    });
    pauseBtn.addEventListener('click', togglePause);
    stopBtn.addEventListener('click', stopSpeech);

    listeners.push(function (s) {
      var isPage = s.owner && s.owner.label === 'page';
      bar.classList.toggle('is-speaking', s.playing);
      readBtn.hidden = s.playing;
      pauseBtn.hidden = !s.playing;
      stopBtn.hidden = !s.playing;
      pauseBtn.textContent = s.paused ? '▶ كمّل القراءة' : '⏸ وقّف مؤقتاً';
      status.textContent = s.playing
        ? (s.paused ? 'القراءة متوقفة مؤقتاً' : '🔊 جاري القراءة...')
        : '';
      if (!isPage && !s.playing) status.textContent = '';
    });
  }

  // ---------- زر "اسمع الرد" ----------

  function initSpeakButtons() {
    document.addEventListener('click', function (event) {
      var btn = event.target.closest('.speak-btn');
      if (!btn) return;
      if (btn.classList.contains('speaking')) {
        stopSpeech();
        return;
      }
      var scope = btn.closest('[data-speak-scope]') || btn.parentElement;
      var source = scope.querySelector('[data-speak-text]');
      var body = source ? source.textContent : '';
      var chunks = splitForSpeech(body);
      if (!ttsSupported()) {
        flashNotice('القراءة بالصوت مش مدعومة في المتصفح ده. جرّب Chrome أو Safari.');
        return;
      }
      var started = speakChunks(chunks, {
        label: 'reply',
        onEnd: function () { setSpeakState(btn, false); }
      });
      if (started) setSpeakState(btn, true);
    });

    // أزرار "إيقاف الصوت" العايمة: بتظهر بس وقت القراءة
    document.querySelectorAll('[data-stop-audio]').forEach(function (b) {
      b.addEventListener('click', stopSpeech);
    });
    listeners.push(function (s) {
      document.querySelectorAll('[data-stop-audio]').forEach(function (b) { b.hidden = !s.playing; });
    });

    listeners.push(function (s) {
      if (!s.playing) {
        document.querySelectorAll('.speak-btn.speaking').forEach(function (b) { setSpeakState(b, false); });
      }
    });
  }

  function setSpeakState(btn, on) {
    btn.classList.toggle('speaking', on);
    btn.textContent = on ? '⏹ أوقف الصوت' : '🔊 اسمع الرد';
    btn.setAttribute('aria-label', on ? 'إيقاف القراءة' : 'اسمع الرد بصوت عالي');
  }

  function flashNotice(msg) {
    var box = document.getElementById('notice');
    if (box) {
      box.textContent = msg;
      box.hidden = false;
    } else {
      window.alert(msg);
    }
  }

  // ---------- تشغيل ----------

  function init() {
    initReader();
    initSpeakButtons();
  }

  window.GHVoice = {
    speakChunks: speakChunks,
    stop: stopSpeech,
    splitForSpeech: splitForSpeech,
    listen: function (listener) { listeners.push(listener); }
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
