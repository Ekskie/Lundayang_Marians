// Global Javascript functionality for Lundayang Marians

// Password visibility eye toggle handler
window.togglePasswordVisibility = function (inputId, buttonEl) {
    const input = document.getElementById(inputId);
    if (!input) return;

    const icon = buttonEl.querySelector('i');
    if (input.type === 'password') {
        input.type = 'text';
        if (icon) {
            icon.setAttribute('data-lucide', 'eye-off');
        }
    } else {
        input.type = 'password';
        if (icon) {
            icon.setAttribute('data-lucide', 'eye');
        }
    }
    if (window.lucide) {
        window.lucide.createIcons();
    }
};

// Page Loader helpers
window.showPageLoader = function (message) {
    const loader = document.getElementById('page-loader');
    if (!loader) return;
    if (message) {
        const textEl = loader.querySelector('.page-loader-text');
        if (textEl) textEl.textContent = message;
    }
    loader.classList.add('active');
};

window.hidePageLoader = function () {
    const loader = document.getElementById('page-loader');
    if (!loader) return;
    loader.classList.remove('active');
};

// Always hide loader cleanly when page is shown (including browser Back/Forward bfcache)
window.addEventListener('pageshow', () => {
    window.hidePageLoader();
});

document.addEventListener('DOMContentLoaded', () => {
    window.hidePageLoader();

    // 1. Branded Page Transition on internal links & standard forms
    document.addEventListener('click', (e) => {
        const link = e.target.closest('a[href]');
        if (!link) return;
        const href = link.getAttribute('href') || '';
        if (
            !href ||
            href.startsWith('#') ||
            href.startsWith('javascript:') ||
            href.startsWith('mailto:') ||
            href.startsWith('tel:') ||
            link.hasAttribute('download') ||
            link.hasAttribute('data-no-loader') ||
            link.target === '_blank' ||
            e.ctrlKey ||
            e.metaKey ||
            e.shiftKey ||
            e.altKey
        ) {
            return;
        }
        try {
            const url = new URL(link.href, window.location.origin);
            if (url.origin !== window.location.origin) return;
            // Same-page hash navigation should not show full-screen loader
            if (url.pathname === window.location.pathname && url.search === window.location.search && url.hash) {
                return;
            }
            window.showPageLoader();
        } catch {
            // Ignore malformed URLs
        }
    });

    document.addEventListener('submit', (e) => {
        const form = e.target;
        if (!form || form.hasAttribute('data-no-loader') || e.defaultPrevented) return;
        // Let forms with dedicated upload overlays handle their own UI
        if (form.querySelector('#pdf_file') && document.getElementById('upload-overlay')) return;
        window.showPageLoader();
    });

    // 2. Mobile Navigation Drawer Toggle
    const mobileNavToggle = document.getElementById('mobile-nav-toggle');
    const navLinks = document.getElementById('nav-links');
    if (mobileNavToggle && navLinks) {
        mobileNavToggle.addEventListener('click', (e) => {
            e.stopPropagation();
            const isOpen = navLinks.classList.toggle('nav-open');
            mobileNavToggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
        });

        document.addEventListener('click', (e) => {
            if (!navLinks.contains(e.target) && !mobileNavToggle.contains(e.target)) {
                navLinks.classList.remove('nav-open');
                mobileNavToggle.setAttribute('aria-expanded', 'false');
            }
        });
    }

    // 3. Dropdown Menu toggle (Click to toggle, close others, sync aria-expanded)
    function closeAllDropdowns() {
        document.querySelectorAll('.dropdown-menu').forEach((m) => m.classList.remove('show'));
        document.querySelectorAll('.btn-profile-dropdown').forEach((b) => b.setAttribute('aria-expanded', 'false'));
    }

    const dropdownContainers = document.querySelectorAll('.dropdown-container');
    dropdownContainers.forEach((container) => {
        const btn = container.querySelector('.btn-profile-dropdown');
        const menu = container.querySelector('.dropdown-menu');
        if (btn && menu) {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const isShown = menu.classList.contains('show');
                closeAllDropdowns();
                if (!isShown) {
                    menu.classList.add('show');
                    btn.setAttribute('aria-expanded', 'true');
                }
            });
        }
    });

    document.addEventListener('click', closeAllDropdowns);
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeAllDropdowns();
    });

    // 4. Consistent Smart Back Button Handler
    document.querySelectorAll('.js-smart-back').forEach((btn) => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            const fallback = btn.getAttribute('data-fallback') || '/';
            const sameOriginReferrer =
                document.referrer &&
                new URL(document.referrer).origin === window.location.origin &&
                document.referrer !== window.location.href;

            window.showPageLoader();
            if (sameOriginReferrer && window.history.length > 1) {
                window.history.back();
            } else {
                window.location.href = fallback;
            }
        });
    });

    // 5. Search Bar Suggestions Autocomplete
    document.querySelectorAll('.js-search-suggest').forEach((input) => {
        const wrap = input.closest('.search-autocomplete-wrap');
        if (!wrap) return;
        const menu = wrap.querySelector('.search-autocomplete-menu');
        if (!menu) return;

        const strandScope = input.getAttribute('data-strand') || '';
        let debounceTimer = null;
        let activeIdx = -1;
        let items = [];

        const closeMenu = () => {
            menu.classList.remove('open');
            menu.innerHTML = '';
            activeIdx = -1;
            items = [];
        };

        const highlightItem = (idx) => {
            const nodes = menu.querySelectorAll('.search-suggest-item');
            nodes.forEach((n, i) => n.classList.toggle('active', i === idx));
            activeIdx = idx;
        };

        const renderSuggestions = (suggestions, query) => {
            items = suggestions || [];
            activeIdx = -1;
            menu.innerHTML = '';

            items.forEach((item) => {
                const a = document.createElement('a');
                a.href = `/paper/${encodeURIComponent(item.id)}`;
                a.className = 'search-suggest-item';

                const titleEl = document.createElement('span');
                titleEl.className = 'search-suggest-title';
                titleEl.textContent = item.title;

                const metaEl = document.createElement('div');
                metaEl.className = 'search-suggest-meta';

                const badge = document.createElement('span');
                badge.className = 'search-suggest-badge';
                badge.textContent = item.strand;
                metaEl.appendChild(badge);

                if (item.academic_year) {
                    const yr = document.createElement('span');
                    yr.textContent = item.academic_year;
                    metaEl.appendChild(yr);
                }
                if (item.hint) {
                    const hint = document.createElement('span');
                    hint.textContent = `• ${item.hint}`;
                    metaEl.appendChild(hint);
                }

                a.appendChild(titleEl);
                a.appendChild(metaEl);
                menu.appendChild(a);
            });

            // Footer quick link to run full search for the typed query
            const footerLink = document.createElement('a');
            const targetPath = strandScope ? `/strand/${encodeURIComponent(strandScope)}` : '/search';
            footerLink.href = `${targetPath}?q=${encodeURIComponent(query)}`;
            footerLink.className = 'search-suggest-item search-suggest-footer';

            const footerLabel = document.createElement('span');
            footerLabel.textContent = items.length
                ? `Search all results for "${query}"`
                : `No instant matches — search all results for "${query}"`;
            footerLink.appendChild(footerLabel);
            menu.appendChild(footerLink);

            menu.classList.add('open');
        };

        input.addEventListener('input', () => {
            const q = input.value.trim();
            clearTimeout(debounceTimer);
            if (q.length < 1) {
                closeMenu();
                return;
            }
            debounceTimer = setTimeout(async () => {
                try {
                    const params = new URLSearchParams({ q });
                    if (strandScope) params.set('strand', strandScope);
                    const res = await fetch(`/api/search-suggestions?${params.toString()}`);
                    if (!res.ok) {
                        closeMenu();
                        return;
                    }
                    const data = await res.json();
                    renderSuggestions(data.suggestions || [], q);
                } catch {
                    closeMenu();
                }
            }, 180);
        });

        input.addEventListener('keydown', (e) => {
            if (!menu.classList.contains('open')) return;
            const nodes = menu.querySelectorAll('.search-suggest-item');
            if (!nodes.length) return;

            if (e.key === 'ArrowDown') {
                e.preventDefault();
                highlightItem((activeIdx + 1) % nodes.length);
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                highlightItem((activeIdx - 1 + nodes.length) % nodes.length);
            } else if (e.key === 'Enter' && activeIdx >= 0 && nodes[activeIdx]) {
                e.preventDefault();
                window.showPageLoader();
                window.location.href = nodes[activeIdx].href;
            } else if (e.key === 'Escape') {
                closeMenu();
            }
        });

        document.addEventListener('click', (e) => {
            if (!wrap.contains(e.target)) {
                closeMenu();
            }
        });
    });

    // 6. Live Password Strength Checker
    document.querySelectorAll('[data-pw-strength]').forEach((input) => {
        const targetId = input.getAttribute('data-pw-strength');
        const box = document.getElementById(targetId);
        if (!box) return;

        const fillEl = box.querySelector('.pw-strength-fill');
        const labelEl = box.querySelector('.pw-strength-label');
        const ruleLen = box.querySelector('[data-rule="length"]');
        const ruleUpper = box.querySelector('[data-rule="upper"]');
        const ruleLower = box.querySelector('[data-rule="lower"]');
        const ruleDigit = box.querySelector('[data-rule="digit"]');

        const evaluate = () => {
            const val = input.value || '';
            const checks = {
                length: val.length >= 8,
                upper: /[A-Z]/.test(val),
                lower: /[a-z]/.test(val),
                digit: /\d/.test(val),
            };

            if (ruleLen) ruleLen.classList.toggle('met', checks.length);
            if (ruleUpper) ruleUpper.classList.toggle('met', checks.upper);
            if (ruleLower) ruleLower.classList.toggle('met', checks.lower);
            if (ruleDigit) ruleDigit.classList.toggle('met', checks.digit);

            const score = Object.values(checks).filter(Boolean).length;
            const pct = val.length === 0 ? 0 : score * 25;
            if (fillEl) {
                fillEl.style.width = `${pct}%`;
                if (score <= 1) {
                    fillEl.style.backgroundColor = '#f87171';
                } else if (score === 2) {
                    fillEl.style.backgroundColor = '#fbbf24';
                } else if (score === 3) {
                    fillEl.style.backgroundColor = '#60a5fa';
                } else {
                    fillEl.style.backgroundColor = '#4ade80';
                }
            }
            if (labelEl) {
                if (val.length === 0) labelEl.textContent = 'Enter a password';
                else if (score <= 1) labelEl.textContent = 'Weak';
                else if (score === 2) labelEl.textContent = 'Fair';
                else if (score === 3) labelEl.textContent = 'Good';
                else labelEl.textContent = 'Strong';
            }
        };

        input.addEventListener('input', evaluate);
        evaluate();
    });

    // 7. Bookmark Button Async Handler (if present)
    const bookmarkToggleBtn = document.getElementById('bookmark-toggle-btn');
    if (bookmarkToggleBtn) {
        bookmarkToggleBtn.addEventListener('click', async () => {
            const paperId = bookmarkToggleBtn.getAttribute('data-paper-id');
            if (!paperId) return;

            try {
                bookmarkToggleBtn.disabled = true;
                const formData = new FormData();
                formData.append('paper_id', paperId);

                const response = await fetch('/bookmark/toggle', {
                    method: 'POST',
                    body: formData,
                });

                const result = await response.json();
                if (result.success) {
                    if (result.bookmarked) {
                        bookmarkToggleBtn.innerHTML = '★ Bookmarked';
                        bookmarkToggleBtn.classList.remove('btn-outline');
                        bookmarkToggleBtn.classList.add('btn-accent');
                    } else {
                        bookmarkToggleBtn.innerHTML = '☆ Bookmark';
                        bookmarkToggleBtn.classList.remove('btn-accent');
                        bookmarkToggleBtn.classList.add('btn-outline');
                    }
                } else {
                    alert('Error updating bookmark: ' + result.error);
                }
            } catch (err) {
                console.error('Bookmark request failed:', err);
                alert('An error occurred. Please try again.');
            } finally {
                bookmarkToggleBtn.disabled = false;
            }
        });
    }
});
