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