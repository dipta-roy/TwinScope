document.addEventListener('DOMContentLoaded', () => {
    // Smooth scrolling for navigation links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });

    // Add scroll effect to navigation
    const nav = document.querySelector('.glass-nav');
    window.addEventListener('scroll', () => {
        if (window.scrollY > 50) {
            nav.style.background = 'rgba(255, 255, 255, 0.1)';
            nav.style.boxShadow = '0 8px 32px 0 rgba(0, 0, 0, 0.4)';
        } else {
            nav.style.background = 'rgba(255, 255, 255, 0.05)';
            nav.style.boxShadow = '0 8px 32px 0 rgba(0, 0, 0, 0.3)';
        }
    });

    // Simple interaction effect for feature cards
    const cards = document.querySelectorAll('.feature-card');
    cards.forEach(card => {
        card.addEventListener('mousemove', (e) => {
            const rect = card.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            
            card.style.setProperty('--mouse-x', `${x}px`);
            card.style.setProperty('--mouse-y', `${y}px`);
        });
    });

    // Image Modal Logic
    const modal = document.getElementById("imageModal");
    const modalImg = document.getElementById("modalImg");
    const captionText = document.getElementById("modalCaption");
    const closeBtn = document.querySelector(".close-modal");
    const screenshots = document.querySelectorAll(".screenshot-img");

    screenshots.forEach(img => {
        img.addEventListener('click', function() {
            modal.style.display = "block";
            // Small delay to allow display:block to apply before adding opacity class
            setTimeout(() => modal.classList.add('show'), 10);
            modalImg.src = this.src;
            captionText.innerHTML = this.alt;
        });
    });

    const closeModal = () => {
        modal.classList.remove('show');
        setTimeout(() => modal.style.display = "none", 300);
    };

    if (closeBtn) {
        closeBtn.addEventListener('click', closeModal);
    }

    // Close modal when clicking outside the image
    window.addEventListener('click', (e) => {
        if (e.target === modal) {
            closeModal();
        }
    });

    // Close modal with Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === "Escape" && modal.style.display === "block") {
            closeModal();
        }
    });
});
