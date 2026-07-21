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
            title: "Screenshot Blocked",
            text: "A screenshot or screen capture attempt was detected. The document content has been hidden to protect this research paper.",
            meta: "Capture protection engaged"
        },
        hidden: {
            title: "Viewing Paused",
            text: "This protected paper is hidden while the window or app is not active. Tap or click below to resume viewing.",
            meta: "Secure viewing paused"
        },
        default: {
            title: "Security Warning",
            text: "This protected paper is locked by the viewer if a capture attempt, focus loss, or window switch is detected.",
            meta: "Secure viewing mode active"
        }
    };

    let isBlackedOut = false;
    let savedCanvasData = null;

    const applySecurityMessage = (mode) => {
        const nextMessage = securityMessages[mode] || securityMessages.default;
        if (securityLockTitle) securityLockTitle.textContent = nextMessage.title;
        if (securityLockText) securityLockText.textContent = nextMessage.text;
        if (securityLockMeta) securityLockMeta.textContent = nextMessage.meta;
    };

    // Wipe the canvas content to pure black so even OS-level screenshots capture nothing
    const destroyCanvasContent = () => {
        if (canvas && ctx) {
            // Save current content so we can restore later
            try {
                if (!savedCanvasData && canvas.width > 0 && canvas.height > 0) {
                    savedCanvasData = ctx.getImageData(0, 0, canvas.width, canvas.height);
                }
            } catch (e) { /* ignore if canvas is tainted */ }
            // Fill with black
            ctx.fillStyle = "#000000";
            ctx.fillRect(0, 0, canvas.width, canvas.height);
        }
        // Also hide the wrapper entirely
        if (pdfCanvasWrapper) {
            pdfCanvasWrapper.style.visibility = "hidden";
        }
    };

    // Restore canvas content from saved data or re-render
    const restoreCanvasContent = () => {
        if (pdfCanvasWrapper) {
            pdfCanvasWrapper.style.visibility = "visible";
        }
        if (savedCanvasData && canvas && ctx) {
            try {
                ctx.putImageData(savedCanvasData, 0, 0);
                savedCanvasData = null;
            } catch (e) {
                // Fallback: re-render the current page
                if (pdfDoc) {
                    savedCanvasData = null;
                    queueRenderPage(pageNum);
                }
            }
        } else if (pdfDoc) {
            // Fallback: re-render
            queueRenderPage(pageNum);
        }
    };

    const activateBlackout = (mode = "default") => {
        if (isBlackedOut) return; // Prevent double-activation
        isBlackedOut = true;
        applySecurityMessage(mode);
        destroyCanvasContent();
        detailPageContainer?.classList.add("is-blackout");
        if (securityResumeBtn) securityResumeBtn.style.display = "inline-block";
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

    // When user switches tabs/apps, immediately black out
    document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
            activateBlackout("hidden");
        }
        // Do NOT auto-deactivate — user must click Resume
    });

    // Window blur (user clicks outside browser, alt-tabs, etc.)
    window.addEventListener("blur", () => {
        activateBlackout("hidden");
    });

    // On mobile, pagehide fires when switching apps
    window.addEventListener("pagehide", () => {
        activateBlackout("hidden");
    });

    // ═══════════════════════════════════════════
    // KEYBOARD SCREENSHOT DETECTION (PC)
    // ═══════════════════════════════════════════

    window.addEventListener("keyup", (e) => {
        // PrintScreen key (fires on keyup, not keydown on many browsers)
        if (e.key === "PrintScreen") {
            activateBlackout("screenshot");
            // Also try to overwrite clipboard with blank
            try {
                navigator.clipboard.writeText("Screenshot disabled — Lundayang Marians").catch(() => {});
            } catch (err) { /* clipboard API may not be available */ }
        }
    });

    window.addEventListener("keydown", (e) => {
        const isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0;
        const metaKey = isMac ? e.metaKey : e.ctrlKey;

        // PrintScreen key
        if (e.key === "PrintScreen") {
            e.preventDefault();
            activateBlackout("screenshot");
            return;
        }

        // Win + Shift + S (Windows Snipping Tool) — detected as Meta + Shift + S
        if (e.shiftKey && (e.metaKey || e.ctrlKey) && (e.key === 's' || e.key === 'S')) {
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
        if (metaKey && e.shiftKey && (e.key === 'i' || e.key === 'I')) {
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
        // Multi-touch detection: some phones use volume+power combo
        // which can sometimes be detected via rapid touch events
        let touchCount = 0;
        let touchTimer = null;

        document.addEventListener("touchstart", (e) => {
            // If 3+ fingers touch simultaneously, likely a gesture screenshot
            if (e.touches.length >= 3) {
                activateBlackout("screenshot");
            }
        }, { passive: true });

        // Detect rapid resize events (some phones trigger resize during screenshot)
        let lastWidth = window.innerWidth;
        let lastHeight = window.innerHeight;
        let resizeDebounceTimer = null;

        window.addEventListener("resize", () => {
            const widthDiff = Math.abs(window.innerWidth - lastWidth);
            const heightDiff = Math.abs(window.innerHeight - lastHeight);

            // Tiny resize changes (< 5px) that happen rapidly can indicate
            // screenshot animation on some Android devices
            if (widthDiff === 0 && heightDiff > 0 && heightDiff < 10) {
                if (resizeDebounceTimer) clearTimeout(resizeDebounceTimer);
                resizeDebounceTimer = setTimeout(() => {
                    // Only trigger if document was visible (not a keyboard resize)
                    if (!document.hidden && document.activeElement?.tagName !== "INPUT"
                        && document.activeElement?.tagName !== "TEXTAREA") {
                        activateBlackout("screenshot");
                    }
                }, 100);
            }

            lastWidth = window.innerWidth;
            lastHeight = window.innerHeight;
        });

        // Touch cancel can fire when the OS takes over (screenshot, app switch)
        document.addEventListener("touchcancel", () => {
            activateBlackout("hidden");
        }, { passive: true });
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
