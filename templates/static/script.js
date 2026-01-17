window.addEventListener('scroll', function() {
    let header = document.querySelector('header');
    let windowPosition = window.scrollY > 0;
    header.classList.toggle('scrolling-active', windowPosition);
});

// Navigation functions
function openNav() {
    document.getElementById("myNav").style.width = "100%";
}

function closeNav() {
    document.getElementById("myNav").style.width = "0%";
}

function openMobileNav() {
    const sidenav = document.getElementById("mySidenav");
    const navIcon = document.getElementById("navIcon");

    sidenav.style.width = "250px";
    navIcon.style.display = "None";

    // Update ARIA states for accessibility
    navIcon.setAttribute('aria-expanded', 'true');
    sidenav.setAttribute('aria-hidden', 'false');

    // Focus on close button for keyboard navigation
    setTimeout(() => {
        const closeBtn = document.querySelector('.closebtnMobile');
        if (closeBtn) {
            closeBtn.focus();
        }
    }, 100);

    // Prevent body scroll when menu is open
    document.body.style.overflow = 'hidden';
}

function closeMobileNav() {
    const sidenav = document.getElementById("mySidenav");
    const navIcon = document.getElementById("navIcon");

    sidenav.style.width = "0";
    navIcon.style.display = "Block";

    // Update ARIA states for accessibility
    navIcon.setAttribute('aria-expanded', 'false');
    sidenav.setAttribute('aria-hidden', 'true');

    // Return focus to hamburger button
    navIcon.focus();

    // Restore body scroll
    document.body.style.overflow = '';
}

// Add keyboard support for mobile nav
document.addEventListener('DOMContentLoaded', function() {
    const navIcon = document.getElementById("navIcon");
    const sidenav = document.getElementById("mySidenav");

    // Keyboard support for hamburger button (Enter/Space)
    if (navIcon) {
        navIcon.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                openMobileNav();
            }
        });
    }

    // Close menu with Escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && sidenav && sidenav.style.width === '250px') {
            closeMobileNav();
        }
    });

    // Close menu when clicking outside
    document.addEventListener('click', function(e) {
        if (sidenav && sidenav.style.width === '250px') {
            if (!sidenav.contains(e.target) && !navIcon.contains(e.target)) {
                closeMobileNav();
            }
        }
    });
});

// ===== DROPDOWN NAVIGATION FUNCTIONS =====

// Toggle dropdown on click (for keyboard users)
function toggleDropdown(button) {
    const dropdown = button.parentElement;
    const content = dropdown.querySelector('.dropdown-content');
    const isExpanded = button.getAttribute('aria-expanded') === 'true';

    // Close all other dropdowns
    document.querySelectorAll('.dropdown').forEach(d => {
        const toggle = d.querySelector('.dropdown-toggle');
        const dropdownContent = d.querySelector('.dropdown-content');
        if (toggle && dropdownContent) {
            toggle.setAttribute('aria-expanded', 'false');
            dropdownContent.style.display = 'none';
            dropdownContent.style.visibility = 'hidden';
            dropdownContent.style.opacity = '0';
        }
    });

    // Toggle current dropdown
    button.setAttribute('aria-expanded', !isExpanded);
    if (isExpanded) {
        content.style.display = 'none';
        content.style.visibility = 'hidden';
        content.style.opacity = '0';
    } else {
        content.style.display = 'block';
        content.style.visibility = 'visible';
        content.style.opacity = '1';
    }
}

// Close dropdown when clicking outside
document.addEventListener('click', function(event) {
    if (!event.target.closest('.dropdown')) {
        document.querySelectorAll('.dropdown').forEach(dropdown => {
            const toggle = dropdown.querySelector('.dropdown-toggle');
            const content = dropdown.querySelector('.dropdown-content');
            if (toggle && content) {
                toggle.setAttribute('aria-expanded', 'false');
                content.style.display = 'none';
            }
        });
    }
});

// Keyboard navigation for dropdowns
document.addEventListener('keydown', function(event) {
    const activeDropdown = document.querySelector('.dropdown [aria-expanded="true"]')?.parentElement;
    if (!activeDropdown) return;

    const items = activeDropdown.querySelectorAll('.dropdown-content a');
    const currentIndex = Array.from(items).indexOf(document.activeElement);

    switch(event.key) {
        case 'ArrowDown':
            event.preventDefault();
            if (currentIndex < items.length - 1) {
                items[currentIndex + 1].focus();
            } else if (currentIndex === -1 && items.length > 0) {
                items[0].focus();
            }
            break;
        case 'ArrowUp':
            event.preventDefault();
            if (currentIndex > 0) {
                items[currentIndex - 1].focus();
            }
            break;
        case 'Escape':
            event.preventDefault();
            const toggle = activeDropdown.querySelector('.dropdown-toggle');
            if (toggle) {
                toggle.click();
                toggle.focus();
            }
            break;
    }
});

// ===========================
// ERROR HANDLING WITH RETRY
// ===========================

/**
 * Fetch with automatic retry functionality
 * @param {string} url - The URL to fetch
 * @param {object} options - Fetch options
 * @param {number} maxRetries - Maximum number of retries (default: 3)
 * @param {number} delay - Delay between retries in ms (default: 1000)
 * @returns {Promise} - Fetch response
 */
