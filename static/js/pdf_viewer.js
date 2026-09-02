// Secure Multi-Page Canvas-Based Scrollable PDF Viewer using PDF.js

// Helper function to fetch & cache PDF ArrayBuffers in browser CacheStorage
window.getCachedPdfDocument = async function(pdfUrl) {
    const pdfjsLib = window['pdfjs-dist/build/pdf'];
    if (!pdfjsLib) throw new Error("PDF.js library not loaded");

    if (!('caches' in window)) {
        return pdfjsLib.getDocument(pdfUrl).promise;
    }

    try {
        const cache = await caches.open('lundayang-pdf-cache-v1');
        const cachedResponse = await cache.match(pdfUrl);

        if (cachedResponse) {
            const arrayBuffer = await cachedResponse.arrayBuffer();
            return pdfjsLib.getDocument({ data: arrayBuffer }).promise;
        }

        const response = await fetch(pdfUrl);
        if (!response.ok) {
            throw new Error(`Failed to fetch PDF document (${response.status})`);
        }

        await cache.put(pdfUrl, response.clone());
        const arrayBuffer = await response.arrayBuffer();
        return pdfjsLib.getDocument({ data: arrayBuffer }).promise;
    } catch (err) {
        console.warn("[PDF Cache] Web cache failed, falling back to direct URL fetch:", err);
        return pdfjsLib.getDocument(pdfUrl).promise;
    }
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

            // Burn watermark directly into canvas
            burnWatermarkOnCanvas(canvas, ctx);

            // Hide placeholder skeleton
            if (skeleton) {
                skeleton.style.display = 'none';
            }

            state.rendered = true;
            state.rendering = false;
            state.renderedScale = scale;
            state.renderTask = null;

            // Render PDF.js Text Layer for text selection and copy/paste
            if (textLayerDiv) {
                textLayerDiv.innerHTML = '';
                textLayerDiv.style.width = `${viewport.width}px`;
                textLayerDiv.style.height = `${viewport.height}px`;
                textLayerDiv.style.setProperty('--scale-factor', viewport.scale);

                try {
                    const textContent = await page.getTextContent();
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
