// Secure Canvas-Based PDF Viewer using PDF.js

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
        ctx = canvas.getContext('2d'),
        textLayerRenderTask = null;

    // Render the specified page number
    function renderPage(num) {
        pageRendering = true;
        
        if (textLayerRenderTask) {
            try {
                textLayerRenderTask.cancel();
            } catch (e) {}
            textLayerRenderTask = null;
        }

        pdfDoc.getPage(num).then((page) => {
            const viewport = page.getViewport({ scale: scale });
            canvas.height = viewport.height;
            canvas.width = viewport.width;

            const pageContainer = document.getElementById('pdf-page-container');
            if (pageContainer) {
                pageContainer.style.width = `${viewport.width}px`;
                pageContainer.style.height = `${viewport.height}px`;
            }

            const renderContext = {
                canvasContext: ctx,
                viewport: viewport
            };
            const renderTask = page.render(renderContext);

            // Wait for rendering to finish
            renderTask.promise.then(() => {
                // Burn watermark directly into canvas pixels
                burnWatermarkOnCanvas();
                pageRendering = false;
                if (pageNumPending !== null) {
                    renderPage(pageNumPending);
                    pageNumPending = null;
                }
            });

            // Render PDF.js Text Layer for text selection and copy/paste
            const textLayerDiv = document.getElementById('pdf-text-layer');
            if (textLayerDiv) {
                textLayerDiv.innerHTML = '';
                textLayerDiv.style.width = `${viewport.width}px`;
                textLayerDiv.style.height = `${viewport.height}px`;
                textLayerDiv.style.setProperty('--scale-factor', viewport.scale);

                page.getTextContent().then((textContent) => {
                    if (pdfjsLib.renderTextLayer) {
                        try {
                            textLayerRenderTask = pdfjsLib.renderTextLayer({
                                textContentSource: textContent,
                                textContent: textContent,
                                container: textLayerDiv,
                                viewport: viewport,
                                textDivs: []
                            });
                        } catch (tlErr) {
                            console.warn("renderTextLayer failed:", tlErr);
                        }
                    }
                }).catch(err => {
                    console.warn("Error retrieving text content:", err);
                });
            }
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

    // Load Document with Web CacheStorage
    window.getCachedPdfDocument(pdfUrl).then((pdfDoc_) => {
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
