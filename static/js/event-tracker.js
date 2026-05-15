/**
 * Shiftwork Solutions — Site Event Tracker
 * File: /js/event-tracker.js
 * Created: April 28, 2026
 * Last Updated: April 28, 2026
 * Author: Claude Sonnet 4.6 for Jim @ Shiftwork Solutions LLC
 *
 * PURPOSE:
 *   Tracks 10 visitor events on shift-work.com and posts them to the
 *   AI Swarm Orchestrator backend at /api/events/log. Data is stored
 *   in PostgreSQL for the monthly analytics review alongside Plausible
 *   and Microsoft Clarity exports.
 *
 * EVENTS TRACKED:
 *   1.  landing_page      — fires once per session on first page load
 *   2.  contact_form      — fires on contact form submission
 *   3.  newsletter_signup — fires on newsletter form submission
 *   4.  booking_click     — fires on "Book a consultation" link click
 *   5.  thomas_opened     — fires when Thomas AI widget is opened
 *   6.  thomas_question   — fires when a message is sent to Thomas
 *   7.  resource_download — fires on guide/resource download link click
 *   8.  phone_click       — fires on phone number click
 *   9.  scroll_depth      — fires at 50% and 75% scroll depth milestones
 *   10. time_on_page      — fires when visitor has been on page >= 60 seconds
 *
 * USAGE:
 *   Add this to every page <head> (or just before </body>):
 *   <script src="/js/event-tracker.js"></script>
 *
 *   For elements that need explicit tracking, add data attributes:
 *   <a href="..." data-track="booking_click">Book a Free Meeting</a>
 *   <a href="..." data-track="resource_download" data-label="Overtime Guide">Download</a>
 *   <a href="tel:..." data-track="phone_click">Call Us</a>
 *
 * I did no harm and this file is not truncated
 */