async function fetchWithRetry(url, options = {}, maxRetries = 3, delay = 1000) {
    let lastError;

    for (let attempt = 0; attempt <= maxRetries; attempt++) {
        try {
            const response = await fetch(url, options);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            return response;
        } catch (error) {
            lastError = error;
            console.warn(`Fetch attempt ${attempt + 1} failed:`, error.message);

            if (attempt < maxRetries) {
                // Exponential backoff
                const waitTime = delay * Math.pow(2, attempt);
                await new Promise(resolve => setTimeout(resolve, waitTime));
            }
        }
    }

    throw lastError;
}

/**
 * Show inline error message with retry button
 * @param {HTMLElement} container - Container to show error in
 * @param {string} message - Error message
 * @param {function} retryCallback - Function to call on retry
 */
function showInlineError(container, message, retryCallback) {
    const errorHtml = `
        <div class="inline-error">
            <div class="inline-error-icon">
                <i class="fas fa-exclamation-circle"></i>
            </div>
            <div class="inline-error-content">
                <p class="inline-error-message">${escapeHtml(message)}</p>
                <button class="inline-error-retry" onclick="this.closest('.inline-error').remove(); (${retryCallback.toString()})();">
                    <i class="fas fa-redo"></i> Try Again
                </button>
            </div>
        </div>
    `;

    container.innerHTML = errorHtml;
}

/**
 * Show toast notification for errors
 * @param {string} message - Error message
 * @param {string} type - Type: 'error', 'warning', 'success'
 * @param {number} duration - Duration in ms (default: 5000)
 */
function showToast(message, type = 'error', duration = 5000) {
    // Remove existing toast
    const existingToast = document.querySelector('.toast-notification');
    if (existingToast) {
        existingToast.remove();
    }

    const icons = {
        error: 'fa-exclamation-circle',
        warning: 'fa-exclamation-triangle',
        success: 'fa-check-circle',
        info: 'fa-info-circle'
    };

    const toast = document.createElement('div');
    toast.className = `toast-notification toast-${type}`;
    toast.innerHTML = `
        <i class="fas ${icons[type] || icons.info}"></i>
        <span>${escapeHtml(message)}</span>
        <button class="toast-close" onclick="this.parentElement.remove()">
            <i class="fas fa-times"></i>
        </button>
    `;

    document.body.appendChild(toast);

    // Animate in
    requestAnimationFrame(() => {
        toast.classList.add('show');
    });

    // Auto remove
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Add toast and inline error styles dynamically
(function addErrorStyles() {
    if (document.getElementById('error-handler-styles')) return;

    const styles = document.createElement('style');
    styles.id = 'error-handler-styles';
    styles.textContent = `
        /* Toast Notifications */
        .toast-notification {
            position: fixed;
            bottom: 20px;
            right: 20px;
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 14px 20px;
            background: white;
            border-radius: 10px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
            z-index: 10000;
            transform: translateX(120%);
            transition: transform 0.3s ease;
            max-width: 400px;
        }

        .toast-notification.show {
            transform: translateX(0);
        }

        .toast-error {
            border-left: 4px solid #dc3545;
        }

        .toast-error i:first-child {
            color: #dc3545;
        }

        .toast-warning {
            border-left: 4px solid #ffc107;
        }

        .toast-warning i:first-child {
            color: #ffc107;
        }

        .toast-success {
            border-left: 4px solid #28a745;
        }

        .toast-success i:first-child {
            color: #28a745;
        }

        .toast-info {
            border-left: 4px solid #17a2b8;
        }

        .toast-info i:first-child {
            color: #17a2b8;
        }

        .toast-notification span {
            flex: 1;
            font-size: 0.95rem;
            color: #333;
        }

        .toast-close {
            background: none;
            border: none;
            padding: 4px;
            cursor: pointer;
            color: #999;
            transition: color 0.2s;
        }

        .toast-close:hover {
            color: #333;
        }

        /* Inline Error */
        .inline-error {
            display: flex;
            align-items: center;
            gap: 1rem;
            padding: 1.5rem;
            background: #fff5f5;
            border: 1px solid #ffebeb;
            border-left: 4px solid #dc3545;
            border-radius: 8px;
            margin: 1rem 0;
        }

        .inline-error-icon {
            font-size: 2rem;
            color: #dc3545;
        }

        .inline-error-content {
            flex: 1;
        }

        .inline-error-message {
            margin: 0 0 0.75rem;
            color: #721c24;
            font-size: 0.95rem;
        }

        .inline-error-retry {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.5rem 1rem;
            background: #670000;
            color: white;
            border: none;
            border-radius: 6px;
            font-size: 0.9rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .inline-error-retry:hover {
            background: #a70000;
            transform: translateY(-1px);
        }
        
        @media (max-width: 480px) {
            .toast-notification {
                left: 10px;
                right: 10px;
                bottom: 10px;
                max-width: none;
            }

            .inline-error {
                flex-direction: column;
                text-align: center;
            }
        }
    `;

    document.head.appendChild(styles);
})();