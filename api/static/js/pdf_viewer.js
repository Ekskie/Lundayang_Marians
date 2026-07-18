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

    // Load Document
    pdfjsLib.getDocument(pdfUrl).promise.then((pdfDoc_) => {
        pdfDoc = pdfDoc_;
        document.getElementById('page-count').textContent = pdfDoc.numPages;
        
        // Hide loader and show canvas
        document.getElementById('pdf-loader').style.display = 'none';
        canvas.style.display = 'block';
        
        renderPage(pageNum);
    }).catch((err) => {
        console.error("Error loading PDF document:", err);
        document.getElementById('pdf-loader').innerHTML = `
            <div style="color: #ef4444; padding: 2rem; text-align: center;">
                <p>⚠️ Error loading document. Please verify your authentication session or contact the school office.</p>
                <p style="font-size: 0.8rem; margin-top: 0.5rem; color: #94a3b8;">${err.message}</p>
            </div>
        `;
    });

    // --- SECURITY CONTROLS ---

    // 1. Disable Right-click context menu inside PDF container
    const pdfContainer = document.querySelector(".pdf-viewer-container");
    if (pdfContainer) {
        pdfContainer.addEventListener('contextmenu', e => e.preventDefault());
    }

    // 2. Prevent Common Keyboard Shortcuts (Save, Print, Copy)
    window.addEventListener('keydown', (e) => {
        const isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0;
        const metaKey = isMac ? e.metaKey : e.ctrlKey;
        
        // Prevent Ctrl/Cmd + S (Save), P (Print), C (Copy), A (Select All)
        if (metaKey && (e.key === 's' || e.key === 'p' || e.key === 'c' || e.key === 'a' || e.key === 'S' || e.key === 'P' || e.key === 'C' || e.key === 'A')) {
            e.preventDefault();
            alert("🔒 Downloading, printing, or copying research text is restricted to preserve intellectual property.");
        }
    });

    // 3. Disable Drag/Drop of contents
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
});
