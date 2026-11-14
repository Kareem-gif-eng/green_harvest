/*
 * مساعدك الزراعي: رفع الصور ومعاينتها والإرسال للسيرفر وعرض الرد.
 * الكتابة بالصوت والقراءة بالصوت بتيجي من voice.js المشترك.
 * مفيش أي مفتاح API هنا: كل طلبات الذكاء الاصطناعي بتروح للسيرفر.
 */
(function () {
  'use strict';

  var MAX_IMAGE_BYTES = 5 * 1024 * 1024;
  var ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp'];

  function validateImage(file) {
    if (ALLOWED_TYPES.indexOf(file.type) === -1) {
      return 'الملف "' + file.name + '" مش صورة مقبولة. استخدم JPG أو PNG أو WEBP.';
    }
    if (file.size > MAX_IMAGE_BYTES) {
      return 'الصورة "' + file.name + '" حجمها أكبر من 5 ميجا. صغّرها وحاول تاني.';
    }
    return null;
  }

  function friendlyStatus(status) {
    if (status === 401) return 'انتهت الجلسة. سجّل دخول تاني.';
    if (status === 413) return 'حجم الصور كبير. صغّرها وحاول تاني.';
    if (status === 503) return 'مساعدك مش متاح دلوقتي. حاول بعد شوية.';
    return 'حصلت مشكلة. حاول تاني.';
  }

  function init() {
    var root = document.getElementById('assistant');
    if (!root) return;

    var enabled = root.dataset.enabled === 'yes';
    var maxImages = parseInt(root.dataset.maxImages, 10) || 4;
    var url = root.dataset.messageUrl;
    var csrf = root.dataset.csrf;

    var chat = document.getElementById('chat');
    var form = document.getElementById('composer');
    var text = document.getElementById('text');
    var send = document.getElementById('send');
    var sendMarkup = send.innerHTML;
    var statusBox = document.getElementById('status');
    var statusText = document.getElementById('status-text');
    var notice = document.getElementById('notice');
    var previews = document.getElementById('previews');
    var pick = document.getElementById('pick');
    var camera = document.getElementById('camera');
    var promptChips = root.querySelectorAll('[data-prompt]');

    var files = [];   // {file, url}
    var busy = false;

    function showNotice(msg) {
      notice.textContent = msg || '';
      notice.hidden = !msg;
    }

    function scrollChat() {
      chat.scrollTop = chat.scrollHeight;
    }

    function removeEmptyNote() {
      var empty = document.getElementById('empty-note');
      if (empty) empty.remove();
    }

    function makeBubble(role, body, imageUrls, withSpeak) {
      var bubble = document.createElement('div');
      bubble.className = 'bubble ' + (role === 'user' ? 'mine' : 'bot');
      bubble.setAttribute('data-speak-scope', '');

      var who = document.createElement('div');
      who.className = 'who';
      who.textContent = role === 'user' ? 'أنت' : 'مساعدك الزراعي 🌱';
      bubble.appendChild(who);

      var content = document.createElement('div');
      content.className = 'bubble-text';
      content.setAttribute('data-speak-text', '');
      content.textContent = body;
      bubble.appendChild(content);

      (imageUrls || []).forEach(function (src) {
        var img = document.createElement('img');
        img.className = 'chat-img';
        img.src = src;
        img.alt = 'صورة أرسلتها';
        bubble.appendChild(img);
      });

      if (withSpeak) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'speak-btn';
        btn.setAttribute('aria-label', 'اسمع الرد بصوت عالي');
        btn.textContent = '🔊 اسمع الرد';
        bubble.appendChild(btn);
      }
      return bubble;
    }

    function addBubble(role, body, imageUrls, withSpeak) {
      removeEmptyNote();
      var bubble = makeBubble(role, body, imageUrls, withSpeak);
      chat.appendChild(bubble);
      scrollChat();
      return bubble;
    }

    function setBusy(on, label) {
      busy = on;
      send.disabled = on;
      send.innerHTML = on ? 'جاري الرد...' : sendMarkup;
      statusBox.hidden = !on;
      if (label) statusText.textContent = label;
      if (on) { send.setAttribute('aria-busy', 'true'); }
      else { send.removeAttribute('aria-busy'); }
    }

    // ----- الصور -----

    function renderPreviews() {
      previews.innerHTML = '';
      files.forEach(function (item, index) {
        var box = document.createElement('div');
        box.className = 'preview';

        var img = document.createElement('img');
        img.src = item.url;
        img.alt = 'صورة ' + (index + 1);
        box.appendChild(img);

        var remove = document.createElement('button');
        remove.type = 'button';
        remove.textContent = '×';
        remove.setAttribute('aria-label', 'احذف الصورة رقم ' + (index + 1));
        remove.addEventListener('click', function () { removeFile(index); });
        box.appendChild(remove);

        previews.appendChild(box);
      });
      previews.hidden = files.length === 0;
    }

    function removeFile(index) {
      URL.revokeObjectURL(files[index].url);
      files.splice(index, 1);
      renderPreviews();
    }

    function clearFiles() {
      files.forEach(function (item) { URL.revokeObjectURL(item.url); });
      files = [];
      renderPreviews();
    }

    function addFiles(fileList) {
      var problems = [];
      Array.prototype.forEach.call(fileList, function (file) {
        if (files.length >= maxImages) {
          problems.push('تقدر ترفع ' + maxImages + ' صور بس في الرسالة الواحدة.');
          return;
        }
        var problem = validateImage(file);
        if (problem) {
          problems.push(problem);
          return;
        }
        files.push({ file: file, url: URL.createObjectURL(file) });
      });
      renderPreviews();
      showNotice(problems[0] || '');
    }

    Array.prototype.forEach.call(promptChips, function (chip) {
      chip.addEventListener('click', function () {
        if (busy) return;
        text.value = chip.getAttribute('data-prompt') || '';
        text.focus();
        text.dispatchEvent(new Event('input', { bubbles: true }));
      });
    });

    text.addEventListener('keydown', function (event) {
      if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        if (typeof form.requestSubmit === 'function') form.requestSubmit();
        else send.click();
      }
    });

    pick.addEventListener('change', function (event) {
      addFiles(event.target.files);
      event.target.value = '';
    });
    camera.addEventListener('change', function (event) {
      addFiles(event.target.files);
      event.target.value = '';
    });

    // ----- الإرسال -----

    form.addEventListener('submit', function (event) {
      event.preventDefault();
      if (busy) return;
      var message = text.value.trim();
      if (!message && !files.length) {
        showNotice('اكتب سؤالك أو أضف صورة الأول.');
        return;
      }
      if (!enabled) {
        showNotice('مساعدك مش مفعّل دلوقتي.');
        return;
      }
      showNotice('');

      var data = new FormData();
      data.append('text', message);
      files.forEach(function (item) { data.append('images', item.file, item.file.name); });

      var pending = addBubble('user', message || '(صور بدون كلام)',
        files.map(function (item) { return item.url; }), false);
      pending.classList.add('pending');
      setBusy(true, files.length ? 'جاري تحليل الصور...' : 'مساعدك بيفكر في ردّه...');

      fetch(url, {
        method: 'POST',
        body: data,
        credentials: 'same-origin',
        headers: { 'X-CSRF-Token': csrf }
      }).then(function (response) {
        return response.json().then(function (body) {
          return { status: response.status, body: body };
        }).catch(function () {
          return { status: response.status, body: null };
        });
      }).then(function (result) {
        if (result.body && result.body.ok) {
          pending.classList.remove('pending');
          addBubble('bot', result.body.reply, [], true);
          text.value = '';
          clearFiles();
        } else {
          pending.remove();
          showNotice((result.body && result.body.error) || friendlyStatus(result.status));
        }
      }).catch(function () {
        pending.remove();
        showNotice('مافيش اتصال بالسيرفر. اتأكد من الإنترنت وحاول تاني.');
      }).then(function () {
        setBusy(false);
        text.focus();
      });
    });

    scrollChat();
  }

  document.addEventListener('DOMContentLoaded', init);
})();