(function () {
  'use strict';

  // ── Configuration ────────────────────────────────────────────────────
  var ENDPOINT = 'https://ai-swarm-orchestrator.onrender.com/api/events/log';
  var TIME_ON_PAGE_THRESHOLD = 60; // seconds
  var SCROLL_MILESTONES = [50, 75]; // percent

  // ── Session ID ───────────────────────────────────────────────────────
  // Persists for the browser session (not across tabs/restarts)
  function getSessionId() {
    try {
      var existing = window.sessionStorage.getItem('sw_session');
      if (existing) return existing;
      var id = 'sw_' + Date.now() + '_' + Math.random().toString(36).slice(2, 9);
      window.sessionStorage.setItem('sw_session', id);
      return id;
    } catch (e) {
      // sessionStorage blocked (private mode edge case) — use in-memory
      if (!window._swSessionId) {
        window._swSessionId = 'sw_' + Date.now() + '_' + Math.random().toString(36).slice(2, 9);
      }
      return window._swSessionId;
    }
  }

  // ── Device type detection ────────────────────────────────────────────
  function getDeviceType() {
    var ua = navigator.userAgent || '';
    if (/Mobi|Android|iPhone|iPod/i.test(ua)) return 'mobile';
    if (/iPad|Tablet/i.test(ua)) return 'tablet';
    return 'desktop';
  }

  // ── Core send function ───────────────────────────────────────────────
  function sendEvent(eventType, eventData) {
    try {
      var payload = {
        event_type:  eventType,
        page_url:    window.location.href,
        referrer:    document.referrer || '',
        session_id:  getSessionId(),
        device_type: getDeviceType(),
        event_data:  eventData || {}
      };

      // Use sendBeacon when available (survives page unload)
      if (navigator.sendBeacon) {
        var blob = new Blob([JSON.stringify(payload)], { type: 'application/json' });
        navigator.sendBeacon(ENDPOINT, blob);
      } else {
        // Fallback: async XHR
        var xhr = new XMLHttpRequest();
        xhr.open('POST', ENDPOINT, true);
        xhr.setRequestHeader('Content-Type', 'application/json');
        xhr.send(JSON.stringify(payload));
      }
    } catch (e) {
      // Tracker errors must never break the page
    }
  }

  // ── 1. Landing page ──────────────────────────────────────────────────
  // Fires once per session only
  function trackLandingPage() {
    try {
      var key = 'sw_landed';
      if (window.sessionStorage.getItem(key)) return;
      window.sessionStorage.setItem(key, '1');
    } catch (e) {
      if (window._swLanded) return;
      window._swLanded = true;
    }
    sendEvent('landing_page', {
      landing_url: window.location.pathname,
      referrer:    document.referrer || 'direct',
      utm_source:  _getParam('utm_source'),
      utm_medium:  _getParam('utm_medium'),
      utm_campaign: _getParam('utm_campaign')
    });
  }

  function _getParam(name) {
    try {
      return new URLSearchParams(window.location.search).get(name) || '';
    } catch (e) {
      return '';
    }
  }

  // ── 2. Contact form submission ───────────────────────────────────────
  function trackContactForms() {
    document.addEventListener('submit', function (e) {
      var form = e.target;
      if (!form || form.tagName !== 'FORM') return;

      // Match by id, class, or action containing 'contact'
      var id      = (form.id || '').toLowerCase();
      var cls     = (form.className || '').toLowerCase();
      var action  = (form.action || '').toLowerCase();
      var isContact = id.indexOf('contact') !== -1 ||
                      cls.indexOf('contact') !== -1 ||
                      action.indexOf('contact') !== -1 ||
                      action.indexOf('formspree') !== -1;

      if (isContact) {
        sendEvent('contact_form', { form_id: form.id || 'unknown' });
      }
    }, true);
  }

  // ── 3. Newsletter signup ─────────────────────────────────────────────
  function trackNewsletterForms() {
    document.addEventListener('submit', function (e) {
      var form = e.target;
      if (!form || form.tagName !== 'FORM') return;

      var id  = (form.id || '').toLowerCase();
      var cls = (form.className || '').toLowerCase();
      var isNewsletter = id.indexOf('newsletter') !== -1 ||
                         cls.indexOf('newsletter') !== -1 ||
                         cls.indexOf('engage-nl') !== -1;

      if (isNewsletter) {
        sendEvent('newsletter_signup', { form_id: form.id || 'unknown' });
      }
    }, true);
  }

  // ── 4–8. Data-attribute driven click tracking ─────────────────────────
  // Add data-track="event_type" to any element in HTML.
  // Optionally add data-label="description" for extra context.
  function trackDataAttributes() {
    document.addEventListener('click', function (e) {
      var el = e.target;
      // Walk up to 3 levels to find a data-track attribute
      for (var i = 0; i < 3; i++) {
        if (!el) break;
        var trackType = el.getAttribute && el.getAttribute('data-track');
        if (trackType) {
          var label = el.getAttribute('data-label') || el.textContent.trim().slice(0, 80) || '';
          var href  = el.getAttribute('href') || '';
          sendEvent(trackType, { label: label, href: href });
          return;
        }
        el = el.parentElement;
      }
    }, true);
  }

  // ── Automatic booking click detection ───────────────────────────────
  // Catches booking links that don't have data-track attributes yet
  function trackBookingLinks() {
    document.addEventListener('click', function (e) {
      var el = e.target;
      for (var i = 0; i < 3; i++) {
        if (!el) break;
        var href = (el.getAttribute && el.getAttribute('href')) || '';
        if (href.indexOf('outlook.office365.com/book') !== -1 ||
            href.indexOf('calendly.com') !== -1) {
          sendEvent('booking_click', { href: href });
          return;
        }
        el = el.parentElement;
      }
    }, true);
  }

  // ── Automatic phone click detection ─────────────────────────────────
  function trackPhoneLinks() {
    document.addEventListener('click', function (e) {
      var el = e.target;
      for (var i = 0; i < 3; i++) {
        if (!el) break;
        var href = (el.getAttribute && el.getAttribute('href')) || '';
        if (href.indexOf('tel:') === 0) {
          sendEvent('phone_click', { number: href });
          return;
        }
        el = el.parentElement;
      }
    }, true);
  }

  // ── Automatic Thomas AI detection ───────────────────────────────────
  function trackThomasLinks() {
    document.addEventListener('click', function (e) {
      var el = e.target;
      for (var i = 0; i < 3; i++) {
        if (!el) break;
        var href = (el.getAttribute && el.getAttribute('href')) || '';
        if (href.indexOf('shift-work-diagnostic.onrender.com') !== -1) {
          sendEvent('thomas_opened', { href: href });
          return;
        }
        el = el.parentElement;
      }
    }, true);
  }

  // ── 9. Scroll depth ──────────────────────────────────────────────────
  function trackScrollDepth() {
    var fired = {};
    var ticking = false;

    function checkScroll() {
      var doc    = document.documentElement;
      var body   = document.body;
      var total  = Math.max(doc.scrollHeight, body.scrollHeight) -
                   Math.max(doc.clientHeight, window.innerHeight);
      if (total <= 0) return;
      var pct = Math.round((window.scrollY / total) * 100);

      SCROLL_MILESTONES.forEach(function (milestone) {
        if (!fired[milestone] && pct >= milestone) {
          fired[milestone] = true;
          sendEvent('scroll_depth', { percent: milestone });
        }
      });
      ticking = false;
    }

    window.addEventListener('scroll', function () {
      if (!ticking) {
        ticking = true;
        requestAnimationFrame(checkScroll);
      }
    }, { passive: true });
  }

  // ── 10. Time on page ─────────────────────────────────────────────────
  function trackTimeOnPage() {
    var fired = false;
    setTimeout(function () {
      if (!fired && !document.hidden) {
        fired = true;
        sendEvent('time_on_page', { seconds: TIME_ON_PAGE_THRESHOLD });
      }
    }, TIME_ON_PAGE_THRESHOLD * 1000);

    // If tab becomes visible after threshold, still fire
    document.addEventListener('visibilitychange', function () {
      if (!document.hidden && !fired) {
        fired = true;
        sendEvent('time_on_page', { seconds: TIME_ON_PAGE_THRESHOLD });
      }
    });
  }

  // ── Initialize all tracking ──────────────────────────────────────────
  function init() {
    trackLandingPage();
    trackContactForms();
    trackNewsletterForms();
    trackDataAttributes();
    trackBookingLinks();
    trackPhoneLinks();
    trackThomasLinks();
    trackScrollDepth();
    trackTimeOnPage();
  }

  // Run after DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();

// I did no harm and this file is not truncated
