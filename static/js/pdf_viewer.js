// Secure Multi-Page Canvas-Based Scrollable PDF Viewer using PDF.js

// Helper function to fetch & cache PDF ArrayBuffers in browser CacheStorage
// Progressive Streaming PDF Document Loader using PDF.js
window.getCachedPdfDocument = async function(pdfUrl) {
    const pdfjsLib = window['pdfjs-dist/build/pdf'];
    if (!pdfjsLib) throw new Error("PDF.js library not loaded");

    // Pass the URL directly to PDF.js with Range request streaming enabled
    // This allows PDF.js to fetch only the first chunk (~64KB) and display Page 1 in <1s
    // without blocking or downloading the entire multi-megabyte document upfront!
    const loadingTask = pdfjsLib.getDocument({
        url: pdfUrl,
        cMapUrl: 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.4.120/cmaps/',
        cMapPacked: true,
        enableXfa: false,
        disableAutoFetch: false,
        disableStream: false,
        rangeChunkSize: 65536
    });

    return loadingTask.promise;
};

document.addEventListener("DOMContentLoaded", () => {
    const pagesContainer = document.getElementById("pdf-pages-container");
    const canvasWrapper = document.querySelector(".pdf-canvas-wrapper");
    if (!pagesContainer || !canvasWrapper) return;

    const paperId = pagesContainer.getAttribute("data-paper-id");
    if (!paperId) return;

    const pdfUrl = `/api/paper/${paperId}/pdf`;
    
    // PDFJS initialization
    const pdfjsLib = window['pdfjs-dist/build/pdf'];
    if (!pdfjsLib) return;
    pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.4.120/pdf.worker.min.js';

    let pdfDoc = null;
    let totalPages = 0;
    let currentPageNum = 1;
    let scale = 1.0;
    let basePageWidth = 600;
    let basePageHeight = 800;
    let pageStates = {}; // pageNum -> { rendered: bool, rendering: bool, renderTask: null, textLayerTask: null, renderedScale: 0 }
    let intersectionObserver = null;

    // Burns a tiled diagonal watermark directly into the canvas pixels
    // so ANY screenshot captures the watermark
    function burnWatermarkOnCanvas(canvas, ctx) {
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

    // --- AUTO-OCR OVERLAY ENGINE FOR SCANNED PDFS (Tesseract.js) ---
    let ocrWorkerPromise = null;
    let ocrJobQueue = Promise.resolve();
    const pageOcrCache = {}; // pageNum -> { baseWidth, baseHeight, lines, words }

    async function loadTesseractScript() {
        if (window.Tesseract) return true;
        return new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = 'https://cdn.jsdelivr.net/npm/tesseract.js@5/dist/tesseract.min.js';
            script.async = true;
            script.onload = () => resolve(true);
            script.onerror = () => reject(new Error("Failed to load Tesseract.js"));
            document.head.appendChild(script);
        });
    }

    async function getOcrWorker() {
        if (!window.Tesseract) {
            try {
                await loadTesseractScript();
            } catch (err) {
                console.warn("[Auto-OCR] Could not load Tesseract library:", err);
                return null;
            }
        }
        if (!ocrWorkerPromise) {
            ocrWorkerPromise = (async () => {
                try {
                    const worker = await window.Tesseract.createWorker('eng');
                    return worker;
                } catch (err) {
                    console.error("[Auto-OCR] Failed to initialize worker:", err);
                    ocrWorkerPromise = null;
                    return null;
                }
            })();
        }
        return ocrWorkerPromise;
    }

    function showOcrStatus(pageNum, status, message) {
        const pageContainer = document.getElementById(`page-container-${pageNum}`);
        if (!pageContainer) return;

        let pill = pageContainer.querySelector('.pdf-ocr-pill');
        if (!pill) {
            pill = document.createElement('div');
            pill.className = 'pdf-ocr-pill';
            pageContainer.appendChild(pill);
        }

        pill.classList.remove('fade-out', 'ready');
        if (status === 'processing') {
            pill.innerHTML = `<div class="ocr-spin"></div><span>${message || 'Recognizing text...'}</span>`;
        } else if (status === 'ready') {
            pill.classList.add('ready');
            pill.innerHTML = `<i data-lucide="check" style="width: 12px; height: 12px; display: inline-block; vertical-align: middle;"></i><span>${message || 'Text selectable'}</span>`;
            if (window.lucide) window.lucide.createIcons();
            setTimeout(() => {
                pill.classList.add('fade-out');
                setTimeout(() => pill.remove(), 600);
            }, 3000);
        } else if (status === 'error') {
            pill.remove();
        }
    }

    function renderOcrTextLayer(pageNum, textLayerDiv, viewport) {
        const cached = pageOcrCache[pageNum];
        if (!cached || !textLayerDiv) return;

        textLayerDiv.innerHTML = '';
        textLayerDiv.style.width = `${viewport.width}px`;
        textLayerDiv.style.height = `${viewport.height}px`;

        const scaleX = viewport.width / cached.baseWidth;
        const scaleY = viewport.height / cached.baseHeight;

        if (cached.lines && cached.lines.length > 0) {
            cached.lines.forEach(line => {
                const lineWords = line.words && line.words.length > 0 ? line.words : null;
                if (lineWords) {
                    lineWords.forEach(word => {
                        if (!word.text || !word.bbox) return;
                        const wLeft = word.bbox.x0 * scaleX;
                        const wTop = word.bbox.y0 * scaleY;
                        const wWidth = Math.max((word.bbox.x1 - word.bbox.x0) * scaleX, 4);
                        const wHeight = Math.max((word.bbox.y1 - word.bbox.y0) * scaleY, 8);
                        const fontSize = Math.max(wHeight * 0.88, 7);

                        const span = document.createElement('span');
                        span.textContent = word.text + ' ';
                        span.style.left = `${wLeft}px`;
                        span.style.top = `${wTop}px`;
                        span.style.width = `${wWidth}px`;
                        span.style.height = `${wHeight}px`;
                        span.style.fontSize = `${fontSize}px`;
                        span.style.lineHeight = `${wHeight}px`;
                        span.style.position = 'absolute';
                        span.style.color = 'transparent';
                        span.style.cursor = 'text';
                        span.style.whiteSpace = 'pre';
                        span.style.userSelect = 'text';
                        span.style.webkitUserSelect = 'text';

                        textLayerDiv.appendChild(span);
                    });
                    const br = document.createElement('br');
                    textLayerDiv.appendChild(br);
                } else if (line.text && line.bbox) {
                    const lLeft = line.bbox.x0 * scaleX;
                    const lTop = line.bbox.y0 * scaleY;
                    const lWidth = Math.max((line.bbox.x1 - line.bbox.x0) * scaleX, 10);
                    const lHeight = Math.max((line.bbox.y1 - line.bbox.y0) * scaleY, 10);
                    const fontSize = Math.max(lHeight * 0.85, 8);

                    const span = document.createElement('span');
                    span.textContent = line.text;
                    span.style.left = `${lLeft}px`;
                    span.style.top = `${lTop}px`;
                    span.style.width = `${lWidth}px`;
                    span.style.height = `${lHeight}px`;
                    span.style.fontSize = `${fontSize}px`;
                    span.style.lineHeight = `${lHeight}px`;
                    span.style.position = 'absolute';
                    span.style.color = 'transparent';
                    span.style.cursor = 'text';
                    span.style.whiteSpace = 'pre';
                    span.style.userSelect = 'text';
                    span.style.webkitUserSelect = 'text';

                    textLayerDiv.appendChild(span);
                    textLayerDiv.appendChild(document.createElement('br'));
                }
            });
        } else if (cached.words && cached.words.length > 0) {
            cached.words.forEach(word => {
                if (!word.text || !word.bbox) return;
                const wLeft = word.bbox.x0 * scaleX;
                const wTop = word.bbox.y0 * scaleY;
                const wWidth = Math.max((word.bbox.x1 - word.bbox.x0) * scaleX, 4);
                const wHeight = Math.max((word.bbox.y1 - word.bbox.y0) * scaleY, 8);
                const fontSize = Math.max(wHeight * 0.88, 7);

                const span = document.createElement('span');
                span.textContent = word.text + ' ';
                span.style.left = `${wLeft}px`;
                span.style.top = `${wTop}px`;
                span.style.width = `${wWidth}px`;
                span.style.height = `${wHeight}px`;
                span.style.fontSize = `${fontSize}px`;
                span.style.lineHeight = `${wHeight}px`;
                span.style.position = 'absolute';
                span.style.color = 'transparent';
                span.style.cursor = 'text';
                span.style.whiteSpace = 'pre';
                span.style.userSelect = 'text';
                span.style.webkitUserSelect = 'text';

                textLayerDiv.appendChild(span);
            });
        }
    }

    // Render a single page into its container
    async function renderPage(pageNum) {
        const state = pageStates[pageNum];
        if (!state || !pdfDoc) return;

        // Already rendered at this scale
        if (state.rendered && state.renderedScale === scale) return;

        // If currently rendering at another scale, cancel prior tasks
        if (state.rendering && state.renderTask) {
            try {
                state.renderTask.cancel();
            } catch (e) {}
        }
        if (state.textLayerTask) {
            try {
                state.textLayerTask.cancel();
            } catch (e) {}
        }

        state.rendering = true;

        const pageContainer = document.getElementById(`page-container-${pageNum}`);
        const canvas = document.getElementById(`pdf-canvas-${pageNum}`);
        const textLayerDiv = document.getElementById(`pdf-text-layer-${pageNum}`);
        const skeleton = document.getElementById(`pdf-skeleton-${pageNum}`);

        if (!pageContainer || !canvas) {
            state.rendering = false;
            return;
        }

        try {
            const page = await pdfDoc.getPage(pageNum);
            const viewport = page.getViewport({ scale: scale });

            canvas.height = viewport.height;
            canvas.width = viewport.width;

            pageContainer.style.width = `${viewport.width}px`;
            pageContainer.style.height = `${viewport.height}px`;

            const ctx = canvas.getContext('2d');
            const renderContext = {
                canvasContext: ctx,
                viewport: viewport
            };

            state.renderTask = page.render(renderContext);
            await state.renderTask.promise;

            // Check if digital text content exists on this page
            let hasDigitalText = false;
            let textContent = null;
            try {
                textContent = await page.getTextContent();
                hasDigitalText = textContent && textContent.items && textContent.items.some(item => item.str && item.str.trim().length > 0);
            } catch (tcErr) {
                console.warn(`TextContent read failed on page ${pageNum}:`, tcErr);
            }

            if (hasDigitalText) {
                // Regular digital PDF: burn watermark and render native PDF.js text layer
                burnWatermarkOnCanvas(canvas, ctx);

                if (textLayerDiv) {
                    textLayerDiv.innerHTML = '';
                    textLayerDiv.style.width = `${viewport.width}px`;
                    textLayerDiv.style.height = `${viewport.height}px`;
                    textLayerDiv.style.setProperty('--scale-factor', viewport.scale);

                    try {
                        if (pdfjsLib.renderTextLayer) {
                            state.textLayerTask = pdfjsLib.renderTextLayer({
                                textContentSource: textContent,
                                textContent: textContent,
                                container: textLayerDiv,
                                viewport: viewport,
                                textDivs: []
                            });
                        }
                    } catch (tlErr) {
                        console.warn(`Text layer error on page ${pageNum}:`, tlErr);
                    }
                }
            } else {
                // Scanned PDF page detected (0 digital text items)
                // 1. Capture clean offscreen canvas snapshot before watermarking (if not already cached)
                let cleanCanvas = null;
                if (!pageOcrCache[pageNum]) {
                    cleanCanvas = document.createElement('canvas');
                    cleanCanvas.width = canvas.width;
                    cleanCanvas.height = canvas.height;
                    const cleanCtx = cleanCanvas.getContext('2d');
                    cleanCtx.drawImage(canvas, 0, 0);
                }

                // 2. Burn watermark onto the visible screen canvas
                burnWatermarkOnCanvas(canvas, ctx);

                // 3. Render OCR text layer from cache or queue worker recognition
                if (pageOcrCache[pageNum]) {
                    renderOcrTextLayer(pageNum, textLayerDiv, viewport);
                } else if (cleanCanvas) {
                    showOcrStatus(pageNum, 'processing', 'Recognizing text...');
                    ocrJobQueue = ocrJobQueue.then(async () => {
                        try {
                            const worker = await getOcrWorker();
                            if (!worker) {
                                showOcrStatus(pageNum, 'error');
                                return;
                            }
                            const res = await worker.recognize(cleanCanvas);
                            const data = res && res.data ? res.data : null;
                            if (data && ((data.words && data.words.length > 0) || (data.lines && data.lines.length > 0))) {
                                pageOcrCache[pageNum] = {
                                    baseWidth: cleanCanvas.width,
                                    baseHeight: cleanCanvas.height,
                                    lines: (data.lines || []).map(l => ({
                                        text: l.text,
                                        bbox: l.bbox,
                                        words: (l.words || []).map(w => ({
                                            text: w.text,
                                            bbox: w.bbox
                                        }))
                                    })),
                                    words: (data.words || []).map(w => ({
                                        text: w.text,
                                        bbox: w.bbox
                                    }))
                                };

                                const currentDiv = document.getElementById(`pdf-text-layer-${pageNum}`);
                                if (currentDiv && pdfDoc) {
                                    const currPage = await pdfDoc.getPage(pageNum);
                                    const currViewport = currPage.getViewport({ scale: scale });
                                    renderOcrTextLayer(pageNum, currentDiv, currViewport);
                                }
                                showOcrStatus(pageNum, 'ready', 'Text selectable');
                            } else {
                                showOcrStatus(pageNum, 'error');
                            }
                        } catch (err) {
                            console.warn(`[Auto-OCR] Recognition error on page ${pageNum}:`, err);
                            showOcrStatus(pageNum, 'error');
                        }
                    });
                }
            }

            // Hide placeholder skeleton
            if (skeleton) {
                skeleton.style.display = 'none';
            }

            state.rendered = true;
            state.rendering = false;
            state.renderedScale = scale;
            state.renderTask = null;
        } catch (err) {
            if (err && err.name === 'RenderingCancelledException') {
                return;
            }
            console.error(`Error rendering page ${pageNum}:`, err);
            state.rendering = false;
        }
    }

    // Setup IntersectionObserver for lazy page rendering
    function initObserver() {
        if (intersectionObserver) {
            intersectionObserver.disconnect();
        }

        intersectionObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                const pageNum = parseInt(entry.target.getAttribute('data-page-number'), 10);
                if (entry.isIntersecting && pageNum) {
                    renderPage(pageNum);
                }
            });
        }, {
            root: canvasWrapper,
            rootMargin: '450px 0px' // Preload pages 450px before entering visible scroll area
        });

        // Observe all page container elements
        for (let num = 1; num <= totalPages; num++) {
            const pageContainer = document.getElementById(`page-container-${num}`);
            if (pageContainer) {
                intersectionObserver.observe(pageContainer);
            }
        }
    }

    // Track active page based on scroll position inside canvasWrapper
    let scrollTimeout = null;
    function handleScroll() {
        if (!totalPages) return;

        const wrapperRect = canvasWrapper.getBoundingClientRect();
        const wrapperTargetY = wrapperRect.top + (wrapperRect.height * 0.35); // Focus threshold

        let closestPage = currentPageNum;
        let minDistance = Infinity;

        for (let num = 1; num <= totalPages; num++) {
            const container = document.getElementById(`page-container-${num}`);
            if (!container) continue;

            const rect = container.getBoundingClientRect();
            const containerCenter = rect.top + (rect.height / 2);
            const distance = Math.abs(containerCenter - wrapperTargetY);

            if (distance < minDistance) {
                minDistance = distance;
                closestPage = num;
            }
        }

        if (closestPage !== currentPageNum) {
            currentPageNum = closestPage;
            const pageNumEl = document.getElementById('page-num');
            if (pageNumEl) {
                pageNumEl.textContent = currentPageNum;
            }
        }
    }

    canvasWrapper.addEventListener('scroll', () => {
        if (scrollTimeout) return;
        scrollTimeout = requestAnimationFrame(() => {
            handleScroll();
            scrollTimeout = null;
        });
    }, { passive: true });

    // Build the skeleton page placeholders for all pages
    function buildPagePlaceholders() {
        pagesContainer.innerHTML = '';
        pageStates = {};

        const scaledWidth = Math.round(basePageWidth * scale);
        const scaledHeight = Math.round(basePageHeight * scale);

        for (let num = 1; num <= totalPages; num++) {
            pageStates[num] = {
                rendered: false,
                rendering: false,
                renderTask: null,
                textLayerTask: null,
                renderedScale: 0
            };

            const pageDiv = document.createElement('div');
            pageDiv.id = `page-container-${num}`;
            pageDiv.className = 'pdf-page-container';
            pageDiv.setAttribute('data-page-number', num);
            pageDiv.style.width = `${scaledWidth}px`;
            pageDiv.style.height = `${scaledHeight}px`;

            pageDiv.innerHTML = `
                <canvas id="pdf-canvas-${num}" class="pdf-page-canvas"></canvas>
                <div id="pdf-text-layer-${num}" class="textLayer"></div>
                <div id="pdf-skeleton-${num}" class="pdf-page-skeleton">
                    <div class="spinner"></div>
                    <span>Page ${num}</span>
                </div>
            `;

            pagesContainer.appendChild(pageDiv);
        }

        initObserver();
    }

    // Apply new scale / zoom level
    function applyScale(newScale) {
        scale = Math.min(Math.max(newScale, 0.4), 3.0);

        const scaledWidth = Math.round(basePageWidth * scale);
        const scaledHeight = Math.round(basePageHeight * scale);

        for (let num = 1; num <= totalPages; num++) {
            const pageContainer = document.getElementById(`page-container-${num}`);
            const skeleton = document.getElementById(`pdf-skeleton-${num}`);
            
            if (pageContainer) {
                pageContainer.style.width = `${scaledWidth}px`;
                pageContainer.style.height = `${scaledHeight}px`;
            }

            const state = pageStates[num];
            if (state) {
                if (state.renderedScale !== scale) {
                    state.rendered = false;
                    if (skeleton) skeleton.style.display = 'flex';
                }
            }
        }

        // Immediately re-render visible pages at new scale
        const wrapperRect = canvasWrapper.getBoundingClientRect();
        for (let num = 1; num <= totalPages; num++) {
            const container = document.getElementById(`page-container-${num}`);
            if (container) {
                const rect = container.getBoundingClientRect();
                if (rect.bottom >= wrapperRect.top - 450 && rect.top <= wrapperRect.bottom + 450) {
                    renderPage(num);
                }
            }
        }
    }

    // Fit to Width layout handler
    function fitToWidth() {
        if (!pdfDoc || !canvasWrapper || !basePageWidth) return;
        const availableWidth = canvasWrapper.clientWidth - 28; // Accounting for scrollbar & padding
        if (availableWidth <= 0) return;
        const targetScale = availableWidth / basePageWidth;
        applyScale(targetScale);
    }

    const fitWidthBtn = document.getElementById("pdf-fit-width-btn");
    if (fitWidthBtn) {
        fitWidthBtn.addEventListener("click", fitToWidth);
    }

    // Previous Page button - smoothly scrolls up to previous page
    const prevPageBtn = document.getElementById('prev-page');
    if (prevPageBtn) {
        prevPageBtn.addEventListener('click', () => {
            if (currentPageNum > 1) {
                const targetPage = currentPageNum - 1;
                const targetEl = document.getElementById(`page-container-${targetPage}`);
                if (targetEl) {
                    targetEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            }
        });
    }

    // Next Page button - smoothly scrolls down to next page
    const nextPageBtn = document.getElementById('next-page');
    if (nextPageBtn) {
        nextPageBtn.addEventListener('click', () => {
            if (currentPageNum < totalPages) {
                const targetPage = currentPageNum + 1;
                const targetEl = document.getElementById(`page-container-${targetPage}`);
                if (targetEl) {
                    targetEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            }
        });
    }

    // Zoom In handler
    const zoomInBtn = document.getElementById('zoom-in');
    if (zoomInBtn) {
        zoomInBtn.addEventListener('click', () => {
            applyScale(scale + 0.15);
        });
    }

    // Zoom Out handler
    const zoomOutBtn = document.getElementById('zoom-out');
    if (zoomOutBtn) {
        zoomOutBtn.addEventListener('click', () => {
            applyScale(scale - 0.15);
        });
    }

    // Load Document with Web CacheStorage
    window.getCachedPdfDocument(pdfUrl).then(async (pdfDoc_) => {
        pdfDoc = pdfDoc_;
        totalPages = pdfDoc.numPages;
        
        const pageCountEl = document.getElementById('page-count');
        if (pageCountEl) {
            pageCountEl.textContent = totalPages;
        }

        // Read Page 1 dimensions to set base aspect ratio
        try {
            const firstPage = await pdfDoc.getPage(1);
            const initialViewport = firstPage.getViewport({ scale: 1.0 });
            basePageWidth = initialViewport.width;
            basePageHeight = initialViewport.height;
        } catch (e) {
            console.warn("Could not read Page 1 viewport:", e);
        }

        // Calculate initial fit-to-width scale
        const availableWidth = canvasWrapper.clientWidth - 28;
        if (availableWidth > 0 && basePageWidth > 0) {
            scale = availableWidth / basePageWidth;
        } else {
            scale = 1.0;
        }

        // Hide main card loader
        const loaderEl = document.getElementById('pdf-loader');
        if (loaderEl) {
            loaderEl.style.display = 'none';
        }

        // Build all page placeholders and start rendering
        buildPagePlaceholders();

    }).catch((err) => {
        console.error("Error loading PDF document:", err);
        const loaderEl = document.getElementById('pdf-loader');
        if (loaderEl) {
            loaderEl.innerHTML = `
                <div style="color: #ef4444; padding: 2rem; text-align: center;">
                    <p>⚠️ Error loading document. Please verify your authentication session or contact the school office.</p>
                    <p style="font-size: 0.8rem; margin-top: 0.5rem; color: #94a3b8;">${err.message}</p>
                </div>
            `;
        }
    });

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
            // Give browser a frame to adjust fullscreen size then fitToWidth
            setTimeout(fitToWidth, 100);
        });
    }

    // Automatically re-scale PDF width on screen/window size changes
    window.addEventListener("resize", () => {
        if (pdfDoc) {
            fitToWidth();
        }
    });
});
