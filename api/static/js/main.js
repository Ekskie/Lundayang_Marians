// Global Javascript functionality for Lundayang Marians

document.addEventListener("DOMContentLoaded", () => {
    // 1. FAQ Accordion Collapse/Expand
    const faqQuestions = document.querySelectorAll(".faq-question");
    faqQuestions.forEach(q => {
        q.addEventListener("click", () => {
            const item = q.parentElement;
            const isActive = item.classList.contains("active");
            
            // Close all other FAQ items
            document.querySelectorAll(".faq-item").forEach(i => i.classList.remove("active"));
            
            // Toggle current FAQ item
            if (!isActive) {
                item.classList.add("active");
            }
        });
    });

    // 2. Bookmark Button Async Handler
    const bookmarkToggleBtn = document.getElementById("bookmark-toggle-btn");
    if (bookmarkToggleBtn) {
        bookmarkToggleBtn.addEventListener("click", async () => {
            const paperId = bookmarkToggleBtn.getAttribute("data-paper-id");
            if (!paperId) return;

            try {
                bookmarkToggleBtn.disabled = true;
                const formData = new FormData();
                formData.append("paper_id", paperId);

                const response = await fetch("/bookmark/toggle", {
                    method: "POST",
                    body: formData
                });

                const result = await response.json();
                if (result.success) {
                    if (result.bookmarked) {
                        bookmarkToggleBtn.innerHTML = "★ Bookmarked";
                        bookmarkToggleBtn.classList.remove("btn-outline");
                        bookmarkToggleBtn.classList.add("btn-accent");
                    } else {
                        bookmarkToggleBtn.innerHTML = "☆ Bookmark";
                        bookmarkToggleBtn.classList.remove("btn-accent");
                        bookmarkToggleBtn.classList.add("btn-outline");
                    }
                } else {
                    alert("Error updating bookmark: " + result.error);
                }
            } catch (err) {
                console.error("Bookmark request failed:", err);
                alert("An error occurred. Please try again.");
            } finally {
                bookmarkToggleBtn.disabled = false;
            }
        });
    }

    // 3. Dropdown Menu toggle (Click to toggle, close others)
    const dropdownContainers = document.querySelectorAll(".dropdown-container");
    dropdownContainers.forEach(container => {
        const btn = container.querySelector(".btn-profile-dropdown");
        const menu = container.querySelector(".dropdown-menu");
        if (btn && menu) {
            btn.addEventListener("click", (e) => {
                e.stopPropagation();
                const isShown = menu.classList.contains("show");
                
                // Close all other dropdown menus first
                document.querySelectorAll(".dropdown-menu").forEach(m => m.classList.remove("show"));
                
                // Toggle current
                if (!isShown) {
                    menu.classList.add("show");
                }
            });
        }
    });

    // Close dropdowns when clicking anywhere outside
    document.addEventListener("click", () => {
        document.querySelectorAll(".dropdown-menu").forEach(m => m.classList.remove("show"));
    });
});
