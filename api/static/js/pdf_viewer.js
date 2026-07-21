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
                // Apply dynamic security watermark directly to canvas matrix
                drawCanvasWatermark(ctx, canvas.width, canvas.height);
                
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

    // Dynamic anti-screenshot canvas watermark
    function drawCanvasWatermark(context, width, height) {
        context.save();
        context.rotate(-25 * Math.PI / 180);
        context.font = 'bold 15px sans-serif';
        context.fillStyle = 'rgba(0, 32, 96, 0.16)';
        context.textAlign = 'center';
        
        const watermarkText = 'CONFIDENTIAL • LUNDAYANG MARIANS • PROTECTED RESEARCH';
        const stepX = 340;
        const stepY = 110;

        for (let y = -height; y < height * 2; y += stepY) {
            for (let x = -width; x < width * 2; x += stepX) {
                context.fillText(watermarkText, x, y);
            }
        }
        context.restore();
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

    // --- SECURITY & SCREENSHOT PROTECTION CONTROLS ---

    const detailPageContainer = document.querySelector(".detail-page-container");
    const securityLockTitle = document.getElementById("security-lock-title");
    const securityLockText = document.getElementById("security-lock-text");
    const securityLockMeta = document.getElementById("security-lock-meta");

    const securityMessages = {
        screenshot: {
            title: "Screenshot unavailable",
            text: "A screenshot attempt was detected. The viewer has locked this page to protect the research document.",
            meta: "Capture protection engaged"
        },
        hidden: {
            title: "Viewing paused",
            text: "This protected paper is hidden while the window is not active. Return to the tab to continue reading.",
            meta: "Secure viewing paused"
        },
        default: {
            title: "Security warning",
            text: "This protected paper is locked by the viewer if a capture attempt, focus loss, or window switch is detected.",
            meta: "Secure viewing mode active"
        }
    };

    const applySecurityMessage = (mode) => {
        const nextMessage = securityMessages[mode] || securityMessages.default;
        if (securityLockTitle) securityLockTitle.textContent = nextMessage.title;
        if (securityLockText) securityLockText.textContent = nextMessage.text;
        if (securityLockMeta) securityLockMeta.textContent = nextMessage.meta;
    };

    const activateBlackout = (mode = "default") => {
        applySecurityMessage(mode);
        detailPageContainer?.classList.add("is-blackout");
    };

    const deactivateBlackout = () => {
        detailPageContainer?.classList.remove("is-blackout");
        applySecurityMessage("default");
    };

    // 1. Blackout on window blur / tab switch / mobile pagehide / app switcher
    window.addEventListener("blur", () => activateBlackout("hidden"));
    window.addEventListener("focus", deactivateBlackout);
    window.addEventListener("pagehide", () => activateBlackout("hidden"));
    window.addEventListener("pageshow", deactivateBlackout);
    document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
            activateBlackout("hidden");
        } else {
            deactivateBlackout();
        }
    });

    // 2. Blackout on desktop screenshot shortcut keys (PrintScreen / keyCode 44, Win+Shift+S, Cmd+Shift+3/4/5)
    document.addEventListener("keyup", function (e) {
        var keyCode = e.keyCode ? e.keyCode : e.which;
        if (keyCode == 44 || e.key === "PrintScreen") {
            // Hide container temporarily and show security blackout warning
            activateBlackout("screenshot");
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText("Protected Document").catch(() => {});
            }
            alert("🔒 Screenshots are disabled on this site.");
            window.setTimeout(deactivateBlackout, 2000);
        }
    });

    window.addEventListener("keydown", (event) => {
        const keyCode = event.keyCode ? event.keyCode : event.which;
        // PrintScreen Key
        if (event.key === "PrintScreen" || keyCode === 44) {
            activateBlackout("screenshot");
            window.setTimeout(deactivateBlackout, 3000);
        }

        const isMac = navigator.platform.toUpperCase().indexOf("MAC") >= 0;
        const metaKey = isMac ? event.metaKey : event.ctrlKey;

        // Windows Snipping Tool (Win + Shift + S) or Mac Screenshot (Cmd + Shift + 3 / 4 / 5)
        if (event.shiftKey && (event.key === "S" || event.key === "s" || event.code === "KeyS")) {
            activateBlackout("screenshot");
            window.setTimeout(deactivateBlackout, 3000);
        }

        // Prevent Ctrl/Cmd + P (Print), S (Save), C (Copy), A (Select All)
        if (metaKey && (event.key === 's' || event.key === 'p' || event.key === 'c' || event.key === 'a' || event.key === 'S' || event.key === 'P' || event.key === 'C' || event.key === 'A')) {
            event.preventDefault();
            activateBlackout("screenshot");
            alert("🔒 Downloading, printing, or copying research text is restricted to preserve intellectual property.");
            window.setTimeout(deactivateBlackout, 2000);
        }
    });

    // 3. Mobile Screenshot & Gesture Protection
    // Multi-finger touches (e.g. 3-finger screenshot gesture on mobile OS) or system touch cancel
    window.addEventListener("touchstart", (e) => {
        if (e.touches && e.touches.length > 1) {
            activateBlackout("screenshot");
            window.setTimeout(deactivateBlackout, 2000);
        }
    }, { passive: true });

    // When physical hardware buttons (Power + Vol Down) or screen capture overlay triggers on mobile, iOS/Android fires touchcancel
    window.addEventListener("touchcancel", () => {
        activateBlackout("screenshot");
        window.setTimeout(deactivateBlackout, 2500);
    });

    // Mobile orientation & screen capture dimension change protection
    window.addEventListener("orientationchange", () => {
        activateBlackout("hidden");
        window.setTimeout(deactivateBlackout, 1500);
    });

    // 4. Blackout during Print preview trigger
    window.addEventListener("beforeprint", () => activateBlackout("screenshot"));
    window.addEventListener("afterprint", deactivateBlackout);

    // 5. Disable Right-click context menu, selection callouts, and multi-touch gestures inside PDF container
    const pdfContainer = document.querySelector(".pdf-viewer-container");
    if (pdfContainer) {
        pdfContainer.addEventListener('contextmenu', e => e.preventDefault());
        pdfContainer.addEventListener('touchstart', e => {
            if (e.touches && e.touches.length > 1) {
                e.preventDefault();
                activateBlackout("screenshot");
            }
        }, { passive: false });
    }

    // 6. Disable Drag/Drop of contents
    window.addEventListener('dragstart', e => e.preventDefault());

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
