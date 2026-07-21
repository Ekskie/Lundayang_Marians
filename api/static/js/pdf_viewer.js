// Secure Canvas-Based PDF Viewer using PDF.js

document.addEventListener("DOMContentLoaded", () => {
    const canvas = document.getElementById("pdf-canvas");
    if (!canvas) return;

    const paperId = canvas.getAttribute("data-paper-id");
    if (!paperId) return;

    const pdfUrl = `/api/paper/${paperId}/pdf`;
    
    // PDFJS initialization
    const pdfjsLib = window['pdfjs-dist/build/pdf'];
    pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.4.120/pdf.worker.min.js';

    let pdfDoc = null,
        pageNum = 1,
        pageRendering = false,
        pageNumPending = null,
        scale = 1.3,
        ctx = canvas.getContext('2d');

    // Render the specified page number
    function renderPage(num) {
        pageRendering = true;
        
        pdfDoc.getPage(num).then((page) => {
            const viewport = page.getViewport({ scale: scale });
            canvas.height = viewport.height;
            canvas.width = viewport.width;

            const renderContext = {
                canvasContext: ctx,
                viewport: viewport
            };
            const renderTask = page.render(renderContext);

            // Wait for rendering to finish
            renderTask.promise.then(() => {
                // Burn watermark directly into canvas pixels (anti-screenshot measure)
                burnWatermarkOnCanvas();
                pageRendering = false;
                if (pageNumPending !== null) {
                    renderPage(pageNumPending);
                    pageNumPending = null;
                }
            });
        }).catch(err => {
            console.error("Error rendering page:", err);
            pageRendering = false;
        });

        // Update page counters
        document.getElementById('page-num').textContent = num;
    }

    // Burns a tiled diagonal watermark directly into the canvas pixels
    // so ANY screenshot (including hardware Power+Volume) captures the watermark
    function burnWatermarkOnCanvas() {
        if (!canvas || !ctx) return;
        
        ctx.save();
        ctx.globalAlpha = 0.06; // Very subtle but visible in screenshots
        ctx.fillStyle = "#002060";
        ctx.font = `bold ${Math.max(14, canvas.width * 0.028)}px 'Poppins', sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";

        const text = "LUNDAYANG MARIANS — VIEW ONLY";
        const spacingX = 320;
        const spacingY = 160;

        // Rotate canvas for diagonal watermark
        ctx.translate(canvas.width / 2, canvas.height / 2);
        ctx.rotate(-35 * Math.PI / 180);
        ctx.translate(-canvas.width / 2, -canvas.height / 2);

        // Tile the watermark across the entire canvas (with overflow for rotation)
        for (let y = -canvas.height; y < canvas.height * 2; y += spacingY) {
            for (let x = -canvas.width; x < canvas.width * 2; x += spacingX) {
                ctx.fillText(text, x, y);
            }
        }
        ctx.restore();
    }

    // Queue page rendering
    function queueRenderPage(num) {
        if (pageRendering) {
            pageNumPending = num;
        } else {
            renderPage(num);
        }
    }

    // Previous Page handler
    document.getElementById('prev-page').addEventListener('click', () => {
        if (pageNum <= 1) {
            return;
        }
        pageNum--;
        queueRenderPage(pageNum);
    });

    // Next Page handler
    document.getElementById('next-page').addEventListener('click', () => {
        if (pageNum >= pdfDoc.numPages) {
            return;
        }
        pageNum++;
        queueRenderPage(pageNum);
    });

    // Zoom In handler
    document.getElementById('zoom-in').addEventListener('click', () => {
        if (scale >= 3.0) return;
        scale += 0.2;
        queueRenderPage(pageNum);
    });

    // Zoom Out handler
    document.getElementById('zoom-out').addEventListener('click', () => {
        if (scale <= 0.6) return;
        scale -= 0.2;
        queueRenderPage(pageNum);
    });

    // Fit to Width layout handler
    const canvasWrapper = document.querySelector(".pdf-canvas-wrapper");
    function fitToWidth() {
        if (!pdfDoc || !canvasWrapper) return;
        pdfDoc.getPage(pageNum).then((page) => {
            const viewport1 = page.getViewport({ scale: 1.0 });
            const wrapperWidth = canvasWrapper.clientWidth;
            // Subtract offset padding/border for a safe fit
            const targetWidth = wrapperWidth - 16;
            scale = targetWidth / viewport1.width;
            queueRenderPage(pageNum);
        });
    }

    const fitWidthBtn = document.getElementById("pdf-fit-width-btn");
    if (fitWidthBtn) {
        fitWidthBtn.addEventListener("click", fitToWidth);
    }

    // Load Document
    pdfjsLib.getDocument(pdfUrl).promise.then((pdfDoc_) => {
        pdfDoc = pdfDoc_;
        document.getElementById('page-count').textContent = pdfDoc.numPages;
        
        // Hide loader and show canvas
        document.getElementById('pdf-loader').style.display = 'none';
        canvas.style.display = 'block';
        
        // Automatically fit PDF to canvas wrapper width on load
        fitToWidth();
    }).catch((err) => {
        console.error("Error loading PDF document:", err);
        document.getElementById('pdf-loader').innerHTML = `
            <div style="color: #ef4444; padding: 2rem; text-align: center;">
                <p>⚠️ Error loading document. Please verify your authentication session or contact the school office.</p>
                <p style="font-size: 0.8rem; margin-top: 0.5rem; color: #94a3b8;">${err.message}</p>
            </div>
        `;
    });

    // --- SECURITY CONTROLS (Comprehensive Screenshot & Capture Protection) ---

    const detailPageContainer = document.querySelector(".detail-page-container");
    const securityLockTitle = document.getElementById("security-lock-title");
    const securityLockText = document.getElementById("security-lock-text");
    const securityLockMeta = document.getElementById("security-lock-meta");
    const securityResumeBtn = document.getElementById("security-resume-btn");
    const pdfCanvasWrapper = document.querySelector(".pdf-canvas-wrapper");

    // Detect mobile/touch device
    const isMobileDevice = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent)
        || ('ontouchstart' in window)
        || (navigator.maxTouchPoints > 0);

    const securityMessages = {
        screenshot: {
            title: "Couldn't save screenshot",
            text: "Taking screenshots isn't allowed by the app or your organization.",
            meta: "Security policy enforced"
        },
        hidden: {
            title: "Viewing Paused",
            text: "This protected paper is hidden while the window or app is not active. Tap below to resume.",
            meta: "Secure viewing paused"
        },
        default: {
            title: "Couldn't save screenshot",
            text: "Taking screenshots isn't allowed by the app or your organization.",
            meta: "Secure viewing mode active"
        }
    };

    let isBlackedOut = false;
    let savedCanvasData = null;
    let isAlertActive = false;

    const applySecurityMessage = (mode) => {
        const nextMessage = securityMessages[mode] || securityMessages.default;
        if (securityLockTitle) securityLockTitle.textContent = nextMessage.title;
        if (securityLockText) securityLockText.textContent = nextMessage.text;
        if (securityLockMeta) securityLockMeta.textContent = nextMessage.meta;
    };

    // Wipe and hide canvas content instantly (sub-millisecond execution)
    const destroyCanvasContent = () => {
        // 1. Hide canvas & wrapper instantly in DOM
        if (canvas) {
            canvas.style.display = "none";
        }
        if (pdfCanvasWrapper) {
            pdfCanvasWrapper.style.display = "none";
        }
        if (detailPageContainer) {
            detailPageContainer.classList.add("is-blackout");
        }
        // 2. Clear canvas pixels to black
        if (canvas && ctx) {
            ctx.fillStyle = "#000000";
            ctx.fillRect(0, 0, canvas.width, canvas.height);
        }
    };

    // Restore canvas content from PDF.js re-render
    const restoreCanvasContent = () => {
        if (canvas) {
            canvas.style.display = "block";
        }
        if (pdfCanvasWrapper) {
            pdfCanvasWrapper.style.display = "block";
        }
        if (pdfDoc) {
            queueRenderPage(pageNum);
        }
    };

    const showAndroidScreenshotToast = () => {
        let toast = document.getElementById("android-screenshot-toast");
        if (!toast) {
            toast = document.createElement("div");
            toast.id = "android-screenshot-toast";
            toast.style.cssText = `
                position: fixed;
                bottom: 30px;
                left: 50%;
                transform: translateX(-50%);
                background: #18181b;
                color: #ffffff;
                padding: 14px 20px;
                border-radius: 14px;
                box-shadow: 0 10px 40px rgba(0, 0, 0, 0.75);
                font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                z-index: 999999;
                max-width: 92%;
                width: 380px;
                border-left: 4px solid #ef4444;
                pointer-events: none;
                transition: opacity 0.3s ease, transform 0.3s ease;
                opacity: 0;
            `;
            toast.innerHTML = `
                <div style="font-weight: 700; font-size: 15px; margin-bottom: 3px; color: #ffffff;">Couldn't save screenshot</div>
                <div style="font-size: 13px; color: #d1d5db; line-height: 1.4;">Taking screenshots isn't allowed by the app or your organization.</div>
            `;
            document.body.appendChild(toast);
        }

        toast.style.opacity = "1";
        toast.style.transform = "translateX(-50%) translateY(0)";

        setTimeout(() => {
            toast.style.opacity = "0";
            toast.style.transform = "translateX(-50%) translateY(12px)";
        }, 4500);
    };

    const activateBlackout = (mode = "default") => {
        if (!isBlackedOut) {
            isBlackedOut = true;
            applySecurityMessage(mode);
            destroyCanvasContent();
            detailPageContainer?.classList.add("is-blackout");
            if (securityResumeBtn) securityResumeBtn.style.display = "inline-block";
        }
    };

    const deactivateBlackout = () => {
        if (!isBlackedOut) return;
        isBlackedOut = false;
        detailPageContainer?.classList.remove("is-blackout");
        if (securityResumeBtn) securityResumeBtn.style.display = "none";
        applySecurityMessage("default");
        restoreCanvasContent();
    };

    // Resume button handler (user must actively click to resume)
    if (securityResumeBtn) {
        securityResumeBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            deactivateBlackout();
        });
    }

    // ═══════════════════════════════════════════
    // VISIBILITY & FOCUS PROTECTION (PC + Mobile)
    // ═══════════════════════════════════════════

    // When user switches tabs/apps or hides window
    document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
            activateBlackout("hidden");
        }
    });

    // Window blur (user clicks outside browser, alt-tabs, app switch)
    window.addEventListener("blur", () => {
        activateBlackout("hidden");
    });

    // ═══════════════════════════════════════════
    // KEYBOARD SCREENSHOT DETECTION (PC + Mobile Keyboards)
    // ═══════════════════════════════════════════

    window.addEventListener("keyup", (e) => {
        // PrintScreen / Snapshot key
        if (e.key === "PrintScreen" || e.key === "Snapshot") {
            activateBlackout("screenshot");
            try {
                navigator.clipboard.writeText("Screenshot disabled — Lundayang Marians").catch(() => {});
            } catch (err) { /* clipboard API may not be available */ }
        }
    });

    window.addEventListener("keydown", (e) => {
        const isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0;
        const metaKey = isMac ? e.metaKey : e.ctrlKey;

        // Intercept Android hardware volume buttons (Volume Down + Power screenshot combination)
        if (['AudioVolumeDown', 'AudioVolumeUp', 'VolumeDown', 'VolumeUp', 'AudioVolumeMute'].includes(e.key) ||
            ['VolumeDown', 'VolumeUp', 'VolumeMute'].includes(e.code)) {
            activateBlackout("screenshot");
            return;
        }

        // PrintScreen key
        if (e.key === "PrintScreen" || e.key === "Snapshot") {
            e.preventDefault();
            activateBlackout("screenshot");
            return;
        }

        // Win + Shift + S or Cmd + Shift + 3/4/5 (Mac screenshot tools)
        if (e.shiftKey && (e.metaKey || e.ctrlKey) && ['s', 'S', '3', '4', '5'].includes(e.key)) {
            e.preventDefault();
            activateBlackout("screenshot");
            return;
        }

        // Prevent Ctrl/Cmd + S (Save), P (Print), C (Copy), A (Select All)
        if (metaKey && ['s','p','c','a','S','P','C','A'].includes(e.key)) {
            e.preventDefault();
            activateBlackout("screenshot");
            return;
        }

        // Ctrl + Shift + I (DevTools)
        if (metaKey && e.shiftKey && ['i', 'I', 'j', 'J', 'c', 'C'].includes(e.key)) {
            e.preventDefault();
            activateBlackout("screenshot");
            return;
        }

        // F12 (DevTools)
        if (e.key === 'F12') {
            e.preventDefault();
            activateBlackout("screenshot");
            return;
        }

        // Ctrl + U (View Source)
        if (metaKey && (e.key === 'u' || e.key === 'U')) {
            e.preventDefault();
            activateBlackout("screenshot");
            return;
        }
    });

    // ═══════════════════════════════════════════
    // MOBILE-SPECIFIC PROTECTIONS
    // ═══════════════════════════════════════════

    if (isMobileDevice) {
        // Multi-touch detection: 2+ or 3+ fingers touch simultaneously (gesture screenshots)
        document.addEventListener("touchstart", (e) => {
            if (e.touches.length >= 2) {
                activateBlackout("screenshot");
            }
        }, { passive: true });

        document.addEventListener("touchmove", (e) => {
            if (e.touches.length >= 2) {
                activateBlackout("screenshot");
            }
        }, { passive: true });

        // Touch cancel fires when OS takes over for screenshot / control center / app switcher
        document.addEventListener("touchcancel", () => {
            activateBlackout("screenshot");
        }, { passive: true });

        // Prevent long press context menu (image save) on mobile
        document.addEventListener("contextmenu", (e) => {
            e.preventDefault();
            activateBlackout("screenshot");
            return false;
        });

        // Detect rapid resize/orientation events (some Android devices trigger resize during screenshot animation)
        let lastWidth = window.innerWidth;
        let lastHeight = window.innerHeight;
        let resizeDebounceTimer = null;

        window.addEventListener("resize", () => {
            const widthDiff = Math.abs(window.innerWidth - lastWidth);
            const heightDiff = Math.abs(window.innerHeight - lastHeight);

            if (widthDiff === 0 && heightDiff > 0 && heightDiff < 10) {
                if (resizeDebounceTimer) clearTimeout(resizeDebounceTimer);
                resizeDebounceTimer = setTimeout(() => {
                    if (!document.hidden && document.activeElement?.tagName !== "INPUT"
                        && document.activeElement?.tagName !== "TEXTAREA") {
                        activateBlackout("screenshot");
                    }
                }, 100);
            }

            lastWidth = window.innerWidth;
            lastHeight = window.innerHeight;
        });
    }

    // ═══════════════════════════════════════════
    // GENERAL PROTECTIONS (PC + Mobile)
    // ═══════════════════════════════════════════

    // 1. Disable Right-click context menu inside PDF container
    const pdfContainer = document.querySelector(".pdf-viewer-container");
    if (pdfContainer) {
        pdfContainer.addEventListener('contextmenu', e => e.preventDefault());
    }

    // 2. Disable right-click globally on the detail page
    detailPageContainer?.addEventListener('contextmenu', e => e.preventDefault());

    // 3. Disable Drag/Drop of contents
    window.addEventListener('dragstart', e => e.preventDefault());

    // 4. Prevent text selection via CSS is already applied, but also via JS
    document.addEventListener('selectstart', (e) => {
        if (detailPageContainer?.contains(e.target)) {
            e.preventDefault();
        }
    });

    // 5. Detect DevTools open via debugger timing (basic)
    let devToolsCheckInterval = null;
    const checkDevTools = () => {
        const start = performance.now();
        debugger; // This pauses execution if DevTools is open
        const end = performance.now();
        if (end - start > 100) {
            activateBlackout("screenshot");
            if (devToolsCheckInterval) {
                clearInterval(devToolsCheckInterval);
                devToolsCheckInterval = null;
            }
        }
    };
    // Uncomment the line below to enable DevTools detection (causes debugger pauses):
    // devToolsCheckInterval = setInterval(checkDevTools, 2000);

    // --- FULLSCREEN VIEW CONTROLS ---
    const fullscreenBtn = document.getElementById("pdf-fullscreen-btn");
    const mainViewport = document.getElementById("pdf-main-viewport");

    if (fullscreenBtn && mainViewport) {
        fullscreenBtn.addEventListener("click", () => {
            if (!document.fullscreenElement) {
                mainViewport.requestFullscreen().catch(err => {
                    alert(`Error enabling fullscreen: ${err.message}`);
                });
            } else {
                document.exitFullscreen();
            }
        });

        // Update icon and title when fullscreen state changes
        document.addEventListener("fullscreenchange", () => {
            if (document.fullscreenElement === mainViewport) {
                fullscreenBtn.setAttribute("title", "Exit Fullscreen");
                fullscreenBtn.innerHTML = '<i data-lucide="minimize" style="width: 16px; height: 16px; display: inline-block; vertical-align: middle;"></i>';
            } else {
                fullscreenBtn.setAttribute("title", "Fullscreen");
                fullscreenBtn.innerHTML = '<i data-lucide="maximize" style="width: 16px; height: 16px; display: inline-block; vertical-align: middle;"></i>';
            }
            if (window.lucide) {
                window.lucide.createIcons();
            }
        });
    }

    // Automatically re-scale PDF width on screen/window size changes
    window.addEventListener("resize", () => {
        if (pdfDoc) {
            fitToWidth();
        }
    });
});
